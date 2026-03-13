"""Deterministic dashboard server for UI QA automation."""
import argparse
import datetime as dt
import json
import os
import sys
import threading
import time
from http.server import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.config import CFG, SHARED, SHARED_LOCK
from modules.dashboard import DashHandler


def _seed_shared(scenario: str) -> None:
    now = dt.datetime.now()
    close_1 = (now + dt.timedelta(days=2)).isoformat()
    close_2 = (now + dt.timedelta(days=5)).isoformat()
    close_3 = (now + dt.timedelta(days=1)).isoformat()

    markets = []
    if scenario != "empty_markets":
        markets = [
            {
                "ticker": "KXBTC-2026-12-31",
                "title": "Will Bitcoin close above $120k on Dec 31, 2026?",
                "subtitle": "Crypto",
                "category": "crypto",
                "yes_bid": 62,
                "no_bid": 38,
                "last_price": 61,
                "volume": 250000,
                "volume_24h": 12000,
                "close_time": close_1,
                "status": "open",
                "event_ticker": "KXBTC",
                "yes_ask": 63,
                "no_ask": 39,
                "open_time": now.isoformat(),
                "result": None,
                "platform": "kalshi",
            },
            {
                "ticker": "KXFED-2026-06",
                "title": "Will the Fed cut rates by June 2026?",
                "subtitle": "Macro",
                "category": "fed_rates",
                "yes_bid": 47,
                "no_bid": 53,
                "last_price": 48,
                "volume": 190000,
                "volume_24h": 10000,
                "close_time": close_2,
                "status": "open",
                "event_ticker": "KXFED",
                "yes_ask": 48,
                "no_ask": 54,
                "open_time": now.isoformat(),
                "result": None,
                "platform": "kalshi",
            },
            {
                "ticker": "KXWEATHER-CHI",
                "title": "Will Chicago hit 70F this weekend?",
                "subtitle": "Weather",
                "category": "weather",
                "yes_bid": 35,
                "no_bid": 65,
                "last_price": 34,
                "volume": 86000,
                "volume_24h": 5400,
                "close_time": close_3,
                "status": "open",
                "event_ticker": "KXWTHR",
                "yes_ask": 36,
                "no_ask": 66,
                "open_time": now.isoformat(),
                "result": None,
                "platform": "kalshi",
            },
        ]

    trades = [
        {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "ticker": "KXBTC-2026-12-31",
            "title": "Will Bitcoin close above $120k on Dec 31, 2026?",
            "side": "yes",
            "contracts": 4,
            "price_cents": 61,
            "cost": 2.44,
            "confidence": 72,
            "probability": 68,
            "edge": 7,
            "evidence": "Momentum + inflows",
            "bull_prob": 70,
            "bear_prob": 56,
            "status": "filled",
            "platform": "kalshi",
        }
    ]

    positions = [
        {
            "ticker": "KXBTC-2026-12-31",
            "market_ticker": "KXBTC-2026-12-31",
            "side": "yes",
            "contracts": 4,
            "avg_price": 61,
            "market_title": "Will Bitcoin close above $120k on Dec 31, 2026?",
        }
    ]

    with SHARED_LOCK:
        SHARED["enabled"] = True
        SHARED["status"] = "Idle"
        SHARED["balance"] = 1243.52
        SHARED["poly_balance"] = 100.0
        SHARED["poly_enabled"] = True
        SHARED["dry_run"] = True
        SHARED["last_scan"] = now.strftime("%H:%M:%S")
        SHARED["next_scan"] = (now + dt.timedelta(minutes=3)).strftime("%H:%M:%S")
        SHARED["scan_count"] = 42
        SHARED["_arb_opportunities"] = 2
        SHARED["_cross_arb_opportunities"] = 1
        SHARED["_quickflip_active"] = 1
        SHARED["_risk_summary"] = {
            "total": 18,
            "wins": 11,
            "losses": 7,
            "win_rate": "61%",
            "wagered": "$124.00",
            "day_trades": 3,
            "day_pnl": "$12.30",
            "exposure": "$34.50",
            "paused": False,
        }
        SHARED["_cached_markets"] = markets
        SHARED["_positions"] = positions
        SHARED["_trades"] = trades
        SHARED["log_lines"] = [
            {"time": now.strftime("%H:%M:%S"), "msg": "Scan complete", "level": "INFO"},
            {"time": now.strftime("%H:%M:%S"), "msg": "No arb found on last market", "level": "WARNING"},
        ]


class ErrorStateHandler(DashHandler):
    def do_GET(self):
        if self.path == "/api/state":
            self.send_response(500)
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "forced error"}).encode())
            return
        return super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9011)
    parser.add_argument(
        "--scenario",
        choices=["normal", "empty_markets", "error_state"],
        default="normal",
    )
    args = parser.parse_args()

    CFG["dashboard_host"] = args.host
    CFG["dashboard_port"] = args.port
    CFG["dashboard_token"] = ""
    CFG["dry_run"] = True

    _seed_shared(args.scenario)
    handler = ErrorStateHandler if args.scenario == "error_state" else DashHandler
    server = HTTPServer((args.host, args.port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"READY:{server.server_port}:{args.scenario}", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
