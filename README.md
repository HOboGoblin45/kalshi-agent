# Kalshi Agent v7 -- Hardened Trading Workstation

Production-grade AI trading agent for Kalshi and Polymarket prediction markets with precision-safe math, event-driven market state, calibration tracking, and real-time dashboard.

## Safety First

- **dry_run is ALWAYS true by default** -- config files cannot override this
- Only the `--live` CLI flag enables live order placement
- Electron app starts in dry-run mode; never auto-escalates to live
- All credentials stay out of version control (enforced by `.gitignore` + `SECRET_FIELDS`)

## Architecture

```
kalshi-agent.py         Main orchestrator: scan loop, debate engine, trade execution
modules/
  config.py             Safe config loading (DEFAULTS -> file -> env -> --live flag)
  precision.py          Decimal-based fixed-point math, VenueFees, fee models
  market_state.py       In-memory BookState store with staleness detection
  scoring.py            Feature extraction, Kelly criterion, execution eligibility
  calibration.py        Brier score, log loss, reliability bins, per-category stats
  execution.py          Execution policy engine (taker vs maker vs no_trade)
  arbitrage.py          Cross-platform arb with quality classification
  risk.py               Position sizing, exit management, circuit breakers
  debate.py             Bull vs Bear AI debate using Claude Sonnet
  apis.py               Kalshi REST + Polymarket CLOB API clients
  dashboard.py          HTTP dashboard server (API + React SPA)
  data_fetcher.py       Live data briefs (weather, sports, economic)
  notifier.py           Email trade notifications
src/                    React + TypeScript + Tailwind frontend
electron/               Desktop app packaging
tests/                  262 unit tests covering all production modules
```

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
npm install
```

### 2) Configure credentials

```bash
cp kalshi-config.example.json kalshi-config.json
# Edit kalshi-config.json with your API keys
# NEVER commit kalshi-config.json to git
```

Required credentials:
- `kalshi_api_key_id` + `kalshi_private_key_path` (Kalshi API)
- `anthropic_api_key` (Claude API for debate engine)
- Polymarket keys (optional, for cross-platform trading)

### 3) Run in dry-run mode (default)

```bash
python kalshi-agent.py --config kalshi-config.json
```

Dashboard opens at `http://127.0.0.1:9000`

### 4) Enable live trading (requires explicit flag)

```bash
python kalshi-agent.py --config kalshi-config.json --live
```

## Key Design Decisions

### Precision-Safe Money Math
All price, fee, and P&L calculations use Python `Decimal` -- never floats for money. The `VenueFees` class models per-venue fee schedules (Kalshi $0.07/contract taker, Polymarket $0.02).

### Kelly Criterion with Fee Awareness
Position sizing uses full Kelly with fee-aware EV:
- Win payoff subtracts 2x fee (entry + exit)
- Lose cost includes 1x fee (entry only)
- Expensive contracts (>85c) are gated: even at 95% probability, $0.14 round-trip fees on $0.10 payoff = negative EV

### Execution Policy Engine
Separates the "what to trade" decision from "how to trade":
- **Taker**: aggressive fill when edge is time-sensitive or spread is tight
- **Maker**: passive limit order when spread is wide and urgency is low
- **No-trade**: when fee drag exceeds edge or book quality is too poor

### Arbitrage Quality Classification
Cross-platform arbitrage candidates are classified before execution:
- **Locked** (>0.95 similarity): execute in live mode
- **Soft/Speculative**: display only, require manual review
- **Unsafe**: blocked from execution

### Calibration Tracking
Every prediction is recorded. The system tracks:
- Brier score (lower = better calibrated; 0.25 = random)
- Log loss
- Per-category win rates and accuracy
- `should_trade_category()` blocks categories where calibration is poor

## Frontend Commands

```bash
npm run dev       # Development server with HMR
npm run build     # Production build to dist/
npm run check     # TypeScript type checking
npm run lint      # ESLint
```

## Desktop App (Electron)

```bash
npm run desktop:dev           # Dev mode
npm run desktop:pack          # Package without installer
npm run desktop:dist:win      # Windows installer
```

See [DESKTOP_PACKAGING.md](DESKTOP_PACKAGING.md) for full guide.

## Testing

```bash
pytest -q                     # 262 Python tests
npm run check                 # TypeScript checks
```

Tests cover: precision math, config safety (dry_run enforcement), scoring/Kelly, market state/staleness, execution engine, calibration metrics.

## Configuration Reference

See `kalshi-config.example.json` for all available options. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `dry_run` | `true` | Always true unless `--live` flag passed |
| `environment` | `demo` | `demo` or `prod` |
| `max_bet_per_trade` | `1.50` | Max cost per trade in dollars |
| `max_daily_trades` | `12` | Circuit breaker: max trades per day |
| `min_confidence` | `65` | Minimum AI confidence to trade |
| `min_edge_pct` | `5` | Minimum edge percentage |
| `kelly_fraction` | `0.20` | Kelly fraction (fractional Kelly for safety) |
| `quickflip_enabled` | `false` | Quick-flip strategy (disabled by default) |
| `cross_arb_enabled` | `false` | Cross-platform arbitrage (disabled by default) |

## Compliance

- [PRIVACY.md](PRIVACY.md)
- [APP_STORE_RELEASE_CHECKLIST.md](APP_STORE_RELEASE_CHECKLIST.md)

## Disclaimer

This software is for informational and automation support purposes only and does not constitute financial advice. Use at your own risk. Always start with dry-run mode and small position sizes.
