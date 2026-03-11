#!/usr/bin/env python3
"""
Backtesting engine for the Kalshi AI Trading Agent.

Replays historical trade data from kalshi-trades.json and kalshi-calibration.json
to analyze strategy performance, calibration accuracy, and risk metrics.

Usage:
  python backtester.py --trades kalshi-trades.json
  python backtester.py --trades kalshi-trades.json --calibration kalshi-calibration.json
  python backtester.py --trades kalshi-trades.json --by-category
  python backtester.py --trades kalshi-trades.json --by-platform
"""
import argparse, json, os, sys, datetime, math
from collections import defaultdict


class BacktestResult:
    """Container for backtest results."""

    def __init__(self):
        self.trades = []
        self.wins = 0
        self.losses = 0
        self.open_trades = 0
        self.total_wagered = 0.0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        self.peak_equity = 0.0
        self.equity_curve = []
        self.by_category = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "wagered": 0.0})
        self.by_platform = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "wagered": 0.0})
        self.by_side = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
        self.by_confidence_bucket = defaultdict(lambda: {"wins": 0, "losses": 0, "count": 0})
        self.daily_pnl = defaultdict(float)
        self.winning_streak = 0
        self.losing_streak = 0
        self.max_winning_streak = 0
        self.max_losing_streak = 0

    @property
    def total_resolved(self):
        return self.wins + self.losses

    @property
    def win_rate(self):
        return self.wins / self.total_resolved * 100 if self.total_resolved > 0 else 0

    @property
    def avg_win(self):
        win_pnls = [t["pnl"] for t in self.trades if t.get("status") == "win"]
        return sum(win_pnls) / len(win_pnls) if win_pnls else 0

    @property
    def avg_loss(self):
        loss_pnls = [t["pnl"] for t in self.trades if t.get("status") == "loss"]
        return sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0

    @property
    def profit_factor(self):
        gross_wins = sum(t["pnl"] for t in self.trades if t.get("pnl", 0) > 0)
        gross_losses = abs(sum(t["pnl"] for t in self.trades if t.get("pnl", 0) < 0))
        return gross_wins / gross_losses if gross_losses > 0 else float("inf")

    @property
    def sharpe_estimate(self):
        """Rough daily Sharpe ratio estimate."""
        if len(self.daily_pnl) < 2:
            return 0.0
        daily_returns = list(self.daily_pnl.values())
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std = math.sqrt(variance) if variance > 0 else 1
        return round(mean_ret / std * math.sqrt(252), 2)  # Annualized


def run_backtest(trades, initial_bankroll=100.0):
    """
    Run a backtest over historical trades.

    Args:
        trades: list of trade dicts from kalshi-trades.json
        initial_bankroll: starting capital

    Returns:
        BacktestResult with all metrics
    """
    result = BacktestResult()
    equity = initial_bankroll

    for trade in sorted(trades, key=lambda t: t.get("time", "")):
        status = trade.get("status", "open")
        cost = trade.get("cost", 0)
        pnl = trade.get("pnl", 0)
        category = _infer_category(trade)
        platform = trade.get("platform", "kalshi")
        side = trade.get("side", "unknown")
        confidence = trade.get("confidence", 0)
        day = trade.get("time", "")[:10]

        result.trades.append(trade)
        result.total_wagered += cost

        if status == "win":
            result.wins += 1
            result.winning_streak += 1
            result.losing_streak = 0
            result.max_winning_streak = max(result.max_winning_streak, result.winning_streak)
        elif status == "loss":
            result.losses += 1
            result.losing_streak += 1
            result.winning_streak = 0
            result.max_losing_streak = max(result.max_losing_streak, result.losing_streak)
        else:
            result.open_trades += 1

        if status in ("win", "loss"):
            equity += pnl
            result.total_pnl += pnl
            result.daily_pnl[day] += pnl

            # Track peak and drawdown
            if equity > result.peak_equity:
                result.peak_equity = equity
            drawdown = result.peak_equity - equity
            if drawdown > result.max_drawdown:
                result.max_drawdown = drawdown

            # By category
            result.by_category[category]["pnl"] += pnl
            result.by_category[category]["wagered"] += cost
            if status == "win":
                result.by_category[category]["wins"] += 1
            else:
                result.by_category[category]["losses"] += 1

            # By platform
            result.by_platform[platform]["pnl"] += pnl
            result.by_platform[platform]["wagered"] += cost
            if status == "win":
                result.by_platform[platform]["wins"] += 1
            else:
                result.by_platform[platform]["losses"] += 1

            # By side
            if status == "win":
                result.by_side[side]["wins"] += 1
            else:
                result.by_side[side]["losses"] += 1
            result.by_side[side]["pnl"] += pnl

            # By confidence bucket
            bucket = f"{(confidence // 10) * 10}-{(confidence // 10) * 10 + 9}%"
            result.by_confidence_bucket[bucket]["count"] += 1
            if status == "win":
                result.by_confidence_bucket[bucket]["wins"] += 1
            else:
                result.by_confidence_bucket[bucket]["losses"] += 1

        result.equity_curve.append(round(equity, 2))

    return result


def analyze_calibration(calibration_records):
    """
    Analyze prediction calibration: were our probability estimates accurate?

    Groups predictions into 10% buckets and compares predicted vs actual win rates.

    Returns dict of bucket -> {predicted_avg, actual_win_rate, count, gap}
    """
    buckets = defaultdict(lambda: {"predictions": [], "outcomes": []})

    for rec in calibration_records:
        prob = rec.get("our_probability", 50)
        resolved = rec.get("resolved")
        if resolved is None:
            continue

        bucket = f"{(prob // 10) * 10}-{(prob // 10) * 10 + 9}%"
        buckets[bucket]["predictions"].append(prob)
        buckets[bucket]["outcomes"].append(1 if resolved else 0)

    results = {}
    for bucket, data in sorted(buckets.items()):
        preds = data["predictions"]
        outcomes = data["outcomes"]
        if not outcomes:
            continue
        predicted_avg = sum(preds) / len(preds)
        actual_rate = sum(outcomes) / len(outcomes) * 100
        results[bucket] = {
            "predicted_avg": round(predicted_avg, 1),
            "actual_win_rate": round(actual_rate, 1),
            "count": len(outcomes),
            "gap": round(actual_rate - predicted_avg, 1),
        }
    return results


def _infer_category(trade):
    """Infer market category from trade data."""
    title = (trade.get("title", "") + " " + trade.get("ticker", "")).lower()
    categories = {
        "weather": ["temperature", "weather", "storm", "hurricane", "rainfall", "snowfall"],
        "fed_rates": ["fed", "fomc", "interest rate", "rate cut", "rate hike"],
        "inflation": ["inflation", "cpi", "pce"],
        "employment": ["unemployment", "jobs", "nonfarm", "payroll"],
        "energy": ["oil", "gas price", "opec", "wti"],
        "markets": ["s&p", "nasdaq", "dow", "treasury"],
        "policy": ["congress", "regulation", "tariff", "executive order"],
    }
    for cat, keywords in categories.items():
        if any(kw in title for kw in keywords):
            return cat
    return "other"


def format_report(result, calibration=None):
    """Format backtest results as a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("BACKTEST REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total trades:      {len(result.trades)}")
    lines.append(f"Resolved:          {result.total_resolved} ({result.wins}W / {result.losses}L)")
    lines.append(f"Open:              {result.open_trades}")
    lines.append(f"Win rate:          {result.win_rate:.1f}%")
    lines.append(f"Total wagered:     ${result.total_wagered:.2f}")
    lines.append(f"Total P&L:         ${result.total_pnl:.2f}")
    lines.append(f"Avg win:           ${result.avg_win:.2f}")
    lines.append(f"Avg loss:          ${result.avg_loss:.2f}")
    lines.append(f"Profit factor:     {result.profit_factor:.2f}")
    lines.append(f"Max drawdown:      ${result.max_drawdown:.2f}")
    lines.append(f"Best streak:       {result.max_winning_streak}W")
    lines.append(f"Worst streak:      {result.max_losing_streak}L")
    lines.append(f"Sharpe (est):      {result.sharpe_estimate}")

    if result.by_category:
        lines.append("")
        lines.append("BY CATEGORY:")
        lines.append(f"  {'Category':<15} {'W':>4} {'L':>4} {'Rate':>6} {'P&L':>8} {'Wagered':>8}")
        for cat, stats in sorted(result.by_category.items(), key=lambda x: -x[1]["pnl"]):
            total = stats["wins"] + stats["losses"]
            rate = stats["wins"] / total * 100 if total > 0 else 0
            lines.append(f"  {cat:<15} {stats['wins']:>4} {stats['losses']:>4} "
                          f"{rate:>5.0f}% ${stats['pnl']:>7.2f} ${stats['wagered']:>7.2f}")

    if result.by_platform:
        lines.append("")
        lines.append("BY PLATFORM:")
        for plat, stats in sorted(result.by_platform.items()):
            total = stats["wins"] + stats["losses"]
            rate = stats["wins"] / total * 100 if total > 0 else 0
            lines.append(f"  {plat:<15} {stats['wins']}W/{stats['losses']}L "
                          f"({rate:.0f}%) P&L: ${stats['pnl']:.2f}")

    if result.by_confidence_bucket:
        lines.append("")
        lines.append("BY CONFIDENCE:")
        lines.append(f"  {'Bucket':<10} {'Count':>6} {'Win%':>6}")
        for bucket, stats in sorted(result.by_confidence_bucket.items()):
            total = stats["count"]
            rate = stats["wins"] / total * 100 if total > 0 else 0
            lines.append(f"  {bucket:<10} {total:>6} {rate:>5.0f}%")

    if calibration:
        lines.append("")
        lines.append("CALIBRATION (predicted vs actual):")
        lines.append(f"  {'Bucket':<10} {'Predicted':>10} {'Actual':>8} {'Gap':>6} {'N':>4}")
        for bucket, stats in sorted(calibration.items()):
            lines.append(f"  {bucket:<10} {stats['predicted_avg']:>9.1f}% "
                          f"{stats['actual_win_rate']:>6.1f}% {stats['gap']:>+5.1f}% {stats['count']:>4}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Kalshi Agent Backtester")
    ap.add_argument("--trades", required=True, help="Path to kalshi-trades.json")
    ap.add_argument("--calibration", default="", help="Path to kalshi-calibration.json")
    ap.add_argument("--bankroll", type=float, default=100.0, help="Initial bankroll")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    if not os.path.exists(args.trades):
        print(f"Error: {args.trades} not found")
        sys.exit(1)

    with open(args.trades) as f:
        trades = json.load(f)

    result = run_backtest(trades, initial_bankroll=args.bankroll)

    calibration = None
    if args.calibration and os.path.exists(args.calibration):
        with open(args.calibration) as f:
            cal_records = json.load(f)
        calibration = analyze_calibration(cal_records)

    if args.json:
        output = {
            "total_trades": len(result.trades),
            "wins": result.wins, "losses": result.losses,
            "win_rate": round(result.win_rate, 1),
            "total_pnl": round(result.total_pnl, 2),
            "max_drawdown": round(result.max_drawdown, 2),
            "profit_factor": round(result.profit_factor, 2),
            "sharpe": result.sharpe_estimate,
            "by_category": dict(result.by_category),
            "by_platform": dict(result.by_platform),
        }
        if calibration:
            output["calibration"] = calibration
        print(json.dumps(output, indent=2))
    else:
        print(format_report(result, calibration))


if __name__ == "__main__":
    main()
