"""
Kalshi AI Trading Agent v6 -- Cross-Platform Arbitrage + Bull/Bear Debate + Dashboard
http://localhost:9000

Inspired by:
- ryanfrigo/kalshi-ai-trading-bot (multi-agent ensemble, debate protocol)
- prediction-market-arbitrage-bot (cross-market arbitrage math)
- Ezekiel Njuguna's two-layer architecture (brain/hands separation)

Key innovations over v5:
- POLYMARKET INTEGRATION: Dual-platform trading (Kalshi + Polymarket)
- CROSS-PLATFORM ARBITRAGE: Guaranteed profit when same market mispriced across platforms
- BEST-PRICE ROUTING: Directional trades route to cheapest platform
- QUICK-FLIP SCALPING: Buy cheap contracts (3-15c) with 2x sell targets
- COMPOUNDING TIERS: Dynamic bet sizing that scales with bankroll growth
- Bull vs Bear DEBATE protocol: AI argues both sides before deciding
- Within-market arbitrage scanner (no AI needed, math only)
- Calibration tracking (log predictions to measure accuracy over time)

  python kalshi-agent.py --config kalshi-config.json
"""
import os, sys, json, time, datetime, argparse, traceback, threading

# ── Module imports ──
from modules.config import CFG, SHARED, SHARED_LOCK, log, parse_orderbook_price, load_config
from modules.apis import KalshiAPI, MarketCache, PolymarketAPI, PolymarketCache
from modules.data_fetcher import DataFetcher
from modules.notifier import Notifier, PerformanceReporter
from modules.risk import RiskMgr, ExitManager
from modules.debate import DebateEngine
from modules.scoring import (kelly, calc_hours_left, score_market, filter_and_rank,
    is_execution_eligible, dynamic_min_edge, get_category_kelly_cap,
    debate_spread_kelly_mult, bayesian_kelly_prob, thorp_concurrent_reduction)
from modules.calibration import CalibrationTracker
from modules.execution import build_execution_plan, should_quickflip, MakerOrderManager
from modules.market_state import MARKET_STATE
from modules.arbitrage import (
    match_markets, scan_cross_platform_arbitrage, execute_cross_arb,
    exit_cross_arb, should_rotate_arb, ARB_TRACKER,
    scan_arbitrage, _best_ask, _estimate_slippage, route_order, get_best_price,
    find_quickflip_candidates, get_bankroll_tier, get_dynamic_kelly, BANKROLL_TIERS,
    check_single_market_arb, push_ws_arb, pop_ws_arbs,
)
from modules.dashboard import start_dashboard
from modules.ws_feed import KalshiWSFeed
from modules.news_trigger import NewsTrigger
from modules.combinatorial import CombinatorialScanner


# ════════════════════════════════════════
# AGENT
# ════════════════════════════════════════
class Agent:
    def __init__(self):
        self.api = KalshiAPI(); self.debate = DebateEngine()
        self.risk = RiskMgr(); self.cache = MarketCache(self.api)
        self.data = DataFetcher()
        self.calibration = CalibrationTracker()
        self.notifier = Notifier()
        self.reporter = PerformanceReporter(self.risk, self.notifier)
        self.stop_event = threading.Event()
        # Polymarket integration
        self.poly_enabled = CFG.get("polymarket_enabled", False)
        self.poly_api = None; self.poly_cache = None
        self.cross_platform_matches = []
        self.win_streak = 0; self.loss_cooldown = 0
        self._scan_number = 0
        self._last_orderbook_cache = {}
        self._quickflip_targets = {}  # ticker -> {target_price, side, contracts, entry_time}
        if self.poly_enabled:
            try:
                self.poly_api = PolymarketAPI()
                self.poly_cache = PolymarketCache(self.poly_api)
                SHARED["poly_enabled"] = True
                log.info(f"Polymarket: {'TRADING' if self.poly_api.is_trading_enabled else 'READ-ONLY'} mode")
            except Exception as e:
                log.error(f"Polymarket init failed: {e} -- running Kalshi-only")
                self.poly_enabled = False
        self.exit_mgr = ExitManager(self.api, self.risk, self.notifier, poly_api=self.poly_api)
        self.maker_mgr = MakerOrderManager(self.api)
        self.ws_feed = KalshiWSFeed()
        # Wire real-time arb callback on WS book updates
        if CFG.get("ws_arb_enabled", True):
            def _ws_arb_callback(ticker, book_state):
                opp = check_single_market_arb(ticker, book_state)
                if opp:
                    push_ws_arb(opp)
                    log.debug(f"  WS-ARB queued: {ticker} profit={opp['profit_cents']:.1f}c")
            self.ws_feed.set_arb_callback(_ws_arb_callback)
        # Market maker (zero AI cost revenue layer)
        from modules.market_maker import MarketMaker
        self.market_maker = MarketMaker(self.api)
        if CFG.get("mm_enabled", False):
            self.market_maker.start()
        self._ws_started = False
        # News-triggered AI scanning
        self.news_trigger = NewsTrigger(
            category_rules=CFG.get("category_rules", {}),
            poll_interval_seconds=CFG.get("news_poll_interval_seconds", 60),
            cooldown_seconds=CFG.get("news_cooldown_seconds", 300))
        if CFG.get("news_trigger_enabled", False):
            self.news_trigger.start()
        self._startup_check()

    def _startup_check(self):
        """Verify critical dependencies before starting."""
        checks = []
        try:
            bal = self.api.balance()
            checks.append(f"Kalshi balance: ${bal:.2f}")
        except Exception as e:
            checks.append(f"WARNING: Kalshi API failed: {e}")
        if self.poly_enabled and self.poly_api:
            try:
                pbal = self.poly_api.balance()
                checks.append(f"Polymarket balance: ${pbal:.2f}")
            except Exception as e:
                checks.append(f"WARNING: Polymarket API failed: {e}")
        if CFG.get("anthropic_api_key"):
            checks.append("Anthropic API key: configured")
        else:
            checks.append("WARNING: No Anthropic API key -- AI debate disabled")
        if CFG.get("mm_enabled"):
            checks.append("Market maker: ENABLED")
        else:
            checks.append("Market maker: disabled")
        if CFG.get("news_trigger_enabled"):
            checks.append("News trigger: ENABLED")
        else:
            checks.append("News trigger: disabled (using fixed AI timer)")
        if CFG.get("ws_arb_enabled", True):
            checks.append("WebSocket arb trigger: ENABLED")
        for check in checks:
            log.info(f"  Startup: {check}")

    @staticmethod
    def _clean_title(m):
        """Return a readable title for multi-outcome parlay markets.
        Kalshi parlays have titles like 'yes Kevin Durant: 3+,yes Reed Sheppard: 2+,...'
        which are comma-separated outcome legs. Parse into a concise summary."""
        import re
        title = m.get("title") or ""
        t_lower = title.lower().strip()
        # Detect parlay-style titles: start with yes/no and have multiple comma-separated legs
        if not (t_lower.startswith(("yes ", "no ")) and title.count(",") >= 1):
            return title  # Normal market title, keep as-is
        # Parse outcome legs: split on comma, strip yes/no prefix
        legs = [leg.strip() for leg in title.split(",")]
        clean_legs = []
        for leg in legs:
            # Strip "yes " or "no " prefix
            cleaned = re.sub(r'^(yes|no)\s+', '', leg, flags=re.IGNORECASE).strip()
            if cleaned and cleaned not in clean_legs:
                clean_legs.append(cleaned)
        if not clean_legs:
            return title
        # Summarize: show first 2-3 legs + count
        MAX_SHOWN = 3
        if len(clean_legs) <= MAX_SHOWN:
            summary = " + ".join(clean_legs)
        else:
            summary = " + ".join(clean_legs[:MAX_SHOWN]) + f" +{len(clean_legs) - MAX_SHOWN} more"
        # Add event context if available
        sub = m.get("subtitle") or ""
        if sub:
            return f"{sub}: {summary}"
        return summary

    def _check_quickflip_exits(self):
        """Check open quickflip positions and sell at target or stop out."""
        if not self._quickflip_targets:
            return
        expired = []
        qf_timeout_hrs = CFG.get("quickflip_timeout_hours", 4)
        for tk, qf in list(self._quickflip_targets.items()):
            try:
                age_hrs = (datetime.datetime.now() - qf["entry_time"]).total_seconds() / 3600
                # Timeout: sell at market after N hours
                if age_hrs >= qf_timeout_hrs:
                    log.info(f"  QF TIMEOUT: {tk} held {age_hrs:.1f}h, selling at market")
                    if qf["platform"] == "kalshi":
                        ob = self.api.orderbook(tk)
                        book = ob.get("orderbook", {})
                        side_book = book.get(qf["side"], book.get(f"{qf['side']}_dollars", []))
                        if side_book:
                            current = parse_orderbook_price(side_book[0][0] if isinstance(side_book[0], list) else side_book[0])
                            if current and not CFG.get("dry_run", True):
                                sell_price = max(1, int(current) - 2)
                                sell_side = "no" if qf["side"] == "yes" else "yes"
                                self.api.place_order(tk, sell_side, qf["contracts"], sell_price)
                                log.info(f"  QF TIMEOUT SOLD: {tk} @{sell_price}c (entry was {qf['entry_price']}c)")
                            elif current:
                                log.info(f"  QF TIMEOUT DRY-RUN: would sell {tk} @{int(current)-2}c")
                    expired.append(tk)
                    continue
                # Check if target price reached
                if qf["platform"] == "kalshi":
                    ob = self.api.orderbook(tk)
                    book = ob.get("orderbook", {})
                    side_book = book.get(qf["side"], book.get(f"{qf['side']}_dollars", []))
                    if not side_book:
                        continue
                    current = parse_orderbook_price(side_book[0][0] if isinstance(side_book[0], list) else side_book[0])
                    if current is None:
                        continue
                    if current >= qf["target_price"]:
                        sell_price = max(1, int(qf["target_price"]))
                        if not CFG.get("dry_run", True):
                            sell_side = "no" if qf["side"] == "yes" else "yes"
                            self.api.place_order(tk, sell_side, qf["contracts"], sell_price)
                            log.info(f"  QF TARGET HIT: {tk} @{sell_price}c (entry {qf['entry_price']}c, +{sell_price - qf['entry_price']}c profit)")
                        else:
                            log.info(f"  QF TARGET HIT DRY-RUN: {tk} @{sell_price}c (entry {qf['entry_price']}c)")
                        # Record profit
                        pnl = qf["contracts"] * (sell_price - qf["entry_price"]) / 100
                        self.risk.day_pnl += pnl
                        for t in reversed(self.risk.trades):
                            if t.get("ticker") == tk and t.get("status") == "open" and "Quick-flip" in t.get("evidence", ""):
                                t["status"] = "win"; t["exit_price"] = sell_price
                                t["pnl"] = round(pnl, 2); t["exit_reason"] = "QF target hit"
                                t["exit_time"] = datetime.datetime.now().isoformat()
                                break
                        self.risk._save()
                        expired.append(tk)
                    # Stop-loss: if price dropped 50% from entry, cut losses
                    elif current <= qf["entry_price"] * 0.5:
                        sell_price = max(1, int(current) - 1)
                        if not CFG.get("dry_run", True):
                            sell_side = "no" if qf["side"] == "yes" else "yes"
                            self.api.place_order(tk, sell_side, qf["contracts"], sell_price)
                            log.info(f"  QF STOP-LOSS: {tk} @{sell_price}c (entry {qf['entry_price']}c)")
                        else:
                            log.info(f"  QF STOP-LOSS DRY-RUN: {tk} @{sell_price}c (entry {qf['entry_price']}c)")
                        pnl = qf["contracts"] * (sell_price - qf["entry_price"]) / 100
                        self.risk.day_pnl += pnl
                        for t in reversed(self.risk.trades):
                            if t.get("ticker") == tk and t.get("status") == "open" and "Quick-flip" in t.get("evidence", ""):
                                t["status"] = "loss"; t["exit_price"] = sell_price
                                t["pnl"] = round(pnl, 2); t["exit_reason"] = "QF stop-loss"
                                t["exit_time"] = datetime.datetime.now().isoformat()
                                break
                        self.risk._save()
                        expired.append(tk)
            except Exception as e:
                log.debug(f"  QF exit check failed for {tk}: {e}")
        for tk in expired:
            del self._quickflip_targets[tk]
        if expired:
            log.info(f"Quick-flip exits: {len(expired)} positions closed, {len(self._quickflip_targets)} still open")

    def _check_calibration_outcomes(self):
        """Check if any predicted markets have settled and record outcomes."""
        pending = [r for r in self.calibration.records if r.get("resolved") is None]
        if not pending:
            return
        pending_tickers = list(set(r["ticker"] for r in pending))[:20]  # batch limit
        try:
            settlements = self.api.settled_markets(pending_tickers)
            for tk, resolved_yes in settlements.items():
                self.calibration.record_outcome(tk, resolved_yes)
                log.info(f"  Calibration: {tk} resolved {'YES' if resolved_yes else 'NO'}")
        except Exception as e:
            log.debug(f"Calibration outcome check failed: {e}")

    def _is_ai_scan_due(self):
        mult = CFG.get("ai_scan_interval_multiplier", 5)
        timer_due = self._scan_number % mult == 0
        news_due = self.news_trigger.has_triggers() if CFG.get("news_trigger_enabled", False) else False
        return timer_due or news_due

    def _update_progress(self, phase_num, phase_name, step="", total_phases=4):
        pct = int((phase_num / total_phases) * 100) if total_phases > 0 else 0
        with SHARED_LOCK:
            SHARED["_scan_progress"] = {
                "phase": phase_name, "step": step, "pct": min(pct, 100),
                "total_phases": total_phases, "current_phase": phase_num,
            }

    def _generate_scan_summary(self, scan_type, scan_events):
        """Use Anthropic to generate a brief, readable scan summary."""
        try:
            if not hasattr(self, 'debate') or not self.debate.client:
                return ""
            events_text = "\n".join(f"- {e}" for e in scan_events[-30:])
            resp = self.debate.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content":
                    f"You are a trading agent dashboard assistant. Summarize this scan in 2-4 concise sentences for the user. "
                    f"Focus on: what was found, any trades made (or why not), and key market observations. "
                    f"Use a direct, terminal-style tone. No markdown.\n\n"
                    f"Scan type: {scan_type}\n"
                    f"Events:\n{events_text}"}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            log.debug(f"Scan summary generation failed: {e}")
            return ""

    def scan(self):
        if not SHARED["enabled"]:
            SHARED["status"] = "Disabled"; return
        self._scan_number += 1
        ai_due = self._is_ai_scan_due()
        scan_type = "FULL (arb + AI)" if ai_due else "FAST (arb only)"
        total_phases = 4 if ai_due else 3
        scan_events = []
        SHARED["status"] = "Scanning..."
        self._update_progress(0, "Initializing", "Starting scan...", total_phases)
        log.info("=" * 50); log.info(f"SCAN #{self._scan_number} ({scan_type})")

        # ── BALANCE CHECK ──
        self._update_progress(0, "Initializing", "Checking balances...", total_phases)
        bal = self.api.balance(); SHARED["balance"] = bal
        poly_bal = 0.0
        if self.poly_enabled and self.poly_api:
            try: poly_bal = self.poly_api.balance()
            except Exception as e: log.debug(f"Polymarket balance error: {e}")
            SHARED["poly_balance"] = poly_bal
        combined_bal = bal + poly_bal
        log.info(f"Balance: Kalshi ${bal:.2f} | Polymarket ${poly_bal:.2f} | Combined ${combined_bal:.2f}")
        scan_events.append(f"Balance: Kalshi ${bal:.2f} + Polymarket ${poly_bal:.2f} = ${combined_bal:.2f}")
        # Check calibration outcomes for settled markets
        self._check_calibration_outcomes()
        # Manage resting maker orders (cancel stale, reprice)
        self.maker_mgr.check_and_manage()
        if combined_bal < 1:
            SHARED["status"] = "Low balance"
            scan_events.append("Scan aborted: combined balance below $1")
            with SHARED_LOCK: SHARED["_scan_progress"] = {"phase": "idle", "step": "", "pct": 0, "total_phases": total_phases, "current_phase": 0}
            return

        # ── COMPOUNDING ──
        if CFG.get("compounding_enabled", True):
            tier = get_bankroll_tier(combined_bal)
            kf = get_dynamic_kelly(tier["kelly_fraction"], self.win_streak, self.loss_cooldown)
            if tier["max_bet_per_trade"] > CFG["max_bet_per_trade"]:
                log.info(f"Bankroll tier upgrade: max_bet ${CFG['max_bet_per_trade']:.0f} -> ${tier['max_bet_per_trade']:.0f}")
            active_max_bet = max(CFG["max_bet_per_trade"], tier["max_bet_per_trade"])
            active_max_exposure = max(CFG["max_total_exposure"], tier["max_total_exposure"])
            active_kelly = kf
        else:
            active_max_bet = CFG["max_bet_per_trade"]
            active_max_exposure = CFG["max_total_exposure"]
            active_kelly = CFG["kelly_fraction"]

        self.risk.new_day()
        self._cb_notified = False if not self.risk.paused else getattr(self, '_cb_notified', False)
        with SHARED_LOCK:
            SHARED["_risk_summary"] = self.risk.summary(); SHARED["_trades"] = self.risk.trades
        if self.risk.paused:
            SHARED["status"] = "Paused"
            if not hasattr(self, '_cb_notified') or not self._cb_notified:
                self.notifier.notify_circuit_breaker(self.risk.day_pnl)
                self._cb_notified = True
            return

        # ── LOAD MARKETS ──
        self._update_progress(0, "Initializing", "Loading markets...", total_phases)
        mkts = self.cache.get()
        # Score & rank all markets, then cache the best ones for the dashboard
        scored_short, scored_long = filter_and_rank(mkts)
        all_scored = scored_short + scored_long
        all_scored.sort(key=lambda x: x.get("_score", 0), reverse=True)
        _CACHE_KEYS = ["ticker", "title", "subtitle", "category", "yes_bid", "no_bid",
                       "last_price", "volume", "volume_24h", "close_time", "status", "event_ticker",
                       "yes_ask", "no_ask", "open_time", "result", "platform", "display_price"]
        with SHARED_LOCK:
            SHARED["_cached_markets"] = [
                {**{k: m.get(k) for k in _CACHE_KEYS},
                 "category": m.get("_category", m.get("category", "")),
                 "title": self._clean_title(m),
                 "_score": m.get("_score", 0)}
                for m in (all_scored if all_scored else mkts)[:200]
            ]
        poly_mkts = []
        if self.poly_enabled and self.poly_cache:
            try:
                poly_mkts = self.poly_cache.get()
                log.info(f"Polymarket: {len(poly_mkts)} markets loaded")
            except Exception as e:
                log.error(f"Polymarket market load failed: {e}")
        for m in mkts:
            if "platform" not in m: m["platform"] = "kalshi"

        # ── START WEBSOCKET FEED (first scan only) ──
        if not self._ws_started and all_scored:
            ws_tickers = [m["ticker"] for m in all_scored[:30] if m.get("ticker")]
            if ws_tickers:
                self.ws_feed.start(ws_tickers)
                self._ws_started = True

        # ── PRE-FETCH LIVE DATA ──
        self._update_progress(0, "Initializing", "Fetching live data...", total_phases)
        scan_events.append(f"Loaded {len(mkts)} Kalshi markets" + (f" + {len(poly_mkts)} Polymarket markets" if poly_mkts else ""))
        SHARED["status"] = "Fetching live data..."
        cat_rules = CFG.get("category_rules", {})
        active_categories = set()
        for m in mkts:
            text = " ".join(str(m.get(k, "")) for k in ["title", "ticker", "category", "subtitle"]).lower()
            for cat_name, cat_kws in cat_rules.items():
                if any(kw in text for kw in cat_kws):
                    active_categories.add(cat_name); break
        if active_categories:
            log.info(f"Active market categories: {', '.join(sorted(active_categories))}")
        self.data.fetch_all(market_categories=active_categories if active_categories else None)

        # ══════════════════════════════════════
        # PHASE 0: CRYPTO MARKET MAKING (zero AI cost)
        # ══════════════════════════════════════
        if CFG.get("mm_enabled", False):
            self._update_progress(0, "Market Making", "Scanning crypto brackets...", total_phases + 1)
            try:
                from modules.crypto_markets import CryptoMarketDiscovery, BTCPriceFeed

                if not hasattr(self, '_crypto_discovery'):
                    self._crypto_discovery = CryptoMarketDiscovery(self.api)
                    self._btc_feed = BTCPriceFeed()

                # Refresh BTC price
                btc_price = self._btc_feed.fetch()
                if btc_price:
                    log.info(f"  BTC price: ${btc_price:,.2f}")

                # Discover active events
                events = self._crypto_discovery.scan_active_events()

                for event in events:
                    # Check for sum-to-100 arbitrage
                    sum_arb = event.find_sum_arb()
                    if sum_arb:
                        log.info(f"  SUM ARB: {event.event_ticker} -- {sum_arb}")
                        scan_events.append(f"SUM-ARB: {event.event_ticker}")

                    # Quote active brackets
                    candidates = event.active_brackets(
                        min_volume=CFG.get("mm_min_volume", 0))
                    top_n = CFG.get("mm_max_markets_per_event", 5)

                    for bracket in candidates[:top_n]:
                        fair_value = self._btc_feed.bracket_fair_value(
                            bracket, btc_price)
                        if 5 <= fair_value <= 95:
                            self.market_maker.quote_market(
                                bracket["ticker"],
                                fair_value_cents=fair_value,
                                event_ticker=event.event_ticker)

                # Check for filled orders
                new_fills = self.market_maker.check_fills()
                if new_fills:
                    log.info(f"  MM: {len(new_fills)} new fills detected")
                    for f in new_fills:
                        self.notifier.send(
                            f"MM Fill: {f['ticker']}",
                            f"{f['side']} {f['size']}x @{f['price_cents']}c")

                mm_summary = self.market_maker.summary()
                scan_events.append(
                    f"MM: {mm_summary['markets_quoted']} markets, "
                    f"{mm_summary['active_quotes']} quotes, "
                    f"fills={mm_summary['total_fills']}")

            except Exception as e:
                log.error(f"  Market making phase failed: {e}")

        # ══════════════════════════════════════
        # PHASE 1: CROSS-PLATFORM ARBITRAGE
        # ══════════════════════════════════════
        if self.poly_enabled and poly_mkts and self.poly_api and CFG.get("cross_arb_enabled", True):
            self._update_progress(1, "Cross-Platform Arb", "Matching markets...", total_phases)
            SHARED["status"] = "Cross-platform arbitrage scan..."
            log.info("Phase 1: Cross-platform arbitrage scan...")
            try:
                kws = CFG["target_keywords"]; cat_rules = CFG.get("category_rules", {})
                for pm in poly_mkts:
                    text = " ".join(str(pm.get(k, "")) for k in ["title", "subtitle", "event_ticker"]).lower()
                    pm["_category"] = "other"
                    best_cat_score = 0
                    for cat_name, cat_kws in cat_rules.items():
                        hits = sum(1 for kw in cat_kws if kw in text)
                        if hits > best_cat_score: best_cat_score = hits; pm["_category"] = cat_name

                threshold = CFG.get("cross_arb_match_threshold", 0.70)
                self.cross_platform_matches = match_markets(mkts, poly_mkts, threshold)
                log.info(f"  Cross-platform matches: {len(self.cross_platform_matches)}")
                for match in self.cross_platform_matches[:5]:
                    log.info(f"    {match['kalshi'].get('title', '')[:35]} <-> {match['polymarket'].get('title', '')[:35]} (sim:{match['similarity']:.2f})")

                cross_arbs = scan_cross_platform_arbitrage(
                    self.cross_platform_matches, self.api, self.poly_api,
                    fee_kalshi=CFG["taker_fee_per_contract"],
                    fee_poly=CFG.get("polymarket_fee_per_contract", 0.00))
                SHARED["_cross_arb_opportunities"] = len(cross_arbs)

                scan_events.append(f"Phase 1: {len(self.cross_platform_matches)} cross-platform matches, {len(cross_arbs)} arb opportunities")
                if cross_arbs:
                    for ca in cross_arbs[:3]:
                        log.info(f"  CROSS-ARB: {ca['title'][:40]} -- {ca['strategy_desc']} -- profit: {ca['profit_cents']:.1f}c")
                        try:
                                result = execute_cross_arb(self.api, self.poly_api, ca,
                                    max_cost=CFG.get("cross_arb_max_cost", 10.0), dry_run=CFG.get("dry_run", True))
                                if result["success"]:
                                    log.info(f"  CROSS-ARB EXECUTED: {result['contracts']}x profit=${result['expected_profit']:.2f}")
                                    self.risk.record(ca["kalshi_ticker"], ca["title"], "cross_arb",
                                        result["contracts"], int(ca["cost_cents"]), 99,
                                        int(ca["profit_cents"]), f"Cross-arb: {ca['strategy_desc']}", 0, 0,
                                        platform="cross")
                                    self.notifier.notify_arbitrage({
                                        "ticker": ca["kalshi_ticker"], "title": ca["title"],
                                        "yes_price": ca.get("k_price", 0), "no_price": ca.get("p_price", 0),
                                        "total_cost": ca["cost_cents"], "profit_cents": ca["profit_cents"]})
                                elif result.get("naked_position"):
                                    log.error(f"  CROSS-ARB: NAKED POSITION -- Leg 1 filled but Leg 2 failed!")
                                    self.notifier.send("ALERT: Naked Arb Position",
                                        f"Cross-arb Leg 2 failed!\nMarket: {ca['title']}\n"
                                        f"Kalshi leg filled but Polymarket leg FAILED.\n"
                                        f"Manual intervention may be needed.")
                        except Exception as ex:
                                log.error(f"  Cross-arb execution failed: {ex}")
                else:
                    log.info("  No cross-platform arbitrage found")

                # ── ROTATION CHECK ──
                # If we have open arb positions, check if any new opportunity
                # is profitable enough to justify exiting and rotating
                open_arb_positions = ARB_TRACKER.get_open_positions()
                if open_arb_positions and cross_arbs:
                    use_parallel = CFG.get("arb_parallel_execution", False)
                    min_improve = CFG.get("arb_rotation_min_improvement_cents", 3.0)
                    rotations = should_rotate_arb(
                        open_arb_positions, cross_arbs,
                        kalshi_fee=CFG["taker_fee_per_contract"],
                        poly_fee=CFG.get("polymarket_fee_per_contract", 0.02),
                        min_improvement_cents=min_improve)

                    max_rotations = CFG.get("arb_max_rotations_per_scan", 1)
                    for rot in rotations[:max_rotations]:
                        exit_pos = rot["exit_position"]
                        enter_opp = rot["enter_opportunity"]
                        log.info(f"  ROTATION: Exit {exit_pos['kalshi_ticker']} "
                                 f"(profit {rot['current_profit']:.1f}c) -> "
                                 f"Enter {enter_opp['kalshi_ticker']} "
                                 f"(profit {rot['new_profit']:.1f}c) "
                                 f"net improvement: +{rot['net_improvement']:.1f}c")
                        scan_events.append(
                            f"ROTATION: {exit_pos['kalshi_ticker']} -> {enter_opp['kalshi_ticker']} "
                            f"(+{rot['net_improvement']:.1f}c improvement)")

                        # Exit current position
                        exit_result = exit_cross_arb(
                            self.api, self.poly_api, exit_pos,
                            dry_run=CFG.get("dry_run", True),
                            parallel=use_parallel)

                        if exit_result.get("success"):
                            # Enter new position
                            enter_result = execute_cross_arb(
                                self.api, self.poly_api, enter_opp,
                                max_cost=CFG.get("cross_arb_max_cost", 10.0),
                                dry_run=CFG.get("dry_run", True),
                                parallel=use_parallel)

                            if enter_result.get("success"):
                                log.info(f"  ROTATION COMPLETE: "
                                         f"{enter_result['contracts']}x, "
                                         f"expected profit ${enter_result['expected_profit']:.2f}")
                                self.notifier.send(
                                    f"ARB ROTATION: {enter_opp.get('title', '')[:40]}",
                                    f"Exited: {exit_pos['kalshi_ticker']}\n"
                                    f"Entered: {enter_opp['kalshi_ticker']}\n"
                                    f"Net improvement: +{rot['net_improvement']:.1f}c\n"
                                    f"Expected profit: ${enter_result['expected_profit']:.2f}")
                            else:
                                log.error(f"  ROTATION ENTRY FAILED: {enter_result.get('reason')}")
                        else:
                            log.error(f"  ROTATION EXIT FAILED: {exit_result.get('reason')}")

            except Exception as e:
                log.error(f"Cross-platform arb phase failed: {e}")

        # ══════════════════════════════════════
        # PHASE 2: WITHIN-MARKET ARBITRAGE
        # ══════════════════════════════════════
        self._update_progress(2, "Within-Market Arb", "Draining WS arb queue...", total_phases)

        # Drain WS-detected arb opportunities first (real-time, no REST needed)
        ws_arbs = pop_ws_arbs(max_age_seconds=30)
        if ws_arbs:
            log.info(f"Phase 2: {len(ws_arbs)} WS-detected arb opportunities")
            for wa in ws_arbs[:3]:
                log.info(f"  WS-ARB: {wa['ticker']} -- yes:{wa['yes_price']:.0f}c + no:{wa['no_price']:.0f}c = {wa['total_cost']:.0f}c -- profit: {wa['profit_cents']:.1f}c")
                try:
                    if CFG.get("dry_run", True):
                        log.info(f"  WS-ARB DRY-RUN: would place YES+NO on {wa['ticker']}")
                    else:
                        self.api.place_order(wa["ticker"], "yes", 1, int(wa["yes_price"]))
                        self.api.place_order(wa["ticker"], "no", 1, int(wa["no_price"]))
                    log.info(f"  WS-ARB EXECUTED: {wa['ticker']}")
                    self.risk.record(wa["ticker"], wa.get("title", ""), "ws_arb", 1, int(wa["total_cost"]),
                        99, int(wa["profit_cents"]), "WS Arbitrage: YES+NO < $1", 0, 0)
                    self.notifier.notify_arbitrage(wa)
                except Exception as ex:
                    log.error(f"  WS-ARB failed: {ex}")
            scan_events.append(f"Phase 2 (WS): {len(ws_arbs)} real-time arb opportunities")

        self._update_progress(2, "Within-Market Arb", "Scanning orderbooks...", total_phases)
        if not CFG.get("within_arb_enabled", True):
            log.info("Phase 2: SKIPPED (within_arb_enabled=false)")
            arb_opps = []
            scan_events.append("Phase 2: Skipped (disabled)")
        else:
            log.info("Phase 2: Within-market arbitrage scan...")
            arb_opps = scan_arbitrage(self.api, mkts, ob_cache=self._last_orderbook_cache)
        SHARED["_arb_opportunities"] = len(arb_opps) + SHARED.get("_cross_arb_opportunities", 0)
        if arb_opps:
            scan_events.append(f"Phase 2: {len(arb_opps)} within-market arb opportunities found")
        else:
            scan_events.append("Phase 2: No within-market arbitrage found")
        if arb_opps:
            for a in arb_opps[:3]:
                log.info(f"  ARB: {a['ticker']} -- yes:{a['yes_price']:.0f}c + no:{a['no_price']:.0f}c = {a['total_cost']:.0f}c -- profit: {a['profit_cents']:.1f}c")
                try:
                    if CFG.get("dry_run", True):
                        log.info(f"  ARB DRY-RUN: would place YES+NO on {a['ticker']}")
                    else:
                        self.api.place_order(a["ticker"], "yes", 1, int(a["yes_price"]))
                        self.api.place_order(a["ticker"], "no", 1, int(a["no_price"]))
                    log.info(f"  ARB EXECUTED: {a['ticker']}")
                    self.risk.record(a["ticker"], a["title"], "arb", 1, int(a["total_cost"]),
                        99, int(a["profit_cents"]), "Arbitrage: YES+NO < $1", 0, 0)
                    self.notifier.notify_arbitrage(a)
                except Exception as ex:
                    log.error(f"  ARB failed: {ex}")
        else:
            log.info("  No within-market arbitrage found (normal)")

        # Combinatorial arbitrage scan (threshold + mutual exclusion)
        try:
            combo_scanner = CombinatorialScanner()
            combo_groups = combo_scanner.group_related_markets(mkts)
            combo_arbs = combo_scanner.scan_all(combo_groups)
            if combo_arbs:
                log.info(f"  COMBO-ARB: {len(combo_arbs)} combinatorial arb opportunities")
                for ca in combo_arbs[:3]:
                    log.info(f"    {ca['type']}: {ca.get('description', '')[:60]} profit={ca['profit_cents']:.1f}c")
                scan_events.append(f"Phase 2 (combo): {len(combo_arbs)} combinatorial arb opportunities")
                SHARED["_arb_opportunities"] = SHARED.get("_arb_opportunities", 0) + len(combo_arbs)
        except Exception as e:
            log.debug(f"Combinatorial arb scan failed: {e}")

        # ══════════════════════════════════════
        # PHASE 3: QUICK-FLIP SCAN
        # ══════════════════════════════════════
        self._update_progress(3, "Quick-Flip Scan", "Checking open QF positions...", total_phases)
        # First, check existing quickflip positions for target/stop/timeout exits
        self._check_quickflip_exits()
        self._update_progress(3, "Quick-Flip Scan", "Finding scalp targets...", total_phases)
        if CFG.get("quickflip_enabled", True):
            log.info("Phase 3: Quick-flip scan...")
            try:
                all_scannable = mkts + poly_mkts
                qf_candidates = find_quickflip_candidates(all_scannable,
                    min_price=CFG.get("quickflip_min_price", 3),
                    max_price=CFG.get("quickflip_max_price", 15),
                    min_volume=max(50, CFG.get("min_volume", 10)))
                SHARED["_quickflip_active"] = len(qf_candidates)
                scan_events.append(f"Phase 3: {len(qf_candidates)} quick-flip candidates found")
                if qf_candidates:
                    for qf in qf_candidates[:3]:
                        m = qf["market"]
                        # Execution policy check for quickflip
                        qf_ok, qf_reason = should_quickflip(m)
                        if not qf_ok:
                            log.info(f"  QF BLOCKED: {m.get('title', '')[:40]} -- {qf_reason}")
                            continue
                        log.info(f"  QF: {m.get('title', '')[:40]} -- {qf['side']} @{qf['entry_price']}c target:{qf['target_price']}c ROI:{qf['potential_roi']:.0f}%")
                        qf_max = CFG.get("quickflip_max_bet", 3.0)
                        if qf_max > 0:
                            try:
                                qf_contracts = max(1, int(qf_max / (qf["entry_price"] / 100)))
                                platform = qf.get("platform", "kalshi")
                                tk = m.get("ticker", "")
                                if platform == "kalshi" and tk:
                                    if CFG.get("dry_run", True):
                                        log.info(f"  QF DRY-RUN: {qf['side']} {qf_contracts}x @{qf['entry_price']}c on Kalshi")
                                    else:
                                        self.api.place_order(tk, qf["side"], qf_contracts, qf["entry_price"])
                                        log.info(f"  QF EXECUTED: {qf['side']} {qf_contracts}x @{qf['entry_price']}c on Kalshi")
                                    self.risk.record(tk, m.get("title", ""), qf["side"], qf_contracts,
                                        qf["entry_price"], 50, int(qf["potential_roi"]),
                                        f"Quick-flip: target {qf['target_price']}c", 0, 0, platform="kalshi")
                                    self._quickflip_targets[tk] = {
                                        "target_price": qf["target_price"], "side": qf["side"],
                                        "contracts": qf_contracts, "entry_price": qf["entry_price"],
                                        "entry_time": datetime.datetime.now(), "platform": "kalshi",
                                    }
                                elif platform == "polymarket" and self.poly_api and self.poly_api.is_trading_enabled:
                                    token = m.get("token_id", "")
                                    if token:
                                        if CFG.get("dry_run", True):
                                            log.info(f"  QF DRY-RUN: {qf['side']} {qf_contracts}x @{qf['entry_price']}c on Polymarket")
                                        else:
                                            self.poly_api.place_order(token, qf["side"], qf_contracts, qf["entry_price"])
                                            log.info(f"  QF EXECUTED: {qf['side']} {qf_contracts}x @{qf['entry_price']}c on Polymarket")
                                        self.risk.record(tk, m.get("title", ""), qf["side"], qf_contracts,
                                            qf["entry_price"], 50, int(qf["potential_roi"]),
                                            f"Quick-flip: target {qf['target_price']}c", 0, 0, platform="polymarket")
                                        self._quickflip_targets[tk or token] = {
                                            "target_price": qf["target_price"], "side": qf["side"],
                                            "contracts": qf_contracts, "entry_price": qf["entry_price"],
                                            "entry_time": datetime.datetime.now(), "platform": "polymarket",
                                            "token_id": token,
                                        }
                            except Exception as ex:
                                log.debug(f"  QF execution failed: {ex}")
                else:
                    log.info("  No quick-flip candidates found")
            except Exception as e:
                log.debug(f"Quick-flip phase failed: {e}")

        # ══════════════════════════════════════
        # PHASE 4: AI-DRIVEN DIRECTIONAL TRADING
        # ══════════════════════════════════════
        if not CFG.get("debate_enabled", True):
            log.info("Phase 4: SKIPPED (debate_enabled=false)")
            scan_events.append("Phase 4: Skipped (debate disabled)")
            self._finish_scan(bal, poly_bal, scan_type, scan_events)
            return
        if not ai_due:
            scans_until = CFG.get('ai_scan_interval_multiplier', 5) - (self._scan_number % CFG.get('ai_scan_interval_multiplier', 5))
            log.info(f"Phase 4: SKIPPED (next AI scan in {scans_until} scans)")
            scan_events.append(f"Phase 4: Skipped (AI scan in {scans_until} more scans)")
            self._finish_scan(bal, poly_bal, scan_type, scan_events)
            return
        self._update_progress(4, "AI Analysis", "Running debate engine...", total_phases)
        # Check for news-triggered categories
        news_triggered_cats = {}
        if CFG.get("news_trigger_enabled", False):
            news_triggered_cats = self.news_trigger.get_triggered_categories()
            if news_triggered_cats:
                log.info(f"  NEWS-TRIGGERED AI: categories={list(news_triggered_cats.keys())}")
                for cat, items in news_triggered_cats.items():
                    for item in items[:2]:
                        log.info(f"    {cat}: '{item.title[:60]}'")
                scan_events.append(f"Phase 4: News-triggered categories: {', '.join(news_triggered_cats.keys())}")

        log.info("Phase 4: AI directional trading...")
        short_term, long_term = filter_and_rank(mkts)
        log.info(f"Short-term (<{CFG['max_close_hours']}h): {len(short_term)} | Long-term: {len(long_term)}")

        weather_mkts = [m for m in short_term + long_term if m.get("_category") == "weather"]
        if weather_mkts:
            try: self.data.expand_nws_for_markets(weather_mkts)
            except Exception as e: log.debug(f"NWS expansion failed: {e}")

        # If news-triggered, prioritize markets in triggered categories
        if news_triggered_cats:
            triggered_set = set(news_triggered_cats.keys())
            triggered_markets = [m for m in short_term + long_term
                                 if m.get("_category") in triggered_set]
            if triggered_markets:
                log.info(f"  News-triggered: prioritizing {len(triggered_markets)} markets in {triggered_set}")
                # Put triggered markets first, then fill remaining slots
                other = [m for m in short_term if m.get("_category") not in triggered_set]
                batch = triggered_markets[:CFG["markets_per_scan"]]
                remaining = CFG["markets_per_scan"] - len(batch)
                if remaining > 0:
                    batch.extend(other[:remaining])
            else:
                batch = short_term[:CFG["markets_per_scan"]]
                if long_term: batch.extend(long_term[:max(10, CFG["markets_per_scan"] - len(batch))])
        else:
            batch = short_term[:CFG["markets_per_scan"]]
            if long_term: batch.extend(long_term[:max(10, CFG["markets_per_scan"] - len(batch))])
        if not batch:
            SHARED["status"] = "Idle -- no targets"
            scan_events.append("Phase 4: No market targets found")
            self._finish_scan(bal, poly_bal, scan_type, scan_events)
            return

        existing = set()
        try:
            pos_list = self.api.positions()
            for p in pos_list:
                tk = p.get("ticker", p.get("market_ticker", ""))
                if tk: existing.add(tk)
            with SHARED_LOCK:
                SHARED["_positions"] = pos_list
        except Exception as e:
            log.debug(f"Could not load existing positions: {e}")
        existing.update(self.risk.traded_tickers)

        SHARED["status"] = f"AI scanning {len(batch)} markets..."
        self._update_progress(4, "AI Analysis", f"Quick-scanning {len(batch)} markets...", total_phases)
        log.info(f"Quick-scanning {len(batch)} markets...")
        data_brief = self.data.format_brief_for_scan()
        cands = self.debate.quick_scan(batch, existing, data_brief)
        log.info(f"Candidates: {len(cands)}")
        scan_events.append(f"Phase 4: Scanned {len(batch)} markets, {len(cands)} candidates found")
        if not cands:
            SHARED["status"] = "Idle -- no edge"
            scan_events.append("Phase 4: No edge found in any market")
            self._finish_scan(bal, poly_bal, scan_type, scan_events)
            return

        for c in cands:
            cm = " [CANT-MISS]" if c.get("is_cant_miss") else ""
            log.info(f"  > {c.get('ticker', '?')}: edge~{c.get('initial_edge_estimate', '?')}% {c.get('side', '?')}{cm}")

        poly_match_lookup = {}
        if self.poly_enabled and self.cross_platform_matches:
            for match in self.cross_platform_matches:
                k_ticker = match["kalshi"].get("ticker", "")
                if k_ticker:
                    poly_match_lookup[k_ticker] = match["polymarket"]

        # ── BULL vs BEAR DEBATE on top candidates ──
        debate_total = min(len(cands), CFG["deep_dive_top_n"])
        debate_idx = 0
        for cand in cands[:CFG["deep_dive_top_n"]]:
            if not SHARED["enabled"]: break
            tk = cand.get("ticker", "")
            if not tk or tk in existing: continue
            mkt = next((m for m in mkts if m["ticker"] == tk), None)
            if not mkt: continue
            debate_idx += 1

            hrs = mkt.get("_hrs_left", 9999); cat = mkt.get("_category", "other")
            self._update_progress(4, "AI Analysis", f"Debating {tk} ({debate_idx}/{debate_total})...", total_phases)
            SHARED["status"] = f"Debating {tk}..."
            log.info(f"\n  DEBATE: [{cat.upper()}] {tk} -- {mkt.get('title', '')[:50]}")

            poly_match = poly_match_lookup.get(tk)
            trade_platform = "kalshi"
            ob = None; ob_spread = 999

            if poly_match and self.poly_api:
                try:
                    ob = self.api.orderbook(tk)
                    MARKET_STATE.update_book(tk, ob, source="rest")
                    MARKET_STATE.record_feed_success("kalshi")
                    book = ob.get("orderbook", {})
                    yb = book.get("yes", book.get("yes_dollars", []))
                    nb = book.get("no", book.get("no_dollars", []))
                    if yb and nb:
                        by = parse_orderbook_price(yb[0][0] if isinstance(yb[0], list) else yb[0])
                        bn = parse_orderbook_price(nb[0][0] if isinstance(nb[0], list) else nb[0])
                        if by and bn:
                            ob_spread = int(by + bn - 100) if by + bn > 100 else int(100 - by - bn)
                            log.info(f"  Orderbook (Kalshi): YES={by}c NO={bn}c spread={ob_spread}c")
                except Exception as e:
                    MARKET_STATE.record_feed_error("kalshi")
                    log.debug(f"  Kalshi orderbook error: {e}")
                try:
                    p_token = poly_match.get("token_id", "")
                    if p_token:
                        p_ob = self.poly_api.orderbook(p_token)
                        MARKET_STATE.record_feed_success("polymarket")
                        p_book = p_ob.get("orderbook", {})
                        p_yes = p_book.get("yes", [])
                        if p_yes:
                            p_yes_price = _best_ask(p_yes)
                            log.info(f"  Orderbook (Polymarket): YES={p_yes_price}c")
                except Exception as e:
                    MARKET_STATE.record_feed_error("polymarket")
                    log.debug(f"  Polymarket orderbook error: {e}")
            else:
                try:
                    ob = self.api.orderbook(tk)
                    MARKET_STATE.update_book(tk, ob, source="rest")
                    MARKET_STATE.record_feed_success("kalshi")
                    book = ob.get("orderbook", {})
                    yb = book.get("yes", book.get("yes_dollars", []))
                    nb = book.get("no", book.get("no_dollars", []))
                    if yb and nb:
                        by = parse_orderbook_price(yb[0][0] if isinstance(yb[0], list) else yb[0])
                        bn = parse_orderbook_price(nb[0][0] if isinstance(nb[0], list) else nb[0])
                        if by and bn:
                            ob_spread = int(by + bn - 100) if by + bn > 100 else int(100 - by - bn)
                            log.info(f"  Orderbook: YES={by}c NO={bn}c spread={ob_spread}c")
                        else:
                            log.debug(f"  Orderbook: invalid prices for {tk}")
                except Exception as e:
                    MARKET_STATE.record_feed_error("kalshi")
                    log.debug(f"  Orderbook fetch error for {tk}: {e}")

            if ob_spread > 25:
                log.info(f"  -> SKIP: spread {ob_spread}c too wide (>25c)")
                continue

            r = self.debate.run_debate(mkt, ob, self.data)
            if not r: continue

            log.info(f"  VERDICT: prob={r['probability']}% conf={r['confidence']}% side={r['side']} edge={r['edge']}%")
            log.info(f"  Bull: {r['bull_prob']}% | Bear: {r['bear_prob']}% | Spread: {r['debate_spread']}%")
            log.info(f"  Evidence: {r['evidence'][:70]}")
            if r.get("risk"): log.info(f"  Risk: {r['risk'][:70]}")

            scan_events.append(f"Debate {tk}: {r['side']} prob={r['probability']}% conf={r['confidence']}% edge={r['edge']}% -- {r['evidence'][:80]}")

            if r["side"] == "HOLD": log.info("  -> HOLD"); scan_events.append(f"  {tk}: HOLD -- no action"); continue

            if hrs > CFG["max_close_hours"]:
                if abs(r["edge"]) < CFG["cant_miss_edge_pct"] or r["confidence"] < CFG["cant_miss_min_confidence"]:
                    log.info("  -> SKIP: below cant-miss bar"); continue

            yc = mkt.get("yes_bid", mkt.get("last_price", 50)) or 50

            bp = r["price_cents"]
            side_lower = r["side"].lower()
            if poly_match and self.poly_api and self.poly_api.is_trading_enabled:
                routed_platform, routed_price, routed_ob = get_best_price(
                    tk, self.api, poly_match, self.poly_api, side_lower,
                    CFG["taker_fee_per_contract"], CFG.get("polymarket_fee_per_contract", 0.00))
                if routed_platform and routed_price:
                    trade_platform = routed_platform
                    if bp == 0: bp = routed_price
                    if routed_ob: ob = routed_ob
                    log.info(f"  Best price: {trade_platform} @{routed_price}c")

            if ob and bp == 0:
                book = ob.get("orderbook", {})
                if r["side"] == "YES":
                    yb = book.get("yes", book.get("yes_dollars", []))
                    if yb:
                        parsed = parse_orderbook_price(yb[0][0] if isinstance(yb[0], list) else yb[0])
                        if parsed: bp = parsed
                else:
                    nb = book.get("no", book.get("no_dollars", []))
                    if nb:
                        parsed = parse_orderbook_price(nb[0][0] if isinstance(nb[0], list) else nb[0])
                        if parsed: bp = parsed
            if bp == 0: bp = yc if r["side"] == "YES" else 100 - yc
            bp = max(1, min(99, bp))

            trade_fee = CFG["taker_fee_per_contract"] if trade_platform == "kalshi" else CFG.get("polymarket_fee_per_contract", 0.00)

            # ── Upgrade 1: Bayesian Modified Kelly Probability ──
            # ── Upgrade 8: Realized-Edge Recalibration (adaptive priors) ──
            raw_prob = r["probability"]
            cat_stats = self.calibration.category_stats().get(cat, {})
            prior_a, prior_b = self.calibration.adaptive_prior(cat)
            bayes_prob = bayesian_kelly_prob(
                raw_prob, cat_stats.get("wins", 0), cat_stats.get("total", 0),
                prior_alpha=prior_a, prior_beta=prior_b)
            if abs(bayes_prob - raw_prob) > 1:
                log.info(f"  Bayesian shrinkage: prob {raw_prob}% -> {bayes_prob:.1f}% (cat={cat}, n={cat_stats.get('total', 0)}, prior=({prior_a:.1f},{prior_b:.1f}))")
            pfk = bayes_prob if r["side"] == "YES" else 100 - bayes_prob
            # ── Upgrade 3: Category-Specific Kelly Cap ──
            cat_kelly_cap = get_category_kelly_cap(cat, CFG.get("category_kelly_caps"))
            effective_kelly = min(active_kelly, cat_kelly_cap)
            # ── Upgrade 2: Debate-Spread-Adaptive Kelly Multiplier ──
            ds_mult = debate_spread_kelly_mult(r.get("debate_spread", 0))
            effective_kelly *= ds_mult
            if ds_mult < 1.0:
                log.info(f"  Debate spread {r.get('debate_spread', 0)}% -> Kelly mult {ds_mult:.2f}")
            # ── Upgrade 5: Simultaneous Bet Reduction (Thorp) ──
            n_concurrent = len(existing)
            if n_concurrent > 1:
                effective_kelly = thorp_concurrent_reduction(effective_kelly, n_concurrent)
                log.info(f"  Thorp reduction: {n_concurrent} concurrent bets -> Kelly={effective_kelly:.3f}")
            contracts, cost = kelly(pfk, bp, combined_bal, active_max_bet, trade_fee, effective_kelly)
            if contracts == 0: log.info("  -> Kelly: no bet (EV negative after fees)"); continue

            # ── Upgrade 6: 2x Kelly Safety Ceiling ──
            # Absolute cap: never risk more than 2x the raw Kelly bet
            raw_kelly_bet = active_kelly * combined_bal
            max_allowed_cost = 2.0 * raw_kelly_bet
            if cost > max_allowed_cost and max_allowed_cost > 0:
                capped_contracts = max(1, int(max_allowed_cost / (bp / 100 + trade_fee)))
                log.info(f"  2x Kelly ceiling: {contracts}x -> {capped_contracts}x (cost ${cost:.2f} > 2*Kelly ${max_allowed_cost:.2f})")
                contracts = capped_contracts
                cost = round(contracts * bp / 100, 2)

            # ── Upgrade 4: Dynamic Fee-Drag Minimum Edge ──
            dyn_min = dynamic_min_edge(bp, trade_fee)
            if abs(r["edge"]) < dyn_min:
                log.info(f"  -> SKIP: edge {r['edge']:.1f}% < dynamic min {dyn_min:.1f}% (fee-drag at {bp}c)")
                continue

            # Slippage check
            if ob and contracts > 1:
                book = ob.get("orderbook", {})
                side_asks = book.get("yes" if r["side"] == "YES" else "no", [])
                if side_asks:
                    avg_fill, worst_fill = _estimate_slippage(side_asks, contracts, bp)
                    if avg_fill > bp + 2:
                        log.info(f"  Slippage warning: {contracts}x would fill avg={avg_fill:.1f}c worst={worst_fill}c (target {bp}c)")
                        bp = int(round(avg_fill))
                        cost = round(contracts * bp / 100, 2)

            fees = contracts * trade_fee; total = cost + fees
            net_profit = contracts * (100 - bp) / 100 - fees
            roi_pct = (net_profit / total * 100) if total > 0 else 0
            platform_tag = f"[{trade_platform.upper()}]" if trade_platform != "kalshi" else ""
            log.info(f"  Kelly: {contracts}x {r['side']} @{bp}c = ${cost:.2f} +${fees:.2f}fee {platform_tag}")
            log.info(f"  If correct: ${net_profit:.2f} net ({roi_pct:.0f}% ROI)")

            # Check execution eligibility (liquidity, parlay legs, expiry)
            eligible, elig_reason = is_execution_eligible(mkt)
            if not eligible:
                log.info(f"  -> INELIGIBLE: {elig_reason}"); continue

            ok, reason = self.risk.check(total, r["confidence"], abs(r["edge"]))
            if not ok: log.info(f"  -> BLOCKED: {reason}"); continue
            if net_profit <= 0: log.info("  -> SKIP: not profitable after fees"); continue

            if ob_spread > 0 and abs(r["edge"]) < ob_spread * 0.3:
                log.info(f"  -> SKIP: edge {r['edge']}% too small vs spread {ob_spread}c")
                continue

            # Execution policy: taker vs maker vs no_trade
            book_state = MARKET_STATE.get_book(tk)
            exec_plan = build_execution_plan(
                ticker=tk, side=side_lower, probability=r["probability"],
                confidence=r["confidence"], edge_pct=abs(r["edge"]),
                price_cents=bp, contracts=contracts, hours_left=hrs,
                platform=trade_platform, book=book_state)
            if exec_plan.action == "no_trade":
                log.info(f"  -> NO_TRADE: {exec_plan.reason}"); continue
            # Use execution plan's price and log the decision
            bp = exec_plan.price_cents
            log.info(f"  Execution: {exec_plan.action} @ {bp}c (edge_after_fees={exec_plan.edge_after_fees_pct:.1f}%, urgency={exec_plan.urgency})")

            log.info(f"  * EXECUTE: BUY {r['side'].upper()} {contracts}x {tk} @{bp}c [{cat}] on {trade_platform.upper()}")
            scan_events.append(f"TRADE: BUY {r['side']} {contracts}x {tk} @{bp}c on {trade_platform} (conf={r['confidence']}% edge={r['edge']}%)")
            try:
                if CFG.get("dry_run", True):
                    log.info(f"  DRY-RUN: {exec_plan.action} order not sent")
                    scan_events.append(f"  {tk}: DRY-RUN -- {exec_plan.action} order simulated, not sent")
                elif exec_plan.action == "maker" and trade_platform == "kalshi":
                    self.maker_mgr.place_maker_order(tk, side_lower, contracts, bp)
                else:
                    if trade_platform == "kalshi":
                        res = self.api.place_order(tk, side_lower, contracts, bp)
                        oid = res.get("order", {}).get("order_id", "?")
                        log.info(f"  OK: order {oid} -- {res.get('order', {}).get('status', '?')}")
                    elif trade_platform == "polymarket" and self.poly_api:
                        token = poly_match.get("token_id", "") if side_lower == "yes" else poly_match.get("no_token_id", poly_match.get("token_id", ""))
                        res = self.poly_api.place_order(token, side_lower, contracts, bp)
                        log.info(f"  OK: Polymarket order placed")

                self.risk.record(tk, mkt.get("title", ""), side_lower, contracts, bp,
                    r["confidence"], r["edge"], r["evidence"], r["bull_prob"], r["bear_prob"],
                    probability=r["probability"], platform=trade_platform)
                self.calibration.record_prediction(
                    ticker=tk, side=r["side"], probability=r["probability"],
                    confidence=r["confidence"], market_price=bp, edge=r["edge"],
                    category=cat, bull_prob=r["bull_prob"], bear_prob=r["bear_prob"],
                    debate_spread=r.get("debate_spread", 0))
                self.notifier.notify_trade({"ticker": tk, "title": mkt.get("title", ""),
                    "side": r["side"], "contracts": contracts, "price_cents": bp, "cost": cost,
                    "edge": r["edge"], "confidence": r["confidence"],
                    "bull_prob": r["bull_prob"], "bear_prob": r["bear_prob"], "evidence": r["evidence"],
                    "platform": trade_platform})
                bal = self.api.balance()
                if self.poly_api: poly_bal = self.poly_api.balance()
                with SHARED_LOCK:
                    SHARED["balance"] = bal; SHARED["poly_balance"] = poly_bal
            except Exception as ex: log.error(f"  Order failed: {ex}")
            time.sleep(5)

        self._finish_scan(bal, poly_bal, scan_type, scan_events)

    def _finish_scan(self, kalshi_bal=None, poly_bal=None, scan_type="", scan_events=None):
        with SHARED_LOCK:
            SHARED["_risk_summary"] = self.risk.summary(); SHARED["_trades"] = self.risk.trades
            SHARED["status"] = "Idle"; SHARED["last_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            SHARED["scan_count"] += 1
            if kalshi_bal is not None: SHARED["balance"] = kalshi_bal
            if poly_bal is not None: SHARED["poly_balance"] = poly_bal
            SHARED["_scan_progress"] = {"phase": "idle", "step": "", "pct": 100, "total_phases": 0, "current_phase": 0}
            SHARED["_open_arb_positions"] = len(ARB_TRACKER.get_open_positions())
            SHARED["_arb_tracker_summary"] = {
                "open": len(ARB_TRACKER.get_open_positions()),
                "positions": [
                    {"ticker": p["kalshi_ticker"], "profit": p["entry_profit_cents"],
                     "age_min": round((time.time() - p["entry_time"]) / 60, 1)}
                    for p in ARB_TRACKER.get_open_positions()
                ],
            }
            if hasattr(self, 'market_maker'):
                SHARED["_mm_summary"] = self.market_maker.summary()
            if hasattr(self, 'news_trigger'):
                SHARED["_news_trigger_summary"] = self.news_trigger.summary()
        s = self.risk.summary()
        combined = (kalshi_bal or 0) + (poly_bal or 0)
        log.info(f"\nScan done. {s['day_trades']} trades, exposure {s['exposure']}, combined balance ${combined:.2f}")
        if scan_events:
            scan_events.append(f"Scan complete. {s['day_trades']} day trades, exposure {s['exposure']}, balance ${combined:.2f}")
            summary = self._generate_scan_summary(scan_type, scan_events)
            if summary:
                with SHARED_LOCK:
                    SHARED["_scan_summary"] = summary
                log.info(f"AI Summary: {summary}")

    def run(self):
        iv = CFG["scan_interval_minutes"] * 60
        ai_iv = iv * CFG.get("ai_scan_interval_multiplier", 5)
        log.info(f"Agent running. Arb scan every {CFG['scan_interval_minutes']}m, AI debate every {ai_iv // 60}m. Ctrl+C to stop.")
        SHARED["status"] = "Idle"

        exit_thread = threading.Thread(target=self.exit_mgr.run_loop, args=(self.stop_event,), daemon=True)
        exit_thread.start()
        report_thread = threading.Thread(target=self.reporter.run_loop, args=(self.stop_event,), daemon=True)
        report_thread.start()

        try:
            while True:
                try:
                    if SHARED["enabled"]: self.scan()
                    else: SHARED["status"] = "Disabled"
                except KeyboardInterrupt: raise
                except Exception as e: log.error(f"Scan error: {e}"); traceback.print_exc()
                nxt = datetime.datetime.now() + datetime.timedelta(seconds=iv)
                SHARED["next_scan"] = nxt.strftime("%H:%M:%S")
                log.info(f"Next scan: {nxt.strftime('%H:%M:%S')}")
                try: time.sleep(iv)
                except KeyboardInterrupt: raise
        finally:
            self.stop_event.set()
            self.ws_feed.stop()
            self.news_trigger.stop()


def main():
    ap = argparse.ArgumentParser(description="Kalshi AI Agent v6 -- Cross-Platform Arbitrage")
    ap.add_argument("--config", type=str, help="Path to config JSON file")
    ap.add_argument("--scan-once", action="store_true"); ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--report", action="store_true", help="Generate performance report and exit")
    ap.add_argument("--backtest", action="store_true", help="Run backtest on kalshi-trades.json and exit")
    ap.add_argument("--backtest-json", action="store_true", help="Output backtest results as JSON")
    ap.add_argument("--collect-resolved", action="store_true",
                    help="Fetch recently resolved markets for forward backtesting and exit")
    ap.add_argument("--resolved-output", type=str, default="kalshi-resolved.json",
                    help="Output file for --collect-resolved (default: kalshi-resolved.json)")
    ap.add_argument("--forward-backtest", action="store_true",
                    help="Run forward backtest on resolved markets and exit")
    ap.add_argument("--resolved", type=str, default="kalshi-resolved.json",
                    help="Input file for --forward-backtest (default: kalshi-resolved.json)")
    ap.add_argument("--forward-limit", type=int, default=0,
                    help="Max markets to test in forward backtest (0=all)")
    ap.add_argument("--mm", action="store_true",
                    help="Enable market making on crypto bracket markets (zero AI cost)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Force dry-run mode (default)")
    mode.add_argument("--live", action="store_true", help="Enable live order placement (requires explicit intent)")
    args = ap.parse_args()

    # Use centralized config loader with safe defaults
    # dry_run from config file is IGNORED -- only --live flag can enable live trading
    live_mode = args.live and not args.dry_run
    load_config(config_path=args.config, live_mode=live_mode)

    # Auto-enable Polymarket if keys are provided
    if CFG.get("polymarket_private_key") and not CFG.get("polymarket_enabled"):
        CFG["polymarket_enabled"] = True
        log.info("Polymarket auto-enabled (private key detected)")

    # Enable market making via CLI flag
    if args.mm:
        CFG["mm_enabled"] = True
        CFG["crypto_mm_enabled"] = True

    if args.backtest:
        from modules.backtester import run_backtest, analyze_calibration, format_report
        trades_file = CFG.get("trades_file", "kalshi-trades.json")
        if not os.path.exists(trades_file):
            print(f"Error: {trades_file} not found"); return
        with open(trades_file) as f:
            trades = json.load(f)
        result = run_backtest(trades, initial_bankroll=CFG.get("max_bankroll", 100.0))
        cal_file = CFG.get("calibration_file", "kalshi-calibration.json")
        calibration = None
        if os.path.exists(cal_file):
            with open(cal_file) as f:
                calibration = analyze_calibration(json.load(f))
        if args.backtest_json:
            out = {
                "total_trades": len(result.trades), "wins": result.wins,
                "losses": result.losses, "win_rate": round(result.win_rate, 1),
                "total_pnl": round(result.total_pnl, 2),
                "max_drawdown": round(result.max_drawdown, 2),
                "profit_factor": round(result.profit_factor, 2),
                "sharpe": result.sharpe_estimate,
                "by_category": dict(result.by_category),
                "by_platform": dict(result.by_platform),
            }
            if calibration:
                out["calibration"] = calibration
            print(json.dumps(out, indent=2))
        else:
            print(format_report(result, calibration))
        return

    if args.collect_resolved:
        api = KalshiAPI()
        print("Fetching recently resolved markets...")
        markets = api.closed_markets(limit=200)
        # Load existing resolved data to avoid duplicates
        out_path = args.resolved_output
        existing = []
        if os.path.exists(out_path):
            with open(out_path) as f:
                existing = json.load(f)
        seen = {m["ticker"] for m in existing}
        new_count = 0
        for m in markets:
            ticker = m.get("ticker", "")
            if ticker in seen:
                continue
            result_val = m.get("result", "")
            if result_val not in ("yes", "no"):
                continue
            record = {
                "ticker": ticker,
                "title": m.get("title", ""),
                "category": m.get("category", ""),
                "result": result_val,
                "close_time": m.get("close_time", ""),
                "yes_ask": m.get("yes_ask", 0),
                "no_ask": m.get("no_ask", 0),
                "volume": m.get("volume", 0),
            }
            existing.append(record)
            new_count += 1
        with open(out_path, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"Collected {new_count} new resolved markets ({len(existing)} total) -> {out_path}")
        return

    if args.forward_backtest:
        from modules.forward_backtest import run_forward_backtest, format_forward_report
        from modules.backtester import _infer_category
        resolved_path = args.resolved
        if not os.path.exists(resolved_path):
            print(f"Error: {resolved_path} not found. Run --collect-resolved first."); return
        with open(resolved_path) as f:
            resolved = json.load(f)
        if args.forward_limit > 0:
            resolved = resolved[:args.forward_limit]
        print(f"Running forward backtest on {len(resolved)} resolved markets...")
        debate = DebateEngine()
        def debate_fn(market):
            return debate.run_debate(market)
        fb_result = run_forward_backtest(resolved, debate_fn, category_fn=_infer_category)
        if args.backtest_json:
            out = {
                "total": fb_result.total,
                "accuracy": round(fb_result.accuracy, 1),
                "brier_score": round(fb_result.brier_score, 4),
                "market_brier": round(fb_result.market_brier_score, 4),
                "brier_skill": round(fb_result.brier_skill, 4),
                "by_category": {k: dict(v) for k, v in fb_result.by_category.items()},
                "errors": fb_result.errors,
                "predictions": fb_result.predictions,
            }
            print(json.dumps(out, indent=2))
        else:
            print(format_forward_report(fb_result))
        return

    a = Agent()
    try:
        if args.report:
            report = a.reporter.generate_report()
            print(report)
            report_file = CFG.get("report_file", "kalshi-weekly-report.txt")
            with open(report_file, "w") as f: f.write(report)
            print(f"\nSaved to {report_file}")
            if a.notifier.enabled:
                a.notifier.send_report(report)
                print("Emailed.")
            return
        if not args.no_dashboard:
            start_dashboard(); print(f"\n  Dashboard: http://localhost:{CFG.get('dashboard_port', 9000)}\n")
        with SHARED_LOCK:
            SHARED["balance"] = a.api.balance()
            if a.poly_enabled and a.poly_api:
                try: SHARED["poly_balance"] = a.poly_api.balance()
                except Exception: pass
        if args.scan_once: a.scan()
        else: a.run()
    except KeyboardInterrupt:
        log.info("\nStopped.")
        if hasattr(a, 'market_maker') and a.market_maker.is_active():
            a.market_maker.stop()
    except Exception as e: log.error(f"Fatal: {e}"); traceback.print_exc(); sys.exit(1)

if __name__ == "__main__": main()
