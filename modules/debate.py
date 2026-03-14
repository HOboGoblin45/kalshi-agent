"""Bull vs Bear debate engine for AI-driven trade analysis."""
import json, re, time, datetime
import requests as req_lib

from modules.config import CFG, log, parse_int

try:
    import anthropic; HAS_SDK = True
except ImportError:
    HAS_SDK = False


class DebateEngine:
    """Three-step adversarial analysis: Bull -> Bear -> Synthesis."""

    def __init__(self):
        self.api_key = CFG["anthropic_api_key"]
        self.client = anthropic.Anthropic(api_key=self.api_key) if HAS_SDK else None
        self._last = 0
        self._gap = 6

    def _throttle(self):
        e = time.time() - self._last
        if e < self._gap: time.sleep(self._gap - e)
        self._last = time.time()

    def _call(self, prompt, max_tok=1200, retries=2, use_search=True):
        self._throttle()
        tools = [{"type": "web_search_20250305", "name": "web_search"}] if use_search else []
        for attempt in range(retries):
            try:
                if HAS_SDK:
                    kwargs = dict(model="claude-sonnet-4-20250514", max_tokens=max_tok,
                        messages=[{"role": "user", "content": prompt}])
                    if tools: kwargs["tools"] = tools
                    resp = self.client.messages.create(**kwargs)
                    return "\n".join(b.text for b in resp.content if hasattr(b, "text"))
                else:
                    body = {"model": "claude-sonnet-4-20250514", "max_tokens": max_tok,
                            "messages": [{"role": "user", "content": prompt}]}
                    if tools: body["tools"] = tools
                    r = req_lib.post("https://api.anthropic.com/v1/messages",
                        headers={"Content-Type": "application/json", "x-api-key": self.api_key,
                                 "anthropic-version": "2023-06-01"},
                        json=body, timeout=120)
                    if r.status_code == 429:
                        w = 60 * (attempt + 1); log.warning(f"Rate limit, wait {w}s"); time.sleep(w); continue
                    r.raise_for_status()
                    return "\n".join(b["text"] for b in r.json()["content"] if b.get("type") == "text")
            except Exception as e:
                if "rate_limit" in str(e).lower() and attempt < retries - 1:
                    time.sleep(60 * (attempt + 1)); continue
                raise
        return ""

    def quick_scan(self, markets, skip_tickers, data_brief=""):
        lines = []
        for m in markets:
            if m["ticker"] in skip_tickers: continue
            t = m.get("title", ""); sub = m.get("subtitle", "")
            yc = m.get("display_price", m.get("yes_bid", m.get("last_price", "?"))) or "?"; vol = m.get("volume", 0) or 0
            hrs = m.get("_hrs_left", "?"); cat = m.get("_category", "other")
            if isinstance(hrs, float): hrs = f"{hrs:.0f}"
            desc = t + (f" [{sub}]" if sub and sub != t else "")
            lines.append(f"  {m['ticker']}: ({cat.upper()}) {desc} -- yes:{yc}c -- vol:{vol} -- {hrs}h left")
        if not lines: return []
        mlist = "\n".join(lines[:CFG["markets_per_scan"]])

        data_section = ""
        if data_brief:
            data_section = f"""

LIVE DATA (pre-fetched from official sources -- use these as ground truth):
{data_brief}

IMPORTANT: Compare the live data above DIRECTLY to the market prices. If NWS says 62°F and a market asks "above 58°F?" priced at 50c, that's concrete evidence of a 10%+ edge. If FRED shows Fed Funds at 5.33% and a market implies otherwise, that's edge."""

        prompt = f"""You are a disciplined prediction market trader. Find concrete edge using data and exploit mispricings. Focus on verifiable facts vs market prices.

TODAY: {datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")}

FIND EDGE BY: Searching for CURRENT data (NWS forecasts, ESPN scores/odds, FRED economic data, news, data releases) and comparing to market prices. Stale prices after news/data releases = real edge. Near-expiry (<6h) markets with clear outcomes = best opportunities. Cheap contracts (10-20c) where true prob is higher = asymmetric bets. Account for ~$0.07/contract fees on BOTH sides.

MARKETS:
{mlist}
{data_section}

Return up to 5 candidates as a JSON array. Use EXACT tickers from above. One JSON object per market.
[{{{{"ticker":"EXACT-TICKER-HERE","title":"short desc","category":"weather","market_yes_cents":65,"initial_edge_estimate":8,"side":"YES","evidence":"specific fact vs market price","is_cant_miss":false}}}}]
Return [] ONLY if no edge found after research."""

        for attempt in range(2):
            try:
                text = self._call(prompt, 1500)
                log.debug(f"Quick scan raw response (attempt {attempt + 1}): {text[:500]}")
                s, e = text.find("["), text.rfind("]") + 1
                if s >= 0 and e > s:
                    result = json.loads(text[s:e])
                    if isinstance(result, list): return result
                log.warning(f"Quick scan: JSON parse failed (attempt {attempt + 1}), trying regex fallback")
                fallback = []
                for m in re.finditer(r'"ticker"\s*:\s*"([^"]+)"', text):
                    ticker = m.group(1)
                    chunk = text[max(0, m.start() - 50):m.end() + 300]
                    side_m = re.search(r'"side"\s*:\s*"(YES|NO)"', chunk, re.IGNORECASE)
                    edge_m = re.search(r'"initial_edge_estimate"\s*:\s*(\d+)', chunk)
                    if side_m:
                        fallback.append({"ticker": ticker, "title": "", "category": "other",
                            "market_yes_cents": 50, "initial_edge_estimate": int(edge_m.group(1)) if edge_m else 10,
                            "side": side_m.group(1).upper(), "evidence": "(parsed from malformed response)",
                            "is_cant_miss": False})
                if fallback:
                    log.info(f"Quick scan: regex fallback recovered {len(fallback)} candidates")
                    return fallback
                if attempt == 0:
                    log.warning("Quick scan: retrying with fresh API call"); continue
            except Exception as ex:
                log.error(f"Quick scan error (attempt {attempt + 1}): {ex}")
                if attempt == 0: continue
        return []

    def run_debate(self, market, orderbook_data=None, data_fetcher=None):
        yc = market.get("display_price", market.get("yes_bid", market.get("last_price", 50))) or 50
        hrs = market.get("_hrs_left", "?")
        title = market.get("title", market["ticker"])
        sub = market.get("subtitle", "")
        full_title = title + (f" -- {sub}" if sub and sub != title else "")
        cat = market.get("_category", "other")

        ob_info = "Not available"
        if orderbook_data:
            ob = orderbook_data.get("orderbook", {})
            ob_info = f"YES bids: {ob.get('yes', ob.get('yes_dollars', []))[:5]}\nNO bids: {ob.get('no', ob.get('no_dollars', []))[:5]}"

        live_data = ""
        if data_fetcher:
            city, forecasts = data_fetcher.get_weather_for_market(title)
            if city and forecasts:
                wx_lines = []
                for p in forecasts[:3]:
                    precip = f", precip {p['precip_pct']}%" if p.get('precip_pct') is not None else ""
                    wx_lines.append(f"  {p['name']}: {p['temp']}°{p['temp_unit']}{precip} -- {p['short']}")
                live_data += f"\nNWS OFFICIAL FORECAST for {city.title()}:\n" + "\n".join(wx_lines)
            elif city:
                live_data += f"\n(City '{city}' identified but forecast not in pre-fetch cache)"
            fred_data = data_fetcher.get_fred_for_category(cat)
            if fred_data:
                live_data += f"\nFRED OFFICIAL DATA: {fred_data}"
            sports_data = data_fetcher.get_sports_for_market(title)
            if sports_data:
                live_data += f"\nESPN LIVE SPORTS DATA:\n{sports_data}"

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
VOLUME: {market.get('volume', '?')}
CLOSES: {market.get('close_time', market.get('expiration_time', '?'))}
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
            "sports": "Use the ESPN live data provided. Check team records, recent form, injuries, and betting lines. Compare spread/O-U to market price.",
            "crypto": "Search for current price of the relevant cryptocurrency. Check recent trend and any major news/regulatory events.",
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
{bull_text[:700]}

BEAR CASE (prob={bear_prob}%, ceiling={bear_ceiling}%):
{bear_text[:700]}

DEBATE METRICS:
- Bull estimate: {bull_prob}% | Bear estimate: {bear_prob}%
- Debate spread: {abs(bull_prob - bear_prob)}% (>30% = extreme disagreement to trade)
- Bull floor: {bull_floor}% | Bear ceiling: {bear_ceiling}%
- Market price: {yc}c (implies {yc}%)

DECISION FRAMEWORK (disciplined edge extraction):
1. EVIDENCE QUALITY: Which side has harder data? Official sources (NWS, FRED, ESPN, BLS) > news articles > opinion. Go with concrete numbers.
2. MARKET INEFFICIENCY: If either side found FRESH data (released in last 2-4 hours) the market hasn't priced in, that's real edge. Trade it.
3. CALIBRATION CHECK: If bull and bear estimates are within 5% of each other, use their midpoint. If they disagree by >20%, the situation is uncertain -- require stronger evidence to trade.
4. FLOOR/CEILING RULE: If bull floor > market price, STRONG YES. If bear ceiling < market price, STRONG NO. These are the clearest signals.
5. FEE AWARENESS: After ~$0.07/contract fees on entry AND exit, you need ~5%+ edge to profit. Don't trade marginal edges.
6. HOLD IS VALID: Saying HOLD protects capital for better opportunities. Only trade when evidence clearly supports a direction.
7. ASYMMETRIC BETS: Cheap contracts (10-25c) with verified data supporting higher probability are the best risk/reward.

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
        synth_text = self._call(synthesis_prompt, 800, use_search=False)
        log.debug(f"SYNTHESIS response: {synth_text[:500]}")
        result = self._parse_synthesis(synth_text, yc, bull_prob, bear_prob)
        result["bull_prob"] = bull_prob
        result["bear_prob"] = bear_prob
        result["debate_spread"] = abs(bull_prob - bear_prob)
        return result

    def _extract_prob(self, text, label, default):
        for line in text.split("\n"):
            if label in line:
                return parse_int(line.split(":", 1)[1], default)
        return default

    def _parse_synthesis(self, text, market_cents, bull_prob, bear_prob):
        r = {"probability": 0, "confidence": 0, "side": "HOLD", "evidence": "", "risk": "",
             "price_cents": 0, "contracts": 0, "edge": 0}
        for line in text.split("\n"):
            l = line.strip()
            if l.startswith("PROBABILITY:"): r["probability"] = max(1, min(99, parse_int(l.split(":", 1)[1])))
            elif l.startswith("CONFIDENCE:"): r["confidence"] = max(0, min(99, parse_int(l.split(":", 1)[1])))
            elif l.startswith("SIDE:"):
                v = l.split(":", 1)[1].upper()
                r["side"] = "YES" if "YES" in v else "NO" if "NO" in v else "HOLD"
            elif l.startswith("EVIDENCE:"): r["evidence"] = l.split(":", 1)[1].strip()[:250]
            elif l.startswith("RISK:"): r["risk"] = l.split(":", 1)[1].strip()[:250]
            elif l.startswith("PRICE_CENTS:"): r["price_cents"] = max(1, min(99, parse_int(l.split(":", 1)[1])))
            elif l.startswith("CONTRACTS:"): r["contracts"] = max(0, min(20, parse_int(l.split(":", 1)[1])))

        if r["side"] == "YES": r["edge"] = r["probability"] - market_cents
        elif r["side"] == "NO": r["edge"] = (100 - r["probability"]) - (100 - market_cents)

        # ── CONVICTION GATES ──
        debate_spread = abs(bull_prob - bear_prob)

        if debate_spread > 45:
            log.info(f"    [GATE] Debate spread {debate_spread}% > 30% -> HOLD (extreme disagreement)")
            r["side"] = "HOLD"; r["confidence"] = max(0, r["confidence"] - 15)
        elif debate_spread > 25:
            penalty = int((debate_spread - 25) * 0.5)
            r["confidence"] = max(0, r["confidence"] - penalty)
            log.info(f"    [GATE] Debate spread {debate_spread}% -> light penalty -{penalty}")

        if r["side"] != "HOLD":
            low_est = min(bull_prob, bear_prob)
            high_est = max(bull_prob, bear_prob)
            if low_est <= r["probability"] <= high_est and debate_spread > 30:
                r["confidence"] = max(0, r["confidence"] - 5)
                log.info(f"    [GATE] Probability {r['probability']}% inside debate range [{low_est}-{high_est}] -> -5 conf")
            elif r["probability"] > high_est and r["side"] == "YES":
                r["confidence"] = min(99, r["confidence"] + 10)
                log.info(f"    [GATE] Probability {r['probability']}% ABOVE debate range [{low_est}-{high_est}] -> +10 conf (strong YES)")
            elif r["probability"] < low_est and r["side"] == "NO":
                r["confidence"] = min(99, r["confidence"] + 10)
                log.info(f"    [GATE] Probability {r['probability']}% BELOW debate range [{low_est}-{high_est}] -> +10 conf (strong NO)")

        price_for_side = r["price_cents"] if r["price_cents"] > 0 else (market_cents if r["side"] == "YES" else 100 - market_cents)
        if price_for_side > 0:
            fee_drag_pct = (CFG["taker_fee_per_contract"] / (price_for_side / 100)) * 100
            if abs(r["edge"]) < fee_drag_pct:
                log.info(f"    [GATE] Edge {r['edge']}% < fee drag {fee_drag_pct:.1f}% -> HOLD")
                r["side"] = "HOLD"

        return r
