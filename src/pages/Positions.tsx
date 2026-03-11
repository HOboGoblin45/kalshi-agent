import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronUp, ChevronDown, TrendingUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import { useStore, type Position } from "../store/useStore";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";

const sparkData = [
  { v: 124200 },
  { v: 125100 },
  { v: 124800 },
  { v: 126300 },
  { v: 125900 },
  { v: 127200 },
  { v: 127849 },
];

const tabs = ["Open", "Pending", "Settled"] as const;
type Tab = (typeof tabs)[number];

export default function Positions() {
  const navigate = useNavigate();
  const { portfolio, positions, removePosition, addSharesToPosition } = useStore();
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>("Open");
  const [closeModal, setCloseModal] = useState<Position | null>(null);
  const [addModal, setAddModal] = useState<Position | null>(null);
  const [addShares, setAddShares] = useState(10);
  const [hovered, setHovered] = useState<string | null>(null);

  const statusMap: Record<Tab, Position["status"]> = {
    Open: "open",
    Pending: "pending",
    Settled: "settled",
  };

  const filtered = positions.filter((p) => p.status === statusMap[tab]);
  const pnlPos = portfolio.todayPnl >= 0;

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl md:text-3xl font-bold">Live Positions</h1>
        <div className="flex bg-bg-surface rounded-xl p-1 border border-border-subtle">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-all ${
                tab === t ? "text-white shadow" : "text-text-secondary"
              }`}
              style={tab === t ? { background: "var(--accent-color)" } : undefined}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Portfolio summary */}
      <div className="card mb-6">
        <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">Total Portfolio Value</p>
        <p className="font-mono text-3xl font-bold mb-2">
          ${portfolio.totalValue.toLocaleString("en-US", { minimumFractionDigits: 2 })}
        </p>
        <div className="flex items-center gap-2 mb-3">
          {pnlPos ? (
            <ChevronUp size={16} className="text-accent-green" />
          ) : (
            <ChevronDown size={16} className="text-accent-red" />
          )}
          <span className={`font-mono text-sm font-semibold ${pnlPos ? "text-accent-green" : "text-accent-red"}`}>
            {pnlPos ? "+" : ""}${portfolio.todayPnl.toLocaleString()} ({pnlPos ? "+" : ""}
            {portfolio.todayPnlPct}%)
          </span>
        </div>
        <div className="h-20">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkData}>
              <Line
                type="monotone"
                dataKey="v"
                stroke={pnlPos ? "#30D158" : "#FF453A"}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Position list */}
      <div className="space-y-3">
        <AnimatePresence mode="popLayout">
          {filtered.map((pos) => {
            const value = pos.shares * (pos.currentPrice / 100);
            const cost = pos.shares * (pos.avgPrice / 100);
            const pnl = pos.status === "settled" ? (pos.settledPnl ?? 0) : value - cost;
            const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
            const isPos = pnl >= 0;

            return (
              <motion.div
                key={pos.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -200 }}
                className="card relative"
                onMouseEnter={() => setHovered(pos.id)}
                onMouseLeave={() => setHovered(null)}
              >
                <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                  {/* Left */}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-text-primary truncate">{pos.marketQuestion}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                          pos.side === "YES"
                            ? "bg-accent-green/15 text-accent-green"
                            : "bg-accent-red/15 text-accent-red"
                        }`}
                      >
                        {pos.side}
                      </span>
                      <span className="text-xs text-text-secondary">Market closes {pos.closeDate}</span>
                    </div>
                  </div>

                  {/* Middle */}
                  <div className="flex gap-6 text-sm">
                    <div>
                      <p className="text-xs text-text-secondary">Shares × Avg</p>
                      <p className="font-mono font-semibold">
                        {pos.shares} × {pos.avgPrice}¢
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-text-secondary">Current Value</p>
                      <p className="font-mono font-semibold">${value.toFixed(2)}</p>
                    </div>
                  </div>

                  {/* Right */}
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-xs text-text-secondary">
                        {pos.status === "settled" ? "Settled P&L" : "Unrealized P&L"}
                      </p>
                      <p className={`font-mono font-semibold ${isPos ? "text-accent-green" : "text-accent-red"}`}>
                        {isPos ? "+" : ""}${pnl.toFixed(2)}{" "}
                        <span className="text-xs">({isPos ? "+" : ""}{pnlPct.toFixed(1)}%)</span>
                      </p>
                    </div>

                    {/* Mini odds bar */}
                    <div className="w-16 h-2 rounded-full overflow-hidden bg-bg-elevated flex">
                      <div
                        className="h-full bg-accent-green rounded-l-full"
                        style={{ width: `${pos.currentPrice}%` }}
                      />
                      <div
                        className="h-full bg-accent-red rounded-r-full"
                        style={{ width: `${100 - pos.currentPrice}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* Hover actions */}
                {hovered === pos.id && pos.status === "open" && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute right-4 top-1/2 -translate-y-1/2 flex gap-2"
                  >
                    <button
                      onClick={() => setCloseModal(pos)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent-red text-white"
                    >
                      Close Position
                    </button>
                    <button
                      onClick={() => {
                        setAddShares(10);
                        setAddModal(pos);
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white"
                      style={{ background: "var(--accent-color)" }}
                    >
                      Add Shares
                    </button>
                  </motion.div>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>

        {filtered.length === 0 && (
          <div className="text-center py-16">
            <TrendingUp size={40} className="mx-auto text-text-tertiary mb-3" />
            <p className="text-text-secondary font-medium">No {tab.toLowerCase()} positions</p>
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

      {/* Close confirmation modal */}
      <Modal open={closeModal !== null} onClose={() => setCloseModal(null)}>
        {closeModal && (
          <div>
            <h3 className="text-lg font-bold mb-2">Close Position</h3>
            <p className="text-sm text-text-secondary mb-4">
              Close {closeModal.shares} shares of "{closeModal.marketQuestion}"? You'll receive $
              {(closeModal.shares * (closeModal.currentPrice / 100)).toFixed(2)}.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setCloseModal(null)}
                className="flex-1 h-11 rounded-xl text-sm font-semibold bg-bg-elevated text-text-primary border border-border-subtle"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  removePosition(closeModal.id);
                  setCloseModal(null);
                  toast("Position closed successfully", "success");
                }}
                className="flex-1 h-11 rounded-xl text-sm font-semibold bg-accent-red text-white"
              >
                Confirm
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Add shares modal */}
      <Modal open={addModal !== null} onClose={() => setAddModal(null)}>
        {addModal && (
          <div>
            <h3 className="text-lg font-bold mb-2">Add Shares</h3>
            <p className="text-sm text-text-secondary mb-4">
              Add shares to "{addModal.marketQuestion}"
            </p>
            <input
              type="number"
              min={1}
              value={addShares}
              onChange={(e) => setAddShares(Math.max(1, parseInt(e.target.value) || 1))}
              className="w-full h-11 px-4 rounded-xl bg-bg-elevated border border-border-subtle text-text-primary font-mono mb-4 focus:outline-none focus:border-white/20"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setAddModal(null)}
                className="flex-1 h-11 rounded-xl text-sm font-semibold bg-bg-elevated text-text-primary border border-border-subtle"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  addSharesToPosition(addModal.id, addShares);
                  setAddModal(null);
                  toast(`Added ${addShares} shares`, "success");
                }}
                className="flex-1 h-11 rounded-xl text-sm font-semibold text-white"
                style={{ background: "var(--accent-color)" }}
              >
                Buy
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
