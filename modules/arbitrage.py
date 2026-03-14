"""Cross-platform matching, arbitrage scanning, routing, and within-market arbitrage."""
import os, json, time, datetime
import threading

from modules.config import CFG, log, parse_orderbook_price
from modules.market_state import MARKET_STATE


class ArbPositionTracker:
    """Track open cross-platform arbitrage positions for rotation decisions.

    An arb position consists of two legs (one on Kalshi, one on Polymarket)
    that together guarantee a payout. We track these so the rotation engine
    can compare the current position's remaining profit against new opportunities.
    """

    def __init__(self):
        self._positions = {}  # key -> ArbPosition dict
        self._lock = threading.Lock()

    def record_entry(self, key, kalshi_ticker, poly_token, strategy_desc,
                     k_price, p_price, contracts, profit_cents, entry_time=None):
        """Record a new arb position after both legs fill."""
        with self._lock:
            self._positions[key] = {
                "kalshi_ticker": kalshi_ticker,
                "poly_token": poly_token,
                "strategy_desc": strategy_desc,
                "k_entry_price": k_price,
                "p_entry_price": p_price,
                "contracts": contracts,
                "entry_profit_cents": profit_cents,
                "entry_time": entry_time or time.time(),
                "status": "open",
            }

    def record_exit(self, key, reason="manual"):
        """Mark a position as closed."""
        with self._lock:
            if key in self._positions:
                self._positions[key]["status"] = "closed"
                self._positions[key]["exit_time"] = time.time()
                self._positions[key]["exit_reason"] = reason

    def get_open_positions(self):
        """Return list of open arb positions."""
        with self._lock:
            return [dict(pos, key=k) for k, pos in self._positions.items()
                    if pos["status"] == "open"]

    def get_position(self, key):
        """Get a specific position by key."""
        with self._lock:
            return self._positions.get(key)

    def has_open_positions(self):
        with self._lock:
            return any(p["status"] == "open" for p in self._positions.values())

    def clear_closed(self, max_age_hours=24):
        """Remove closed positions older than max_age_hours."""
        cutoff = time.time() - max_age_hours * 3600
        with self._lock:
            self._positions = {
                k: v for k, v in self._positions.items()
                if v["status"] == "open" or v.get("exit_time", time.time()) > cutoff
            }


# Module-level singleton
ARB_TRACKER = ArbPositionTracker()


def should_rotate_arb(current_positions, new_opportunities,
                      kalshi_fee=0.07, poly_fee=0.02, min_improvement_cents=3.0):
    """Determine if we should exit a current arb position to enter a better one.

    Rotation is only worthwhile if the new opportunity's profit exceeds:
    1. The current position's remaining profit (which may have changed since entry)
    2. PLUS the round-trip exit cost (selling both legs of current + buying both legs of new)

    Args:
        current_positions: list of open ArbPosition dicts from ARB_TRACKER
        new_opportunities: list of arb opportunity dicts from scan_cross_platform_arbitrage
        kalshi_fee: Kalshi fee per contract in dollars
        poly_fee: Polymarket fee per contract in dollars
        min_improvement_cents: minimum net improvement to justify the churn

    Returns:
        list of rotation dicts with exit_position, enter_opportunity, net_improvement
    """
    if not current_positions or not new_opportunities:
        return []

    # Round-trip exit cost: sell both legs of current position
    # = 2 legs x fee per leg (Kalshi exit fee + Polymarket exit fee)
    exit_fee_cents = (kalshi_fee + poly_fee) * 100  # exit current position
    entry_fee_cents = (kalshi_fee + poly_fee) * 100  # enter new position
    total_rotation_cost = exit_fee_cents + entry_fee_cents

    rotations = []

    for pos in current_positions:
        current_profit = pos.get("entry_profit_cents", 0)

        for opp in new_opportunities:
            new_profit = opp.get("profit_cents", 0)

            # Skip if same market (can't rotate into what you already hold)
            if opp.get("kalshi_ticker") == pos.get("kalshi_ticker"):
                continue

            net_improvement = new_profit - current_profit - total_rotation_cost

            if net_improvement >= min_improvement_cents:
                rotations.append({
                    "exit_position": pos,
                    "enter_opportunity": opp,
                    "current_profit": current_profit,
                    "new_profit": new_profit,
                    "rotation_cost": total_rotation_cost,
                    "net_improvement": round(net_improvement, 2),
                })

    # Sort by net improvement (best rotation first)
    rotations.sort(key=lambda r: r["net_improvement"], reverse=True)
    return rotations


def _jaccard_similarity(s1, s2):
    w1 = set(s1.lower().split()); w2 = set(s2.lower().split())
    if not w1 or not w2: return 0.0
    return len(w1 & w2) / len(w1 | w2)


def _levenshtein_similarity(s1, s2):
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2: return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0: return 1.0
    prev = list(range(len(s2) + 1)); curr = [0] * (len(s2) + 1)
    for i in range(1, len(s1) + 1):
        curr[0] = i
        for j in range(1, len(s2) + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return 1.0 - (prev[len(s2)] / max_len)


def combined_similarity(title1, title2):
    return 0.6 * _jaccard_similarity(title1, title2) + 0.4 * _levenshtein_similarity(title1, title2)


def classify_arb_quality(match, k_ob=None, p_ob=None):
    """Classify an arbitrage opportunity by reliability.

    Returns:
        "locked": True arbitrage (high confidence match + both legs executable)
        "soft": Likely mispricing (moderate match confidence, some execution risk)
        "speculative": Possible disagreement trade (lower match confidence)
        "unsafe": Should not be traded (stale data, low match quality, etc.)
    """
    sim = match.get("similarity", 0)
    source = match.get("source", "computed")

    # Similarity-based classification
    if sim >= 0.95 or source == "cache":
        match_quality = "high"
    elif sim >= 0.85:
        match_quality = "medium"
    elif sim >= 0.70:
        match_quality = "low"
    else:
        return "unsafe", "Match similarity too low"

    # Check for stale book data
    from modules.market_state import MARKET_STATE
    km = match.get("kalshi", {})
    k_ticker = km.get("ticker", "")
    k_book = MARKET_STATE.get_book(k_ticker)
    if k_book and k_book.is_stale:
        return "unsafe", "Kalshi book data is stale"

    # Classification
    if match_quality == "high":
        return "locked", "High-confidence semantic match"
    elif match_quality == "medium":
        return "soft", "Moderate semantic match -- verify settlement terms"
    else:
        return "speculative", "Low match confidence -- manual review recommended"


def match_markets(kalshi_markets, poly_markets, threshold=0.70):
    """Match markets across platforms using title similarity.
    Uses Jaccard pre-filter to avoid expensive Levenshtein on all pairs."""
    matches = []; used_poly = set()
    cache_path = "market-matches.json"
    cached_matches = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f: cached_matches = json.load(f)
            cutoff = time.time() - 7 * 86400
            cached_matches = {k: v for k, v in cached_matches.items() if v.get("timestamp", 0) > cutoff}
        except Exception: cached_matches = {}

    # Pre-compute word sets for Jaccard filtering
    poly_word_sets = []
    for pm in poly_markets:
        poly_word_sets.append(set(pm.get("title", "").lower().split()))

    # Jaccard-only threshold: if Jaccard alone is below this, skip Levenshtein
    # Since combined = 0.6*jaccard + 0.4*lev, and lev <= 1.0,
    # jaccard must be >= (threshold - 0.4) / 0.6 for combined to possibly reach threshold
    jaccard_prefilter = max(0.0, (threshold - 0.4) / 0.6)

    for km in kalshi_markets:
        k_title = km.get("title", ""); k_ticker = km.get("ticker", "")
        k_category = km.get("_category", "other"); k_hrs = km.get("_hrs_left", 9999)
        if k_ticker in cached_matches:
            cached_poly_id = cached_matches[k_ticker].get("poly_ticker", "")
            for i, pm in enumerate(poly_markets):
                if i not in used_poly and pm.get("ticker", "") == cached_poly_id:
                    matches.append({"kalshi": km, "polymarket": pm,
                        "similarity": cached_matches[k_ticker].get("similarity", 0.90), "source": "cache"})
                    used_poly.add(i); break
            continue
        best_match, best_score = None, 0
        k_words = set(k_title.lower().split())
        for i, pm in enumerate(poly_markets):
            if i in used_poly: continue
            p_category = pm.get("_category", "other"); p_hrs = pm.get("_hrs_left", 9999)
            if k_category != "other" and p_category != "other" and k_category != p_category: continue
            if abs(k_hrs - p_hrs) > 48 and k_hrs < 9999 and p_hrs < 9999: continue
            # Fast Jaccard pre-filter: skip expensive Levenshtein if no chance of matching
            p_words = poly_word_sets[i]
            if k_words and p_words:
                jaccard = len(k_words & p_words) / len(k_words | p_words)
            else:
                jaccard = 0.0
            if jaccard < jaccard_prefilter:
                continue
            score = 0.6 * jaccard + 0.4 * _levenshtein_similarity(k_title, pm.get("title", ""))
            if abs(k_hrs - p_hrs) < 6 and k_hrs < 9999: score = min(1.0, score + 0.05)
            if score > best_score and score >= threshold:
                best_score = score; best_match = (i, pm)
        if best_match:
            idx, pm = best_match
            matches.append({"kalshi": km, "polymarket": pm, "similarity": round(best_score, 3), "source": "computed"})
            used_poly.add(idx)
            cached_matches[k_ticker] = {"poly_ticker": pm.get("ticker", ""), "similarity": round(best_score, 3),
                "timestamp": time.time(), "k_title": k_title[:80], "p_title": pm.get("title", "")[:80]}
    try:
        with open(cache_path, "w") as f: json.dump(cached_matches, f, indent=2)
    except Exception: pass
    return matches


def _estimate_slippage(asks, contracts, best_price):
    """Estimate avg fill price walking the orderbook."""
    if not asks or contracts <= 0: return best_price, best_price
    remaining, total_cost, max_fill = contracts, 0, best_price
    for entry in asks:
        try:
            if isinstance(entry, (list, tuple)):
                p, s = int(float(entry[0])), int(float(entry[1])) if len(entry) > 1 else 1
            elif isinstance(entry, dict):
                p, s = int(float(entry.get("price", 0))), int(float(entry.get("size", 0)))
            else: break
            if 0 < p < 1: p = int(round(p * 100))
        except (ValueError, TypeError, IndexError): break
        fill = min(remaining, s); total_cost += fill * p; max_fill = p
        remaining -= fill
        if remaining <= 0: break
    filled = contracts - remaining
    if filled == 0: return best_price, best_price
    return round(total_cost / filled, 1), max_fill


def _best_ask(asks):
    """Get best ask price in cents. Handles list, dict, and scalar formats."""
    if not asks: return None
    first = asks[0]
    try:
        if isinstance(first, dict):
            raw = float(first.get("price", first.get("p", 0)))
        elif isinstance(first, (list, tuple)):
            raw = float(first[0])
        else:
            raw = float(first)
        if 0 < raw < 1: raw = raw * 100
        price = int(round(raw))
        return price if 1 <= price <= 99 else None
    except (ValueError, TypeError, IndexError):
        return None


def scan_cross_platform_arbitrage(matches, kalshi_api, poly_api, fee_kalshi=0.07, fee_poly=0.02):
    """Scan matched market pairs for cross-platform arbitrage with slippage adjustment.

    Only labels opportunities as "arbitrage" when match quality is high enough.
    Lower-quality matches are labeled as "soft_mispricing" for information only.
    """
    opportunities = []
    target_contracts = max(1, int(CFG.get("cross_arb_max_cost", 10.0) * 100 / 80))
    for match in matches:
        km, pm = match["kalshi"], match["polymarket"]
        if match.get("similarity", 0) < 0.80: continue

        # Classify match quality
        arb_class, arb_reason = classify_arb_quality(match)
        if arb_class == "unsafe":
            log.debug(f"  Cross-arb skip {km.get('ticker', '?')}: {arb_reason}")
            continue
        try:
            k_ob = kalshi_api.orderbook(km["ticker"])
            MARKET_STATE.update_book(km["ticker"], k_ob, source="rest")
            MARKET_STATE.record_feed_success("kalshi")
            k_book = k_ob.get("orderbook", {})
            yes_token = pm.get("token_id", "")
            if not yes_token: continue
            p_ob = poly_api.orderbook(yes_token)
            MARKET_STATE.record_feed_success("polymarket")
            p_book = p_ob.get("orderbook", {})
            # Strategy 1: YES@Kalshi + NO@Polymarket
            k_yes = k_book.get("yes", []); p_no = p_book.get("no", [])
            profit_1, cost_1, slip_1 = -999, 999, {}
            if k_yes and p_no:
                k_yes_p = _best_ask(k_yes); p_no_p = _best_ask(p_no)
                if k_yes_p and p_no_p:
                    k_avg, k_worst = _estimate_slippage(k_yes, target_contracts, k_yes_p)
                    p_avg, p_worst = _estimate_slippage(p_no, target_contracts, p_no_p)
                    cost_1 = k_yes_p + p_no_p; profit_1 = 100 - cost_1 - (fee_kalshi + fee_poly) * 100
                    slip_cost = k_avg + p_avg
                    slip_1 = {"avg_profit": 100 - slip_cost - (fee_kalshi + fee_poly) * 100,
                              "k_avg": k_avg, "p_avg": p_avg}
            # Strategy 2: NO@Kalshi + YES@Polymarket
            k_no = k_book.get("no", []); p_yes = p_book.get("yes", [])
            profit_2, cost_2, slip_2 = -999, 999, {}
            if k_no and p_yes:
                k_no_p = _best_ask(k_no); p_yes_p = _best_ask(p_yes)
                if k_no_p and p_yes_p:
                    k_avg, k_worst = _estimate_slippage(k_no, target_contracts, k_no_p)
                    p_avg, p_worst = _estimate_slippage(p_yes, target_contracts, p_yes_p)
                    cost_2 = k_no_p + p_yes_p; profit_2 = 100 - cost_2 - (fee_kalshi + fee_poly) * 100
                    slip_cost = k_avg + p_avg
                    slip_2 = {"avg_profit": 100 - slip_cost - (fee_kalshi + fee_poly) * 100,
                              "k_avg": k_avg, "p_avg": p_avg}
            best = max(profit_1, profit_2)
            if best > CFG.get("cross_arb_min_profit_cents", 2):
                is_s1 = profit_1 >= profit_2
                slip = slip_1 if is_s1 else slip_2
                opp = {
                    "kalshi_ticker": km["ticker"], "poly_token": yes_token,
                    "poly_no_token": pm.get("no_token_id", ""),
                    "title": km.get("title", ""),
                    "strategy": 1 if is_s1 else 2,
                    "strategy_desc": "YES@Kalshi+NO@Poly" if is_s1 else "NO@Kalshi+YES@Poly",
                    "profit_cents": round(best, 1),
                    "cost_cents": round(cost_1 if is_s1 else cost_2, 1),
                    "k_price": _best_ask(k_yes) if is_s1 else _best_ask(k_no),
                    "p_price": _best_ask(p_no) if is_s1 else _best_ask(p_yes),
                    "similarity": match.get("similarity", 0),
                    "type": "cross_platform_arbitrage",
                    "arb_class": arb_class,
                    "arb_reason": arb_reason,
                }
                if slip:
                    opp["slippage_adjusted_profit"] = round(slip.get("avg_profit", best), 1)
                    if slip.get("avg_profit", best) <= 0:
                        log.debug(f"  Cross-arb {km.get('ticker', '?')}: profitable at best-ask but not after slippage")
                        continue
                opportunities.append(opp)
            time.sleep(0.15)
        except Exception as e:
            log.debug(f"Cross-arb scan error for {km.get('ticker', '?')}: {e}"); continue
    opportunities.sort(key=lambda x: x.get("slippage_adjusted_profit", x["profit_cents"]), reverse=True)
    return opportunities


def execute_cross_arb(kalshi_api, poly_api, opp, max_cost=10.0, dry_run=False, parallel=False):
    """Execute both legs of a cross-platform arb.

    SAFETY: only executes "locked" arb classification by default.
    Soft/speculative opportunities are logged but not executed.

    Args:
        parallel: If True, execute both legs simultaneously using threads.
                  Faster but riskier -- if one leg fails, the other may have filled.
                  Default False (sequential: Kalshi first, wait, then Polymarket).
    """
    arb_class = opp.get("arb_class", "speculative")
    if arb_class not in ("locked",) and not dry_run:
        log.info(f"  Cross-arb {opp.get('kalshi_ticker', '?')}: skipping live execution (class={arb_class})")
        return {"success": False, "reason": f"Arb class '{arb_class}' not eligible for live execution"}

    cost_per_pair = opp["cost_cents"] / 100.0
    contracts = min(int(max_cost / cost_per_pair) if cost_per_pair > 0 else 0, 20)
    if contracts == 0:
        return {"success": False, "reason": "Zero contracts"}
    total_cost = round(contracts * cost_per_pair, 2)
    total_profit = round(contracts * opp["profit_cents"] / 100, 2)

    if dry_run:
        return {"success": True, "dry_run": True, "contracts": contracts,
            "total_cost": total_cost, "expected_profit": total_profit,
            "strategy": opp["strategy_desc"], "execution_mode": "parallel" if parallel else "sequential"}

    side1 = "yes" if opp["strategy"] == 1 else "no"
    side2_token = opp.get("poly_no_token", opp["poly_token"]) if opp["strategy"] == 1 else opp["poly_token"]
    side2 = "no" if opp["strategy"] == 1 else "yes"

    def _leg1_kalshi():
        kalshi_api.place_order(opp["kalshi_ticker"], side1, contracts, opp["k_price"])
        return True

    def _leg2_poly():
        poly_api.place_order(side2_token, side2, contracts, opp["p_price"])
        return True

    if parallel:
        # PARALLEL EXECUTION: both legs fire simultaneously
        import concurrent.futures
        log.info(f"  ARB: Parallel execution -- firing both legs simultaneously")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_leg1_kalshi)
            f2 = pool.submit(_leg2_poly)

            leg1_ok, leg2_ok = False, False
            leg1_err, leg2_err = None, None
            try:
                leg1_ok = f1.result(timeout=30)
                log.info(f"  ARB Leg 1 (Kalshi): {side1} {contracts}x @{opp['k_price']}c OK")
            except Exception as e:
                leg1_err = e
                log.error(f"  ARB Leg 1 (Kalshi) FAILED: {e}")
            try:
                leg2_ok = f2.result(timeout=30)
                log.info(f"  ARB Leg 2 (Polymarket): {side2} {contracts}x @{opp['p_price']}c OK")
            except Exception as e:
                leg2_err = e
                log.error(f"  ARB Leg 2 (Polymarket) FAILED: {e}")

        if leg1_ok and leg2_ok:
            ARB_TRACKER.record_entry(
                key=opp["kalshi_ticker"],
                kalshi_ticker=opp["kalshi_ticker"],
                poly_token=side2_token,
                strategy_desc=opp["strategy_desc"],
                k_price=opp["k_price"], p_price=opp["p_price"],
                contracts=contracts, profit_cents=opp["profit_cents"])
            return {"success": True, "contracts": contracts, "total_cost": total_cost,
                "expected_profit": total_profit, "strategy": opp["strategy_desc"],
                "execution_mode": "parallel"}
        elif leg1_ok and not leg2_ok:
            return {"success": False, "reason": f"Leg 2 failed: {leg2_err}",
                "leg1_filled": True, "naked_position": True, "execution_mode": "parallel"}
        elif not leg1_ok and leg2_ok:
            return {"success": False, "reason": f"Leg 1 failed: {leg1_err}",
                "leg2_filled": True, "naked_position": True, "execution_mode": "parallel"}
        else:
            return {"success": False, "reason": f"Both legs failed: L1={leg1_err}, L2={leg2_err}",
                "execution_mode": "parallel"}

    else:
        # SEQUENTIAL EXECUTION (default): Kalshi first, wait, then Polymarket
        try:
            _leg1_kalshi()
            log.info(f"  ARB Leg 1 (Kalshi): {side1} {contracts}x @{opp['k_price']}c")
        except Exception as e:
            log.error(f"  ARB Leg 1 FAILED: {e}")
            return {"success": False, "reason": f"Leg 1 failed: {e}"}

        time.sleep(1)

        try:
            _leg2_poly()
            log.info(f"  ARB Leg 2 (Polymarket): {side2} {contracts}x @{opp['p_price']}c")
        except Exception as e:
            log.error(f"  ARB Leg 2 FAILED: {e} -- Leg 1 NAKED!!")
            return {"success": False, "reason": f"Leg 2 failed: {e}",
                "leg1_filled": True, "naked_position": True}

        ARB_TRACKER.record_entry(
            key=opp["kalshi_ticker"],
            kalshi_ticker=opp["kalshi_ticker"],
            poly_token=side2_token,
            strategy_desc=opp["strategy_desc"],
            k_price=opp["k_price"], p_price=opp["p_price"],
            contracts=contracts, profit_cents=opp["profit_cents"])

        return {"success": True, "contracts": contracts, "total_cost": total_cost,
            "expected_profit": total_profit, "strategy": opp["strategy_desc"],
            "execution_mode": "sequential"}


def route_order(side, kalshi_price, poly_price, kalshi_fee=0.07, poly_fee=0.02):
    """Route to the platform with the best effective price."""
    k_eff = kalshi_price + kalshi_fee * 100; p_eff = poly_price + poly_fee * 100
    return ("kalshi", kalshi_price) if k_eff <= p_eff else ("polymarket", poly_price)


def get_best_price(ticker, kalshi_api, poly_match, poly_api, side, kalshi_fee=0.07, poly_fee=0.02):
    """Get the best price across both platforms for a given side."""
    k_price, k_ob, p_price, p_ob = None, None, None, None
    try:
        k_ob = kalshi_api.orderbook(ticker)
        asks = k_ob.get("orderbook", {}).get("yes" if side == "yes" else "no", [])
        if asks: k_price = _best_ask(asks)
    except Exception: pass
    if poly_match and poly_api:
        token_id = poly_match.get("token_id", "")
        if token_id:
            try:
                p_ob = poly_api.orderbook(token_id)
                asks = p_ob.get("orderbook", {}).get("yes" if side == "yes" else "no", [])
                if asks: p_price = _best_ask(asks)
            except Exception: pass
    if k_price is not None and p_price is not None:
        platform, price = route_order(side, k_price, p_price, kalshi_fee, poly_fee)
        return platform, price, k_ob if platform == "kalshi" else p_ob
    if k_price is not None: return "kalshi", k_price, k_ob
    if p_price is not None: return "polymarket", p_price, p_ob
    return None, None, None


def scan_arbitrage(api, markets, ob_cache=None):
    """Check for within-market YES+NO < 100c arbitrage.

    Uses MARKET_STATE store for book caching and staleness tracking.
    """
    opportunities = []
    skipped = 0
    candidates = [m for m in markets if (m.get("volume", 0) or 0) >= 50][:100]
    for m in candidates:
        tk = m["ticker"]
        try:
            # Check for fresh cached book state first
            cached_book = MARKET_STATE.get_book_if_fresh(tk)
            if cached_book:
                best_yes = cached_book.best_yes_bid
                best_no = cached_book.best_no_bid
                if best_yes is None or best_no is None:
                    continue
                # Use ob_cache for change detection
                if ob_cache is not None:
                    prev = ob_cache.get(tk)
                    if prev:
                        _, old_yes, old_no = prev
                        if old_yes == best_yes and old_no == best_no:
                            skipped += 1; continue
                    ob_cache[tk] = (time.time(), best_yes, best_no)
            else:
                # Fetch fresh book from API and update state store
                ob = api.orderbook(tk)
                book_state = MARKET_STATE.update_book(tk, ob, source="rest")
                MARKET_STATE.record_feed_success("kalshi")

                book = ob.get("orderbook", {})
                yes_bids = book.get("yes", book.get("yes_dollars", []))
                no_bids = book.get("no", book.get("no_dollars", []))
                if not yes_bids or not no_bids: continue
                raw_yes = yes_bids[0][0] if isinstance(yes_bids[0], list) else yes_bids[0]
                raw_no = no_bids[0][0] if isinstance(no_bids[0], list) else no_bids[0]
                best_yes = parse_orderbook_price(raw_yes)
                best_no = parse_orderbook_price(raw_no)
                if best_yes is None or best_no is None: continue

                if ob_cache is not None:
                    prev = ob_cache.get(tk)
                    now = time.time()
                    if prev:
                        ts, old_yes, old_no = prev
                        if now - ts < 180 and old_yes == best_yes and old_no == best_no:
                            skipped += 1; continue
                    ob_cache[tk] = (now, best_yes, best_no)

            total_cost = best_yes + best_no
            fee_cost = CFG["taker_fee_per_contract"] * 2 * 100
            if total_cost + fee_cost < 100:
                profit_cents = 100 - total_cost - fee_cost
                opportunities.append({
                    "ticker": tk, "title": m.get("title", ""),
                    "yes_price": best_yes, "no_price": best_no,
                    "total_cost": total_cost, "profit_cents": profit_cents,
                    "type": "arbitrage",
                })
        except Exception as e:
            MARKET_STATE.record_feed_error("kalshi")
            continue
        time.sleep(0.1)
    if skipped: log.debug(f"  Arb scan: skipped {skipped} unchanged orderbooks")
    opportunities.sort(key=lambda x: x["profit_cents"], reverse=True)
    return opportunities


# ════════════════════════════════════════
# QUICK-FLIP SCALPING
# ════════════════════════════════════════

def find_quickflip_candidates(markets, min_price=3, max_price=15, min_volume=50):
    """Find cheap contracts (3-15c) with decent volume for quick-flip scalping."""
    candidates = []
    for m in markets:
        yc = m.get("yes_bid", m.get("last_price", 50)) or 50
        vol = m.get("volume", 0) or 0
        hrs = m.get("_hrs_left", 9999)
        if min_price <= yc <= max_price and vol >= min_volume and hrs > 2:
            candidates.append({
                "market": m, "side": "yes", "entry_price": yc,
                "target_price": min(yc * 2, 50), "stop_price": max(1, yc - 2),
                "potential_roi": round((min(yc * 2, 50) - yc) / yc * 100, 0),
                "platform": m.get("platform", "kalshi"), "hours_left": hrs,
            })
        no_price = 100 - yc
        if min_price <= no_price <= max_price and vol >= min_volume and hrs > 2:
            candidates.append({
                "market": m, "side": "no", "entry_price": no_price,
                "target_price": min(no_price * 2, 50), "stop_price": max(1, no_price - 2),
                "potential_roi": round((min(no_price * 2, 50) - no_price) / no_price * 100, 0),
                "platform": m.get("platform", "kalshi"), "hours_left": hrs,
            })
    candidates.sort(key=lambda x: x["potential_roi"], reverse=True)
    return candidates[:10]


# ════════════════════════════════════════
# COMPOUNDING BANKROLL TIERS
# ════════════════════════════════════════

BANKROLL_TIERS = [
    # (min_bankroll, max_bet, max_exposure, kelly_fraction)
    (500, 60.0, 200.0, 0.20),
    (300, 40.0, 150.0, 0.25),
    (150, 25.0, 100.0, 0.25),
    (75, 15.0, 60.0, 0.30),
    (0, 8.0, 35.0, 0.30),
]


def get_bankroll_tier(bankroll):
    """Get dynamic trading parameters based on current bankroll."""
    for min_br, max_bet, max_exp, kelly in BANKROLL_TIERS:
        if bankroll >= min_br:
            return {"max_bet_per_trade": max_bet, "max_total_exposure": max_exp,
                    "kelly_fraction": kelly, "tier_min": min_br}
    return {"max_bet_per_trade": 5.0, "max_total_exposure": 25.0,
            "kelly_fraction": 0.20, "tier_min": 0}


def get_dynamic_kelly(base_fraction, win_streak=0, loss_cooldown=0):
    """Adjust Kelly fraction based on recent performance."""
    if loss_cooldown > 0:
        return max(0.10, base_fraction * 0.5)
    if win_streak >= 2:
        bonus = (win_streak - 1) * 0.05
        return min(0.50, base_fraction + bonus)
    return base_fraction


# ════════════════════════════════════════
# CROSS-PLATFORM RISK MANAGEMENT
# ════════════════════════════════════════

class CrossPlatformRiskMgr:
    """Track exposure and risk across both Kalshi and Polymarket."""

    def __init__(self):
        self.kalshi_exposure = 0.0
        self.poly_exposure = 0.0
        self.arb_pairs = []
        self.win_streak = 0
        self.loss_cooldown = 0

    @property
    def total_exposure(self):
        return self.kalshi_exposure + self.poly_exposure

    def check_directional(self, platform, cost, max_exposure):
        if platform == "kalshi":
            new_total = self.kalshi_exposure + cost + self.poly_exposure
        else:
            new_total = self.poly_exposure + cost + self.kalshi_exposure
        return new_total <= max_exposure

    def check_arbitrage(self, k_cost, p_cost, bankroll, max_arb_pct=0.50):
        arb_total = k_cost + p_cost
        return (self.total_exposure + arb_total) <= bankroll * max_arb_pct

    def record_trade(self, platform, cost):
        if platform == "kalshi":
            self.kalshi_exposure += cost
        else:
            self.poly_exposure += cost

    def record_arb(self, kalshi_cost, poly_cost):
        self.kalshi_exposure += kalshi_cost
        self.poly_exposure += poly_cost
        self.arb_pairs.append({"time": datetime.datetime.now().isoformat(),
                               "k_cost": kalshi_cost, "p_cost": poly_cost})

    def record_outcome(self, is_win):
        if is_win:
            self.win_streak += 1; self.loss_cooldown = 0
        else:
            self.win_streak = 0; self.loss_cooldown = 2

    def tick_cooldown(self):
        if self.loss_cooldown > 0:
            self.loss_cooldown -= 1

    def summary(self):
        return {"kalshi_exposure": f"${self.kalshi_exposure:.2f}",
                "poly_exposure": f"${self.poly_exposure:.2f}",
                "total_exposure": f"${self.total_exposure:.2f}",
                "arb_pairs": len(self.arb_pairs), "win_streak": self.win_streak,
                "loss_cooldown": self.loss_cooldown}


def check_circuit_breakers(kalshi_balance, poly_balance, day_pnl, max_daily_loss=15.0,
                            min_platform_balance=5.0, consecutive_losses=0):
    """Check cross-platform circuit breakers."""
    if day_pnl < -max_daily_loss:
        return True, f"Combined daily loss ${day_pnl:.2f} exceeds limit ${max_daily_loss:.2f}"
    if kalshi_balance < min_platform_balance and poly_balance < min_platform_balance:
        return True, f"Both platforms below minimum balance (K:${kalshi_balance:.2f} P:${poly_balance:.2f})"
    if consecutive_losses >= 3:
        return True, f"{consecutive_losses} consecutive losses -- cooling down"
    return False, "OK"


def platform_available(balance, min_balance=5.0):
    """Check if a platform has enough balance to trade."""
    return balance >= min_balance
