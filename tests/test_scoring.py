"""Tests for modules/scoring.py -- market scoring and Kelly criterion."""
import unittest

from modules.scoring import (
    kelly, _best_price, _count_parlay_legs, score_market,
    extract_features, is_execution_eligible,
)


class TestKellyProduction(unittest.TestCase):
    """Test the production Kelly implementation (not the sidecar version)."""

    def test_positive_ev(self):
        contracts, cost = kelly(75, 50, 100, 10, 0.07, 0.20)
        self.assertGreater(contracts, 0)
        self.assertGreater(cost, 0)

    def test_negative_ev_returns_zero(self):
        contracts, cost = kelly(50, 50, 100, 10, 0.07, 0.20)
        self.assertEqual(contracts, 0)
        self.assertEqual(cost, 0)

    def test_high_fee_kills_ev(self):
        # Even with edge, very high fees should make it unprofitable
        contracts, cost = kelly(60, 50, 100, 10, 0.50, 0.20)
        self.assertEqual(contracts, 0)

    def test_max_bet_respected(self):
        contracts, cost = kelly(90, 20, 1000, 2.0, 0.07, 0.50)
        self.assertLessEqual(cost + contracts * 0.07, 2.0 + 0.01)  # small float tolerance

    def test_zero_bankroll(self):
        contracts, cost = kelly(75, 50, 0, 10, 0.07, 0.20)
        self.assertEqual(contracts, 0)

    def test_very_cheap_contract(self):
        # 5c contract with 80% probability should have strong EV
        contracts, cost = kelly(80, 5, 100, 10, 0.07, 0.20)
        self.assertGreater(contracts, 0)

    def test_expensive_contract_fee_drag(self):
        # 90c contract: even if 95% likely to win, fee drag may kill it
        contracts, cost = kelly(95, 90, 100, 10, 0.07, 0.20)
        # Win payoff is only 10c ($0.10), fees are $0.14 round-trip
        # win_payoff = 1.0 - 0.90 - 0.14 = -0.04 < 0
        self.assertEqual(contracts, 0)


class TestBestPrice(unittest.TestCase):
    def test_display_price_first(self):
        m = {"display_price": 67, "yes_bid": 50, "last_price": 55}
        self.assertEqual(_best_price(m), 67)

    def test_falls_through_to_last_price(self):
        m = {"display_price": 0, "yes_bid": 0, "last_price": 55}
        self.assertEqual(_best_price(m), 55)

    def test_no_bid_fallback(self):
        m = {"display_price": 0, "yes_bid": 0, "last_price": 0, "no_bid": 40}
        self.assertEqual(_best_price(m), 60)

    def test_all_zero(self):
        m = {"display_price": 0, "yes_bid": 0, "last_price": 0}
        self.assertIsNone(_best_price(m))


class TestCountParlayLegs(unittest.TestCase):
    def test_normal_title(self):
        m = {"title": "Will Bitcoin close above $100k?"}
        self.assertEqual(_count_parlay_legs(m), 1)

    def test_parlay_2_legs(self):
        m = {"title": "yes Lakers: 110+,yes Celtics: 105+"}
        self.assertEqual(_count_parlay_legs(m), 2)

    def test_parlay_many_legs(self):
        m = {"title": "yes A: 1+,yes B: 2+,yes C: 3+,yes D: 4+,yes E: 5+,yes F: 6+"}
        self.assertEqual(_count_parlay_legs(m), 6)


class TestExtractFeatures(unittest.TestCase):
    def test_basic_features(self):
        m = {"volume": 500, "display_price": 50, "_hrs_left": 12, "_category": "weather"}
        features = extract_features(m)
        self.assertEqual(features["category"], "weather")
        self.assertEqual(features["volume"], 500)
        self.assertTrue(features["has_data_source"])
        self.assertFalse(features["is_parlay"])

    def test_thin_market(self):
        m = {"volume": 3, "display_price": 50, "_hrs_left": 24, "_category": "other"}
        features = extract_features(m)
        self.assertTrue(features["is_thin"])
        self.assertEqual(features["thin_penalty"], -1)

    def test_parlay_detection(self):
        m = {"volume": 100, "display_price": 10, "_hrs_left": 6, "_category": "sports",
             "title": "yes A: 1+,yes B: 2+,yes C: 3+"}
        features = extract_features(m)
        self.assertTrue(features["is_parlay"])
        self.assertEqual(features["parlay_legs"], 3)


class TestExecutionEligibility(unittest.TestCase):
    def test_normal_market_eligible(self):
        m = {"volume": 100, "display_price": 50, "_hrs_left": 24, "_category": "weather",
             "title": "Will it rain?"}
        eligible, reason = is_execution_eligible(m)
        self.assertTrue(eligible)

    def test_extremely_thin_ineligible(self):
        m = {"volume": 3, "display_price": 50, "_hrs_left": 24, "_category": "other",
             "title": "Will X happen?"}
        eligible, reason = is_execution_eligible(m)
        self.assertFalse(eligible)
        self.assertIn("thin", reason.lower())

    def test_4_leg_parlay_ineligible(self):
        m = {"volume": 100, "display_price": 10, "_hrs_left": 6, "_category": "sports",
             "title": "yes A: 1+,yes B: 2+,yes C: 3+,yes D: 4+"}
        eligible, reason = is_execution_eligible(m)
        self.assertFalse(eligible)
        self.assertIn("parlay", reason.lower())

    def test_expiring_very_soon_ineligible(self):
        m = {"volume": 100, "display_price": 50, "_hrs_left": 0.1, "_category": "weather",
             "title": "Will it rain?"}
        eligible, reason = is_execution_eligible(m)
        self.assertFalse(eligible)
        self.assertIn("expiry", reason.lower())


if __name__ == "__main__":
    unittest.main()
