"""Tests for modules/calibration.py -- prediction accuracy tracking."""
import os
import json
import math
import tempfile
import unittest

from modules.calibration import CalibrationTracker


class TestCalibrationTracker(unittest.TestCase):
    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        self.tmpfile.write('[]')
        self.tmpfile.close()
        self.tracker = CalibrationTracker(log_path=self.tmpfile.name)

    def tearDown(self):
        os.unlink(self.tmpfile.name)

    def _record_and_resolve(self, ticker, prob, resolved_yes, side="YES", category="test"):
        self.tracker.record_prediction(
            ticker=ticker, side=side, probability=prob, confidence=70,
            market_price=50, edge=5.0, category=category,
        )
        self.tracker.record_outcome(ticker, resolved_yes)

    def test_record_prediction(self):
        self.tracker.record_prediction(
            ticker="T1", side="YES", probability=70, confidence=80,
            market_price=50, edge=10.0, category="weather",
        )
        self.assertEqual(len(self.tracker.records), 1)
        self.assertIsNone(self.tracker.records[0]["resolved"])

    def test_record_outcome(self):
        self.tracker.record_prediction(
            ticker="T1", side="YES", probability=70, confidence=80,
            market_price=50, edge=10.0,
        )
        self.tracker.record_outcome("T1", resolved_yes=True)
        self.assertTrue(self.tracker.records[0]["resolved"])

    def test_record_outcome_no_side(self):
        """If side=YES and resolved_yes=False, resolved should be False."""
        self.tracker.record_prediction(
            ticker="T2", side="YES", probability=70, confidence=80,
            market_price=50, edge=10.0,
        )
        self.tracker.record_outcome("T2", resolved_yes=False)
        self.assertFalse(self.tracker.records[0]["resolved"])

    def test_brier_perfect(self):
        """Perfect predictions should have Brier score near 0."""
        for i in range(10):
            self._record_and_resolve(f"WIN-{i}", 99, True)
        brier = self.tracker.brier_score(category="test")
        self.assertLess(brier, 0.01)

    def test_brier_worst(self):
        """Totally wrong predictions should have Brier score near 1."""
        for i in range(10):
            self._record_and_resolve(f"LOSE-{i}", 99, False)
        brier = self.tracker.brier_score(category="test")
        self.assertGreater(brier, 0.9)

    def test_brier_random_baseline(self):
        """50/50 predictions resolved 50/50 should be ~0.25."""
        for i in range(20):
            self._record_and_resolve(f"R-{i}", 50, i % 2 == 0)
        brier = self.tracker.brier_score(category="test")
        self.assertAlmostEqual(brier, 0.25, places=2)

    def test_brier_no_data(self):
        self.assertEqual(self.tracker.brier_score(), 0.25)

    def test_log_loss_no_data(self):
        self.assertEqual(self.tracker.log_loss(), 1.0)

    def test_log_loss_good_predictions(self):
        for i in range(10):
            self._record_and_resolve(f"G-{i}", 90, True)
        ll = self.tracker.log_loss(category="test")
        self.assertLess(ll, 0.2)

    def test_category_filter(self):
        self._record_and_resolve("W1", 80, True, category="weather")
        self._record_and_resolve("S1", 80, False, category="sports")
        brier_w = self.tracker.brier_score(category="weather")
        brier_s = self.tracker.brier_score(category="sports")
        self.assertLess(brier_w, brier_s)

    def test_last_n(self):
        for i in range(20):
            self._record_and_resolve(f"OLD-{i}", 50, True)
        for i in range(5):
            self._record_and_resolve(f"NEW-{i}", 95, True)
        brier_all = self.tracker.brier_score(category="test")
        brier_recent = self.tracker.brier_score(category="test", last_n=5)
        self.assertLess(brier_recent, brier_all)

    def test_reliability_bins(self):
        for i in range(20):
            self._record_and_resolve(f"BIN-{i}", 80, True)
        bins = self.tracker.reliability_bins(category="test")
        self.assertTrue(len(bins) > 0)
        # The 80% bin should show ~100% observed frequency (all resolved True)
        for b in bins:
            if b["predicted_avg"] > 70:
                self.assertGreater(b["observed_freq"], 80)

    def test_category_stats(self):
        self._record_and_resolve("W1", 70, True, category="weather")
        self._record_and_resolve("W2", 70, True, category="weather")
        self._record_and_resolve("S1", 70, False, category="sports")
        stats = self.tracker.category_stats()
        self.assertIn("weather", stats)
        self.assertEqual(stats["weather"]["wins"], 2)
        self.assertEqual(stats["sports"]["wins"], 0)

    def test_should_trade_category_insufficient_data(self):
        ok, reason = self.tracker.should_trade_category("crypto")
        self.assertTrue(ok)  # allow with insufficient data
        self.assertIn("Insufficient", reason)

    def test_should_trade_category_poor(self):
        for i in range(15):
            self._record_and_resolve(f"BAD-{i}", 90, False, category="bad_cat")
        ok, reason = self.tracker.should_trade_category("bad_cat")
        self.assertFalse(ok)
        self.assertIn("Poor", reason)

    def test_summary(self):
        self._record_and_resolve("X", 70, True)
        self.tracker.record_prediction(
            ticker="PENDING", side="YES", probability=60, confidence=50,
            market_price=50, edge=5.0,
        )
        s = self.tracker.summary()
        self.assertEqual(s["total_predictions"], 2)
        self.assertEqual(s["resolved"], 1)
        self.assertEqual(s["pending"], 1)

    def test_persistence(self):
        self.tracker.record_prediction(
            ticker="PERSIST", side="YES", probability=70, confidence=80,
            market_price=50, edge=10.0,
        )
        # Load from same file
        tracker2 = CalibrationTracker(log_path=self.tmpfile.name)
        self.assertEqual(len(tracker2.records), 1)
        self.assertEqual(tracker2.records[0]["ticker"], "PERSIST")

    def test_max_records_cap(self):
        """Records should be capped at 5000."""
        self.tracker.records = [{"ticker": f"T{i}", "resolved": None, "our_probability": 50, "category": "test"} for i in range(5500)]
        self.tracker._save()
        tracker2 = CalibrationTracker(log_path=self.tmpfile.name)
        self.assertLessEqual(len(tracker2.records), 5000)


if __name__ == "__main__":
    unittest.main()
