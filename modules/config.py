"""Shared configuration, state, logging, and utility functions."""
import os, sys, json, datetime, logging, threading, re
from logging.handlers import RotatingFileHandler

# Add scripts directory to path for shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kalshi-trading-skill", "scripts"))

DEFAULTS = {
    "kalshi_api_key_id": "", "kalshi_private_key_path": "", "anthropic_api_key": "",
    "environment": "prod",
    "scan_interval_minutes": 3,
    "ai_scan_interval_multiplier": 5,
    "markets_per_scan": 40,
    "deep_dive_top_n": 2,
    "market_cache_minutes": 15,
    "target_keywords": [
        "fed", "fomc", "interest rate", "inflation", "cpi", "pce", "gdp", "recession",
        "unemployment", "jobs", "nonfarm", "payroll", "treasury", "yield", "mortgage", "gas price",
        "oil price", "temperature", "hurricane", "tornado", "rainfall", "snowfall", "weather",
        "climate", "heat", "cold", "storm", "s&p", "nasdaq", "dow",
        "sec", "regulation", "congress", "legislation", "bill", "executive order", "tariff", "trade war",
        "crypto regulation", "bitcoin etf", "stablecoin", "debt ceiling", "government shutdown",
        "sanctions", "iran", "china trade", "opec", "oil production",
        "bitcoin", "ethereum", "crypto", "price", "above", "below", "over", "under",
        "percent", "rate", "election", "vote", "poll", "primary", "candidate",
        "trump", "biden", "president", "governor", "senate", "house",
        "supreme court", "ruling", "verdict", "trial", "indict",
        "ai", "openai", "google", "apple", "meta", "amazon", "nvidia", "tesla", "microsoft",
        "earnings", "revenue", "profit", "ipo", "merger", "acquisition",
        "war", "conflict", "ceasefire", "ukraine", "russia", "israel", "nato",
        "earthquake", "wildfire", "flood", "drought",
        "fda", "drug", "vaccine", "covid", "outbreak", "disease",
        "oscar", "grammy", "emmy", "super bowl", "nfl", "nba", "mlb", "world cup",
        "spacex", "launch", "nasa", "moon",
        "tiktok", "ban", "app", "social media",
        "strike", "union", "layoff", "hiring",
        "housing", "rent", "mortgage rate", "home price",
        "immigration", "border", "visa",
        "will", "market", "close", "open", "high", "low",
    ],
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
    "cross_arb_enabled": True,
    "cross_arb_min_profit_cents": 2,
    "cross_arb_max_cost": 10.00,
    "cross_arb_match_threshold": 0.70,
    # Quick-flip scalping
    "quickflip_enabled": True,
    "quickflip_max_bet": 3.00,
    "quickflip_min_price": 3,
    "quickflip_max_price": 15,
    "quickflip_target_multiplier": 2.0,
    # Compounding / aggressive mode
    "aggressive_mode": False,
    "compounding_enabled": True,
    # Strategy toggles
    "debate_enabled": True,
    "within_arb_enabled": True,
    # Trading parameters
    "max_bet_per_trade": 8.00,
    "max_total_exposure": 35.00,
    "max_daily_trades": 15,
    "max_daily_loss": 15.00,
    "min_confidence": 65,
    "min_edge_pct": 5,
    "kelly_fraction": 0.30,
    "min_volume": 10,
    "min_close_hours": 0.5,
    "max_close_hours": 48,
    "cant_miss_edge_pct": 15,
    "cant_miss_min_confidence": 82,
    "max_price_cents": 95,
    "min_price_cents": 5,
    "taker_fee_per_contract": 0.07,
    "trade_log": "kalshi-trades.json",
    "calibration_log": "kalshi-calibration.json",
    "dashboard_port": 9000,
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
    "_risk_summary": {}, "_trades": [], "_arb_opportunities": 0,
    "poly_balance": 0, "poly_enabled": False,
    "_cross_arb_opportunities": 0, "_quickflip_active": 0,
    "_cross_platform_risk": {},
}
SHARED_LOCK = threading.Lock()

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
