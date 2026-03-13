import { useNavigate } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../store/useStore";

export default function Positions() {
  const navigate = useNavigate();
  const positions = useStore((s) => s.positions);
  const agentState = useStore((s) => s.agentState);
  const trades = useStore((s) => s.trades);

  const balance = agentState ? agentState.balance + (agentState.poly_balance || 0) : 0;
  const risk = agentState?.risk;

  return (
    <div className="p-2 md:p-2.5 max-w-5xl mx-auto">
      <h1 className="text-base md:text-lg font-bold mb-2">Live Positions</h1>

      <div className="card mb-2.5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Metric label="Balance" value={`$${balance.toFixed(2)}`} />
          <Metric label="Today P&L" value={risk?.day_pnl ?? "$0"} />
          <Metric label="Win Rate" value={risk?.win_rate ?? "--"} />
          <Metric label="Exposure" value={risk?.exposure ?? "$0"} />
        </div>
      </div>

      <h2 className="text-[10px] font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
        Open Positions ({positions.length})
      </h2>
      <div className="space-y-1.5">
        <AnimatePresence mode="popLayout">
          {positions.map((pos, i) => {
            const ticker = pos.ticker || pos.market_ticker || `pos-${i}`;
            const side = (pos.side || "yes").toUpperCase();
            const contracts = pos.contracts || 0;

            return (
              <motion.div
                key={ticker}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -80 }}
                className="card"
              >
                <div className="flex flex-col lg:flex-row lg:items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xs font-semibold text-text-primary truncate">
                      {pos.market_title || ticker}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                          side === "YES"
                            ? "bg-accent-green/15 text-accent-green"
                            : "bg-accent-red/15 text-accent-red"
                        }`}
                      >
                        {side}
                      </span>
                      <span className="text-[10px] text-text-secondary font-mono">
                        {ticker.slice(0, 26)}
                      </span>
                    </div>
                  </div>

                  <div className="flex gap-3 text-[11px]">
                    <div>
                      <p className="text-[10px] text-text-secondary uppercase">Contracts</p>
                      <p className="font-mono font-semibold">{contracts}</p>
                    </div>
                    {pos.avg_price != null && (
                      <div>
                        <p className="text-[10px] text-text-secondary uppercase">Avg Price</p>
                        <p className="font-mono font-semibold">{pos.avg_price}c</p>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {positions.length === 0 && (
          <div className="text-center py-8 card">
            <TrendingUp size={24} className="mx-auto text-text-tertiary mb-2" />
            <p className="text-text-secondary font-medium text-xs">No open positions</p>
            <p className="text-xs text-text-tertiary mt-1">The agent will open positions automatically.</p>
            <button
              onClick={() => navigate("/")}
              className="mt-2.5 px-3 h-8 rounded-md text-xs font-semibold text-white"
              style={{ background: "var(--accent-color)" }}
            >
              Browse Markets
            </button>
          </div>
        )}
      </div>

      {trades.length > 0 && (
        <div className="mt-3">
          <h2 className="text-[10px] font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
            Recent Trades ({trades.length})
          </h2>
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-3 py-2 text-[10px] text-text-secondary uppercase">Time</th>
                  <th className="text-left px-3 py-2 text-[10px] text-text-secondary uppercase">Market</th>
                  <th className="text-left px-3 py-2 text-[10px] text-text-secondary uppercase">Side</th>
                  <th className="text-left px-3 py-2 text-[10px] text-text-secondary uppercase">Qty</th>
                  <th className="text-left px-3 py-2 text-[10px] text-text-secondary uppercase">Price</th>
                  <th className="text-left px-3 py-2 text-[10px] text-text-secondary uppercase">Edge</th>
                </tr>
              </thead>
              <tbody>
                {trades
                  .slice()
                  .reverse()
                  .slice(0, 20)
                  .map((t, i) => (
                    <tr key={i} className="border-b border-border-subtle/40 hover:bg-white/5">
                      <td className="px-3 py-1.5 text-[11px] text-text-secondary font-mono">
                        {typeof t.time === "string" ? t.time.slice(5, 16) : ""}
                      </td>
                      <td className="px-3 py-1.5 text-[11px] truncate max-w-[220px]">{t.title || t.ticker}</td>
                      <td
                        className={`px-3 py-1.5 text-[11px] font-bold ${
                          t.side === "yes" ? "text-accent-green" : "text-accent-red"
                        }`}
                      >
                        {(t.side || "").toUpperCase()}
                      </td>
                      <td className="px-3 py-1.5 text-[11px] font-mono">{t.contracts}</td>
                      <td className="px-3 py-1.5 text-[11px] font-mono">{t.price_cents}c</td>
                      <td className="px-3 py-1.5 text-[11px] font-mono">{t.edge}%</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-text-secondary uppercase tracking-wider mb-0.5">{label}</p>
      <p className="font-mono text-lg font-bold">{value}</p>
    </div>
  );
}
