#!/usr/bin/env python3
"""
Kalshi API client for the trading skill.
Handles authentication (RSA-PSS signing), balance, markets, orderbook, positions, and order placement.

Usage:
  python kalshi_api.py --action balance --key-id KEY_ID --key-path /path/to/key.pem
  python kalshi_api.py --action markets --key-id KEY_ID --key-path PATH
  python kalshi_api.py --action orderbook --key-id KEY_ID --key-path PATH --ticker TICKER
  python kalshi_api.py --action positions --key-id KEY_ID --key-path PATH
  python kalshi_api.py --action order --key-id KEY_ID --key-path PATH --ticker T --side yes --count 3 --price 60
  python kalshi_api.py --action order --key-id KEY_ID --key-path PATH --ticker T --side no --count 2 --price 40
"""
import argparse, json, time, uuid, base64, sys
from urllib.parse import urlparse
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

BASE = "https://api.elections.kalshi.com/trade-api/v2"

class KalshiClient:
    def __init__(self, key_id, key_path, environment="prod"):
        self.key_id = key_id
        if environment == "demo":
            self.base = "https://demo-api.kalshi.co/trade-api/v2"
        else:
            self.base = BASE
        with open(key_path, "rb") as f:
            self.pk = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

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

    def _req(self, method, path, jdata=None):
        url = self.base + path
        sign_path = urlparse(url).path
        h = self._auth(method, sign_path)
        if method == "GET":
            r = requests.get(url, headers=h, timeout=30)
        elif method == "POST":
            r = requests.post(url, headers=h, json=jdata, timeout=30)
        else:
            raise ValueError(method)
        r.raise_for_status()
        return r.json()

    def balance(self):
        return self._req("GET", "/portfolio/balance").get("balance", 0) / 100

    def all_markets(self):
        out, cur = [], None
        for _ in range(10):
            q = "/markets?limit=200&status=open" + (f"&cursor={cur}" if cur else "")
            d = self._req("GET", q)
            out.extend(d.get("markets", []))
            cur = d.get("cursor")
            if not cur: break
        return out

    def orderbook(self, ticker):
        return self._req("GET", f"/markets/{ticker}/orderbook")

    def positions(self):
        d = self._req("GET", "/portfolio/positions")
        return d.get("market_positions", d.get("positions", []))

    def place_order(self, ticker, side, count, price_cents):
        o = {"ticker": ticker, "action": "buy", "side": side, "count": count,
             "type": "limit", "client_order_id": str(uuid.uuid4())}
        if side == "yes": o["yes_price"] = int(price_cents)
        else: o["no_price"] = int(price_cents)
        return self._req("POST", "/portfolio/orders", o)


def main():
    ap = argparse.ArgumentParser(description="Kalshi API Client")
    ap.add_argument("--action", required=True, choices=["balance","markets","orderbook","positions","order"])
    ap.add_argument("--key-id", required=True)
    ap.add_argument("--key-path", required=True)
    ap.add_argument("--environment", default="prod")
    ap.add_argument("--ticker", default="")
    ap.add_argument("--side", default="yes")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--price", type=int, default=50)
    args = ap.parse_args()

    client = KalshiClient(args.key_id, args.key_path, args.environment)

    if args.action == "balance":
        bal = client.balance()
        print(json.dumps({"balance": bal, "balance_cents": int(bal*100)}))

    elif args.action == "markets":
        mkts = client.all_markets()
        print(json.dumps({"count": len(mkts), "markets": mkts[:5]}, indent=2, default=str))
        print(f"\n... {len(mkts)} total markets loaded")

    elif args.action == "orderbook":
        if not args.ticker:
            print("Error: --ticker required for orderbook"); sys.exit(1)
        ob = client.orderbook(args.ticker)
        print(json.dumps(ob, indent=2, default=str))

    elif args.action == "positions":
        pos = client.positions()
        print(json.dumps({"count": len(pos), "positions": pos}, indent=2, default=str))

    elif args.action == "order":
        if not args.ticker:
            print("Error: --ticker required for order"); sys.exit(1)
        result = client.place_order(args.ticker, args.side, args.count, args.price)
        print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()
