"""Unit tests for the forward-simulation backtester."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from modules.forward_backtest import (
    run_forward_backtest, format_forward_report, ForwardBacktestResult
)


RESOLVED_MARKETS = [
    {"ticker": "KTEMP-NYC", "title": "NYC temperature above 60",
     "result": "yes", "yes_ask": 50, "volume": 100, "category": "weather"},
    {"ticker": "KFED-HOLD", "title": "Fed holds rates",
     "result": "no", "yes_ask": 72, "volume": 200, "category": "fed_rates"},
    {"ticker": "KOIL-80", "title": "Oil price above 80",
     "result": "yes", "yes_ask": 30, "volume": 50, "category": "energy"},
    {"ticker": "KCPI-GT3", "title": "CPI greater than 3%",
     "result": "no", "yes_ask": 60, "volume": 80, "category": "inflation"},
]


def mock_debate_perfect(market):
    """Mock debate that perfectly predicts outcomes."""
    ticker = market["ticker"]
    predictions = {
        "KTEMP-NYC": {"probability": 90, "confidence": 80, "side": "YES",
                      "bull_prob": 92, "bear_prob": 70, "evidence": "NWS says warm"},
        "KFED-HOLD": {"probability": 30, "confidence": 75, "side": "NO",
                      "bull_prob": 40, "bear_prob": 20, "evidence": "Inflation rising"},
        "KOIL-80":   {"probability": 85, "confidence": 70, "side": "YES",
                      "bull_prob": 88, "bear_prob": 60, "evidence": "OPEC cuts"},
        "KCPI-GT3":  {"probability": 25, "confidence": 65, "side": "NO",
                      "bull_prob": 35, "bear_prob": 15, "evidence": "Core CPI falling"},
    }
    return predictions.get(ticker, {"probability": 50, "confidence": 50, "side": "HOLD",
                                     "bull_prob": 55, "bear_prob": 45, "evidence": ""})


def mock_debate_bad(market):
    """Mock debate that always gets it wrong."""
    ticker = market["ticker"]
    predictions = {
        "KTEMP-NYC": {"probability": 10, "confidence": 80, "side": "NO",
                      "bull_prob": 20, "bear_prob": 5, "evidence": "Snow expected"},
        "KFED-HOLD": {"probability": 90, "confidence": 80, "side": "YES",
                      "bull_prob": 95, "bear_prob": 80, "evidence": "Dovish Fed"},
        "KOIL-80":   {"probability": 15, "confidence": 70, "side": "NO",
                      "bull_prob": 25, "bear_prob": 10, "evidence": "Demand low"},
        "KCPI-GT3":  {"probability": 85, "confidence": 65, "side": "YES",
                      "bull_prob": 90, "bear_prob": 75, "evidence": "Inflation surge"},
    }
    return predictions.get(ticker, {"probability": 50, "confidence": 50, "side": "HOLD",
                                     "bull_prob": 55, "bear_prob": 45, "evidence": ""})


class TestForwardBacktest(unittest.TestCase):
    def test_perfect_predictions(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        self.assertEqual(result.total, 4)
        self.assertEqual(result.correct_side, 4)
        self.assertAlmostEqual(result.accuracy, 100.0, places=1)

    def test_brier_score_perfect(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        # Good predictions should have low Brier score
        self.assertLess(result.brier_score, 0.15)

    def test_bad_predictions(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_bad)
        self.assertEqual(result.total, 4)
        self.assertEqual(result.correct_side, 0)
        self.assertAlmostEqual(result.accuracy, 0.0, places=1)

    def test_brier_score_bad(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_bad)
        # Bad predictions should have high Brier score
        self.assertGreater(result.brier_score, 0.5)

    def test_brier_skill_positive_for_good_ai(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        # Good AI should beat market prices
        self.assertGreater(result.brier_skill, 0)

    def test_brier_skill_negative_for_bad_ai(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_bad)
        # Bad AI should be worse than market prices
        self.assertLess(result.brier_skill, 0)

    def test_by_category(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        self.assertIn("weather", result.by_category)
        self.assertEqual(result.by_category["weather"]["count"], 1)
        self.assertEqual(result.by_category["weather"]["correct"], 1)

    def test_calibration_buckets(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        # 90% prediction should be in 90-99% bucket
        self.assertIn("90-99%", result.calibration_buckets)
        self.assertEqual(len(result.calibration_buckets["90-99%"]["predictions"]), 1)

    def test_predictions_stored(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        self.assertEqual(len(result.predictions), 4)
        first = result.predictions[0]
        self.assertIn("ticker", first)
        self.assertIn("ai_prob", first)
        self.assertIn("correct", first)
        self.assertIn("brier", first)

    def test_empty_markets(self):
        result = run_forward_backtest([], mock_debate_perfect)
        self.assertEqual(result.total, 0)
        self.assertEqual(result.brier_score, 1.0)
        self.assertEqual(result.accuracy, 0)

    def test_debate_error_handling(self):
        def failing_debate(market):
            raise RuntimeError("API error")
        result = run_forward_backtest(RESOLVED_MARKETS, failing_debate)
        self.assertEqual(result.total, 0)
        self.assertEqual(len(result.errors), 4)

    def test_skip_unresolved(self):
        markets = [{"ticker": "X", "title": "Test", "result": "pending", "yes_ask": 50}]
        result = run_forward_backtest(markets, mock_debate_perfect)
        self.assertEqual(result.total, 0)

    def test_custom_category_fn(self):
        def cat_fn(m):
            return "custom"
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect, category_fn=cat_fn)
        self.assertIn("custom", result.by_category)
        self.assertEqual(result.by_category["custom"]["count"], 4)


class TestForwardReport(unittest.TestCase):
    def test_produces_output(self):
        result = run_forward_backtest(RESOLVED_MARKETS, mock_debate_perfect)
        report = format_forward_report(result)
        self.assertIn("FORWARD BACKTEST REPORT", report)
        self.assertIn("Brier", report)
        self.assertIn("accuracy", report.lower())

    def test_empty_report(self):
        result = run_forward_backtest([], mock_debate_perfect)
        report = format_forward_report(result)
        self.assertIn("FORWARD BACKTEST REPORT", report)

    def test_report_with_errors(self):
        def failing_debate(market):
            raise RuntimeError("API error")
        result = run_forward_backtest(RESOLVED_MARKETS, failing_debate)
        report = format_forward_report(result)
        self.assertIn("ERRORS", report)


if __name__ == "__main__":
    unittest.main()
