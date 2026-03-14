"""Tests for crypto bracket market discovery and market maker engine."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock, patch
from modules.crypto_markets import BracketEvent, CryptoMarketDiscovery, BTCPriceFeed
from modules.market_maker import MarketMaker, Quote


# ── Sample bracket data ──

SAMPLE_BRACKETS = [
    {"ticker": "KXBTC-B70000", "subtitle": "$70,000 to 70,249.99",
     "yes_bid": 2, "yes_ask": 4, "volume": 100},
    {"ticker": "KXBTC-B70250", "subtitle": "$70,250 to 70,499.99",
     "yes_bid": 5, "yes_ask": 8, "volume": 200},
    {"ticker": "KXBTC-B70500", "subtitle": "$70,500 to 70,749.99",
     "yes_bid": 10, "yes_ask": 14, "volume": 500},
    {"ticker": "KXBTC-B70750", "subtitle": "$70,750 to 70,999.99",
     "yes_bid": 20, "yes_ask": 25, "volume": 4258},
    {"ticker": "KXBTC-B71000", "subtitle": "$71,000 to 71,249.99",
     "yes_bid": 41, "yes_ask": 47, "volume": 1805},
    {"ticker": "KXBTC-B71250", "subtitle": "$71,250 to 71,499.99",
     "yes_bid": 10, "yes_ask": 14, "volume": 500},
    {"ticker": "KXBTC-B71500", "subtitle": "$71,500 to 71,749.99",
     "yes_bid": 5, "yes_ask": 8, "volume": 200},
    {"ticker": "KXBTC-B71750", "subtitle": "$71,750 or above",
     "yes_bid": 1, "yes_ask": 3, "volume": 50},
    {"ticker": "KXBTC-B69750", "subtitle": "$69,750 or below",
     "yes_bid": 0, "yes_ask": 2, "volume": 30},
]


class TestBracketEvent(unittest.TestCase):
    def setUp(self):
        self.event = BracketEvent("KXBTC-26MAR1420", "BTC Price Range")
        self.event.update_brackets(SAMPLE_BRACKETS)

    def test_update_brackets_parses_correctly(self):
        self.assertEqual(len(self.event.brackets), 9)
        # First sorted bracket should be the "or below" one
        b = self.event.brackets[0]
        self.assertEqual(b["ticker"], "KXBTC-B69750")

    def test_sum_yes_asks(self):
        total = self.event.sum_yes_asks()
        # 4 + 8 + 14 + 25 + 47 + 14 + 8 + 3 + 2 = 125
        self.assertEqual(total, 125)

    def test_sum_yes_bids(self):
        total = self.event.sum_yes_bids()
        # 2 + 5 + 10 + 20 + 41 + 10 + 5 + 1 + 0 = 94
        self.assertEqual(total, 94)

    def test_find_sum_arb_detects_long_arb(self):
        """When sum of asks < 100, buying all brackets guarantees profit."""
        # Set all asks to very low values
        for b in self.event.brackets:
            b["yes_ask"] = 3
        # sum_asks = 27, well below 100
        result = self.event.find_sum_arb(maker_fee_coeff=0.0)
        self.assertIsNotNone(result)
        self.assertIn("long_arb", result)
        self.assertGreater(result["long_arb"]["profit_cents"], 0)

    def test_find_sum_arb_detects_short_arb(self):
        """When sum of bids > 100, selling all brackets guarantees profit."""
        for b in self.event.brackets:
            b["yes_bid"] = 15
        # sum_bids = 135, well above 100
        result = self.event.find_sum_arb(maker_fee_coeff=0.0)
        self.assertIsNotNone(result)
        self.assertIn("short_arb", result)
        self.assertGreater(result["short_arb"]["profit_cents"], 0)

    def test_find_sum_arb_returns_none_when_no_arb(self):
        """Normal pricing: no arb available."""
        result = self.event.find_sum_arb()
        # With sum_asks=125 and sum_bids=94, no arb after fees
        self.assertIsNone(result)

    def test_parse_range_normal(self):
        low, high = self.event._parse_range("$71,000 to 71,249.99")
        self.assertAlmostEqual(low, 71000.0)
        self.assertAlmostEqual(high, 71249.99)

    def test_parse_range_or_above(self):
        low, high = self.event._parse_range("$71,750 or above")
        self.assertAlmostEqual(low, 71750.0)
        self.assertIsNone(high)

    def test_parse_range_or_below(self):
        low, high = self.event._parse_range("$69,750 or below")
        self.assertIsNone(low)
        self.assertAlmostEqual(high, 69750.0)

    def test_parse_range_empty(self):
        low, high = self.event._parse_range("")
        self.assertIsNone(low)
        self.assertIsNone(high)

    def test_active_brackets(self):
        active = self.event.active_brackets(min_volume=100)
        # Should exclude the "or above" (vol=50) and "or below" (vol=30)
        self.assertTrue(all(b["volume"] >= 100 for b in active))
        # Sorted by yes_ask descending
        asks = [b["yes_ask"] for b in active]
        self.assertEqual(asks, sorted(asks, reverse=True))

    def test_to_cents_dollar_values(self):
        """Values < 1.0 are treated as dollar amounts and converted to cents."""
        self.assertEqual(BracketEvent._to_cents(0.47), 47)
        self.assertEqual(BracketEvent._to_cents(0.03), 3)
        self.assertEqual(BracketEvent._to_cents(0.99), 99)

    def test_to_cents_cent_values(self):
        """Values > 1.0 are kept as cents."""
        self.assertEqual(BracketEvent._to_cents(47), 47)
        self.assertEqual(BracketEvent._to_cents(3), 3)


class TestBTCPriceFeed(unittest.TestCase):
    def setUp(self):
        self.feed = BTCPriceFeed()

    def test_bracket_fair_value_at_current_price(self):
        """Bracket containing current price should have high fair value."""
        bracket = {"range_low": 70750.0, "range_high": 71000.0}
        cents = self.feed.bracket_fair_value(bracket, current_price=70900.0)
        # Current price is inside this bracket, should be relatively high
        self.assertGreaterEqual(cents, 20)
        self.assertLessEqual(cents, 99)

    def test_bracket_fair_value_far_away(self):
        """Bracket far from current price should have low fair value."""
        bracket = {"range_low": 65000.0, "range_high": 65250.0}
        cents = self.feed.bracket_fair_value(bracket, current_price=71000.0)
        # 6000 away from current price, should be very low
        self.assertLessEqual(cents, 5)

    def test_bracket_fair_value_no_price(self):
        """Without price data, return 50 (no information)."""
        bracket = {"range_low": 71000.0, "range_high": 71250.0}
        cents = self.feed.bracket_fair_value(bracket, current_price=None)
        self.assertEqual(cents, 50)

    def test_bracket_fair_value_or_above(self):
        bracket = {"range_low": 75000.0, "range_high": None}
        cents = self.feed.bracket_fair_value(bracket, current_price=71000.0)
        self.assertLessEqual(cents, 30)  # well above current price

    def test_bracket_fair_value_or_below(self):
        bracket = {"range_low": None, "range_high": 65000.0}
        cents = self.feed.bracket_fair_value(bracket, current_price=71000.0)
        self.assertLessEqual(cents, 30)  # well below current price


class TestMarketMaker(unittest.TestCase):
    def setUp(self):
        self.mock_api = MagicMock()
        self.mm = MarketMaker(self.mock_api)

    def test_quote_market_dry_run(self):
        """In dry run, quote_market should log but not call API."""
        self.mm.start()
        self.mm.quote_market("KXBTC-TEST", fair_value_cents=50)
        # In dry run (default), no real API calls
        self.mock_api.place_order.assert_not_called()
        # But quotes should be tracked
        summary = self.mm.summary()
        self.assertEqual(summary["markets_quoted"], 1)
        self.assertEqual(summary["active_quotes"], 2)  # YES bid + NO bid

    def test_record_fill_updates_inventory(self):
        """Fills should update inventory correctly."""
        self.mm.record_fill("KXBTC-TEST", "yes", 47, 5)
        inv = self.mm.get_inventory()
        self.assertEqual(inv["KXBTC-TEST"], 5)

        self.mm.record_fill("KXBTC-TEST", "no", 48, 3)
        inv = self.mm.get_inventory()
        self.assertEqual(inv["KXBTC-TEST"], 2)  # 5 - 3

    def test_cancel_all_kill_switch(self):
        """Kill switch should cancel all resting orders."""
        self.mm.start()
        self.mm.quote_market("KXBTC-A", fair_value_cents=50)
        self.mm.quote_market("KXBTC-B", fair_value_cents=30)
        summary = self.mm.summary()
        self.assertEqual(summary["active_quotes"], 4)  # 2 markets × 2 sides

        cancelled = self.mm.cancel_all()
        self.assertEqual(cancelled, 4)
        summary = self.mm.summary()
        self.assertEqual(summary["active_quotes"], 0)
        self.assertEqual(summary["markets_quoted"], 0)

    def test_inventory_skew(self):
        """When inventory is positive, YES bid should decrease."""
        self.mm.start()
        # Record positive inventory
        self.mm._inventory["KXBTC-SKEW"] = 3

        self.mm.quote_market("KXBTC-SKEW", fair_value_cents=50, spread_cents=6)
        quotes = self.mm._quotes.get("KXBTC-SKEW", {})
        yes_q = quotes.get("yes")
        self.assertIsNotNone(yes_q)
        # Without skew: yes_bid = 50 - 3 = 47
        # With skew (3 contracts × 1c): yes_bid = 47 - 3 = 44
        # max_skew = spread // 2 = 3, so skew is min(3, 3) = 3
        self.assertEqual(yes_q.price_cents, 44)

    def test_not_active_no_quotes(self):
        """When not active, quote_market should do nothing."""
        self.mm.quote_market("KXBTC-TEST", fair_value_cents=50)
        summary = self.mm.summary()
        self.assertEqual(summary["markets_quoted"], 0)

    def test_summary(self):
        """Summary should return correct structure."""
        summary = self.mm.summary()
        self.assertIn("active", summary)
        self.assertIn("markets_quoted", summary)
        self.assertIn("active_quotes", summary)
        self.assertIn("total_fills", summary)
        self.assertIn("net_inventory", summary)

    def test_cancel_market(self):
        """Cancel specific market quotes."""
        self.mm.start()
        self.mm.quote_market("KXBTC-A", fair_value_cents=50)
        self.mm.quote_market("KXBTC-B", fair_value_cents=30)
        self.mm.cancel_market("KXBTC-A")
        summary = self.mm.summary()
        self.assertEqual(summary["markets_quoted"], 1)


class TestCryptoMarketDiscovery(unittest.TestCase):
    def test_get_mm_candidates_filters(self):
        mock_api = MagicMock()
        discovery = CryptoMarketDiscovery(mock_api)

        # Manually populate an event
        event = BracketEvent("TEST-EVENT")
        event.update_brackets(SAMPLE_BRACKETS)
        discovery.events["TEST-EVENT"] = event

        # min_spread=3, min_volume=10
        candidates = discovery.get_mm_candidates(min_spread=3, min_volume=100)
        self.assertTrue(len(candidates) > 0)
        for event, bracket in candidates:
            self.assertGreaterEqual(bracket["spread"], 3)
            self.assertGreaterEqual(bracket["volume"], 100)

    def test_get_mm_candidates_sorted_by_spread(self):
        mock_api = MagicMock()
        discovery = CryptoMarketDiscovery(mock_api)

        event = BracketEvent("TEST-EVENT")
        event.update_brackets(SAMPLE_BRACKETS)
        discovery.events["TEST-EVENT"] = event

        candidates = discovery.get_mm_candidates(min_spread=1, min_volume=0)
        spreads = [b["spread"] for _, b in candidates]
        self.assertEqual(spreads, sorted(spreads, reverse=True))


if __name__ == "__main__":
    unittest.main()
