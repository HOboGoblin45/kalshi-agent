"""Tests for WebSocket real-time arbitrage trigger."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock, patch
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MockBookState:
    """Minimal BookState-like object for testing."""
    ticker: str = ""
    best_yes_bid: Optional[int] = None
    best_no_bid: Optional[int] = None


class TestCheckSingleMarketArb(unittest.TestCase):
    def setUp(self):
        from modules.arbitrage import check_single_market_arb
        self.check = check_single_market_arb

    def test_arb_detected_when_yes_plus_no_below_100(self):
        """YES 40c + NO 40c = 80c + 14c fees = 94c < 100c = 6c profit."""
        book = MockBookState(ticker="TEST-ARB", best_yes_bid=40, best_no_bid=40)
        result = self.check("TEST-ARB", book)
        self.assertIsNotNone(result)
        self.assertEqual(result["ticker"], "TEST-ARB")
        self.assertEqual(result["type"], "ws_arbitrage")
        self.assertGreater(result["profit_cents"], 0)
        self.assertEqual(result["yes_price"], 40)
        self.assertEqual(result["no_price"], 40)

    def test_no_arb_when_prices_sum_to_normal(self):
        """YES 50c + NO 50c = 100c + fees > 100c, no arb."""
        book = MockBookState(ticker="TEST-NORM", best_yes_bid=50, best_no_bid=50)
        result = self.check("TEST-NORM", book)
        self.assertIsNone(result)

    def test_no_arb_when_prices_near_100(self):
        """YES 55c + NO 48c = 103c + fees > 100c, no arb."""
        book = MockBookState(ticker="TEST-HIGH", best_yes_bid=55, best_no_bid=48)
        result = self.check("TEST-HIGH", book)
        self.assertIsNone(result)

    def test_none_book_state(self):
        result = self.check("TEST", None)
        self.assertIsNone(result)

    def test_missing_bid_prices(self):
        book = MockBookState(ticker="TEST", best_yes_bid=40, best_no_bid=None)
        result = self.check("TEST", book)
        self.assertIsNone(result)

    def test_zero_bid_prices(self):
        book = MockBookState(ticker="TEST", best_yes_bid=0, best_no_bid=40)
        result = self.check("TEST", book)
        self.assertIsNone(result)

    def test_min_profit_filter(self):
        """Arb with profit below ws_arb_min_profit_cents should be filtered."""
        # YES 43c + NO 43c = 86c + 14c fees = 100c = 0c profit
        book = MockBookState(ticker="TEST-THIN", best_yes_bid=43, best_no_bid=43)
        result = self.check("TEST-THIN", book)
        self.assertIsNone(result)

    def test_detected_at_timestamp(self):
        book = MockBookState(ticker="TEST-TS", best_yes_bid=30, best_no_bid=30)
        before = time.time()
        result = self.check("TEST-TS", book)
        after = time.time()
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["detected_at"], before)
        self.assertLessEqual(result["detected_at"], after)


class TestWsArbQueue(unittest.TestCase):
    def setUp(self):
        from modules.arbitrage import WS_ARB_QUEUE, push_ws_arb, pop_ws_arbs
        self.queue = WS_ARB_QUEUE
        self.push = push_ws_arb
        self.pop = pop_ws_arbs
        # Clear queue before each test
        self.queue.clear()

    def test_push_and_pop(self):
        opp = {"ticker": "T1", "profit_cents": 5.0, "detected_at": time.time(),
               "yes_price": 30, "no_price": 30, "total_cost": 60, "type": "ws_arbitrage"}
        self.push(opp)
        results = self.pop()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "T1")

    def test_pop_clears_queue(self):
        opp = {"ticker": "T1", "profit_cents": 5.0, "detected_at": time.time(),
               "yes_price": 30, "no_price": 30, "total_cost": 60, "type": "ws_arbitrage"}
        self.push(opp)
        self.pop()
        results = self.pop()
        self.assertEqual(len(results), 0)

    def test_stale_entries_filtered(self):
        """Opportunities older than max_age_seconds are discarded."""
        old_opp = {"ticker": "T-OLD", "profit_cents": 5.0,
                   "detected_at": time.time() - 60,
                   "yes_price": 30, "no_price": 30, "total_cost": 60, "type": "ws_arbitrage"}
        fresh_opp = {"ticker": "T-FRESH", "profit_cents": 5.0,
                     "detected_at": time.time(),
                     "yes_price": 30, "no_price": 30, "total_cost": 60, "type": "ws_arbitrage"}
        self.push(old_opp)
        self.push(fresh_opp)
        results = self.pop(max_age_seconds=30)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "T-FRESH")

    def test_dedup_within_5s(self):
        """Same ticker within 5s should not be queued twice."""
        now = time.time()
        opp1 = {"ticker": "T-DUP", "profit_cents": 5.0, "detected_at": now,
                "yes_price": 30, "no_price": 30, "total_cost": 60, "type": "ws_arbitrage"}
        opp2 = {"ticker": "T-DUP", "profit_cents": 6.0, "detected_at": now + 1,
                "yes_price": 29, "no_price": 29, "total_cost": 58, "type": "ws_arbitrage"}
        self.push(opp1)
        self.push(opp2)
        results = self.pop()
        self.assertEqual(len(results), 1)

    def test_sorted_newest_first(self):
        """Pop results should be sorted newest first."""
        now = time.time()
        opp1 = {"ticker": "T-A", "profit_cents": 5.0, "detected_at": now - 10,
                "yes_price": 30, "no_price": 30, "total_cost": 60, "type": "ws_arbitrage"}
        opp2 = {"ticker": "T-B", "profit_cents": 6.0, "detected_at": now,
                "yes_price": 29, "no_price": 29, "total_cost": 58, "type": "ws_arbitrage"}
        self.push(opp1)
        self.push(opp2)
        results = self.pop()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["ticker"], "T-B")
        self.assertEqual(results[1]["ticker"], "T-A")


class TestWsFeedArbCallback(unittest.TestCase):
    def test_set_arb_callback(self):
        from modules.ws_feed import KalshiWSFeed
        feed = KalshiWSFeed()
        callback = MagicMock()
        feed.set_arb_callback(callback)
        self.assertEqual(feed._arb_callback, callback)

    def test_callback_fired_on_push(self):
        """_push_to_market_state should fire the arb callback."""
        from modules.ws_feed import KalshiWSFeed
        feed = KalshiWSFeed()

        callback = MagicMock()
        feed.set_arb_callback(callback)

        # Set up internal book data
        feed._books["TEST-CB"] = {
            "yes": {"40": 10, "42": 5},
            "no": {"55": 8},
        }

        feed._push_to_market_state("TEST-CB")
        callback.assert_called_once()
        args = callback.call_args
        self.assertEqual(args[0][0], "TEST-CB")  # ticker
        # Second arg should be a BookState

    def test_callback_exception_does_not_crash_feed(self):
        """Callback errors should be silently caught."""
        from modules.ws_feed import KalshiWSFeed
        feed = KalshiWSFeed()

        def bad_callback(ticker, book_state):
            raise RuntimeError("Callback exploded!")

        feed.set_arb_callback(bad_callback)
        feed._books["TEST-ERR"] = {
            "yes": {"50": 10},
            "no": {"50": 10},
        }

        # Should not raise
        feed._push_to_market_state("TEST-ERR")

    def test_no_callback_no_crash(self):
        """Without callback set, _push_to_market_state should work normally."""
        from modules.ws_feed import KalshiWSFeed
        feed = KalshiWSFeed()
        feed._books["TEST-NC"] = {
            "yes": {"50": 10},
            "no": {"50": 10},
        }
        # Should not raise
        feed._push_to_market_state("TEST-NC")


if __name__ == "__main__":
    unittest.main()
