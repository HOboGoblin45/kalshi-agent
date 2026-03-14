"""Unit tests for the backtesting engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from modules.backtester import run_backtest, analyze_calibration, _infer_category, format_report


SAMPLE_TRADES = [
    {"time": "2026-03-01T10:00:00", "ticker": "KTEMP-NYC", "title": "NYC temperature",
     "side": "yes", "contracts": 2, "price_cents": 50, "cost": 1.00,
     "confidence": 72, "edge": 15, "probability": 75, "evidence": "NWS says 63F",
     "bull_prob": 80, "bear_prob": 60, "status": "win", "pnl": 0.86,
     "platform": "kalshi"},
    {"time": "2026-03-01T14:00:00", "ticker": "KFED-HOLD", "title": "Fed holds rates",
     "side": "yes", "contracts": 3, "price_cents": 72, "cost": 2.16,
     "confidence": 65, "edge": 8, "probability": 80, "evidence": "FedWatch 92%",
     "bull_prob": 85, "bear_prob": 70, "status": "loss", "pnl": -2.16,
     "platform": "kalshi"},
    {"time": "2026-03-02T09:00:00", "ticker": "POLY-OIL", "title": "Oil price above 80",
     "side": "no", "contracts": 1, "price_cents": 30, "cost": 0.30,
     "confidence": 55, "edge": 5, "probability": 25, "evidence": "OPEC steady",
     "bull_prob": 30, "bear_prob": 20, "status": "win", "pnl": 0.63,
     "platform": "polymarket"},
    {"time": "2026-03-03T12:00:00", "ticker": "KTEMP-CHI", "title": "Chicago temperature",
     "side": "yes", "contracts": 1, "price_cents": 40, "cost": 0.40,
     "confidence": 80, "edge": 20, "probability": 60, "evidence": "NWS forecast",
     "bull_prob": 70, "bear_prob": 45, "status": "open",
     "platform": "kalshi"},
]


class TestRunBacktest(unittest.TestCase):
    def test_basic_metrics(self):
        result = run_backtest(SAMPLE_TRADES)
        self.assertEqual(len(result.trades), 4)
        self.assertEqual(result.wins, 2)
        self.assertEqual(result.losses, 1)
        self.assertEqual(result.open_trades, 1)
        self.assertEqual(result.total_resolved, 3)

    def test_win_rate(self):
        result = run_backtest(SAMPLE_TRADES)
        self.assertAlmostEqual(result.win_rate, 66.7, delta=0.1)

    def test_pnl_calculation(self):
        result = run_backtest(SAMPLE_TRADES)
        expected_pnl = 0.86 + (-2.16) + 0.63  # = -0.67
        self.assertAlmostEqual(result.total_pnl, expected_pnl, places=2)

    def test_by_category(self):
        result = run_backtest(SAMPLE_TRADES)
        self.assertIn("weather", result.by_category)
        self.assertEqual(result.by_category["weather"]["wins"], 1)

    def test_by_platform(self):
        result = run_backtest(SAMPLE_TRADES)
        self.assertIn("kalshi", result.by_platform)
        self.assertIn("polymarket", result.by_platform)
        self.assertEqual(result.by_platform["polymarket"]["wins"], 1)

    def test_equity_curve(self):
        result = run_backtest(SAMPLE_TRADES, initial_bankroll=100.0)
        self.assertEqual(len(result.equity_curve), 4)
        # After win of 0.86: 100.86
        self.assertAlmostEqual(result.equity_curve[0], 100.86, places=2)

    def test_max_drawdown(self):
        result = run_backtest(SAMPLE_TRADES, initial_bankroll=100.0)
        self.assertGreater(result.max_drawdown, 0)

    def test_empty_trades(self):
        result = run_backtest([])
        self.assertEqual(result.wins, 0)
        self.assertEqual(result.losses, 0)
        self.assertEqual(result.win_rate, 0)

    def test_streaks(self):
        # Two wins then one loss
        result = run_backtest(SAMPLE_TRADES)
        self.assertGreaterEqual(result.max_winning_streak, 1)


class TestCategoryInference(unittest.TestCase):
    def test_weather(self):
        self.assertEqual(_infer_category({"title": "NYC temperature above 60"}), "weather")

    def test_fed(self):
        self.assertEqual(_infer_category({"title": "Fed holds interest rate"}), "fed_rates")

    def test_energy(self):
        self.assertEqual(_infer_category({"title": "Oil price above 80"}), "energy")

    def test_unknown(self):
        self.assertEqual(_infer_category({"title": "Random event", "ticker": "X"}), "other")


class TestCalibration(unittest.TestCase):
    def test_perfect_calibration(self):
        records = [
            {"our_probability": 80, "resolved": True},
            {"our_probability": 82, "resolved": True},
            {"our_probability": 78, "resolved": True},
            {"our_probability": 85, "resolved": False},
        ]
        cal = analyze_calibration(records)
        # 80, 82, 85 in 80-89% bucket; 78 in 70-79%
        self.assertIn("80-89%", cal)
        self.assertEqual(cal["80-89%"]["count"], 3)
        self.assertIn("70-79%", cal)
        self.assertEqual(cal["70-79%"]["count"], 1)

    def test_unresolved_ignored(self):
        records = [
            {"our_probability": 70, "resolved": None},
            {"our_probability": 70, "resolved": True},
        ]
        cal = analyze_calibration(records)
        self.assertEqual(cal["70-79%"]["count"], 1)

    def test_empty_records(self):
        cal = analyze_calibration([])
        self.assertEqual(len(cal), 0)


class TestFormatReport(unittest.TestCase):
    def test_produces_output(self):
        result = run_backtest(SAMPLE_TRADES)
        report = format_report(result)
        self.assertIn("BACKTEST REPORT", report)
        self.assertIn("Win rate", report)
        self.assertIn("BY CATEGORY", report)


if __name__ == "__main__":
    unittest.main()
