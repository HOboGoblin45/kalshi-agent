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
    <div className="p-4 md:p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl md:text-3xl font-bold mb-4">Live Positions</h1>

      {/* Portfolio summary */}
      <div className="card mb-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">Balance</p>
            <p className="font-mono text-2xl font-bold">${balance.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">Today P&L</p>
            <p className="font-mono text-2xl font-bold">{risk?.day_pnl ?? "$0"}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">Win Rate</p>
            <p className="font-mono text-2xl font-bold">{risk?.win_rate ?? "--"}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">Exposure</p>
            <p className="font-mono text-2xl font-bold">{risk?.exposure ?? "$0"}</p>
          </div>
        </div>
      </div>

      {/* Position list */}
      <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
        Open Positions ({positions.length})
      </h2>
      <div className="space-y-3">
        <AnimatePresence mode="popLayout">
          {positions.map((pos, i) => {
            const ticker = pos.ticker || pos.market_ticker || `pos-${i}`;
            const side = (pos.side || "yes").toUpperCase();
            const contracts = pos.contracts || 0;

            return (
              <motion.div
                key={ticker}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -200 }}
                className="card"
              >
                <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-text-primary truncate">
                      {pos.market_title || ticker}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                          side === "YES"
                            ? "bg-accent-green/15 text-accent-green"
                            : "bg-accent-red/15 text-accent-red"
                        }`}
                      >
                        {side}
                      </span>
                      <span className="text-xs text-text-secondary font-mono">{ticker.slice(0, 25)}</span>
                    </div>
                  </div>

                  <div className="flex gap-6 text-sm">
                    <div>
                      <p className="text-xs text-text-secondary">Contracts</p>
                      <p className="font-mono font-semibold">{contracts}</p>
                    </div>
                    {pos.avg_price != null && (
                      <div>
                        <p className="text-xs text-text-secondary">Avg Price</p>
                        <p className="font-mono font-semibold">{pos.avg_price}¢</p>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {positions.length === 0 && (
          <div className="text-center py-16">
            <TrendingUp size={40} className="mx-auto text-text-tertiary mb-3" />
            <p className="text-text-secondary font-medium">No open positions</p>
            <p className="text-xs text-text-tertiary mt-1">The agent will open positions automatically</p>
            <button
              onClick={() => navigate("/")}
              className="mt-3 px-5 h-10 rounded-xl text-sm font-semibold text-white"
              style={{ background: "var(--accent-color)" }}
            >
              Browse Markets
            </button>
          </div>
        )}
      </div>

      {/* Recent trades */}
      {trades.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
            Recent Trades ({trades.length})
          </h2>
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-4 py-2 text-xs text-text-secondary uppercase">Time</th>
                  <th className="text-left px-4 py-2 text-xs text-text-secondary uppercase">Market</th>
                  <th className="text-left px-4 py-2 text-xs text-text-secondary uppercase">Side</th>
                  <th className="text-left px-4 py-2 text-xs text-text-secondary uppercase">Qty</th>
                  <th className="text-left px-4 py-2 text-xs text-text-secondary uppercase">Price</th>
                  <th className="text-left px-4 py-2 text-xs text-text-secondary uppercase">Edge</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice().reverse().map((t, i) => (
                  <tr key={i} className="border-b border-border-subtle/50 hover:bg-white/5">
                    <td className="px-4 py-2 text-xs text-text-secondary font-mono">
                      {typeof t.time === "string" ? t.time.slice(5, 16) : ""}
                    </td>
                    <td className="px-4 py-2 text-xs truncate max-w-[200px]">
                      {t.title || t.ticker}
                    </td>
                    <td className={`px-4 py-2 text-xs font-bold ${t.side === "yes" ? "text-accent-green" : "text-accent-red"}`}>
                      {(t.side || "").toUpperCase()}
                    </td>
                    <td className="px-4 py-2 text-xs font-mono">{t.contracts}</td>
                    <td className="px-4 py-2 text-xs font-mono">{t.price_cents}¢</td>
                    <td className="px-4 py-2 text-xs font-mono">{t.edge}%</td>
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
