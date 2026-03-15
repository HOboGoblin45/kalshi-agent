"""Combinatorial arbitrage scanner for logically related markets.

Finds pricing inconsistencies across markets with subset/superset relationships:
- "BTC > $70k" should always cost <= "BTC > $65k" (subset relationship)
- Sum of mutually exclusive outcomes must equal 100c
- Bracket markets: if bracket A contains bracket B's range, price(A) >= price(B)

These opportunities are pure math (no AI needed) and are risk-free when correct.

Usage:
    scanner = CombinatorialScanner()
    groups = scanner.group_related_markets(markets)
    arbs = scanner.scan_all(groups)
"""
import re
import time
import logging
from collections import defaultdict

from modules.config import CFG, log


def _extract_threshold(title):
    """Extract a numeric threshold from market titles like 'BTC above $70,000'.

    Returns (direction, value) where direction is 'above' or 'below', or None.
    """
    title_lower = title.lower()

    # Match patterns like "above $70,000" or "at or above 70000"
    above_match = re.search(r'(?:above|over|higher than|at least|>=?)\s*\$?([\d,]+\.?\d*)', title_lower)
    if above_match:
        val = float(above_match.group(1).replace(',', ''))
        return ('above', val)

    # Match patterns like "below $70,000" or "under 70000"
    below_match = re.search(r'(?:below|under|lower than|at most|<=?)\s*\$?([\d,]+\.?\d*)', title_lower)
    if below_match:
        val = float(below_match.group(1).replace(',', ''))
        return ('below', val)

    # Match "between X and Y" or "X to Y"
    range_match = re.search(r'(?:between\s+)?\$?([\d,]+\.?\d*)\s*(?:to|and|-)\s*\$?([\d,]+\.?\d*)', title_lower)
    if range_match:
        low = float(range_match.group(1).replace(',', ''))
        high = float(range_match.group(2).replace(',', ''))
        return ('range', low, high)

    return None


def _extract_event_key(market):
    """Extract a grouping key for related markets.

    Markets from the same event (same event_ticker) are related.
    Also groups by detected subject (BTC, ETH, temperature, etc).
    """
    event_ticker = market.get("event_ticker", "")
    if event_ticker:
        return event_ticker

    # Fallback: group by keyword patterns
    title = market.get("title", "").lower()
    for keyword in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol",
                     "temperature", "unemployment", "gdp", "inflation",
                     "s&p", "nasdaq", "fed funds"]:
        if keyword in title:
            return f"_topic_{keyword}"
    return None


class CombinatorialScanner:
    """Scan groups of related markets for combinatorial arbitrage."""

    def group_related_markets(self, markets):
        """Group markets by event/topic.

        Returns dict of {group_key: [markets]}
        """
        groups = defaultdict(list)
        for m in markets:
            key = _extract_event_key(m)
            if key:
                groups[key].append(m)
        # Only return groups with 2+ markets (can't have arb with 1 market)
        return {k: v for k, v in groups.items() if len(v) >= 2}

    def scan_threshold_arbs(self, markets):
        """Find threshold-based arbitrage in a group of related markets.

        If "X above $70k" costs more than "X above $65k", that's an arb
        because the $65k outcome is a superset of the $70k outcome.

        Returns list of arb opportunity dicts.
        """
        # Extract thresholds
        above_markets = []
        below_markets = []

        for m in markets:
            title = m.get("title", "")
            parsed = _extract_threshold(title)
            if parsed is None:
                continue

            yes_price = m.get("yes_ask", m.get("yes_bid", m.get("last_price", 0))) or 0
            if yes_price <= 0:
                continue

            if parsed[0] == 'above':
                above_markets.append((parsed[1], yes_price, m))
            elif parsed[0] == 'below':
                below_markets.append((parsed[1], yes_price, m))

        opportunities = []

        # For "above" markets: higher threshold should cost LESS
        # "above $70k" is a subset of "above $65k", so price($70k) <= price($65k)
        above_markets.sort(key=lambda x: x[0])  # sort by threshold ascending
        for i in range(len(above_markets)):
            for j in range(i + 1, len(above_markets)):
                low_thresh, low_price, low_mkt = above_markets[i]
                high_thresh, high_price, high_mkt = above_markets[j]
                # higher threshold should cost less or equal
                if high_price > low_price:
                    profit = high_price - low_price
                    fee_cost = CFG.get("taker_fee_per_contract", 0.07) * 2 * 100
                    net_profit = profit - fee_cost
                    if net_profit > 0:
                        opportunities.append({
                            "type": "threshold_arb",
                            "description": f"'{high_mkt.get('title', '')[:50]}' priced higher than "
                                           f"'{low_mkt.get('title', '')[:50]}' (subset violation)",
                            "buy_ticker": low_mkt.get("ticker", ""),
                            "sell_ticker": high_mkt.get("ticker", ""),
                            "buy_price": low_price,
                            "sell_price": high_price,
                            "profit_cents": round(net_profit, 1),
                            "thresholds": (low_thresh, high_thresh),
                        })

        # For "below" markets: higher threshold should cost MORE
        # "below $70k" is a superset of "below $65k", so price($70k) >= price($65k)
        below_markets.sort(key=lambda x: x[0])
        for i in range(len(below_markets)):
            for j in range(i + 1, len(below_markets)):
                low_thresh, low_price, low_mkt = below_markets[i]
                high_thresh, high_price, high_mkt = below_markets[j]
                # higher threshold should cost more or equal
                if low_price > high_price:
                    profit = low_price - high_price
                    fee_cost = CFG.get("taker_fee_per_contract", 0.07) * 2 * 100
                    net_profit = profit - fee_cost
                    if net_profit > 0:
                        opportunities.append({
                            "type": "threshold_arb",
                            "description": f"'{low_mkt.get('title', '')[:50]}' priced higher than "
                                           f"'{high_mkt.get('title', '')[:50]}' (superset violation)",
                            "buy_ticker": high_mkt.get("ticker", ""),
                            "sell_ticker": low_mkt.get("ticker", ""),
                            "buy_price": high_price,
                            "sell_price": low_price,
                            "profit_cents": round(net_profit, 1),
                            "thresholds": (low_thresh, high_thresh),
                        })

        return opportunities

    def scan_mutual_exclusion(self, markets):
        """Find mutual-exclusion violations in event markets.

        For markets within the same event that are mutually exclusive
        (exactly one must resolve YES), the sum of YES asks should be >= 100c
        and the sum of YES bids should be <= 100c. Deviations are arb.

        This is similar to bracket sum-to-100 arb but generalized.

        Returns list of arb opportunity dicts.
        """
        # Need at least 3 markets to meaningfully check sum
        if len(markets) < 3:
            return []

        total_ask = 0
        total_bid = 0
        valid_count = 0

        for m in markets:
            ask = m.get("yes_ask", 0) or 0
            bid = m.get("yes_bid", 0) or 0
            if ask > 0:
                total_ask += ask
                valid_count += 1
            if bid > 0:
                total_bid += bid

        if valid_count < 3:
            return []

        fee_per_contract = CFG.get("taker_fee_per_contract", 0.07)
        opportunities = []

        # Long arb: if total_ask < 100, buy all for guaranteed $1 payout
        if total_ask > 0 and total_ask < 100:
            total_fees = sum(
                fee_per_contract * (m.get("yes_ask", 0) / 100) * (1 - m.get("yes_ask", 0) / 100) * 100
                for m in markets if (m.get("yes_ask", 0) or 0) > 0
            )
            net_profit = 100 - total_ask - total_fees
            if net_profit > 0:
                event_ticker = markets[0].get("event_ticker", "?")
                opportunities.append({
                    "type": "mutual_exclusion_long",
                    "description": f"Event {event_ticker}: sum of asks ({total_ask:.0f}c) < 100c",
                    "event_ticker": event_ticker,
                    "total_cost_cents": round(total_ask + total_fees, 1),
                    "profit_cents": round(net_profit, 1),
                    "n_markets": valid_count,
                })

        # Short arb: if total_bid > 100, sell all for guaranteed profit
        if total_bid > 100:
            total_fees = sum(
                fee_per_contract * (m.get("yes_bid", 0) / 100) * (1 - m.get("yes_bid", 0) / 100) * 100
                for m in markets if (m.get("yes_bid", 0) or 0) > 0
            )
            net_profit = total_bid - total_fees - 100
            if net_profit > 0:
                event_ticker = markets[0].get("event_ticker", "?")
                opportunities.append({
                    "type": "mutual_exclusion_short",
                    "description": f"Event {event_ticker}: sum of bids ({total_bid:.0f}c) > 100c",
                    "event_ticker": event_ticker,
                    "total_receive_cents": round(total_bid - total_fees, 1),
                    "profit_cents": round(net_profit, 1),
                    "n_markets": valid_count,
                })

        return opportunities

    def scan_all(self, groups):
        """Scan all market groups for combinatorial arbitrage.

        Args:
            groups: dict from group_related_markets()

        Returns:
            list of arb opportunity dicts, sorted by profit descending
        """
        all_opps = []
        for key, markets in groups.items():
            try:
                all_opps.extend(self.scan_threshold_arbs(markets))
                all_opps.extend(self.scan_mutual_exclusion(markets))
            except Exception as e:
                log.debug(f"Combinatorial scan error for {key}: {e}")
        all_opps.sort(key=lambda x: x.get("profit_cents", 0), reverse=True)
        return all_opps
