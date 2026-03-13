"""Market scoring, filtering, and Kelly criterion position sizing."""
import datetime

from modules.config import CFG, log


def kelly(prob_pct, price_cents, bankroll, max_bet, fee, fraction=0.20):
    p = prob_pct / 100.0; price = price_cents / 100.0
    win_payoff = (1.0 - price) - fee; lose_cost = price + fee
    if win_payoff <= 0: return 0, 0
    ev = p * win_payoff - (1 - p) * lose_cost
    if ev <= 0: return 0, 0
    b = win_payoff / lose_cost; q = 1 - p
    kf = max(0, ((b * p - q) / b) * fraction) if b > 0 else 0
    bet = min(kf * bankroll, max_bet)
    total_per = price + fee
    contracts = max(1, int(bet / total_per)) if bet >= total_per else 0
    while contracts > 0 and contracts * total_per > max_bet: contracts -= 1
    return contracts, round(contracts * price, 2)


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
