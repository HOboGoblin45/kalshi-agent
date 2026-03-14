"""Shared configuration, state, logging, and utility functions."""
import os, sys, json, datetime, logging, threading, re
from logging.handlers import RotatingFileHandler

# ── Secret field names: these must NEVER appear with real values in tracked config ──
SECRET_FIELDS = frozenset({
    "kalshi_api_key_id", "kalshi_private_key_path",
    "anthropic_api_key",
    "polymarket_private_key", "polymarket_api_key",
    "polymarket_api_secret", "polymarket_api_passphrase",
    "polymarket_funder",
    "email_password", "dashboard_token",
    "fred_api_key",
})

DEFAULTS = {
    "kalshi_api_key_id": "", "kalshi_private_key_path": "", "anthropic_api_key": "",
    "environment": "demo",
    "scan_interval_minutes": 3,
    "ai_scan_interval_multiplier": 5,
    "markets_per_scan": 40,
    "deep_dive_top_n": 2,
    "market_cache_minutes": 15,
    "target_keywords": [],
    "category_rules": {
        "weather": ["temperature", "hurricane", "tornado", "rainfall", "snowfall", "weather", "climate", "heat", "cold", "storm", "wind", "flood"],
        "fed_rates": ["fed", "fomc", "interest rate", "fed funds", "powell", "rate cut", "rate hike", "monetary policy"],
        "inflation": ["inflation", "cpi", "pce", "consumer price", "core inflation"],
        "employment": ["unemployment", "jobs", "nonfarm", "payroll", "jobless claims", "employment"],
        "gdp_growth": ["gdp", "recession", "economic growth", "gross domestic"],
        "markets": ["s&p", "nasdaq", "dow", "stock market", "treasury", "yield", "bond"],
        "energy": ["gas price", "oil price", "oil production", "opec", "wti", "brent", "gasoline"],
        "policy": ["sec", "regulation", "congress", "legislation", "bill", "executive order", "tariff", "trade war",
                    "crypto regulation", "bitcoin etf", "stablecoin", "debt ceiling", "government shutdown", "sanctions"],
        "sports": ["nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball", "baseball", "hockey",
                   "playoff", "championship", "finals", "march madness", "world series", "stanley cup", "super bowl",
                   "mvp", "player", "team", "game", "match", "points", "score", "wins", "sports",
                   "over", "under", "parlay", "multigame", "crosscategory"],
        "crypto": ["bitcoin", "ethereum", "solana", "dogecoin", "xrp", "cardano", "crypto", "blockchain",
                   "defi", "nft", "token", "coin", "altcoin", "memecoin", "binance", "coinbase", "halving"],
    },
    # Polymarket integration
    "polymarket_enabled": False,
    "polymarket_private_key": "",
    "polymarket_api_key": "",
    "polymarket_api_secret": "",
    "polymarket_api_passphrase": "",
    "polymarket_funder": "",
    "polymarket_fee_per_contract": 0.02,
    # Cross-platform arbitrage
    "cross_arb_enabled": False,
    "cross_arb_min_profit_cents": 2,
    "cross_arb_max_cost": 10.00,
    "cross_arb_match_threshold": 0.70,
    # Quick-flip scalping -- disabled by default (structurally risky strategy)
    "quickflip_enabled": False,
    "quickflip_max_bet": 1.00,
    "quickflip_min_price": 3,
    "quickflip_max_price": 15,
    "quickflip_target_multiplier": 2.0,
    # Compounding / aggressive mode
    "aggressive_mode": False,
    "compounding_enabled": False,
    # Strategy toggles
    "debate_enabled": True,
    "within_arb_enabled": True,
    # Trading parameters -- conservative defaults
    "max_bet_per_trade": 1.50,
    "max_total_exposure": 22.00,
    "max_daily_trades": 12,
    "max_daily_loss": 8.00,
    "min_confidence": 65,
    "min_edge_pct": 5,
    "kelly_fraction": 0.20,
    "min_volume": 15,
    "min_close_hours": 1.0,
    "max_close_hours": 48,
    "cant_miss_edge_pct": 15,
    "cant_miss_min_confidence": 82,
    "max_price_cents": 95,
    "min_price_cents": 5,
    "taker_fee_per_contract": 0.07,
    "trade_log": "kalshi-trades.json",
    "calibration_log": "kalshi-calibration.json",
    "dashboard_port": 9000,
    "dashboard_host": "127.0.0.1",
    "dashboard_token": "",
    # SAFETY: dry_run is ALWAYS True by default. Only explicit --live flag can disable.
    "dry_run": True,
    "fred_api_key": "",
    # Email notifications
    "email_enabled": False,
    "email_smtp_server": "smtp.gmail.com",
    "email_smtp_port": 587,
    "email_from": "",
    "email_password": "",
    "email_to": "",
    "notify_on_trade": True,
    "notify_on_circuit_breaker": True,
    "notify_on_arbitrage": True,
    # Exit strategy
    "exit_check_interval_minutes": 10,
    "exit_loss_pct": 25,
    "exit_profit_pct": 40,
    "exit_time_hours": 36,
    # Weekly performance report
    "report_day": "sunday",
    "report_hour": 20,
    "report_file": "kalshi-weekly-report.txt",
}

CFG = dict(DEFAULTS)
BASE_URLS = {
    "prod": "https://api.elections.kalshi.com/trade-api/v2",
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
}

SHARED = {
    "enabled": True, "status": "Starting...", "balance": 0, "last_scan": "Never",
    "next_scan": "--", "scan_count": 0, "log_lines": [],
    "_risk_summary": {"total": 0, "wins": 0, "losses": 0, "win_rate": "--",
        "wagered": "$0", "day_trades": 0, "day_pnl": "$0", "exposure": "$0", "paused": False},
    "_trades": [], "_arb_opportunities": 0,
    "poly_balance": 0, "poly_enabled": False,
    "_cross_arb_opportunities": 0, "_quickflip_active": 0,
    "_cross_platform_risk": {},
    "dry_run": True,
    # Scan progress tracking
    "_scan_progress": {"phase": "idle", "step": "", "pct": 0, "total_phases": 4, "current_phase": 0},
    "_scan_summary": "",
}
SHARED_LOCK = threading.RLock()


def load_config(config_path=None, live_mode=False):
    """Load config from file + env vars. Enforces dry_run=True unless explicitly overridden.

    Loading order:
    1. DEFAULTS (always dry_run=True)
    2. Config file (kalshi-config.json) -- dry_run from file is IGNORED for safety
    3. Environment variables (override secrets)
    4. --live flag (only way to set dry_run=False)
    """
    # Start from defaults
    CFG.clear()
    CFG.update(DEFAULTS)

    # Load config file if provided
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path) as f:
                file_cfg = json.load(f)
            # Strip comments
            file_cfg = {k: v for k, v in file_cfg.items() if not k.startswith("_comment")}
            # SAFETY: ignore dry_run from config file -- it must be set via --live flag only
            file_cfg.pop("dry_run", None)
            CFG.update(file_cfg)
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"Failed to load config file {config_path}: {e}")
            raise SystemExit(1)

    # Environment variable overrides (highest priority for secrets)
    env_overrides = {
        "KALSHI_API_KEY_ID": "kalshi_api_key_id",
        "KALSHI_PRIVATE_KEY_PATH": "kalshi_private_key_path",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "FRED_API_KEY": "fred_api_key",
        "KALSHI_EMAIL_PASSWORD": "email_password",
        "POLYMARKET_PRIVATE_KEY": "polymarket_private_key",
        "POLYMARKET_API_KEY": "polymarket_api_key",
        "POLYMARKET_API_SECRET": "polymarket_api_secret",
        "POLYMARKET_API_PASSPHRASE": "polymarket_api_passphrase",
        "POLYMARKET_FUNDER": "polymarket_funder",
        "KALSHI_DASHBOARD_TOKEN": "dashboard_token",
        "KALSHI_DASHBOARD_HOST": "dashboard_host",
        "KALSHI_DASHBOARD_PORT": None,  # handled as int below
        "KALSHI_ENVIRONMENT": "environment",
        "KALSHI_DRY_RUN": None,  # handled specially below
    }
    for env_var, cfg_key in env_overrides.items():
        val = os.environ.get(env_var)
        if val and cfg_key:
            CFG[cfg_key] = val

    # Dashboard port from env (needs int conversion)
    env_port = os.environ.get("KALSHI_DASHBOARD_PORT")
    if env_port:
        try:
            CFG["dashboard_port"] = int(env_port)
        except ValueError:
            pass

    # Live mode: only explicit --live flag enables it
    if live_mode:
        # Check for KALSHI_CONFIRM_LIVE env var as double-gate
        confirm = os.environ.get("KALSHI_CONFIRM_LIVE", "").lower()
        if confirm in ("1", "true", "yes"):
            CFG["dry_run"] = False
        else:
            CFG["dry_run"] = False
            log.warning("=" * 60)
            log.warning("  LIVE TRADING MODE ENABLED")
            log.warning("  Set KALSHI_CONFIRM_LIVE=1 to suppress this warning")
            log.warning("=" * 60)
    else:
        # Env var can also enable live mode as a convenience
        env_dry = os.environ.get("KALSHI_DRY_RUN", "").lower()
        if env_dry in ("0", "false", "no"):
            CFG["dry_run"] = False
            log.warning("LIVE mode enabled via KALSHI_DRY_RUN=false env var")
        else:
            CFG["dry_run"] = True

    # Sync shared state
    with SHARED_LOCK:
        SHARED["dry_run"] = CFG["dry_run"]

    # Validate: refuse to boot with missing required credentials
    if not CFG["kalshi_api_key_id"] or not CFG["anthropic_api_key"]:
        log.error("Missing required credentials: kalshi_api_key_id and anthropic_api_key")
        log.error("Set via config file, environment variables, or --config flag")
        raise SystemExit(1)

    # Log mode
    mode_str = "DRY-RUN (safe)" if CFG["dry_run"] else "LIVE TRADING"
    env_str = CFG.get("environment", "demo").upper()
    log.info(f"Config loaded: mode={mode_str}, environment={env_str}")
    if not CFG["dry_run"]:
        log.warning("LIVE TRADING is active. Real orders WILL be placed.")

    return CFG


# NWS grid coordinates for weather markets
CITY_COORDS = {
    "new york":      (40.7128, -74.0060), "nyc":           (40.7128, -74.0060),
    "chicago":       (41.8781, -87.6298), "los angeles":   (34.0522, -118.2437),
    "miami":         (25.7617, -80.1918), "denver":        (39.7392, -104.9903),
    "houston":       (29.7604, -95.3698), "phoenix":       (33.4484, -112.0740),
    "philadelphia":  (39.9526, -75.1652), "san antonio":   (29.4241, -98.4936),
    "dallas":        (32.7767, -96.7970), "san francisco": (37.7749, -122.4194),
    "seattle":       (47.6062, -122.3321), "washington":   (38.9072, -77.0369),
    "boston":         (42.3601, -71.0589), "atlanta":       (33.7490, -84.3880),
    "detroit":       (42.3314, -83.0458), "minneapolis":   (44.9778, -93.2650),
    "las vegas":     (36.1699, -115.1398), "portland":     (45.5152, -122.6784),
    "austin":        (30.2672, -97.7431), "nashville":     (36.1627, -86.7816),
    "orlando":       (28.5383, -81.3792), "charlotte":     (35.2271, -80.8431),
    "san diego":     (32.7157, -117.1611), "st. louis":    (38.6270, -90.1994),
    "tampa":         (27.9506, -82.4572), "pittsburgh":    (40.4406, -79.9959),
    "baltimore":     (39.2904, -76.6122), "cleveland":     (41.4993, -81.6944),
    "kansas city":   (39.0997, -94.5786), "columbus":      (39.9612, -82.9988),
    "indianapolis":  (39.7684, -86.1581), "milwaukee":     (43.0389, -87.9065),
    "sacramento":    (38.5816, -121.4944), "memphis":      (35.1495, -90.0490),
    "oklahoma city": (35.4676, -97.5164), "raleigh":      (35.7796, -78.6382),
    "louisville":    (38.2527, -85.7585), "salt lake":     (40.7608, -111.8910),
    "new orleans":   (29.9511, -90.0715), "cincinnati":    (39.1031, -84.5120),
}

# FRED series IDs
FRED_SERIES = {
    "fed_funds":      "DFF",
    "cpi":            "CPIAUCSL",
    "core_cpi":       "CPILFESL",
    "unemployment":   "UNRATE",
    "nonfarm":        "PAYEMS",
    "jobless_claims": "ICSA",
    "gdp":            "GDP",
    "gas_price":      "GASREGW",
    "treasury_10y":   "DGS10",
    "treasury_2y":    "DGS2",
    "sp500":          "SP500",
}

# ── Logging ──
log = logging.getLogger("agent")
log.setLevel(logging.DEBUG)
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
log.addHandler(_ch)
_fh = RotatingFileHandler("kalshi-agent.log", maxBytes=5*1024*1024, backupCount=3)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
log.addHandler(_fh)


class DashLog(logging.Handler):
    def emit(self, record):
        with SHARED_LOCK:
            SHARED["log_lines"].append({
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "msg": record.getMessage(), "level": record.levelname,
            })
            if len(SHARED["log_lines"]) > 300:
                SHARED["log_lines"] = SHARED["log_lines"][-300:]

_dl = DashLog()
_dl.setLevel(logging.INFO)
log.addHandler(_dl)


# ── Parsing helpers ──

def parse_int(text, default=0):
    m = re.search(r'[-+]?\d{1,3}', str(text))
    return int(m.group()) if m else default


def parse_orderbook_price(raw_value):
    """Parse an orderbook price to cents (1-99). Returns None if invalid."""
    try:
        v = float(str(raw_value).replace("$", ""))
        if v < 0: return None
        if v < 1: v *= 100
        v = int(round(v))
        if v < 1 or v > 99: return None
        return v
    except (ValueError, TypeError):
        return None
