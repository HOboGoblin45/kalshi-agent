"""Tests for combinatorial arbitrage scanner."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from modules.combinatorial import (
    CombinatorialScanner, _extract_threshold, _extract_event_key
)


class TestExtractThreshold(unittest.TestCase):
    def test_above_pattern(self):
        result = _extract_threshold("BTC above $70,000")
        self.assertEqual(result, ('above', 70000.0))

    def test_over_pattern(self):
        result = _extract_threshold("Temperature over 85 degrees")
        self.assertEqual(result, ('above', 85.0))

    def test_below_pattern(self):
        result = _extract_threshold("BTC below $65,000")
        self.assertEqual(result, ('below', 65000.0))

    def test_under_pattern(self):
        result = _extract_threshold("Unemployment under 4.5")
        self.assertEqual(result, ('below', 4.5))

    def test_range_pattern(self):
        result = _extract_threshold("BTC between $70,000 and $75,000")
        self.assertEqual(result[0], 'range')
        self.assertEqual(result[1], 70000.0)
        self.assertEqual(result[2], 75000.0)

    def test_no_threshold(self):
        result = _extract_threshold("Will it rain tomorrow?")
        self.assertIsNone(result)

    def test_at_least_pattern(self):
        result = _extract_threshold("GDP at least 3.0%")
        self.assertEqual(result, ('above', 3.0))


class TestExtractEventKey(unittest.TestCase):
    def test_event_ticker(self):
        m = {"event_ticker": "KXBTC-26MAR", "title": "BTC price"}
        self.assertEqual(_extract_event_key(m), "KXBTC-26MAR")

    def test_topic_fallback(self):
        m = {"title": "Bitcoin price above $70k"}
        key = _extract_event_key(m)
        self.assertEqual(key, "_topic_bitcoin")

    def test_no_group(self):
        m = {"title": "Random unrelated market"}
        key = _extract_event_key(m)
        self.assertIsNone(key)


class TestGroupRelatedMarkets(unittest.TestCase):
    def setUp(self):
        self.scanner = CombinatorialScanner()

    def test_group_by_event_ticker(self):
        markets = [
            {"event_ticker": "EVT-1", "title": "A"},
            {"event_ticker": "EVT-1", "title": "B"},
            {"event_ticker": "EVT-2", "title": "C"},
        ]
        groups = self.scanner.group_related_markets(markets)
        self.assertIn("EVT-1", groups)
        self.assertEqual(len(groups["EVT-1"]), 2)
        # EVT-2 has only 1 market, should be excluded
        self.assertNotIn("EVT-2", groups)

    def test_group_by_topic(self):
        markets = [
            {"title": "Bitcoin above $70k"},
            {"title": "Bitcoin above $75k"},
        ]
        groups = self.scanner.group_related_markets(markets)
        self.assertTrue(any("bitcoin" in k for k in groups.keys()))


class TestThresholdArbs(unittest.TestCase):
    def setUp(self):
        self.scanner = CombinatorialScanner()

    def test_above_subset_violation(self):
        """'above $75k' priced higher than 'above $70k' is an arb."""
        markets = [
            {"title": "BTC above $70,000", "yes_ask": 30, "ticker": "BTC-70K"},
            {"title": "BTC above $75,000", "yes_ask": 55, "ticker": "BTC-75K"},
        ]
        arbs = self.scanner.scan_threshold_arbs(markets)
        # BTC above 75k is a subset of BTC above 70k, so it should cost LESS
        # But it costs MORE (55 > 30), so there's an arb (25c - 14c fees = 11c)
        self.assertTrue(len(arbs) > 0)
        self.assertEqual(arbs[0]["type"], "threshold_arb")
        self.assertEqual(arbs[0]["buy_ticker"], "BTC-70K")
        self.assertEqual(arbs[0]["sell_ticker"], "BTC-75K")

    def test_no_arb_when_correctly_priced(self):
        """'above $75k' priced lower than 'above $70k' is correct."""
        markets = [
            {"title": "BTC above $70,000", "yes_ask": 50, "ticker": "BTC-70K"},
            {"title": "BTC above $75,000", "yes_ask": 30, "ticker": "BTC-75K"},
        ]
        arbs = self.scanner.scan_threshold_arbs(markets)
        self.assertEqual(len(arbs), 0)

    def test_below_superset_violation(self):
        """'below $65k' priced higher than 'below $70k' is an arb."""
        markets = [
            {"title": "BTC below $65,000", "yes_ask": 55, "ticker": "BTC-B65K"},
            {"title": "BTC below $70,000", "yes_ask": 25, "ticker": "BTC-B70K"},
        ]
        arbs = self.scanner.scan_threshold_arbs(markets)
        # below $65k is a subset of below $70k, so price($65k) <= price($70k)
        # But $65k costs 55 and $70k costs 25 -> violation (30c - 14c fees = 16c)
        self.assertTrue(len(arbs) > 0)

    def test_fee_filter(self):
        """Small mispricing should be filtered by fees."""
        markets = [
            {"title": "BTC above $70,000", "yes_ask": 40, "ticker": "BTC-70K"},
            {"title": "BTC above $75,000", "yes_ask": 41, "ticker": "BTC-75K"},
        ]
        arbs = self.scanner.scan_threshold_arbs(markets)
        # 1c difference - 14c fees = -13c, not profitable
        self.assertEqual(len(arbs), 0)


class TestMutualExclusion(unittest.TestCase):
    def setUp(self):
        self.scanner = CombinatorialScanner()

    def test_long_arb_when_sum_below_100(self):
        """Sum of YES asks < 100c means buying all guarantees profit."""
        markets = [
            {"event_ticker": "EVT", "yes_ask": 10, "yes_bid": 8, "ticker": "T1"},
            {"event_ticker": "EVT", "yes_ask": 15, "yes_bid": 12, "ticker": "T2"},
            {"event_ticker": "EVT", "yes_ask": 20, "yes_bid": 17, "ticker": "T3"},
            {"event_ticker": "EVT", "yes_ask": 10, "yes_bid": 8, "ticker": "T4"},
        ]
        # Sum of asks = 55, well below 100
        arbs = self.scanner.scan_mutual_exclusion(markets)
        self.assertTrue(len(arbs) > 0)
        self.assertEqual(arbs[0]["type"], "mutual_exclusion_long")

    def test_short_arb_when_sum_above_100(self):
        """Sum of YES bids > 100c means selling all guarantees profit."""
        markets = [
            {"event_ticker": "EVT", "yes_ask": 40, "yes_bid": 35, "ticker": "T1"},
            {"event_ticker": "EVT", "yes_ask": 40, "yes_bid": 35, "ticker": "T2"},
            {"event_ticker": "EVT", "yes_ask": 40, "yes_bid": 35, "ticker": "T3"},
        ]
        # Sum of bids = 105, above 100
        arbs = self.scanner.scan_mutual_exclusion(markets)
        self.assertTrue(len(arbs) > 0)
        self.assertEqual(arbs[0]["type"], "mutual_exclusion_short")

    def test_no_arb_normal_pricing(self):
        """Normal pricing should yield no arb."""
        markets = [
            {"event_ticker": "EVT", "yes_ask": 35, "yes_bid": 30, "ticker": "T1"},
            {"event_ticker": "EVT", "yes_ask": 35, "yes_bid": 30, "ticker": "T2"},
            {"event_ticker": "EVT", "yes_ask": 35, "yes_bid": 30, "ticker": "T3"},
        ]
        # Sum asks = 105 (no long arb), sum bids = 90 (no short arb)
        arbs = self.scanner.scan_mutual_exclusion(markets)
        self.assertEqual(len(arbs), 0)

    def test_too_few_markets(self):
        markets = [
            {"event_ticker": "EVT", "yes_ask": 10, "ticker": "T1"},
            {"event_ticker": "EVT", "yes_ask": 10, "ticker": "T2"},
        ]
        arbs = self.scanner.scan_mutual_exclusion(markets)
        self.assertEqual(len(arbs), 0)


class TestScanAll(unittest.TestCase):
    def test_scan_all_combines_results(self):
        scanner = CombinatorialScanner()
        groups = {
            "EVT-1": [
                {"event_ticker": "EVT-1", "title": "BTC above $70,000",
                 "yes_ask": 40, "yes_bid": 38, "ticker": "T1"},
                {"event_ticker": "EVT-1", "title": "BTC above $75,000",
                 "yes_ask": 50, "yes_bid": 48, "ticker": "T2"},
                {"event_ticker": "EVT-1", "title": "BTC above $80,000",
                 "yes_ask": 5, "yes_bid": 3, "ticker": "T3"},
            ],
        }
        arbs = scanner.scan_all(groups)
        # Should find threshold arb (T2 > T1) and possibly mutual exclusion
        self.assertTrue(len(arbs) > 0)

    def test_sorted_by_profit(self):
        scanner = CombinatorialScanner()
        groups = {
            "EVT-1": [
                {"event_ticker": "EVT-1", "title": "X above $100",
                 "yes_ask": 40, "yes_bid": 38, "ticker": "T1"},
                {"event_ticker": "EVT-1", "title": "X above $200",
                 "yes_ask": 60, "yes_bid": 58, "ticker": "T2"},
                {"event_ticker": "EVT-1", "title": "X above $300",
                 "yes_ask": 70, "yes_bid": 68, "ticker": "T3"},
            ],
        }
        arbs = scanner.scan_all(groups)
        if len(arbs) >= 2:
            profits = [a["profit_cents"] for a in arbs]
            self.assertEqual(profits, sorted(profits, reverse=True))


if __name__ == "__main__":
    unittest.main()
