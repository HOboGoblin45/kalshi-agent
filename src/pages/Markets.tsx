import { useState } from "react";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useStore } from "../store/useStore";

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

function termBar(pct: number, width = 20): string {
  const filled = Math.round((pct / 100) * width);
  return "[" + "|".repeat(filled) + ".".repeat(width - filled) + "]";
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
    <div className="p-3 md:p-4 max-w-7xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <h1 className="text-sm font-bold uppercase tracking-wider term-glow">+--- MARKETS ---+</h1>
        {agentState && (
          <span className={`text-[10px] font-bold ${agentState.enabled ? "text-accent-green" : "text-accent-red"}`}>
            {agentState.enabled ? "[LIVE]" : "[OFF]"}
          </span>
        )}
        <span className="text-[10px] text-text-tertiary ml-auto">
          {filtered.length} results
        </span>
      </div>

      <div className="relative mb-3">
        <Search
          size={14}
          className="absolute left-2 top-1/2 -translate-y-1/2 text-text-tertiary"
        />
        <input
          type="text"
          placeholder="grep markets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full h-9 pl-8 pr-3 bg-bg-surface border border-border-subtle text-xs text-accent-green placeholder:text-text-tertiary focus:outline-none focus:border-accent-green"
        />
      </div>

      {filtered.length === 0 && !search && (
        <div className="text-center py-10 text-text-secondary card">
          <p className="text-xs">[INFO] no markets loaded yet</p>
          <p className="text-[10px] text-text-tertiary mt-1">agent will load markets on next scan...</p>
        </div>
      )}

      {filtered.length === 0 && search && (
        <div className="text-center py-10 text-text-secondary card">
          <p className="text-xs">[WARN] no matches for &quot;{search}&quot;</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {filtered.map((m) => {
          const yesPrice = m.yes_bid ?? m.last_price ?? 50;
          return (
            <motion.div
              key={m.ticker}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="card cursor-pointer transition-colors hover:border-accent-green group"
              onClick={() => navigate(`/market/${encodeURIComponent(m.ticker)}`)}
            >
              <div className="flex items-start justify-between mb-1.5">
                <span className="text-[10px] text-text-tertiary">
                  {m.ticker?.slice(0, 24)}
                </span>
                <span className="text-xs font-bold term-glow text-accent-green">{yesPrice}%</span>
              </div>

              <h3 className="text-xs text-accent-green font-medium mb-1.5 line-clamp-2 leading-snug">
                {m.title}
              </h3>

              <div className="flex items-center gap-2 text-[10px] text-text-tertiary mb-2">
                <span>vol:{formatVol(m.volume)}</span>
                <span>|</span>
                <span>exp:{formatCloseDate(m.close_time)}</span>
              </div>

              <div className="text-[10px] mb-1.5 tracking-tight">
                <span className="text-accent-green">{termBar(yesPrice)}</span>
                <span className="text-text-tertiary ml-1">{yesPrice}%</span>
              </div>

              <div className="flex items-center justify-between text-[10px]">
                <span className="text-text-secondary">
                  YES <span className="text-accent-green font-bold">{yesPrice}c</span>
                </span>
                <span className="text-text-secondary">
                  NO <span className="text-accent-red font-bold">{100 - yesPrice}c</span>
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
