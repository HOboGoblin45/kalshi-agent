"""Tests for modules/precision.py -- fixed-point price/fee/money math."""
import unittest
from decimal import Decimal

from modules.precision import (
    to_decimal, dollars_to_cents, cents_to_dollars,
    round_price_cents, net_edge_cents,
    VenueFees, KALSHI_FEES, POLYMARKET_FEES, get_venue_fees,
)


class TestToDecimal(unittest.TestCase):
    def test_int(self):
        self.assertEqual(to_decimal(42), Decimal("42"))

    def test_float(self):
        self.assertEqual(to_decimal(0.67), Decimal("0.67"))

    def test_string(self):
        self.assertEqual(to_decimal("0.6700"), Decimal("0.6700"))

    def test_dollar_string(self):
        self.assertEqual(to_decimal("$1.50"), Decimal("1.50"))

    def test_none(self):
        self.assertEqual(to_decimal(None), Decimal("0"))

    def test_default(self):
        self.assertEqual(to_decimal(None, Decimal("50")), Decimal("50"))

    def test_empty_string(self):
        self.assertEqual(to_decimal(""), Decimal("0"))

    def test_comma_number(self):
        self.assertEqual(to_decimal("1,234.56"), Decimal("1234.56"))


class TestDollarsCents(unittest.TestCase):
    def test_dollars_to_cents(self):
        self.assertEqual(dollars_to_cents("0.6700"), Decimal("67.00"))

    def test_dollars_to_cents_zero(self):
        self.assertEqual(dollars_to_cents(0), Decimal("0.00"))

    def test_cents_to_dollars(self):
        self.assertEqual(cents_to_dollars(67), Decimal("0.6700"))

    def test_round_trip(self):
        original = Decimal("0.6700")
        cents = dollars_to_cents(original)
        back = cents_to_dollars(cents)
        self.assertEqual(back, original)


class TestRoundPriceCents(unittest.TestCase):
    def test_whole_cent(self):
        self.assertEqual(round_price_cents(67), 67)

    def test_fractional_rounds_up(self):
        self.assertEqual(round_price_cents(67.5), 68)

    def test_fractional_rounds_down(self):
        self.assertEqual(round_price_cents(67.4), 67)


class TestNetEdgeCents(unittest.TestCase):
    def test_positive_edge(self):
        # If we think YES is 80% but market prices it at 60c, there should be edge
        edge = net_edge_cents(80, 60, 0.07, "YES")
        self.assertGreater(edge, 0)

    def test_no_edge(self):
        # If our probability matches market price, edge should be ~0 or negative after fees
        edge = net_edge_cents(50, 50, 0.07, "YES")
        self.assertLessEqual(edge, 0)

    def test_fee_impact(self):
        # Higher fees should reduce edge
        edge_low_fee = net_edge_cents(70, 50, 0.01, "YES")
        edge_high_fee = net_edge_cents(70, 50, 0.10, "YES")
        self.assertGreater(edge_low_fee, edge_high_fee)


class TestVenueFees(unittest.TestCase):
    def test_kalshi_taker_cost(self):
        self.assertEqual(KALSHI_FEES.taker_cost(1), Decimal("0.07"))
        self.assertEqual(KALSHI_FEES.taker_cost(10), Decimal("0.70"))

    def test_round_trip_cost(self):
        self.assertEqual(KALSHI_FEES.round_trip_cost(1), Decimal("0.14"))

    def test_net_pnl_profit(self):
        # Buy at 30c, sell at 50c, 1 contract
        pnl = KALSHI_FEES.net_pnl(30, 50, 1)
        expected = Decimal("0.20") - Decimal("0.14")  # $0.20 gross - $0.14 fees
        self.assertEqual(pnl, expected)

    def test_net_pnl_loss(self):
        # Buy at 50c, sell at 30c, 1 contract
        pnl = KALSHI_FEES.net_pnl(50, 30, 1)
        self.assertLess(pnl, 0)

    def test_polymarket_cheaper(self):
        k_cost = KALSHI_FEES.round_trip_cost(1)
        p_cost = POLYMARKET_FEES.round_trip_cost(1)
        self.assertGreater(k_cost, p_cost)

    def test_get_venue_fees(self):
        self.assertEqual(get_venue_fees("kalshi").name, "kalshi")
        self.assertEqual(get_venue_fees("polymarket").name, "polymarket")
        self.assertEqual(get_venue_fees("unknown").name, "kalshi")  # default


class TestKalshiFeeAccuracy(unittest.TestCase):
    """Verify fee calculations match Kalshi's actual fee schedule."""

    def test_fee_on_cheap_contract(self):
        # 10c contract, $0.07 fee each way
        # Total cost to enter: $0.10 + $0.07 = $0.17
        # If wins: payout $1.00 - entry_fee $0.07 - exit_fee $0.07 = $0.86 received
        # Net profit: $0.86 - $0.10 = $0.76
        pnl = KALSHI_FEES.net_pnl(10, 100, 1)  # buy at 10c, settles at 100c
        self.assertAlmostEqual(float(pnl), 0.76, places=2)

    def test_fee_drag_expensive_contract(self):
        # 90c contract, fee drag is proportionally larger
        pnl = KALSHI_FEES.net_pnl(90, 100, 1)  # buy at 90c, settles at 100c
        # Gross: $0.10, fees: $0.14, net: -$0.04
        self.assertLess(float(pnl), 0)  # Can't profit buying 90c even when right!


if __name__ == "__main__":
    unittest.main()
