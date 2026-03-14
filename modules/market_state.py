"""In-memory market state store with staleness tracking and book state.

Provides a normalized view of order book state for scanner, execution,
arbitrage, and dashboard consumers. Designed to support both REST polling
(current) and future websocket feeds.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from modules.config import log


@dataclass
class BookLevel:
    """A single price level in the order book."""
    price_cents: int
    size: int


@dataclass
class BookState:
    """Snapshot of an order book for one market."""
    ticker: str
    yes_bids: list = field(default_factory=list)  # list of BookLevel, sorted best-first
    yes_asks: list = field(default_factory=list)
    no_bids: list = field(default_factory=list)
    no_asks: list = field(default_factory=list)
    timestamp: float = 0.0  # time.time() when fetched
    source: str = "rest"  # "rest" or "ws"

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp if self.timestamp > 0 else float("inf")

    @property
    def is_stale(self) -> bool:
        """Book data older than 60s from REST is considered stale."""
        max_age = 30 if self.source == "ws" else 60
        return self.age_seconds > max_age

    @property
    def best_yes_bid(self) -> Optional[int]:
        return self.yes_bids[0].price_cents if self.yes_bids else None

    @property
    def best_yes_ask(self) -> Optional[int]:
        return self.yes_asks[0].price_cents if self.yes_asks else None

    @property
    def best_no_bid(self) -> Optional[int]:
        return self.no_bids[0].price_cents if self.no_bids else None

    @property
    def best_no_ask(self) -> Optional[int]:
        return self.no_asks[0].price_cents if self.no_asks else None

    @property
    def spread_cents(self) -> Optional[int]:
        """Yes-side spread (ask - bid). None if either side is missing."""
        if self.best_yes_bid is not None and self.best_yes_ask is not None:
            return self.best_yes_ask - self.best_yes_bid
        return None

    @property
    def microprice(self) -> Optional[float]:
        """Volume-weighted microprice from top of book.
        Better estimate of 'true' price than mid when books are imbalanced."""
        if not self.yes_bids or not self.yes_asks:
            return None
        bid_p = self.yes_bids[0].price_cents
        bid_s = self.yes_bids[0].size
        ask_p = self.yes_asks[0].price_cents
        ask_s = self.yes_asks[0].size
        total_size = bid_s + ask_s
        if total_size == 0:
            return (bid_p + ask_p) / 2.0
        return (bid_p * ask_s + ask_p * bid_s) / total_size

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_yes_bid is not None and self.best_yes_ask is not None:
            return (self.best_yes_bid + self.best_yes_ask) / 2.0
        return None

    @property
    def imbalance(self) -> Optional[float]:
        """Order book imbalance at top of book. Positive = more bid pressure."""
        if not self.yes_bids or not self.yes_asks:
            return None
        bid_s = self.yes_bids[0].size
        ask_s = self.yes_asks[0].size
        total = bid_s + ask_s
        if total == 0:
            return 0.0
        return (bid_s - ask_s) / total


def _parse_book_side(raw_levels) -> list:
    """Parse raw API book levels into BookLevel objects."""
    levels = []
    for entry in (raw_levels or []):
        try:
            if isinstance(entry, (list, tuple)):
                price = float(entry[0])
                size = int(float(entry[1])) if len(entry) > 1 else 1
            elif isinstance(entry, dict):
                price = float(entry.get("price", 0))
                size = int(float(entry.get("size", entry.get("quantity", 0))))
            else:
                continue
            # Normalize: if price < 1, it's in dollars -> convert to cents
            if 0 < price < 1:
                price = round(price * 100)
            else:
                price = round(price)
            price = int(price)
            if 1 <= price <= 99 and size > 0:
                levels.append(BookLevel(price_cents=price, size=size))
        except (ValueError, TypeError, IndexError):
            continue
    return levels


class MarketStateStore:
    """Thread-safe in-memory store for market book state."""

    def __init__(self):
        self._books: dict[str, BookState] = {}
        self._lock = threading.RLock()
        self._feed_health = {
            "kalshi": {"last_update": 0, "errors": 0, "status": "unknown"},
            "polymarket": {"last_update": 0, "errors": 0, "status": "unknown"},
        }

    def update_book(self, ticker: str, raw_orderbook: dict, source: str = "rest") -> BookState:
        """Update book state from a raw API orderbook response."""
        book_data = raw_orderbook.get("orderbook", raw_orderbook)

        # Parse Kalshi-style books (yes/no arrays)
        yes_bids = _parse_book_side(book_data.get("yes", book_data.get("yes_dollars", [])))
        no_bids = _parse_book_side(book_data.get("no", book_data.get("no_dollars", [])))

        # For Kalshi: yes bids = buy YES (sorted high to low = best first)
        # yes asks = derived from NO bids (buy NO at X = sell YES at 100-X)
        yes_asks = []
        for nb in no_bids:
            implied_ask = 100 - nb.price_cents
            if 1 <= implied_ask <= 99:
                yes_asks.append(BookLevel(price_cents=implied_ask, size=nb.size))

        # Sort: bids high-to-low (best first), asks low-to-high (best first)
        yes_bids.sort(key=lambda x: x.price_cents, reverse=True)
        yes_asks.sort(key=lambda x: x.price_cents)
        no_bids.sort(key=lambda x: x.price_cents, reverse=True)

        # Derive NO asks from YES bids
        no_asks = []
        for yb in yes_bids:
            implied = 100 - yb.price_cents
            if 1 <= implied <= 99:
                no_asks.append(BookLevel(price_cents=implied, size=yb.size))
        no_asks.sort(key=lambda x: x.price_cents)

        state = BookState(
            ticker=ticker,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
            no_bids=no_bids,
            no_asks=no_asks,
            timestamp=time.time(),
            source=source,
        )

        with self._lock:
            self._books[ticker] = state

        return state

    def get_book(self, ticker: str) -> Optional[BookState]:
        with self._lock:
            return self._books.get(ticker)

    def get_book_if_fresh(self, ticker: str) -> Optional[BookState]:
        """Return book state only if it's not stale."""
        book = self.get_book(ticker)
        if book and not book.is_stale:
            return book
        return None

    def record_feed_error(self, venue: str):
        with self._lock:
            if venue in self._feed_health:
                self._feed_health[venue]["errors"] += 1
                self._feed_health[venue]["status"] = "degraded"

    def record_feed_success(self, venue: str):
        with self._lock:
            if venue in self._feed_health:
                self._feed_health[venue]["last_update"] = time.time()
                self._feed_health[venue]["errors"] = 0
                self._feed_health[venue]["status"] = "healthy"

    def feed_status(self) -> dict:
        with self._lock:
            result = {}
            for venue, health in self._feed_health.items():
                age = time.time() - health["last_update"] if health["last_update"] > 0 else float("inf")
                result[venue] = {
                    "status": health["status"],
                    "age_seconds": round(age, 1),
                    "errors": health["errors"],
                }
            return result

    def stale_tickers(self) -> list:
        """Return tickers with stale book data."""
        with self._lock:
            return [t for t, b in self._books.items() if b.is_stale]

    def clear(self):
        with self._lock:
            self._books.clear()


# Global singleton
MARKET_STATE = MarketStateStore()
