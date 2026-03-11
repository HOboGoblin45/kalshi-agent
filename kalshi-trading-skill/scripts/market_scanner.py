#!/usr/bin/env python3
"""
Market scanner: filter, rank, and detect arbitrage on Kalshi markets.

Usage:
  python market_scanner.py --action filter --key-id KEY --key-path PATH
  python market_scanner.py --action arbitrage --key-id KEY --key-path PATH
  python market_scanner.py --action detail --key-id KEY --key-path PATH --ticker TICKER
"""
import argparse, json, sys, time, datetime
sys.path.insert(0, ".")
from kalshi_api import KalshiClient

TARGET_KEYWORDS = [
    "fed","fomc","interest rate","inflation","cpi","pce","gdp","recession",
    "unemployment","jobs","nonfarm","payroll","treasury","yield","mortgage",
    "gas price","oil price","temperature","hurricane","tornado","rainfall",
    "snowfall","weather","climate","heat","cold","storm","s&p","nasdaq","dow",
    "sec","regulation","congress","legislation","bill","executive order",
    "tariff","trade war","crypto regulation","bitcoin etf","stablecoin",
    "debt ceiling","government shutdown","sanctions","opec","oil production"
]

CATEGORY_RULES = {
    "weather":["temperature","hurricane","tornado","rainfall","snowfall","weather","climate","heat","cold","storm","wind","flood"],
    "fed_rates":["fed","fomc","interest rate","fed funds","powell","rate cut","rate hike","monetary policy"],
    "inflation":["inflation","cpi","pce","consumer price","core inflation"],
    "employment":["unemployment","jobs","nonfarm","payroll","jobless claims","employment"],
    "gdp_growth":["gdp","recession","economic growth","gross domestic"],
    "markets":["s&p","nasdaq","dow","stock market","treasury","yield","bond"],
    "energy":["gas price","oil price","oil production","opec","wti","brent","gasoline"],
    "policy":["sec","regulation","congress","legislation","bill","executive order","tariff","trade war","crypto regulation","bitcoin etf","stablecoin","debt ceiling","government shutdown","sanctions"],
}

def calc_hours_left(m):
    close = m.get("close_time") or m.get("expiration_time") or ""
    if not close: return 9999
    try:
        ct = datetime.datetime.fromisoformat(close.replace("Z","+00:00"))
        return (ct - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600
    except: return 9999

def categorize(m):
    text = " ".join(str(m.get(k,"")) for k in ["title","ticker","category","subtitle","event_ticker"]).lower()
    best, best_score = "other", 0
    for cat, kws in CATEGORY_RULES.items():
        hits = sum(1 for kw in kws if kw in text)
        if hits > best_score: best_score = hits; best = cat
    return best

def score_market(m):
    s = 0
    vol = m.get("volume",0) or 0
    yc = m.get("yes_bid", m.get("last_price",50)) or 50
    hrs = m.get("_hrs_left", 9999)
    cat = m.get("_category", "other")
    if vol>=1000: s+=4
    elif vol>=500: s+=3
    elif vol>=100: s+=2
    elif vol>=20: s+=1
    if 25<=yc<=75: s+=3
    elif 15<=yc<=85: s+=2
    elif 8<=yc<=92: s+=1
    if 1<=hrs<=6: s+=6
    elif 6<hrs<=12: s+=5
    elif 12<hrs<=24: s+=4
    elif 24<hrs<=48: s+=2
    if cat in ("weather","fed_rates","inflation","employment"): s+=3
    elif cat in ("energy","policy"): s+=2
    elif cat in ("gdp_growth","markets"): s+=1
    if vol<50: s-=2
    if hrs<=12 and (yc>=85 or yc<=15): s+=2
    return s

def filter_markets(markets, max_close_hours=48, min_volume=20, min_price=8, max_price=92):
    results = []
    for m in markets:
        yc = m.get("yes_bid", m.get("last_price",50)) or 50
        if yc > max_price or yc < min_price: continue
        if (m.get("volume",0) or 0) < min_volume: continue
        hrs = calc_hours_left(m)
        if hrs < 1: continue
        m["_hrs_left"] = round(hrs, 1)
        text = " ".join(str(m.get(k,"")) for k in ["title","ticker","category","subtitle","event_ticker"]).lower()
        if not any(kw in text for kw in TARGET_KEYWORDS): continue
        m["_category"] = categorize(m)
        m["_score"] = score_market(m)
        results.append(m)
    results.sort(key=lambda x: x.get("_score",0), reverse=True)
    return results

def scan_arbitrage(client, markets, fee=0.07):
    opportunities = []
    candidates = [m for m in markets if (m.get("volume",0) or 0) >= 50][:80]
    for m in candidates:
        try:
            ob = client.orderbook(m["ticker"])
            book = ob.get("orderbook",{})
            yes_bids = book.get("yes", book.get("yes_dollars",[]))
            no_bids = book.get("no", book.get("no_dollars",[]))
            if not yes_bids or not no_bids: continue
            by = float(str(yes_bids[0][0] if isinstance(yes_bids[0],list) else yes_bids[0]).replace("$",""))
            bn = float(str(no_bids[0][0] if isinstance(no_bids[0],list) else no_bids[0]).replace("$",""))
            if by<1: by*=100
            if bn<1: bn*=100
            fee_cost = fee*2*100
            if by+bn+fee_cost < 100:
                profit = 100 - by - bn - fee_cost
                opportunities.append({
                    "ticker":m["ticker"],"title":m.get("title",""),
                    "yes_price":by,"no_price":bn,
                    "total_cost":by+bn,"profit_cents":profit
                })
        except: continue
        time.sleep(0.1)
    opportunities.sort(key=lambda x: x["profit_cents"], reverse=True)
    return opportunities

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", required=True, choices=["filter","arbitrage","detail"])
    ap.add_argument("--key-id", required=True)
    ap.add_argument("--key-path", required=True)
    ap.add_argument("--environment", default="prod")
    ap.add_argument("--ticker", default="")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    client = KalshiClient(args.key_id, args.key_path, args.environment)

    if args.action == "filter":
        mkts = client.all_markets()
        filtered = filter_markets(mkts)
        display = []
        for m in filtered[:args.limit]:
            display.append({
                "ticker":m["ticker"],"title":m.get("title",""),
                "subtitle":m.get("subtitle",""),
                "yes_bid":m.get("yes_bid"), "volume":m.get("volume",0),
                "hours_left":m["_hrs_left"],"category":m["_category"],"score":m["_score"],
                "close_time":m.get("close_time","")
            })
        print(json.dumps({"total_open":len(mkts),"filtered":len(filtered),"top":display}, indent=2, default=str))

    elif args.action == "arbitrage":
        mkts = client.all_markets()
        arbs = scan_arbitrage(client, mkts)
        print(json.dumps({"opportunities":len(arbs),"results":arbs[:10]}, indent=2))

    elif args.action == "detail":
        if not args.ticker: print("Error: --ticker required"); sys.exit(1)
        ob = client.orderbook(args.ticker)
        print(json.dumps(ob, indent=2, default=str))

if __name__ == "__main__":
    main()
