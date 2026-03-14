"""Cross-platform matching, arbitrage scanning, routing, and within-market arbitrage."""
import os, json, time

from modules.config import CFG, log, parse_orderbook_price
from modules.market_state import MARKET_STATE

# Import shared implementations from scripts/
from cross_platform import (
    find_quickflip_candidates,
    get_bankroll_tier,
    get_dynamic_kelly,
    BANKROLL_TIERS,
)


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
    """Scan matched market pairs for cross-platform arbitrage with slippage adjustment."""
    opportunities = []
    target_contracts = max(1, int(CFG.get("cross_arb_max_cost", 10.0) * 100 / 80))
    for match in matches:
        km, pm = match["kalshi"], match["polymarket"]
        if match.get("similarity", 0) < 0.80: continue
        try:
            k_ob = kalshi_api.orderbook(km["ticker"])
            k_book = k_ob.get("orderbook", {})
            yes_token = pm.get("token_id", "")
            if not yes_token: continue
            p_ob = poly_api.orderbook(yes_token)
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


def execute_cross_arb(kalshi_api, poly_api, opp, max_cost=10.0, dry_run=False):
    """Execute both legs of a cross-platform arb."""
    cost_per_pair = opp["cost_cents"] / 100.0
    contracts = min(int(max_cost / cost_per_pair) if cost_per_pair > 0 else 0, 20)
    if contracts == 0: return {"success": False, "reason": "Zero contracts"}
    total_cost = round(contracts * cost_per_pair, 2)
    total_profit = round(contracts * opp["profit_cents"] / 100, 2)
    if dry_run: return {"success": True, "dry_run": True, "contracts": contracts,
        "total_cost": total_cost, "expected_profit": total_profit, "strategy": opp["strategy_desc"]}
    try:
        side1 = "yes" if opp["strategy"] == 1 else "no"
        kalshi_api.place_order(opp["kalshi_ticker"], side1, contracts, opp["k_price"])
        log.info(f"  ARB Leg 1 (Kalshi): {side1} {contracts}x @{opp['k_price']}c")
    except Exception as e:
        log.error(f"  ARB Leg 1 FAILED: {e}"); return {"success": False, "reason": f"Leg 1 failed: {e}"}
    time.sleep(1)
    try:
        if opp["strategy"] == 1:
            token = opp.get("poly_no_token", opp["poly_token"])
            poly_api.place_order(token, "no", contracts, opp["p_price"])
        else:
            poly_api.place_order(opp["poly_token"], "yes", contracts, opp["p_price"])
        log.info(f"  ARB Leg 2 (Polymarket): {contracts}x @{opp['p_price']}c")
    except Exception as e:
        log.error(f"  ARB Leg 2 FAILED: {e} -- Leg 1 NAKED!!")
        return {"success": False, "reason": f"Leg 2 failed: {e}", "leg1_filled": True, "naked_position": True}
    return {"success": True, "contracts": contracts, "total_cost": total_cost,
        "expected_profit": total_profit, "strategy": opp["strategy_desc"]}


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
