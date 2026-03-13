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
    return new Date(dt).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
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
    return (
      (m.title || "").toLowerCase().includes(q) ||
      (m.subtitle || "").toLowerCase().includes(q) ||
      (m.ticker || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-2 md:p-2.5 max-w-6xl mx-auto">
      <div className="flex items-center gap-1.5 mb-2">
        <h1 className="text-base md:text-lg font-bold">Markets</h1>
        {agentState && (
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                agentState.enabled ? "bg-accent-green pulse-green" : "bg-accent-red"
              }`}
            />
            <span
              className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                agentState.enabled
                  ? "text-accent-green bg-accent-green/15"
                  : "text-accent-red bg-accent-red/15"
              }`}
            >
              {agentState.enabled ? "LIVE" : "OFF"}
            </span>
          </div>
        )}
        <span className="text-[10px] text-text-secondary ml-auto font-mono">
          {filtered.length} markets
        </span>
      </div>

      <div className="relative mb-2">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
        />
        <input
          type="text"
          placeholder="Search markets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full h-8 pl-8.5 pr-2.5 rounded-md bg-bg-surface border border-border-subtle text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-white/20"
        />
      </div>

      {filtered.length === 0 && !search && (
        <div className="text-center py-10 text-text-secondary">
          <p className="text-base font-medium">No markets loaded yet</p>
          <p className="text-xs mt-1">The agent will load markets on its next scan</p>
        </div>
      )}

      {filtered.length === 0 && search && (
        <div className="text-center py-10 text-text-secondary">
          <p className="text-base font-medium">No markets found</p>
          <p className="text-xs mt-1">Try a different search</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {filtered.map((m) => {
          const yesPrice = m.yes_bid ?? m.last_price ?? 50;
          return (
            <motion.div
              key={m.ticker}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="card cursor-pointer transition-colors hover:border-white/20"
              onClick={() => navigate(`/market/${encodeURIComponent(m.ticker)}`)}
            >
              <div className="flex items-start justify-between mb-1.5">
                <span className="text-[10px] font-mono text-text-tertiary bg-bg-elevated px-1.5 py-0.5 rounded">
                  {m.ticker?.slice(0, 20)}
                </span>
                <ProbabilityGauge value={yesPrice} />
              </div>

              <h3 className="font-semibold text-[12px] text-text-primary mb-1 line-clamp-2 leading-tight">
                {m.title}
              </h3>

              <div className="flex items-center gap-1.5 text-[10px] text-text-secondary mb-1.5">
                <span className="font-mono">{formatVol(m.volume)}</span>
                <span>|</span>
                <span>{formatCloseDate(m.close_time)}</span>
              </div>

              <div className="w-full h-1 rounded-full overflow-hidden bg-bg-elevated flex mb-1.5">
                <motion.div
                  className="h-full bg-accent-green rounded-l-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${yesPrice}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
                <motion.div
                  className="h-full bg-accent-red rounded-r-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${100 - yesPrice}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
              </div>

              <div className="flex items-center justify-between text-[10px]">
                <span className="text-text-secondary">
                  YES <span className="font-mono text-accent-green">{yesPrice}c</span>
                </span>
                <span className="text-text-secondary">
                  NO <span className="font-mono text-accent-red">{100 - yesPrice}c</span>
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
