"""Unit tests for fee-aware fractional Kelly Criterion position sizing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kalshi-trading-skill", "scripts"))

import unittest
from kelly import kelly


class TestKellyBasic(unittest.TestCase):
    """Test basic Kelly sizing behavior."""

    def test_positive_ev_returns_contracts(self):
        result = kelly(80, 60, 100, 20, fee_per_contract=0.07, fraction=0.30)
        self.assertGreater(result["contracts"], 0)
        self.assertIn("cost", result)
        self.assertIn("fees", result)

    def test_negative_ev_returns_zero(self):
        # 30% prob at 60c => negative EV
        result = kelly(30, 60, 100, 20, fee_per_contract=0.07, fraction=0.30)
        self.assertEqual(result["contracts"], 0)
        self.assertIn("reason", result)

    def test_zero_win_payoff(self):
        # Price 95c + 7c fee => win_payoff = -2c => can't profit
        result = kelly(99, 95, 100, 20, fee_per_contract=0.07, fraction=0.30)
        self.assertEqual(result["contracts"], 0)
        self.assertIn("win payoff", result.get("reason", "").lower())

    def test_high_fee_kills_edge(self):
        # Moderate edge but huge fee
        result = kelly(60, 50, 100, 20, fee_per_contract=0.25, fraction=0.30)
        self.assertEqual(result["contracts"], 0)

    def test_max_bet_cap(self):
        # Large bankroll but small max_bet should cap contracts
        result = kelly(85, 40, 1000, 5.0, fee_per_contract=0.07, fraction=0.30)
        total_cost = result["contracts"] * (0.40 + 0.07)
        self.assertLessEqual(total_cost, 5.0 + 0.01)  # Float tolerance

    def test_bankroll_zero(self):
        result = kelly(80, 50, 0, 10, fee_per_contract=0.07, fraction=0.30)
        self.assertEqual(result["contracts"], 0)

    def test_fraction_affects_sizing(self):
        aggressive = kelly(80, 50, 100, 20, fee_per_contract=0.07, fraction=0.50)
        conservative = kelly(80, 50, 100, 20, fee_per_contract=0.07, fraction=0.10)
        self.assertGreaterEqual(aggressive["contracts"], conservative["contracts"])

    def test_ev_per_contract_correct(self):
        result = kelly(75, 50, 100, 20, fee_per_contract=0.07, fraction=0.30)
        if result["contracts"] > 0:
            p = 0.75
            win_payoff = 0.50 - 0.07
            lose_cost = 0.50 + 0.07
            expected_ev = p * win_payoff - (1 - p) * lose_cost
            self.assertAlmostEqual(result["ev_per_contract"], expected_ev, places=3)

    def test_roi_format(self):
        result = kelly(80, 50, 100, 20, fee_per_contract=0.07, fraction=0.30)
        if result["contracts"] > 0:
            self.assertTrue(result["roi_if_correct"].endswith("%"))


class TestKellyEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_prob_1_percent(self):
        result = kelly(1, 50, 100, 20)
        self.assertEqual(result["contracts"], 0)

    def test_prob_99_percent(self):
        result = kelly(99, 50, 100, 20)
        self.assertGreater(result["contracts"], 0)

    def test_price_1_cent(self):
        result = kelly(10, 1, 100, 20, fee_per_contract=0.07)
        # Very cheap contract, even small prob can be +EV
        if result["contracts"] > 0:
            self.assertGreater(result["ev_per_contract"], 0)

    def test_price_99_cents(self):
        result = kelly(99, 99, 100, 20, fee_per_contract=0.07)
        # Win payoff = 1c - 7c fee = -6c => can't profit
        self.assertEqual(result["contracts"], 0)

    def test_zero_fee(self):
        result = kelly(60, 50, 100, 20, fee_per_contract=0.0, fraction=0.30)
        self.assertGreater(result["contracts"], 0)
        self.assertEqual(result["fees"], 0.0)


if __name__ == "__main__":
    unittest.main()
