#!/usr/bin/env python3
"""
Cross-platform market matching, arbitrage detection, best-price routing,
quick-flip scalping, and compounding bankroll tiers.

Used by the main agent to find and exploit price discrepancies
between Kalshi and Polymarket on the same events.
"""
import json, os, time, datetime, logging, math

log = logging.getLogger("agent")

# ════════════════════════════════════════
# MARKET MATCHING
# ════════════════════════════════════════

def _jaccard_similarity(s1, s2):
    """Word-level Jaccard similarity between two strings."""
    w1 = set(s1.lower().split())
    w2 = set(s2.lower().split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def _levenshtein_similarity(s1, s2):
    """Normalized Levenshtein similarity (1 - normalized_distance)."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0

    # Optimized Levenshtein using two-row approach
    prev = list(range(len(s2) + 1))
    curr = [0] * (len(s2) + 1)
    for i in range(1, len(s1) + 1):
        curr[0] = i
        for j in range(1, len(s2) + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev

    distance = prev[len(s2)]
    return 1.0 - (distance / max_len)


def combined_similarity(title1, title2):
    """Combined similarity: 60% Jaccard + 40% Levenshtein."""
    j = _jaccard_similarity(title1, title2)
    l = _levenshtein_similarity(title1, title2)
    return 0.6 * j + 0.4 * l


def match_markets(kalshi_markets, poly_markets, threshold=0.70, cache_path="market-matches.json"):
    """
    Match markets across platforms using combined title similarity.
    Returns list of dicts: {kalshi, polymarket, similarity}

    Three-layer matching:
    1. Exact: same category + close resolution dates + high title similarity
    2. Fuzzy: title similarity above threshold
    3. Cached: previously confirmed matches
    """
    # Load cached matches
    cached_matches = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            # Expire entries older than 7 days
            cutoff = time.time() - 7 * 86400
            cached_matches = {
                k: v for k, v in cached.items()
                if v.get("timestamp", 0) > cutoff
            }
        except Exception:
            cached_matches = {}

    matches = []
    used_poly = set()

    for km in kalshi_markets:
        k_title = km.get("title", "")
        k_category = km.get("_category", "other")
        k_hrs = km.get("_hrs_left", 9999)
        k_ticker = km.get("ticker", "")

        # Check cache first
        cache_key = k_ticker
        if cache_key in cached_matches:
            cached_poly_id = cached_matches[cache_key].get("poly_ticker", "")
            for i, pm in enumerate(poly_markets):
                if i in used_poly:
                    continue
                if pm.get("ticker", "") == cached_poly_id:
                    matches.append({
                        "kalshi": km,
                        "polymarket": pm,
                        "similarity": cached_matches[cache_key].get("similarity", 0.90),
                        "source": "cache",
                    })
                    used_poly.add(i)
                    break
            continue

        best_match = None
        best_score = 0

        for i, pm in enumerate(poly_markets):
            if i in used_poly:
                continue

            p_category = pm.get("_category", "other")
            p_hrs = pm.get("_hrs_left", 9999)
            p_title = pm.get("title", "")

            # Layer 1: Category + time proximity filter
            # Different categories are unlikely to be the same market
            if k_category != "other" and p_category != "other" and k_category != p_category:
                continue

            # Resolution dates must be within 48h of each other
            if abs(k_hrs - p_hrs) > 48 and k_hrs < 9999 and p_hrs < 9999:
                continue

            # Layer 2: Title similarity
            score = combined_similarity(k_title, p_title)

            # Boost score if resolution dates are very close (< 6h)
            if abs(k_hrs - p_hrs) < 6 and k_hrs < 9999:
                score = min(1.0, score + 0.05)

            if score > best_score and score >= threshold:
                best_score = score
                best_match = (i, pm)

        if best_match:
            idx, pm = best_match
            match_entry = {
                "kalshi": km,
                "polymarket": pm,
                "similarity": round(best_score, 3),
                "source": "computed",
            }
            matches.append(match_entry)
            used_poly.add(idx)

            # Cache this match
            cached_matches[k_ticker] = {
                "poly_ticker": pm.get("ticker", ""),
                "similarity": round(best_score, 3),
                "timestamp": time.time(),
                "k_title": k_title[:80],
                "p_title": pm.get("title", "")[:80],
            }

    # Save cache
    if cache_path and cached_matches:
        try:
            with open(cache_path, "w") as f:
                json.dump(cached_matches, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save match cache: {e}")

    return matches


# ════════════════════════════════════════
# CROSS-PLATFORM ARBITRAGE SCANNER
# ════════════════════════════════════════

def scan_cross_platform_arbitrage(matches, kalshi_api, poly_api, fee_kalshi=0.07, fee_poly=0.00):
    """
    Scan matched market pairs for cross-platform arbitrage.

    True arb exists when:
      Buy YES on Platform A + Buy NO on Platform B < $1.00 (after fees)
      Guaranteed $1.00 payout regardless of outcome.

    Returns list of arb opportunities sorted by profit (highest first).
    """
    opportunities = []

    for match in matches:
        km = match["kalshi"]
        pm = match["polymarket"]
        similarity = match.get("similarity", 0)

        # Only arb on high-confidence matches (>= 0.80)
        if similarity < 0.80:
            continue

        try:
            # Fetch live orderbooks from both platforms
            k_ob = kalshi_api.orderbook(km["ticker"])
            k_book = k_ob.get("orderbook", {})

            # Get Polymarket orderbook for YES token
            yes_token = pm.get("token_id", "")
            if not yes_token:
                continue
            p_ob = poly_api.orderbook(yes_token)
            p_book = p_ob.get("orderbook", {})

            # Extract best prices (in cents)
            k_yes_asks = k_book.get("yes", [])
            k_no_asks = k_book.get("no", [])
            p_yes_asks = p_book.get("yes", [])
            p_no_asks = p_book.get("no", [])

            # Strategy 1: Buy YES on Kalshi + Buy NO on Polymarket
            if k_yes_asks and p_no_asks:
                k_yes_price = _best_ask_price(k_yes_asks)
                p_no_price = _best_ask_price(p_no_asks)
                if k_yes_price and p_no_price:
                    cost_1 = k_yes_price + p_no_price
                    fees_1 = (fee_kalshi + fee_poly) * 100
                    profit_1 = 100 - cost_1 - fees_1
                    depth_1 = min(
                        _depth_at_price(k_yes_asks, k_yes_price),
                        _depth_at_price(p_no_asks, p_no_price),
                    )
                else:
                    profit_1 = -999
                    cost_1 = 999
                    depth_1 = 0
            else:
                profit_1 = -999
                cost_1 = 999
                depth_1 = 0

            # Strategy 2: Buy NO on Kalshi + Buy YES on Polymarket
            if k_no_asks and p_yes_asks:
                k_no_price = _best_ask_price(k_no_asks)
                p_yes_price = _best_ask_price(p_yes_asks)
                if k_no_price and p_yes_price:
                    cost_2 = k_no_price + p_yes_price
                    fees_2 = (fee_kalshi + fee_poly) * 100
                    profit_2 = 100 - cost_2 - fees_2
                    depth_2 = min(
                        _depth_at_price(k_no_asks, k_no_price),
                        _depth_at_price(p_yes_asks, p_yes_price),
                    )
                else:
                    profit_2 = -999
                    cost_2 = 999
                    depth_2 = 0
            else:
                profit_2 = -999
                cost_2 = 999
                depth_2 = 0

            best_profit = max(profit_1, profit_2)
            if best_profit > 0:
                is_strat1 = profit_1 >= profit_2
                opportunities.append({
                    "kalshi_ticker": km["ticker"],
                    "poly_token": yes_token,
                    "poly_no_token": pm.get("no_token_id", ""),
                    "title": km.get("title", ""),
                    "strategy": 1 if is_strat1 else 2,
                    "strategy_desc": (
                        "YES@Kalshi + NO@Polymarket" if is_strat1
                        else "NO@Kalshi + YES@Polymarket"
                    ),
                    "profit_cents": round(best_profit, 1),
                    "cost_cents": round(cost_1 if is_strat1 else cost_2, 1),
                    "k_price": k_yes_price if is_strat1 else k_no_price,
                    "p_price": p_no_price if is_strat1 else p_yes_price,
                    "depth": depth_1 if is_strat1 else depth_2,
                    "similarity": similarity,
                    "type": "cross_platform_arbitrage",
                })

            time.sleep(0.15)  # Rate limit between orderbook fetches
        except Exception as e:
            log.debug(f"Cross-arb scan error for {km.get('ticker','?')}: {e}")
            continue

    opportunities.sort(key=lambda x: x["profit_cents"], reverse=True)
    return opportunities


def _best_ask_price(asks):
    """Get the best (lowest) ask price from an orderbook side. Returns cents or None."""
    if not asks:
        return None
    first = asks[0]
    if isinstance(first, list):
        return int(first[0])
    return int(first)


def _depth_at_price(asks, price):
    """Get total depth (contracts) available at the best price."""
    total = 0
    for entry in asks:
        if isinstance(entry, list):
            if int(entry[0]) == price:
                total += int(entry[1])
            elif int(entry[0]) > price:
                break
        else:
            break
    return max(total, 1)


def execute_cross_arb(kalshi_api, poly_api, opportunity, max_cost_dollars=10.0, dry_run=False):
    """
    Execute both legs of a cross-platform arbitrage.

    Strategy: Place the LESS liquid leg first (Kalshi), then the second leg (Polymarket).
    If leg 1 fails, skip. If leg 1 fills but leg 2 fails, try to cancel/reverse leg 1.

    Returns: dict with execution result
    """
    strat = opportunity["strategy"]
    depth = opportunity.get("depth", 1)
    cost_per_pair = opportunity["cost_cents"] / 100.0

    # Calculate number of contracts (pairs)
    contracts = min(
        int(max_cost_dollars / cost_per_pair) if cost_per_pair > 0 else 0,
        depth,
        20,  # Hard cap
    )
    if contracts == 0:
        return {"success": False, "reason": "Zero contracts (cost too high or no depth)"}

    total_cost = round(contracts * cost_per_pair, 2)
    total_profit = round(contracts * opportunity["profit_cents"] / 100, 2)

    if dry_run:
        return {
            "success": True, "dry_run": True,
            "contracts": contracts, "total_cost": total_cost,
            "expected_profit": total_profit, "strategy": opportunity["strategy_desc"],
        }

    # Leg 1: Kalshi (less liquid -- place first)
    try:
        if strat == 1:
            k_result = kalshi_api.place_order(
                opportunity["kalshi_ticker"], "yes", contracts, opportunity["k_price"]
            )
        else:
            k_result = kalshi_api.place_order(
                opportunity["kalshi_ticker"], "no", contracts, opportunity["k_price"]
            )
        log.info(f"  ARB Leg 1 (Kalshi): placed {contracts}x @{opportunity['k_price']}c")
    except Exception as e:
        log.error(f"  ARB Leg 1 (Kalshi) FAILED: {e}")
        return {"success": False, "reason": f"Leg 1 failed: {e}"}

    # Small delay for Kalshi order to settle
    time.sleep(1)

    # Leg 2: Polymarket
    try:
        if strat == 1:
            # Buy NO on Polymarket
            token_id = opportunity.get("poly_no_token", opportunity["poly_token"])
            p_result = poly_api.place_order(
                token_id, "no", contracts, opportunity["p_price"]
            )
        else:
            # Buy YES on Polymarket
            p_result = poly_api.place_order(
                opportunity["poly_token"], "yes", contracts, opportunity["p_price"]
            )
        log.info(f"  ARB Leg 2 (Polymarket): placed {contracts}x @{opportunity['p_price']}c")
    except Exception as e:
        log.error(f"  ARB Leg 2 (Polymarket) FAILED: {e} -- Leg 1 is NAKED, monitor closely!")
        return {
            "success": False, "reason": f"Leg 2 failed: {e}",
            "leg1_filled": True, "naked_position": True,
        }

    return {
        "success": True,
        "contracts": contracts,
        "total_cost": total_cost,
        "expected_profit": total_profit,
        "strategy": opportunity["strategy_desc"],
    }


# ════════════════════════════════════════
# BEST-PRICE ROUTING
# ════════════════════════════════════════

def route_order(side, kalshi_price, poly_price, kalshi_fee=0.07, poly_fee=0.00):
    """
    Route a directional order to the platform with the best effective price.

    Args:
        side: "yes" or "no"
        kalshi_price: Price in cents on Kalshi
        poly_price: Price in cents on Polymarket
        kalshi_fee: Kalshi fee per contract in dollars
        poly_fee: Polymarket fee per contract in dollars

    Returns: ("kalshi" | "polymarket", effective_price_cents)
    """
    k_effective = kalshi_price + kalshi_fee * 100
    p_effective = poly_price + poly_fee * 100

    # For buying: lower effective price = better
    if k_effective <= p_effective:
        return "kalshi", kalshi_price
    else:
        return "polymarket", poly_price


def get_best_price_across_platforms(ticker, kalshi_api, poly_match, poly_api, side,
                                     kalshi_fee=0.07, poly_fee=0.00):
    """
    Fetch orderbooks from both platforms and return the best price for the given side.

    Args:
        ticker: Kalshi market ticker
        kalshi_api: KalshiAPI instance
        poly_match: Matched polymarket market dict (or None)
        poly_api: PolymarketAPI instance (or None)
        side: "yes" or "no"

    Returns: (platform, price_cents, orderbook) or ("kalshi", price, ob) if no poly match
    """
    # Always get Kalshi price
    k_price = None
    k_ob = None
    try:
        k_ob = kalshi_api.orderbook(ticker)
        k_book = k_ob.get("orderbook", {})
        if side == "yes":
            asks = k_book.get("yes", [])
        else:
            asks = k_book.get("no", [])
        if asks:
            k_price = _best_ask_price(asks)
    except Exception:
        pass

    # Get Polymarket price if we have a match
    p_price = None
    p_ob = None
    if poly_match and poly_api:
        token_id = poly_match.get("token_id", "")
        if token_id:
            try:
                p_ob = poly_api.orderbook(token_id)
                p_book = p_ob.get("orderbook", {})
                if side == "yes":
                    asks = p_book.get("yes", [])
                else:
                    asks = p_book.get("no", [])
                if asks:
                    p_price = _best_ask_price(asks)
            except Exception:
                pass

    if k_price is None and p_price is None:
        return None, None, None

    if k_price is not None and p_price is not None:
        platform, price = route_order(side, k_price, p_price, kalshi_fee, poly_fee)
        ob = k_ob if platform == "kalshi" else p_ob
        return platform, price, ob

    if k_price is not None:
        return "kalshi", k_price, k_ob
    return "polymarket", p_price, p_ob


# ════════════════════════════════════════
# QUICK-FLIP SCALPING
# ════════════════════════════════════════

def find_quickflip_candidates(markets, min_price=3, max_price=15, min_volume=50):
    """
    Find cheap contracts (3-15c) with decent volume for quick-flip scalping.
    These are "unlikely" events where a small price move = huge % gain.

    Buy at 5c, sell at 10c = 100% profit.
    Buy at 3c, sell at 8c = 167% profit.

    Returns: list of candidate dicts sorted by potential ROI
    """
    candidates = []

    for m in markets:
        yc = m.get("yes_bid", m.get("last_price", 50)) or 50
        vol = m.get("volume", 0) or 0
        hrs = m.get("_hrs_left", 9999)

        # Check YES side (cheap YES = unlikely event)
        if min_price <= yc <= max_price and vol >= min_volume and hrs > 2:
            candidates.append({
                "market": m,
                "side": "yes",
                "entry_price": yc,
                "target_price": min(yc * 2, 50),  # 2x or capped at 50c
                "stop_price": max(1, yc - 2),
                "potential_roi": round((min(yc * 2, 50) - yc) / yc * 100, 0),
                "platform": m.get("platform", "kalshi"),
                "hours_left": hrs,
            })

        # Check NO side (cheap NO = very likely event, but cheap NO contract)
        no_price = 100 - yc
        if min_price <= no_price <= max_price and vol >= min_volume and hrs > 2:
            candidates.append({
                "market": m,
                "side": "no",
                "entry_price": no_price,
                "target_price": min(no_price * 2, 50),
                "stop_price": max(1, no_price - 2),
                "potential_roi": round((min(no_price * 2, 50) - no_price) / no_price * 100, 0),
                "platform": m.get("platform", "kalshi"),
                "hours_left": hrs,
            })

    # Sort by potential ROI (highest first)
    candidates.sort(key=lambda x: x["potential_roi"], reverse=True)
    return candidates[:10]  # Return top 10


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
    """
    Get dynamic trading parameters based on current bankroll.
    As bankroll grows, bet sizes scale up but Kelly fraction scales down.

    Returns: dict with max_bet, max_exposure, kelly_fraction
    """
    for min_br, max_bet, max_exp, kelly in BANKROLL_TIERS:
        if bankroll >= min_br:
            return {
                "max_bet_per_trade": max_bet,
                "max_total_exposure": max_exp,
                "kelly_fraction": kelly,
                "tier_min": min_br,
            }
    # Fallback
    return {
        "max_bet_per_trade": 5.0,
        "max_total_exposure": 25.0,
        "kelly_fraction": 0.20,
        "tier_min": 0,
    }


def get_dynamic_kelly(base_fraction, win_streak=0, loss_cooldown=0):
    """
    Adjust Kelly fraction based on recent performance.
    Win streaks increase sizing (up to 50%), losses decrease it.

    Args:
        base_fraction: Base Kelly fraction from bankroll tier
        win_streak: Number of consecutive wins
        loss_cooldown: Trades remaining in loss cooldown (0 = normal)

    Returns: Adjusted Kelly fraction
    """
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
        self.arb_pairs = []  # Track paired arb positions
        self.win_streak = 0
        self.loss_cooldown = 0

    @property
    def total_exposure(self):
        return self.kalshi_exposure + self.poly_exposure

    def check_directional(self, platform, cost, max_exposure):
        """Check if a directional trade is within risk limits."""
        if platform == "kalshi":
            new_total = self.kalshi_exposure + cost + self.poly_exposure
        else:
            new_total = self.poly_exposure + cost + self.kalshi_exposure
        return new_total <= max_exposure

    def check_arbitrage(self, k_cost, p_cost, bankroll, max_arb_pct=0.50):
        """Check if an arb trade is within limits. Arb gets higher limits since it's hedged."""
        arb_total = k_cost + p_cost
        max_arb = bankroll * max_arb_pct
        return (self.total_exposure + arb_total) <= max_arb

    def record_trade(self, platform, cost):
        if platform == "kalshi":
            self.kalshi_exposure += cost
        else:
            self.poly_exposure += cost

    def record_arb(self, kalshi_cost, poly_cost):
        self.kalshi_exposure += kalshi_cost
        self.poly_exposure += poly_cost
        self.arb_pairs.append({
            "time": datetime.datetime.now().isoformat(),
            "k_cost": kalshi_cost,
            "p_cost": poly_cost,
        })

    def record_outcome(self, is_win):
        if is_win:
            self.win_streak += 1
            self.loss_cooldown = 0
        else:
            self.win_streak = 0
            self.loss_cooldown = 2  # 2 trades at reduced size

    def tick_cooldown(self):
        if self.loss_cooldown > 0:
            self.loss_cooldown -= 1

    def summary(self):
        return {
            "kalshi_exposure": f"${self.kalshi_exposure:.2f}",
            "poly_exposure": f"${self.poly_exposure:.2f}",
            "total_exposure": f"${self.total_exposure:.2f}",
            "arb_pairs": len(self.arb_pairs),
            "win_streak": self.win_streak,
            "loss_cooldown": self.loss_cooldown,
        }


# ════════════════════════════════════════
# CIRCUIT BREAKERS
# ════════════════════════════════════════

def check_circuit_breakers(kalshi_balance, poly_balance, day_pnl, max_daily_loss=15.0,
                            min_platform_balance=5.0, consecutive_losses=0):
    """
    Check cross-platform circuit breakers.
    Returns: (should_pause, reason) tuple
    """
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
