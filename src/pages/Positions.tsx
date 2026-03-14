import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../store/useStore";

function termBar(pct: number, width = 12): string {
  const filled = Math.round((pct / 100) * width);
  return "[" + "|".repeat(filled) + ".".repeat(width - filled) + "]";
}

export default function Positions() {
  const navigate = useNavigate();
  const positions = useStore((s) => s.positions);
  const agentState = useStore((s) => s.agentState);
  const trades = useStore((s) => s.trades);

  const balance = agentState ? agentState.balance + (agentState.poly_balance || 0) : 0;
  const risk = agentState?.risk;

  return (
    <div className="p-2 md:p-3 max-w-5xl mx-auto">
      <h1 className="text-sm font-bold uppercase tracking-wider term-glow mb-2">+--- POSITIONS ---+</h1>

      <div className="card mb-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Metric label="BALANCE" value={`$${balance.toFixed(2)}`} />
          <Metric label="DAY_PNL" value={risk?.day_pnl ?? "$0"} />
          <Metric label="WIN_RATE" value={risk?.win_rate ?? "--"} />
          <Metric label="EXPOSURE" value={risk?.exposure ?? "$0"} />
        </div>
      </div>

      <div className="text-[10px] text-text-tertiary mb-1.5 uppercase tracking-wider">
        -- open positions ({positions.length}) --
      </div>
      <div className="space-y-1">
        <AnimatePresence mode="popLayout">
          {positions.map((pos, i) => {
            const ticker = pos.ticker || pos.market_ticker || `pos-${i}`;
            const side = (pos.side || "yes").toUpperCase();
            const contracts = pos.contracts || 0;

            return (
              <motion.div
                key={ticker}
                layout
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, x: -40 }}
                className="card hover:border-accent-green"
              >
                <div className="flex flex-col lg:flex-row lg:items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xs text-accent-green truncate">
                      {pos.market_title || ticker}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-[10px] font-bold ${side === "YES" ? "text-accent-green" : "text-accent-red"}`}>
                        [{side}]
                      </span>
                      <span className="text-[10px] text-text-tertiary">
                        {ticker.slice(0, 26)}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-4 text-[10px]">
                    <div>
                      <p className="text-text-tertiary uppercase">QTY</p>
                      <p className="font-bold text-accent-green">{contracts}</p>
                    </div>
                    {pos.avg_price != null && (
                      <div>
                        <p className="text-text-tertiary uppercase">AVG</p>
                        <p className="font-bold text-accent-green">{pos.avg_price}c</p>
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
            <TrendingUp size={20} className="mx-auto text-text-tertiary mb-2" />
            <p className="text-text-secondary text-xs">[INFO] no open positions</p>
            <p className="text-[10px] text-text-tertiary mt-1">agent will open positions automatically</p>
            <button
              onClick={() => navigate("/")}
              className="mt-2 px-3 h-7 text-[10px] font-bold border border-accent-green text-accent-green hover:bg-accent-green hover:text-bg-base transition-colors uppercase"
            >
              [ BROWSE MARKETS ]
            </button>
          </div>
        )}
      </div>

      {trades.length > 0 && (
        <div className="mt-3">
          <div className="text-[10px] text-text-tertiary mb-1.5 uppercase tracking-wider">
            -- recent trades ({trades.length}) --
          </div>
          <div className="card p-0 overflow-hidden">
            <TradesTable trades={trades} />
          </div>
        </div>
      )}
    </div>
  );
}

function TradesTable({ trades }: { trades: any[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const rows = trades.slice().reverse().slice(0, 20);

  return (
    <table className="w-full text-[10px]">
      <thead>
        <tr className="border-b border-border-subtle">
          <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">TIME</th>
          <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">MARKET</th>
          <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">SIDE</th>
          <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">QTY</th>
          <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">PRICE</th>
          <th className="text-left px-2 py-1.5 text-text-tertiary uppercase">EDGE</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t, i) => (
          <>
            <tr
              key={i}
              className="border-b border-border-subtle/40 hover:bg-bg-elevated cursor-pointer"
              onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
            >
              <td className="px-2 py-1 text-text-tertiary">
                {typeof t.time === "string" ? t.time.slice(5, 16) : ""}
              </td>
              <td className="px-2 py-1 text-accent-green truncate max-w-[220px]">{t.title || t.ticker}</td>
              <td className={`px-2 py-1 font-bold ${t.side === "yes" ? "text-accent-green" : "text-accent-red"}`}>
                {(t.side || "").toUpperCase()}
              </td>
              <td className="px-2 py-1 text-text-secondary">{t.contracts}</td>
              <td className="px-2 py-1 text-text-secondary">{t.price_cents}c</td>
              <td className="px-2 py-1 text-accent-gold">{t.edge}%</td>
            </tr>
            {expandedIdx === i && (
              <tr key={`${i}-detail`} className="border-b border-border-subtle/40">
                <td colSpan={6} className="px-3 py-2 bg-bg-elevated">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-1.5">
                    <span className="text-text-tertiary">prob: <span className="text-accent-green">{t.probability}%</span></span>
                    <span className="text-text-tertiary">conf: <span className="text-accent-green">{t.confidence}%</span></span>
                    <span className="text-text-tertiary">bull: <span className="text-accent-green">{t.bull_prob}%</span></span>
                    <span className="text-text-tertiary">bear: <span className="text-accent-red">{t.bear_prob}%</span></span>
                  </div>
                  {t.evidence && (
                    <p className="text-[10px] text-text-secondary whitespace-pre-wrap leading-relaxed">{t.evidence}</p>
                  )}
                  {!t.evidence && (
                    <p className="text-[10px] text-text-tertiary italic">no rationale recorded</p>
                  )}
                </td>
              </tr>
            )}
          </>
        ))}
      </tbody>
    </table>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-0.5">{label}</p>
      <p className="text-sm font-bold text-accent-green term-glow">{value}</p>
    </div>
  );
}
