#!/usr/bin/env python3
"""
Polymarket API client for cross-platform arbitrage.
Mirrors KalshiClient structure for seamless integration.

Polymarket runs on Polygon (Ethereum L2). Uses:
- Gamma API (gamma-api.polymarket.com) for market discovery
- CLOB API (clob.polymarket.com) for orderbooks, orders, positions
- py-clob-client for EIP-712 order signing

Usage:
  python polymarket_api.py --action balance --private-key 0x...
  python polymarket_api.py --action markets
  python polymarket_api.py --action orderbook --token-id TOKEN_ID --private-key 0x...
"""
import argparse, json, time, sys, logging

log = logging.getLogger("agent")

# Try importing Polymarket dependencies -- graceful fallback if not installed
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.constants import POLYGON
    HAS_CLOB = True
except ImportError:
    HAS_CLOB = False

try:
    from eth_account import Account
    HAS_ETH = True
except ImportError:
    HAS_ETH = False

import requests

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
CHAIN_ID = POLYGON if HAS_CLOB else 137


class PolymarketAPI:
    """Polymarket CLOB API client, mirroring KalshiAPI interface."""

    def __init__(self, private_key="", api_key="", api_secret="", api_passphrase="", funder=""):
        self.private_key = private_key
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.funder = funder
        self.client = None
        self._address = ""

        if not HAS_CLOB:
            log.warning("py-clob-client not installed -- Polymarket read-only mode")
            return
        if not HAS_ETH:
            log.warning("eth-account not installed -- Polymarket read-only mode")
            return
        if not private_key:
            log.info("Polymarket: no private key -- read-only mode (market data only)")
            return

        try:
            acct = Account.from_key(private_key)
            self._address = acct.address

            # Initialize CLOB client
            if api_key and api_secret and api_passphrase:
                # Use provided API credentials
                creds = {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "passphrase": api_passphrase,
                }
                self.client = ClobClient(
                    CLOB_API,
                    key=private_key,
                    chain_id=CHAIN_ID,
                    creds=creds,
                    funder=funder if funder else None,
                )
            else:
                # Derive API credentials from wallet signature
                self.client = ClobClient(
                    CLOB_API,
                    key=private_key,
                    chain_id=CHAIN_ID,
                    funder=funder if funder else None,
                )
                try:
                    self.client.set_api_creds(self.client.create_or_derive_api_creds())
                    log.info(f"Polymarket: derived API creds for {self._address[:10]}...")
                except Exception as e:
                    log.warning(f"Polymarket: failed to derive API creds: {e} -- read-only mode")
                    self.client = None

            if self.client:
                log.info(f"Polymarket API: connected as {self._address[:10]}...")
        except Exception as e:
            log.error(f"Polymarket init failed: {e}")
            self.client = None

    @property
    def is_trading_enabled(self):
        return self.client is not None

    @property
    def address(self):
        return self._address

    def balance(self):
        """Get USDC balance in dollars. Returns float."""
        if not self.client:
            return 0.0
        try:
            bal = self.client.get_balance()
            # Balance returned in USDC (6 decimals)
            if isinstance(bal, dict):
                return float(bal.get("balance", 0)) / 1e6
            return float(bal) / 1e6 if float(bal) > 100 else float(bal)
        except Exception as e:
            log.error(f"Polymarket balance error: {e}")
            return 0.0

    def all_markets(self, limit=500):
        """Fetch all active markets from Gamma API. No auth needed."""
        markets = []
        offset = 0
        page_size = 100
        for _ in range(limit // page_size + 1):
            try:
                r = requests.get(
                    f"{GAMMA_API}/markets",
                    params={
                        "closed": "false",
                        "limit": page_size,
                        "offset": offset,
                        "order": "volume24hr",
                        "ascending": "false",
                    },
                    timeout=15,
                )
                if r.status_code != 200:
                    break
                batch = r.json()
                if not batch:
                    break
                markets.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
                time.sleep(0.2)
            except Exception as e:
                log.error(f"Polymarket market fetch error at offset {offset}: {e}")
                break
        return markets

    def orderbook(self, token_id):
        """
        Fetch CLOB orderbook for a specific outcome token.
        Returns format compatible with our internal structure.
        """
        if self.client:
            try:
                ob = self.client.get_order_book(token_id)
                return self._normalize_orderbook(ob)
            except Exception as e:
                log.debug(f"Polymarket CLOB orderbook error for {token_id}: {e}")

        # Fallback: REST API
        try:
            r = requests.get(
                f"{CLOB_API}/book",
                params={"token_id": token_id},
                timeout=10,
            )
            if r.status_code == 200:
                return self._normalize_orderbook(r.json())
        except Exception as e:
            log.debug(f"Polymarket REST orderbook error: {e}")
        return {"orderbook": {"yes": [], "no": []}}

    def _normalize_orderbook(self, raw_ob):
        """Convert Polymarket orderbook to Kalshi-compatible format (prices in cents)."""
        result = {"yes": [], "no": []}
        try:
            # Polymarket orderbook has "bids" (buy) and "asks" (sell) for each token
            # For the YES token: bids = people wanting to buy YES, asks = people selling YES
            bids = []
            asks = []
            if hasattr(raw_ob, 'bids'):
                bids = raw_ob.bids or []
                asks = raw_ob.asks or []
            elif isinstance(raw_ob, dict):
                bids = raw_ob.get("bids", [])
                asks = raw_ob.get("asks", [])

            # YES side: asks are what we'd buy at (sorted ascending, first = cheapest)
            for entry in asks:
                if hasattr(entry, 'price'):
                    price = float(entry.price)
                    size = float(entry.size)
                elif isinstance(entry, dict):
                    price = float(entry.get("price", 0))
                    size = float(entry.get("size", 0))
                else:
                    continue
                cents = int(round(price * 100))
                if 1 <= cents <= 99:
                    result["yes"].append([cents, int(size)])

            # NO side: bids are what we'd buy NO at (NO price = 100 - YES bid price)
            for entry in bids:
                if hasattr(entry, 'price'):
                    price = float(entry.price)
                    size = float(entry.size)
                elif isinstance(entry, dict):
                    price = float(entry.get("price", 0))
                    size = float(entry.get("size", 0))
                else:
                    continue
                no_cents = int(round((1.0 - price) * 100))
                if 1 <= no_cents <= 99:
                    result["no"].append([no_cents, int(size)])

            # Sort: YES ascending (cheapest ask first), NO ascending (cheapest first)
            result["yes"].sort(key=lambda x: x[0])
            result["no"].sort(key=lambda x: x[0])
        except Exception as e:
            log.debug(f"Orderbook normalize error: {e}")

        return {"orderbook": result}

    def place_order(self, token_id, side, size, price_cents):
        """
        Place a limit order on Polymarket CLOB.
        Args:
            token_id: The outcome token ID
            side: "yes" or "no" -- translated to BUY/SELL on the token
            size: Number of contracts
            price_cents: Price in cents (1-99)
        Returns: order result dict
        """
        if not self.client:
            raise RuntimeError("Polymarket trading not enabled (no API credentials)")

        price = price_cents / 100.0

        try:
            # For YES: we BUY the token at the given price
            # For NO: we SELL the token at (1 - no_price), which is equivalent to buying NO
            if side.lower() == "yes":
                order_args = OrderArgs(
                    price=price,
                    size=size,
                    side="BUY",
                    token_id=token_id,
                )
            else:
                # Buying NO = Selling YES at complementary price
                order_args = OrderArgs(
                    price=1.0 - price,
                    size=size,
                    side="SELL",
                    token_id=token_id,
                )

            signed = self.client.create_order(order_args)
            result = self.client.post_order(signed, OrderType.GTC)
            log.info(f"Polymarket order placed: {side} {size}x @{price_cents}c token={token_id[:16]}...")
            return result
        except Exception as e:
            log.error(f"Polymarket order failed: {e}")
            raise

    def cancel_order(self, order_id):
        """Cancel an open order."""
        if not self.client:
            return False
        try:
            self.client.cancel(order_id)
            return True
        except Exception as e:
            log.error(f"Polymarket cancel failed: {e}")
            return False

    def positions(self):
        """Fetch all open positions. Returns list of position dicts."""
        if not self.client:
            return []
        try:
            positions = self.client.get_positions()
            if isinstance(positions, list):
                return positions
            return positions.get("positions", []) if isinstance(positions, dict) else []
        except Exception as e:
            log.error(f"Polymarket positions error: {e}")
            return []

    def get_market_by_condition(self, condition_id):
        """Fetch a single market by condition ID from Gamma API."""
        try:
            r = requests.get(f"{GAMMA_API}/markets/{condition_id}", timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.debug(f"Polymarket market fetch error: {e}")
        return None


def normalize_polymarket(pm):
    """
    Convert a raw Polymarket Gamma API market dict to our normalized format.
    Matches the structure used internally by the Kalshi agent.
    """
    import datetime as _dt

    # Extract token IDs for YES and NO outcomes
    tokens = pm.get("tokens", [])
    yes_token = ""
    no_token = ""
    yes_price = 50
    no_price = 50
    for tok in tokens:
        outcome = (tok.get("outcome", "") or "").lower()
        if outcome == "yes":
            yes_token = tok.get("token_id", "")
            yes_price = float(tok.get("price", 0.5)) * 100
        elif outcome == "no":
            no_token = tok.get("token_id", "")
            no_price = float(tok.get("price", 0.5)) * 100

    # If no explicit yes/no tokens, use the first two
    if not yes_token and len(tokens) >= 1:
        yes_token = tokens[0].get("token_id", "")
        yes_price = float(tokens[0].get("price", 0.5)) * 100
    if not no_token and len(tokens) >= 2:
        no_token = tokens[1].get("token_id", "")
        no_price = float(tokens[1].get("price", 0.5)) * 100

    # Calculate hours left
    end_date = pm.get("end_date_iso", pm.get("endDate", ""))
    hrs_left = 9999
    if end_date:
        try:
            ct = _dt.datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            hrs_left = max(0, (ct - _dt.datetime.now(_dt.timezone.utc)).total_seconds() / 3600)
        except Exception:
            pass

    volume = 0
    try:
        volume = int(float(pm.get("volume", pm.get("volume24hr", 0)) or 0))
    except (ValueError, TypeError):
        pass

    return {
        "platform": "polymarket",
        "ticker": pm.get("condition_id", pm.get("id", "")),
        "token_id": yes_token,
        "no_token_id": no_token,
        "title": pm.get("question", pm.get("title", "")),
        "subtitle": pm.get("description", "")[:200],
        "category": "other",
        "yes_bid": int(round(yes_price)),
        "no_bid": int(round(no_price)),
        "last_price": int(round(yes_price)),
        "volume": volume,
        "close_time": end_date,
        "expiration_time": end_date,
        "_hrs_left": round(hrs_left, 1),
        "_score": 0,
        "_category": "other",
        "resolution_source": pm.get("resolution_source", ""),
        "event_ticker": pm.get("market_slug", pm.get("slug", "")),
        "polymarket_raw": pm,  # Keep raw data for matching
    }


def main():
    ap = argparse.ArgumentParser(description="Polymarket API Client")
    ap.add_argument("--action", required=True,
                     choices=["balance", "markets", "orderbook", "positions", "order"])
    ap.add_argument("--private-key", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--api-secret", default="")
    ap.add_argument("--api-passphrase", default="")
    ap.add_argument("--token-id", default="")
    ap.add_argument("--side", default="yes")
    ap.add_argument("--size", type=int, default=1)
    ap.add_argument("--price", type=int, default=50)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    client = PolymarketAPI(
        private_key=args.private_key,
        api_key=args.api_key,
        api_secret=args.api_secret,
        api_passphrase=args.api_passphrase,
    )

    if args.action == "balance":
        bal = client.balance()
        print(json.dumps({"balance": bal, "balance_usdc": round(bal, 6)}))

    elif args.action == "markets":
        mkts = client.all_markets()
        normalized = [normalize_polymarket(m) for m in mkts[:args.limit]]
        print(json.dumps({
            "count": len(mkts),
            "markets": normalized,
        }, indent=2, default=str))
        print(f"\n... {len(mkts)} total Polymarket markets")

    elif args.action == "orderbook":
        if not args.token_id:
            print("Error: --token-id required"); sys.exit(1)
        ob = client.orderbook(args.token_id)
        print(json.dumps(ob, indent=2, default=str))

    elif args.action == "positions":
        pos = client.positions()
        print(json.dumps({"count": len(pos), "positions": pos}, indent=2, default=str))

    elif args.action == "order":
        if not args.token_id:
            print("Error: --token-id required"); sys.exit(1)
        result = client.place_order(args.token_id, args.side, args.size, args.price)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
