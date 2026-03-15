"""
Market maker engine for Kalshi bracket markets.

Places two-sided quotes (bid YES + bid NO) on selected markets,
captures the bid-ask spread, and manages inventory risk.

This module uses ZERO AI. Revenue comes from spread capture, not prediction.

Key concepts:
- Quote: a resting limit order on one side of a market
- Spread capture: buying YES at 47c and selling at 52c = 5c profit
- Inventory: net position (positive = long YES, negative = long NO)
- Skew: shifting quotes to reduce inventory risk
"""
import time, logging, threading, uuid
from collections import defaultdict
from modules.config import CFG

log = logging.getLogger("agent")


class Quote:
    """Represents one resting order managed by the market maker."""

    def __init__(self, ticker, side, price_cents, size, order_id=None):
        self.ticker = ticker
        self.side = side  # "yes" or "no"
        self.price_cents = price_cents
        self.size = size
        self.order_id = order_id
        self.placed_at = time.time()
        self.status = "pending"  # pending, resting, filled, cancelled


class MarketMaker:
    """Two-sided quote engine with inventory management.

    For each target market, maintains a YES bid and a NO bid.
    The NO bid at price X is economically equivalent to a YES ask at (100-X).

    Example:
        YES bid at 47c + NO bid at 48c
        = willing to buy YES at 47c, sell YES at 52c (100-48)
        = 5c spread

    Inventory management:
        If we accumulate too much YES inventory, we skew:
        - Lower the YES bid (less eager to buy more YES)
        - Lower the NO bid (more eager to sell YES / buy NO)
        This naturally reduces inventory over time.
    """

    def __init__(self, api):
        self.api = api
        self._quotes = {}  # ticker -> {"yes": Quote, "no": Quote}
        self._inventory = defaultdict(int)  # ticker -> net YES contracts
        self._fills = []  # history of fills for P&L tracking
        self._lock = threading.Lock()
        self._active = False
        self._total_spread_captured = 0.0

    def start(self):
        """Enable market making."""
        self._active = True
        log.info("Market maker: ACTIVE")

    def stop(self):
        """Disable market making and cancel all resting orders."""
        self._active = False
        self.cancel_all()
        log.info("Market maker: STOPPED")

    def is_active(self):
        return self._active

    def quote_market(self, ticker, fair_value_cents, spread_cents=None,
                     size=None, event_ticker=None):
        """Place or update two-sided quotes on a market.

        Args:
            ticker: market ticker (e.g., KXBTC-26MAR1420-B71000)
            fair_value_cents: estimated fair YES price (e.g., 45 for 45c)
            spread_cents: total spread width (default from config)
            size: contracts per side (default from config)
            event_ticker: parent event for grouping
        """
        if not self._active:
            return

        spread = spread_cents or CFG.get("mm_default_spread_cents", 4)
        quote_size = size or CFG.get("mm_default_quote_size", 5)

        # Calculate quote prices
        half_spread = spread // 2
        yes_bid = max(1, fair_value_cents - half_spread)
        no_bid = max(1, 100 - fair_value_cents - half_spread)

        # Apply inventory skew
        inv = self._inventory.get(ticker, 0)
        skew_per_contract = CFG.get("mm_inventory_skew_cents", 1)
        max_skew = spread // 2  # never skew more than half the spread

        if inv > 0:
            # Long YES inventory -- make YES cheaper, NO more attractive
            skew = min(inv * skew_per_contract, max_skew)
            yes_bid = max(1, yes_bid - skew)
            no_bid = max(1, no_bid - skew)
        elif inv < 0:
            # Long NO inventory -- make NO cheaper, YES more attractive
            skew = min(abs(inv) * skew_per_contract, max_skew)
            yes_bid = min(99, yes_bid + skew)
            no_bid = min(99, no_bid + skew)

        # Check inventory limits
        max_inventory = CFG.get("mm_max_inventory_per_market", 20)
        quote_size_yes = quote_size
        quote_size_no = quote_size
        if abs(inv) >= max_inventory:
            log.info(f"  MM {ticker}: inventory limit reached ({inv}), "
                     f"only quoting reduction side")
            if inv > 0:
                quote_size_yes = 0  # don't buy more YES
            else:
                quote_size_no = 0  # don't buy more NO

        # Place or amend orders
        dry_run = CFG.get("dry_run", True)

        with self._lock:
            existing = self._quotes.get(ticker, {})

            # YES bid
            if quote_size_yes > 0:
                self._place_or_amend(
                    ticker, "yes", yes_bid, quote_size_yes,
                    existing.get("yes"), dry_run)

            # NO bid
            if quote_size_no > 0:
                self._place_or_amend(
                    ticker, "no", no_bid, quote_size_no,
                    existing.get("no"), dry_run)

    def _place_or_amend(self, ticker, side, price, size, existing_quote, dry_run):
        """Place a new order or amend an existing resting order."""
        if existing_quote and existing_quote.status == "resting":
            # Amend if price changed
            if existing_quote.price_cents != price:
                if dry_run:
                    log.info(f"  MM [DRY] amend {ticker} {side} "
                             f"{existing_quote.price_cents}c -> {price}c x{size}")
                else:
                    try:
                        self.api.amend_order(existing_quote.order_id,
                                            new_price_cents=price, new_count=size)
                        existing_quote.price_cents = price
                        existing_quote.size = size
                    except Exception as e:
                        log.error(f"  MM amend failed {ticker} {side}: {e}")
                        self._cancel_quote(existing_quote)
                        existing_quote = None

        if not existing_quote or existing_quote.status != "resting":
            # Place new order
            if dry_run:
                log.info(f"  MM [DRY] place {ticker} {side} {price}c x{size}")
                q = Quote(ticker, side, price, size,
                          order_id=f"dry-{uuid.uuid4().hex[:8]}")
                q.status = "resting"
            else:
                try:
                    result = self.api.place_order(ticker, side, size, price)
                    order_id = result.get("order", {}).get("order_id", "")
                    q = Quote(ticker, side, price, size, order_id=order_id)
                    q.status = "resting"
                    log.info(f"  MM placed {ticker} {side} {price}c x{size} "
                             f"id={order_id}")
                except Exception as e:
                    log.error(f"  MM place failed {ticker} {side} {price}c: {e}")
                    return

            if ticker not in self._quotes:
                self._quotes[ticker] = {}
            self._quotes[ticker][side] = q

    def _cancel_quote(self, quote):
        """Cancel a single quote."""
        if quote and quote.status == "resting" and quote.order_id:
            try:
                if not quote.order_id.startswith("dry-"):
                    self.api.cancel_order(quote.order_id)
                quote.status = "cancelled"
            except Exception as e:
                log.error(f"  MM cancel failed {quote.order_id}: {e}")

    def record_fill(self, ticker, side, price_cents, size):
        """Record a fill (called when order execution is confirmed).
        Updates inventory and tracks P&L.
        """
        with self._lock:
            if side == "yes":
                self._inventory[ticker] += size
            else:
                self._inventory[ticker] -= size

            self._fills.append({
                "ticker": ticker,
                "side": side,
                "price_cents": price_cents,
                "size": size,
                "time": time.time(),
            })

            inv = self._inventory[ticker]
            log.info(f"  MM FILL: {ticker} {side} {price_cents}c x{size} "
                     f"| inventory now: {inv}")

    def cancel_all(self):
        """KILL SWITCH -- cancel all resting orders immediately."""
        cancelled = 0
        with self._lock:
            for ticker, sides in self._quotes.items():
                for side, quote in sides.items():
                    if quote.status == "resting" and quote.order_id:
                        try:
                            if not quote.order_id.startswith("dry-"):
                                self.api.cancel_order(quote.order_id)
                            quote.status = "cancelled"
                            cancelled += 1
                        except Exception as e:
                            log.error(f"  MM cancel failed {quote.order_id}: {e}")
            self._quotes.clear()
        log.info(f"  MM KILL SWITCH: cancelled {cancelled} orders")
        return cancelled

    def cancel_market(self, ticker):
        """Cancel all quotes on a specific market."""
        with self._lock:
            sides = self._quotes.get(ticker, {})
            for side, quote in sides.items():
                if quote.status == "resting" and quote.order_id:
                    try:
                        if not quote.order_id.startswith("dry-"):
                            self.api.cancel_order(quote.order_id)
                        quote.status = "cancelled"
                    except Exception:
                        pass
            self._quotes.pop(ticker, None)

    def get_inventory(self):
        """Return current inventory across all markets."""
        with self._lock:
            return dict(self._inventory)

    def get_total_exposure(self):
        """Total absolute exposure in contracts."""
        with self._lock:
            return sum(abs(v) for v in self._inventory.values())

    def check_fills(self):
        """Poll the API for filled orders and update inventory.

        Checks all resting quotes to see if they've been filled.
        Returns list of newly detected fills.
        """
        new_fills = []
        dry_run = CFG.get("dry_run", True)

        with self._lock:
            for ticker, sides in list(self._quotes.items()):
                for side, quote in list(sides.items()):
                    if quote.status != "resting" or not quote.order_id:
                        continue
                    if quote.order_id.startswith("dry-"):
                        continue  # can't check dry-run orders

                    try:
                        order = self.api.get_order(quote.order_id)
                        status = order.get("order", {}).get("status", "")
                        remaining = order.get("order", {}).get("remaining_count", quote.size)

                        filled_count = quote.size - remaining

                        if filled_count > 0 and quote.status == "resting":
                            # Record the fill
                            fill = {
                                "ticker": ticker,
                                "side": side,
                                "price_cents": quote.price_cents,
                                "size": filled_count,
                                "time": time.time(),
                                "order_id": quote.order_id,
                            }
                            self._fills.append(fill)
                            new_fills.append(fill)

                            # Update inventory
                            if side == "yes":
                                self._inventory[ticker] += filled_count
                            else:
                                self._inventory[ticker] -= filled_count

                            log.info(f"  MM FILL DETECTED: {ticker} {side} "
                                     f"{quote.price_cents}c x{filled_count} "
                                     f"| inventory now: {self._inventory[ticker]}")

                        if status in ("filled", "canceled", "cancelled"):
                            quote.status = "filled" if status == "filled" else "cancelled"

                    except Exception as e:
                        log.debug(f"  MM fill check failed for {quote.order_id}: {e}")

        return new_fills

    def summary(self):
        """Return market maker status summary for dashboard."""
        with self._lock:
            active_quotes = sum(1 for t in self._quotes.values()
                              for q in t.values() if q.status == "resting")
            markets_quoted = len(self._quotes)
            total_fills = len(self._fills)
            net_inventory = sum(self._inventory.values())

            return {
                "active": self._active,
                "markets_quoted": markets_quoted,
                "active_quotes": active_quotes,
                "total_fills": total_fills,
                "net_inventory": net_inventory,
                "inventory_by_market": dict(self._inventory),
                "total_spread_captured": round(self._total_spread_captured, 2),
            }
