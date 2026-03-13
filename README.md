# Kalshi Agent Dashboard

Production-grade monitoring and control dashboard for the Kalshi AI trading agent with cross-platform support (Kalshi + Polymarket), risk telemetry, and compact real-time UI.

## Features

- Live portfolio, risk, and trading telemetry
- Dashboard controls for enabling/disabling agent scans
- Arbitrage and quick-flip visibility
- Compact, mobile-aware UI with persistent preferences
- Dry-run and live trading mode support from backend
- Local dashboard security defaults (localhost host binding)

## Project Structure

- `kalshi-agent.py`: main backend runtime and orchestration
- `modules/`: APIs, dashboard server, risk, scoring, arbitrage, notifier
- `src/`: React + TypeScript frontend
- `tests/`: Python test suite

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
npm install
```

### 2) Configure credentials

- Copy `.env.example` values or update `kalshi-config.json`
- Ensure required keys are available:
  - `kalshi_api_key_id`
  - `kalshi_private_key_path`
  - `anthropic_api_key`

### 3) Run in safe mode first

```bash
python kalshi-agent.py --config kalshi-config.json --dry-run
```

Dashboard URL (default): `http://127.0.0.1:9000`

## Frontend Commands

```bash
npm run dev
npm run lint
npm run build
npm run preview
npm run check
```

## Desktop App (Electron)

```bash
npm run desktop:dev
npm run desktop:pack
npm run desktop:dist:win
npm run desktop:dist:store
```

- Windows launcher: `Start Kalshi Desktop.bat`
- Full local launcher (backend + desktop): `Start Kalshi Full Desktop.bat`
- Full packaging guide: [DESKTOP_PACKAGING.md](DESKTOP_PACKAGING.md)
- Local use does not require a persistent external server; backend runs on your machine and desktop app can auto-start it in dry-run mode.
- For Store builds, copy `.store.env.example` to `.store.env` and fill Partner Center identity values before `desktop:dist:store`.

## Release Safety Notes

- Default mode is `dry_run=true`
- Use `--live` explicitly for live order placement
- Dashboard toggle endpoint is constrained to local-origin requests
- Keep `dashboard_token` configured if exposing dashboard beyond localhost

## Testing

```bash
pytest -q
npm run check
```

## App Store / Distribution

Use the release checklist in [APP_STORE_RELEASE_CHECKLIST.md](APP_STORE_RELEASE_CHECKLIST.md) before submitting binaries or packaged builds.

## Compliance Documents

- [PRIVACY.md](PRIVACY.md)

## Disclaimer

This software is for informational and automation support purposes only and does not constitute financial advice.
