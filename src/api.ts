const BASE = "/api";

export interface AgentState {
  enabled: boolean;
  status: string;
  balance: number;
  poly_balance: number;
  poly_enabled: boolean;
  environment: string;
  dry_run?: boolean;
  risk: {
    total: number;
    wins: number;
    losses: number;
    win_rate: string;
    wagered: string;
    day_trades: number;
    day_pnl: string;
    exposure: string;
    paused: boolean;
  };
  trades: Trade[];
  log: { time: string; msg: string; level: string }[];
  last_scan: string;
  next_scan: string;
  max_daily: number;
  scan_count: number;
  scan_interval: number;
  ai_interval: number;
  arb_opps: number;
  cross_arb_opps: number;
  quickflip_active: number;
  scan_progress: {
    phase: string;
    step: string;
    pct: number;
    total_phases: number;
    current_phase: number;
  };
  scan_summary: string;
  feed_health?: Record<string, { status: string; age_seconds: number; errors: number }>;
  stale_markets?: number;
}

export interface Trade {
  time: string;
  ticker: string;
  title: string;
  side: string;
  contracts: number;
  price_cents: number;
  cost: number;
  confidence: number;
  probability: number;
  edge: number;
  evidence: string;
  bull_prob: number;
  bear_prob: number;
  status: string;
  platform: string;
}

export interface KalshiMarket {
  ticker: string;
  title: string;
  subtitle: string;
  category: string;
  yes_bid: number | null;
  no_bid: number | null;
  last_price: number | null;
  volume: number | null;
  volume_24h: number | null;
  close_time: string | null;
  status: string;
  event_ticker: string;
  yes_ask: number | null;
  no_ask: number | null;
  open_time: string | null;
  result: string | null;
  platform: string;
  display_price?: number | null;
  _score?: number;
}

export interface KalshiPosition {
  ticker: string;
  market_ticker: string;
  side: string;
  contracts: number;
  avg_price: number;
  market_title?: string;
  [key: string]: unknown;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  getState: () => fetchJson<AgentState>("/state"),
  getMarkets: () => fetchJson<KalshiMarket[]>("/markets"),
  getPositions: () => fetchJson<KalshiPosition[]>("/positions"),
  getTrades: () => fetchJson<Trade[]>("/trades"),
  toggle: () => fetch(`${BASE}/toggle`, { method: "POST" }).then((r) => r.json()),
};
