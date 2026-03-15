"""WebSocket feed for real-time Kalshi orderbook updates.

Connects to Kalshi's WebSocket API, subscribes to orderbook_delta channel,
and pushes updates into MarketStateStore for fresher data than REST polling.
"""
import json
import time
import base64
import threading
import asyncio
from typing import Optional

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

from modules.config import CFG, log
from modules.market_state import MARKET_STATE, BookLevel


WS_URLS = {
    "prod": "wss://api.elections.kalshi.com/trade-api/ws/v2",
    "demo": "wss://demo-api.kalshi.co/trade-api/ws/v2",
}


class KalshiWSFeed:
    """Real-time orderbook feed via Kalshi WebSocket API.

    Usage:
        feed = KalshiWSFeed()
        feed.start(tickers=["TICKER-1", "TICKER-2"])
        # ... later ...
        feed.stop()
    """

    def __init__(self):
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._subscribed_tickers: set = set()
        self._msg_id = 0
        self._books: dict = {}  # ticker -> {yes: {price_str: count}, no: {price_str: count}}
        self._connected = False
        self._arb_callback = None  # callable(ticker, book_state) for real-time arb detection

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_ws_url(self) -> str:
        env = CFG.get("environment", "demo")
        return WS_URLS.get(env, WS_URLS["demo"])

    def _auth_headers(self):
        """Build authentication headers for WebSocket handshake."""
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        import os

        key_id = CFG.get("kalshi_api_key_id", "")
        key_path = CFG.get("kalshi_private_key_path", "")
        if not key_id or not key_path:
            return {}

        if not os.path.isabs(key_path):
            key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", key_path)

        try:
            with open(key_path, "rb") as f:
                pk = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

            ts = str(int(time.time() * 1000))
            method = "GET"
            path = "/trade-api/ws/v2"
            msg = f"{ts}{method}{path}".encode()
            sig = pk.sign(msg, padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ), hashes.SHA256())

            return {
                "KALSHI-ACCESS-KEY": key_id,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
                "KALSHI-ACCESS-TIMESTAMP": ts,
            }
        except Exception as e:
            log.warning(f"WS auth header generation failed: {e}")
            return {}

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def _connect_and_listen(self, tickers: list):
        """Main async loop: connect, subscribe, process messages."""
        url = self._get_ws_url()
        headers = self._auth_headers()
        if not headers:
            log.warning("WS feed: no auth credentials, cannot connect")
            return

        reconnect_delay = 2
        max_reconnect_delay = 60

        while not self._stop_event.is_set():
            try:
                log.info(f"WS feed: connecting to {url}...")
                async with websockets.connect(url, additional_headers=headers,
                                               ping_interval=30, ping_timeout=10) as ws:
                    self._ws = ws
                    self._connected = True
                    reconnect_delay = 2
                    log.info(f"WS feed: connected, subscribing to {len(tickers)} tickers")

                    # Subscribe to orderbook_delta for each ticker
                    for tk in tickers:
                        await self._subscribe(ws, tk)
                        self._subscribed_tickers.add(tk)

                    # Process messages
                    async for raw_msg in ws:
                        if self._stop_event.is_set():
                            break
                        try:
                            msg = json.loads(raw_msg)
                            self._handle_message(msg)
                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                self._connected = False
                MARKET_STATE.record_feed_error("kalshi")
                if self._stop_event.is_set():
                    break
                log.warning(f"WS feed disconnected: {e} -- reconnecting in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

        self._connected = False

    async def _subscribe(self, ws, ticker: str):
        """Subscribe to orderbook_delta for a single ticker."""
        msg = {
            "id": self._next_id(),
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_ticker": ticker,
            }
        }
        await ws.send(json.dumps(msg))

    async def _subscribe_new(self, ticker: str):
        """Subscribe to a new ticker on existing connection."""
        if self._ws and self._connected:
            await self._subscribe(self._ws, ticker)
            self._subscribed_tickers.add(ticker)

    def _handle_message(self, msg: dict):
        """Process incoming WebSocket messages."""
        msg_type = msg.get("type", "")

        if msg_type == "orderbook_snapshot":
            self._handle_snapshot(msg)
        elif msg_type == "orderbook_delta":
            self._handle_delta(msg)
        elif msg_type == "error":
            log.warning(f"WS error: {msg.get('msg', msg)}")
        # Ignore subscription confirmations, heartbeats, etc.

    def _handle_snapshot(self, msg: dict):
        """Process full orderbook snapshot."""
        ticker = msg.get("msg", {}).get("market_ticker", "")
        if not ticker:
            return

        yes_levels = msg.get("msg", {}).get("yes", [])
        no_levels = msg.get("msg", {}).get("no", [])

        # Build internal book state
        self._books[ticker] = {"yes": {}, "no": {}}
        for level in (yes_levels or []):
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price_str, count_str = str(level[0]), str(level[1])
                self._books[ticker]["yes"][price_str] = float(count_str)

        for level in (no_levels or []):
            if isinstance(level, (list, tuple)) and len(level) >= 2:
                price_str, count_str = str(level[0]), str(level[1])
                self._books[ticker]["no"][price_str] = float(count_str)

        self._push_to_market_state(ticker)

    def _handle_delta(self, msg: dict):
        """Process incremental orderbook update."""
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")
        if not ticker or ticker not in self._books:
            return

        price = str(data.get("price", data.get("price_dollars", "")))
        delta = float(data.get("delta", data.get("delta_fp", 0)))
        side = data.get("side", "")

        if side not in ("yes", "no") or not price:
            return

        book_side = self._books[ticker][side]
        current = book_side.get(price, 0)
        new_count = current + delta

        if new_count <= 0:
            book_side.pop(price, None)
        else:
            book_side[price] = new_count

        self._push_to_market_state(ticker)

    def set_arb_callback(self, callback):
        """Set a callback function for real-time arb detection on every book update.

        The callback signature is: callback(ticker, book_state) where book_state
        is the BookState object from MARKET_STATE after the update.
        """
        self._arb_callback = callback

    def _push_to_market_state(self, ticker: str):
        """Convert internal book to MARKET_STATE format."""
        if ticker not in self._books:
            return

        book = self._books[ticker]

        # Build raw orderbook format compatible with MARKET_STATE.update_book
        yes_levels = []
        for price_str, count in book["yes"].items():
            try:
                price = float(price_str)
                if count > 0:
                    yes_levels.append({"price": price, "size": int(count)})
            except ValueError:
                continue

        no_levels = []
        for price_str, count in book["no"].items():
            try:
                price = float(price_str)
                if count > 0:
                    no_levels.append({"price": price, "size": int(count)})
            except ValueError:
                continue

        raw = {"yes": yes_levels, "no": no_levels}
        book_state = MARKET_STATE.update_book(ticker, raw, source="ws")
        MARKET_STATE.record_feed_success("kalshi")

        # Fire arb callback on every book update
        if self._arb_callback and book_state:
            try:
                self._arb_callback(ticker, book_state)
            except Exception:
                pass  # Never let callback errors kill the WS feed

    def start(self, tickers: list):
        """Start WebSocket feed in background thread."""
        if not HAS_WEBSOCKETS:
            log.warning("WS feed: websockets library not installed, skipping")
            return
        if not tickers:
            return
        if self._thread and self._thread.is_alive():
            log.warning("WS feed: already running")
            return

        self._stop_event.clear()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._connect_and_listen(tickers))
            except Exception as e:
                log.error(f"WS feed thread error: {e}")
            finally:
                loop.close()

        self._thread = threading.Thread(target=_run, daemon=True, name="ws-feed")
        self._thread.start()
        log.info(f"WS feed: started for {len(tickers)} tickers")

    def stop(self):
        """Stop the WebSocket feed."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._connected = False
        log.info("WS feed: stopped")

    def add_ticker(self, ticker: str):
        """Subscribe to a new ticker on existing connection."""
        if ticker in self._subscribed_tickers:
            return
        if self._connected and self._ws:
            # Schedule subscription on the event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._subscribe_new(ticker), loop)
            except Exception:
                pass  # Will be picked up on next reconnect
