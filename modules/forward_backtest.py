"""
Forward-simulation backtester for the Kalshi AI Trading Agent.

Runs the debate engine on resolved markets to measure prediction
accuracy WITHOUT live trading. Compares AI probability estimates
against actual outcomes using Brier score and calibration metrics.

Usage (via CLI):
  python kalshi-agent.py --forward-backtest --resolved kalshi-resolved.json
"""
import json, math, os, datetime
from collections import defaultdict


class ForwardBacktestResult:
    """Container for forward backtest results."""

    def __init__(self):
        self.predictions = []     # list of {ticker, title, ai_prob, market_price, actual, ...}
        self.total = 0
        self.correct_side = 0     # AI side matched actual outcome
        self.brier_sum = 0.0
        self.market_brier_sum = 0.0
        self.by_category = defaultdict(lambda: {
            "count": 0, "correct": 0, "brier_sum": 0.0, "market_brier_sum": 0.0
        })
        self.by_confidence = defaultdict(lambda: {
            "count": 0, "correct": 0, "brier_sum": 0.0
        })
        self.calibration_buckets = defaultdict(lambda: {
            "predictions": [], "outcomes": []
        })
        self.errors = []          # markets where debate failed

    @property
    def brier_score(self):
        """Lower is better. 0 = perfect, 0.25 = random."""
        return self.brier_sum / self.total if self.total > 0 else 1.0

    @property
    def market_brier_score(self):
        """Brier score using market prices as predictions."""
        return self.market_brier_sum / self.total if self.total > 0 else 1.0

    @property
    def accuracy(self):
        """Percentage of markets where AI picked the correct side."""
        return self.correct_side / self.total * 100 if self.total > 0 else 0

    @property
    def brier_skill(self):
        """Brier Skill Score: 1 - (AI_brier / market_brier). Positive = better than market."""
        if self.market_brier_score == 0:
            return 0.0
        return 1.0 - (self.brier_score / self.market_brier_score)


def run_forward_backtest(resolved_markets, debate_fn, category_fn=None):
    """
    Run the debate engine on resolved markets and measure accuracy.

    Args:
        resolved_markets: list of dicts with {ticker, title, result, yes_ask, ...}
        debate_fn: callable(market_dict) -> debate_result_dict with keys
                   {probability, confidence, side, bull_prob, bear_prob, evidence}
        category_fn: optional callable(market_dict) -> category string

    Returns:
        ForwardBacktestResult with all accuracy metrics
    """
    result = ForwardBacktestResult()

    for market in resolved_markets:
        ticker = market.get("ticker", "?")
        actual_result = market.get("result", "")
        if actual_result not in ("yes", "no"):
            continue

        actual_yes = 1 if actual_result == "yes" else 0
        market_price = market.get("yes_ask", 50)
        if isinstance(market_price, (int, float)) and market_price > 1:
            market_prob = market_price / 100.0
        else:
            market_prob = market_price if market_price <= 1 else 0.5

        # Build a market dict compatible with debate engine
        debate_market = {
            "ticker": ticker,
            "title": market.get("title", ""),
            "subtitle": market.get("subtitle", ""),
            "display_price": market_price,
            "yes_bid": market_price,
            "volume": market.get("volume", 0),
            "close_time": market.get("close_time", ""),
            "_hrs_left": 0,
            "_category": market.get("category", "other"),
        }

        try:
            debate_result = debate_fn(debate_market)
        except Exception as e:
            result.errors.append({"ticker": ticker, "error": str(e)})
            continue

        ai_prob_pct = debate_result.get("probability", 50)
        ai_prob = ai_prob_pct / 100.0
        ai_side = debate_result.get("side", "HOLD")
        confidence = debate_result.get("confidence", 50)
        category = category_fn(market) if category_fn else market.get("category", "other")

        # Brier scores
        brier = (ai_prob - actual_yes) ** 2
        market_brier = (market_prob - actual_yes) ** 2

        # Did AI pick the correct side?
        correct = False
        if ai_side == "YES" and actual_result == "yes":
            correct = True
        elif ai_side == "NO" and actual_result == "no":
            correct = True

        result.total += 1
        result.brier_sum += brier
        result.market_brier_sum += market_brier
        if correct:
            result.correct_side += 1

        # By category
        result.by_category[category]["count"] += 1
        result.by_category[category]["brier_sum"] += brier
        result.by_category[category]["market_brier_sum"] += market_brier
        if correct:
            result.by_category[category]["correct"] += 1

        # By confidence bucket
        conf_bucket = f"{(confidence // 10) * 10}-{(confidence // 10) * 10 + 9}%"
        result.by_confidence[conf_bucket]["count"] += 1
        result.by_confidence[conf_bucket]["brier_sum"] += brier
        if correct:
            result.by_confidence[conf_bucket]["correct"] += 1

        # Calibration buckets (10% wide)
        prob_bucket = f"{(ai_prob_pct // 10) * 10}-{(ai_prob_pct // 10) * 10 + 9}%"
        result.calibration_buckets[prob_bucket]["predictions"].append(ai_prob_pct)
        result.calibration_buckets[prob_bucket]["outcomes"].append(actual_yes)

        prediction = {
            "ticker": ticker,
            "title": market.get("title", ""),
            "category": category,
            "ai_prob": ai_prob_pct,
            "market_price": market_price,
            "actual": actual_result,
            "side": ai_side,
            "correct": correct,
            "confidence": confidence,
            "brier": round(brier, 4),
            "market_brier": round(market_brier, 4),
            "bull_prob": debate_result.get("bull_prob", 0),
            "bear_prob": debate_result.get("bear_prob", 0),
            "evidence": debate_result.get("evidence", ""),
        }
        result.predictions.append(prediction)

    return result


def format_forward_report(result):
    """Format forward backtest results as a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("FORWARD BACKTEST REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Markets tested:    {result.total}")
    lines.append(f"Errors/skipped:    {len(result.errors)}")
    lines.append(f"Side accuracy:     {result.accuracy:.1f}%")
    lines.append(f"AI Brier score:    {result.brier_score:.4f}")
    lines.append(f"Market Brier:      {result.market_brier_score:.4f}")
    lines.append(f"Brier Skill Score: {result.brier_skill:+.4f}")

    skill_note = ""
    if result.brier_skill > 0:
        skill_note = " (AI beats market)"
    elif result.brier_skill < 0:
        skill_note = " (market beats AI)"
    else:
        skill_note = " (tied)"
    lines.append(f"  Interpretation:  {skill_note.strip()}")

    if result.by_category:
        lines.append("")
        lines.append("BY CATEGORY:")
        lines.append(f"  {'Category':<15} {'N':>4} {'Acc%':>6} {'Brier':>7} {'Mkt Brier':>10}")
        for cat, stats in sorted(result.by_category.items(), key=lambda x: -x[1]["count"]):
            n = stats["count"]
            acc = stats["correct"] / n * 100 if n > 0 else 0
            brier = stats["brier_sum"] / n if n > 0 else 0
            mkt_brier = stats["market_brier_sum"] / n if n > 0 else 0
            lines.append(f"  {cat:<15} {n:>4} {acc:>5.1f}% {brier:>7.4f} {mkt_brier:>10.4f}")

    if result.calibration_buckets:
        lines.append("")
        lines.append("CALIBRATION (AI predicted vs actual):")
        lines.append(f"  {'Bucket':<10} {'N':>4} {'Predicted':>10} {'Actual':>8} {'Gap':>7}")
        for bucket, data in sorted(result.calibration_buckets.items()):
            preds = data["predictions"]
            outcomes = data["outcomes"]
            if not outcomes:
                continue
            predicted_avg = sum(preds) / len(preds)
            actual_rate = sum(outcomes) / len(outcomes) * 100
            gap = actual_rate - predicted_avg
            lines.append(f"  {bucket:<10} {len(outcomes):>4} {predicted_avg:>9.1f}% "
                         f"{actual_rate:>6.1f}% {gap:>+6.1f}%")

    if result.errors:
        lines.append("")
        lines.append(f"ERRORS ({len(result.errors)}):")
        for err in result.errors[:10]:
            lines.append(f"  {err['ticker']}: {err['error'][:80]}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
