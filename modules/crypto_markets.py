"""
Crypto bracket market discovery and management for Kalshi.

Kalshi crypto events use bracket-style markets where 40-75 price ranges each
represent a possible BTC settlement bracket. Exactly one bracket resolves YES
($1), all others resolve NO ($0). The sum of all bracket prices must equal
$1.00 -- any deviation is an arbitrage opportunity.

Usage:
    discovery = CryptoMarketDiscovery(kalshi_api)
    events = discovery.scan_active_events()
    brackets = discovery.get_brackets("KXBTC-26MAR1420")
"""
import time, logging, re, threading, math
from collections import defaultdict
from modules.config import CFG

log = logging.getLogger("agent")


class BracketEvent:
    """Represents one crypto bracket event (e.g., BTC price range at 8pm today).

    Contains 40-75 bracket markets that collectively span all possible
    price outcomes. Exactly one bracket will resolve YES.
    """

    def __init__(self, event_ticker, title="", close_time=""):
        self.event_ticker = event_ticker
        self.title = title
        self.close_time = close_time
        self.brackets = []  # list of bracket dicts
        self.last_updated = 0
        self._sorted = False

    def update_brackets(self, markets):
        """Update bracket list from API response.
        Each market dict should have: ticker, yes_bid, yes_ask, no_bid, no_ask,
        volume, subtitle (containing the price range text).
        """
        self.brackets = []
        for m in markets:
            ticker = m.get("ticker", "")
            subtitle = m.get("yes_sub_title", m.get("subtitle", ""))

            # Parse price range from subtitle like "$71,000 to 71,249.99"
            low, high = self._parse_range(subtitle)

            yes_bid = self._to_cents(m.get("yes_bid_dollars", m.get("yes_bid", 0)))
            yes_ask = self._to_cents(m.get("yes_ask_dollars", m.get("yes_ask", 0)))
            no_bid = self._to_cents(m.get("no_bid_dollars", m.get("no_bid", 0)))
            no_ask = self._to_cents(m.get("no_ask_dollars", m.get("no_ask", 0)))

            self.brackets.append({
                "ticker": ticker,
                "subtitle": subtitle,
                "range_low": low,
                "range_high": high,
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "no_bid": no_bid,
                "no_ask": no_ask,
                "spread": yes_ask - yes_bid if yes_ask > 0 and yes_bid > 0 else 99,
                "volume": float(m.get("volume", m.get("volume_fp", 0)) or 0),
            })

        self.brackets.sort(key=lambda b: b["range_low"] if b["range_low"] else 0)
        self._sorted = True
        self.last_updated = time.time()

    def sum_yes_asks(self):
        """Sum of all YES ask prices. Should be ~100c. >100 = short arb. <100 = long arb."""
        return sum(b["yes_ask"] for b in self.brackets if b["yes_ask"] > 0)

    def sum_yes_bids(self):
        """Sum of all YES bid prices. Should be ~100c."""
        return sum(b["yes_bid"] for b in self.brackets)

    def find_sum_arb(self, maker_fee_coeff=0.0175):
        """Check for sum-to-100 arbitrage opportunities.

        Long arb: if sum of YES asks < 100c (buy all brackets, guaranteed $1 payout)
        Short arb: if sum of YES bids > 100c (sell all brackets, pay out $1 max)

        Returns dict with arb details or None.
        """
        total_ask = self.sum_yes_asks()
        total_bid = self.sum_yes_bids()

        # Estimate total fees for buying/selling all brackets
        total_buy_fees = sum(
            maker_fee_coeff * (b["yes_ask"] / 100) * (1 - b["yes_ask"] / 100) * 100
            for b in self.brackets if b["yes_ask"] > 0
        )
        total_sell_fees = sum(
            maker_fee_coeff * (b["yes_bid"] / 100) * (1 - b["yes_bid"] / 100) * 100
            for b in self.brackets if b["yes_bid"] > 0
        )

        result = {"event": self.event_ticker, "n_brackets": len(self.brackets)}

        if total_ask + total_buy_fees < 100:
            result["long_arb"] = {
                "total_cost_cents": round(total_ask + total_buy_fees, 2),
                "profit_cents": round(100 - total_ask - total_buy_fees, 2),
                "type": "buy_all_brackets",
            }

        if total_bid - total_sell_fees > 100:
            result["short_arb"] = {
                "total_receive_cents": round(total_bid - total_sell_fees, 2),
                "profit_cents": round(total_bid - total_sell_fees - 100, 2),
                "type": "sell_all_brackets",
            }

        if "long_arb" in result or "short_arb" in result:
            return result
        return None

    def active_brackets(self, min_volume=0):
        """Return brackets with trading activity, sorted by proximity to current price."""
        active = [b for b in self.brackets
                  if b["volume"] >= min_volume and b["yes_ask"] > 0]
        # Sort by yes_ask descending (highest probability = closest to current price)
        active.sort(key=lambda b: b["yes_ask"], reverse=True)
        return active

    def _parse_range(self, subtitle):
        """Parse '$71,000 to 71,249.99' into (71000.0, 71249.99)."""
        if not subtitle:
            return None, None
        # Handle "X or above" and "X or below"
        if "or above" in subtitle.lower():
            nums = re.findall(r'[\d,]+\.?\d*', subtitle.replace(',', ''))
            return (float(nums[0]) if nums else None), None
        if "or below" in subtitle.lower():
            nums = re.findall(r'[\d,]+\.?\d*', subtitle.replace(',', ''))
            return None, (float(nums[0]) if nums else None)
        # Handle "X to Y"
        nums = re.findall(r'[\d,]+\.?\d*', subtitle.replace(',', ''))
        if len(nums) >= 2:
            return float(nums[0]), float(nums[1])
        return None, None

    @staticmethod
    def _to_cents(val):
        """Convert a price to cents. Dollar values (0 < v < 1) become cents."""
        try:
            v = float(val or 0)
            if 0 < v < 1.0:
                return int(round(v * 100))
            return int(round(v))
        except (ValueError, TypeError):
            return 0


class CryptoMarketDiscovery:
    """Discover and track active crypto bracket events on Kalshi."""

    SERIES = ["KXBTC", "KXBTCD", "KXETH", "KXSOL"]

    def __init__(self, api):
        self.api = api
        self.events = {}  # event_ticker -> BracketEvent
        self._lock = threading.Lock()

    def scan_active_events(self):
        """Fetch all open crypto bracket events.
        Returns list of BracketEvent objects.
        """
        discovered = []
        for series in self.SERIES:
            try:
                d = self.api._req("GET",
                    f"/events?series_ticker={series}&status=open&limit=10")
                for event_data in d.get("events", []):
                    et = event_data.get("event_ticker", "")
                    if not et:
                        continue

                    be = BracketEvent(
                        event_ticker=et,
                        title=event_data.get("title", ""),
                        close_time=event_data.get("close_time",
                                    event_data.get("expiration_time", "")),
                    )

                    # Fetch all markets for this event
                    md = self.api._req("GET",
                        f"/markets?event_ticker={et}&status=open&limit=200")
                    be.update_brackets(md.get("markets", []))

                    with self._lock:
                        self.events[et] = be
                    discovered.append(be)

                    log.info(f"  Crypto discovery: {et} -- {len(be.brackets)} brackets, "
                             f"sum_asks={be.sum_yes_asks()}c sum_bids={be.sum_yes_bids()}c")

            except Exception as e:
                log.debug(f"  Crypto discovery error for {series}: {e}")

        return discovered

    def get_event(self, event_ticker):
        with self._lock:
            return self.events.get(event_ticker)

    def get_all_active(self):
        with self._lock:
            return list(self.events.values())

    def get_mm_candidates(self, min_spread=3, min_volume=10):
        """Find brackets suitable for market making.
        Returns list of (event, bracket) tuples sorted by spread (widest first).
        """
        candidates = []
        with self._lock:
            for event in self.events.values():
                for bracket in event.brackets:
                    if bracket["spread"] >= min_spread and bracket["volume"] >= min_volume:
                        candidates.append((event, bracket))
        candidates.sort(key=lambda x: x[1]["spread"], reverse=True)
        return candidates


class BTCPriceFeed:
    """Fetch real-time BTC price from free public APIs as fair-value anchor.

    The market maker uses this to determine which bracket is closest to
    the current BTC price and set fair_value_cents for each bracket.
    """

    SOURCES = [
        ("binance", "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"),
        ("coinbase", "https://api.coinbase.com/v2/prices/BTC-USD/spot"),
    ]

    def __init__(self):
        self.price = None
        self.source = None
        self.last_updated = 0

    def fetch(self):
        """Fetch BTC price from multiple sources. Returns price in USD or None."""
        import requests

        for name, url in self.SOURCES:
            try:
                r = requests.get(url, timeout=5)
                r.raise_for_status()
                data = r.json()

                if name == "binance":
                    self.price = float(data["price"])
                elif name == "coinbase":
                    self.price = float(data["data"]["amount"])

                self.source = name
                self.last_updated = time.time()
                return self.price
            except Exception:
                continue

        log.warning("BTCPriceFeed: all sources failed")
        return self.price  # return last known price

    def bracket_fair_value(self, bracket, current_price=None):
        """Estimate fair value (in cents) for a bracket market given current BTC price.

        Uses a simple Gaussian probability model centered on current price.
        For the bracket containing the current price, fair value is ~30-50c.
        For brackets 1-2 brackets away, it decreases rapidly.

        Args:
            bracket: dict with range_low, range_high
            current_price: BTC price in USD (uses self.price if None)

        Returns:
            Estimated YES probability in cents (1-99)
        """
        price = current_price or self.price
        if price is None:
            return 50  # no data, assume 50/50

        low = bracket.get("range_low")
        high = bracket.get("range_high")

        if low is None and high is None:
            return 1  # can't estimate

        # Handle "X or above" / "X or below" edge brackets
        if high is None:  # "X or above"
            distance = (low - price) / price * 100 if low else 0
            return max(1, min(99, int(50 - distance * 10)))
        if low is None:  # "X or below"
            distance = (price - high) / price * 100 if high else 0
            return max(1, min(99, int(50 - distance * 10)))

        # Normal bracket: estimate probability that price lands in [low, high]
        # sigma = hourly BTC volatility (~0.7% of price)
        vol_pct = CFG.get("btc_volatility_pct", 0.7)
        sigma = price * vol_pct / 100

        # Probability of landing in bracket = CDF(high) - CDF(low)
        def normal_cdf(x, mu, s):
            return 0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2))))

        prob = normal_cdf(high, price, sigma) - normal_cdf(low, price, sigma)
        cents = max(1, min(99, int(round(prob * 100))))
        return cents
