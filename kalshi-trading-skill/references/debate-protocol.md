# Bull vs Bear Debate Protocol

The adversarial debate protocol is the core decision engine. It produces better-calibrated probabilities than single-shot analysis because it forces consideration of both sides before committing.

## Why Debate Works Better

Single-shot AI analysis tends toward overconfidence. When you ask "should I bet YES on this market?", the AI finds supporting evidence and stops. The debate protocol fixes this by:

1. Forcing a dedicated BEAR researcher to attack the BULL's best arguments
2. Requiring the SYNTHESIS judge to weigh both sides before deciding
3. Applying automatic conviction gates based on disagreement

## Three Steps

### Step 1: Bull Researcher

**Role:** Make the strongest possible case for YES.

**Required research by category:**
- Weather: "Search NWS point forecast [city] [date]"
- Fed/Rates: "Search CME FedWatch tool current probabilities"
- Inflation: "Search latest CPI release BLS"
- Employment: "Search latest nonfarm payrolls BLS"
- Policy: "Search [specific bill/regulation] latest news"
- Energy: "Search WTI crude price today"

**Output format:**
```
THESIS: [one sentence bullish thesis]
KEY_DATA: [most important fact found, with source]
ARGUMENTS: [3 evidence-based arguments for YES]
PROBABILITY_FLOOR: [minimum reasonable YES probability, integer]
PROBABILITY: [YES probability estimate, integer 1-99]
CATALYSTS: [what could push probability higher in next 24h]
```

### Step 2: Bear Researcher

**Role:** Directly counter the Bull's arguments. Destroy the weakest points.

**Required approach:**
- Receive the Bull's full case
- Search for COUNTER-EVIDENCE that contradicts each key data point
- Check: Is the Bull's source current? Reliable? Cherry-picked?
- For weather: search alternative models or uncertainty ranges
- For econ: search for revisions, seasonal adjustments, contradicting indicators

**Output format:**
```
COUNTER_THESIS: [one sentence bearish thesis]
COUNTER_DATA: [specific fact that contradicts the Bull]
COUNTER_ARGUMENTS: [3 arguments for NO, each addressing a Bull point]
PROBABILITY_CEILING: [maximum reasonable YES probability, integer]
PROBABILITY: [YES probability estimate, integer 1-99]
RISK_FACTORS: [what could go wrong for YES holders]
```

### Step 3: Synthesis Judge

**Role:** Weigh both sides and make the final call. YOUR MONEY IS ON THE LINE.

**Decision framework:**
1. EVIDENCE QUALITY: Which side cited more specific, verifiable data?
2. BASE RATE: Start from the market price. The market is RIGHT by default.
3. CONVICTION CHECK: If bull-bear spread > 30%, HOLD.
4. If bull floor > market price, lean YES. If bear ceiling < market price, lean NO.
5. EDGE DURABILITY: How long until this information is common knowledge?
6. FEE HURDLE: After $0.07/contract, is there still profit?
7. WORST CASE: If wrong, is the loss acceptable?

**Output format:**
```
PROBABILITY: [integer 1-99, final evidence-weighted estimate]
CONFIDENCE: [integer 1-99]
SIDE: [YES or NO or HOLD]
EDGE_DURATION_HOURS: [how long edge lasts]
EVIDENCE: [single most decisive fact]
RISK: [strongest counter-argument you couldn't dismiss]
PRICE_CENTS: [bid price, integer 1-99]
CONTRACTS: [integer 1-20]
```

## Conviction Gates (applied automatically after synthesis)

| Condition | Action |
|---|---|
| Bull-Bear spread > 30% | Force HOLD, -25 confidence |
| Spread 15-30% | Reduce confidence by (spread-15) points |
| Probability inside debate range on wide debate | -10 confidence |
| Edge < fee drag percentage | Force HOLD |
| Edge < half the orderbook spread | Skip (bad fills) |

## Parsing Rules

Extract values from the synthesis output by line prefix:
- `PROBABILITY:` → integer, clamp 1-99
- `CONFIDENCE:` → integer, clamp 0-99
- `SIDE:` → YES, NO, or HOLD
- `EVIDENCE:` → string, max 250 chars
- `RISK:` → string, max 250 chars
- `PRICE_CENTS:` → integer, clamp 1-99
- `CONTRACTS:` → integer, clamp 0-20

Recalculate edge from probability vs market price:
- YES side: edge = probability - market_yes_cents
- NO side: edge = (100 - probability) - (100 - market_yes_cents)
