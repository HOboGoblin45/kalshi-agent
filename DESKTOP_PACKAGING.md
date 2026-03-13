# Desktop Packaging Guide

Last updated: 2026-03-13

## Goal

Build signed desktop installers for distribution (Windows-first path).

## Prerequisites

- Node.js 20+
- Python 3.11+
- `npm install` completed
- Valid app icons in `build/` (recommended):
  - `icon.ico` (Windows)
  - `icon.icns` (macOS)

## Commands

### Local desktop shell (development)

```bash
npm run desktop:dev
```

This opens an Electron shell that points to:

- `http://127.0.0.1:9000` by default
- override with `KALSHI_DASHBOARD_URL`
- if dashboard is not running, Electron auto-starts local backend in `--dry-run` mode

### Build production web assets

```bash
npm run build
```

### Build unpacked desktop app (quick smoke test)

```bash
npm run desktop:pack
```

Output: `release/win-unpacked` (on Windows)

### Build distributables

```bash
npm run desktop:dist:win
```

Outputs include NSIS installer and ZIP in `release/`.

### Build Microsoft Store package (AppX)

1. Copy `.store.env.example` to `.store.env`
2. Fill it with exact Partner Center identity values

```bash
npm run desktop:dist:store
```

Output includes `.appx` in `release/`.

## Windows Store Path (MSIX/AppX)

Electron Builder is configured for AppX in `package.json` under `build.appx`.

Before submission, replace placeholder values with your Partner Center values:

- `build.appx.publisher`
- `build.appx.publisherDisplayName`
- `build.appx.identityName`

The project now supports secure local metadata injection via `.store.env` and `scripts/generate-appx-config.mjs`.

Typical flow:

1. Reserve app name in Microsoft Partner Center.
2. Copy exact identity/publisher values into `package.json`.
3. Build AppX (`npm run desktop:dist:store`).
4. Validate install locally.
5. Upload to Partner Center submission.

Note: signing and identity mismatch are the most common blockers. The values must exactly match Partner Center.

## Do You Need a Persistent Server?

For your own local use: **no external persistent server is required**.

- The desktop app points to a local dashboard at `http://127.0.0.1:9000`.
- Electron now tries to auto-start backend locally with:

```bash
python kalshi-agent.py --config kalshi-config.json --dry-run
```

For public distribution: end users still need that backend process running locally (or you package an embedded backend runtime in a future step).

## Security Baseline

- Dashboard host should remain `127.0.0.1` for consumer builds.
- Use backend `dry_run` by default in release demos.
- Never bundle real API credentials.

## Release QA

Before shipping, run:

```bash
npm run check
pytest -q
```

And execute the app store checklist in `APP_STORE_RELEASE_CHECKLIST.md`.
