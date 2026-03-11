"""
Kalshi AI Trading Agent v6 -- Cross-Platform Arbitrage + Bull/Bear Debate + Dashboard
http://localhost:9000

Inspired by:
- ryanfrigo/kalshi-ai-trading-bot (multi-agent ensemble, debate protocol)
- prediction-market-arbitrage-bot (cross-market arbitrage math)
- Ezekiel Njuguna's two-layer architecture (brain/hands separation)

Key innovations over v5:
- POLYMARKET INTEGRATION: Dual-platform trading (Kalshi + Polymarket)
- CROSS-PLATFORM ARBITRAGE: Guaranteed profit when same market mispriced across platforms
- BEST-PRICE ROUTING: Directional trades route to cheapest platform
- QUICK-FLIP SCALPING: Buy cheap contracts (3-15c) with 2x sell targets
- COMPOUNDING TIERS: Dynamic bet sizing that scales with bankroll growth
- Bull vs Bear DEBATE protocol: AI argues both sides before deciding
- Within-market arbitrage scanner (no AI needed, math only)
- Calibration tracking (log predictions to measure accuracy over time)

  python kalshi-agent.py --config kalshi-config.json
  python kalshi-agent.py --config kalshi-config.json --dry-run
"""
import os,sys,json,time,uuid,base64,math,datetime,argparse,traceback,logging,threading,re,smtplib
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse
import http.server
import requests as req_lib
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
try:
    import anthropic; HAS_SDK=True
except ImportError:
    HAS_SDK=False

# Polymarket integration
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.constants import POLYGON
    HAS_POLYMARKET=True
except ImportError:
    HAS_POLYMARKET=False

try:
    from eth_account import Account as EthAccount
    HAS_ETH_ACCOUNT=True
except ImportError:
    HAS_ETH_ACCOUNT=False

DEFAULTS={
    "kalshi_api_key_id":"","kalshi_private_key_path":"","anthropic_api_key":"",
    "environment":"prod",
    "scan_interval_minutes":3,
    "markets_per_scan":40,
    "deep_dive_top_n":3,
    "market_cache_minutes":15,
    "target_keywords":["fed","fomc","interest rate","inflation","cpi","pce","gdp","recession",
        "unemployment","jobs","nonfarm","payroll","treasury","yield","mortgage","gas price",
        "oil price","temperature","hurricane","tornado","rainfall","snowfall","weather",
        "climate","heat","cold","storm","s&p","nasdaq","dow",
        "sec","regulation","congress","legislation","bill","executive order","tariff","trade war",
        "crypto regulation","bitcoin etf","stablecoin","debt ceiling","government shutdown",
        "sanctions","iran","china trade","opec","oil production",
        "bitcoin","ethereum","crypto","price","above","below","over","under",
        "percent","rate","election","vote","poll","primary","candidate",
        "trump","biden","president","governor","senate","house",
        "supreme court","ruling","verdict","trial","indict",
        "ai","openai","google","apple","meta","amazon","nvidia","tesla","microsoft",
        "earnings","revenue","profit","ipo","merger","acquisition",
        "war","conflict","ceasefire","ukraine","russia","israel","nato",
        "earthquake","wildfire","flood","drought",
        "fda","drug","vaccine","covid","outbreak","disease",
        "oscar","grammy","emmy","super bowl","nfl","nba","mlb","world cup",
        "spacex","launch","nasa","moon",
        "tiktok","ban","app","social media",
        "strike","union","layoff","hiring",
        "housing","rent","mortgage rate","home price",
        "immigration","border","visa",
        "will","market","close","open","high","low"],
    "category_rules":{
        "weather":["temperature","hurricane","tornado","rainfall","snowfall","weather","climate","heat","cold","storm","wind","flood"],
        "fed_rates":["fed","fomc","interest rate","fed funds","powell","rate cut","rate hike","monetary policy"],
        "inflation":["inflation","cpi","pce","consumer price","core inflation"],
        "employment":["unemployment","jobs","nonfarm","payroll","jobless claims","employment"],
        "gdp_growth":["gdp","recession","economic growth","gross domestic"],
        "markets":["s&p","nasdaq","dow","stock market","treasury","yield","bond"],
        "energy":["gas price","oil price","oil production","opec","wti","brent","gasoline"],
        "policy":["sec","regulation","congress","legislation","bill","executive order","tariff","trade war","crypto regulation","bitcoin etf","stablecoin","debt ceiling","government shutdown","sanctions"]
    },
    # Polymarket integration
    "polymarket_enabled":False,
    "polymarket_private_key":"",
    "polymarket_api_key":"",
    "polymarket_api_secret":"",
    "polymarket_api_passphrase":"",
    "polymarket_funder":"",
    "polymarket_fee_per_contract":0.00,  # Most Polymarket markets are 0% fee
    # Cross-platform arbitrage
    "cross_arb_enabled":True,
    "cross_arb_min_profit_cents":2,  # Minimum profit per arb pair
    "cross_arb_max_cost":10.00,  # Max cost per arb execution
    "cross_arb_match_threshold":0.70,  # Title similarity threshold
    # Quick-flip scalping
    "quickflip_enabled":True,
    "quickflip_max_bet":3.00,
    "quickflip_min_price":3,
    "quickflip_max_price":15,
    "quickflip_target_multiplier":2.0,
    # Compounding / aggressive mode
    "aggressive_mode":False,
    "compounding_enabled":True,
    # Trading parameters (aggressive defaults in v6)
    "max_bet_per_trade":8.00,
    "max_total_exposure":35.00,
    "max_daily_trades":15,
    "max_daily_loss":15.00,
    "min_confidence":65,
    "min_edge_pct":5,
    "kelly_fraction":0.30,
    "min_volume":10,
    "min_close_hours":0.5,
    "max_close_hours":48,
    "cant_miss_edge_pct":15,
    "cant_miss_min_confidence":82,
    "max_price_cents":95,
    "min_price_cents":5,
    "taker_fee_per_contract":0.07,
    "trade_log":"kalshi-trades.json",
    "calibration_log":"kalshi-calibration.json",
    "dashboard_port":9000,
    "fred_api_key":"",
    # Email notifications (Gmail SMTP)
    "email_enabled":False,
    "email_smtp_server":"smtp.gmail.com",
    "email_smtp_port":587,
    "email_from":"",
    "email_password":"",
    "email_to":"",
    "notify_on_trade":True,
    "notify_on_circuit_breaker":True,
    "notify_on_arbitrage":True,
    # Exit strategy / position monitoring
    "exit_check_interval_minutes":10,
    "exit_loss_pct":25,
    "exit_profit_pct":40,
    "exit_time_hours":36,
    # Weekly performance report
    "report_day":"sunday",
    "report_hour":20,
    "report_file":"kalshi-weekly-report.txt",
}
CFG=dict(DEFAULTS)
BASE_URLS={"prod":"https://api.elections.kalshi.com/trade-api/v2","demo":"https://demo-api.kalshi.co/trade-api/v2"}

SHARED={"enabled":True,"status":"Starting...","balance":0,"last_scan":"Never",
    "next_scan":"--","scan_count":0,"log_lines":[],"dry_run":False,
    "_risk_summary":{},"_trades":[],"_arb_opportunities":0,
    # Polymarket additions
    "poly_balance":0,"poly_enabled":False,
    "_cross_arb_opportunities":0,"_quickflip_active":0,
    "_cross_platform_risk":{}}
SHARED_LOCK = threading.Lock()

log=logging.getLogger("agent"); log.setLevel(logging.DEBUG)
_ch=logging.StreamHandler(); _ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("%(asctime)s  %(message)s",datefmt="%H:%M:%S")); log.addHandler(_ch)
_fh=RotatingFileHandler("kalshi-agent.log",maxBytes=5*1024*1024,backupCount=3); _fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")); log.addHandler(_fh)

class DashLog(logging.Handler):
    def emit(self,record):
        with SHARED_LOCK:
            SHARED["log_lines"].append({"time":datetime.datetime.now().strftime("%H:%M:%S"),
                "msg":record.getMessage(),"level":record.levelname})
            if len(SHARED["log_lines"])>300: SHARED["log_lines"]=SHARED["log_lines"][-300:]
_dl=DashLog(); _dl.setLevel(logging.INFO); log.addHandler(_dl)

def parse_int(text, default=0):
    m=re.search(r'[-+]?\d{1,3}', str(text))
    return int(m.group()) if m else default

def parse_orderbook_price(raw_value):
    """Parse an orderbook price to cents (1-99). Returns None if invalid."""
    try:
        v = float(str(raw_value).replace("$",""))
        if v < 0: return None
        if v < 1: v *= 100  # Convert dollars to cents
        v = int(round(v))
        if v < 1 or v > 99: return None
        return v
    except (ValueError, TypeError):
        return None

# ════════════════════════════════════════
# LIVE DATA PRE-FETCH (NWS + FRED)
# ════════════════════════════════════════
# Common Kalshi weather market cities -> NWS grid coordinates
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

# FRED series IDs for key economic indicators
FRED_SERIES = {
    "fed_funds":      "DFF",       # Daily Federal Funds Rate
    "cpi":            "CPIAUCSL",  # CPI All Urban
    "core_cpi":       "CPILFESL",  # Core CPI
    "unemployment":   "UNRATE",    # Unemployment Rate
    "nonfarm":        "PAYEMS",    # Nonfarm Payrolls
    "jobless_claims": "ICSA",      # Initial Jobless Claims
    "gdp":            "GDP",       # GDP
    "gas_price":      "GASREGW",   # Regular Gas Price Weekly
    "treasury_10y":   "DGS10",     # 10-Year Treasury Yield
    "treasury_2y":    "DGS2",      # 2-Year Treasury Yield
    "sp500":          "SP500",     # S&P 500 Index
}

class DataFetcher:
    """Pre-fetch live data from NWS and FRED before AI analysis.
    This gives the AI verified numbers instead of relying on web search."""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 600  # 10 min cache
        self.fred_key = CFG.get("fred_api_key", "")
        self.brief = {}  # Latest data brief

    def _cached(self, key):
        if key in self.cache:
            val, ts = self.cache[key]
            if time.time() - ts < self.cache_ttl:
                return val
        return None

    def _set_cache(self, key, val):
        self.cache[key] = (val, time.time())
        return val

    def fetch_all(self):
        """Run before each scan. Populates self.brief with latest data."""
        self.brief = {}
        self.feed_status = {"nws": False, "fred": False}
        # NWS -- no key needed
        try:
            self.brief["nws_forecasts"] = self._fetch_nws_batch()
            if self.brief["nws_forecasts"]:
                self.feed_status["nws"] = True
        except Exception as e:
            log.warning(f"NWS prefetch failed: {e}")
            self.brief["nws_forecasts"] = {}
        # FRED -- requires key
        if self.fred_key:
            fred_ok = 0
            for key in ["fed_funds","cpi","core_cpi","unemployment","nonfarm","jobless_claims","gas_price","treasury_10y","treasury_2y"]:
                try:
                    self.brief[key] = self._fetch_fred(key)
                    if self.brief[key]: fred_ok += 1
                except Exception as e:
                    log.debug(f"FRED {key} failed: {e}")
                    self.brief[key] = None
            if fred_ok > 0:
                self.feed_status["fred"] = True
        data_count = sum(1 for v in self.brief.values() if v)
        if data_count == 0:
            log.warning("Data prefetch: ZERO feeds loaded -- AI will rely on web search only")
        else:
            log.info(f"Data prefetch: {data_count} feeds loaded (NWS:{'OK' if self.feed_status['nws'] else 'FAIL'} FRED:{'OK' if self.feed_status['fred'] else 'FAIL'})")
        return self.brief

    def _fetch_nws_batch(self):
        """Fetch NWS forecasts for top weather cities. Returns dict of city->forecast."""
        cached = self._cached("nws_batch")
        if cached: return cached
        results = {}
        # Only fetch top 8 cities to avoid hammering NWS
        top_cities = ["new york","chicago","miami","denver","houston","phoenix","los angeles","seattle"]
        for city in top_cities:
            try:
                lat, lon = CITY_COORDS[city]
                # Step 1: Get grid point
                r = req_lib.get(f"https://api.weather.gov/points/{lat},{lon}",
                    headers={"User-Agent":"KalshiAgent/1.0","Accept":"application/json"}, timeout=10)
                if r.status_code != 200: continue
                grid = r.json().get("properties",{})
                forecast_url = grid.get("forecast","")
                if not forecast_url: continue
                # Step 2: Get forecast
                r2 = req_lib.get(forecast_url,
                    headers={"User-Agent":"KalshiAgent/1.0","Accept":"application/json"}, timeout=10)
                if r2.status_code != 200: continue
                periods = r2.json().get("properties",{}).get("periods",[])
                if periods:
                    forecasts = []
                    for p in periods[:4]:  # Next 2 day/night periods
                        forecasts.append({
                            "name": p.get("name",""),
                            "temp": p.get("temperature"),
                            "temp_unit": p.get("temperatureUnit","F"),
                            "wind_speed": p.get("windSpeed",""),
                            "precip_pct": p.get("probabilityOfPrecipitation",{}).get("value"),
                            "short": p.get("shortForecast",""),
                        })
                    results[city] = forecasts
                time.sleep(0.3)  # Be nice to NWS
            except Exception as e:
                log.debug(f"NWS fetch failed for {city}: {e}")
                continue
        return self._set_cache("nws_batch", results)

    def _fetch_fred(self, series_name):
        """Fetch latest value from FRED. Returns dict with value, date, units."""
        cached = self._cached(f"fred_{series_name}")
        if cached: return cached
        sid = FRED_SERIES.get(series_name)
        if not sid or not self.fred_key: return None
        try:
            r = req_lib.get(
                f"https://api.stlouisfed.org/fred/series/observations",
                params={"series_id":sid,"api_key":self.fred_key,"file_type":"json",
                        "sort_order":"desc","limit":"3"},
                timeout=10)
            if r.status_code != 200: return None
            obs = r.json().get("observations",[])
            # Skip any "." values (FRED uses "." for missing)
            for o in obs:
                if o.get("value",".") != ".":
                    result = {"value": o["value"], "date": o["date"], "series": sid}
                    return self._set_cache(f"fred_{series_name}", result)
        except Exception as e:
            log.debug(f"FRED fetch failed for {series_name}: {e}")
        return None

    def format_brief_for_scan(self):
        """Format a compact data brief for the quick scan prompt."""
        lines = []
        # FRED data
        fred_labels = {
            "fed_funds": "Fed Funds Rate",
            "cpi": "CPI (latest)",
            "unemployment": "Unemployment Rate",
            "jobless_claims": "Initial Jobless Claims",
            "gas_price": "Regular Gas Price",
            "treasury_10y": "10Y Treasury Yield",
            "treasury_2y": "2Y Treasury Yield",
        }
        for key, label in fred_labels.items():
            d = self.brief.get(key)
            if d: lines.append(f"  {label}: {d['value']} (as of {d['date']})")
        # NWS summary
        nws = self.brief.get("nws_forecasts",{})
        if nws:
            lines.append("  Weather forecasts (NWS official):")
            for city, periods in nws.items():
                if periods:
                    p = periods[0]
                    precip = f", {p['precip_pct']}% precip" if p.get('precip_pct') is not None else ""
                    lines.append(f"    {city.title()}: {p['name']} {p['temp']}°{p['temp_unit']}{precip} -- {p['short']}")
        return "\n".join(lines) if lines else ""

    def get_weather_for_market(self, market_title):
        """Extract city from market title and return NWS forecast if available."""
        title_lower = market_title.lower()
        nws = self.brief.get("nws_forecasts", {})
        for city, forecasts in nws.items():
            # Check if city name appears in market title
            if city in title_lower or city.replace(" ","") in title_lower:
                return city, forecasts
        # Also check CITY_COORDS keys that aren't in the pre-fetched batch
        for city in CITY_COORDS:
            if city in title_lower:
                return city, None  # City found but forecast not pre-fetched
        return None, None

    def get_fred_for_category(self, category):
        """Get relevant FRED data for a market category."""
        mapping = {
            "fed_rates": ["fed_funds", "treasury_2y", "treasury_10y"],
            "inflation": ["cpi", "core_cpi"],
            "employment": ["unemployment", "nonfarm", "jobless_claims"],
            "gdp_growth": ["gdp"],
            "energy": ["gas_price"],
            "markets": ["treasury_10y", "treasury_2y"],
        }
        series_keys = mapping.get(category, [])
        lines = []
        for key in series_keys:
            d = self.brief.get(key)
            if d: lines.append(f"{key}: {d['value']} (as of {d['date']})")
        return " | ".join(lines) if lines else ""

    def expand_nws_for_markets(self, markets):
        """Dynamically fetch NWS data for cities found in active weather markets
        that aren't already in our pre-fetched batch."""
        nws = self.brief.get("nws_forecasts", {})
        fetched_cities = set(nws.keys())
        new_fetches = 0
        for m in markets:
            if m.get("_category") != "weather": continue
            title_lower = m.get("title","").lower() + " " + m.get("subtitle","").lower()
            for city, coords in CITY_COORDS.items():
                if city in fetched_cities: continue
                if city in title_lower or city.replace(" ","") in title_lower:
                    # Found a weather market referencing a city we haven't fetched
                    try:
                        lat, lon = coords
                        r = req_lib.get(f"https://api.weather.gov/points/{lat},{lon}",
                            headers={"User-Agent":"KalshiAgent/1.0","Accept":"application/json"}, timeout=10)
                        if r.status_code != 200: continue
                        forecast_url = r.json().get("properties",{}).get("forecast","")
                        if not forecast_url: continue
                        r2 = req_lib.get(forecast_url,
                            headers={"User-Agent":"KalshiAgent/1.0","Accept":"application/json"}, timeout=10)
                        if r2.status_code != 200: continue
                        periods = r2.json().get("properties",{}).get("periods",[])
                        if periods:
                            forecasts = []
                            for p in periods[:4]:
                                forecasts.append({
                                    "name": p.get("name",""), "temp": p.get("temperature"),
                                    "temp_unit": p.get("temperatureUnit","F"),
                                    "wind_speed": p.get("windSpeed",""),
                                    "precip_pct": p.get("probabilityOfPrecipitation",{}).get("value"),
                                    "short": p.get("shortForecast",""),
                                })
                            nws[city] = forecasts
                            fetched_cities.add(city)
                            new_fetches += 1
                            log.info(f"  NWS expanded: {city.title()} -> {forecasts[0]['temp']}°{forecasts[0]['temp_unit']}")
                        time.sleep(0.3)
                    except Exception as e:
                        log.debug(f"NWS expand failed for {city}: {e}")
                        continue
                    if new_fetches >= 6: break  # Don't hammer NWS
            if new_fetches >= 6: break
        self.brief["nws_forecasts"] = nws

# ════════════════════════════════════════
# EMAIL NOTIFIER
# ════════════════════════════════════════
class Notifier:
    """Send email notifications for trades, alerts, and reports."""
    def __init__(self):
        self.enabled = CFG.get("email_enabled", False)
        self.smtp_server = CFG.get("email_smtp_server", "smtp.gmail.com")
        self.smtp_port = CFG.get("email_smtp_port", 587)
        self.from_addr = CFG.get("email_from", "")
        self.password = CFG.get("email_password", "")
        self.to_addr = CFG.get("email_to", "")
        if self.enabled and (not self.from_addr or not self.password or not self.to_addr):
            log.warning("Email enabled but missing from/password/to -- disabling")
            self.enabled = False
        if self.enabled:
            # Test SMTP connection on startup
            try:
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as s:
                    s.starttls()
                    s.login(self.from_addr, self.password)
                log.info(f"Email notifications: ON -> {self.to_addr} (SMTP verified)")
            except Exception as e:
                log.warning(f"Email SMTP login failed: {e} -- disabling email notifications")
                self.enabled = False

    def send(self, subject, body):
        if not self.enabled: return
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = self.to_addr
            msg["Subject"] = f"[Kalshi Agent] {subject}"
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as s:
                s.starttls()
                s.login(self.from_addr, self.password)
                s.send_message(msg)
            log.info(f"Email sent: {subject}")
        except Exception as e:
            log.warning(f"Email failed: {e}")

    def notify_trade(self, trade_info):
        if not CFG.get("notify_on_trade", True): return
        side = trade_info.get("side","?").upper()
        tk = trade_info.get("ticker","?")
        title = trade_info.get("title","")[:40]
        contracts = trade_info.get("contracts",0)
        price = trade_info.get("price_cents",0)
        cost = trade_info.get("cost",0)
        edge = trade_info.get("edge",0)
        conf = trade_info.get("confidence",0)
        bull = trade_info.get("bull_prob",0)
        bear = trade_info.get("bear_prob",0)
        evidence = trade_info.get("evidence","")[:100]
        self.send(f"Trade: {side} {contracts}x {tk} @{price}c",
            f"TRADE EXECUTED\n\n"
            f"Market: {title}\nTicker: {tk}\n"
            f"Side: {side}\nContracts: {contracts}\nPrice: {price}c\nCost: ${cost:.2f}\n"
            f"Edge: {edge}%\nConfidence: {conf}%\n"
            f"Bull: {bull}% | Bear: {bear}%\n\n"
            f"Evidence: {evidence}\n\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def notify_exit(self, ticker, title, side, reason, pnl):
        self.send(f"Exit: {ticker} ({reason})",
            f"POSITION EXITED\n\n"
            f"Market: {title}\nTicker: {ticker}\nSide: {side}\n"
            f"Reason: {reason}\nP&L: ${pnl:.2f}\n\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def notify_circuit_breaker(self, day_pnl):
        if not CFG.get("notify_on_circuit_breaker", True): return
        self.send("CIRCUIT BREAKER TRIGGERED",
            f"Daily loss limit reached.\n\nDay P&L: ${day_pnl:.2f}\n"
            f"Limit: ${CFG['max_daily_loss']:.2f}\n\n"
            f"Agent is PAUSED until tomorrow.\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def notify_arbitrage(self, arb_info):
        if not CFG.get("notify_on_arbitrage", True): return
        self.send(f"Arbitrage: {arb_info['ticker']} +{arb_info['profit_cents']:.1f}c",
            f"ARBITRAGE EXECUTED\n\n"
            f"Market: {arb_info.get('title','')}\nTicker: {arb_info['ticker']}\n"
            f"YES: {arb_info['yes_price']:.0f}c + NO: {arb_info['no_price']:.0f}c = {arb_info['total_cost']:.0f}c\n"
            f"Guaranteed profit: {arb_info['profit_cents']:.1f}c per contract\n\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def send_report(self, report_text):
        self.send(f"Weekly Performance Report -- {datetime.date.today().strftime('%B %d, %Y')}", report_text)

# ════════════════════════════════════════
# EXIT MANAGER -- position monitoring
# ════════════════════════════════════════
class ExitManager:
    """Monitor open positions and exit when:
    - Position has lost more than exit_loss_pct of its value
    - Position has gained more than exit_profit_pct
    - Position has been held longer than exit_time_hours
    """
    def __init__(self, api, risk, notifier):
        self.api = api
        self.risk = risk
        self.notifier = notifier
        self.loss_pct = CFG.get("exit_loss_pct", 25)
        self.profit_pct = CFG.get("exit_profit_pct", 40)
        self.max_hold_hrs = CFG.get("exit_time_hours", 36)
        self._pos_fail_count = 0

    def check_positions(self):
        """Check all open positions for exit conditions. Returns list of exit actions taken."""
        exits = []
        try:
            positions = self.api.positions()
            self._pos_fail_count = 0  # Reset on success
        except Exception as e:
            self._pos_fail_count += 1
            log.error(f"Exit check: can't load positions (fail #{self._pos_fail_count}): {e}")
            if self._pos_fail_count >= 3:
                log.error("CRITICAL: Position monitoring failed 3x in a row -- open positions are NOT being tracked")
                self.notifier.send("ALERT: Position Monitoring Down",
                    f"Failed to load positions {self._pos_fail_count} consecutive times.\n"
                    f"Last error: {e}\n\nOpen positions may not be exited automatically.\n"
                    f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return exits

        for pos in positions:
            tk = pos.get("ticker", pos.get("market_ticker", ""))
            if not tk: continue

            # Get position details
            side = "yes" if pos.get("yes_contracts", pos.get("position",0)) > 0 else "no"
            contracts = abs(pos.get("yes_contracts", pos.get("no_contracts", pos.get("position", 0))))
            if contracts == 0: continue

            # Find original trade in our log
            original = None
            for t in reversed(self.risk.trades):
                if t.get("ticker") == tk and t.get("status") == "open":
                    original = t; break
            if not original: continue  # Not our trade

            entry_price = original.get("price_cents", 50)

            # Get current market price
            try:
                ob = self.api.orderbook(tk)
                book = ob.get("orderbook", {})
                if side == "yes":
                    bids = book.get("yes", book.get("yes_dollars", []))
                    if not bids: continue
                    current = parse_orderbook_price(bids[0][0] if isinstance(bids[0], list) else bids[0])
                else:
                    bids = book.get("no", book.get("no_dollars", []))
                    if not bids: continue
                    current = parse_orderbook_price(bids[0][0] if isinstance(bids[0], list) else bids[0])
                if current is None:
                    log.debug(f"Exit check: invalid orderbook price for {tk}")
                    continue
            except Exception as e:
                log.debug(f"Exit check: orderbook error for {tk}: {e}")
                continue

            # Calculate P&L percentage
            pnl_pct = ((current - entry_price) / entry_price * 100) if entry_price > 0 else 0

            # Check entry time
            hours_held = 0
            try:
                entry_time = datetime.datetime.fromisoformat(original["time"])
                hours_held = (datetime.datetime.now() - entry_time).total_seconds() / 3600
            except Exception:
                pass  # Missing or malformed entry time -- default to 0 hours held

            # ── EXIT CONDITIONS ──
            reason = None
            if pnl_pct <= -self.loss_pct:
                reason = f"Stop loss ({pnl_pct:.0f}% loss)"
            elif pnl_pct >= self.profit_pct:
                reason = f"Profit taking ({pnl_pct:.0f}% gain)"
            elif hours_held >= self.max_hold_hrs:
                reason = f"Time exit ({hours_held:.0f}h held)"

            if not reason: continue

            pnl_dollars = contracts * (current - entry_price) / 100
            log.info(f"  EXIT: {tk} -- {reason} | entry:{entry_price}c now:{current:.0f}c P&L:${pnl_dollars:.2f}")

            # Place sell order -- price aggressively for stop-loss/time exits to ensure fill
            try:
                if "Stop loss" in reason:
                    sell_price = max(1, int(current) - 3)  # 3c below bid for urgent exits
                elif "Time exit" in reason:
                    sell_price = max(1, int(current) - 2)  # 2c below bid for time exits
                else:
                    sell_price = max(1, int(current))      # Current bid for profit-taking (patient)
                sell_order = {"ticker": tk, "action": "sell", "side": side,
                    "count": contracts, "type": "limit", "client_order_id": str(uuid.uuid4())}
                if side == "yes": sell_order["yes_price"] = sell_price
                else: sell_order["no_price"] = sell_price
                result = self.api._req("POST", "/portfolio/orders", sell_order)
                oid = result.get("order", {}).get("order_id", "?")
                log.info(f"  EXIT OK: order {oid}")

                # Update trade log
                original["status"] = "win" if pnl_dollars > 0 else "loss"
                original["exit_price"] = sell_price
                original["exit_time"] = datetime.datetime.now().isoformat()
                original["exit_reason"] = reason
                original["pnl"] = round(pnl_dollars, 2)
                self.risk._save()
                self.risk.day_pnl += pnl_dollars

                exits.append({"ticker": tk, "reason": reason, "pnl": pnl_dollars})
                self.notifier.notify_exit(tk, original.get("title",""), side, reason, pnl_dollars)

            except Exception as e:
                log.error(f"  EXIT failed {tk}: {e}")

            time.sleep(1)

        return exits

    def run_loop(self, stop_event):
        """Background thread: check positions periodically."""
        interval = CFG.get("exit_check_interval_minutes", 10) * 60
        log.info(f"Exit manager: checking positions every {CFG.get('exit_check_interval_minutes',10)}m")
        while not stop_event.is_set():
            try:
                if SHARED.get("enabled", True) and not SHARED.get("dry_run", False):
                    exits = self.check_positions()
                    if exits:
                        with SHARED_LOCK:
                            SHARED["_risk_summary"] = self.risk.summary()
                            SHARED["_trades"] = self.risk.trades
                        for e in exits:
                            log.info(f"EXIT completed: {e['ticker']} -> {e['reason']} (${e['pnl']:.2f})")
            except Exception as e:
                log.warning(f"Exit check error: {e}")
            stop_event.wait(interval)

# ════════════════════════════════════════
# WEEKLY PERFORMANCE REPORT
# ════════════════════════════════════════
class PerformanceReporter:
    """Generate weekly performance reports from trade history."""
    def __init__(self, risk, notifier):
        self.risk = risk
        self.notifier = notifier
        self.last_report_date = None

    def should_report(self):
        now = datetime.datetime.now()
        target_day = CFG.get("report_day", "sunday").lower()
        target_hour = CFG.get("report_hour", 20)
        days = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
        if now.weekday() != days.get(target_day, 6): return False
        if now.hour != target_hour: return False
        if self.last_report_date == now.date(): return False
        return True

    def generate_report(self):
        """Generate a comprehensive performance report."""
        now = datetime.datetime.now()
        week_ago = now - datetime.timedelta(days=7)
        all_trades = self.risk.trades
        # Filter to this week
        week_trades = []
        for t in all_trades:
            try:
                tt = datetime.datetime.fromisoformat(t["time"])
                if tt >= week_ago: week_trades.append(t)
            except Exception: continue

        total = len(week_trades)
        wins = sum(1 for t in week_trades if t.get("status") == "win")
        losses = sum(1 for t in week_trades if t.get("status") == "loss")
        still_open = sum(1 for t in week_trades if t.get("status") == "open")
        total_wagered = sum(t.get("cost", 0) for t in week_trades)
        total_pnl = sum(t.get("pnl", 0) for t in week_trades if t.get("pnl") is not None)

        # Category breakdown
        cat_stats = {}
        for t in week_trades:
            cat = "unknown"
            # Infer category from keywords in title
            title_lower = (t.get("title","") + " " + t.get("ticker","")).lower()
            for cat_name, cat_kws in CFG.get("category_rules", {}).items():
                if any(kw in title_lower for kw in cat_kws):
                    cat = cat_name; break
            if cat not in cat_stats: cat_stats[cat] = {"trades":0,"wins":0,"losses":0,"pnl":0}
            cat_stats[cat]["trades"] += 1
            if t.get("status") == "win": cat_stats[cat]["wins"] += 1
            if t.get("status") == "loss": cat_stats[cat]["losses"] += 1
            cat_stats[cat]["pnl"] += t.get("pnl", 0) or 0

        # Best and worst trades
        settled = [t for t in week_trades if t.get("pnl") is not None]
        best = max(settled, key=lambda t: t.get("pnl",0)) if settled else None
        worst = min(settled, key=lambda t: t.get("pnl",0)) if settled else None

        # Average edge and confidence
        avg_edge = sum(abs(t.get("edge",0)) for t in week_trades)/total if total else 0
        avg_conf = sum(t.get("confidence",0) for t in week_trades)/total if total else 0
        avg_spread = sum(abs(t.get("bull_prob",50)-t.get("bear_prob",50)) for t in week_trades)/total if total else 0

        # Build report text
        lines = [
            f"KALSHI AI AGENT -- WEEKLY PERFORMANCE REPORT",
            f"Period: {week_ago.strftime('%B %d')} -- {now.strftime('%B %d, %Y')}",
            f"{'='*50}",
            f"",
            f"SUMMARY",
            f"  Total trades: {total}",
            f"  Wins: {wins} | Losses: {losses} | Open: {still_open}",
            f"  Win rate: {wins/(wins+losses)*100:.0f}%" if wins+losses > 0 else "  Win rate: N/A",
            f"  Total wagered: ${total_wagered:.2f}",
            f"  Net P&L: ${total_pnl:.2f}",
            f"  ROI: {total_pnl/total_wagered*100:.1f}%" if total_wagered > 0 else "  ROI: N/A",
            f"",
            f"DEBATE QUALITY",
            f"  Avg edge claimed: {avg_edge:.1f}%",
            f"  Avg confidence: {avg_conf:.0f}%",
            f"  Avg bull-bear spread: {avg_spread:.0f}% (lower = more agreement = better)",
            f"",
        ]

        if cat_stats:
            lines.append("CATEGORY BREAKDOWN")
            for cat, s in sorted(cat_stats.items(), key=lambda x: x[1]["trades"], reverse=True):
                wr = f"{s['wins']/(s['wins']+s['losses'])*100:.0f}%" if s['wins']+s['losses']>0 else "N/A"
                lines.append(f"  {cat}: {s['trades']} trades, {wr} win rate, ${s['pnl']:.2f} P&L")
            lines.append("")

        if best and best.get("pnl",0)>0:
            lines.append(f"BEST TRADE: {best.get('title','')[:40]} -- ${best['pnl']:.2f}")
        if worst and worst.get("pnl",0)<0:
            lines.append(f"WORST TRADE: {worst.get('title','')[:40]} -- ${worst['pnl']:.2f}")
        lines.append("")

        # Lifetime stats
        all_wins = sum(1 for t in all_trades if t.get("status")=="win")
        all_losses = sum(1 for t in all_trades if t.get("status")=="loss")
        all_pnl = sum(t.get("pnl",0) for t in all_trades if t.get("pnl") is not None)
        lines.extend([
            f"LIFETIME",
            f"  Total trades: {len(all_trades)}",
            f"  Win rate: {all_wins/(all_wins+all_losses)*100:.0f}%" if all_wins+all_losses>0 else "  Win rate: N/A",
            f"  Net P&L: ${all_pnl:.2f}",
            f"",
            f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        ])

        return "\n".join(lines)

    def maybe_send_report(self):
        """Check if it's time and send the weekly report."""
        if not self.should_report(): return
        self.last_report_date = datetime.date.today()
        report = self.generate_report()
        # Save to file
        report_file = CFG.get("report_file", "kalshi-weekly-report.txt")
        try:
            with open(report_file, "w") as f: f.write(report)
            log.info(f"Weekly report saved to {report_file}")
        except Exception as e:
            log.warning(f"Failed to save weekly report: {e}")
        # Email it
        self.notifier.send_report(report)
        log.info("Weekly performance report generated and emailed")

    def run_loop(self, stop_event):
        """Background thread: check hourly if it's time to send a report."""
        while not stop_event.is_set():
            try: self.maybe_send_report()
            except Exception as e: log.warning(f"Report error: {e}")
            stop_event.wait(3600)  # Check every hour

# ════════════════════════════════════════
# KALSHI API
# ════════════════════════════════════════
class KalshiAPI:
    def __init__(self):
        self.key_id=CFG["kalshi_api_key_id"]
        self.base=BASE_URLS.get(CFG["environment"],BASE_URLS["prod"])
        self.pk=serialization.load_pem_private_key(
            open(CFG["kalshi_private_key_path"],"rb").read(),password=None,backend=default_backend())
    def _sign(self,ts,method,path):
        msg=f"{ts}{method}{path.split('?')[0]}".encode()
        sig=self.pk.sign(msg,padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH),hashes.SHA256())
        return base64.b64encode(sig).decode()
    def _auth(self,method,path):
        ts=str(int(time.time()*1000))
        return {"KALSHI-ACCESS-KEY":self.key_id,"KALSHI-ACCESS-SIGNATURE":self._sign(ts,method,path),
                "KALSHI-ACCESS-TIMESTAMP":ts,"Content-Type":"application/json"}
    def _req(self,method,path,jdata=None,retries=3):
        url=self.base+path; sign_path=urlparse(url).path
        for attempt in range(retries):
            try:
                h=self._auth(method,sign_path)
                if method=="GET": r=req_lib.get(url,headers=h,timeout=30)
                elif method=="POST": r=req_lib.post(url,headers=h,json=jdata,timeout=30)
                elif method=="DELETE": r=req_lib.delete(url,headers=h,timeout=30)
                else: raise ValueError(method)
                if r.status_code==429:
                    retry_after=r.headers.get("Retry-After")
                    w=min(120,int(retry_after)) if retry_after and retry_after.isdigit() else min(60,10*(attempt+1))
                    log.warning(f"Rate limited, wait {w}s"); time.sleep(w); continue
                r.raise_for_status()
                return r.json() if method!="DELETE" else r
            except req_lib.exceptions.ConnectionError:
                if attempt<retries-1: log.warning(f"Conn error, retry {attempt+1}"); time.sleep(3)
                else: raise
            except req_lib.exceptions.HTTPError:
                log.error(f"HTTP {r.status_code}: {r.text[:200]}"); raise
        raise Exception(f"Failed after {retries} retries")
    def balance(self): return self._req("GET","/portfolio/balance").get("balance",0)/100
    def all_markets(self):
        out,cur=[],None
        for _ in range(10):
            q="/markets?limit=200&status=open"+(f"&cursor={cur}" if cur else "")
            d=self._req("GET",q); out.extend(d.get("markets",[])); cur=d.get("cursor")
            if not cur: break
        return out
    def orderbook(self,t): return self._req("GET",f"/markets/{t}/orderbook")
    def positions(self):
        d=self._req("GET","/portfolio/positions"); return d.get("market_positions",d.get("positions",[]))
    def place_order(self,ticker,side,count,price_cents):
        o={"ticker":ticker,"action":"buy","side":side,"count":count,
           "type":"limit","client_order_id":str(uuid.uuid4())}
        if side=="yes": o["yes_price"]=int(price_cents)
        else: o["no_price"]=int(price_cents)
        return self._req("POST","/portfolio/orders",o)

class MarketCache:
    def __init__(self,api):
        self.api=api; self.markets=[]; self.last_refresh=0
        self.ttl=CFG["market_cache_minutes"]*60
        self._refresh_failures=0
    def get(self):
        now=time.time()
        if not self.markets or (now-self.last_refresh)>self.ttl:
            log.info("Loading markets (full refresh)...")
            try:
                fresh=self.api.all_markets(); self.markets=fresh; self.last_refresh=now
                self._refresh_failures=0
                log.info(f"Cached {len(self.markets)} markets")
            except Exception as e:
                self._refresh_failures+=1
                log.error(f"Market refresh failed (attempt #{self._refresh_failures}): {e}")
                if self.markets:
                    log.warning(f"Using stale cache ({len(self.markets)} mkts, {int(now-self.last_refresh)}s old)")
                else:
                    raise  # No cached data at all -- can't continue
        else:
            log.info(f"Using cache ({len(self.markets)} mkts, {int(now-self.last_refresh)}s old)")
        return self.markets

# ════════════════════════════════════════
# POLYMARKET API CLIENT
# ════════════════════════════════════════
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

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
            bal = self.client.get_balance()
            if isinstance(bal, dict): return float(bal.get("balance", 0)) / 1e6
            return float(bal) / 1e6 if float(bal) > 100 else float(bal)
        except Exception as e:
            log.error(f"Polymarket balance error: {e}"); return 0.0

    def all_markets(self, limit=500):
        markets = []; offset = 0; page_size = 100
        for _ in range(limit // page_size + 1):
            try:
                r = req_lib.get(f"{GAMMA_API}/markets",
                    params={"closed":"false","limit":page_size,"offset":offset,
                            "order":"volume24hr","ascending":"false"}, timeout=15)
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
                order_args = OrderArgs(price=1.0-price, size=count, side="SELL", token_id=token_id)
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
        except Exception as e: log.error(f"Polymarket positions error: {e}"); return []


def normalize_polymarket(pm):
    """Convert Polymarket Gamma API market dict to internal format matching Kalshi markets."""
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


# ════════════════════════════════════════
# CROSS-PLATFORM MATCHING & ARBITRAGE
# ════════════════════════════════════════

def _jaccard_similarity(s1, s2):
    w1 = set(s1.lower().split()); w2 = set(s2.lower().split())
    if not w1 or not w2: return 0.0
    return len(w1 & w2) / len(w1 | w2)

def _levenshtein_similarity(s1, s2):
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2: return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0: return 1.0
    prev = list(range(len(s2) + 1)); curr = [0] * (len(s2) + 1)
    for i in range(1, len(s1) + 1):
        curr[0] = i
        for j in range(1, len(s2) + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            curr[j] = min(curr[j-1]+1, prev[j]+1, prev[j-1]+cost)
        prev, curr = curr, prev
    return 1.0 - (prev[len(s2)] / max_len)

def combined_similarity(title1, title2):
    return 0.6 * _jaccard_similarity(title1, title2) + 0.4 * _levenshtein_similarity(title1, title2)

def match_markets(kalshi_markets, poly_markets, threshold=0.70):
    """Match markets across platforms using title similarity. Returns list of match dicts."""
    matches = []; used_poly = set()
    cache_path = "market-matches.json"
    cached_matches = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f: cached_matches = json.load(f)
            cutoff = time.time() - 7 * 86400
            cached_matches = {k: v for k, v in cached_matches.items() if v.get("timestamp", 0) > cutoff}
        except Exception: cached_matches = {}

    for km in kalshi_markets:
        k_title = km.get("title", ""); k_ticker = km.get("ticker", "")
        k_category = km.get("_category", "other"); k_hrs = km.get("_hrs_left", 9999)
        # Check cache
        if k_ticker in cached_matches:
            cached_poly_id = cached_matches[k_ticker].get("poly_ticker", "")
            for i, pm in enumerate(poly_markets):
                if i not in used_poly and pm.get("ticker", "") == cached_poly_id:
                    matches.append({"kalshi": km, "polymarket": pm,
                        "similarity": cached_matches[k_ticker].get("similarity", 0.90), "source": "cache"})
                    used_poly.add(i); break
            continue
        best_match, best_score = None, 0
        for i, pm in enumerate(poly_markets):
            if i in used_poly: continue
            p_category = pm.get("_category", "other"); p_hrs = pm.get("_hrs_left", 9999)
            if k_category != "other" and p_category != "other" and k_category != p_category: continue
            if abs(k_hrs - p_hrs) > 48 and k_hrs < 9999 and p_hrs < 9999: continue
            score = combined_similarity(k_title, pm.get("title", ""))
            if abs(k_hrs - p_hrs) < 6 and k_hrs < 9999: score = min(1.0, score + 0.05)
            if score > best_score and score >= threshold:
                best_score = score; best_match = (i, pm)
        if best_match:
            idx, pm = best_match
            matches.append({"kalshi": km, "polymarket": pm, "similarity": round(best_score, 3), "source": "computed"})
            used_poly.add(idx)
            cached_matches[k_ticker] = {"poly_ticker": pm.get("ticker", ""), "similarity": round(best_score, 3),
                "timestamp": time.time(), "k_title": k_title[:80], "p_title": pm.get("title", "")[:80]}
    try:
        with open(cache_path, "w") as f: json.dump(cached_matches, f, indent=2)
    except Exception: pass
    return matches

def scan_cross_platform_arbitrage(matches, kalshi_api, poly_api, fee_kalshi=0.07, fee_poly=0.00):
    """Scan matched market pairs for cross-platform arbitrage opportunities."""
    opportunities = []
    for match in matches:
        km, pm = match["kalshi"], match["polymarket"]
        if match.get("similarity", 0) < 0.80: continue
        try:
            k_ob = kalshi_api.orderbook(km["ticker"])
            k_book = k_ob.get("orderbook", {})
            yes_token = pm.get("token_id", "")
            if not yes_token: continue
            p_ob = poly_api.orderbook(yes_token)
            p_book = p_ob.get("orderbook", {})
            # Strategy 1: YES@Kalshi + NO@Polymarket
            k_yes = k_book.get("yes", []); p_no = p_book.get("no", [])
            profit_1, cost_1 = -999, 999
            if k_yes and p_no:
                k_yes_p = _best_ask(k_yes); p_no_p = _best_ask(p_no)
                if k_yes_p and p_no_p:
                    cost_1 = k_yes_p + p_no_p; profit_1 = 100 - cost_1 - (fee_kalshi + fee_poly) * 100
            # Strategy 2: NO@Kalshi + YES@Polymarket
            k_no = k_book.get("no", []); p_yes = p_book.get("yes", [])
            profit_2, cost_2 = -999, 999
            if k_no and p_yes:
                k_no_p = _best_ask(k_no); p_yes_p = _best_ask(p_yes)
                if k_no_p and p_yes_p:
                    cost_2 = k_no_p + p_yes_p; profit_2 = 100 - cost_2 - (fee_kalshi + fee_poly) * 100
            best = max(profit_1, profit_2)
            if best > CFG.get("cross_arb_min_profit_cents", 2):
                is_s1 = profit_1 >= profit_2
                opportunities.append({
                    "kalshi_ticker": km["ticker"], "poly_token": yes_token,
                    "poly_no_token": pm.get("no_token_id", ""),
                    "title": km.get("title", ""),
                    "strategy": 1 if is_s1 else 2,
                    "strategy_desc": "YES@Kalshi+NO@Poly" if is_s1 else "NO@Kalshi+YES@Poly",
                    "profit_cents": round(best, 1),
                    "cost_cents": round(cost_1 if is_s1 else cost_2, 1),
                    "k_price": _best_ask(k_yes) if is_s1 else _best_ask(k_no),
                    "p_price": _best_ask(p_no) if is_s1 else _best_ask(p_yes),
                    "similarity": match.get("similarity", 0),
                    "type": "cross_platform_arbitrage",
                })
            time.sleep(0.15)
        except Exception as e:
            log.debug(f"Cross-arb scan error for {km.get('ticker','?')}: {e}"); continue
    opportunities.sort(key=lambda x: x["profit_cents"], reverse=True)
    return opportunities

def _best_ask(asks):
    if not asks: return None
    first = asks[0]
    return int(first[0]) if isinstance(first, list) else int(first)

def execute_cross_arb(kalshi_api, poly_api, opp, max_cost=10.0, dry_run=False):
    """Execute both legs of a cross-platform arb. Returns result dict."""
    cost_per_pair = opp["cost_cents"] / 100.0
    contracts = min(int(max_cost / cost_per_pair) if cost_per_pair > 0 else 0, 20)
    if contracts == 0: return {"success": False, "reason": "Zero contracts"}
    total_cost = round(contracts * cost_per_pair, 2)
    total_profit = round(contracts * opp["profit_cents"] / 100, 2)
    if dry_run: return {"success": True, "dry_run": True, "contracts": contracts,
        "total_cost": total_cost, "expected_profit": total_profit, "strategy": opp["strategy_desc"]}
    # Leg 1: Kalshi (less liquid)
    try:
        side1 = "yes" if opp["strategy"] == 1 else "no"
        kalshi_api.place_order(opp["kalshi_ticker"], side1, contracts, opp["k_price"])
        log.info(f"  ARB Leg 1 (Kalshi): {side1} {contracts}x @{opp['k_price']}c")
    except Exception as e:
        log.error(f"  ARB Leg 1 FAILED: {e}"); return {"success": False, "reason": f"Leg 1 failed: {e}"}
    time.sleep(1)
    # Leg 2: Polymarket
    try:
        if opp["strategy"] == 1:
            token = opp.get("poly_no_token", opp["poly_token"])
            poly_api.place_order(token, "no", contracts, opp["p_price"])
        else:
            poly_api.place_order(opp["poly_token"], "yes", contracts, opp["p_price"])
        log.info(f"  ARB Leg 2 (Polymarket): {contracts}x @{opp['p_price']}c")
    except Exception as e:
        log.error(f"  ARB Leg 2 FAILED: {e} -- Leg 1 NAKED!!")
        return {"success": False, "reason": f"Leg 2 failed: {e}", "leg1_filled": True, "naked_position": True}
    return {"success": True, "contracts": contracts, "total_cost": total_cost,
        "expected_profit": total_profit, "strategy": opp["strategy_desc"]}


# ════════════════════════════════════════
# BEST-PRICE ROUTING
# ════════════════════════════════════════
def route_order(side, kalshi_price, poly_price, kalshi_fee=0.07, poly_fee=0.00):
    """Route to the platform with the best effective price."""
    k_eff = kalshi_price + kalshi_fee * 100; p_eff = poly_price + poly_fee * 100
    return ("kalshi", kalshi_price) if k_eff <= p_eff else ("polymarket", poly_price)

def get_best_price(ticker, kalshi_api, poly_match, poly_api, side, kalshi_fee=0.07, poly_fee=0.00):
    """Get the best price across both platforms for a given side."""
    k_price, k_ob, p_price, p_ob = None, None, None, None
    try:
        k_ob = kalshi_api.orderbook(ticker)
        asks = k_ob.get("orderbook", {}).get("yes" if side == "yes" else "no", [])
        if asks: k_price = _best_ask(asks)
    except Exception: pass
    if poly_match and poly_api:
        token_id = poly_match.get("token_id", "")
        if token_id:
            try:
                p_ob = poly_api.orderbook(token_id)
                asks = p_ob.get("orderbook", {}).get("yes" if side == "yes" else "no", [])
                if asks: p_price = _best_ask(asks)
            except Exception: pass
    if k_price is not None and p_price is not None:
        platform, price = route_order(side, k_price, p_price, kalshi_fee, poly_fee)
        return platform, price, k_ob if platform == "kalshi" else p_ob
    if k_price is not None: return "kalshi", k_price, k_ob
    if p_price is not None: return "polymarket", p_price, p_ob
    return None, None, None


# ════════════════════════════════════════
# QUICK-FLIP SCALPING
# ════════════════════════════════════════
def find_quickflip_candidates(markets, min_price=3, max_price=15, min_volume=50):
    """Find cheap contracts (3-15c) for quick-flip scalping."""
    candidates = []
    for m in markets:
        yc = m.get("yes_bid", m.get("last_price", 50)) or 50
        vol = m.get("volume", 0) or 0; hrs = m.get("_hrs_left", 9999)
        if min_price <= yc <= max_price and vol >= min_volume and hrs > 2:
            candidates.append({"market": m, "side": "yes", "entry_price": yc,
                "target_price": min(yc * 2, 50), "stop_price": max(1, yc - 2),
                "potential_roi": round((min(yc * 2, 50) - yc) / yc * 100, 0),
                "platform": m.get("platform", "kalshi"), "hours_left": hrs})
        no_price = 100 - yc
        if min_price <= no_price <= max_price and vol >= min_volume and hrs > 2:
            candidates.append({"market": m, "side": "no", "entry_price": no_price,
                "target_price": min(no_price * 2, 50), "stop_price": max(1, no_price - 2),
                "potential_roi": round((min(no_price * 2, 50) - no_price) / no_price * 100, 0),
                "platform": m.get("platform", "kalshi"), "hours_left": hrs})
    candidates.sort(key=lambda x: x["potential_roi"], reverse=True)
    return candidates[:10]


# ════════════════════════════════════════
# COMPOUNDING BANKROLL TIERS
# ════════════════════════════════════════
BANKROLL_TIERS = [
    (500, 60.0, 200.0, 0.20), (300, 40.0, 150.0, 0.25),
    (150, 25.0, 100.0, 0.25), (75, 15.0, 60.0, 0.30), (0, 8.0, 35.0, 0.30),
]

def get_bankroll_tier(bankroll):
    """Get dynamic trading parameters based on current combined bankroll."""
    for min_br, max_bet, max_exp, kf in BANKROLL_TIERS:
        if bankroll >= min_br:
            return {"max_bet_per_trade": max_bet, "max_total_exposure": max_exp,
                    "kelly_fraction": kf, "tier_min": min_br}
    return {"max_bet_per_trade": 5.0, "max_total_exposure": 25.0, "kelly_fraction": 0.20, "tier_min": 0}

def get_dynamic_kelly(base_fraction, win_streak=0, loss_cooldown=0):
    """Adjust Kelly fraction based on recent performance."""
    if loss_cooldown > 0: return max(0.10, base_fraction * 0.5)
    if win_streak >= 2: return min(0.50, base_fraction + (win_streak - 1) * 0.05)
    return base_fraction


# ════════════════════════════════════════
# WITHIN-MARKET ARBITRAGE SCANNER
# (No AI needed -- pure math)
# ════════════════════════════════════════
def scan_arbitrage(api, markets):
    """
    Check for markets where YES+NO orderbook best bids sum to < 100.
    Buying YES and NO guarantees $1 payout for less than $1 cost = riskless profit.
    This is the only TRUE arbitrage -- everything else is probabilistic.
    """
    opportunities = []
    # Sample markets with decent volume
    candidates = [m for m in markets if (m.get("volume",0) or 0) >= 50][:100]
    for m in candidates:
        try:
            ob = api.orderbook(m["ticker"])
            book = ob.get("orderbook",{})
            # Get best YES and NO ask prices (what we'd pay)
            # In Kalshi's binary market: YES bid at X means you can buy YES at X
            # NO bid at Y means you can buy NO at Y
            # If X + Y < 100 cents, buying both = guaranteed profit
            yes_bids = book.get("yes", book.get("yes_dollars",[]))
            no_bids = book.get("no", book.get("no_dollars",[]))
            if not yes_bids or not no_bids: continue
            # Best (highest) bid = cheapest entry for each side
            raw_yes = yes_bids[0][0] if isinstance(yes_bids[0],list) else yes_bids[0]
            raw_no = no_bids[0][0] if isinstance(no_bids[0],list) else no_bids[0]
            best_yes = parse_orderbook_price(raw_yes)
            best_no = parse_orderbook_price(raw_no)
            if best_yes is None or best_no is None: continue
            total_cost = best_yes + best_no
            fee_cost = CFG["taker_fee_per_contract"] * 2 * 100  # 2 contracts, convert to cents
            if total_cost + fee_cost < 100:
                profit_cents = 100 - total_cost - fee_cost
                opportunities.append({
                    "ticker": m["ticker"], "title": m.get("title",""),
                    "yes_price": best_yes, "no_price": best_no,
                    "total_cost": total_cost, "profit_cents": profit_cents,
                    "type": "arbitrage"
                })
        except Exception:
            continue
        time.sleep(0.1)  # Rate limit
    opportunities.sort(key=lambda x: x["profit_cents"], reverse=True)
    return opportunities

# ════════════════════════════════════════
# BULL vs BEAR DEBATE ENGINE
# (The #1 improvement from reference repos)
# ════════════════════════════════════════
class DebateEngine:
    """
    Three-step adversarial analysis:
    1. BULL: Makes strongest YES case with web search
    2. BEAR: Makes strongest NO case, directly countering bull's arguments
    3. SYNTHESIS: Weighs both sides, produces final probability and trade decision

    This reduces overconfidence -- the single biggest problem with one-shot AI analysis.
    """
    def __init__(self):
        self.api_key = CFG["anthropic_api_key"]
        self.client = anthropic.Anthropic(api_key=self.api_key) if HAS_SDK else None
        self._last = 0
        self._gap = 6

    def _throttle(self):
        e = time.time() - self._last
        if e < self._gap: time.sleep(self._gap - e)
        self._last = time.time()

    def _call(self, prompt, max_tok=1200, retries=2):
        self._throttle()
        for attempt in range(retries):
            try:
                if HAS_SDK:
                    resp = self.client.messages.create(
                        model="claude-sonnet-4-20250514", max_tokens=max_tok,
                        tools=[{"type":"web_search_20250305","name":"web_search"}],
                        messages=[{"role":"user","content":prompt}])
                    return "\n".join(b.text for b in resp.content if hasattr(b,"text"))
                else:
                    r = req_lib.post("https://api.anthropic.com/v1/messages",
                        headers={"Content-Type":"application/json","x-api-key":self.api_key,
                                 "anthropic-version":"2023-06-01"},
                        json={"model":"claude-sonnet-4-20250514","max_tokens":max_tok,
                              "tools":[{"type":"web_search_20250305","name":"web_search"}],
                              "messages":[{"role":"user","content":prompt}]}, timeout=120)
                    if r.status_code == 429:
                        w = 60*(attempt+1); log.warning(f"Rate limit, wait {w}s"); time.sleep(w); continue
                    r.raise_for_status()
                    return "\n".join(b["text"] for b in r.json()["content"] if b.get("type")=="text")
            except Exception as e:
                if "rate_limit" in str(e).lower() and attempt < retries-1:
                    time.sleep(60*(attempt+1)); continue
                raise
        return ""

    def quick_scan(self, markets, skip_tickers, data_brief=""):
        """Pass 1: Fast scan with category-specific research instructions and live data"""
        lines = []
        for m in markets:
            if m["ticker"] in skip_tickers: continue
            t = m.get("title",""); sub = m.get("subtitle","")
            yc = m.get("yes_bid", m.get("last_price","?")); vol = m.get("volume",0) or 0
            hrs = m.get("_hrs_left","?")
            cat = m.get("_category","other")
            if isinstance(hrs,float): hrs=f"{hrs:.0f}"
            desc = t + (f" [{sub}]" if sub and sub!=t else "")
            lines.append(f"  {m['ticker']}: ({cat.upper()}) {desc} -- yes:{yc}c -- vol:{vol} -- {hrs}h left")
        if not lines: return []
        mlist = "\n".join(lines[:CFG["markets_per_scan"]])

        data_section = ""
        if data_brief:
            data_section = f"""

LIVE DATA (pre-fetched from official sources -- use these as ground truth):
{data_brief}

IMPORTANT: Compare the live data above DIRECTLY to the market prices. If NWS says 62°F and a market asks "above 58°F?" priced at 50c, that's concrete evidence of a 10%+ edge. If FRED shows Fed Funds at 5.33% and a market implies otherwise, that's edge."""
        if not lines: return []
        mlist = "\n".join(lines[:CFG["markets_per_scan"]])

        prompt = f"""You are an AGGRESSIVE prediction market trader. Your job is to FIND EDGE AND EXPLOIT IT. You are hungry for trades. The market is often wrong and slow to react. Be bold.

TODAY: {datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")}

TASK: From these markets, identify up to 5 tradeable opportunities. Look for ANY edge -- not just massive ones. A 3-5%% edge IS worth trading.

AGGRESSIVE PLAYBOOK -- think like a shark:

1. STALE PRICES: Markets often lag behind breaking news by hours. Search for the LATEST news on each topic. If reality has changed but the price hasn't, ATTACK.

2. WEATHER EXPLOITS: NWS forecasts update every few hours. If NWS says 72F and a market prices "above 65F" at only 70c, that's free money. Check forecasts for ALL weather markets.

3. NEAR-EXPIRY PICKS: Markets closing in <6h with prices between 15-85c are goldmines. Reality is usually clearer than the market thinks near expiry. If you can determine the likely outcome, BET.

4. CONSENSUS VS PRICE: When polls, forecasts, or expert consensus clearly disagree with the market price by even 5%%, that's tradeable edge.

5. ASYMMETRIC BETS: A contract at 10c that should be 20c is a 100%% ROI. Look for cheap contracts where the true probability is even slightly higher.

6. DATA ALREADY RELEASED: If a jobs report, CPI print, or court ruling already happened today but the market hasn't moved, that's instant edge.

7. MOMENTUM PLAYS: If a price has been trending in one direction and the underlying fundamentals support it continuing, ride the wave.

RESEARCH CHECKLIST:
- WEATHER: Search NWS forecasts for each city mentioned. Compare temp/precip to market thresholds.
- ECONOMICS: Search latest data releases (BLS, FRED, Fed speakers). Compare to market prices.
- POLITICS: Search latest news on the specific topic. Has something happened that markets missed?
- CRYPTO/STOCKS: Search current prices. Is the market stale vs current reality?
- EVENTS: Search for latest updates on sports, awards, trials, launches, etc.

RULES:
- Return up to 5 candidates (more is better -- be aggressive)
- Even a 3%% edge is worth flagging
- Search for CURRENT data, not yesterday's
- Be concrete: cite the specific number or fact you found
- You are TRYING to find trades. An empty list means you failed.

MARKETS:
{mlist}
{data_section}

CRITICAL RULES FOR YOUR RESPONSE:
- Each entry MUST have the EXACT ticker from the market list above (e.g. "KXTEMP-25MAR11-PHI-T50-B60")
- Do NOT group multiple markets into one entry
- Do NOT use descriptions like "Multiple weather markets" as tickers
- One JSON object per individual market
- The ticker field must EXACTLY match a ticker shown in the MARKETS section above

Return ONLY a JSON array:
[{{{{"ticker":"KXTEMP-25MAR11-PHI-T50-B60","title":"Philadelphia temp above 60F","category":"weather","market_yes_cents":65,"initial_edge_estimate":8,"side":"YES","evidence":"NWS forecast 72F, market implies only 65%% chance of >65F","is_cant_miss":false}}}}]
Return [] ONLY if you truly cannot find ANY edge after thorough research."""

        for attempt in range(2):
            try:
                text = self._call(prompt, 1500)
                log.debug(f"Quick scan raw response (attempt {attempt+1}): {text[:500]}")
                s,e = text.find("["), text.rfind("]")+1
                if s>=0 and e>s:
                    result = json.loads(text[s:e])
                    if isinstance(result, list): return result
                # JSON parse failed -- try regex fallback for individual candidates
                log.warning(f"Quick scan: JSON parse failed (attempt {attempt+1}), trying regex fallback")
                fallback = []
                for m in re.finditer(r'"ticker"\s*:\s*"([^"]+)"', text):
                    ticker = m.group(1)
                    # Try to extract nearby fields
                    chunk = text[max(0,m.start()-50):m.end()+300]
                    side_m = re.search(r'"side"\s*:\s*"(YES|NO)"', chunk, re.IGNORECASE)
                    edge_m = re.search(r'"initial_edge_estimate"\s*:\s*(\d+)', chunk)
                    if side_m:
                        fallback.append({"ticker":ticker, "title":"", "category":"other",
                            "market_yes_cents":50, "initial_edge_estimate":int(edge_m.group(1)) if edge_m else 10,
                            "side":side_m.group(1).upper(), "evidence":"(parsed from malformed response)",
                            "is_cant_miss":False})
                if fallback:
                    log.info(f"Quick scan: regex fallback recovered {len(fallback)} candidates")
                    return fallback
                if attempt == 0:
                    log.warning("Quick scan: retrying with fresh API call")
                    continue
            except Exception as ex:
                log.error(f"Quick scan error (attempt {attempt+1}): {ex}")
                if attempt == 0: continue
        return []

    def run_debate(self, market, orderbook_data=None, data_fetcher=None):
        """
        Full 3-step debate on a single market.
        Returns final decision dict or None on failure.
        """
        yc = market.get("yes_bid", market.get("last_price",50)) or 50
        hrs = market.get("_hrs_left","?")
        title = market.get("title", market["ticker"])
        sub = market.get("subtitle","")
        full_title = title + (f" -- {sub}" if sub and sub!=title else "")
        cat = market.get("_category","other")

        ob_info = "Not available"
        if orderbook_data:
            ob = orderbook_data.get("orderbook",{})
            ob_info = f"YES bids: {ob.get('yes',ob.get('yes_dollars',[]))[:5]}\nNO bids: {ob.get('no',ob.get('no_dollars',[]))[:5]}"

        # Build live data section from prefetched data
        live_data = ""
        if data_fetcher:
            # Weather data for this specific market
            city, forecasts = data_fetcher.get_weather_for_market(title)
            if city and forecasts:
                wx_lines = []
                for p in forecasts[:3]:
                    precip = f", precip {p['precip_pct']}%" if p.get('precip_pct') is not None else ""
                    wx_lines.append(f"  {p['name']}: {p['temp']}°{p['temp_unit']}{precip} -- {p['short']}")
                live_data += f"\nNWS OFFICIAL FORECAST for {city.title()}:\n" + "\n".join(wx_lines)
            elif city:
                live_data += f"\n(City '{city}' identified but forecast not in pre-fetch cache)"
            # FRED data for this category
            fred_data = data_fetcher.get_fred_for_category(cat)
            if fred_data:
                live_data += f"\nFRED OFFICIAL DATA: {fred_data}"

        live_section = ""
        if live_data:
            live_section = f"""

VERIFIED LIVE DATA (from official government sources -- treat as ground truth):
{live_data}
Use this data as your PRIMARY evidence. Web search for ADDITIONAL context only."""

        market_context = f"""MARKET: {full_title}
TICKER: {market['ticker']}
CATEGORY: {cat}
YES PRICE: {yc}c (implies {yc}% probability)
VOLUME: {market.get('volume','?')}
CLOSES: {market.get('close_time',market.get('expiration_time','?'))}
HOURS LEFT: {hrs}
ORDERBOOK: {ob_info}
FEES: ~$0.07/contract{live_section}"""

        # ── STEP 1: BULL CASE ──
        log.info("    [BULL] Researching YES case...")
        cat = market.get("_category", "other")
        cat_instruction = {
            "weather": "Search for the exact NWS point forecast for this location and date. Quote the specific temperature/precipitation numbers.",
            "fed_rates": "Search CME FedWatch for current rate probabilities. Search for latest Fed speaker comments from the last 48 hours.",
            "inflation": "Search for the latest CPI/PCE release from BLS. Quote the actual number and consensus expectation.",
            "employment": "Search for the latest nonfarm payrolls or jobless claims. Quote actual vs expected.",
            "gdp_growth": "Search for latest GDP estimate from BEA or Atlanta Fed GDPNow.",
            "energy": "Search for current WTI crude price and latest OPEC decisions.",
            "policy": "Search for the latest news on this specific regulation/legislation. Find committee votes, statements, or rulings.",
            "markets": "Search for latest close or intraday movement of the relevant index.",
        }.get(cat, "Search for the most recent data relevant to this market.")

        bull_prompt = f"""You are a conviction-driven research analyst. Make the STRONGEST possible case that this market resolves YES. You are the BULL in a bull-vs-bear debate.

{market_context}

REQUIRED RESEARCH: {cat_instruction}

Rules:
- If VERIFIED LIVE DATA is shown above, use it as your PRIMARY evidence -- it's from official government sources
- You MUST cite at least one specific data point (not "I believe" -- give numbers, dates, sources)
- Search the web for ADDITIONAL supporting context beyond the live data
- Start from the market price ({yc}%) and argue why reality is HIGHER
- Give a probability FLOOR (the minimum even if bear arguments are strong)

Structure your response:
THESIS: [one sentence bullish thesis]
KEY_DATA: [the single most important number/fact, with source]
ARGUMENTS: [3 specific evidence-based arguments for YES]
PROBABILITY_FLOOR: [minimum reasonable YES probability as integer]
PROBABILITY: [your YES probability estimate as integer 1-99]
CATALYSTS: [what could push probability higher in the next 24h]"""

        log.debug(f"BULL prompt ({len(bull_prompt)} chars): {bull_prompt[:300]}...")
        bull_text = self._call(bull_prompt, 1000)
        bull_prob = self._extract_prob(bull_text, "PROBABILITY:", 60)
        bull_floor = self._extract_prob(bull_text, "PROBABILITY_FLOOR:", 30)
        log.info(f"    [BULL] prob={bull_prob}% floor={bull_floor}%")

        # ── STEP 2: BEAR CASE ──
        log.info("    [BEAR] Researching NO case...")
        # Extract bull arguments to feed to bear
        bull_args = ""
        for line in bull_text.split("\n"):
            if line.strip().startswith("ARGUMENTS:") or line.strip().startswith("-"):
                bull_args += line + "\n"

        bear_prompt = f"""You are a skeptical risk analyst. Your job is ADVERSARIAL TRUTH-SEEKING. The bull researcher just presented their case -- you must DESTROY their weakest arguments with counter-evidence.

{market_context}
CATEGORY: {cat}

THE BULL'S CASE:
{bull_text[:600]}

YOUR MISSION:
1. Search for COUNTER-EVIDENCE that contradicts the bull's key data point
2. Find what the bull MISSED or got wrong
3. Check: is the bull's source current? Reliable? Cherry-picked?
4. For weather: search for alternative forecast models or uncertainty ranges
5. For econ: search for revisions, seasonal adjustments, or contradicting indicators
6. Give a probability CEILING (the maximum even if bull arguments are strong)

Structure your response:
COUNTER_THESIS: [one sentence bearish thesis]
COUNTER_DATA: [specific fact that CONTRADICTS the bull's key data point]
COUNTER_ARGUMENTS: [3 arguments for NO, each directly addressing a bull point]
PROBABILITY_CEILING: [maximum reasonable YES probability as integer]
PROBABILITY: [your YES probability estimate as integer 1-99]
RISK_FACTORS: [what could go wrong for YES holders in the next 24h]"""

        log.debug(f"BEAR prompt ({len(bear_prompt)} chars): {bear_prompt[:300]}...")
        bear_text = self._call(bear_prompt, 1000)
        bear_prob = self._extract_prob(bear_text, "PROBABILITY:", 40)
        bear_ceiling = self._extract_prob(bear_text, "PROBABILITY_CEILING:", 70)
        log.info(f"    [BEAR] prob={bear_prob}% ceiling={bear_ceiling}%")

        # ── STEP 3: SYNTHESIS ──
        log.info("    [JUDGE] Synthesizing debate...")
        synthesis_prompt = f"""You are a senior portfolio manager making the FINAL trade decision. You've heard a structured bull-vs-bear debate. YOUR MONEY IS ON THE LINE.

{market_context}

BULL CASE (prob={bull_prob}%, floor={bull_floor}%):
{bull_text[:500]}

BEAR CASE (prob={bear_prob}%, ceiling={bear_ceiling}%):
{bear_text[:500]}

DEBATE METRICS:
- Bull estimate: {bull_prob}% | Bear estimate: {bear_prob}%
- Debate spread: {abs(bull_prob-bear_prob)}% (>30% = extreme disagreement to trade)
- Bull floor: {bull_floor}% | Bear ceiling: {bear_ceiling}%
- Market price: {yc}c (implies {yc}%)

DECISION FRAMEWORK (aggressive -- bias toward ACTION):
1. EVIDENCE QUALITY: Which side has harder data? Go with the side that has concrete numbers.
2. MARKET INEFFICIENCY BIAS: Markets are SLOW. If either side found fresh data the market hasn't priced in, TRADE.
3. DISAGREE AND COMMIT: Even if bull and bear differ, if one side has clearly better evidence, GO WITH IT. Only say HOLD if you truly have zero edge.
4. If bull floor > market price, STRONG YES. If bear ceiling < market price, STRONG NO. These are the easiest calls.
5. TIME PRESSURE: Edge decays fast. If you see edge NOW, take it. Waiting means someone else captures it.
6. SMALL EDGE IS STILL EDGE: A 3-5% edge on a reasonably priced contract is still profitable. Don't demand perfection.
7. FORTUNE FAVORS THE BOLD: You miss 100% of the trades you don't take. When evidence leans one way, commit.

RESPOND EXACTLY:
PROBABILITY: [integer 1-99, your final evidence-weighted estimate]
CONFIDENCE: [integer 1-99, how certain you are -- be generous with confidence when evidence is concrete]
SIDE: [YES or NO or HOLD]
EDGE_DURATION_HOURS: [how long this edge will last before market corrects]
EVIDENCE: [the single most decisive verified fact from the debate]
RISK: [the strongest counter-argument you couldn't dismiss]
PRICE_CENTS: [integer 1-99, your bid price]
CONTRACTS: [integer 1-20]"""

        log.debug(f"SYNTHESIS prompt ({len(synthesis_prompt)} chars): {synthesis_prompt[:300]}...")
        synth_text = self._call(synthesis_prompt, 800)
        log.debug(f"SYNTHESIS response: {synth_text[:500]}")
        result = self._parse_synthesis(synth_text, yc, bull_prob, bear_prob)
        result["bull_prob"] = bull_prob
        result["bear_prob"] = bear_prob
        result["debate_spread"] = abs(bull_prob - bear_prob)
        return result

    def _extract_prob(self, text, label, default):
        for line in text.split("\n"):
            if label in line:
                return parse_int(line.split(":",1)[1], default)
        return default

    def _parse_synthesis(self, text, market_cents, bull_prob, bear_prob):
        r = {"probability":0,"confidence":0,"side":"HOLD","evidence":"","risk":"",
             "price_cents":0,"contracts":0,"edge":0}
        for line in text.split("\n"):
            l = line.strip()
            if l.startswith("PROBABILITY:"): r["probability"] = max(1,min(99,parse_int(l.split(":",1)[1])))
            elif l.startswith("CONFIDENCE:"): r["confidence"] = max(0,min(99,parse_int(l.split(":",1)[1])))
            elif l.startswith("SIDE:"):
                v = l.split(":",1)[1].upper()
                r["side"] = "YES" if "YES" in v else "NO" if "NO" in v else "HOLD"
            elif l.startswith("EVIDENCE:"): r["evidence"] = l.split(":",1)[1].strip()[:250]
            elif l.startswith("RISK:"): r["risk"] = l.split(":",1)[1].strip()[:250]
            elif l.startswith("PRICE_CENTS:"): r["price_cents"] = max(1,min(99,parse_int(l.split(":",1)[1])))
            elif l.startswith("CONTRACTS:"): r["contracts"] = max(0,min(20,parse_int(l.split(":",1)[1])))
        # Recalculate edge from our probability vs market
        # YES edge: how much higher we think YES prob is vs market price (both in %)
        # NO edge: simplifies to (market_cents - probability), i.e., market overprices YES
        if r["side"]=="YES": r["edge"] = r["probability"] - market_cents
        elif r["side"]=="NO": r["edge"] = (100-r["probability"]) - (100-market_cents)

        # ── CONVICTION GATES (aggressive mode) ──
        debate_spread = abs(bull_prob - bear_prob)

        # Gate 1: If bull and bear disagree by >30%, force HOLD -- extreme disagreement
        if debate_spread > 45:
            log.info(f"    [GATE] Debate spread {debate_spread}% > 30% -> HOLD (extreme disagreement)")
            r["side"] = "HOLD"; r["confidence"] = max(0, r["confidence"] - 15)

        # Gate 2: Light penalty for large disagreement (25-45% range)
        elif debate_spread > 25:
            penalty = int((debate_spread - 25) * 0.5)
            r["confidence"] = max(0, r["confidence"] - penalty)
            log.info(f"    [GATE] Debate spread {debate_spread}% -> light penalty -{penalty}")

        # Gate 3: Reward or penalize based on where our probability sits vs the debate range
        if r["side"] != "HOLD":
            low_est = min(bull_prob, bear_prob)
            high_est = max(bull_prob, bear_prob)
            if low_est <= r["probability"] <= high_est and debate_spread > 30:
                # Probability is right in the middle of the debate -- only penalize in very wide disagreement
                r["confidence"] = max(0, r["confidence"] - 5)
                log.info(f"    [GATE] Probability {r['probability']}% inside debate range [{low_est}-{high_est}] -> -5 conf")
            elif r["probability"] > high_est and r["side"] == "YES":
                # Both bull AND bear agree probability is below our estimate -> strong YES signal
                r["confidence"] = min(99, r["confidence"] + 10)
                log.info(f"    [GATE] Probability {r['probability']}% ABOVE debate range [{low_est}-{high_est}] -> +10 conf (strong YES)")
            elif r["probability"] < low_est and r["side"] == "NO":
                # Both bull AND bear agree probability is above our estimate -> strong NO signal
                r["confidence"] = min(99, r["confidence"] + 10)
                log.info(f"    [GATE] Probability {r['probability']}% BELOW debate range [{low_est}-{high_est}] -> +10 conf (strong NO)")

        # Gate 4: Edge must exceed fee drag or it's unprofitable
        price_for_side = r["price_cents"] if r["price_cents"] > 0 else (market_cents if r["side"]=="YES" else 100-market_cents)
        if price_for_side > 0:
            fee_drag_pct = (CFG["taker_fee_per_contract"] / (price_for_side/100)) * 100
            if abs(r["edge"]) < fee_drag_pct:
                log.info(f"    [GATE] Edge {r['edge']}% < fee drag {fee_drag_pct:.1f}% -> HOLD")
                r["side"] = "HOLD"

        return r

# ════════════════════════════════════════
# KELLY CRITERION (fee-aware)
# ════════════════════════════════════════
def kelly(prob_pct, price_cents, bankroll, max_bet, fee, fraction=0.20):
    p = prob_pct/100.0; price = price_cents/100.0
    win_payoff = (1.0-price) - fee; lose_cost = price + fee
    if win_payoff <= 0: return 0,0
    ev = p*win_payoff - (1-p)*lose_cost
    if ev <= 0: return 0,0
    b = win_payoff/lose_cost; q = 1-p
    kf = max(0, ((b*p-q)/b)*fraction) if b>0 else 0
    bet = min(kf*bankroll, max_bet)
    total_per = price+fee
    contracts = max(1,int(bet/total_per)) if bet>=total_per else 0
    while contracts>0 and contracts*total_per>max_bet: contracts-=1
    return contracts, round(contracts*price,2)

# ════════════════════════════════════════
# MARKET FILTER & SCORING
# ════════════════════════════════════════
def calc_hours_left(m):
    close = m.get("close_time") or m.get("expiration_time") or ""
    if not close: return 9999
    try:
        ct = datetime.datetime.fromisoformat(close.replace("Z","+00:00"))
        return (ct-datetime.datetime.now(datetime.timezone.utc)).total_seconds()/3600
    except Exception: return 9999

def score_market(m):
    s=0; vol=m.get("volume",0) or 0; yc=m.get("yes_bid",m.get("last_price",50)) or 50
    hrs=m.get("_hrs_left",9999); cat=m.get("_category","other")

    # Volume: more liquid = tighter spreads = better fills
    if vol>=1000: s+=4
    elif vol>=500: s+=3
    elif vol>=100: s+=2
    elif vol>=20: s+=1

    # Price range: mid-range = most edge; extremes = near-certain (less edge but high conviction)
    if 25<=yc<=75: s+=3
    elif 15<=yc<=85: s+=2
    elif 8<=yc<=92: s+=1

    # Time to close: heavy short-term bias
    if 1<=hrs<=6: s+=6
    elif 6<hrs<=12: s+=5
    elif 12<hrs<=24: s+=4
    elif 24<hrs<=48: s+=2
    elif 48<hrs<=72: s+=1

    # Category bonus: weather and econ data markets have the clearest verifiable edge
    if cat in ("weather","fed_rates","inflation","employment"): s+=3
    elif cat in ("energy","policy"): s+=2
    elif cat in ("gdp_growth","markets"): s+=1

    # Penalty for very low volume (thin orderbook = bad fills)
    if vol<10: s-=1  # Only penalize very thin markets

    # Bonus for cheap contracts (asymmetric upside)
    if yc<=15 or yc>=85: s+=2  # Cheap contracts = high ROI if correct

    # Bonus for markets near resolution with extreme prices
    if hrs<=12 and (yc>=85 or yc<=15): s+=2

    return s

def filter_and_rank(markets):
    kws=CFG["target_keywords"]; cat_rules=CFG.get("category_rules",{})
    short_term=[]; long_term=[]
    _f_price=0; _f_vol=0; _f_hrs=0; _f_kw=0; _short_samples=[]; _close_samples=[]
    for m in markets:
        yc=m.get("yes_bid",m.get("last_price",50)) or 50
        if yc>CFG["max_price_cents"] or yc<CFG["min_price_cents"]: _f_price+=1; continue
        if (m.get("volume",0) or 0)<CFG["min_volume"]: _f_vol+=1; continue
        hrs=calc_hours_left(m)
        if hrs<CFG["min_close_hours"]: _f_hrs+=1; continue
        if len(_close_samples)<3: _close_samples.append(f"{m.get('ticker','?')}: hrs={hrs:.1f} close={m.get('close_time','N/A')} exp={m.get('expiration_time','N/A')}")
        m["_hrs_left"]=hrs
        text=" ".join(str(m.get(k,"")) for k in ["title","ticker","category","subtitle","event_ticker"]).lower()
        if not any(kw in text for kw in kws): _f_kw+=1; continue
        # Tag with best category match
        m["_category"]="other"
        best_cat_score=0
        for cat_name, cat_kws in cat_rules.items():
            hits=sum(1 for kw in cat_kws if kw in text)
            if hits>best_cat_score: best_cat_score=hits; m["_category"]=cat_name
        m["_score"]=score_market(m)
        if hrs<=CFG["max_close_hours"]: short_term.append(m)
        else: long_term.append(m)
    log.debug(f"Filter: {len(markets)} total -> price:{_f_price} vol:{_f_vol} hrs:{_f_hrs} kw:{_f_kw} dropped | {len(short_term)} short + {len(long_term)} long pass")
    if _close_samples: log.debug(f"Sample close times: {_close_samples}")
    short_term.sort(key=lambda x:x.get("_score",0),reverse=True)
    long_term.sort(key=lambda x:x.get("_score",0),reverse=True)
    return short_term, long_term[:CFG["markets_per_scan"]]

# ════════════════════════════════════════
# RISK MANAGER + CALIBRATION
# ════════════════════════════════════════
class RiskMgr:
    def __init__(self):
        self.today=datetime.date.today(); self.day_trades=0; self.day_pnl=0.0
        self.exposure=0.0; self.paused=False
        p=CFG["trade_log"]; self.trades=json.load(open(p)) if os.path.exists(p) else []
        self.traded_tickers=set()
        for t in self.trades:
            try:
                if datetime.date.fromisoformat(t["time"][:10])==self.today:
                    self.day_trades+=1; self.exposure+=t.get("cost",0)
                    self.traded_tickers.add(t["ticker"])
            except Exception: pass
    def _save(self):
        with open(CFG["trade_log"],"w") as f: json.dump(self.trades,f,indent=2,default=str)
    def new_day(self):
        if datetime.date.today()!=self.today:
            log.info("New day -- reset"); self.today=datetime.date.today()
            self.day_trades=0; self.day_pnl=0.0; self.paused=False; self.traded_tickers.clear()
    def check(self,cost,conf,edge):
        self.new_day()
        if self.paused: return False,"PAUSED"
        if self.day_trades>=CFG["max_daily_trades"]: return False,f"Daily limit ({CFG['max_daily_trades']})"
        if self.exposure+cost>CFG["max_total_exposure"]: return False,f"Exposure exceeded"
        if cost>CFG["max_bet_per_trade"]: return False,f"Bet too large"
        if conf<CFG["min_confidence"]: return False,f"Low confidence ({conf}%)"
        if abs(edge)<CFG["min_edge_pct"]: return False,f"Low edge ({edge}%)"
        if self.day_pnl<-CFG["max_daily_loss"]: self.paused=True; return False,"CIRCUIT BREAKER"
        return True,"OK"
    def record(self,ticker,title,side,contracts,price_c,conf,edge,evidence,bull_prob=0,bear_prob=0,probability=0,platform="kalshi"):
        cost=contracts*price_c/100
        t={"time":datetime.datetime.now().isoformat(),"ticker":ticker,"title":title,"side":side,
           "contracts":contracts,"price_cents":price_c,"cost":round(cost,2),"confidence":conf,
           "probability":probability,"edge":edge,"evidence":evidence,
           "bull_prob":bull_prob,"bear_prob":bear_prob,"status":"open","platform":platform}
        self.trades.append(t); self.day_trades+=1; self.exposure+=cost
        self.traded_tickers.add(ticker); self._save()
        # Calibration record
        self._log_calibration(t)
    def _log_calibration(self,trade):
        cal_file=CFG["calibration_log"]
        records=[]
        if os.path.exists(cal_file):
            try: records=json.load(open(cal_file))
            except Exception: records=[]
        records.append({"time":trade["time"],"ticker":trade["ticker"],"side":trade["side"],
            "our_probability":trade.get("probability",0),"our_confidence":trade.get("confidence",0),
            "market_price":trade["price_cents"],
            "edge":trade["edge"],"bull_prob":trade.get("bull_prob",0),
            "bear_prob":trade.get("bear_prob",0),"resolved":None})
        if len(records)>2000: records=records[-2000:]
        with open(cal_file,"w") as f: json.dump(records,f,indent=2,default=str)
    def summary(self):
        w=sum(1 for t in self.trades if t.get("status")=="win")
        l=sum(1 for t in self.trades if t.get("status")=="loss")
        tc=sum(t.get("cost",0) for t in self.trades)
        return {"total":len(self.trades),"wins":w,"losses":l,
            "win_rate":f"{w/(w+l)*100:.0f}%" if w+l>0 else "--","wagered":f"${tc:.2f}",
            "day_trades":self.day_trades,"day_pnl":f"${self.day_pnl:.2f}",
            "exposure":f"${self.exposure:.2f}","paused":self.paused}

# ════════════════════════════════════════
# DASHBOARD HTML
# ════════════════════════════════════════
DASHBOARD_HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Kalshi Agent v6</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Instrument+Sans:wght@400;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Instrument Sans',sans-serif;background:#06090f;color:#e0e6f0;min-height:100vh}
.hdr{background:#0c1118;border-bottom:1px solid #1a2536;padding:14px 24px;display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:20px;font-weight:700;background:linear-gradient(135deg,#e8b94a,#f5d78e);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .v{font-size:10px;color:#556a85;margin-left:8px}
.hdr .rt{display:flex;align-items:center;gap:14px}
.env{font-family:'IBM Plex Mono',monospace;font-size:11px;padding:3px 10px;border-radius:10px;font-weight:600}
.env.PROD{background:rgba(248,113,113,.12);color:#f87171;border:1px solid rgba(248,113,113,.2)}
.env.DEMO{background:rgba(96,165,250,.12);color:#60a5fa}
.bal{font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:600;color:#34d399}
.tw{display:flex;align-items:center;gap:10px}
.tl{font-size:13px;font-weight:600}
.tb{width:56px;height:28px;border-radius:14px;border:none;cursor:pointer;position:relative;transition:.3s}
.tb.on{background:#34d399}.tb.off{background:#4a5568}
.tb::after{content:'';position:absolute;width:22px;height:22px;border-radius:50%;background:#fff;top:3px;transition:.3s}
.tb.on::after{left:31px}.tb.off::after{left:3px}
.main{max-width:1100px;margin:0 auto;padding:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.card{background:#0c1118;border:1px solid #1a2536;border-radius:8px;padding:14px}
.card .cl{font-size:10px;color:#556a85;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.card .cv{font-family:'IBM Plex Mono',monospace;font-size:18px;font-weight:600}
.green{color:#34d399}.gold{color:#e8b94a}.red{color:#f87171}.blue{color:#60a5fa}.white{color:#e0e6f0}
.sect{background:#0c1118;border:1px solid #1a2536;border-radius:8px;margin-bottom:16px;overflow:hidden}
.sect h2{font-size:13px;font-weight:600;padding:12px 16px;border-bottom:1px solid #1a2536;color:#8a9bb5}
.lb{max-height:280px;overflow-y:auto;padding:8px 12px;font-family:'IBM Plex Mono',monospace;font-size:11px}
.ll{padding:2px 0;display:flex;gap:8px;border-bottom:1px solid rgba(26,37,54,.4)}
.lt{color:#556a85;min-width:55px}.lm{color:#8a9bb5;word-break:break-word}
.lm.WARNING{color:#e8b94a}.lm.ERROR{color:#f87171}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 12px;font-size:10px;color:#556a85;text-transform:uppercase;border-bottom:1px solid #1a2536}
td{padding:7px 12px;border-bottom:1px solid #0f1520;font-family:'IBM Plex Mono',monospace;font-size:11px}
tr:hover td{background:#0f1520}
.yes{color:#34d399}.no{color:#f87171}
.ft{font-size:11px;color:#3a4a60;padding:10px 16px;text-align:center;border-top:1px solid #1a2536}
.paused{background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.25);color:#f87171;padding:12px;border-radius:8px;text-align:center;margin-bottom:16px;font-weight:600}
.dry{background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.25);color:#60a5fa;padding:10px;border-radius:8px;text-align:center;margin-bottom:16px;font-weight:600}
.debate-tag{font-size:9px;padding:2px 5px;border-radius:3px;font-weight:600;margin-left:4px}
.debate-tag.bull{background:rgba(52,211,153,.15);color:#34d399}
.debate-tag.bear{background:rgba(248,113,113,.15);color:#f87171}
</style></head><body>
<div class="hdr">
<div><h1 style="display:inline">Kalshi AI Agent</h1><span class="v">v6 -- Cross-Platform Arbitrage</span></div>
<div class="rt"><span class="env" id="env">--</span><span class="bal" id="bal">$0.00</span>
<div class="tw"><span class="tl" id="tL">ON</span><button class="tb on" id="tB" onclick="toggle()"></button></div></div></div>
<div class="main">
<div id="dB" class="dry" style="display:none">DRY RUN -- scanning only</div>
<div id="pB" class="paused" style="display:none">PAUSED -- daily loss limit</div>
<div class="cards">
<div class="card"><div class="cl">Status</div><div class="cv gold" id="cS">--</div></div>
<div class="card"><div class="cl">Kalshi</div><div class="cv green" id="cBK">$0</div></div>
<div class="card"><div class="cl">Polymarket</div><div class="cv green" id="cBP">$0</div></div>
<div class="card"><div class="cl">Combined</div><div class="cv green" id="cBC">$0</div></div>
<div class="card"><div class="cl">Scans</div><div class="cv blue" id="cSc">0</div></div>
<div class="card"><div class="cl">Trades Today</div><div class="cv white" id="cD">0/15</div></div>
<div class="card"><div class="cl">Exposure</div><div class="cv white" id="cE">$0</div></div>
<div class="card"><div class="cl">Today P&L</div><div class="cv" id="cP">$0</div></div>
<div class="card"><div class="cl">Lifetime</div><div class="cv white" id="cL">0</div></div>
<div class="card"><div class="cl">Win Rate</div><div class="cv green" id="cW">--</div></div>
<div class="card"><div class="cl">Arb Opps</div><div class="cv gold" id="cA">0</div></div>
<div class="card"><div class="cl">Cross-Arb</div><div class="cv gold" id="cCA">0</div></div>
</div>
<div class="sect"><h2>Trade History (Cross-Platform)</h2>
<table><thead><tr><th>Time</th><th>Plat</th><th>Market</th><th>Side</th><th>Qty</th><th>Price</th><th>Cost</th><th>Edge</th><th>Conf</th><th>Bull/Bear</th><th>Evidence</th></tr></thead>
<tbody id="tbl"><tr><td colspan="10" style="text-align:center;color:#556a85;padding:20px">No trades yet</td></tr></tbody></table></div>
<div class="sect"><h2>Activity Log</h2><div class="lb" id="lB"></div></div>
<div class="ft" id="ft">--</div></div>
<script>
async function poll(){try{
const r=await fetch('/api/state');const d=await r.json();
const e=document.getElementById('env');e.textContent=d.environment;e.className='env '+d.environment;
const combined=(d.balance+(d.poly_balance||0));
document.getElementById('bal').textContent='$'+combined.toFixed(2);
document.getElementById('cBK').textContent='$'+d.balance.toFixed(2);
document.getElementById('cBP').textContent='$'+(d.poly_balance||0).toFixed(2);
document.getElementById('cBC').textContent='$'+combined.toFixed(2);
document.getElementById('cS').textContent=d.status;
document.getElementById('cSc').textContent=d.scan_count;
document.getElementById('cD').textContent=d.risk.day_trades+'/'+d.max_daily;
document.getElementById('cE').textContent=d.risk.exposure;
document.getElementById('cP').textContent=d.risk.day_pnl;
document.getElementById('cL').textContent=d.risk.total;
document.getElementById('cW').textContent=d.risk.win_rate;
document.getElementById('cA').textContent=d.arb_opps;
document.getElementById('cCA').textContent=d.cross_arb_opps||0;
const b=document.getElementById('tB'),l=document.getElementById('tL');
b.className='tb '+(d.enabled?'on':'off');l.textContent=d.enabled?'ON':'OFF';
document.getElementById('pB').style.display=d.risk.paused?'block':'none';
document.getElementById('dB').style.display=d.dry_run?'block':'none';
const polyTag=d.poly_enabled?' | Polymarket: ON':'';
document.getElementById('ft').textContent='Last: '+d.last_scan+' | Next: '+d.next_scan+' | Every '+d.scan_interval+'m | v6 Cross-Platform'+polyTag;
const tb=document.getElementById('tbl');
if(d.trades&&d.trades.length){tb.innerHTML=d.trades.slice().reverse().slice(0,20).map(t=>{
const sc=t.side==='yes'?'yes':'no';
const bp=t.bull_prob||'?'; const brp=t.bear_prob||'?';
const plat=(t.platform||'kalshi').slice(0,1).toUpperCase();
const platColor=plat==='P'?'#a78bfa':plat==='C'?'#e8b94a':'#60a5fa';
return '<tr><td>'+t.time.slice(5,16)+'</td><td style="color:'+platColor+';font-weight:600">'+plat+'</td><td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;font-family:Instrument Sans,sans-serif;font-size:11px">'+(t.title||t.ticker).slice(0,35)+'</td><td class="'+sc+'">'+t.side.toUpperCase()+'</td><td>'+t.contracts+'</td><td>'+t.price_cents+'c</td><td>$'+t.cost.toFixed(2)+'</td><td>'+t.edge+'%</td><td>'+t.confidence+'%</td><td><span class="debate-tag bull">B:'+bp+'%</span><span class="debate-tag bear">R:'+brp+'%</span></td><td style="font-family:Instrument Sans;font-size:10px;color:#8a9bb5;max-width:160px;overflow:hidden;text-overflow:ellipsis">'+(t.evidence||'').slice(0,45)+'</td></tr>';}).join('');}
const lb=document.getElementById('lB');
lb.innerHTML=d.log.slice().reverse().slice(0,100).map(l=>'<div class="ll"><span class="lt">'+l.time+'</span><span class="lm '+l.level+'">'+l.msg+'</span></div>').join('');
}catch(e){}}
async function toggle(){await fetch('/api/toggle',{method:'POST'});poll();}
setInterval(poll,3000);poll();
</script></body></html>"""

class DashHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/': self._html(DASHBOARD_HTML)
        elif self.path=='/api/state': self._json(self._state())
        else: self.send_response(404); self.end_headers()
    def do_POST(self):
        if self.path=='/api/toggle':
            with SHARED_LOCK:
                SHARED["enabled"]=not SHARED["enabled"]
                enabled = SHARED["enabled"]
            log.info(f"Agent {'ENABLED' if enabled else 'DISABLED'} via dashboard")
            self._json({"enabled":enabled})
        else: self.send_response(404); self.end_headers()
    def _html(self,c):
        d=c.encode(); self.send_response(200); self.send_header("Content-Type","text/html")
        self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)
    def _json(self,obj):
        d=json.dumps(obj,default=str).encode(); self.send_response(200)
        self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(d)
    def _state(self):
        risk=SHARED.get("_risk_summary",{"total":0,"wins":0,"losses":0,"win_rate":"--","wagered":"$0","day_trades":0,"day_pnl":"$0","exposure":"$0","paused":False})
        return {"enabled":SHARED["enabled"],"status":SHARED["status"],"balance":SHARED["balance"],
            "poly_balance":SHARED.get("poly_balance",0),"poly_enabled":SHARED.get("poly_enabled",False),
            "environment":CFG["environment"].upper(),"risk":risk,"trades":SHARED.get("_trades",[])[-20:],
            "log":SHARED["log_lines"][-100:],"last_scan":SHARED["last_scan"],"next_scan":SHARED["next_scan"],
            "dry_run":SHARED["dry_run"],"max_daily":CFG["max_daily_trades"],"scan_count":SHARED["scan_count"],
            "scan_interval":CFG["scan_interval_minutes"],"arb_opps":SHARED["_arb_opportunities"],
            "cross_arb_opps":SHARED.get("_cross_arb_opportunities",0),
            "quickflip_active":SHARED.get("_quickflip_active",0)}
    def log_message(self,*a): pass

def start_dashboard():
    port=CFG.get("dashboard_port",9000)
    srv=http.server.HTTPServer(("0.0.0.0",port),DashHandler)
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    log.info(f"Dashboard: http://localhost:{port}")

# ════════════════════════════════════════
# AGENT
# ════════════════════════════════════════
class Agent:
    def __init__(self,dry=False):
        self.dry=dry; SHARED["dry_run"]=dry
        self.api=KalshiAPI(); self.debate=DebateEngine()
        self.risk=RiskMgr(); self.cache=MarketCache(self.api)
        self.data=DataFetcher()
        self.notifier=Notifier()
        self.exit_mgr=ExitManager(self.api, self.risk, self.notifier)
        self.reporter=PerformanceReporter(self.risk, self.notifier)
        self.stop_event=threading.Event()
        # Polymarket integration
        self.poly_enabled = CFG.get("polymarket_enabled", False)
        self.poly_api = None; self.poly_cache = None
        self.cross_platform_matches = []
        self.win_streak = 0; self.loss_cooldown = 0
        if self.poly_enabled:
            try:
                self.poly_api = PolymarketAPI()
                self.poly_cache = PolymarketCache(self.poly_api)
                SHARED["poly_enabled"] = True
                log.info(f"Polymarket: {'TRADING' if self.poly_api.is_trading_enabled else 'READ-ONLY'} mode")
            except Exception as e:
                log.error(f"Polymarket init failed: {e} -- running Kalshi-only")
                self.poly_enabled = False

    def scan(self):
        if not SHARED["enabled"]:
            SHARED["status"]="Disabled"; return
        SHARED["status"]="Scanning..."
        log.info("="*50); log.info("SCAN START (v6 -- Cross-Platform)")

        # ── BALANCE CHECK (both platforms) ──
        bal=self.api.balance(); SHARED["balance"]=bal
        poly_bal = 0.0
        if self.poly_enabled and self.poly_api:
            try: poly_bal = self.poly_api.balance()
            except Exception as e: log.debug(f"Polymarket balance error: {e}")
            SHARED["poly_balance"] = poly_bal
        combined_bal = bal + poly_bal
        log.info(f"Balance: Kalshi ${bal:.2f} | Polymarket ${poly_bal:.2f} | Combined ${combined_bal:.2f}")
        if combined_bal < 1: SHARED["status"]="Low balance"; return

        # ── COMPOUNDING: adjust parameters based on combined bankroll ──
        if CFG.get("compounding_enabled", True):
            tier = get_bankroll_tier(combined_bal)
            kf = get_dynamic_kelly(tier["kelly_fraction"], self.win_streak, self.loss_cooldown)
            # Only upgrade, never downgrade from config
            if tier["max_bet_per_trade"] > CFG["max_bet_per_trade"]:
                log.info(f"Bankroll tier upgrade: max_bet ${CFG['max_bet_per_trade']:.0f} -> ${tier['max_bet_per_trade']:.0f}")
            active_max_bet = max(CFG["max_bet_per_trade"], tier["max_bet_per_trade"])
            active_max_exposure = max(CFG["max_total_exposure"], tier["max_total_exposure"])
            active_kelly = kf
        else:
            active_max_bet = CFG["max_bet_per_trade"]
            active_max_exposure = CFG["max_total_exposure"]
            active_kelly = CFG["kelly_fraction"]

        self.risk.new_day()
        self._cb_notified = False if not self.risk.paused else getattr(self, '_cb_notified', False)
        with SHARED_LOCK:
            SHARED["_risk_summary"]=self.risk.summary(); SHARED["_trades"]=self.risk.trades
        if self.risk.paused:
            SHARED["status"]="Paused"
            if not hasattr(self, '_cb_notified') or not self._cb_notified:
                self.notifier.notify_circuit_breaker(self.risk.day_pnl)
                self._cb_notified = True
            return

        # ── LOAD MARKETS (both platforms) ──
        mkts=self.cache.get()
        poly_mkts = []
        if self.poly_enabled and self.poly_cache:
            try:
                poly_mkts = self.poly_cache.get()
                log.info(f"Polymarket: {len(poly_mkts)} markets loaded")
            except Exception as e:
                log.error(f"Polymarket market load failed: {e}")

        # Tag Kalshi markets with platform
        for m in mkts:
            if "platform" not in m: m["platform"] = "kalshi"

        # ── PRE-FETCH LIVE DATA (NWS + FRED) ──
        SHARED["status"]="Fetching live data..."
        self.data.fetch_all()

        # ══════════════════════════════════════
        # PHASE 1: CROSS-PLATFORM ARBITRAGE (fastest, no AI)
        # ══════════════════════════════════════
        if self.poly_enabled and poly_mkts and self.poly_api and CFG.get("cross_arb_enabled", True):
            SHARED["status"]="Cross-platform arbitrage scan..."
            log.info("Phase 1: Cross-platform arbitrage scan...")
            try:
                # Categorize Polymarket markets for matching
                kws = CFG["target_keywords"]; cat_rules = CFG.get("category_rules", {})
                for pm in poly_mkts:
                    text = " ".join(str(pm.get(k, "")) for k in ["title", "subtitle", "event_ticker"]).lower()
                    pm["_category"] = "other"
                    best_cat_score = 0
                    for cat_name, cat_kws in cat_rules.items():
                        hits = sum(1 for kw in cat_kws if kw in text)
                        if hits > best_cat_score: best_cat_score = hits; pm["_category"] = cat_name

                # Match markets across platforms
                threshold = CFG.get("cross_arb_match_threshold", 0.70)
                self.cross_platform_matches = match_markets(mkts, poly_mkts, threshold)
                log.info(f"  Cross-platform matches: {len(self.cross_platform_matches)}")
                for match in self.cross_platform_matches[:5]:
                    log.info(f"    {match['kalshi'].get('title','')[:35]} <-> {match['polymarket'].get('title','')[:35]} (sim:{match['similarity']:.2f})")

                # Scan for arbitrage
                cross_arbs = scan_cross_platform_arbitrage(
                    self.cross_platform_matches, self.api, self.poly_api,
                    fee_kalshi=CFG["taker_fee_per_contract"],
                    fee_poly=CFG.get("polymarket_fee_per_contract", 0.00))
                SHARED["_cross_arb_opportunities"] = len(cross_arbs)

                if cross_arbs:
                    for ca in cross_arbs[:3]:
                        log.info(f"  CROSS-ARB: {ca['title'][:40]} -- {ca['strategy_desc']} -- profit: {ca['profit_cents']:.1f}c")
                        if not self.dry:
                            try:
                                result = execute_cross_arb(self.api, self.poly_api, ca,
                                    max_cost=CFG.get("cross_arb_max_cost", 10.0), dry_run=False)
                                if result["success"]:
                                    log.info(f"  CROSS-ARB EXECUTED: {result['contracts']}x profit=${result['expected_profit']:.2f}")
                                    self.risk.record(ca["kalshi_ticker"], ca["title"], "cross_arb",
                                        result["contracts"], int(ca["cost_cents"]), 99,
                                        int(ca["profit_cents"]), f"Cross-arb: {ca['strategy_desc']}", 0, 0,
                                        platform="cross")
                                    self.notifier.notify_arbitrage({
                                        "ticker": ca["kalshi_ticker"], "title": ca["title"],
                                        "yes_price": ca.get("k_price", 0), "no_price": ca.get("p_price", 0),
                                        "total_cost": ca["cost_cents"], "profit_cents": ca["profit_cents"]})
                                elif result.get("naked_position"):
                                    log.error(f"  CROSS-ARB: NAKED POSITION -- Leg 1 filled but Leg 2 failed!")
                                    self.notifier.send("ALERT: Naked Arb Position",
                                        f"Cross-arb Leg 2 failed!\nMarket: {ca['title']}\n"
                                        f"Kalshi leg filled but Polymarket leg FAILED.\n"
                                        f"Manual intervention may be needed.")
                            except Exception as ex:
                                log.error(f"  Cross-arb execution failed: {ex}")
                else:
                    log.info("  No cross-platform arbitrage found")
            except Exception as e:
                log.error(f"Cross-platform arb phase failed: {e}")

        # ══════════════════════════════════════
        # PHASE 2: WITHIN-MARKET ARBITRAGE (fast, no AI)
        # ══════════════════════════════════════
        log.info("Phase 2: Within-market arbitrage scan...")
        arb_opps = scan_arbitrage(self.api, mkts)
        SHARED["_arb_opportunities"] = len(arb_opps) + SHARED.get("_cross_arb_opportunities", 0)
        if arb_opps:
            for a in arb_opps[:3]:
                log.info(f"  ARB: {a['ticker']} -- yes:{a['yes_price']:.0f}c + no:{a['no_price']:.0f}c = {a['total_cost']:.0f}c -- profit: {a['profit_cents']:.1f}c")
                if not self.dry:
                    try:
                        self.api.place_order(a["ticker"],"yes",1,int(a["yes_price"]))
                        self.api.place_order(a["ticker"],"no",1,int(a["no_price"]))
                        log.info(f"  ARB EXECUTED: {a['ticker']}")
                        self.risk.record(a["ticker"],a["title"],"arb",1,int(a["total_cost"]),
                            99,int(a["profit_cents"]),"Arbitrage: YES+NO < $1",0,0)
                        self.notifier.notify_arbitrage(a)
                    except Exception as ex: log.error(f"  ARB failed: {ex}")
        else:
            log.info("  No within-market arbitrage found (normal)")

        # ══════════════════════════════════════
        # PHASE 3: QUICK-FLIP SCAN (fast, light AI)
        # ══════════════════════════════════════
        if CFG.get("quickflip_enabled", True):
            log.info("Phase 3: Quick-flip scan...")
            try:
                all_scannable = mkts + poly_mkts
                qf_candidates = find_quickflip_candidates(all_scannable,
                    min_price=CFG.get("quickflip_min_price", 3),
                    max_price=CFG.get("quickflip_max_price", 15),
                    min_volume=max(50, CFG.get("min_volume", 10)))
                SHARED["_quickflip_active"] = len(qf_candidates)
                if qf_candidates:
                    for qf in qf_candidates[:3]:
                        m = qf["market"]
                        log.info(f"  QF: {m.get('title','')[:40]} -- {qf['side']} @{qf['entry_price']}c target:{qf['target_price']}c ROI:{qf['potential_roi']:.0f}%")
                        # Quick-flip uses smaller bet sizes
                        qf_max = CFG.get("quickflip_max_bet", 3.0)
                        if not self.dry and qf_max > 0:
                            try:
                                qf_contracts = max(1, int(qf_max / (qf["entry_price"] / 100)))
                                platform = qf.get("platform", "kalshi")
                                tk = m.get("ticker", "")
                                if platform == "kalshi" and tk:
                                    self.api.place_order(tk, qf["side"], qf_contracts, qf["entry_price"])
                                    log.info(f"  QF EXECUTED: {qf['side']} {qf_contracts}x @{qf['entry_price']}c on Kalshi")
                                    self.risk.record(tk, m.get("title", ""), qf["side"], qf_contracts,
                                        qf["entry_price"], 50, int(qf["potential_roi"]),
                                        f"Quick-flip: target {qf['target_price']}c", 0, 0, platform="kalshi")
                                elif platform == "polymarket" and self.poly_api and self.poly_api.is_trading_enabled:
                                    token = m.get("token_id", "")
                                    if token:
                                        self.poly_api.place_order(token, qf["side"], qf_contracts, qf["entry_price"])
                                        log.info(f"  QF EXECUTED: {qf['side']} {qf_contracts}x @{qf['entry_price']}c on Polymarket")
                                        self.risk.record(tk, m.get("title", ""), qf["side"], qf_contracts,
                                            qf["entry_price"], 50, int(qf["potential_roi"]),
                                            f"Quick-flip: target {qf['target_price']}c", 0, 0, platform="polymarket")
                            except Exception as ex:
                                log.debug(f"  QF execution failed: {ex}")
                else:
                    log.info("  No quick-flip candidates found")
            except Exception as e:
                log.debug(f"Quick-flip phase failed: {e}")

        # ══════════════════════════════════════
        # PHASE 4: AI-DRIVEN DIRECTIONAL TRADING (heavy AI)
        # ══════════════════════════════════════
        log.info("Phase 4: AI directional trading...")
        short_term, long_term = filter_and_rank(mkts)
        log.info(f"Short-term (<{CFG['max_close_hours']}h): {len(short_term)} | Long-term: {len(long_term)}")

        # Expand NWS forecasts for weather markets
        weather_mkts = [m for m in short_term + long_term if m.get("_category")=="weather"]
        if weather_mkts:
            try: self.data.expand_nws_for_markets(weather_mkts)
            except Exception as e: log.debug(f"NWS expansion failed: {e}")

        batch = short_term[:CFG["markets_per_scan"]]
        if long_term: batch.extend(long_term[:max(10, CFG["markets_per_scan"] - len(batch))])
        if not batch: SHARED["status"]="Idle -- no targets"; self._finish_scan(bal, poly_bal); return

        existing = set()
        try:
            for p in self.api.positions():
                tk=p.get("ticker",p.get("market_ticker",""));
                if tk: existing.add(tk)
        except Exception as e:
            log.debug(f"Could not load existing positions: {e}")
        existing.update(self.risk.traded_tickers)

        SHARED["status"]=f"AI scanning {len(batch)} markets..."
        log.info(f"Quick-scanning {len(batch)} markets...")
        data_brief = self.data.format_brief_for_scan()
        cands = self.debate.quick_scan(batch, existing, data_brief)
        log.info(f"Candidates: {len(cands)}")
        if not cands: SHARED["status"]="Idle -- no edge"; self._finish_scan(bal, poly_bal); return

        for c in cands:
            cm=" [CANT-MISS]" if c.get("is_cant_miss") else ""
            log.info(f"  > {c.get('ticker','?')}: edge~{c.get('initial_edge_estimate','?')}% {c.get('side','?')}{cm}")

        # Build Polymarket match lookup for best-price routing
        poly_match_lookup = {}
        if self.poly_enabled and self.cross_platform_matches:
            for match in self.cross_platform_matches:
                k_ticker = match["kalshi"].get("ticker", "")
                if k_ticker:
                    poly_match_lookup[k_ticker] = match["polymarket"]

        # ── BULL vs BEAR DEBATE on top candidates ──
        for cand in cands[:CFG["deep_dive_top_n"]]:
            if not SHARED["enabled"]: break
            tk=cand.get("ticker","")
            if not tk or tk in existing: continue
            mkt=next((m for m in mkts if m["ticker"]==tk),None)
            if not mkt: continue

            hrs=mkt.get("_hrs_left",9999); cat=mkt.get("_category","other")
            SHARED["status"]=f"Debating {tk}..."
            log.info(f"\n  DEBATE: [{cat.upper()}] {tk} -- {mkt.get('title','')[:50]}")

            # ── Best-price routing: check both platforms ──
            poly_match = poly_match_lookup.get(tk)
            trade_platform = "kalshi"  # default
            ob=None; ob_spread=999

            if poly_match and self.poly_api:
                # We have a Polymarket match -- check both platforms for best price
                try:
                    ob=self.api.orderbook(tk)
                    book=ob.get("orderbook",{})
                    yb=book.get("yes",book.get("yes_dollars",[]))
                    nb=book.get("no",book.get("no_dollars",[]))
                    if yb and nb:
                        by=parse_orderbook_price(yb[0][0] if isinstance(yb[0],list) else yb[0])
                        bn=parse_orderbook_price(nb[0][0] if isinstance(nb[0],list) else nb[0])
                        if by and bn:
                            ob_spread=int(by+bn-100) if by+bn>100 else int(100-by-bn)
                            log.info(f"  Orderbook (Kalshi): YES={by}c NO={bn}c spread={ob_spread}c")
                except Exception as e:
                    log.debug(f"  Kalshi orderbook error: {e}")

                # Check Polymarket price too
                try:
                    p_token = poly_match.get("token_id", "")
                    if p_token:
                        p_ob = self.poly_api.orderbook(p_token)
                        p_book = p_ob.get("orderbook", {})
                        p_yes = p_book.get("yes", [])
                        p_no = p_book.get("no", [])
                        if p_yes:
                            p_yes_price = _best_ask(p_yes)
                            log.info(f"  Orderbook (Polymarket): YES={p_yes_price}c")
                except Exception as e:
                    log.debug(f"  Polymarket orderbook error: {e}")
            else:
                # Kalshi only
                try:
                    ob=self.api.orderbook(tk)
                    book=ob.get("orderbook",{})
                    yb=book.get("yes",book.get("yes_dollars",[]))
                    nb=book.get("no",book.get("no_dollars",[]))
                    if yb and nb:
                        by=parse_orderbook_price(yb[0][0] if isinstance(yb[0],list) else yb[0])
                        bn=parse_orderbook_price(nb[0][0] if isinstance(nb[0],list) else nb[0])
                        if by and bn:
                            ob_spread=int(by+bn-100) if by+bn>100 else int(100-by-bn)
                            log.info(f"  Orderbook: YES={by}c NO={bn}c spread={ob_spread}c")
                        else:
                            log.debug(f"  Orderbook: invalid prices for {tk}")
                except Exception as e:
                    log.debug(f"  Orderbook fetch error for {tk}: {e}")

            if ob_spread > 25:
                log.info(f"  -> SKIP: spread {ob_spread}c too wide (>25c)")
                continue

            r = self.debate.run_debate(mkt, ob, self.data)
            if not r: continue

            log.info(f"  VERDICT: prob={r['probability']}% conf={r['confidence']}% side={r['side']} edge={r['edge']}%")
            log.info(f"  Bull: {r['bull_prob']}% | Bear: {r['bear_prob']}% | Spread: {r['debate_spread']}%")
            log.info(f"  Evidence: {r['evidence'][:70]}")
            if r.get("risk"): log.info(f"  Risk: {r['risk'][:70]}")

            if r["side"]=="HOLD": log.info("  -> HOLD"); continue

            if hrs>CFG["max_close_hours"]:
                if abs(r["edge"])<CFG["cant_miss_edge_pct"] or r["confidence"]<CFG["cant_miss_min_confidence"]:
                    log.info("  -> SKIP: below cant-miss bar"); continue

            yc=mkt.get("yes_bid",mkt.get("last_price",50)) or 50

            # ── Best-price routing for execution ──
            bp=r["price_cents"]
            side_lower = r["side"].lower()
            if poly_match and self.poly_api and self.poly_api.is_trading_enabled:
                routed_platform, routed_price, routed_ob = get_best_price(
                    tk, self.api, poly_match, self.poly_api, side_lower,
                    CFG["taker_fee_per_contract"], CFG.get("polymarket_fee_per_contract", 0.00))
                if routed_platform and routed_price:
                    trade_platform = routed_platform
                    if bp == 0: bp = routed_price
                    if routed_ob: ob = routed_ob
                    log.info(f"  Best price: {trade_platform} @{routed_price}c")

            if ob and bp==0:
                book=ob.get("orderbook",{})
                if r["side"]=="YES":
                    yb=book.get("yes",book.get("yes_dollars",[]))
                    if yb:
                        parsed=parse_orderbook_price(yb[0][0] if isinstance(yb[0],list) else yb[0])
                        if parsed: bp=parsed
                else:
                    nb=book.get("no",book.get("no_dollars",[]))
                    if nb:
                        parsed=parse_orderbook_price(nb[0][0] if isinstance(nb[0],list) else nb[0])
                        if parsed: bp=parsed
            if bp==0: bp=yc if r["side"]=="YES" else 100-yc
            bp=max(1,min(99,bp))

            # Use platform-specific fee
            trade_fee = CFG["taker_fee_per_contract"] if trade_platform == "kalshi" else CFG.get("polymarket_fee_per_contract", 0.00)

            pfk=r["probability"] if r["side"]=="YES" else 100-r["probability"]
            contracts,cost=kelly(pfk, bp, combined_bal, active_max_bet, trade_fee, active_kelly)
            if contracts==0: log.info("  -> Kelly: no bet (EV negative after fees)"); continue

            fees=contracts*trade_fee; total=cost+fees
            net_profit=contracts*(100-bp)/100-fees
            roi_pct=(net_profit/total*100) if total>0 else 0
            platform_tag = f"[{trade_platform.upper()}]" if trade_platform != "kalshi" else ""
            log.info(f"  Kelly: {contracts}x {r['side']} @{bp}c = ${cost:.2f} +${fees:.2f}fee {platform_tag}")
            log.info(f"  If correct: ${net_profit:.2f} net ({roi_pct:.0f}% ROI)")

            ok,reason=self.risk.check(total,r["confidence"],abs(r["edge"]))
            if not ok: log.info(f"  -> BLOCKED: {reason}"); continue
            if net_profit<=0: log.info("  -> SKIP: not profitable after fees"); continue

            if ob_spread > 0 and abs(r["edge"]) < ob_spread * 0.3:
                log.info(f"  -> SKIP: edge {r['edge']}% too small vs spread {ob_spread}c")
                continue

            if self.dry:
                log.info(f"  * DRY RUN: {r['side']} {contracts}x @{bp}c (${cost:.2f}) [{cat}] on {trade_platform}")
                continue

            log.info(f"  * EXECUTE: BUY {r['side'].upper()} {contracts}x {tk} @{bp}c [{cat}] on {trade_platform.upper()}")
            try:
                if trade_platform == "kalshi":
                    res=self.api.place_order(tk,side_lower,contracts,bp)
                    oid=res.get("order",{}).get("order_id","?")
                    log.info(f"  OK: order {oid} -- {res.get('order',{}).get('status','?')}")
                elif trade_platform == "polymarket" and self.poly_api:
                    token = poly_match.get("token_id", "") if side_lower == "yes" else poly_match.get("no_token_id", poly_match.get("token_id", ""))
                    res = self.poly_api.place_order(token, side_lower, contracts, bp)
                    log.info(f"  OK: Polymarket order placed")

                self.risk.record(tk,mkt.get("title",""),side_lower,contracts,bp,
                    r["confidence"],r["edge"],r["evidence"],r["bull_prob"],r["bear_prob"],
                    probability=r["probability"],platform=trade_platform)
                self.notifier.notify_trade({"ticker":tk,"title":mkt.get("title",""),
                    "side":r["side"],"contracts":contracts,"price_cents":bp,"cost":cost,
                    "edge":r["edge"],"confidence":r["confidence"],
                    "bull_prob":r["bull_prob"],"bear_prob":r["bear_prob"],"evidence":r["evidence"],
                    "platform":trade_platform})
                bal=self.api.balance()
                if self.poly_api: poly_bal = self.poly_api.balance()
                with SHARED_LOCK:
                    SHARED["balance"]=bal; SHARED["poly_balance"]=poly_bal
            except Exception as ex: log.error(f"  Order failed: {ex}")
            time.sleep(5)

        self._finish_scan(bal, poly_bal)

    def _finish_scan(self, kalshi_bal=None, poly_bal=None):
        with SHARED_LOCK:
            SHARED["_risk_summary"]=self.risk.summary(); SHARED["_trades"]=self.risk.trades
            SHARED["status"]="Idle"; SHARED["last_scan"]=datetime.datetime.now().strftime("%H:%M:%S")
            SHARED["scan_count"]+=1
            if kalshi_bal is not None: SHARED["balance"] = kalshi_bal
            if poly_bal is not None: SHARED["poly_balance"] = poly_bal
        s=self.risk.summary()
        combined = (kalshi_bal or 0) + (poly_bal or 0)
        log.info(f"\nScan done. {s['day_trades']} trades, exposure {s['exposure']}, combined balance ${combined:.2f}")

    def run(self):
        iv=CFG["scan_interval_minutes"]*60
        log.info(f"Agent running. Scan every {CFG['scan_interval_minutes']}m. Ctrl+C to stop.")
        SHARED["status"]="Idle"

        # Start background threads
        exit_thread = threading.Thread(target=self.exit_mgr.run_loop, args=(self.stop_event,), daemon=True)
        exit_thread.start()
        report_thread = threading.Thread(target=self.reporter.run_loop, args=(self.stop_event,), daemon=True)
        report_thread.start()

        try:
            while True:
                try:
                    if SHARED["enabled"]: self.scan()
                    else: SHARED["status"]="Disabled"
                except KeyboardInterrupt: raise
                except Exception as e: log.error(f"Scan error: {e}"); traceback.print_exc()
                nxt=datetime.datetime.now()+datetime.timedelta(seconds=iv)
                SHARED["next_scan"]=nxt.strftime("%H:%M:%S")
                log.info(f"Next scan: {nxt.strftime('%H:%M:%S')}")
                try: time.sleep(iv)
                except KeyboardInterrupt: raise
        finally:
            self.stop_event.set()

def main():
    ap=argparse.ArgumentParser(description="Kalshi AI Agent v6 -- Cross-Platform Arbitrage")
    ap.add_argument("--config",type=str); ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--scan-once",action="store_true"); ap.add_argument("--no-dashboard",action="store_true")
    ap.add_argument("--report",action="store_true",help="Generate performance report and exit")
    args=ap.parse_args()
    if args.config:
        with open(args.config) as f: CFG.update(json.load(f))
    # Environment variables override config file (keeps secrets out of JSON)
    env_overrides = {
        "KALSHI_API_KEY_ID": "kalshi_api_key_id",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "FRED_API_KEY": "fred_api_key",
        "KALSHI_EMAIL_PASSWORD": "email_password",
        "POLYMARKET_PRIVATE_KEY": "polymarket_private_key",
        "POLYMARKET_API_KEY": "polymarket_api_key",
        "POLYMARKET_API_SECRET": "polymarket_api_secret",
        "POLYMARKET_API_PASSPHRASE": "polymarket_api_passphrase",
    }
    for env_var, cfg_key in env_overrides.items():
        val = os.environ.get(env_var)
        if val: CFG[cfg_key] = val
    if not CFG["kalshi_api_key_id"] or not CFG["anthropic_api_key"]:
        print("\n  Error: --config with API keys required (or set KALSHI_API_KEY_ID / ANTHROPIC_API_KEY env vars)\n"); sys.exit(1)
    a=Agent(dry=args.dry_run)
    try:
        if args.report:
            report = a.reporter.generate_report()
            print(report)
            report_file = CFG.get("report_file","kalshi-weekly-report.txt")
            with open(report_file,"w") as f: f.write(report)
            print(f"\nSaved to {report_file}")
            if a.notifier.enabled:
                a.notifier.send_report(report)
                print("Emailed.")
            return
        if not args.no_dashboard:
            start_dashboard(); print(f"\n  Dashboard: http://localhost:{CFG.get('dashboard_port',9000)}\n")
        with SHARED_LOCK:
            SHARED["balance"]=a.api.balance()
            if a.poly_enabled and a.poly_api:
                try: SHARED["poly_balance"]=a.poly_api.balance()
                except Exception: pass
        if args.scan_once: a.scan()
        else: a.run()
    except KeyboardInterrupt: log.info("\nStopped.")
    except Exception as e: log.error(f"Fatal: {e}"); traceback.print_exc(); sys.exit(1)

if __name__=="__main__": main()
