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
