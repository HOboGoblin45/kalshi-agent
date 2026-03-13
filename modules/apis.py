"""API clients for Kalshi and Polymarket platforms."""
import os, json, time, uuid, base64, datetime
import requests as req_lib
from urllib.parse import urlparse
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from modules.config import CFG, BASE_URLS, log

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType
    from py_clob_client.constants import POLYGON
    HAS_POLYMARKET = True
except ImportError:
    HAS_POLYMARKET = False

try:
    from eth_account import Account as EthAccount
    HAS_ETH_ACCOUNT = True
except ImportError:
    HAS_ETH_ACCOUNT = False


GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


class KalshiAPI:
    def __init__(self):
        self.key_id = CFG["kalshi_api_key_id"]
        self.base = BASE_URLS.get(CFG["environment"], BASE_URLS["prod"])
        self.pk = serialization.load_pem_private_key(
            open(CFG["kalshi_private_key_path"], "rb").read(), password=None, backend=default_backend())

    def _sign(self, ts, method, path):
        msg = f"{ts}{method}{path.split('?')[0]}".encode()
        sig = self.pk.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
        return base64.b64encode(sig).decode()

    def _auth(self, method, path):
        ts = str(int(time.time() * 1000))
        return {"KALSHI-ACCESS-KEY": self.key_id,
                "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method, path),
                "KALSHI-ACCESS-TIMESTAMP": ts, "Content-Type": "application/json"}

    def _req(self, method, path, jdata=None, retries=3):
        url = self.base + path
        sign_path = urlparse(url).path
        for attempt in range(retries):
            try:
                h = self._auth(method, sign_path)
                if method == "GET": r = req_lib.get(url, headers=h, timeout=30)
                elif method == "POST": r = req_lib.post(url, headers=h, json=jdata, timeout=30)
                elif method == "DELETE": r = req_lib.delete(url, headers=h, timeout=30)
                else: raise ValueError(method)
                if r.status_code == 429:
                    retry_after = r.headers.get("Retry-After")
                    w = min(120, int(retry_after)) if retry_after and retry_after.isdigit() else min(60, 10 * (attempt + 1))
                    log.warning(f"Rate limited, wait {w}s"); time.sleep(w); continue
                r.raise_for_status()
                return r.json() if method != "DELETE" else r
            except req_lib.exceptions.ConnectionError:
                if attempt < retries - 1: log.warning(f"Conn error, retry {attempt + 1}"); time.sleep(3)
                else: raise
            except req_lib.exceptions.HTTPError:
                log.error(f"HTTP {r.status_code}: {r.text[:200]}"); raise
        raise Exception(f"Failed after {retries} retries")

    def balance(self): return self._req("GET", "/portfolio/balance").get("balance", 0) / 100

    def all_markets(self):
        out, cur = [], None
        for _ in range(10):
            q = "/markets?limit=200&status=open" + (f"&cursor={cur}" if cur else "")
            d = self._req("GET", q); out.extend(d.get("markets", [])); cur = d.get("cursor")
            if not cur: break
        return out

    def orderbook(self, t): return self._req("GET", f"/markets/{t}/orderbook")

    def positions(self):
        d = self._req("GET", "/portfolio/positions")
        return d.get("market_positions", d.get("positions", []))

    def place_order(self, ticker, side, count, price_cents):
        o = {"ticker": ticker, "action": "buy", "side": side, "count": count,
             "type": "limit", "client_order_id": str(uuid.uuid4())}
        if side == "yes": o["yes_price"] = int(price_cents)
        else: o["no_price"] = int(price_cents)
        return self._req("POST", "/portfolio/orders", o)


class MarketCache:
    def __init__(self, api):
        self.api = api; self.markets = []; self.last_refresh = 0
        self.ttl = CFG["market_cache_minutes"] * 60
        self._refresh_failures = 0

    def get(self):
        now = time.time()
        if not self.markets or (now - self.last_refresh) > self.ttl:
            log.info("Loading markets (full refresh)...")
            try:
                fresh = self.api.all_markets(); self.markets = fresh; self.last_refresh = now
                self._refresh_failures = 0
                log.info(f"Cached {len(self.markets)} markets")
            except Exception as e:
                self._refresh_failures += 1
                log.error(f"Market refresh failed (attempt #{self._refresh_failures}): {e}")
                if self.markets:
                    log.warning(f"Using stale cache ({len(self.markets)} mkts, {int(now - self.last_refresh)}s old)")
                else:
                    raise
        else:
            log.info(f"Using cache ({len(self.markets)} mkts, {int(now - self.last_refresh)}s old)")
        return self.markets


class PolymarketAPI:
    """Polymarket CLOB API client, mirroring KalshiAPI interface."""

    def __init__(self):
        self.private_key = CFG.get("polymarket_private_key", "")
        self.client = None
        self._address = ""

        if not HAS_POLYMARKET:
            log.warning("py-clob-client not installed -- Polymarket read-only mode")
            return
        if not HAS_ETH_ACCOUNT:
            log.warning("eth-account not installed -- Polymarket read-only mode")
            return
        if not self.private_key:
            log.info("Polymarket: no private key -- read-only mode (market data only)")
            return

        try:
            acct = EthAccount.from_key(self.private_key)
            self._address = acct.address
            api_key = CFG.get("polymarket_api_key", "")
            api_secret = CFG.get("polymarket_api_secret", "")
            api_passphrase = CFG.get("polymarket_api_passphrase", "")
            funder = CFG.get("polymarket_funder", "") or None
            chain_id = POLYGON if HAS_POLYMARKET else 137

            if api_key and api_secret and api_passphrase:
                creds = {"apiKey": api_key, "secret": api_secret, "passphrase": api_passphrase}
                self.client = ClobClient(CLOB_API, key=self.private_key, chain_id=chain_id,
                                          creds=creds, funder=funder)
            else:
                self.client = ClobClient(CLOB_API, key=self.private_key, chain_id=chain_id,
                                          funder=funder)
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

    def balance(self):
        if not self.client: return 0.0
        try:
            bal = self.client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            return float(bal.get("balance", 0)) / 1e6
        except Exception as e:
            log.error(f"Polymarket balance error: {e}"); return 0.0

    def all_markets(self, limit=500):
        markets = []; offset = 0; page_size = 100
        for _ in range(limit // page_size + 1):
            try:
                r = req_lib.get(f"{GAMMA_API}/markets",
                    params={"closed": "false", "limit": page_size, "offset": offset,
                            "order": "volume24hr", "ascending": "false"}, timeout=15)
                if r.status_code != 200: break
                batch = r.json()
                if not batch: break
                markets.extend(batch); offset += page_size
                if len(batch) < page_size: break
                time.sleep(0.2)
            except Exception as e:
                log.error(f"Polymarket market fetch error at offset {offset}: {e}"); break
        return markets

    def orderbook(self, token_id):
        if self.client:
            try:
                ob = self.client.get_order_book(token_id)
                return self._normalize_orderbook(ob)
            except Exception as e:
                log.debug(f"Polymarket CLOB orderbook error for {token_id}: {e}")
        try:
            r = req_lib.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=10)
            if r.status_code == 200: return self._normalize_orderbook(r.json())
        except Exception as e:
            log.debug(f"Polymarket REST orderbook error: {e}")
        return {"orderbook": {"yes": [], "no": []}}

    def _normalize_orderbook(self, raw_ob):
        result = {"yes": [], "no": []}
        try:
            bids, asks = [], []
            if hasattr(raw_ob, 'bids'):
                bids = raw_ob.bids or []; asks = raw_ob.asks or []
            elif isinstance(raw_ob, dict):
                bids = raw_ob.get("bids", []); asks = raw_ob.get("asks", [])
            for entry in asks:
                price = float(entry.price if hasattr(entry, 'price') else entry.get("price", 0))
                size = float(entry.size if hasattr(entry, 'size') else entry.get("size", 0))
                cents = int(round(price * 100))
                if 1 <= cents <= 99: result["yes"].append([cents, int(size)])
            for entry in bids:
                price = float(entry.price if hasattr(entry, 'price') else entry.get("price", 0))
                size = float(entry.size if hasattr(entry, 'size') else entry.get("size", 0))
                no_cents = int(round((1.0 - price) * 100))
                if 1 <= no_cents <= 99: result["no"].append([no_cents, int(size)])
            result["yes"].sort(key=lambda x: x[0])
            result["no"].sort(key=lambda x: x[0])
        except Exception as e:
            log.debug(f"Orderbook normalize error: {e}")
        return {"orderbook": result}

    def place_order(self, token_id, side, count, price_cents):
        if not self.client: raise RuntimeError("Polymarket trading not enabled")
        price = price_cents / 100.0
        try:
            if side.lower() == "yes":
                order_args = OrderArgs(price=price, size=count, side="BUY", token_id=token_id)
            else:
                order_args = OrderArgs(price=1.0 - price, size=count, side="SELL", token_id=token_id)
            signed = self.client.create_order(order_args)
            result = self.client.post_order(signed, OrderType.GTC)
            log.info(f"Polymarket order: {side} {count}x @{price_cents}c token={token_id[:16]}...")
            return result
        except Exception as e:
            log.error(f"Polymarket order failed: {e}"); raise

    def cancel_order(self, order_id):
        if not self.client: return False
        try: self.client.cancel(order_id); return True
        except Exception as e: log.error(f"Polymarket cancel failed: {e}"); return False

    def positions(self):
        if not self.client: return []
        try:
            positions = self.client.get_positions()
            if isinstance(positions, list): return positions
            return positions.get("positions", []) if isinstance(positions, dict) else []
        except Exception as e:
            log.error(f"Polymarket positions error: {e}"); return []


def normalize_polymarket(pm):
    """Convert Polymarket Gamma API market dict to internal format."""
    tokens = pm.get("tokens", [])
    yes_token, no_token, yes_price, no_price = "", "", 50, 50
    for tok in tokens:
        outcome = (tok.get("outcome", "") or "").lower()
        if outcome == "yes":
            yes_token = tok.get("token_id", ""); yes_price = float(tok.get("price", 0.5)) * 100
        elif outcome == "no":
            no_token = tok.get("token_id", ""); no_price = float(tok.get("price", 0.5)) * 100
    if not yes_token and len(tokens) >= 1:
        yes_token = tokens[0].get("token_id", ""); yes_price = float(tokens[0].get("price", 0.5)) * 100
    if not no_token and len(tokens) >= 2:
        no_token = tokens[1].get("token_id", ""); no_price = float(tokens[1].get("price", 0.5)) * 100

    end_date = pm.get("end_date_iso", pm.get("endDate", ""))
    hrs_left = 9999
    if end_date:
        try:
            ct = datetime.datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            hrs_left = max(0, (ct - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600)
        except Exception: pass

    volume = 0
    try: volume = int(float(pm.get("volume", pm.get("volume24hr", 0)) or 0))
    except (ValueError, TypeError): pass

    return {
        "platform": "polymarket",
        "ticker": pm.get("condition_id", pm.get("id", "")),
        "token_id": yes_token, "no_token_id": no_token,
        "title": pm.get("question", pm.get("title", "")),
        "subtitle": pm.get("description", "")[:200],
        "category": "other",
        "yes_bid": int(round(yes_price)), "no_bid": int(round(no_price)),
        "last_price": int(round(yes_price)), "volume": volume,
        "close_time": end_date, "expiration_time": end_date,
        "_hrs_left": round(hrs_left, 1), "_score": 0, "_category": "other",
        "event_ticker": pm.get("market_slug", pm.get("slug", "")),
    }


class PolymarketCache:
    """Cache for Polymarket markets, mirrors MarketCache."""

    def __init__(self, api):
        self.api = api; self.markets = []; self.last_refresh = 0
        self.ttl = CFG.get("market_cache_minutes", 12) * 60

    def get(self):
        now = time.time()
        if not self.markets or (now - self.last_refresh) > self.ttl:
            log.info("Loading Polymarket markets...")
            try:
                raw = self.api.all_markets()
                self.markets = [normalize_polymarket(m) for m in raw]
                self.last_refresh = now
                log.info(f"Cached {len(self.markets)} Polymarket markets")
            except Exception as e:
                log.error(f"Polymarket market refresh failed: {e}")
                if not self.markets: return []
        return self.markets
