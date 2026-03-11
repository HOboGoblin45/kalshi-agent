---
name: kalshi-trading
description: Analyze Kalshi prediction markets, find mispriced contracts, and execute trades using a Bull vs Bear debate protocol with live NWS weather and FRED economic data. Use this skill whenever the user mentions Kalshi, prediction markets, event contracts, trading markets, market analysis, finding edge, placing bets, weather markets, Fed rate markets, or wants to scan for trading opportunities. Also use when the user asks to check their Kalshi balance, positions, or trade history.
---

# Kalshi Prediction Market Trading Skill

Analyze Kalshi prediction markets using a structured Bull vs Bear adversarial debate protocol, live government data feeds (NWS weather, FRED economics), and fee-aware Kelly Criterion position sizing.

## Prerequisites

The user needs three things configured before this skill can trade:

1. **Kalshi API credentials** — API key ID + RSA private key file (get from kalshi.com/settings/api)
2. **Anthropic API key** — for the Bull/Bear debate AI calls
3. **FRED API key** (optional but recommended) — free from fred.stlouisfed.org

Install Python dependencies:
```bash
pip install cryptography anthropic requests
```

## Core Workflow

When the user asks to scan markets, find opportunities, or place trades, follow this sequence:

### Step 1: Connect and check status
Run `scripts/kalshi_api.py` with the user's credentials to verify the connection and check balance.

```bash
python scripts/kalshi_api.py --action balance --key-id USER_KEY_ID --key-path USER_KEY_PATH
```

### Step 2: Pre-fetch live data
Fetch official government data BEFORE any AI analysis. This gives you verified ground truth.

```bash
python scripts/data_fetcher.py --fred-key USER_FRED_KEY
```

This returns NWS weather forecasts for major US cities and latest FRED economic indicators (Fed Funds Rate, CPI, unemployment, etc.). Treat this data as authoritative.

### Step 3: Load and filter markets
```bash
python scripts/market_scanner.py --action filter --key-id USER_KEY_ID --key-path USER_KEY_PATH
```

This loads all open Kalshi markets, filters to target categories (weather, Fed/rates, inflation, employment, energy, policy), scores them by trading potential, and returns the top 20 candidates.

### Step 4: Check for arbitrage (no AI needed)
```bash
python scripts/market_scanner.py --action arbitrage --key-id USER_KEY_ID --key-path USER_KEY_PATH
```

Scans orderbooks for markets where buying YES + NO costs less than $1.00 (after fees). This is mathematically guaranteed profit — no probability judgment required. These are rare but valuable.

### Step 5: Run the Bull vs Bear Debate

This is the core decision engine. For each promising market, run a structured 3-step adversarial debate. The reason for this approach: a single AI call tends toward overconfidence. Forcing the AI to argue both sides and then synthesize produces better-calibrated probability estimates.

**Step 5a — BULL CASE:** Make the strongest possible case for YES. Search for supporting evidence. Cite specific data points (NWS forecasts, FRED numbers, official sources). Return a probability estimate and a probability floor.

**Step 5b — BEAR CASE:** Receive the bull's arguments and directly counter each one. Search for contradicting evidence. Return a probability estimate and a probability ceiling.

**Step 5c — SYNTHESIS:** Weigh both sides. Apply these conviction gates:
- If bull-bear spread > 30%: HOLD (too uncertain)
- If spread 15-30%: reduce confidence proportionally
- Edge must exceed fee drag or trade is unprofitable
- Start from the market price — the market is right by default

See `references/debate-protocol.md` for the full prompt templates and parsing rules.

### Step 6: Size the position
```bash
python scripts/kelly.py --probability 72 --price-cents 60 --bankroll 40 --max-bet 5 --fee 0.07
```

Uses fee-aware fractional Kelly Criterion. If the expected value after fees is negative, returns 0 contracts — no trade.

### Step 7: Execute or recommend

If the user wants live trading, place the order:
```bash
python scripts/kalshi_api.py --action order --key-id KEY --key-path PATH --ticker TICKER --side yes --count 3 --price 60
```

If dry-run or the user just wants analysis, present the recommendation with full debate summary.

## Category-Specific Research

When analyzing markets, use category-appropriate research. Read `references/market-categories.md` for the full checklist. Quick summary:

- **Weather**: Search NWS point forecast for the exact city and date. Compare forecast temperature to what the market price implies.
- **Fed/Rates**: Search CME FedWatch tool probabilities. Check latest Fed speaker comments.
- **Inflation/CPI**: Search latest BLS CPI release. Check Cleveland Fed inflation nowcast.
- **Employment**: Search latest nonfarm payrolls or jobless claims.
- **Policy**: Search for latest committee votes, SEC rulings, or legislation status.
- **Energy**: Search WTI crude price, OPEC decisions, AAA gas prices.

## Output Format

When presenting analysis to the user, use this structure:

```
MARKET: [title]
CATEGORY: [weather/fed_rates/inflation/etc]
HOURS LEFT: [time to close]

BULL CASE (prob: XX%):
  [key argument and evidence]

BEAR CASE (prob: XX%):
  [key counter-argument and evidence]

VERDICT:
  Side: [YES/NO/HOLD]
  Probability: XX% (market: XXc)
  Edge: XX%
  Confidence: XX%
  Debate spread: XX% (bull-bear disagreement)

POSITION:
  [X contracts @ XXc = $X.XX + $X.XX fees]
  If correct: $X.XX profit (XX% ROI)
```

## Key Principles

- **The market is right by default.** You need strong, specific evidence to justify deviating from the market price. "I think" is not evidence. "NWS forecasts 62°F" is evidence.
- **Fees eat small edges.** At $0.07/contract, a 5% edge on a 50c contract is break-even. Only trade when edge clearly exceeds fee drag.
- **Disagreement = uncertainty.** If the bull and bear can't get within 30% of each other, the situation is too ambiguous to bet on.
- **Prefer short-term markets.** Markets closing within 48 hours have the best informational edges because data is freshest and market reaction time is limited.
- **Government data is ground truth.** NWS forecasts and FRED economic data are authoritative. Use web search only for additional context.

## Examples

**Example 1: Weather market scan**
User: "Check Kalshi weather markets for today"
→ Run data_fetcher.py to get NWS forecasts
→ Filter markets to weather category
→ Find: "NYC high temp above 58°F" priced at 50c, NWS says 63°F
→ Run debate: Bull cites NWS 63°F, Bear argues forecast uncertainty
→ Verdict: YES, 82% probability, 32% edge, high confidence
→ Kelly: 4 contracts @ 52c

**Example 2: Fed rate market**
User: "Any edge on Fed markets?"
→ Fetch FRED fed funds rate + treasury yields
→ Filter to fed_rates category
→ Find: "Fed holds rates at March meeting" priced at 72c
→ CME FedWatch shows 91% probability of hold
→ Run debate: Bull cites FedWatch 91%, Bear argues surprise cut risk
→ Verdict: YES, 88% probability, 16% edge
→ Kelly: 3 contracts @ 74c

**Example 3: No edge found**
User: "Scan all markets"
→ Quick scan finds 2 candidates
→ Debate on candidate 1: bull-bear spread 35% → forced HOLD
→ Debate on candidate 2: edge 4% < fee drag 7% → HOLD
→ Report: "No actionable opportunities this scan. Market prices are well-calibrated right now."
