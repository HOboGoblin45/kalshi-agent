"""Tests for modules/market_state.py -- BookState and MarketStateStore."""
import time
import unittest

from modules.market_state import (
    BookLevel, BookState, MarketStateStore, _parse_book_side,
)


class TestBookLevel(unittest.TestCase):
    def test_basic(self):
        bl = BookLevel(price_cents=50, size=10)
        self.assertEqual(bl.price_cents, 50)
        self.assertEqual(bl.size, 10)


class TestBookStateProperties(unittest.TestCase):
    def _make_book(self, bids, asks, ts=None, source="rest"):
        return BookState(
            ticker="TEST-MKT",
            yes_bids=[BookLevel(*b) for b in bids],
            yes_asks=[BookLevel(*a) for a in asks],
            timestamp=ts or time.time(),
            source=source,
        )

    def test_best_yes_bid(self):
        book = self._make_book([(50, 10), (48, 5)], [(55, 10)])
        self.assertEqual(book.best_yes_bid, 50)

    def test_best_yes_ask(self):
        book = self._make_book([(50, 10)], [(55, 10), (57, 5)])
        self.assertEqual(book.best_yes_ask, 55)

    def test_spread_cents(self):
        book = self._make_book([(50, 10)], [(55, 10)])
        self.assertEqual(book.spread_cents, 5)

    def test_spread_none_when_missing(self):
        book = self._make_book([(50, 10)], [])
        self.assertIsNone(book.spread_cents)

    def test_mid_price(self):
        book = self._make_book([(50, 10)], [(60, 10)])
        self.assertEqual(book.mid_price, 55.0)

    def test_microprice_balanced(self):
        book = self._make_book([(50, 10)], [(60, 10)])
        # Equal sizes: microprice = mid = 55
        self.assertAlmostEqual(book.microprice, 55.0)

    def test_microprice_imbalanced(self):
        book = self._make_book([(50, 100)], [(60, 10)])
        # Big bid: microprice pulled toward ask
        self.assertGreater(book.microprice, 55.0)

    def test_imbalance_balanced(self):
        book = self._make_book([(50, 10)], [(60, 10)])
        self.assertAlmostEqual(book.imbalance, 0.0)

    def test_imbalance_bid_heavy(self):
        book = self._make_book([(50, 90)], [(60, 10)])
        self.assertGreater(book.imbalance, 0)

    def test_imbalance_ask_heavy(self):
        book = self._make_book([(50, 10)], [(60, 90)])
        self.assertLess(book.imbalance, 0)


class TestStaleness(unittest.TestCase):
    def test_fresh_rest(self):
        book = BookState(ticker="T", timestamp=time.time(), source="rest")
        self.assertFalse(book.is_stale)

    def test_stale_rest(self):
        book = BookState(ticker="T", timestamp=time.time() - 120, source="rest")
        self.assertTrue(book.is_stale)

    def test_stale_ws_shorter_window(self):
        book = BookState(ticker="T", timestamp=time.time() - 45, source="ws")
        self.assertTrue(book.is_stale)

    def test_fresh_ws(self):
        book = BookState(ticker="T", timestamp=time.time() - 10, source="ws")
        self.assertFalse(book.is_stale)

    def test_zero_timestamp_is_stale(self):
        book = BookState(ticker="T", timestamp=0, source="rest")
        self.assertTrue(book.is_stale)


class TestParseBookSide(unittest.TestCase):
    def test_dict_entries(self):
        raw = [{"price": 0.50, "quantity": 10}, {"price": 0.60, "size": 5}]
        levels = _parse_book_side(raw)
        self.assertEqual(len(levels), 2)
        self.assertEqual(levels[0].price_cents, 50)
        self.assertEqual(levels[1].price_cents, 60)

    def test_list_entries(self):
        raw = [[50, 10], [60, 5]]
        levels = _parse_book_side(raw)
        self.assertEqual(len(levels), 2)
        self.assertEqual(levels[0].price_cents, 50)

    def test_dollar_format_normalizes(self):
        raw = [{"price": 0.45, "size": 3}]
        levels = _parse_book_side(raw)
        self.assertEqual(levels[0].price_cents, 45)

    def test_filters_invalid_prices(self):
        raw = [{"price": 0, "size": 5}, {"price": 200, "size": 5}]
        levels = _parse_book_side(raw)
        self.assertEqual(len(levels), 0)

    def test_none_input(self):
        self.assertEqual(_parse_book_side(None), [])


class TestMarketStateStore(unittest.TestCase):
    def setUp(self):
        self.store = MarketStateStore()

    def test_update_and_get(self):
        raw = {"yes": [{"price": 50, "size": 10}], "no": [{"price": 40, "size": 5}]}
        book = self.store.update_book("MKT-1", raw)
        self.assertIsNotNone(book)
        self.assertEqual(book.ticker, "MKT-1")
        retrieved = self.store.get_book("MKT-1")
        self.assertEqual(retrieved.ticker, "MKT-1")

    def test_get_missing(self):
        self.assertIsNone(self.store.get_book("NONEXISTENT"))

    def test_get_book_if_fresh(self):
        raw = {"yes": [{"price": 50, "size": 10}], "no": []}
        self.store.update_book("FRESH", raw)
        self.assertIsNotNone(self.store.get_book_if_fresh("FRESH"))

    def test_get_book_if_fresh_stale(self):
        raw = {"yes": [{"price": 50, "size": 10}], "no": []}
        book = self.store.update_book("STALE", raw)
        book.timestamp = time.time() - 120  # force stale
        self.assertIsNone(self.store.get_book_if_fresh("STALE"))

    def test_feed_health_tracking(self):
        self.store.record_feed_success("kalshi")
        status = self.store.feed_status()
        self.assertEqual(status["kalshi"]["status"], "healthy")
        self.assertEqual(status["kalshi"]["errors"], 0)

    def test_feed_error_tracking(self):
        self.store.record_feed_error("kalshi")
        self.store.record_feed_error("kalshi")
        status = self.store.feed_status()
        self.assertEqual(status["kalshi"]["status"], "degraded")
        self.assertEqual(status["kalshi"]["errors"], 2)

    def test_feed_recovery(self):
        self.store.record_feed_error("kalshi")
        self.store.record_feed_success("kalshi")
        status = self.store.feed_status()
        self.assertEqual(status["kalshi"]["status"], "healthy")
        self.assertEqual(status["kalshi"]["errors"], 0)

    def test_stale_tickers(self):
        raw = {"yes": [{"price": 50, "size": 10}], "no": []}
        book = self.store.update_book("OLD", raw)
        book.timestamp = time.time() - 120
        self.store.update_book("NEW", raw)
        stale = self.store.stale_tickers()
        self.assertIn("OLD", stale)
        self.assertNotIn("NEW", stale)

    def test_clear(self):
        raw = {"yes": [{"price": 50, "size": 10}], "no": []}
        self.store.update_book("X", raw)
        self.store.clear()
        self.assertIsNone(self.store.get_book("X"))

    def test_yes_asks_derived_from_no_bids(self):
        # No bid at 40c implies YES ask at 60c
        raw = {"yes": [{"price": 50, "size": 10}], "no": [{"price": 40, "size": 5}]}
        book = self.store.update_book("DERIVE", raw)
        self.assertTrue(any(a.price_cents == 60 for a in book.yes_asks))


if __name__ == "__main__":
    unittest.main()
