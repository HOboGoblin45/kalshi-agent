"""Market scoring, filtering, and Kelly criterion position sizing."""
import datetime
from decimal import Decimal, ROUND_DOWN

from modules.config import CFG, log
from modules.precision import to_decimal, MONEY_PLACES


def kelly(prob_pct, price_cents, bankroll, max_bet, fee, fraction=0.20):
    """Kelly criterion position sizing with fee-aware EV.

    All internal math uses Decimal to avoid float rounding errors.
    Returns (contracts: int, cost: float) for backward compat.
    """
    p = to_decimal(prob_pct) / 100
    price = to_decimal(price_cents) / 100  # dollars per contract
    fee_d = to_decimal(fee)
    bankroll_d = to_decimal(bankroll)
    max_bet_d = to_decimal(max_bet)
    frac = to_decimal(fraction)

    # Win payoff: $1 - price - 2x fee (entry + exit taker fee)
    win_payoff = Decimal("1") - price - fee_d * 2
    # Lose cost: price + entry fee (no exit fee needed -- contract expires worthless)
    lose_cost = price + fee_d

    if win_payoff <= 0:
        return 0, 0.0

    ev = p * win_payoff - (1 - p) * lose_cost
    if ev <= 0:
        return 0, 0.0

    # Kelly fraction: f* = (bp - q) / b
    b = win_payoff / lose_cost
    q = 1 - p
    if b <= 0:
        return 0, 0.0
    kf = max(Decimal("0"), ((b * p - q) / b) * frac)

    bet = min(kf * bankroll_d, max_bet_d)
    total_per = price + fee_d  # cost per contract to enter
    if total_per <= 0 or bet < total_per:
        return 0, 0.0

    contracts = int((bet / total_per).to_integral_value(rounding=ROUND_DOWN))
    contracts = max(1, contracts)
    # Ensure we don't exceed max bet
    while contracts > 0 and contracts * total_per > max_bet_d:
        contracts -= 1
    if contracts <= 0:
        return 0, 0.0

    cost = float((contracts * price).quantize(MONEY_PLACES))
    return contracts, cost


def calc_hours_left(m):
    close = m.get("close_time") or m.get("expiration_time") or ""
    if not close: return 9999
    try:
        ct = datetime.datetime.fromisoformat(close.replace("Z", "+00:00"))
        return (ct - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600
    except Exception: return 9999


def _best_price(m):
    """Return the best available YES price in cents, or None if truly unknown."""
    for k in ("display_price", "yes_bid", "last_price", "yes_ask"):
        v = m.get(k)
        if v and v > 0:
            return v
    nb = m.get("no_bid")
    if nb and 0 < nb < 100:
        return 100 - nb
    return None


def _count_parlay_legs(m):
    """Count number of outcome legs in a multi-outcome parlay market."""
    title = m.get("title") or ""
    if not title:
        return 1
    # Parlay titles are comma-separated legs starting with yes/no
    legs = [l.strip() for l in title.split(",") if l.strip()]
    if len(legs) <= 1:
        return 1
    # Verify they look like parlay legs (start with yes/no)
    parlay_legs = sum(1 for l in legs if l.lower().startswith(("yes ", "no ")))
    return max(1, parlay_legs) if parlay_legs >= 2 else 1


def score_market(m):
    s = 0; vol = m.get("volume", 0) or 0
    yc = _best_price(m) or 50
    hrs = m.get("_hrs_left", 9999); cat = m.get("_category", "other")

    if vol >= 1000: s += 4
    elif vol >= 500: s += 3
    elif vol >= 100: s += 2
    elif vol >= 20: s += 1

    if 25 <= yc <= 75: s += 3
    elif 15 <= yc <= 85: s += 2
    elif 8 <= yc <= 92: s += 1

    if 1 <= hrs <= 6: s += 6
    elif 6 < hrs <= 12: s += 5
    elif 12 < hrs <= 24: s += 4
    elif 24 < hrs <= 48: s += 2
    elif 48 < hrs <= 72: s += 1

    if cat in ("weather", "fed_rates", "inflation", "employment"): s += 3
    elif cat in ("energy", "policy", "sports", "crypto"): s += 2
    elif cat in ("gdp_growth", "markets"): s += 1

    if vol < 10: s -= 1
    if yc <= 15 or yc >= 85: s += 2
    if hrs <= 12 and (yc >= 85 or yc <= 15): s += 2

    # Penalize multi-leg parlays: each extra leg compounds losing probability
    legs = _count_parlay_legs(m)
    if legs >= 6: s -= 5       # 6+ legs = near-impossible, heavily penalize
    elif legs >= 4: s -= 3     # 4-5 legs = very unlikely
    elif legs >= 2: s -= 1     # 2-3 legs = mild penalty
    m["_parlay_legs"] = legs

    return s


def filter_and_rank(markets):
    kws = CFG["target_keywords"]; cat_rules = CFG.get("category_rules", {})
    short_term = []; long_term = []
    _f_price = 0; _f_vol = 0; _f_hrs = 0; _f_kw = 0; _close_samples = []
    for m in markets:
        yc = _best_price(m) or 50
        if yc > CFG["max_price_cents"] or yc < CFG["min_price_cents"]: _f_price += 1; continue
        if (m.get("volume", 0) or 0) < CFG["min_volume"]: _f_vol += 1; continue
        hrs = calc_hours_left(m)
        if hrs < CFG["min_close_hours"]: _f_hrs += 1; continue
        if len(_close_samples) < 3:
            _close_samples.append(f"{m.get('ticker', '?')}: hrs={hrs:.1f}")
        m["_hrs_left"] = hrs
        text = " ".join(str(m.get(k, "")) for k in ["title", "ticker", "category", "subtitle", "event_ticker"]).lower()
        if kws and not any(kw in text for kw in kws): _f_kw += 1; continue
        m["_category"] = "other"
        best_cat_score = 0
        for cat_name, cat_kws in cat_rules.items():
            hits = sum(1 for kw in cat_kws if kw in text)
            if hits > best_cat_score: best_cat_score = hits; m["_category"] = cat_name
        m["_score"] = score_market(m)
        if hrs <= CFG["max_close_hours"]: short_term.append(m)
        else: long_term.append(m)
    log.debug(f"Filter: {len(markets)} total -> price:{_f_price} vol:{_f_vol} hrs:{_f_hrs} kw:{_f_kw} dropped | {len(short_term)} short + {len(long_term)} long pass")
    if _close_samples: log.debug(f"Sample close times: {_close_samples}")
    short_term.sort(key=lambda x: x.get("_score", 0), reverse=True)
    long_term.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return short_term, long_term[:CFG["markets_per_scan"]]
