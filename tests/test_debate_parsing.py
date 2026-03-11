"""Unit tests for debate output parsing (extracted from kalshi-agent.py)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
import re


# ── Parsing helpers (mirrored from kalshi-agent.py) ──

def parse_int(text, default=0):
    m = re.search(r'[-+]?\d{1,3}', str(text))
    return int(m.group()) if m else default


def parse_orderbook_price(raw_value):
    """Parse an orderbook price to cents (1-99). Returns None if invalid."""
    try:
        v = float(str(raw_value).replace("$", ""))
        if v < 0: return None
        if v < 1: v *= 100
        v = int(round(v))
        if v < 1 or v > 99: return None
        return v
    except (ValueError, TypeError):
        return None


def parse_synthesis_field(text, field):
    """Extract a field value from synthesis output text."""
    pattern = rf'^{field}:\s*(.+)$'
    m = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


def parse_synthesis(text):
    """Parse a complete synthesis output into a dict."""
    result = {}
    for field in ["PROBABILITY", "CONFIDENCE", "SIDE", "EVIDENCE", "RISK",
                   "PRICE_CENTS", "CONTRACTS", "EDGE_DURATION_HOURS"]:
        val = parse_synthesis_field(text, field)
        if val is not None:
            if field in ("PROBABILITY", "CONFIDENCE", "PRICE_CENTS", "CONTRACTS",
                         "EDGE_DURATION_HOURS"):
                result[field.lower()] = parse_int(val)
            else:
                result[field.lower()] = val
    return result


# ═══════════════════════════════════════
# PARSE INT
# ═══════════════════════════════════════

class TestParseInt(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(parse_int("75"), 75)

    def test_with_text(self):
        self.assertEqual(parse_int("about 42 percent"), 42)

    def test_negative(self):
        self.assertEqual(parse_int("-15"), -15)

    def test_no_number(self):
        self.assertEqual(parse_int("no digits here"), 0)

    def test_default(self):
        self.assertEqual(parse_int("nothing", default=50), 50)


# ═══════════════════════════════════════
# PARSE ORDERBOOK PRICE
# ═══════════════════════════════════════

class TestParseOrderbookPrice(unittest.TestCase):
    def test_cents_int(self):
        self.assertEqual(parse_orderbook_price(45), 45)

    def test_dollars_float(self):
        self.assertEqual(parse_orderbook_price(0.45), 45)

    def test_dollar_sign(self):
        self.assertEqual(parse_orderbook_price("$0.72"), 72)

    def test_string_cents(self):
        self.assertEqual(parse_orderbook_price("55"), 55)

    def test_out_of_range_high(self):
        self.assertIsNone(parse_orderbook_price(100))

    def test_out_of_range_low(self):
        self.assertIsNone(parse_orderbook_price(0))

    def test_negative(self):
        self.assertIsNone(parse_orderbook_price(-5))

    def test_none(self):
        self.assertIsNone(parse_orderbook_price(None))

    def test_garbage(self):
        self.assertIsNone(parse_orderbook_price("abc"))


# ═══════════════════════════════════════
# SYNTHESIS PARSING
# ═══════════════════════════════════════

class TestSynthesisParsing(unittest.TestCase):
    SAMPLE_SYNTHESIS = """PROBABILITY: 78
CONFIDENCE: 72
SIDE: YES
EDGE_DURATION_HOURS: 12
EVIDENCE: NWS forecasts 63°F, well above the 58°F threshold
RISK: Forecast uncertainty ±3°F could bring temp close to threshold
PRICE_CENTS: 50
CONTRACTS: 4"""

    def test_parse_probability(self):
        result = parse_synthesis(self.SAMPLE_SYNTHESIS)
        self.assertEqual(result["probability"], 78)

    def test_parse_confidence(self):
        result = parse_synthesis(self.SAMPLE_SYNTHESIS)
        self.assertEqual(result["confidence"], 72)

    def test_parse_side(self):
        result = parse_synthesis(self.SAMPLE_SYNTHESIS)
        self.assertEqual(result["side"], "YES")

    def test_parse_contracts(self):
        result = parse_synthesis(self.SAMPLE_SYNTHESIS)
        self.assertEqual(result["contracts"], 4)

    def test_parse_price(self):
        result = parse_synthesis(self.SAMPLE_SYNTHESIS)
        self.assertEqual(result["price_cents"], 50)

    def test_parse_evidence_string(self):
        result = parse_synthesis(self.SAMPLE_SYNTHESIS)
        self.assertIn("NWS", result["evidence"])

    def test_hold_side(self):
        text = "PROBABILITY: 50\nCONFIDENCE: 30\nSIDE: HOLD\nPRICE_CENTS: 50\nCONTRACTS: 0"
        result = parse_synthesis(text)
        self.assertEqual(result["side"], "HOLD")
        self.assertEqual(result["contracts"], 0)

    def test_missing_field(self):
        text = "PROBABILITY: 60\nSIDE: YES"
        result = parse_synthesis(text)
        self.assertIn("probability", result)
        self.assertNotIn("confidence", result)

    def test_empty_text(self):
        result = parse_synthesis("")
        self.assertEqual(result, {})


# ═══════════════════════════════════════
# CONVICTION GATES
# ═══════════════════════════════════════

class TestConvictionGates(unittest.TestCase):
    """Test the conviction gate rules from debate-protocol.md."""

    def _apply_gates(self, bull_prob, bear_prob, probability, confidence, edge_pct, fee_drag_pct):
        """Simplified conviction gate logic."""
        spread = abs(bull_prob - bear_prob)
        side = "YES" if probability > 50 else "NO"

        if spread > 30:
            side = "HOLD"
            confidence -= 25
        elif spread > 15:
            confidence -= (spread - 15)

        if edge_pct < fee_drag_pct:
            side = "HOLD"

        return side, max(0, confidence)

    def test_wide_spread_forces_hold(self):
        side, conf = self._apply_gates(80, 40, 60, 70, 10, 5)
        self.assertEqual(side, "HOLD")
        self.assertEqual(conf, 45)

    def test_moderate_spread_reduces_confidence(self):
        side, conf = self._apply_gates(75, 55, 65, 70, 10, 5)
        # spread=20, penalty=5
        self.assertEqual(side, "YES")
        self.assertEqual(conf, 65)

    def test_narrow_spread_no_penalty(self):
        side, conf = self._apply_gates(70, 60, 65, 70, 10, 5)
        self.assertEqual(conf, 70)

    def test_edge_below_fee_drag_forces_hold(self):
        side, conf = self._apply_gates(70, 60, 65, 70, 3, 7)
        self.assertEqual(side, "HOLD")


if __name__ == "__main__":
    unittest.main()
