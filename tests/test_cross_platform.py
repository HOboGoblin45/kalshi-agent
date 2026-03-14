"""Unit tests for cross-platform matching, arbitrage, and routing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kalshi-trading-skill", "scripts"))

import unittest
import tempfile
from cross_platform import (
    _jaccard_similarity, _levenshtein_similarity, combined_similarity,
    match_markets, scan_cross_platform_arbitrage, _best_ask_price, _depth_at_price,
    route_order, find_quickflip_candidates,
    get_bankroll_tier, get_dynamic_kelly,
    CrossPlatformRiskMgr, check_circuit_breakers, platform_available,
    estimate_slippage,
)


# ═══════════════════════════════════════
# SIMILARITY FUNCTIONS
# ═══════════════════════════════════════

class TestJaccardSimilarity(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(_jaccard_similarity("hello world", "hello world"), 1.0)

    def test_no_overlap(self):
        self.assertAlmostEqual(_jaccard_similarity("hello world", "foo bar"), 0.0)

    def test_partial_overlap(self):
        score = _jaccard_similarity("NYC high temp above 60", "NYC high temp above 65")
        self.assertGreater(score, 0.5)

    def test_case_insensitive(self):
        self.assertAlmostEqual(
            _jaccard_similarity("Hello World", "hello world"), 1.0
        )

    def test_empty_string(self):
        self.assertEqual(_jaccard_similarity("", "hello"), 0.0)
        self.assertEqual(_jaccard_similarity("hello", ""), 0.0)
        self.assertEqual(_jaccard_similarity("", ""), 0.0)


class TestLevenshteinSimilarity(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(_levenshtein_similarity("hello", "hello"), 1.0)

    def test_completely_different(self):
        score = _levenshtein_similarity("abcdef", "zyxwvu")
        self.assertLess(score, 0.5)

    def test_one_char_diff(self):
        score = _levenshtein_similarity("hello", "hallo")
        self.assertGreater(score, 0.7)

    def test_empty_strings(self):
        self.assertAlmostEqual(_levenshtein_similarity("", ""), 1.0)

    def test_one_empty(self):
        self.assertAlmostEqual(_levenshtein_similarity("hello", ""), 0.0)


class TestCombinedSimilarity(unittest.TestCase):
    def test_identical_titles(self):
        self.assertAlmostEqual(
            combined_similarity("Will it rain in NYC?", "Will it rain in NYC?"), 1.0
        )

    def test_similar_market_titles(self):
        score = combined_similarity(
            "Will NYC high temperature be above 60°F on March 12?",
            "NYC high temperature above 60°F March 12"
        )
        self.assertGreater(score, 0.6)

    def test_different_markets(self):
        score = combined_similarity(
            "Fed rate decision March",
            "NYC temperature tomorrow"
        )
        self.assertLess(score, 0.3)


# ═══════════════════════════════════════
# MARKET MATCHING
# ═══════════════════════════════════════

class TestMatchMarkets(unittest.TestCase):
    def setUp(self):
        self.kalshi = [
            {"ticker": "K-TEMP-NYC-60", "title": "NYC high temp above 60°F March 12",
             "_category": "weather", "_hrs_left": 24},
            {"ticker": "K-FED-HOLD", "title": "Fed holds rates at March meeting",
             "_category": "fed_rates", "_hrs_left": 72},
        ]
        self.poly = [
            {"ticker": "P-TEMP-NYC", "title": "NYC high temperature above 60°F March 12",
             "_category": "weather", "_hrs_left": 24, "token_id": "tok1"},
            {"ticker": "P-OIL", "title": "Oil price above 80 this week",
             "_category": "energy", "_hrs_left": 48, "token_id": "tok2"},
        ]

    def test_match_similar_markets(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cache_path = f.name
        try:
            matches = match_markets(self.kalshi, self.poly, threshold=0.50, cache_path=cache_path)
            # Should match the weather markets
            self.assertGreaterEqual(len(matches), 1)
            self.assertEqual(matches[0]["kalshi"]["ticker"], "K-TEMP-NYC-60")
        finally:
            os.unlink(cache_path)

    def test_no_match_different_categories(self):
        kalshi = [{"ticker": "K-FED", "title": "Fed rate decision",
                    "_category": "fed_rates", "_hrs_left": 24}]
        poly = [{"ticker": "P-WEATHER", "title": "NYC temperature tomorrow",
                  "_category": "weather", "_hrs_left": 24, "token_id": "t1"}]
        matches = match_markets(kalshi, poly, threshold=0.70, cache_path=None)
        self.assertEqual(len(matches), 0)

    def test_time_proximity_filter(self):
        # Markets with resolution dates 100h apart shouldn't match
        kalshi = [{"ticker": "K1", "title": "Event ABC", "_category": "other", "_hrs_left": 24}]
        poly = [{"ticker": "P1", "title": "Event ABC", "_category": "other",
                  "_hrs_left": 200, "token_id": "t1"}]
        matches = match_markets(kalshi, poly, threshold=0.50, cache_path=None)
        self.assertEqual(len(matches), 0)


# ═══════════════════════════════════════
# ORDERBOOK HELPERS
# ═══════════════════════════════════════

class TestBestAskPrice(unittest.TestCase):
    def test_list_format(self):
        self.assertEqual(_best_ask_price([[45, 10], [50, 5]]), 45)

    def test_scalar_format(self):
        self.assertEqual(_best_ask_price([30, 40, 50]), 30)

    def test_empty(self):
        self.assertIsNone(_best_ask_price([]))

    def test_none(self):
        self.assertIsNone(_best_ask_price(None))


class TestDepthAtPrice(unittest.TestCase):
    def test_single_level(self):
        self.assertEqual(_depth_at_price([[45, 10]], 45), 10)

    def test_multiple_same_price(self):
        self.assertEqual(_depth_at_price([[45, 10], [45, 5], [50, 3]], 45), 15)

    def test_no_match(self):
        # Returns max(total, 1) = 1 when no entries match
        self.assertEqual(_depth_at_price([[50, 10]], 45), 1)


# ═══════════════════════════════════════
# ARBITRAGE MATH
# ═══════════════════════════════════════

class TestArbitrageMath(unittest.TestCase):
    """Verify the core arb math: YES + NO < $1.00 after fees = profit."""

    def test_arb_no_profit(self):
        # YES@48c + NO@50c = 98c, fees=7c => 100 - 98 - 7 = -5c (no arb)
        yes_price, no_price = 48, 50
        fee_k, fee_p = 0.07, 0.00
        cost = yes_price + no_price
        fees = (fee_k + fee_p) * 100
        profit = 100 - cost - fees
        self.assertLess(profit, 0)

    def test_arb_profit_exists(self):
        # YES@35c + NO@45c = 80c, fees=7c => 100 - 80 - 7 = 13c profit
        yes_price, no_price = 35, 45
        fee_k, fee_p = 0.07, 0.00
        cost = yes_price + no_price
        fees = (fee_k + fee_p) * 100
        profit = 100 - cost - fees
        self.assertGreater(profit, 0)
        self.assertAlmostEqual(profit, 13.0)

    def test_arb_with_both_fees(self):
        # YES@35c + NO@45c = 80c, fees = (0.07+0.02)*100 = 9c => profit = 11c
        yes_price, no_price = 35, 45
        fee_k, fee_p = 0.07, 0.02
        cost = yes_price + no_price
        fees = (fee_k + fee_p) * 100
        profit = 100 - cost - fees
        self.assertAlmostEqual(profit, 11.0)


# ═══════════════════════════════════════
# BEST-PRICE ROUTING
# ═══════════════════════════════════════

class TestRouteOrder(unittest.TestCase):
    def test_kalshi_cheaper(self):
        platform, price = route_order("yes", 45, 50, kalshi_fee=0.07, poly_fee=0.00)
        # Kalshi: 45 + 7 = 52, Poly: 50 + 0 = 50 => Poly wins
        self.assertEqual(platform, "polymarket")

    def test_poly_cheaper(self):
        platform, price = route_order("yes", 40, 50, kalshi_fee=0.07, poly_fee=0.00)
        # Kalshi: 40 + 7 = 47, Poly: 50 + 0 = 50 => Kalshi wins
        self.assertEqual(platform, "kalshi")

    def test_equal_prefers_kalshi(self):
        platform, _ = route_order("yes", 50, 50, kalshi_fee=0.00, poly_fee=0.00)
        self.assertEqual(platform, "kalshi")  # Ties go to kalshi (<=)


# ═══════════════════════════════════════
# QUICK-FLIP SCALPING
# ═══════════════════════════════════════

class TestQuickFlipCandidates(unittest.TestCase):
    def test_finds_cheap_contracts(self):
        markets = [
            {"yes_bid": 5, "volume": 100, "_hrs_left": 24, "platform": "kalshi"},
            {"yes_bid": 50, "volume": 200, "_hrs_left": 24, "platform": "kalshi"},
        ]
        candidates = find_quickflip_candidates(markets)
        # Only the 5c market qualifies (3-15c range)
        tickers = [c["entry_price"] for c in candidates]
        self.assertIn(5, tickers)

    def test_filters_low_volume(self):
        markets = [{"yes_bid": 5, "volume": 10, "_hrs_left": 24}]
        candidates = find_quickflip_candidates(markets, min_volume=50)
        self.assertEqual(len(candidates), 0)

    def test_filters_expiring_soon(self):
        markets = [{"yes_bid": 5, "volume": 100, "_hrs_left": 1}]
        candidates = find_quickflip_candidates(markets)
        self.assertEqual(len(candidates), 0)

    def test_both_sides_checked(self):
        # yes_bid=95 => no_price=5 (cheap NO side)
        markets = [{"yes_bid": 95, "volume": 100, "_hrs_left": 24}]
        candidates = find_quickflip_candidates(markets)
        no_sides = [c for c in candidates if c["side"] == "no"]
        self.assertGreater(len(no_sides), 0)


# ═══════════════════════════════════════
# BANKROLL TIERS
# ═══════════════════════════════════════

class TestBankrollTier(unittest.TestCase):
    def test_high_bankroll(self):
        tier = get_bankroll_tier(600)
        self.assertEqual(tier["max_bet_per_trade"], 60.0)

    def test_low_bankroll(self):
        tier = get_bankroll_tier(10)
        self.assertEqual(tier["max_bet_per_trade"], 8.0)

    def test_tiers_ordered(self):
        # Higher bankroll should give higher max_bet
        low = get_bankroll_tier(50)
        high = get_bankroll_tier(500)
        self.assertGreater(high["max_bet_per_trade"], low["max_bet_per_trade"])


class TestDynamicKelly(unittest.TestCase):
    def test_loss_cooldown_reduces(self):
        adjusted = get_dynamic_kelly(0.30, win_streak=0, loss_cooldown=2)
        self.assertLess(adjusted, 0.30)

    def test_win_streak_increases(self):
        adjusted = get_dynamic_kelly(0.30, win_streak=3, loss_cooldown=0)
        self.assertGreater(adjusted, 0.30)

    def test_cap_at_50pct(self):
        adjusted = get_dynamic_kelly(0.30, win_streak=20, loss_cooldown=0)
        self.assertLessEqual(adjusted, 0.50)

    def test_no_streak_unchanged(self):
        self.assertEqual(get_dynamic_kelly(0.30, 0, 0), 0.30)


# ═══════════════════════════════════════
# CROSS-PLATFORM RISK MANAGER
# ═══════════════════════════════════════

class TestCrossPlatformRiskMgr(unittest.TestCase):
    def test_initial_exposure_zero(self):
        mgr = CrossPlatformRiskMgr()
        self.assertEqual(mgr.total_exposure, 0.0)

    def test_record_trade(self):
        mgr = CrossPlatformRiskMgr()
        mgr.record_trade("kalshi", 10.0)
        self.assertEqual(mgr.kalshi_exposure, 10.0)
        mgr.record_trade("polymarket", 5.0)
        self.assertEqual(mgr.total_exposure, 15.0)

    def test_check_directional_within_limits(self):
        mgr = CrossPlatformRiskMgr()
        self.assertTrue(mgr.check_directional("kalshi", 10.0, max_exposure=50.0))

    def test_check_directional_exceeds_limits(self):
        mgr = CrossPlatformRiskMgr()
        mgr.record_trade("kalshi", 45.0)
        self.assertFalse(mgr.check_directional("polymarket", 10.0, max_exposure=50.0))

    def test_record_arb(self):
        mgr = CrossPlatformRiskMgr()
        mgr.record_arb(5.0, 5.0)
        self.assertEqual(len(mgr.arb_pairs), 1)
        self.assertEqual(mgr.total_exposure, 10.0)

    def test_win_streak_tracking(self):
        mgr = CrossPlatformRiskMgr()
        mgr.record_outcome(True)
        mgr.record_outcome(True)
        self.assertEqual(mgr.win_streak, 2)
        mgr.record_outcome(False)
        self.assertEqual(mgr.win_streak, 0)
        self.assertEqual(mgr.loss_cooldown, 2)

    def test_tick_cooldown(self):
        mgr = CrossPlatformRiskMgr()
        mgr.loss_cooldown = 2
        mgr.tick_cooldown()
        self.assertEqual(mgr.loss_cooldown, 1)
        mgr.tick_cooldown()
        self.assertEqual(mgr.loss_cooldown, 0)


# ═══════════════════════════════════════
# CIRCUIT BREAKERS
# ═══════════════════════════════════════

class TestCircuitBreakers(unittest.TestCase):
    def test_daily_loss_triggers(self):
        paused, reason = check_circuit_breakers(100, 100, -20.0, max_daily_loss=15.0)
        self.assertTrue(paused)
        self.assertIn("daily loss", reason.lower())

    def test_both_low_balance_triggers(self):
        paused, reason = check_circuit_breakers(2, 3, 0, min_platform_balance=5.0)
        self.assertTrue(paused)

    def test_single_low_balance_ok(self):
        paused, _ = check_circuit_breakers(2, 100, 0, min_platform_balance=5.0)
        self.assertFalse(paused)

    def test_consecutive_losses_trigger(self):
        paused, _ = check_circuit_breakers(100, 100, 0, consecutive_losses=3)
        self.assertTrue(paused)

    def test_normal_conditions_ok(self):
        paused, reason = check_circuit_breakers(100, 100, -5.0)
        self.assertFalse(paused)
        self.assertEqual(reason, "OK")


class TestPlatformAvailable(unittest.TestCase):
    def test_above_minimum(self):
        self.assertTrue(platform_available(10.0, 5.0))

    def test_below_minimum(self):
        self.assertFalse(platform_available(3.0, 5.0))


# ═══════════════════════════════════════
# SLIPPAGE ESTIMATION
# ═══════════════════════════════════════

class TestEstimateSlippage(unittest.TestCase):
    def test_no_slippage_when_depth_sufficient(self):
        asks = [[45, 100], [50, 50]]
        avg, worst = estimate_slippage(asks, 5, 45)
        self.assertEqual(avg, 45.0)
        self.assertEqual(worst, 45)

    def test_slippage_when_exceeding_depth(self):
        asks = [[45, 3], [48, 5], [50, 10]]
        avg, worst = estimate_slippage(asks, 5, 45)
        # 3 @ 45 + 2 @ 48 = 135 + 96 = 231, avg = 46.2
        self.assertAlmostEqual(avg, 46.2)
        self.assertEqual(worst, 48)

    def test_empty_orderbook(self):
        avg, worst = estimate_slippage([], 5, 45)
        self.assertEqual(avg, 45)

    def test_zero_contracts(self):
        avg, worst = estimate_slippage([[45, 10]], 0, 45)
        self.assertEqual(avg, 45)


# ═══════════════════════════════════════
# ORDERBOOK VALIDATION (dict format)
# ═══════════════════════════════════════

class TestOrderbookDictFormat(unittest.TestCase):
    def test_dict_asks(self):
        asks = [{"price": 45, "size": 10}, {"price": 50, "size": 5}]
        self.assertEqual(_best_ask_price(asks), 45)

    def test_dict_depth(self):
        asks = [{"price": 45, "size": 10}, {"price": 45, "size": 5}]
        self.assertEqual(_depth_at_price(asks, 45), 15)

    def test_dollar_format_prices(self):
        asks = [[0.45, 10], [0.50, 5]]
        self.assertEqual(_best_ask_price(asks), 45)

    def test_invalid_price_rejected(self):
        asks = [[150, 10]]  # > 99 cents
        self.assertIsNone(_best_ask_price(asks))

    def test_mixed_formats_robust(self):
        # Even garbage entries shouldn't crash
        asks = [None, "bad"]
        result = _best_ask_price(asks)
        # Should handle gracefully (first entry is None)
        self.assertIsNone(result)


class TestArbPositionTracker(unittest.TestCase):
    def setUp(self):
        from modules.arbitrage import ArbPositionTracker
        self.tracker = ArbPositionTracker()

    def test_record_and_retrieve(self):
        self.tracker.record_entry("TEST-1", "KTEST", "poly-token", "YES@Kalshi + NO@Poly",
                                  40, 55, 5, 5.0)
        positions = self.tracker.get_open_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["kalshi_ticker"], "KTEST")
        self.assertEqual(positions[0]["contracts"], 5)

    def test_exit_position(self):
        self.tracker.record_entry("TEST-1", "KTEST", "poly-token", "YES@Kalshi", 40, 55, 5, 5.0)
        self.tracker.record_exit("TEST-1", reason="rotation")
        self.assertFalse(self.tracker.has_open_positions())

    def test_multiple_positions(self):
        self.tracker.record_entry("A", "KA", "pa", "s", 40, 55, 5, 5.0)
        self.tracker.record_entry("B", "KB", "pb", "s", 30, 65, 3, 3.0)
        self.assertEqual(len(self.tracker.get_open_positions()), 2)
        self.tracker.record_exit("A")
        self.assertEqual(len(self.tracker.get_open_positions()), 1)

    def test_clear_closed(self):
        self.tracker.record_entry("OLD", "KOLD", "p", "s", 40, 55, 1, 1.0, entry_time=1.0)
        self.tracker.record_exit("OLD")
        self.tracker._positions["OLD"]["exit_time"] = 1.0  # Very old
        self.tracker.clear_closed(max_age_hours=1)
        self.assertEqual(len(self.tracker._positions), 0)


class TestShouldRotateArb(unittest.TestCase):
    def test_no_rotation_when_no_positions(self):
        from modules.arbitrage import should_rotate_arb
        result = should_rotate_arb([], [{"profit_cents": 10}])
        self.assertEqual(result, [])

    def test_no_rotation_when_no_opportunities(self):
        import time
        from modules.arbitrage import should_rotate_arb
        result = should_rotate_arb([{"entry_profit_cents": 5, "entry_time": time.time()}], [])
        self.assertEqual(result, [])

    def test_rotation_when_much_better_opportunity(self):
        import time
        from modules.arbitrage import should_rotate_arb
        current = [{
            "kalshi_ticker": "KOLD", "entry_profit_cents": 3.0,
            "entry_time": time.time() - 300,
        }]
        new_opps = [{
            "kalshi_ticker": "KNEW", "profit_cents": 40.0,
            "title": "New Opp",
        }]
        # total_rotation_cost = (0.07 + 0.02) * 100 * 2 = 18c
        # net = 40 - 3 - 18 = 19c > 3c threshold
        result = should_rotate_arb(current, new_opps, min_improvement_cents=3.0)
        self.assertEqual(len(result), 1)
        self.assertGreater(result[0]["net_improvement"], 0)

    def test_no_rotation_when_marginal_improvement(self):
        import time
        from modules.arbitrage import should_rotate_arb
        current = [{
            "kalshi_ticker": "KOLD", "entry_profit_cents": 8.0,
            "entry_time": time.time(),
        }]
        new_opps = [{
            "kalshi_ticker": "KNEW", "profit_cents": 9.0,  # Only 1c better, not enough after fees
        }]
        result = should_rotate_arb(current, new_opps, min_improvement_cents=3.0)
        self.assertEqual(len(result), 0)

    def test_skip_same_market(self):
        import time
        from modules.arbitrage import should_rotate_arb
        current = [{"kalshi_ticker": "KSAME", "entry_profit_cents": 3.0, "entry_time": time.time()}]
        new_opps = [{"kalshi_ticker": "KSAME", "profit_cents": 50.0}]
        result = should_rotate_arb(current, new_opps)
        self.assertEqual(len(result), 0)


class TestParallelExecution(unittest.TestCase):
    def test_parallel_flag_in_dry_run(self):
        from modules.arbitrage import execute_cross_arb
        opp = {
            "arb_class": "locked", "kalshi_ticker": "KTEST", "poly_token": "ptest",
            "poly_no_token": "ptest_no", "strategy": 1, "cost_cents": 90,
            "profit_cents": 10, "k_price": 40, "p_price": 50,
            "strategy_desc": "YES@Kalshi + NO@Polymarket",
        }
        result = execute_cross_arb(None, None, opp, dry_run=True, parallel=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["execution_mode"], "parallel")

    def test_sequential_flag_in_dry_run(self):
        from modules.arbitrage import execute_cross_arb
        opp = {
            "arb_class": "locked", "kalshi_ticker": "KTEST", "poly_token": "ptest",
            "poly_no_token": "ptest_no", "strategy": 1, "cost_cents": 90,
            "profit_cents": 10, "k_price": 40, "p_price": 50,
            "strategy_desc": "YES@Kalshi + NO@Polymarket",
        }
        result = execute_cross_arb(None, None, opp, dry_run=True, parallel=False)
        self.assertTrue(result["success"])
        self.assertEqual(result["execution_mode"], "sequential")


if __name__ == "__main__":
    unittest.main()
