# UI Refinement and Thorough Testing Plan

Scope approved by user: Proceed without mock mode. Focus on refinement, compactness, and eliminating overlap across the UI. Perform thorough testing of the program as a whole.

## Tasks

1) Compact UI updates
- Markets page (src/pages/Markets.tsx)
  - Reduce container paddings: p-3 md:p-4 and max-w-6xl
  - Tighter header spacing and compact market count
  - Search bar height to h-9 and smaller margins
  - Cards: remove hover scale to eliminate overlap; keep hover border highlight
  - ProbabilityGauge size to 36
  - Progress bar height to h-1.5; grid gap to gap-3
- Layout shell (src/components/Layout.tsx)
  - Sidebar width to 200px; compact nav paddings
  - Compact bottom account row
  - TopBar height to h-12 with smaller paddings and font sizes
- Global styles (src/index.css)
  - Make .card denser: padding 12px, radius 10px, softer shadow
- Probability Gauge (src/components/ProbabilityGauge.tsx)
  - Default size to 36

2) Build pipeline
- Run: npm run build to regenerate dist/ for the Python dashboard server at :9000

3) Thorough testing checklist

Backend/API (Python dashboard and agent)
- Verify endpoints:
  - GET /api/state
  - GET /api/markets
  - GET /api/positions
  - GET /api/trades
  - POST /api/toggle (confirm enabled flag flips and UI updates)
- CORS headers present, JSON schema matches src/api.ts types
- When dist/ exists:
  - Static SPA served correctly and unknown routes fall back to index.html
- When dist/ missing (dev scenario):
  - Verify the 404 + API-only warning logs are printed as expected

Frontend (React app)
- Load via http://localhost:9000 (served from dist/)
- Validate at 900x600 (tool window) and 1440x900:
  - No card overlap; compact spacing; reduced whitespace
  - Markets grid density: 3 columns at lg, 2 columns at sm, 1 column mobile
  - Search interactions; empty states (no markets and filtered empty)
  - TopBar status dot and balance rendering; sticky behavior; no vertical overflow
  - Sidebar nav highlighting; compact paddings; no truncation
  - ProbabilityGauge renders with smaller size without clipping
  - Scroll performance; no jank on polling updates
- Exercise all pages:
  - Markets (/)
  - MarketDetail (/market/:id) — navigation works from card click even with compact layout
  - Positions (/positions)
  - Alerts (/alerts)
  - BotIntelligence (/bot)
  - Profile (/profile)
- Error handling:
  - Simulate API error (temporarily stop agent or block endpoint) and confirm ErrorScreen
  - Verify Messages/Toasts and any Modal sizing with compact theme (visual QA)

4) Post-testing refinements
- Tweak spacing or font sizes if readability degrades at small window sizes
- Record any regressions or edge-case visual issues and iterate

## Execution Order

- [x] Update CSS (.card compact)
- [x] Update ProbabilityGauge default size
- [x] Update Layout compact design
- [x] Update Markets page density + remove hover scale
- [x] Build frontend: npm run build
- [x] Visual QA at :9000 (browser tool), capture screenshots
- [x] Iterate on feedback if any spacing/overlap remains
