#!/usr/bin/env python3
"""
Pre-fetch live data from NWS Weather API and FRED Economic Data.
Returns verified government data for use in market analysis.

Usage:
  python data_fetcher.py                          # NWS only (no key needed)
  python data_fetcher.py --fred-key YOUR_KEY      # NWS + FRED
  python data_fetcher.py --city "denver"           # Single city forecast
  python data_fetcher.py --fred-series DFF         # Single FRED series
"""
import argparse, json, time, sys
import requests

CITY_COORDS = {
    "new york":(40.7128,-74.0060),"nyc":(40.7128,-74.0060),
    "chicago":(41.8781,-87.6298),"los angeles":(34.0522,-118.2437),
    "miami":(25.7617,-80.1918),"denver":(39.7392,-104.9903),
    "houston":(29.7604,-95.3698),"phoenix":(33.4484,-112.0740),
    "philadelphia":(39.9526,-75.1652),"san antonio":(29.4241,-98.4936),
    "dallas":(32.7767,-96.7970),"san francisco":(37.7749,-122.4194),
    "seattle":(47.6062,-122.3321),"washington":(38.9072,-77.0369),
    "boston":(42.3601,-71.0589),"atlanta":(33.7490,-84.3880),
    "detroit":(42.3314,-83.0458),"minneapolis":(44.9778,-93.2650),
    "las vegas":(36.1699,-115.1398),"portland":(45.5152,-122.6784),
    "austin":(30.2672,-97.7431),"nashville":(36.1627,-86.7816),
    "orlando":(28.5383,-81.3792),"charlotte":(35.2271,-80.8431),
    "san diego":(32.7157,-117.1611),"st. louis":(38.6270,-90.1994),
    "tampa":(27.9506,-82.4572),"pittsburgh":(40.4406,-79.9959),
    "baltimore":(39.2904,-76.6122),"cleveland":(41.4993,-81.6944),
    "kansas city":(39.0997,-94.5786),"columbus":(39.9612,-82.9988),
    "indianapolis":(39.7684,-86.1581),"milwaukee":(43.0389,-87.9065),
    "sacramento":(38.5816,-121.4944),"memphis":(35.1495,-90.0490),
    "oklahoma city":(35.4676,-97.5164),"raleigh":(35.7796,-78.6382),
    "louisville":(38.2527,-85.7585),"salt lake":(40.7608,-111.8910),
    "new orleans":(29.9511,-90.0715),"cincinnati":(39.1031,-84.5120),
}

FRED_SERIES = {
    "fed_funds":"DFF","cpi":"CPIAUCSL","core_cpi":"CPILFESL",
    "unemployment":"UNRATE","nonfarm":"PAYEMS","jobless_claims":"ICSA",
    "gdp":"GDP","gas_price":"GASREGW","treasury_10y":"DGS10",
    "treasury_2y":"DGS2","sp500":"SP500",
}

def fetch_nws(city):
    """Fetch NWS forecast for a single city. Returns list of period forecasts."""
    if city.lower() not in CITY_COORDS:
        return {"error": f"Unknown city: {city}. Available: {', '.join(sorted(CITY_COORDS.keys()))}"}
    lat, lon = CITY_COORDS[city.lower()]
    try:
        r = requests.get(f"https://api.weather.gov/points/{lat},{lon}",
            headers={"User-Agent":"KalshiSkill/1.0","Accept":"application/json"}, timeout=10)
        if r.status_code != 200: return {"error": f"NWS points failed: {r.status_code}"}
        forecast_url = r.json().get("properties",{}).get("forecast","")
        if not forecast_url: return {"error": "No forecast URL"}
        r2 = requests.get(forecast_url,
            headers={"User-Agent":"KalshiSkill/1.0","Accept":"application/json"}, timeout=10)
        if r2.status_code != 200: return {"error": f"NWS forecast failed: {r2.status_code}"}
        periods = r2.json().get("properties",{}).get("periods",[])
        result = []
        for p in periods[:6]:
            result.append({
                "name": p.get("name",""), "temp": p.get("temperature"),
                "temp_unit": p.get("temperatureUnit","F"),
                "wind_speed": p.get("windSpeed",""),
                "precip_pct": p.get("probabilityOfPrecipitation",{}).get("value"),
                "forecast": p.get("shortForecast",""),
                "detailed": p.get("detailedForecast","")[:150],
            })
        return {"city": city, "periods": result}
    except Exception as e:
        return {"error": str(e)}

def fetch_nws_batch(cities=None):
    """Fetch NWS for multiple cities."""
    if cities is None:
        cities = ["new york","chicago","miami","denver","houston","phoenix","los angeles","seattle"]
    results = {}
    for city in cities:
        results[city] = fetch_nws(city)
        time.sleep(0.3)
    return results

def fetch_fred(series_name, api_key):
    """Fetch latest value from FRED."""
    sid = FRED_SERIES.get(series_name, series_name)
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id":sid,"api_key":api_key,"file_type":"json","sort_order":"desc","limit":"3"},
            timeout=10)
        if r.status_code != 200: return {"error": f"FRED {r.status_code}"}
        for o in r.json().get("observations",[]):
            if o.get("value",".") != ".":
                return {"series": sid, "name": series_name, "value": o["value"], "date": o["date"]}
        return {"error": "No valid observations"}
    except Exception as e:
        return {"error": str(e)}

def fetch_fred_all(api_key):
    """Fetch all key FRED series."""
    results = {}
    for name in ["fed_funds","cpi","core_cpi","unemployment","nonfarm",
                  "jobless_claims","gas_price","treasury_10y","treasury_2y"]:
        results[name] = fetch_fred(name, api_key)
        time.sleep(0.2)
    return results

def main():
    ap = argparse.ArgumentParser(description="Live Data Fetcher (NWS + FRED)")
    ap.add_argument("--fred-key", default="", help="FRED API key")
    ap.add_argument("--city", default="", help="Single city NWS forecast")
    ap.add_argument("--fred-series", default="", help="Single FRED series")
    ap.add_argument("--all", action="store_true", help="Fetch all data")
    args = ap.parse_args()

    output = {}

    if args.city:
        output["nws"] = fetch_nws(args.city)
    elif args.fred_series and args.fred_key:
        output["fred"] = fetch_fred(args.fred_series, args.fred_key)
    else:
        # Default: fetch all
        print("Fetching NWS weather forecasts...", file=sys.stderr)
        output["nws"] = fetch_nws_batch()
        if args.fred_key:
            print("Fetching FRED economic data...", file=sys.stderr)
            output["fred"] = fetch_fred_all(args.fred_key)
        feeds = sum(1 for v in output.get("nws",{}).values() if not isinstance(v,dict) or "error" not in v)
        feeds += sum(1 for v in output.get("fred",{}).values() if isinstance(v,dict) and "error" not in v) if "fred" in output else 0
        print(f"Loaded {feeds} data feeds", file=sys.stderr)

    print(json.dumps(output, indent=2, default=str))

if __name__ == "__main__":
    main()
