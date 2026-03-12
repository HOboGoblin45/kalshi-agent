import { useState } from "react";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useStore } from "../store/useStore";
import ProbabilityGauge from "../components/ProbabilityGauge";

function formatVol(v: number | null) {
  if (!v) return "$0";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v}`;
}

function formatCloseDate(dt: string | null) {
  if (!dt) return "";
  try {
    return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return dt;
  }
}

export default function Markets() {
  const navigate = useNavigate();
  const markets = useStore((s) => s.markets);
  const agentState = useStore((s) => s.agentState);
  const [search, setSearch] = useState("");

  const filtered = markets.filter((m) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (m.title || "").toLowerCase().includes(q) ||
           (m.subtitle || "").toLowerCase().includes(q) ||
           (m.ticker || "").toLowerCase().includes(q);
  });

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl md:text-3xl font-bold">Markets</h1>
        {agentState && (
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${agentState.enabled ? "bg-accent-green pulse-green" : "bg-accent-red"}`} />
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${agentState.enabled ? "text-accent-green bg-accent-green/15" : "text-accent-red bg-accent-red/15"}`}>
              {agentState.enabled ? "LIVE" : "OFF"}
            </span>
          </div>
        )}
        <span className="text-xs text-text-secondary ml-auto font-mono">
          {filtered.length} markets
        </span>
      </div>

      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
        <input
          type="text"
          placeholder="Search markets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full h-10 pl-9 pr-4 rounded-xl bg-bg-surface border border-border-subtle text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-white/20"
        />
      </div>

      {filtered.length === 0 && !search && (
        <div className="text-center py-16 text-text-secondary">
          <p className="text-lg font-medium">No markets loaded yet</p>
          <p className="text-sm mt-1">The agent will load markets on its next scan</p>
        </div>
      )}

      {filtered.length === 0 && search && (
        <div className="text-center py-16 text-text-secondary">
          <p className="text-lg font-medium">No markets found</p>
          <p className="text-sm mt-1">Try a different search</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((m) => {
          const yesPrice = m.yes_bid ?? m.last_price ?? 50;
          return (
            <motion.div
              key={m.ticker}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              whileHover={{ scale: 1.01 }}
              className="card cursor-pointer transition-colors hover:border-white/15"
              onClick={() => navigate(`/market/${encodeURIComponent(m.ticker)}`)}
            >
              <div className="flex items-start justify-between mb-3">
                <span className="text-[10px] font-mono text-text-tertiary bg-bg-elevated px-2 py-0.5 rounded">
                  {m.ticker?.slice(0, 20)}
                </span>
                <ProbabilityGauge value={yesPrice} size={48} />
              </div>

              <h3 className="font-semibold text-[15px] text-text-primary mb-2 line-clamp-2">
                {m.title}
              </h3>

              <div className="flex items-center gap-2 text-xs text-text-secondary mb-3">
                <span className="font-mono">{formatVol(m.volume)}</span>
                <span>·</span>
                <span>{formatCloseDate(m.close_time)}</span>
              </div>

              <div className="w-full h-2 rounded-full overflow-hidden bg-bg-elevated flex mb-3">
                <motion.div
                  className="h-full bg-accent-green rounded-l-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${yesPrice}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                />
                <motion.div
                  className="h-full bg-accent-red rounded-r-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${100 - yesPrice}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                />
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">
                  YES <span className="font-mono text-accent-green">{yesPrice}¢</span>
                </span>
                <span className="text-text-secondary">
                  NO <span className="font-mono text-accent-red">{100 - yesPrice}¢</span>
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
