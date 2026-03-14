"""Live data pre-fetching from NWS, FRED, and sports APIs."""
import time, re
import requests as req_lib

from modules.config import CFG, CITY_COORDS, FRED_SERIES, log


class DataFetcher:
    """Pre-fetch live data from NWS and FRED before AI analysis.
    This gives the AI verified numbers instead of relying on web search."""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 600  # 10 min cache
        self.fred_key = CFG.get("fred_api_key", "")
        self.brief = {}

    def _cached(self, key):
        if key in self.cache:
            val, ts = self.cache[key]
            if time.time() - ts < self.cache_ttl:
                return val
        return None

    def _set_cache(self, key, val):
        self.cache[key] = (val, time.time())
        return val

    FRED_BY_CATEGORY = {
        "fed_rates": ["fed_funds", "treasury_10y", "treasury_2y"],
        "inflation": ["cpi", "core_cpi"],
        "employment": ["unemployment", "nonfarm", "jobless_claims"],
        "gdp_growth": ["fed_funds"],
        "markets": ["treasury_10y", "treasury_2y"],
        "energy": ["gas_price"],
    }

    # ESPN public API endpoints (no key needed)
    ESPN_SCOREBOARD = {
        "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        "ncaam": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
        "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
        "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    }

    def _fetch_espn_scores(self):
        """Fetch today's games, scores, and odds from ESPN's free API."""
        cached = self._cached("espn_scores")
        if cached: return cached
        all_games = []
        for sport, url in self.ESPN_SCOREBOARD.items():
            try:
                r = req_lib.get(url, timeout=10)
                if r.status_code != 200: continue
                data = r.json()
                events = data.get("events", [])
                for ev in events:
                    comp = ev.get("competitions", [{}])[0]
                    teams = comp.get("competitors", [])
                    if len(teams) < 2: continue
                    home = teams[0]; away = teams[1]
                    game = {
                        "sport": sport,
                        "status": comp.get("status", {}).get("type", {}).get("name", ""),
                        "home_team": home.get("team", {}).get("displayName", ""),
                        "away_team": away.get("team", {}).get("displayName", ""),
                        "home_score": home.get("score", "0"),
                        "away_score": away.get("score", "0"),
                        "home_record": home.get("records", [{}])[0].get("summary", "") if home.get("records") else "",
                        "away_record": away.get("records", [{}])[0].get("summary", "") if away.get("records") else "",
                        "start_time": ev.get("date", ""),
                        "headline": ev.get("name", ""),
                    }
                    # Extract odds if available
                    odds = comp.get("odds", [{}])
                    if odds and isinstance(odds, list) and odds[0]:
                        o = odds[0]
                        game["spread"] = o.get("details", "")
                        game["over_under"] = o.get("overUnder", "")
                    # Extract leaders (top performers)
                    leaders = comp.get("leaders", [])
                    for ld in leaders[:2]:
                        cat = ld.get("name", "")
                        entries = ld.get("leaders", [])
                        if entries:
                            top = entries[0]
                            athlete = top.get("athlete", {}).get("displayName", "")
                            val = top.get("displayValue", "")
                            game[f"leader_{cat}"] = f"{athlete}: {val}"
                    all_games.append(game)
                time.sleep(0.2)
            except Exception as e:
                log.debug(f"ESPN {sport} fetch failed: {e}")
        return self._set_cache("espn_scores", all_games)

    def get_sports_for_market(self, market_title):
        """Find relevant sports data for a market by matching team/player names."""
        games = self.brief.get("sports_games", [])
        if not games: return ""
        title_lower = market_title.lower()
        relevant = []
        for g in games:
            # Match by team name
            home_lower = g["home_team"].lower()
            away_lower = g["away_team"].lower()
            # Check if any word from team name appears in market title
            home_words = [w for w in home_lower.split() if len(w) > 3]
            away_words = [w for w in away_lower.split() if len(w) > 3]
            if any(w in title_lower for w in home_words + away_words):
                relevant.append(g)
        if not relevant: return ""
        lines = []
        for g in relevant[:3]:
            line = f"  {g['away_team']} @ {g['home_team']}"
            if g.get("status") == "STATUS_IN_PROGRESS":
                line += f" | LIVE: {g['away_score']}-{g['home_score']}"
            elif g.get("status") == "STATUS_FINAL":
                line += f" | FINAL: {g['away_score']}-{g['home_score']}"
            else:
                line += f" | {g['start_time'][:16]}"
            if g.get("home_record"): line += f" | Records: {g['away_record']} vs {g['home_record']}"
            if g.get("spread"): line += f" | Spread: {g['spread']}"
            if g.get("over_under"): line += f" | O/U: {g['over_under']}"
            for k, v in g.items():
                if k.startswith("leader_"): line += f" | {k.replace('leader_', '').title()}: {v}"
            lines.append(line)
        return "\n".join(lines)

    def fetch_all(self, market_categories=None):
        """Run before each scan. Populates self.brief with latest data."""
        self.brief = {}
        self.feed_status = {"nws": False, "fred": False, "sports": False}

        need_nws = market_categories is None or "weather" in market_categories
        need_sports = market_categories is None or "sports" in market_categories
        need_fred_cats = set()
        if market_categories is None:
            need_fred_cats = set(self.FRED_BY_CATEGORY.keys())
        else:
            need_fred_cats = market_categories & set(self.FRED_BY_CATEGORY.keys())

        # Fetch sports data (ESPN is free, no key needed)
        if need_sports:
            try:
                games = self._fetch_espn_scores()
                self.brief["sports_games"] = games
                if games:
                    self.feed_status["sports"] = True
                    log.info(f"ESPN: {len(games)} games loaded")
            except Exception as e:
                log.warning(f"ESPN prefetch failed: {e}")
                self.brief["sports_games"] = []
        else:
            self.brief["sports_games"] = []

        if need_nws:
            try:
                self.brief["nws_forecasts"] = self._fetch_nws_batch()
                if self.brief["nws_forecasts"]:
                    self.feed_status["nws"] = True
            except Exception as e:
                log.warning(f"NWS prefetch failed: {e}")
                self.brief["nws_forecasts"] = {}
        else:
            log.debug("Data prefetch: skipping NWS (no weather markets)")
            self.brief["nws_forecasts"] = {}

        if self.fred_key and need_fred_cats:
            fred_ok = 0
            needed_series = set()
            for cat in need_fred_cats:
                needed_series.update(self.FRED_BY_CATEGORY.get(cat, []))
            for key in needed_series:
                try:
                    self.brief[key] = self._fetch_fred(key)
                    if self.brief[key]: fred_ok += 1
                except Exception as e:
                    log.debug(f"FRED {key} failed: {e}")
                    self.brief[key] = None
            if fred_ok > 0:
                self.feed_status["fred"] = True
            skipped = 9 - len(needed_series)
            if skipped > 0:
                log.debug(f"Data prefetch: skipped {skipped} irrelevant FRED series")
        elif not need_fred_cats:
            log.debug("Data prefetch: skipping FRED (no econ/finance markets)")

        data_count = sum(1 for v in self.brief.values() if v)
        if data_count == 0 and (need_nws or need_fred_cats):
            log.warning("Data prefetch: ZERO feeds loaded -- AI will rely on web search only")
        elif data_count > 0:
            log.info(f"Data prefetch: {data_count} feeds loaded (NWS:{'OK' if self.feed_status['nws'] else 'SKIP'} FRED:{'OK' if self.feed_status['fred'] else 'SKIP'})")
        return self.brief

    def _fetch_nws_batch(self):
        cached = self._cached("nws_batch")
        if cached: return cached
        results = {}
        top_cities = ["new york", "chicago", "miami", "denver", "houston", "phoenix", "los angeles", "seattle"]
        for city in top_cities:
            try:
                lat, lon = CITY_COORDS[city]
                r = req_lib.get(f"https://api.weather.gov/points/{lat},{lon}",
                    headers={"User-Agent": "KalshiAgent/1.0", "Accept": "application/json"}, timeout=10)
                if r.status_code != 200: continue
                grid = r.json().get("properties", {})
                forecast_url = grid.get("forecast", "")
                if not forecast_url: continue
                r2 = req_lib.get(forecast_url,
                    headers={"User-Agent": "KalshiAgent/1.0", "Accept": "application/json"}, timeout=10)
                if r2.status_code != 200: continue
                periods = r2.json().get("properties", {}).get("periods", [])
                if periods:
                    forecasts = []
                    for p in periods[:4]:
                        forecasts.append({
                            "name": p.get("name", ""), "temp": p.get("temperature"),
                            "temp_unit": p.get("temperatureUnit", "F"),
                            "wind_speed": p.get("windSpeed", ""),
                            "precip_pct": p.get("probabilityOfPrecipitation", {}).get("value"),
                            "short": p.get("shortForecast", ""),
                        })
                    results[city] = forecasts
                time.sleep(0.3)
            except Exception as e:
                log.debug(f"NWS fetch failed for {city}: {e}")
                continue
        return self._set_cache("nws_batch", results)

    def _fetch_fred(self, series_name):
        cached = self._cached(f"fred_{series_name}")
        if cached: return cached
        sid = FRED_SERIES.get(series_name)
        if not sid or not self.fred_key: return None
        try:
            r = req_lib.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={"series_id": sid, "api_key": self.fred_key, "file_type": "json",
                        "sort_order": "desc", "limit": "3"},
                timeout=10)
            if r.status_code != 200: return None
            obs = r.json().get("observations", [])
            for o in obs:
                if o.get("value", ".") != ".":
                    result = {"value": o["value"], "date": o["date"], "series": sid}
                    return self._set_cache(f"fred_{series_name}", result)
        except Exception as e:
            log.debug(f"FRED fetch failed for {series_name}: {e}")
        return None

    def format_brief_for_scan(self):
        lines = []
        fred_labels = {
            "fed_funds": "Fed Funds Rate", "cpi": "CPI (latest)",
            "unemployment": "Unemployment Rate", "jobless_claims": "Initial Jobless Claims",
            "gas_price": "Regular Gas Price", "treasury_10y": "10Y Treasury Yield",
            "treasury_2y": "2Y Treasury Yield",
        }
        for key, label in fred_labels.items():
            d = self.brief.get(key)
            if d: lines.append(f"  {label}: {d['value']} (as of {d['date']})")
        nws = self.brief.get("nws_forecasts", {})
        if nws:
            lines.append("  Weather forecasts (NWS official):")
            for city, periods in nws.items():
                if periods:
                    p = periods[0]
                    precip = f", {p['precip_pct']}% precip" if p.get('precip_pct') is not None else ""
                    lines.append(f"    {city.title()}: {p['name']} {p['temp']}°{p['temp_unit']}{precip} -- {p['short']}")
        # Sports data from ESPN
        games = self.brief.get("sports_games", [])
        if games:
            lines.append("  Live sports data (ESPN):")
            for g in games[:20]:
                line = f"    {g['sport'].upper()}: {g['away_team']} @ {g['home_team']}"
                if g.get("status") == "STATUS_IN_PROGRESS":
                    line += f" | LIVE {g['away_score']}-{g['home_score']}"
                elif g.get("status") == "STATUS_FINAL":
                    line += f" | FINAL {g['away_score']}-{g['home_score']}"
                else:
                    line += f" | {g.get('start_time', '')[:16]}"
                if g.get("home_record"): line += f" | {g['away_record']} vs {g['home_record']}"
                if g.get("spread"): line += f" | Line: {g['spread']}"
                if g.get("over_under"): line += f" | O/U: {g['over_under']}"
                lines.append(line)
        return "\n".join(lines) if lines else ""

    def get_weather_for_market(self, market_title):
        title_lower = market_title.lower()
        nws = self.brief.get("nws_forecasts", {})
        for city, forecasts in nws.items():
            if city in title_lower or city.replace(" ", "") in title_lower:
                return city, forecasts
        for city in CITY_COORDS:
            if city in title_lower:
                return city, None
        return None, None

    def get_fred_for_category(self, category):
        mapping = {
            "fed_rates": ["fed_funds", "treasury_2y", "treasury_10y"],
            "inflation": ["cpi", "core_cpi"],
            "employment": ["unemployment", "nonfarm", "jobless_claims"],
            "gdp_growth": ["gdp"], "energy": ["gas_price"],
            "markets": ["treasury_10y", "treasury_2y"],
        }
        series_keys = mapping.get(category, [])
        lines = []
        for key in series_keys:
            d = self.brief.get(key)
            if d: lines.append(f"{key}: {d['value']} (as of {d['date']})")
        return " | ".join(lines) if lines else ""

    def expand_nws_for_markets(self, markets):
        nws = self.brief.get("nws_forecasts", {})
        fetched_cities = set(nws.keys())
        new_fetches = 0
        for m in markets:
            if m.get("_category") != "weather": continue
            title_lower = m.get("title", "").lower() + " " + m.get("subtitle", "").lower()
            for city, coords in CITY_COORDS.items():
                if city in fetched_cities: continue
                if city in title_lower or city.replace(" ", "") in title_lower:
                    try:
                        lat, lon = coords
                        r = req_lib.get(f"https://api.weather.gov/points/{lat},{lon}",
                            headers={"User-Agent": "KalshiAgent/1.0", "Accept": "application/json"}, timeout=10)
                        if r.status_code != 200: continue
                        forecast_url = r.json().get("properties", {}).get("forecast", "")
                        if not forecast_url: continue
                        r2 = req_lib.get(forecast_url,
                            headers={"User-Agent": "KalshiAgent/1.0", "Accept": "application/json"}, timeout=10)
                        if r2.status_code != 200: continue
                        periods = r2.json().get("properties", {}).get("periods", [])
                        if periods:
                            forecasts = []
                            for p in periods[:4]:
                                forecasts.append({
                                    "name": p.get("name", ""), "temp": p.get("temperature"),
                                    "temp_unit": p.get("temperatureUnit", "F"),
                                    "wind_speed": p.get("windSpeed", ""),
                                    "precip_pct": p.get("probabilityOfPrecipitation", {}).get("value"),
                                    "short": p.get("shortForecast", ""),
                                })
                            nws[city] = forecasts
                            fetched_cities.add(city)
                            new_fetches += 1
                            log.info(f"  NWS expanded: {city.title()} -> {forecasts[0]['temp']}°{forecasts[0]['temp_unit']}")
                        time.sleep(0.3)
                    except Exception as e:
                        log.debug(f"NWS expand failed for {city}: {e}")
                        continue
                    if new_fetches >= 6: break
            if new_fetches >= 6: break
        self.brief["nws_forecasts"] = nws
