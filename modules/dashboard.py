"""Web dashboard + React frontend server for monitoring agent activity."""
import json, os, time, threading, mimetypes
import http.server
from urllib.parse import unquote
import hmac

from modules.config import CFG, SHARED, SHARED_LOCK, log
from modules.market_state import MARKET_STATE
from modules.calibration import CalibrationTracker

_START_TIME = time.time()  # Track uptime

# Resolve the dist/ directory (built React app)
# Works in both dev (source tree) and packaged (Electron asar) environments
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIST_DIR = os.path.join(_BASE_DIR, "dist")
if not os.path.isdir(_DIST_DIR):
    # Fallback: check relative to cwd (packaged mode may set cwd differently)
    _alt = os.path.join(os.getcwd(), "dist")
    if os.path.isdir(_alt):
        _DIST_DIR = _alt

MIME_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class DashHandler(http.server.BaseHTTPRequestHandler):
    def _allowed_origins(self):
        host = CFG.get("dashboard_host", "127.0.0.1")
        port = CFG.get("dashboard_port", 9000)
        return {
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
            f"http://{host}:{port}",
        }

    def _is_local_origin(self, origin):
        if not origin:
            return True
        return origin in self._allowed_origins()

    def _require_toggle_auth(self):
        origin = self.headers.get("Origin", "")
        if not self._is_local_origin(origin):
            return False

        token = CFG.get("dashboard_token", "")
        if not token:
            return True
        got = self.headers.get("X-Dashboard-Token", "")
        return hmac.compare_digest(got, token)

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if self._is_local_origin(origin) and origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Dashboard-Token")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # API routes
        if self.path == '/api/state': return self._json(self._state())
        if self.path == '/api/markets': return self._json(self._markets())
        if self.path == '/api/positions': return self._json(self._positions())
        if self.path == '/api/trades': return self._json(self._trades())
        if self.path == '/api/calibration': return self._json(self._calibration())
        if self.path == '/api/risk-stats': return self._json(self._risk_stats())
        if self.path == '/api/health': return self._json(self._health())

        # Serve built React app from dist/
        if os.path.isdir(_DIST_DIR):
            return self._serve_static()

        # Fallback: 404
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/toggle':
            if not self._require_toggle_auth():
                self.send_response(403)
                self._cors()
                self.end_headers()
                return
            with SHARED_LOCK:
                SHARED["enabled"] = not SHARED["enabled"]
                enabled = SHARED["enabled"]
            log.info(f"Agent {'ENABLED' if enabled else 'DISABLED'} via dashboard")
            self._json({"enabled": enabled})
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_static(self):
        """Serve files from dist/. For SPA routes, fall back to index.html."""
        path = unquote(self.path.split("?")[0])  # strip query string
        if path == "/":
            path = "/index.html"

        rel = os.path.normpath(path.lstrip("/\\"))
        if rel.startswith(".."):
            self.send_response(403)
            self.end_headers()
            return

        dist_abs = os.path.abspath(_DIST_DIR)
        file_path = os.path.abspath(os.path.join(dist_abs, rel))
        if not (file_path == dist_abs or file_path.startswith(dist_abs + os.sep)):
            self.send_response(403)
            self.end_headers()
            return

        # If file exists, serve it
        if os.path.isfile(file_path):
            return self._send_file(file_path)

        # SPA fallback: serve index.html for any non-file route
        index_path = os.path.join(_DIST_DIR, "index.html")
        if os.path.isfile(index_path):
            return self._send_file(index_path)

        self.send_response(404)
        self.end_headers()

    def _send_file(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        content_type = MIME_TYPES.get(ext, mimetypes.guess_type(file_path)[0] or "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if ext in (".js", ".css", ".woff", ".woff2", ".svg", ".png"):
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _json(self, obj):
        d = json.dumps(obj, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(d)

    def _state(self):
        risk = SHARED.get("_risk_summary", {"total": 0, "wins": 0, "losses": 0, "win_rate": "--",
            "wagered": "$0", "day_trades": 0, "day_pnl": "$0", "exposure": "$0", "paused": False})
        # SAFETY: always re-check CFG for canonical dry_run state
        is_dry_run = CFG.get("dry_run", True)
        return {"enabled": SHARED["enabled"], "status": SHARED["status"], "balance": SHARED["balance"],
            "poly_balance": SHARED.get("poly_balance", 0), "poly_enabled": SHARED.get("poly_enabled", False),
            "dry_run": is_dry_run,
            "environment": CFG["environment"].upper(), "risk": risk, "trades": SHARED.get("_trades", [])[-20:],
            "log": SHARED["log_lines"][-100:], "last_scan": SHARED["last_scan"], "next_scan": SHARED["next_scan"],
            "max_daily": CFG["max_daily_trades"], "scan_count": SHARED["scan_count"],
            "scan_interval": CFG["scan_interval_minutes"],
            "ai_interval": CFG["scan_interval_minutes"] * CFG.get("ai_scan_interval_multiplier", 5),
            "arb_opps": SHARED["_arb_opportunities"],
            "cross_arb_opps": SHARED.get("_cross_arb_opportunities", 0),
            "quickflip_active": SHARED.get("_quickflip_active", 0),
            "scan_progress": SHARED.get("_scan_progress", {"phase": "idle", "step": "", "pct": 0, "total_phases": 0, "current_phase": 0}),
            "scan_summary": SHARED.get("_scan_summary", ""),
            "feed_health": MARKET_STATE.feed_status(),
            "stale_markets": len(MARKET_STATE.stale_tickers())}

    def _markets(self):
        return SHARED.get("_cached_markets", [])

    def _positions(self):
        return SHARED.get("_positions", [])

    def _trades(self):
        return SHARED.get("_trades", [])

    def _calibration(self):
        try:
            tracker = CalibrationTracker()
            return tracker.summary()
        except Exception:
            return {"total_predictions": 0, "resolved": 0, "pending": 0,
                    "overall_brier": 0.25, "overall_log_loss": 1.0, "category_stats": {}}

    def _risk_stats(self):
        """Drawdown probability and risk metrics for the dashboard."""
        import math
        try:
            with SHARED_LOCK:
                trades = list(SHARED.get("_trades", []))
                balance = SHARED.get("balance", 0)

            if not trades:
                return {"drawdown_probs": {}, "peak_balance": balance,
                        "current_balance": balance, "n_trades": 0,
                        "growth_rate": 0, "volatility": 0}

            # Calculate returns from trade history
            returns = []
            for t in trades:
                cost = t.get("cost", 0)
                pnl = t.get("pnl", 0)
                if cost > 0 and t.get("status") in ("win", "loss"):
                    returns.append(pnl / cost)

            n = len(returns)
            if n < 2:
                return {"drawdown_probs": {}, "peak_balance": balance,
                        "current_balance": balance, "n_trades": n,
                        "growth_rate": 0, "volatility": 0}

            # Growth rate (mean return) and volatility (std dev)
            g = sum(returns) / n
            variance = sum((r - g) ** 2 for r in returns) / (n - 1)
            s = math.sqrt(variance) if variance > 0 else 0.001

            # Drawdown probability: P(reaching x% of peak) ≈ x^(2g/s²)
            # x is fraction of peak (e.g., 0.9 = 10% drawdown)
            exponent = (2 * g) / (s * s) if s > 0 else 0
            drawdown_probs = {}
            for dd_pct in [5, 10, 15, 20, 25, 30, 50]:
                x = 1.0 - dd_pct / 100.0  # fraction remaining
                if x > 0 and exponent > 0:
                    prob = min(1.0, x ** exponent)
                elif exponent <= 0:
                    prob = 1.0  # negative growth → drawdown almost certain
                else:
                    prob = 0.0
                drawdown_probs[str(dd_pct)] = round(prob * 100, 1)

            # Track peak balance from trade history
            running = balance
            peak = balance
            for t in reversed(trades):
                pnl = t.get("pnl", 0)
                if t.get("status") in ("win", "loss"):
                    running -= pnl
                    peak = max(peak, running)

            return {
                "drawdown_probs": drawdown_probs,
                "peak_balance": round(peak, 2),
                "current_balance": round(balance, 2),
                "current_drawdown_pct": round((1 - balance / peak) * 100, 1) if peak > 0 else 0,
                "n_trades": n,
                "growth_rate": round(g * 100, 2),
                "volatility": round(s * 100, 2),
                "kelly_edge_ratio": round(g / (s * s), 3) if s > 0 else 0,
            }
        except Exception:
            return {"drawdown_probs": {}, "peak_balance": 0, "current_balance": 0,
                    "n_trades": 0, "growth_rate": 0, "volatility": 0}

    def _health(self):
        """Health check endpoint for monitoring (UptimeRobot, etc)."""
        import datetime
        with SHARED_LOCK:
            balance = SHARED.get("balance", 0)
            poly_bal = SHARED.get("poly_balance", 0)
            last_scan = SHARED.get("last_scan", "")
            status = SHARED.get("status", "unknown")
            scan_count = SHARED.get("scan_count", 0)
            positions = SHARED.get("_positions", [])
            trades = SHARED.get("_trades", [])

        uptime_hours = round((time.time() - _START_TIME) / 3600, 1)

        # Seconds since last scan
        secs_since_scan = None
        if last_scan:
            try:
                today = datetime.date.today()
                last_dt = datetime.datetime.combine(
                    today, datetime.datetime.strptime(last_scan, "%H:%M:%S").time())
                secs_since_scan = int((datetime.datetime.now() - last_dt).total_seconds())
                if secs_since_scan < 0:
                    secs_since_scan += 86400  # wrapped past midnight
            except Exception:
                pass

        # Count errors in recent trades
        errors_24h = sum(1 for t in trades
                        if t.get("status") == "error"
                        and t.get("time", "")[:10] == datetime.date.today().isoformat())

        return {
            "status": status,
            "uptime_hours": uptime_hours,
            "last_scan": last_scan,
            "seconds_since_last_scan": secs_since_scan,
            "scan_count": scan_count,
            "open_positions": len(positions),
            "balance_kalshi": round(balance, 2),
            "balance_polymarket": round(poly_bal, 2),
            "balance_combined": round(balance + poly_bal, 2),
            "errors_last_24h": errors_24h,
        }

    def log_message(self, *a):
        pass


def start_dashboard():
    port = CFG.get("dashboard_port", 9000)
    host = CFG.get("dashboard_host", "127.0.0.1")

    if not os.path.isdir(_DIST_DIR):
        log.warning(f"Frontend not built yet (no dist/ folder). Run 'npm run build' first.")
        log.warning(f"API endpoints will still work at http://{host}:{port}/api/")

    srv = http.server.HTTPServer((host, port), DashHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info(f"Dashboard: http://{host}:{port}")
