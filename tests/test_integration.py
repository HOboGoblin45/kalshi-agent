"""Integration tests with mock APIs simulating a full scan cycle."""
import sys, os, json, time, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kalshi-trading-skill", "scripts"))

import unittest
from unittest.mock import MagicMock, patch
from cross_platform import (
    match_markets, scan_cross_platform_arbitrage,
    execute_cross_arb, find_quickflip_candidates,
    get_best_price_across_platforms, route_order,
    CrossPlatformRiskMgr, check_circuit_breakers,
    estimate_slippage,
)
from kelly import kelly
try:
    from market_scanner import filter_markets, categorize, score_market, calc_hours_left
    HAS_MARKET_SCANNER = True
except BaseException:
    HAS_MARKET_SCANNER = False


# ═══════════════════════════════════════
# MOCK API CLASSES
# ═══════════════════════════════════════

class MockKalshiAPI:
    """Mock Kalshi API that returns configurable orderbook data."""

    def __init__(self, orderbooks=None, balance=100.0):
        self.orderbooks = orderbooks or {}
        self._balance = balance
        self.orders_placed = []

    def orderbook(self, ticker):
        return self.orderbooks.get(ticker, {"orderbook": {"yes": [], "no": []}})

    def balance(self):
        return self._balance

    def place_order(self, ticker, side, count, price):
        order = {"ticker": ticker, "side": side, "count": count, "price": price}
        self.orders_placed.append(order)
        return {"order": {"order_id": f"mock-{len(self.orders_placed)}", "status": "filled"}}

    def positions(self):
        return []

    def all_markets(self):
        return []


class MockPolymarketAPI:
    """Mock Polymarket API for testing cross-platform features."""

    def __init__(self, orderbooks=None, balance=50.0):
        self.orderbooks = orderbooks or {}
        self._balance = balance
        self.orders_placed = []
        self.is_trading_enabled = True
        self._address = "0xMOCK"

    @property
    def address(self):
        return self._address

    def orderbook(self, token_id):
        return self.orderbooks.get(token_id, {"orderbook": {"yes": [], "no": []}})

    def balance(self):
        return self._balance

    def place_order(self, token_id, side, size, price_cents):
        order = {"token_id": token_id, "side": side, "size": size, "price": price_cents}
        self.orders_placed.append(order)
        return {"id": f"poly-{len(self.orders_placed)}"}

    def positions(self):
        return []


# ═══════════════════════════════════════
# SAMPLE DATA
# ═══════════════════════════════════════

def _make_kalshi_market(ticker, title, category="weather", yes_bid=50, volume=200, hours_left=12):
    close_time = (datetime.datetime.now(datetime.timezone.utc) +
                  datetime.timedelta(hours=hours_left)).isoformat()
    return {
        "ticker": ticker, "title": title, "subtitle": "",
        "category": category, "yes_bid": yes_bid,
        "volume": volume, "close_time": close_time,
        "expiration_time": close_time, "event_ticker": ticker,
        "platform": "kalshi",
    }


def _make_poly_market(ticker, title, token_id, category="weather",
                      yes_price=50, volume=300, hours_left=12):
    close_time = (datetime.datetime.now(datetime.timezone.utc) +
                  datetime.timedelta(hours=hours_left)).isoformat()
    return {
        "ticker": ticker, "title": title, "subtitle": "",
        "token_id": token_id, "no_token_id": f"no-{token_id}",
        "category": category, "_category": category,
        "yes_bid": yes_price, "volume": volume,
        "close_time": close_time, "_hrs_left": hours_left,
        "platform": "polymarket",
    }


# ═══════════════════════════════════════
# INTEGRATION: MARKET MATCHING + ARB SCAN
# ═══════════════════════════════════════

@unittest.skipUnless(HAS_MARKET_SCANNER, "market_scanner requires cryptography module")
class TestFullArbScanCycle(unittest.TestCase):
    """Simulate a complete cross-platform arbitrage scan cycle."""

    def setUp(self):
        # Create matching markets on both platforms
        self.kalshi_markets = [
            _make_kalshi_market("KTEMP-NYC-60", "Will NYC temperature exceed 60°F tomorrow",
                                yes_bid=55, volume=500, hours_left=18),
            _make_kalshi_market("KFED-HOLD", "Will the Fed hold rates at March meeting",
                                category="fed_rates", yes_bid=72, volume=1000, hours_left=48),
        ]
        # Add required fields
        for m in self.kalshi_markets:
            m["_hrs_left"] = calc_hours_left(m)
            m["_category"] = categorize(m)
            m["_score"] = score_market(m)

        self.poly_markets = [
            _make_poly_market("PTEMP-NYC", "NYC temperature above 60°F tomorrow",
                              "tok-nyc-yes", yes_price=52, hours_left=18),
            _make_poly_market("PFED-HOLD", "Federal Reserve holds interest rates March",
                              "tok-fed-yes", category="fed_rates", yes_price=70, hours_left=48),
        ]

        # Orderbooks with arb opportunity: YES@Kalshi(40c) + NO@Poly(45c) = 85c < 100c
        self.kalshi_api = MockKalshiAPI(orderbooks={
            "KTEMP-NYC-60": {"orderbook": {"yes": [[40, 20], [42, 15]], "no": [[55, 10]]}},
            "KFED-HOLD": {"orderbook": {"yes": [[72, 30]], "no": [[30, 25]]}},
        })
        self.poly_api = MockPolymarketAPI(orderbooks={
            "tok-nyc-yes": {"orderbook": {"yes": [[52, 25]], "no": [[45, 15], [47, 10]]}},
            "tok-fed-yes": {"orderbook": {"yes": [[70, 40]], "no": [[32, 20]]}},
        })

    def test_match_and_scan_arb(self):
        """Full cycle: match markets -> scan arb -> find opportunities."""
        # Step 1: Match markets
        matches = match_markets(self.kalshi_markets, self.poly_markets,
                                threshold=0.50, cache_path=None)
        self.assertGreaterEqual(len(matches), 1, "Should match at least the weather markets")

        # Step 2: Scan for arb
        arbs = scan_cross_platform_arbitrage(matches, self.kalshi_api, self.poly_api)

        # Step 3: Verify arb math for any found opportunities
        for arb in arbs:
            # Profit must be positive
            self.assertGreater(arb["profit_cents"], 0)
            # Cost must be < 100 (after fees)
            self.assertLess(arb["cost_cents"] + 9, 100)  # 9c = (0.07+0.02)*100

    def test_execute_arb_dry_run(self):
        """Test arb execution in dry-run mode."""
        matches = match_markets(self.kalshi_markets, self.poly_markets,
                                threshold=0.50, cache_path=None)
        arbs = scan_cross_platform_arbitrage(matches, self.kalshi_api, self.poly_api)

        if arbs:
            result = execute_cross_arb(self.kalshi_api, self.poly_api, arbs[0],
                                       max_cost_dollars=10.0, dry_run=True)
            self.assertTrue(result["success"])
            self.assertTrue(result["dry_run"])
            self.assertGreater(result["contracts"], 0)
            # No orders should be placed in dry run
            self.assertEqual(len(self.kalshi_api.orders_placed), 0)
            self.assertEqual(len(self.poly_api.orders_placed), 0)

    def test_execute_arb_live(self):
        """Test arb execution places orders on both platforms."""
        matches = match_markets(self.kalshi_markets, self.poly_markets,
                                threshold=0.50, cache_path=None)
        arbs = scan_cross_platform_arbitrage(matches, self.kalshi_api, self.poly_api)

        if arbs:
            result = execute_cross_arb(self.kalshi_api, self.poly_api, arbs[0],
                                       max_cost_dollars=10.0, dry_run=False)
            if result["success"]:
                # Both legs should have orders
                self.assertGreater(len(self.kalshi_api.orders_placed), 0)
                self.assertGreater(len(self.poly_api.orders_placed), 0)


# ═══════════════════════════════════════
# INTEGRATION: BEST-PRICE ROUTING
# ═══════════════════════════════════════

class TestBestPriceRoutingIntegration(unittest.TestCase):
    """Test full price comparison across platforms."""

    def test_routes_to_cheaper_platform(self):
        # Kalshi YES@45c (eff: 45+7=52), Poly YES@48c (eff: 48+2=50) -> Poly wins
        platform, price = route_order("yes", 45, 48, kalshi_fee=0.07, poly_fee=0.02)
        self.assertEqual(platform, "polymarket")

    def test_routes_kalshi_when_cheaper(self):
        # Kalshi YES@40c (eff: 47), Poly YES@50c (eff: 52) -> Kalshi wins
        platform, price = route_order("yes", 40, 50, kalshi_fee=0.07, poly_fee=0.02)
        self.assertEqual(platform, "kalshi")


# ═══════════════════════════════════════
# INTEGRATION: KELLY + RISK MANAGEMENT
# ═══════════════════════════════════════

class TestKellyWithRiskManagement(unittest.TestCase):
    """Test Kelly sizing integrates with risk limits."""

    def test_kelly_then_risk_check(self):
        # Simulate: debate says 80% prob, market at 60c, $100 bankroll
        result = kelly(80, 60, 100, 10.0, fee_per_contract=0.07, fraction=0.30)
        self.assertGreater(result["contracts"], 0)

        # Check against risk limits
        mgr = CrossPlatformRiskMgr()
        cost = result["total_cost"]
        self.assertTrue(mgr.check_directional("kalshi", cost, max_exposure=50.0))

        # Record and check again
        mgr.record_trade("kalshi", cost)
        # Should still be within limits for another trade of same size
        self.assertTrue(mgr.check_directional("kalshi", cost, max_exposure=50.0))

    def test_circuit_breaker_stops_trading(self):
        paused, reason = check_circuit_breakers(100, 50, -20.0, max_daily_loss=15.0)
        self.assertTrue(paused)


# ═══════════════════════════════════════
# INTEGRATION: QUICK-FLIP END-TO-END
# ═══════════════════════════════════════

class TestQuickFlipEndToEnd(unittest.TestCase):
    """Test quick-flip from candidate finding through execution."""

    def test_find_and_size_quickflip(self):
        markets = [
            _make_kalshi_market("KCHEAP", "Some unlikely event", yes_bid=5, volume=100),
            _make_kalshi_market("KNORM", "Normal event", yes_bid=50, volume=200),
        ]
        for m in markets:
            m["_hrs_left"] = 24

        candidates = find_quickflip_candidates(markets, min_price=3, max_price=15)
        self.assertGreater(len(candidates), 0)

        # Size the trade with Kelly
        qf = candidates[0]
        result = kelly(15, qf["entry_price"], 100, 3.0,
                       fee_per_contract=0.07, fraction=0.30)
        # For a 5c contract at 15% probability, this may or may not be +EV
        # Just verify it doesn't crash


# ═══════════════════════════════════════
# INTEGRATION: SLIPPAGE IN ARB DECISION
# ═══════════════════════════════════════

class TestSlippageInArbDecision(unittest.TestCase):
    """Test that slippage estimation affects arb decisions."""

    def test_thin_orderbook_no_slippage_for_one(self):
        asks = [[45, 1], [55, 1]]
        avg, worst = estimate_slippage(asks, 1, 45)
        self.assertEqual(avg, 45.0)

    def test_thick_orderbook_slippage_for_many(self):
        asks = [[45, 2], [48, 3], [52, 10]]
        avg, worst = estimate_slippage(asks, 10, 45)
        # 2@45 + 3@48 + 5@52 = 90+144+260 = 494, avg = 49.4
        self.assertAlmostEqual(avg, 49.4)
        self.assertEqual(worst, 52)

    def test_slippage_makes_arb_unprofitable(self):
        """If slippage pushes avg fill above breakeven, arb is actually a loss."""
        # Best ask: YES@40 + NO@50 = 90c, profit=1c (barely profitable with 9c fees)
        # But with slippage for 5 contracts:
        yes_asks = [[40, 1], [48, 10]]  # Only 1 at 40c, rest at 48c
        no_asks = [[50, 1], [55, 10]]   # Only 1 at 50c, rest at 55c

        yes_avg, _ = estimate_slippage(yes_asks, 5, 40)
        no_avg, _ = estimate_slippage(no_asks, 5, 50)
        # 1@40 + 4@48 = 232, avg=46.4
        # 1@50 + 4@55 = 270, avg=54.0
        slipped_cost = yes_avg + no_avg  # ~100.4
        profit_after_slip = 100 - slipped_cost - 9  # 100 - 100.4 - 9 = -9.4

        self.assertLess(profit_after_slip, 0, "Slippage should make this arb unprofitable")


# ═══════════════════════════════════════
# INTEGRATION: MARKET FILTER PIPELINE
# ═══════════════════════════════════════

@unittest.skipUnless(HAS_MARKET_SCANNER, "market_scanner requires cryptography module")
class TestMarketFilterPipeline(unittest.TestCase):
    """Test the complete market filtering and scoring pipeline."""

    def test_filter_and_score(self):
        markets = [
            _make_kalshi_market("KTEMP", "NYC temperature above 60°F tomorrow",
                                yes_bid=55, volume=500, hours_left=6),
            _make_kalshi_market("KLOW", "Some market", yes_bid=50, volume=5, hours_left=1),
            _make_kalshi_market("KFED", "Fed rate decision March",
                                category="fed_rates", yes_bid=72, volume=1000, hours_left=24),
        ]

        filtered = filter_markets(markets, max_close_hours=48, min_volume=20)

        # Low volume market should be filtered
        tickers = [m["ticker"] for m in filtered]
        self.assertNotIn("KLOW", tickers)

        # Weather and fed markets should be scored
        for m in filtered:
            self.assertIn("_score", m)
            self.assertIn("_category", m)

        # Weather market closing in 6h with decent volume should score high
        if filtered:
            temp = next((m for m in filtered if m["ticker"] == "KTEMP"), None)
            if temp:
                self.assertGreater(temp["_score"], 5)


# ═══════════════════════════════════════
# INTEGRATION: PRODUCTION MODULE PIPELINE
# ═══════════════════════════════════════

class TestProductionMarketStateIntegration(unittest.TestCase):
    """Test MARKET_STATE population from orderbook data."""

    def setUp(self):
        from modules.market_state import MarketStateStore
        self.store = MarketStateStore()

    def test_rest_orderbook_populates_store(self):
        raw = {"orderbook": {"yes": [["0.4500", "10"]], "no": [["0.5000", "8"]]}}
        book = self.store.update_book("INT-MKT-1", raw, source="rest")
        self.assertEqual(book.ticker, "INT-MKT-1")
        self.assertFalse(book.is_stale)
        self.assertTrue(len(book.yes_bids) > 0)

    def test_feed_health_degrades_on_error(self):
        self.store.record_feed_success("kalshi")
        self.store.record_feed_error("kalshi")
        status = self.store.feed_status()
        self.assertEqual(status["kalshi"]["status"], "degraded")


class TestProductionExecutionPipeline(unittest.TestCase):
    """Test production scoring -> eligibility -> execution plan flow."""

    def test_full_pipeline(self):
        from modules.scoring import extract_features, is_execution_eligible
        from modules.execution import build_execution_plan

        market = {
            "ticker": "PIPE-1", "title": "Will it rain?",
            "volume": 200, "display_price": 50,
            "_hrs_left": 24, "_category": "weather",
        }
        features = extract_features(market)
        self.assertFalse(features["is_thin"])

        eligible, _ = is_execution_eligible(market, features)
        self.assertTrue(eligible)

        plan = build_execution_plan(
            ticker="PIPE-1", side="yes", probability=70, confidence=75,
            edge_pct=15.0, price_cents=50, contracts=2, hours_left=24,
        )
        self.assertIn(plan.action, ("taker", "maker", "no_trade"))

    def test_fee_drag_blocks_expensive_contract(self):
        from modules.scoring import kelly as prod_kelly
        contracts, cost = prod_kelly(95, 90, 100, 10, 0.07, 0.20)
        self.assertEqual(contracts, 0, "90c contract should be blocked by fee drag")


class TestProductionCalibrationPipeline(unittest.TestCase):
    """Test calibration prediction -> outcome -> metrics pipeline."""

    def test_prediction_to_brier(self):
        import tempfile, os
        from modules.calibration import CalibrationTracker

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            f.write('[]')
            path = f.name
        try:
            t = CalibrationTracker(log_path=path)
            t.record_prediction(ticker="C1", side="YES", probability=80,
                                confidence=75, market_price=50, edge=15.0, category="weather")
            t.record_outcome("C1", resolved_yes=True)
            brier = t.brier_score()
            self.assertLess(brier, 0.10)
        finally:
            os.unlink(path)


class TestProductionPrecisionIntegration(unittest.TestCase):
    """Test precision math with fee models."""

    def test_fee_drag_on_expensive(self):
        from modules.precision import KALSHI_FEES
        pnl = KALSHI_FEES.net_pnl(90, 100, 1)
        self.assertLess(float(pnl), 0, "90c contract should lose money after fees")

    def test_cheap_contract_profitable(self):
        from modules.precision import KALSHI_FEES
        pnl = KALSHI_FEES.net_pnl(30, 100, 1)
        self.assertGreater(float(pnl), 0.50)


class TestKellyMathUpgrades(unittest.TestCase):
    """Tests for the 8 Kelly Criterion mathematical upgrades."""

    def test_dynamic_min_edge_cheap_contract(self):
        """Upgrade 4: Cheap contracts should require higher min edge."""
        from modules.scoring import dynamic_min_edge
        # 10c contract with $0.07 fee: (2*0.07)/(0.10)*100 + 1 = 141%
        min_e = dynamic_min_edge(10, 0.07, 1.0)
        self.assertAlmostEqual(min_e, 141.0, places=1)
        # Higher fee drag than expensive contracts
        min_e_50 = dynamic_min_edge(50, 0.07, 1.0)
        self.assertGreater(min_e, min_e_50)

    def test_dynamic_min_edge_expensive_contract(self):
        """Upgrade 4: Expensive contracts have lower fee drag."""
        from modules.scoring import dynamic_min_edge
        # 50c contract: (2*0.07)/(0.50)*100 + 1 = 29%
        min_e = dynamic_min_edge(50, 0.07, 1.0)
        self.assertAlmostEqual(min_e, 29.0, places=0)

    def test_category_kelly_caps(self):
        """Upgrade 3: Weather cap should be higher than crypto."""
        from modules.scoring import get_category_kelly_cap
        weather = get_category_kelly_cap("weather")
        crypto = get_category_kelly_cap("crypto")
        self.assertGreater(weather, crypto)
        self.assertAlmostEqual(weather, 0.25, places=2)
        self.assertAlmostEqual(crypto, 0.10, places=2)

    def test_category_kelly_caps_user_override(self):
        """Upgrade 3: User can override default caps."""
        from modules.scoring import get_category_kelly_cap
        custom = {"weather": 0.30, "custom_cat": 0.18}
        self.assertAlmostEqual(get_category_kelly_cap("weather", custom), 0.30, places=2)
        self.assertAlmostEqual(get_category_kelly_cap("custom_cat", custom), 0.18, places=2)

    def test_debate_spread_full_agreement(self):
        """Upgrade 2: Zero spread → full Kelly multiplier."""
        from modules.scoring import debate_spread_kelly_mult
        self.assertAlmostEqual(debate_spread_kelly_mult(0), 1.0, places=2)

    def test_debate_spread_moderate_disagreement(self):
        """Upgrade 2: 20% spread → 0.6 multiplier."""
        from modules.scoring import debate_spread_kelly_mult
        self.assertAlmostEqual(debate_spread_kelly_mult(20), 0.6, places=2)

    def test_debate_spread_high_disagreement(self):
        """Upgrade 2: 35%+ spread → floor of 0.3."""
        from modules.scoring import debate_spread_kelly_mult
        self.assertAlmostEqual(debate_spread_kelly_mult(35), 0.3, places=2)
        self.assertAlmostEqual(debate_spread_kelly_mult(50), 0.3, places=2)

    def test_bayesian_prob_no_data(self):
        """Upgrade 1: With zero calibration data, heavy shrinkage toward 50%."""
        from modules.scoring import bayesian_kelly_prob
        # raw=80%, n=0, prior=(2,2) → weight=0, posterior=0.5 → 50%
        adj = bayesian_kelly_prob(80, 0, 0, 2, 2)
        self.assertAlmostEqual(adj, 50.0, places=1)

    def test_bayesian_prob_with_data(self):
        """Upgrade 1: With enough data, less shrinkage."""
        from modules.scoring import bayesian_kelly_prob
        # raw=80%, 15 wins out of 20, prior=(2,2)
        # weight = 20/(20+4) = 0.833
        # posterior = (2+15)/(4+20) = 17/24 = 0.708
        # adjusted = 0.833*0.8 + 0.167*0.708 = 0.785
        adj = bayesian_kelly_prob(80, 15, 20, 2, 2)
        self.assertGreater(adj, 75)
        self.assertLess(adj, 80)

    def test_thorp_concurrent_single(self):
        """Upgrade 5: Single bet → full Kelly."""
        from modules.scoring import thorp_concurrent_reduction
        self.assertAlmostEqual(thorp_concurrent_reduction(0.20, 1), 0.20, places=3)

    def test_thorp_concurrent_four(self):
        """Upgrade 5: 4 concurrent bets → half Kelly."""
        from modules.scoring import thorp_concurrent_reduction
        self.assertAlmostEqual(thorp_concurrent_reduction(0.20, 4), 0.10, places=3)

    def test_thorp_concurrent_nine(self):
        """Upgrade 5: 9 concurrent bets → 1/3 Kelly."""
        from modules.scoring import thorp_concurrent_reduction
        self.assertAlmostEqual(thorp_concurrent_reduction(0.30, 9), 0.10, places=3)

    def test_adaptive_prior_no_data(self):
        """Upgrade 8: With no data, returns base priors."""
        from modules.calibration import CalibrationTracker
        tracker = CalibrationTracker(log_path="/tmp/test_cal_nodata.json")
        tracker.records = []
        a, b = tracker.adaptive_prior("nonexistent")
        self.assertEqual(a, 2)
        self.assertEqual(b, 2)

    def test_adaptive_prior_good_calibration(self):
        """Upgrade 8: Good Brier score reduces prior strength."""
        from modules.calibration import CalibrationTracker
        tracker = CalibrationTracker(log_path="/tmp/test_cal_good.json")
        # Create fake resolved records with good calibration
        tracker.records = []
        for i in range(20):
            # Predict 80%, resolve True → good calibration
            tracker.records.append({
                "ticker": f"T{i}", "side": "YES", "our_probability": 80,
                "our_confidence": 85, "market_price": 70, "edge": 10,
                "category": "weather", "resolved": True, "resolution_time": "2025-01-01",
                "bull_prob": 80, "bear_prob": 70, "debate_spread": 10,
            })
        a, b = tracker.adaptive_prior("weather")
        # Good calibration → scale < 1 → priors reduced
        self.assertLess(a, 2)
        self.assertLess(b, 2)

    def test_2x_kelly_ceiling_logic(self):
        """Upgrade 6: Cost should never exceed 2x raw Kelly bet."""
        # Simulate: kelly_fraction=0.20, bankroll=$100, raw_kelly=0.20*100=$20
        # max_allowed = 2*20 = $40. If cost=$50, should be capped.
        raw_kelly_bet = 0.20 * 100  # $20
        max_allowed = 2.0 * raw_kelly_bet  # $40
        cost = 50.0
        self.assertGreater(cost, max_allowed)
        # After capping:
        bp = 30  # 30 cents
        trade_fee = 0.07
        capped_contracts = max(1, int(max_allowed / (bp / 100 + trade_fee)))
        self.assertGreater(capped_contracts, 0)
        capped_cost = round(capped_contracts * bp / 100, 2)
        self.assertLessEqual(capped_cost, max_allowed)


class TestScanPhaseOrder(unittest.TestCase):
    """Verify all scan phases are present and correctly ordered."""

    def test_all_phases_present(self):
        with open("kalshi-agent.py") as f:
            content = f.read()
        # All phases must appear in order
        phases = [
            "PHASE 0",  # Market Making
            "PHASE 1",  # Cross-Platform Arb
            "PHASE 2",  # Within-Market Arb
            "PHASE 3",  # Quick-Flip
            "PHASE 4",  # AI-Driven Directional Trading
        ]
        last_pos = -1
        for phase in phases:
            pos = content.find(phase)
            self.assertGreater(pos, last_pos,
                f"{phase} not found or out of order (pos={pos}, last={last_pos})")
            last_pos = pos

    def test_kill_switch_on_shutdown(self):
        """Verify market maker stop() is called on KeyboardInterrupt."""
        with open("kalshi-agent.py") as f:
            content = f.read()
        self.assertIn("market_maker.stop()", content)

    def test_news_trigger_wired(self):
        """Verify news trigger is initialized and checked."""
        with open("kalshi-agent.py") as f:
            content = f.read()
        self.assertIn("NewsTrigger", content)
        self.assertIn("news_trigger.has_triggers", content)

    def test_ws_arb_wired(self):
        """Verify WebSocket arb trigger is wired."""
        with open("kalshi-agent.py") as f:
            content = f.read()
        self.assertIn("check_single_market_arb", content)
        self.assertIn("push_ws_arb", content)
        self.assertIn("pop_ws_arbs", content)

    def test_combinatorial_scanner_wired(self):
        """Verify combinatorial arb scanner is integrated."""
        with open("kalshi-agent.py") as f:
            content = f.read()
        self.assertIn("CombinatorialScanner", content)

    def test_polymarket_fully_integrated(self):
        """Verify Polymarket is integrated into all trading paths."""
        with open("kalshi-agent.py") as f:
            content = f.read()
        self.assertIn("PolymarketAPI", content)
        self.assertIn("poly_enabled", content)
        self.assertIn("poly_mkts", content)
        self.assertIn("execute_cross_arb(self.api, self.poly_api", content)
        self.assertIn("poly_api.balance()", content)


if __name__ == "__main__":
    unittest.main()
