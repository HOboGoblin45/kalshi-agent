"""Risk management, trade logging, and position exit monitoring."""
import os, json, datetime, time, uuid

from modules.config import CFG, SHARED, SHARED_LOCK, log, parse_orderbook_price
from modules.precision import to_decimal, get_venue_fees, MONEY_PLACES


class RiskMgr:
    def __init__(self):
        self.today = datetime.date.today()
        self.day_trades = 0
        self.day_pnl = 0.0
        self.exposure = 0.0
        self.paused = False
        self.cooldown_trades = 0  # Graduated cooldown: trades remaining at reduced size
        self._recent_losses = 0   # Consecutive recent losses
        p = CFG["trade_log"]
        self.trades = json.load(open(p)) if os.path.exists(p) else []
        self.traded_tickers = set()
        for t in self.trades:
            try:
                if datetime.date.fromisoformat(t["time"][:10]) == self.today:
                    self.day_trades += 1
                    self.exposure += t.get("cost", 0)
                    self.traded_tickers.add(t["ticker"])
            except Exception: pass

    def _save(self):
        with open(CFG["trade_log"], "w") as f:
            json.dump(self.trades, f, indent=2, default=str)

    def new_day(self):
        if datetime.date.today() != self.today:
            log.info("New day -- reset")
            self.today = datetime.date.today()
            self.day_trades = 0
            self.day_pnl = 0.0
            self.paused = False
            self.cooldown_trades = 0
            self._recent_losses = 0
            self.traded_tickers.clear()

    @property
    def in_cooldown(self):
        return self.cooldown_trades > 0

    @property
    def cooldown_bet_fraction(self):
        """During cooldown, reduce bet size to 50%."""
        return 0.5 if self.in_cooldown else 1.0

    def check(self, cost, conf, edge):
        self.new_day()
        if self.paused: return False, "PAUSED"
        if self.day_trades >= CFG["max_daily_trades"]: return False, f"Daily limit ({CFG['max_daily_trades']})"
        if self.exposure + cost > CFG["max_total_exposure"]: return False, "Exposure exceeded"
        # During cooldown, enforce half bet size
        effective_max_bet = CFG["max_bet_per_trade"] * self.cooldown_bet_fraction
        if cost > effective_max_bet:
            return False, f"Bet too large (cooldown: max ${effective_max_bet:.2f})"
        # After 2+ consecutive losses, require higher confidence
        min_conf = CFG["min_confidence"]
        if self._recent_losses >= 3:
            min_conf = max(min_conf, 75)
        elif self._recent_losses >= 2:
            min_conf = max(min_conf, 70)
        if conf < min_conf: return False, f"Low confidence ({conf}% < {min_conf}% required)"
        if abs(edge) < CFG["min_edge_pct"]: return False, f"Low edge ({edge}%)"
        # Hard stop: full pause at max daily loss
        if self.day_pnl < -CFG["max_daily_loss"]:
            self.paused = True
            return False, "CIRCUIT BREAKER"
        # Graduated cooldown: enter cooldown at 60% of max daily loss
        cooldown_threshold = -CFG["max_daily_loss"] * 0.6
        if self.day_pnl < cooldown_threshold and not self.in_cooldown:
            self.cooldown_trades = 3
            log.warning(f"Entering cooldown: day_pnl ${self.day_pnl:.2f} < ${cooldown_threshold:.2f}. Next 3 trades at 50% size.")
        return True, "OK"

    def record(self, ticker, title, side, contracts, price_c, conf, edge, evidence,
               bull_prob=0, bear_prob=0, probability=0, platform="kalshi"):
        cost = contracts * price_c / 100
        t = {"time": datetime.datetime.now().isoformat(), "ticker": ticker, "title": title,
             "side": side, "contracts": contracts, "price_cents": price_c, "cost": round(cost, 2),
             "confidence": conf, "probability": probability, "edge": edge, "evidence": evidence,
             "bull_prob": bull_prob, "bear_prob": bear_prob, "status": "open", "platform": platform}
        self.trades.append(t)
        self.day_trades += 1
        self.exposure += cost
        self.traded_tickers.add(ticker)
        # Decrement cooldown counter
        if self.cooldown_trades > 0:
            self.cooldown_trades -= 1
            if self.cooldown_trades == 0:
                log.info("Cooldown period ended, resuming normal bet sizing.")
        self._save()
        self._log_calibration(t)

    def record_outcome(self, pnl):
        """Track consecutive losses for adaptive confidence gating."""
        if pnl < 0:
            self._recent_losses += 1
        else:
            self._recent_losses = 0

    def _log_calibration(self, trade):
        cal_file = CFG["calibration_log"]
        records = []
        if os.path.exists(cal_file):
            try: records = json.load(open(cal_file))
            except Exception: records = []
        records.append({
            "time": trade["time"], "ticker": trade["ticker"], "side": trade["side"],
            "our_probability": trade.get("probability", 0), "our_confidence": trade.get("confidence", 0),
            "market_price": trade["price_cents"], "edge": trade["edge"],
            "bull_prob": trade.get("bull_prob", 0), "bear_prob": trade.get("bear_prob", 0),
            "resolved": None,
        })
        if len(records) > 2000: records = records[-2000:]
        with open(cal_file, "w") as f:
            json.dump(records, f, indent=2, default=str)

    def summary(self):
        w = sum(1 for t in self.trades if t.get("status") == "win")
        l = sum(1 for t in self.trades if t.get("status") == "loss")
        tc = sum(t.get("cost", 0) for t in self.trades)
        return {
            "total": len(self.trades), "wins": w, "losses": l,
            "win_rate": f"{w / (w + l) * 100:.0f}%" if w + l > 0 else "--",
            "wagered": f"${tc:.2f}",
            "day_trades": self.day_trades, "day_pnl": f"${self.day_pnl:.2f}",
            "exposure": f"${self.exposure:.2f}", "paused": self.paused,
        }


class ExitManager:
    """Monitor open positions and exit on stop-loss, profit-take, or time limit."""

    def __init__(self, api, risk, notifier, poly_api=None):
        self.api = api
        self.poly_api = poly_api
        self.risk = risk
        self.notifier = notifier
        self.loss_pct = CFG.get("exit_loss_pct", 25)
        self.profit_pct = CFG.get("exit_profit_pct", 40)
        self.max_hold_hrs = CFG.get("exit_time_hours", 36)
        self._pos_fail_count = 0

    def check_positions(self):
        exits = []
        try:
            positions = self.api.positions()
            self._pos_fail_count = 0
        except Exception as e:
            self._pos_fail_count += 1
            log.error(f"Exit check: can't load positions (fail #{self._pos_fail_count}): {e}")
            if self._pos_fail_count >= 3:
                log.error("CRITICAL: Position monitoring failed 3x in a row")
                self.notifier.send("ALERT: Position Monitoring Down",
                    f"Failed to load positions {self._pos_fail_count} consecutive times.\n"
                    f"Last error: {e}\n\nOpen positions may not be exited automatically.\n"
                    f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return exits

        for pos in positions:
            tk = pos.get("ticker", pos.get("market_ticker", ""))
            if not tk: continue
            side = "yes" if pos.get("yes_contracts", pos.get("position", 0)) > 0 else "no"
            contracts = abs(pos.get("yes_contracts", pos.get("no_contracts", pos.get("position", 0))))
            if contracts == 0: continue

            original = None
            for t in reversed(self.risk.trades):
                if t.get("ticker") == tk and t.get("status") == "open":
                    original = t; break
            if not original: continue

            entry_price = original.get("price_cents", 50)
            try:
                ob = self.api.orderbook(tk)
                book = ob.get("orderbook", {})
                if side == "yes":
                    bids = book.get("yes", book.get("yes_dollars", []))
                else:
                    bids = book.get("no", book.get("no_dollars", []))
                if not bids: continue
                current = parse_orderbook_price(bids[0][0] if isinstance(bids[0], list) else bids[0])
                if current is None: continue
            except Exception:
                continue

            # Fee-aware PnL using venue fee model
            fees = get_venue_fees("kalshi")
            fee_cents = float(fees.round_trip_cost(1)) * 100  # total fees for 1 contract in cents
            pnl_pct = ((current - entry_price - fee_cents) / entry_price * 100) if entry_price > 0 else 0
            hours_held = 0
            try:
                entry_time = datetime.datetime.fromisoformat(original["time"])
                hours_held = (datetime.datetime.now() - entry_time).total_seconds() / 3600
            except Exception: pass

            reason = None
            if pnl_pct <= -self.loss_pct:
                reason = f"Stop loss ({pnl_pct:.0f}% loss)"
            elif pnl_pct >= self.profit_pct:
                reason = f"Profit taking ({pnl_pct:.0f}% gain)"
            elif hours_held >= self.max_hold_hrs:
                reason = f"Time exit ({hours_held:.0f}h held)"
            if not reason: continue

            pnl_dollars = float(fees.net_pnl(entry_price, current, contracts))
            log.info(f"  EXIT: {tk} -- {reason} | entry:{entry_price}c now:{current:.0f}c P&L:${pnl_dollars:.2f}")

            try:
                if "Stop loss" in reason:
                    sell_price = max(1, int(current) - 3)
                elif "Time exit" in reason:
                    sell_price = max(1, int(current) - 2)
                else:
                    sell_price = max(1, int(current))
                sell_order = {"ticker": tk, "action": "sell", "side": side,
                    "count": contracts, "type": "limit", "client_order_id": str(uuid.uuid4())}
                if side == "yes": sell_order["yes_price"] = sell_price
                else: sell_order["no_price"] = sell_price
                result = self.api._req("POST", "/portfolio/orders", sell_order)
                oid = result.get("order", {}).get("order_id", "?")
                log.info(f"  EXIT OK: order {oid}")

                original["status"] = "win" if pnl_dollars > 0 else "loss"
                original["exit_price"] = sell_price
                original["exit_time"] = datetime.datetime.now().isoformat()
                original["exit_reason"] = reason
                original["pnl"] = round(pnl_dollars, 2)
                self.risk._save()
                self.risk.day_pnl += pnl_dollars
                self.risk.record_outcome(pnl_dollars)
                exits.append({"ticker": tk, "reason": reason, "pnl": pnl_dollars})
                self.notifier.notify_exit(tk, original.get("title", ""), side, reason, pnl_dollars)
            except Exception as e:
                log.error(f"  EXIT failed {tk}: {e}")
            time.sleep(1)
        return exits

    def check_poly_positions(self):
        if not self.poly_api or not self.poly_api.is_trading_enabled:
            return []
        exits = []
        try:
            positions = self.poly_api.positions()
        except Exception as e:
            log.debug(f"Polymarket position check failed: {e}")
            return exits

        for pos in positions:
            token_id = pos.get("asset", pos.get("token_id", ""))
            size = float(pos.get("size", pos.get("position", 0)) or 0)
            if size == 0 or not token_id: continue

            original = None
            for t in reversed(self.risk.trades):
                if t.get("platform") == "polymarket" and t.get("status") == "open":
                    original = t; break
            if not original: continue

            entry_price = original.get("price_cents", 50)
            hours_held = 0
            try:
                entry_time = datetime.datetime.fromisoformat(original["time"])
                hours_held = (datetime.datetime.now() - entry_time).total_seconds() / 3600
            except Exception: pass

            try:
                ob = self.poly_api.orderbook(token_id)
                book = ob.get("orderbook", {})
                bids = book.get("yes", [])
                if not bids: continue
                from modules.arbitrage import _best_ask
                current = _best_ask(bids) if bids else None
                if current is None: continue
            except Exception: continue

            poly_fees = get_venue_fees("polymarket")
            poly_fee_cents = float(poly_fees.round_trip_cost(1)) * 100
            pnl_pct = ((current - entry_price - poly_fee_cents) / entry_price * 100) if entry_price > 0 else 0
            reason = None
            if pnl_pct <= -self.loss_pct:
                reason = f"Stop loss ({pnl_pct:.0f}% loss)"
            elif pnl_pct >= self.profit_pct:
                reason = f"Profit taking ({pnl_pct:.0f}% gain)"
            elif hours_held >= self.max_hold_hrs:
                reason = f"Time exit ({hours_held:.0f}h held)"
            if not reason: continue

            contracts = int(size)
            pnl_dollars = float(poly_fees.net_pnl(entry_price, current, contracts))
            log.info(f"  POLY EXIT: {token_id[:16]}... -- {reason} | entry:{entry_price}c now:{current}c P&L:${pnl_dollars:.2f}")

            try:
                sell_price = max(1, int(current) - 2) if "Stop" in reason or "Time" in reason else max(1, int(current))
                side = original.get("side", "yes")
                self.poly_api.place_order(token_id, "no" if side == "yes" else "yes", contracts, sell_price)
                original["status"] = "win" if pnl_dollars > 0 else "loss"
                original["exit_price"] = sell_price
                original["exit_time"] = datetime.datetime.now().isoformat()
                original["exit_reason"] = reason
                original["pnl"] = round(pnl_dollars, 2)
                self.risk._save()
                self.risk.day_pnl += pnl_dollars
                exits.append({"ticker": token_id[:16], "reason": reason, "pnl": pnl_dollars})
                self.notifier.notify_exit(token_id[:16], original.get("title", ""), side, reason, pnl_dollars)
            except Exception as e:
                log.error(f"  POLY EXIT failed: {e}")
        return exits

    def run_loop(self, stop_event):
        interval = CFG.get("exit_check_interval_minutes", 10) * 60
        log.info(f"Exit manager: checking positions every {CFG.get('exit_check_interval_minutes', 10)}m")
        while not stop_event.is_set():
            try:
                if SHARED.get("enabled", True):
                    exits = self.check_positions()
                    poly_exits = self.check_poly_positions()
                    all_exits = exits + poly_exits
                    if all_exits:
                        with SHARED_LOCK:
                            SHARED["_risk_summary"] = self.risk.summary()
                            SHARED["_trades"] = self.risk.trades
                        for e in all_exits:
                            log.info(f"EXIT completed: {e['ticker']} -> {e['reason']} (${e['pnl']:.2f})")
            except Exception as e:
                log.warning(f"Exit check error: {e}")
            stop_event.wait(interval)
