"""Execution policy engine: decides HOW to trade, not WHAT to trade.

Separates the execution decision (maker vs taker vs no-trade) from
the signal decision (what market, which side, what probability).
"""
import time
from dataclasses import dataclass
from typing import Optional

from modules.config import CFG, log
from modules.precision import to_decimal, get_venue_fees, VenueFees
from modules.market_state import MARKET_STATE, BookState


@dataclass
class ExecutionPlan:
    """A plan for how to execute a trade."""
    action: str  # "taker", "maker", "no_trade"
    price_cents: int
    contracts: int
    platform: str
    side: str  # "yes" or "no"
    reason: str
    # Analytics
    estimated_fill_prob: float = 1.0
    estimated_slippage_cents: float = 0.0
    edge_after_fees_pct: float = 0.0
    urgency: str = "normal"  # "high" (near expiry), "normal", "low"


@dataclass
class PostTradeReport:
    """Post-trade execution analytics."""
    ticker: str
    decision_price: int  # price at time of decision
    order_price: int  # price we submitted
    fill_price: Optional[int]  # actual fill price (if known)
    slippage_cents: float  # order_price - decision_price
    fee_drag_pct: float  # total fees as % of contract cost
    edge_forecast: float  # predicted edge
    edge_captured: Optional[float]  # actual edge (if outcome known)


def assess_book_quality(book: Optional[BookState]) -> dict:
    """Evaluate order book quality for execution decisions."""
    if book is None or book.is_stale:
        return {
            "quality": "unknown",
            "spread": None,
            "depth_yes": 0,
            "depth_no": 0,
            "is_tradeable": False,
            "reason": "stale or missing book data",
        }

    spread = book.spread_cents
    yes_depth = sum(l.size for l in book.yes_bids[:3]) if book.yes_bids else 0
    no_depth = sum(l.size for l in book.no_bids[:3]) if book.no_bids else 0

    if spread is None:
        quality = "thin"
        tradeable = False
        reason = "no two-sided market"
    elif spread > 20:
        quality = "very_wide"
        tradeable = False
        reason = f"spread too wide ({spread}c)"
    elif spread > 10:
        quality = "wide"
        tradeable = True
        reason = f"wide spread ({spread}c) -- maker preferred"
    elif spread > 3:
        quality = "normal"
        tradeable = True
        reason = "normal spread"
    else:
        quality = "tight"
        tradeable = True
        reason = "tight spread -- taker OK"

    return {
        "quality": quality,
        "spread": spread,
        "depth_yes": yes_depth,
        "depth_no": no_depth,
        "microprice": book.microprice,
        "imbalance": book.imbalance,
        "is_tradeable": tradeable,
        "reason": reason,
    }


def build_execution_plan(
    ticker: str,
    side: str,
    probability: int,
    confidence: int,
    edge_pct: float,
    price_cents: int,
    contracts: int,
    hours_left: float,
    platform: str = "kalshi",
    book: Optional[BookState] = None,
) -> ExecutionPlan:
    """Build an execution plan based on market conditions.

    Decides between:
    - taker: aggressive entry when edge is time-sensitive or large
    - maker: passive entry when spread allows and edge is stable
    - no_trade: when execution quality would be too poor
    """
    fees = get_venue_fees(platform)
    book_quality = assess_book_quality(book)

    # Urgency assessment
    if hours_left <= 2:
        urgency = "high"
    elif hours_left <= 12:
        urgency = "normal"
    else:
        urgency = "low"

    # Check if book quality allows trading
    if not book_quality["is_tradeable"] and book is not None:
        return ExecutionPlan(
            action="no_trade", price_cents=price_cents, contracts=contracts,
            platform=platform, side=side,
            reason=f"Book quality too poor: {book_quality['reason']}",
            urgency=urgency,
        )

    # Calculate fee drag
    fee_drag_pct = float(fees.taker_fee * 2) / (price_cents / 100) * 100 if price_cents > 0 else 999

    # Edge after fees
    edge_after = abs(edge_pct) - fee_drag_pct

    if edge_after <= 0:
        return ExecutionPlan(
            action="no_trade", price_cents=price_cents, contracts=contracts,
            platform=platform, side=side,
            reason=f"Edge ({edge_pct:.1f}%) consumed by fees ({fee_drag_pct:.1f}%)",
            edge_after_fees_pct=edge_after, urgency=urgency,
        )

    # Decide taker vs maker
    spread = book_quality.get("spread")
    if spread is not None and spread > 5 and urgency != "high":
        # Wide spread + no urgency = place maker order inside the spread
        if side.lower() == "yes" and book and book.best_yes_bid is not None:
            maker_price = book.best_yes_bid + 1  # improve bid by 1c
        elif side.lower() == "no" and book and book.best_no_bid is not None:
            maker_price = book.best_no_bid + 1
        else:
            maker_price = price_cents

        return ExecutionPlan(
            action="maker", price_cents=min(maker_price, price_cents),
            contracts=contracts, platform=platform, side=side,
            reason=f"Maker order: spread={spread}c, improving bid by 1c",
            estimated_fill_prob=0.6,  # maker fills are uncertain
            edge_after_fees_pct=edge_after, urgency=urgency,
        )

    # Default: taker
    slippage_est = 0.0
    if book and contracts > 1:
        # Estimate slippage for multi-contract orders
        side_key = "yes_asks" if side.lower() == "yes" else "no_asks"
        asks = getattr(book, side_key, [])
        if asks and len(asks) > 1:
            total_size = sum(l.size for l in asks[:5])
            if total_size < contracts:
                slippage_est = 2.0  # rough estimate if we'd walk the book

    return ExecutionPlan(
        action="taker", price_cents=price_cents, contracts=contracts,
        platform=platform, side=side,
        reason=f"Taker entry: edge={edge_pct:.1f}% after_fees={edge_after:.1f}%",
        estimated_fill_prob=0.95, estimated_slippage_cents=slippage_est,
        edge_after_fees_pct=edge_after, urgency=urgency,
    )


class MakerOrderManager:
    """Manage resting maker orders: track, cancel stale, replace with better prices.

    When the execution engine decides on a 'maker' action, we place a limit order
    inside the spread. This manager tracks those orders and handles:
    1. Cancelling orders that have been resting too long without fill
    2. Replacing orders when the book moves (price improvement)
    3. Cancelling orders when edge disappears
    """

    def __init__(self, api):
        self.api = api
        self._orders: dict = {}  # order_id -> {ticker, side, price, contracts, placed_at, max_age_s}
        self._max_age_seconds = 300  # 5 minutes default

    def place_maker_order(self, ticker, side, contracts, price_cents, max_age_s=None):
        """Place a maker (limit) order and track it."""
        if CFG.get("dry_run", True):
            log.info(f"  MAKER DRY-RUN: {side} {contracts}x {ticker} @{price_cents}c")
            return None

        try:
            res = self.api.place_order(ticker, side, contracts, price_cents)
            order_id = res.get("order", {}).get("order_id", "")
            if order_id:
                self._orders[order_id] = {
                    "ticker": ticker,
                    "side": side,
                    "price": price_cents,
                    "contracts": contracts,
                    "placed_at": time.time(),
                    "max_age_s": max_age_s or self._max_age_seconds,
                }
                log.info(f"  MAKER PLACED: {side} {contracts}x {ticker} @{price_cents}c (id={order_id[:12]})")
            return order_id
        except Exception as e:
            log.error(f"  MAKER ORDER FAILED: {e}")
            return None

    def check_and_manage(self):
        """Check all tracked maker orders: cancel stale, update prices.

        Call this periodically (e.g., every scan cycle).
        """
        if not self._orders:
            return

        expired = []
        for order_id, info in list(self._orders.items()):
            age = time.time() - info["placed_at"]
            max_age = info["max_age_s"]

            if age > max_age:
                # Cancel stale order
                try:
                    self.api.cancel_order(order_id)
                    log.info(f"  MAKER CANCEL (stale): {info['ticker']} {info['side']} @{info['price']}c after {age:.0f}s")
                    expired.append(order_id)
                except Exception as e:
                    log.debug(f"  Cancel failed for {order_id}: {e}")
                    expired.append(order_id)  # Remove from tracking regardless
                continue

            # Check if book has moved and we should reprice
            book = MARKET_STATE.get_book_if_fresh(info["ticker"])
            if book:
                self._check_reprice(order_id, info, book)

        for oid in expired:
            self._orders.pop(oid, None)

    def _check_reprice(self, order_id, info, book):
        """Reprice a maker order if the book has moved significantly."""
        side = info["side"]
        current_price = info["price"]

        if side == "yes" and book.best_yes_bid is not None:
            # Our bid should be at or near best bid
            best_bid = book.best_yes_bid
            if current_price < best_bid - 2:
                # Book has moved up, we should improve our price
                new_price = best_bid + 1
                self._replace_order(order_id, info, new_price)
            elif current_price > best_bid + 5:
                # Book has moved down significantly, cancel (edge may be gone)
                try:
                    self.api.cancel_order(order_id)
                    log.info(f"  MAKER CANCEL (book moved): {info['ticker']} our={current_price}c best_bid={best_bid}c")
                    self._orders.pop(order_id, None)
                except Exception:
                    pass

        elif side == "no" and book.best_no_bid is not None:
            best_bid = book.best_no_bid
            if current_price < best_bid - 2:
                new_price = best_bid + 1
                self._replace_order(order_id, info, new_price)
            elif current_price > best_bid + 5:
                try:
                    self.api.cancel_order(order_id)
                    log.info(f"  MAKER CANCEL (book moved): {info['ticker']} our={current_price}c best_bid={best_bid}c")
                    self._orders.pop(order_id, None)
                except Exception:
                    pass

    def _replace_order(self, order_id, info, new_price):
        """Cancel and replace a maker order at a new price."""
        try:
            self.api.cancel_order(order_id)
            self._orders.pop(order_id, None)

            new_id = self.place_maker_order(
                info["ticker"], info["side"], info["contracts"],
                new_price, info["max_age_s"])
            if new_id:
                log.info(f"  MAKER REPRICED: {info['ticker']} {info['price']}c -> {new_price}c")
        except Exception as e:
            log.debug(f"  Maker replace failed: {e}")

    def cancel_all(self, ticker=None):
        """Cancel all tracked maker orders, optionally for a specific ticker."""
        for order_id, info in list(self._orders.items()):
            if ticker and info["ticker"] != ticker:
                continue
            try:
                self.api.cancel_order(order_id)
                log.info(f"  MAKER CANCEL: {info['ticker']} @{info['price']}c")
            except Exception:
                pass
            self._orders.pop(order_id, None)

    @property
    def active_orders(self) -> dict:
        return dict(self._orders)


def should_quickflip(market, features=None) -> tuple:
    """Evaluate whether a quick-flip entry is justified.

    Quick-flips should be CONSTRAINED, not default. Only allowed when:
    1. There is concrete evidence of upcoming catalyst
    2. Spread is tight enough for profitable exit
    3. Volume is sufficient for reliable exit
    """
    if not CFG.get("quickflip_enabled", False):
        return False, "quickflip disabled"

    vol = market.get("volume", 0) or 0
    if vol < 50:
        return False, f"insufficient volume ({vol} < 50)"

    price = market.get("display_price") or market.get("yes_bid") or market.get("last_price") or 50
    if price < CFG.get("quickflip_min_price", 3) or price > CFG.get("quickflip_max_price", 15):
        return False, f"price {price}c outside QF range"

    hrs = market.get("_hrs_left", 9999)
    if hrs > 48:
        return False, "too far from expiry for QF"

    # Check book state for exit feasibility
    tk = market.get("ticker", "")
    book = MARKET_STATE.get_book(tk)
    if book and book.spread_cents and book.spread_cents > 8:
        return False, f"spread too wide for profitable exit ({book.spread_cents}c)"

    return True, "OK"
