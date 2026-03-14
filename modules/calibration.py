"""Calibration tracking: Brier score, log loss, and reliability metrics.

Records predictions alongside outcomes to measure and improve
forecast accuracy over time.
"""
import json, os, math, datetime
from collections import defaultdict
from modules.config import CFG, log


class CalibrationTracker:
    """Track prediction accuracy with rolling calibration statistics."""

    def __init__(self, log_path=None):
        self.log_path = log_path or CFG.get("calibration_log", "kalshi-calibration.json")
        self.records = []
        self._load()

    def _load(self):
        if os.path.isfile(self.log_path):
            try:
                with open(self.log_path) as f:
                    self.records = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.records = []

    def _save(self):
        try:
            # Keep last 5000 records
            if len(self.records) > 5000:
                self.records = self.records[-5000:]
            with open(self.log_path, "w") as f:
                json.dump(self.records, f, indent=2, default=str)
        except OSError as e:
            log.warning(f"Failed to save calibration log: {e}")

    def record_prediction(self, ticker, side, probability, confidence,
                          market_price, edge, category="other",
                          bull_prob=0, bear_prob=0, debate_spread=0):
        """Record a new prediction (outcome unknown yet)."""
        self.records.append({
            "time": datetime.datetime.now().isoformat(),
            "ticker": ticker,
            "side": side,
            "our_probability": probability,
            "our_confidence": confidence,
            "market_price": market_price,
            "edge": edge,
            "category": category,
            "bull_prob": bull_prob,
            "bear_prob": bear_prob,
            "debate_spread": debate_spread,
            "resolved": None,  # True/False when outcome known
            "resolution_time": None,
        })
        self._save()

    def record_outcome(self, ticker, resolved_yes: bool):
        """Record the actual outcome of a market."""
        for r in reversed(self.records):
            if r["ticker"] == ticker and r["resolved"] is None:
                r["resolved"] = resolved_yes if r["side"] == "YES" else not resolved_yes
                r["resolution_time"] = datetime.datetime.now().isoformat()
                break
        self._save()

    def brier_score(self, category=None, last_n=None) -> float:
        """Calculate Brier score (lower is better, 0 = perfect, 0.25 = random).

        Brier score = mean((forecast_prob - outcome)^2)
        """
        resolved = self._get_resolved(category, last_n)
        if not resolved:
            return 0.25  # random baseline
        total = 0.0
        for r in resolved:
            prob = r["our_probability"] / 100.0
            outcome = 1.0 if r["resolved"] else 0.0
            total += (prob - outcome) ** 2
        return total / len(resolved)

    def log_loss(self, category=None, last_n=None) -> float:
        """Calculate log loss (lower is better)."""
        resolved = self._get_resolved(category, last_n)
        if not resolved:
            return 1.0  # bad baseline
        total = 0.0
        eps = 1e-15  # avoid log(0)
        for r in resolved:
            prob = max(eps, min(1 - eps, r["our_probability"] / 100.0))
            outcome = 1.0 if r["resolved"] else 0.0
            total += -(outcome * math.log(prob) + (1 - outcome) * math.log(1 - prob))
        return total / len(resolved)

    def reliability_bins(self, category=None, n_bins=10) -> list:
        """Create reliability diagram data (predicted prob vs observed freq).

        Returns list of {bin_center, predicted_avg, observed_freq, count}.
        """
        resolved = self._get_resolved(category)
        if not resolved:
            return []
        bins = defaultdict(lambda: {"predicted_sum": 0, "outcome_sum": 0, "count": 0})
        bin_width = 100 / n_bins
        for r in resolved:
            bin_idx = min(int(r["our_probability"] / bin_width), n_bins - 1)
            bins[bin_idx]["predicted_sum"] += r["our_probability"]
            bins[bin_idx]["outcome_sum"] += 1 if r["resolved"] else 0
            bins[bin_idx]["count"] += 1
        result = []
        for i in range(n_bins):
            b = bins[i]
            if b["count"] > 0:
                result.append({
                    "bin_center": (i + 0.5) * bin_width,
                    "predicted_avg": b["predicted_sum"] / b["count"],
                    "observed_freq": b["outcome_sum"] / b["count"] * 100,
                    "count": b["count"],
                })
        return result

    def category_stats(self) -> dict:
        """Per-category calibration statistics."""
        categories = defaultdict(list)
        for r in self.records:
            if r["resolved"] is not None:
                categories[r.get("category", "other")].append(r)
        result = {}
        for cat, records in categories.items():
            wins = sum(1 for r in records if r["resolved"])
            result[cat] = {
                "total": len(records),
                "wins": wins,
                "win_rate": round(wins / len(records) * 100, 1) if records else 0,
                "brier": self.brier_score(cat),
                "avg_edge": round(sum(r["edge"] for r in records) / len(records), 1) if records else 0,
            }
        return result

    def should_trade_category(self, category: str, min_records=10) -> tuple:
        """Check if our calibration for this category is good enough to trade.

        Returns (ok: bool, reason: str).
        """
        resolved = self._get_resolved(category)
        if len(resolved) < min_records:
            return True, f"Insufficient data ({len(resolved)}/{min_records} records)"

        brier = self.brier_score(category)
        if brier > 0.30:
            return False, f"Poor calibration (Brier={brier:.3f} > 0.30)"

        return True, f"OK (Brier={brier:.3f}, n={len(resolved)})"

    def summary(self) -> dict:
        """Overall calibration summary for dashboard."""
        resolved = self._get_resolved()
        total = len(self.records)
        return {
            "total_predictions": total,
            "resolved": len(resolved),
            "pending": total - len(resolved),
            "overall_brier": round(self.brier_score(), 4),
            "overall_log_loss": round(self.log_loss(), 4),
            "category_stats": self.category_stats(),
        }

    def _get_resolved(self, category=None, last_n=None) -> list:
        resolved = [r for r in self.records if r["resolved"] is not None]
        if category:
            resolved = [r for r in resolved if r.get("category") == category]
        if last_n:
            resolved = resolved[-last_n:]
        return resolved
