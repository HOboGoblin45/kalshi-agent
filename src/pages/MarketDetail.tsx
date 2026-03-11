import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Bot } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { motion } from "framer-motion";
import { markets } from "../data/markets";
import { useStore } from "../store/useStore";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";

const timeframes = ["1H", "1D", "1W", "1M"] as const;

function formatVol(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v}`;
}

export default function MarketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { positions, addPosition } = useStore();
  const [tf, setTf] = useState<(typeof timeframes)[number]>("1D");
  const [amount, setAmount] = useState(50);
  const [limitPrice, setLimitPrice] = useState(0);
  const [confirmModal, setConfirmModal] = useState<"YES" | "NO" | null>(null);

  const market = markets.find((m) => m.id === id);
  if (!market) {
    return (
      <div className="p-6 text-center">
        <p className="text-text-secondary">Market not found</p>
        <button onClick={() => navigate("/")} className="mt-3 text-sm" style={{ color: "var(--accent-color)" }}>
          Back to Markets
        </button>
      </div>
    );
  }

  const effectivePrice = limitPrice > 0 ? limitPrice : market.yesPrice;
  const shares = Math.floor((amount * 100) / effectivePrice);
  const totalCost = (shares * effectivePrice) / 100;
  const fillChance = limitPrice > 0 ? Math.max(20, Math.min(99, 100 - Math.abs(limitPrice - market.yesPrice) * 3)) : 95;

  const chartData = market.chartData[tf];
  const userPos = positions.find((p) => p.marketId === id && p.status === "open");

  const handleConfirm = () => {
    if (!confirmModal) return;
    const newPos = {
      id: `pos-${Date.now()}`,
      marketId: market.id,
      marketQuestion: market.question,
      side: confirmModal as "YES" | "NO",
      shares,
      avgPrice: effectivePrice,
      currentPrice: market.yesPrice,
      closeDate: market.closeDate,
      status: "open" as const,
    };
    addPosition(newPos);
    setConfirmModal(null);
    toast(`Bought ${shares} ${confirmModal} contracts`, "success");
    navigate("/positions");
  };

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto">
      {/* Header */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary mb-4"
      >
        <ArrowLeft size={16} />
        Back
      </button>

      <h1 className="text-xl md:text-2xl font-bold mb-1">{market.question}</h1>
      <p className="text-sm text-text-secondary mb-4">
        Resolves {market.closeDate} · Vol {formatVol(market.volume)}
      </p>

      {/* Bot banner */}
      <div className="card mb-4 border-accent-gold/20 bg-accent-gold/5">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-accent-gold/20 flex items-center justify-center shrink-0">
            <Bot size={18} className="text-accent-gold" />
          </div>
          <div>
            <p className="text-xs text-text-secondary mb-1">Kalshi-Bot · Just now</p>
            <p className="text-sm font-medium">
              I see a {market.botEdge}% edge here. The market is pricing this wrong.
            </p>
            <p className="text-xs text-text-secondary mt-1">
              Model probability: {market.modelProb}% · Market price: {market.yesPrice}¢
            </p>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="card mb-4">
        <div className="flex gap-2 mb-3">
          {timeframes.map((t) => (
            <button
              key={t}
              onClick={() => setTf(t)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                tf === t ? "text-white" : "text-text-secondary bg-bg-elevated"
              }`}
              style={tf === t ? { background: "var(--accent-color)" } : undefined}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#30D158" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#30D158" stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis domain={["dataMin - 5", "dataMax + 5"]} hide />
              <Tooltip
                contentStyle={{
                  background: "#2C2C2E",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "rgba(235,235,245,0.6)" }}
                formatter={(value) => [`${Number(value).toFixed(1)}¢`, "Price"]}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#30D158"
                strokeWidth={2}
                dot={false}
                fill="url(#priceGrad)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {[
          { label: "Current", value: `${market.yesPrice}¢` },
          { label: "Last", value: `${market.stats.last}¢` },
          { label: "High", value: `${market.stats.high}¢` },
          { label: "Volume", value: formatVol(market.volume) },
        ].map((s) => (
          <div key={s.label} className="card text-center">
            <p className="text-xs text-text-secondary">{s.label}</p>
            <p className="font-mono font-bold text-lg">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Place order */}
      <div className="card mb-4">
        <h3 className="font-semibold mb-3">Place Order</h3>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs text-text-secondary block mb-1">Amount ($)</label>
            <input
              type="number"
              min={1}
              value={amount}
              onChange={(e) => setAmount(Math.max(1, parseInt(e.target.value) || 1))}
              className="w-full h-10 px-3 rounded-xl bg-bg-elevated border border-border-subtle font-mono text-sm focus:outline-none focus:border-white/20"
            />
          </div>
          <div>
            <label className="text-xs text-text-secondary block mb-1">Limit Price (¢, 0 = market)</label>
            <input
              type="number"
              min={0}
              max={99}
              value={limitPrice}
              onChange={(e) => setLimitPrice(Math.max(0, Math.min(99, parseInt(e.target.value) || 0)))}
              className="w-full h-10 px-3 rounded-xl bg-bg-elevated border border-border-subtle font-mono text-sm focus:outline-none focus:border-white/20"
            />
          </div>
        </div>
        <div className="flex justify-between text-xs text-text-secondary mb-4">
          <span>Shares: <span className="font-mono text-text-primary">{shares}</span></span>
          <span>Fill Chance: <span className="font-mono text-text-primary">{fillChance}%</span></span>
          <span>Total: <span className="font-mono text-text-primary">${totalCost.toFixed(2)}</span></span>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setConfirmModal("YES")}
            className="flex-1 h-11 rounded-xl text-sm font-bold bg-accent-green text-black"
          >
            BUY YES
          </button>
          <button
            onClick={() => setConfirmModal("NO")}
            className="flex-1 h-11 rounded-xl text-sm font-bold bg-accent-red text-white"
          >
            BUY NO
          </button>
        </div>
      </div>

      {/* User position */}
      {userPos && (
        <div className="card">
          <h3 className="font-semibold mb-3">Your Position</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-xs text-text-secondary">Shares</p>
              <p className="font-mono font-semibold">{userPos.shares}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">Avg Price</p>
              <p className="font-mono font-semibold">{userPos.avgPrice}¢</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">Current Value</p>
              <p className="font-mono font-semibold">
                ${((userPos.shares * userPos.currentPrice) / 100).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">P&L</p>
              {(() => {
                const pnl = (userPos.shares * (userPos.currentPrice - userPos.avgPrice)) / 100;
                return (
                  <p className={`font-mono font-semibold ${pnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                    {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
                  </p>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Confirm modal */}
      <Modal open={confirmModal !== null} onClose={() => setConfirmModal(null)}>
        {confirmModal && (
          <div>
            <h3 className="text-lg font-bold mb-2">Confirm Order</h3>
            <p className="text-sm text-text-secondary mb-4">
              Buy {shares} {confirmModal} contracts on "{market.question}" for ${totalCost.toFixed(2)}?
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmModal(null)}
                className="flex-1 h-11 rounded-xl text-sm font-semibold bg-bg-elevated text-text-primary border border-border-subtle"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                className={`flex-1 h-11 rounded-xl text-sm font-bold ${
                  confirmModal === "YES" ? "bg-accent-green text-black" : "bg-accent-red text-white"
                }`}
              >
                Confirm
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
