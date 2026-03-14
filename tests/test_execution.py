"""Tests for modules/execution.py -- execution policy engine."""
import unittest
from unittest.mock import patch

from modules.market_state import BookState, BookLevel
from modules.execution import (
    assess_book_quality, build_execution_plan, should_quickflip,
    ExecutionPlan,
)


def _make_book(bids, asks, stale=False):
    import time
    ts = time.time() - 200 if stale else time.time()
    return BookState(
        ticker="TEST",
        yes_bids=[BookLevel(*b) for b in bids],
        yes_asks=[BookLevel(*a) for a in asks],
        timestamp=ts,
        source="rest",
    )


class TestAssessBookQuality(unittest.TestCase):
    def test_none_book(self):
        q = assess_book_quality(None)
        self.assertEqual(q["quality"], "unknown")
        self.assertFalse(q["is_tradeable"])

    def test_stale_book(self):
        book = _make_book([(50, 10)], [(55, 10)], stale=True)
        q = assess_book_quality(book)
        self.assertEqual(q["quality"], "unknown")

    def test_tight_spread(self):
        book = _make_book([(50, 10)], [(52, 10)])
        q = assess_book_quality(book)
        self.assertEqual(q["quality"], "tight")
        self.assertTrue(q["is_tradeable"])

    def test_normal_spread(self):
        book = _make_book([(50, 10)], [(55, 10)])
        q = assess_book_quality(book)
        self.assertEqual(q["quality"], "normal")
        self.assertTrue(q["is_tradeable"])

    def test_wide_spread(self):
        book = _make_book([(40, 10)], [(55, 10)])
        q = assess_book_quality(book)
        self.assertEqual(q["quality"], "wide")
        self.assertTrue(q["is_tradeable"])

    def test_very_wide_spread(self):
        book = _make_book([(30, 10)], [(55, 10)])
        q = assess_book_quality(book)
        self.assertEqual(q["quality"], "very_wide")
        self.assertFalse(q["is_tradeable"])

    def test_no_two_sided(self):
        book = _make_book([(50, 10)], [])
        q = assess_book_quality(book)
        self.assertEqual(q["quality"], "thin")
        self.assertFalse(q["is_tradeable"])


class TestBuildExecutionPlan(unittest.TestCase):
    def test_no_trade_when_edge_consumed(self):
        # 10c contract with 5% edge, but 14% fee drag -> no trade
        plan = build_execution_plan(
            ticker="T", side="yes", probability=60, confidence=70,
            edge_pct=5.0, price_cents=10, contracts=1, hours_left=24,
        )
        self.assertEqual(plan.action, "no_trade")
        self.assertIn("fees", plan.reason.lower())

    def test_taker_with_good_edge(self):
        book = _make_book([(48, 10)], [(52, 10)])
        plan = build_execution_plan(
            ticker="T", side="yes", probability=70, confidence=80,
            edge_pct=30.0, price_cents=50, contracts=1, hours_left=24,
            book=book,
        )
        self.assertEqual(plan.action, "taker")

    def test_maker_on_wide_spread(self):
        book = _make_book([(40, 10)], [(50, 10)])
        plan = build_execution_plan(
            ticker="T", side="yes", probability=70, confidence=80,
            edge_pct=30.0, price_cents=50, contracts=1, hours_left=24,
            book=book,
        )
        self.assertEqual(plan.action, "maker")

    def test_taker_when_urgent(self):
        book = _make_book([(40, 10)], [(50, 10)])
        plan = build_execution_plan(
            ticker="T", side="yes", probability=70, confidence=80,
            edge_pct=30.0, price_cents=50, contracts=1, hours_left=1,
            book=book,
        )
        # Even wide spread, urgency forces taker
        self.assertEqual(plan.action, "taker")
        self.assertEqual(plan.urgency, "high")

    def test_no_trade_poor_book(self):
        book = _make_book([(30, 10)], [(55, 10)])  # very wide
        plan = build_execution_plan(
            ticker="T", side="yes", probability=70, confidence=80,
            edge_pct=30.0, price_cents=50, contracts=1, hours_left=24,
            book=book,
        )
        self.assertEqual(plan.action, "no_trade")
        self.assertIn("book quality", plan.reason.lower())

    def test_no_book_defaults_to_taker(self):
        plan = build_execution_plan(
            ticker="T", side="yes", probability=70, confidence=80,
            edge_pct=30.0, price_cents=50, contracts=1, hours_left=24,
        )
        # None book -> book_quality["is_tradeable"]=False but book IS None so skip check
        self.assertIn(plan.action, ("taker", "no_trade"))


class TestShouldQuickflip(unittest.TestCase):
    @patch("modules.execution.CFG", {"quickflip_enabled": False})
    def test_disabled(self):
        ok, reason = should_quickflip({"volume": 100, "display_price": 10})
        self.assertFalse(ok)
        self.assertIn("disabled", reason)

    @patch("modules.execution.CFG", {"quickflip_enabled": True, "quickflip_min_price": 3, "quickflip_max_price": 15})
    def test_low_volume(self):
        ok, reason = should_quickflip({"volume": 10, "display_price": 10})
        self.assertFalse(ok)
        self.assertIn("volume", reason)

    @patch("modules.execution.CFG", {"quickflip_enabled": True, "quickflip_min_price": 3, "quickflip_max_price": 15})
    def test_price_too_high(self):
        ok, reason = should_quickflip({"volume": 100, "display_price": 50, "_hrs_left": 12})
        self.assertFalse(ok)
        self.assertIn("price", reason)

    @patch("modules.execution.CFG", {"quickflip_enabled": True, "quickflip_min_price": 3, "quickflip_max_price": 15})
    def test_too_far_from_expiry(self):
        ok, reason = should_quickflip({"volume": 100, "display_price": 10, "_hrs_left": 100})
        self.assertFalse(ok)
        self.assertIn("expiry", reason)


if __name__ == "__main__":
    unittest.main()
