import { useEffect, useState } from "react";

interface CategoryStat {
  total: number;
  wins: number;
  win_rate: number;
  brier: number;
  avg_edge: number;
}

interface CalibrationData {
  total_predictions: number;
  resolved: number;
  pending: number;
  overall_brier: number;
  overall_log_loss: number;
  category_stats: Record<string, CategoryStat>;
}

interface RiskStats {
  drawdown_probs: Record<string, number>;
  peak_balance: number;
  current_balance: number;
  current_drawdown_pct: number;
  n_trades: number;
  growth_rate: number;
  volatility: number;
  kelly_edge_ratio: number;
}

export default function Calibration() {
  const [data, setData] = useState<CalibrationData | null>(null);
  const [riskStats, setRiskStats] = useState<RiskStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/calibration").then((r) => r.json()),
      fetch("/api/risk-stats").then((r) => r.json()),
    ]).then(([cal, risk]) => {
      setData(cal);
      setRiskStats(risk);
      setLoading(false);
    }).catch(() => setLoading(false));

    const interval = setInterval(() => {
      fetch("/api/calibration").then((r) => r.json()).then(setData).catch(() => {});
      fetch("/api/risk-stats").then((r) => r.json()).then(setRiskStats).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="p-2 md:p-3 max-w-4xl mx-auto">
        <h1 className="text-sm font-bold uppercase tracking-wider term-glow mb-2">+--- CALIBRATION ---+</h1>
        <div className="card text-center py-8">
          <p className="text-xs text-text-tertiary animate-pulse">loading calibration data...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-2 md:p-3 max-w-4xl mx-auto">
        <h1 className="text-sm font-bold uppercase tracking-wider term-glow mb-2">+--- CALIBRATION ---+</h1>
        <div className="card text-center py-8">
          <p className="text-xs text-text-secondary">[INFO] no calibration data available</p>
          <p className="text-[10px] text-text-tertiary mt-1">data appears after the agent makes predictions</p>
        </div>
      </div>
    );
  }

  const brierColor = data.overall_brier < 0.15 ? "text-accent-green" :
                     data.overall_brier < 0.25 ? "text-accent-gold" : "text-accent-red";

  const categories = Object.entries(data.category_stats).sort(
    ([, a], [, b]) => b.total - a.total
  );

  return (
    <div className="p-2 md:p-3 max-w-4xl mx-auto">
      <h1 className="text-sm font-bold uppercase tracking-wider term-glow mb-2">+--- CALIBRATION ---+</h1>

      {/* Overview metrics */}
      <div className="card mb-3">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Metric label="PREDICTIONS" value={String(data.total_predictions)} />
          <Metric label="RESOLVED" value={String(data.resolved)} />
          <Metric label="PENDING" value={String(data.pending)} />
          <Metric label="BRIER" value={data.overall_brier.toFixed(4)} color={brierColor} />
          <Metric label="LOG_LOSS" value={data.overall_log_loss.toFixed(4)} />
        </div>
      </div>

      {/* Brier score gauge */}
      <div className="card mb-3">
        <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-2">
          -- BRIER SCORE (lower is better) --
        </div>
        <div className="relative w-full h-4 bg-bg-elevated border border-border-subtle overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${
              data.overall_brier < 0.15 ? "bg-accent-green" :
              data.overall_brier < 0.25 ? "bg-accent-gold" : "bg-accent-red"
            }`}
            style={{ width: `${Math.min(data.overall_brier * 400, 100)}%` }}
          />
          {/* Reference markers */}
          <div className="absolute top-0 left-[25%] h-full w-px bg-text-tertiary/30" title="Random (0.25)" />
          <div className="absolute top-0 left-[15%] h-full w-px bg-accent-green/30" title="Good (0.15)" />
        </div>
        <div className="flex justify-between text-[9px] text-text-tertiary mt-0.5">
          <span>0 (perfect)</span>
          <span className="text-accent-green">0.15 (good)</span>
          <span className="text-accent-gold">0.25 (random)</span>
          <span className="text-accent-red">0.50+ (bad)</span>
        </div>
      </div>

      {/* Drawdown Probability Widget */}
      {riskStats && riskStats.n_trades >= 2 && (
        <div className="card mb-3">
          <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-2">
            -- DRAWDOWN RISK ANALYSIS --
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <Metric label="GROWTH RATE" value={`${riskStats.growth_rate}%`}
              color={riskStats.growth_rate > 0 ? "text-accent-green" : "text-accent-red"} />
            <Metric label="VOLATILITY" value={`${riskStats.volatility}%`} />
            <Metric label="KELLY RATIO" value={riskStats.kelly_edge_ratio.toFixed(3)}
              color={riskStats.kelly_edge_ratio > 0.5 ? "text-accent-green" : "text-accent-gold"} />
            <Metric label="CURR DRAWDOWN" value={`${riskStats.current_drawdown_pct}%`}
              color={riskStats.current_drawdown_pct < 5 ? "text-accent-green" :
                     riskStats.current_drawdown_pct < 15 ? "text-accent-gold" : "text-accent-red"} />
          </div>
          <div className="text-[10px] text-text-tertiary mb-1">
            P(drawdown reaches X%) — lower is safer:
          </div>
          <div className="grid grid-cols-7 gap-1">
            {["5", "10", "15", "20", "25", "30", "50"].map((dd) => {
              const prob = riskStats.drawdown_probs[dd] ?? 0;
              const color = prob < 20 ? "text-accent-green" :
                           prob < 50 ? "text-accent-gold" : "text-accent-red";
              return (
                <div key={dd} className="text-center">
                  <div className="text-[9px] text-text-tertiary">{dd}%</div>
                  <div className={`text-[11px] font-bold ${color}`}>{prob}%</div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[9px] text-text-tertiary mt-1">
            <span>Peak: ${riskStats.peak_balance.toFixed(2)}</span>
            <span>Current: ${riskStats.current_balance.toFixed(2)}</span>
            <span>Trades: {riskStats.n_trades}</span>
          </div>
        </div>
      )}

      {/* Category breakdown */}
      {categories.length > 0 && (
        <>
          <div className="text-[10px] text-text-tertiary mb-1.5 uppercase tracking-wider">
            -- per-category stats ({categories.length} categories) --
          </div>
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">Category</th>
                  <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">Total</th>
                  <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">Wins</th>
                  <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">Win Rate</th>
                  <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">Brier</th>
                  <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">Avg Edge</th>
                </tr>
              </thead>
              <tbody>
                {categories.map(([cat, stats]) => {
                  const wrColor = stats.win_rate > 55 ? "text-accent-green" :
                                  stats.win_rate > 45 ? "text-accent-gold" : "text-accent-red";
                  const brColor = stats.brier < 0.15 ? "text-accent-green" :
                                  stats.brier < 0.25 ? "text-accent-gold" : "text-accent-red";
                  return (
                    <tr key={cat} className="border-b border-border-subtle/40 hover:bg-bg-elevated">
                      <td className="px-2 py-1 text-accent-green font-bold uppercase">{cat}</td>
                      <td className="px-2 py-1 text-text-secondary">{stats.total}</td>
                      <td className="px-2 py-1 text-text-secondary">{stats.wins}</td>
                      <td className={`px-2 py-1 font-bold ${wrColor}`}>{stats.win_rate}%</td>
                      <td className={`px-2 py-1 font-bold ${brColor}`}>{stats.brier.toFixed(3)}</td>
                      <td className="px-2 py-1 text-accent-gold">{stats.avg_edge}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {data.total_predictions === 0 && (
        <div className="card text-center py-8 mt-3">
          <p className="text-xs text-text-secondary">[INFO] no predictions recorded yet</p>
          <p className="text-[10px] text-text-tertiary mt-1">calibration data builds up as the agent trades</p>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-sm font-bold term-glow ${color || "text-accent-green"}`}>{value}</p>
    </div>
  );
}
