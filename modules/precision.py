"""Fixed-point precision utilities for money, price, and fee calculations.

All prices are internally stored as Decimal cents (e.g., 67.50 = 67.50 cents).
This avoids float rounding errors in execution-critical math.
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP, InvalidOperation

# Standard precision context
PRICE_PLACES = Decimal("0.01")    # 2 decimal places for subpenny prices
MONEY_PLACES = Decimal("0.0001")  # 4 decimal places for money/PnL
PCT_PLACES = Decimal("0.01")      # 2 decimal places for percentages


def to_decimal(value, default=Decimal("0")) -> Decimal:
    """Safely convert any value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    try:
        s = str(value).replace("$", "").replace(",", "").strip()
        if not s:
            return default
        return Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return default


def dollars_to_cents(dollar_value) -> Decimal:
    """Convert a dollar amount (possibly string like '0.6700') to cents."""
    d = to_decimal(dollar_value)
    return (d * 100).quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)


def cents_to_dollars(cents_value) -> Decimal:
    """Convert cents to dollars."""
    d = to_decimal(cents_value)
    return (d / 100).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def round_price_cents(price_cents, tick_size=Decimal("1")) -> int:
    """Round a price to the nearest valid tick (default: whole cents).

    Kalshi uses whole-cent ticks. Polymarket uses 0.01 (1 cent) ticks too.
    Returns int for backward compat with existing code that expects int cents.
    """
    d = to_decimal(price_cents)
    rounded = (d / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_size
    return int(rounded)


def net_edge_cents(probability_pct, price_cents, fee_per_contract, side="YES") -> Decimal:
    """Calculate net edge in cents after fees on both entry and exit.

    Args:
        probability_pct: Our estimated probability (0-100)
        price_cents: Market price in cents
        fee_per_contract: Fee per contract in dollars (e.g., 0.07)
        side: YES or NO
    """
    prob = to_decimal(probability_pct) / 100
    price = to_decimal(price_cents) / 100  # Convert to dollars
    fee = to_decimal(fee_per_contract)

    if side.upper() == "YES":
        # If YES resolves: we get $1.00, paid price + 2x fee (entry + exit)
        ev_win = (Decimal("1") - price - fee * 2) * prob
        ev_lose = (price + fee) * (1 - prob)  # lose entry cost + entry fee (no exit needed)
        raw_edge = ev_win - ev_lose
    else:
        # If NO resolves: same math with inverted price
        no_price = (Decimal("100") - to_decimal(price_cents)) / 100
        ev_win = (Decimal("1") - no_price - fee * 2) * (1 - prob)
        ev_lose = (no_price + fee) * prob
        raw_edge = ev_win - ev_lose

    return (raw_edge * 100).quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)


class VenueFees:
    """Per-venue fee model."""

    def __init__(self, taker_fee=Decimal("0.07"), maker_rebate=Decimal("0"), name="kalshi"):
        self.taker_fee = to_decimal(taker_fee)
        self.maker_rebate = to_decimal(maker_rebate)
        self.name = name

    def taker_cost(self, contracts=1) -> Decimal:
        """Total taker fee for N contracts (entry only)."""
        return self.taker_fee * contracts

    def round_trip_cost(self, contracts=1) -> Decimal:
        """Total fees for entry + exit as taker."""
        return self.taker_fee * contracts * 2

    def net_pnl(self, entry_cents, exit_cents, contracts, is_maker_exit=False) -> Decimal:
        """Calculate net PnL in dollars after fees."""
        entry = to_decimal(entry_cents) / 100
        exit_price = to_decimal(exit_cents) / 100
        gross = (exit_price - entry) * contracts
        entry_fee = self.taker_fee * contracts
        exit_fee = (-self.maker_rebate if is_maker_exit else self.taker_fee) * contracts
        return (gross - entry_fee - exit_fee).quantize(MONEY_PLACES)


# Pre-configured venue fee instances
KALSHI_FEES = VenueFees(taker_fee=Decimal("0.07"), maker_rebate=Decimal("0"), name="kalshi")
POLYMARKET_FEES = VenueFees(taker_fee=Decimal("0.02"), maker_rebate=Decimal("0"), name="polymarket")


def get_venue_fees(platform="kalshi") -> VenueFees:
    """Get fee model for a venue."""
    if platform.lower() == "polymarket":
        return POLYMARKET_FEES
    return KALSHI_FEES
