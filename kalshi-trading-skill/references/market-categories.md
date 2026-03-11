# Market Categories & Research Checklists

## Category Detection

Markets are categorized by keyword matching against title, subtitle, ticker, and category fields.

| Category | Keywords |
|---|---|
| weather | temperature, hurricane, tornado, rainfall, snowfall, weather, climate, heat, cold, storm, wind, flood |
| fed_rates | fed, fomc, interest rate, fed funds, powell, rate cut, rate hike, monetary policy |
| inflation | inflation, cpi, pce, consumer price, core inflation |
| employment | unemployment, jobs, nonfarm, payroll, jobless claims, employment |
| gdp_growth | gdp, recession, economic growth, gross domestic |
| markets | s&p, nasdaq, dow, stock market, treasury, yield, bond |
| energy | gas price, oil price, oil production, opec, wti, brent, gasoline |
| policy | sec, regulation, congress, legislation, bill, executive order, tariff, trade war, crypto regulation, bitcoin etf, stablecoin, debt ceiling, government shutdown, sanctions |

## Research Checklists

### Weather Markets

These have the clearest verifiable edge because NWS publishes exact forecasts.

1. Identify the city from the market title
2. Run: `python scripts/data_fetcher.py --city "city name"`
3. Get the NWS forecast temperature, precipitation probability, wind speed
4. Compare to what the market price implies
5. Edge formula: `NWS says 62°F, market asks "above 58°F?" at 50c → edge = ~30%`

**Best data sources:** NWS point forecasts (api.weather.gov), Weather Underground, AccuWeather

### Fed/Rates Markets

Edge comes from Fed speaker signals, FOMC minutes, and FedWatch probabilities.

1. Run: `python scripts/data_fetcher.py --fred-key KEY` (gets fed_funds, treasury yields)
2. Search "CME FedWatch tool" for current rate probabilities
3. Search "Fed speaker [name] comments today" for latest signals
4. Compare FedWatch probability to Kalshi market price
5. Edge formula: `FedWatch shows 90% hold, Kalshi at 72c → edge = 18%`

**Best data sources:** CME FedWatch, FRED (DFF series), Federal Reserve speeches, FOMC minutes

### Inflation/CPI Markets

Edge appears when data releases but market hasn't adjusted.

1. Run data_fetcher for CPI and core CPI
2. Search "latest CPI release BLS [month year]"
3. Search "Cleveland Fed inflation nowcast" for real-time estimates
4. If data has dropped: compare actual to market-implied level
5. If pending: compare consensus forecast to market price

**Best data sources:** BLS CPI release, Cleveland Fed Inflation Nowcast, FRED (CPIAUCSL, CPILFESL)

### Employment Markets

Similar to CPI — edge from fresh data releases.

1. Run data_fetcher for unemployment, nonfarm, jobless claims
2. Search "latest jobs report BLS nonfarm payrolls"
3. Search "weekly initial jobless claims" (released every Thursday)
4. Compare actual numbers to market-implied range

**Best data sources:** BLS Employment Situation, DOL Weekly Claims, FRED (UNRATE, PAYEMS, ICSA)

### Energy Markets

Price markets move fast but prediction markets lag.

1. Run data_fetcher for gas_price
2. Search "WTI crude oil price today"
3. Search "OPEC latest production decision"
4. Search "AAA national gas price average"
5. Compare current price/trajectory to market prediction

**Best data sources:** EIA, AAA Gas Prices, OPEC announcements, FRED (GASREGW)

### Policy/Regulation Markets

Slowest-moving but highest edge potential. AI research on legislative signals.

1. Search "[specific bill or regulation name] latest news"
2. Search "SEC [topic] ruling 2026" or "Congress vote [bill]"
3. Search committee hearing transcripts for signals
4. Check GovTrack.us for bill status
5. Policy markets often have the longest resolution times — use cant-miss criteria

**Best data sources:** Congress.gov, GovTrack, SEC EDGAR, Federal Register

## Scoring System

Markets are scored 0-20 for trading priority:

| Factor | Points |
|---|---|
| Volume ≥1000 | +4 |
| Volume ≥500 | +3 |
| Volume ≥100 | +2 |
| Price 25-75c (sweet spot) | +3 |
| Price 15-85c | +2 |
| Closing 1-6 hours | +6 |
| Closing 6-12 hours | +5 |
| Closing 12-24 hours | +4 |
| Weather/Fed/Inflation/Employment | +3 |
| Energy/Policy | +2 |
| Volume <50 (penalty) | -2 |
| Near resolution + extreme price | +2 |
