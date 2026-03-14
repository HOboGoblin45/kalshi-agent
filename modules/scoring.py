"""Market scoring, filtering, feature extraction, and Kelly criterion sizing."""
import datetime
from decimal import Decimal, ROUND_DOWN

from modules.config import CFG, log
from modules.precision import to_decimal, MONEY_PLACES


# ── Upgrade 3: Category-Specific Kelly Caps ──
# Max Kelly fraction per category. Categories with stronger data edges
# can tolerate larger positions; speculative categories are capped lower.
DEFAULT_CATEGORY_KELLY_CAPS = {
    "weather":    0.25,   # Strong data edge (NWS, NOAA)
    "fed_rates":  0.22,   # Reliable public data (FOMC dots)
    "inflation":  0.20,   # CPI/PCE published data
    "employment": 0.20,   # BLS data
    "sports":     0.12,   # High variance, limited edge
    "crypto":     0.10,   # Very high variance
    "policy":     0.12,   # Speculative, hard to model
    "energy":     0.15,   # Moderate data availability
    "gdp_growth": 0.15,   # Moderate data
    "markets":    0.12,   # Random walk assumption
    "other":      0.10,   # Unknown category, be cautious
}


def thorp_concurrent_reduction(kelly_fraction, n_concurrent_bets):
    """Thorp's simultaneous bet reduction: f_adj = f / sqrt(n).

    With more concurrent positions, each individual bet should be smaller
    to maintain the same overall risk level.

    - 1 bet: full Kelly
    - 4 bets: half Kelly
    - 9 bets: 1/3 Kelly
    """
    import math
    n = max(1, n_concurrent_bets)
    return kelly_fraction / math.sqrt(n)


def bayesian_kelly_prob(raw_prob_pct, category_wins, category_total, prior_alpha=2, prior_beta=2):
    """Bayesian shrinkage of probability estimate using Beta-Binomial posterior.

    Shrinks our raw probability toward 50% based on how much calibration data
    we have for this category. With few observations, heavy shrinkage. With
    many observations and good calibration, minimal shrinkage.

    p_adjusted = (α + wins) / (α + β + n)
    Then blend: p_final = weight * raw_prob + (1 - weight) * p_posterior
    where weight = n / (n + α + β)  -- grows toward 1 as data accumulates.

    Returns adjusted probability percentage (0-100).
    """
    n = max(0, category_total)
    wins = max(0, min(n, category_wins))

    # Posterior mean from Beta-Binomial
    posterior_mean = (prior_alpha + wins) / (prior_alpha + prior_beta + n)

    # Weight: how much to trust our raw estimate vs the posterior
    # With 0 data: weight ≈ 0 (full shrinkage toward 50%)
    # With 20+ data: weight ≈ 0.83+ (mostly trust raw prob)
    weight = n / (n + prior_alpha + prior_beta) if (n + prior_alpha + prior_beta) > 0 else 0

    raw_frac = raw_prob_pct / 100.0
    adjusted = weight * raw_frac + (1 - weight) * posterior_mean

    # Clamp to [1, 99] to avoid extreme positions
    return max(1.0, min(99.0, adjusted * 100.0))


def debate_spread_kelly_mult(debate_spread_pct):
    """Continuous Kelly multiplier based on bull-bear debate spread.

    When bull and bear disagree strongly (high spread), reduce Kelly.
    When they agree (low spread), full Kelly.

    Formula: mult = max(0.3, 1 - spread/50)
    - spread=0% → mult=1.0 (full agreement, full Kelly)
    - spread=20% → mult=0.6 (moderate disagreement)
    - spread>=35% → mult=0.3 (floor, high disagreement)
    """
    spread = max(0, abs(debate_spread_pct))
    return max(0.3, 1.0 - spread / 50.0)


def get_category_kelly_cap(category, user_caps=None):
    """Get the max Kelly fraction for a category.

    User can override defaults via config 'category_kelly_caps'.
    """
    caps = {**DEFAULT_CATEGORY_KELLY_CAPS}
    if user_caps:
        caps.update(user_caps)
    return caps.get(category, caps.get("other", 0.10))


def dynamic_min_edge(price_cents, fee_per_contract=0.07, base_min_edge=1.0):
    """Dynamic fee-drag minimum edge: 2 * fee / price + base%.

    At low prices, fee drag is large (e.g., 7c fee on 10c contract = 140%).
    At high prices, fee drag shrinks (7c on 50c = 28%).
    This ensures we never trade when fees eat the edge.

    Returns min edge as a percentage.
    """
    if price_cents <= 0:
        return 99.0
    fee_drag_pct = (2 * fee_per_contract * 100) / price_cents
    return fee_drag_pct + base_min_edge


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
    legs = [l.strip() for l in title.split(",") if l.strip()]
    if len(legs) <= 1:
        return 1
    parlay_legs = sum(1 for l in legs if l.lower().startswith(("yes ", "no ")))
    return max(1, parlay_legs) if parlay_legs >= 2 else 1


# ── Feature Extraction ──

def extract_features(m):
    """Extract a feature dict from a market for scoring and analysis.

    Separates feature extraction from scoring so features can be used
    by calibration, debugging, and dashboard independently.
    """
    vol = m.get("volume", 0) or 0
    yc = _best_price(m) or 50
    hrs = m.get("_hrs_left", 9999)
    cat = m.get("_category", "other")
    legs = _count_parlay_legs(m)

    # Liquidity quality: ratio of volume to a reasonable threshold
    liquidity_score = min(4, int(vol / 250))  # 0-4 scale

    # Price informativeness: how much room for edge (extreme prices = more edge potential)
    if 25 <= yc <= 75:
        price_score = 3
    elif 15 <= yc <= 85:
        price_score = 2
    elif 8 <= yc <= 92:
        price_score = 1
    else:
        price_score = 0

    # Time urgency: closer to expiry = higher urgency
    if 1 <= hrs <= 6:
        time_score = 6
    elif 6 < hrs <= 12:
        time_score = 5
    elif 12 < hrs <= 24:
        time_score = 4
    elif 24 < hrs <= 48:
        time_score = 2
    elif 48 < hrs <= 72:
        time_score = 1
    else:
        time_score = 0

    # Category data availability bonus
    data_rich_cats = {"weather", "fed_rates", "inflation", "employment"}
    moderate_cats = {"energy", "policy", "sports", "crypto"}
    if cat in data_rich_cats:
        cat_score = 3
    elif cat in moderate_cats:
        cat_score = 2
    elif cat in ("gdp_growth", "markets"):
        cat_score = 1
    else:
        cat_score = 0

    # Parlay penalty
    if legs >= 6:
        parlay_penalty = -5
    elif legs >= 4:
        parlay_penalty = -3
    elif legs >= 2:
        parlay_penalty = -1
    else:
        parlay_penalty = 0

    # Asymmetric opportunity: cheap contracts near expiry with data
    asymmetric_bonus = 0
    if (yc <= 15 or yc >= 85):
        asymmetric_bonus += 2
    if hrs <= 12 and (yc >= 85 or yc <= 15):
        asymmetric_bonus += 2

    # Thin market penalty
    thin_penalty = -1 if vol < 10 else 0

    features = {
        "price_cents": yc,
        "volume": vol,
        "hours_left": hrs,
        "category": cat,
        "parlay_legs": legs,
        "liquidity_score": liquidity_score,
        "price_score": price_score,
        "time_score": time_score,
        "cat_score": cat_score,
        "parlay_penalty": parlay_penalty,
        "asymmetric_bonus": asymmetric_bonus,
        "thin_penalty": thin_penalty,
        # Quality flags
        "is_thin": vol < 10,
        "is_expiring_soon": 0 < hrs <= 6,
        "is_deep_otm": yc <= 10 or yc >= 90,
        "is_parlay": legs >= 2,
        "has_data_source": cat in data_rich_cats,
    }
    return features


def score_market(m):
    """Score a market for scan priority using extracted features."""
    features = extract_features(m)
    s = (features["liquidity_score"]
         + features["price_score"]
         + features["time_score"]
         + features["cat_score"]
         + features["parlay_penalty"]
         + features["asymmetric_bonus"]
         + features["thin_penalty"])

    m["_parlay_legs"] = features["parlay_legs"]
    m["_features"] = features
    return s


# ── Execution Eligibility ──

def is_execution_eligible(m, features=None):
    """Determine if a market is eligible for automated execution.

    Returns (eligible: bool, reason: str).
    Separate from scoring -- a high-scoring market may still not be
    safe to trade if liquidity or data quality is poor.
    """
    if features is None:
        features = extract_features(m)

    # Hard filters
    if features["is_thin"] and features["volume"] < 5:
        return False, "Extremely thin market (<5 volume)"

    if features["parlay_legs"] >= 4:
        return False, f"Too many parlay legs ({features['parlay_legs']})"

    if features["hours_left"] < 0.25:  # < 15 minutes
        return False, "Too close to expiry (<15min)"

    # Soft warning: still eligible but flagged
    return True, "OK"


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
