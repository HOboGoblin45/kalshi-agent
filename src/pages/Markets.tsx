import { useState, useMemo } from "react";
import { Search, ChevronDown } from "lucide-react";
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

function priceColor(pct: number): string {
  if (pct >= 70) return "green";
  if (pct <= 30) return "red";
  return "amber";
}

function priceTextClass(pct: number): string {
  if (pct >= 70) return "text-accent-green";
  if (pct <= 30) return "text-accent-red";
  return "text-accent-gold";
}

type SortKey = "volume" | "yes_price" | "expiry" | "score" | "default";

const PAGE_SIZE = 30;

export default function Markets() {
  const navigate = useNavigate();
  const markets = useStore((s) => s.markets);
  const agentState = useStore((s) => s.agentState);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("default");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    let list = markets.filter((m) => {
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        (m.title || "").toLowerCase().includes(q) ||
        (m.subtitle || "").toLowerCase().includes(q) ||
        (m.ticker || "").toLowerCase().includes(q)
      );
    });

    if (sortBy === "volume") {
      list = [...list].sort((a, b) => (b.volume ?? 0) - (a.volume ?? 0));
    } else if (sortBy === "yes_price") {
      list = [...list].sort((a, b) => {
        const pa = a.display_price ?? a.yes_bid ?? a.last_price ?? 50;
        const pb = b.display_price ?? b.yes_bid ?? b.last_price ?? 50;
        return pb - pa;
      });
    } else if (sortBy === "expiry") {
      list = [...list].sort((a, b) => {
        const da = a.close_time ? new Date(a.close_time).getTime() : Infinity;
        const db = b.close_time ? new Date(b.close_time).getTime() : Infinity;
        return da - db;
      });
    } else if (sortBy === "score") {
      list = [...list].sort((a, b) => (b._score ?? 0) - (a._score ?? 0));
    }

    return list;
  }, [markets, search, sortBy]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Reset page when search/sort changes
  const handleSearch = (val: string) => { setSearch(val); setPage(0); };

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <h1 className="text-sm font-bold uppercase tracking-wider term-glow">+--- MARKETS ---+</h1>
        {agentState && (
          <span className={`text-xs font-bold ${agentState.enabled ? "text-accent-green" : "text-accent-red"}`}>
            {agentState.enabled ? "[LIVE]" : "[OFF]"}
          </span>
        )}
        <span className="text-xs text-text-secondary ml-auto">
          {filtered.length} markets
        </span>
      </div>

      {/* Search + Sort row */}
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary"
          />
          <input
            type="text"
            placeholder="grep markets..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full h-9 pl-8 pr-3 bg-bg-surface border border-border-subtle text-sm text-accent-green placeholder:text-text-tertiary focus:outline-none focus:border-accent-green"
          />
        </div>
        <div className="relative">
          <select
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value as SortKey); setPage(0); }}
            className="h-9 pl-2 pr-7 bg-bg-surface border border-border-subtle text-xs text-accent-green appearance-none cursor-pointer focus:outline-none focus:border-accent-green"
          >
            <option value="default">sort:default</option>
            <option value="score">sort:score</option>
            <option value="volume">sort:volume</option>
            <option value="yes_price">sort:yes%</option>
            <option value="expiry">sort:expiry</option>
          </select>
          <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
        </div>
      </div>

      {/* Empty states */}
      {filtered.length === 0 && !search && (
        <div className="text-center py-10 text-text-secondary card">
          <p className="text-sm">[INFO] no markets loaded yet</p>
          <p className="text-xs text-text-tertiary mt-1">agent will load markets on next scan...</p>
        </div>
      )}

      {filtered.length === 0 && search && (
        <div className="text-center py-10 text-text-secondary card">
          <p className="text-sm">[WARN] no matches for &quot;{search}&quot;</p>
        </div>
      )}

      {/* Market grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {paged.map((m) => {
          const yesPrice = m.display_price ?? m.yes_bid ?? m.last_price ?? 50;
          const noPrice = 100 - yesPrice;
          const color = priceColor(yesPrice);
          const hasLiquidity = (m.volume ?? 0) > 0;
          const cardBorder = !hasLiquidity ? "card-muted" : `card-${color}`;

          return (
            <motion.div
              key={m.ticker}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`card ${cardBorder} cursor-pointer group`}
              onClick={() => navigate(`/market/${encodeURIComponent(m.ticker)}`)}
            >
              {/* Category tag + score + ticker */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  {m.category ? (
                    <span className="text-[10px] uppercase tracking-wider text-text-tertiary bg-bg-elevated px-1.5 py-0.5">
                      {m.category}
                    </span>
                  ) : (
                    <span className="text-[10px] text-text-tertiary truncate max-w-[120px]">
                      {m.ticker}
                    </span>
                  )}
                  {(m._score ?? 0) > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 ${(m._score ?? 0) >= 10 ? "text-accent-green bg-accent-green/10" : (m._score ?? 0) >= 6 ? "text-accent-gold bg-accent-gold/10" : "text-text-tertiary bg-bg-elevated"}`}>
                      s:{m._score}
                    </span>
                  )}
                </div>
                {!hasLiquidity && (
                  <span className="text-[10px] text-text-tertiary bg-bg-elevated px-1.5 py-0.5">NO LIQ</span>
                )}
              </div>

              {/* Title */}
              <h3 className="text-sm text-accent-green font-semibold mb-3 line-clamp-2 leading-snug group-hover:term-glow">
                {m.title}
              </h3>

              {/* Price bar */}
              <div className="price-bar mb-2">
                <div
                  className={`price-bar-fill ${color}`}
                  style={{ width: `${yesPrice}%` }}
                />
              </div>

              {/* YES / NO prices - prominent */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xs text-text-secondary">YES</span>
                  <span className={`text-lg font-bold ${priceTextClass(yesPrice)}`}>{yesPrice}c</span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xs text-text-secondary">NO</span>
                  <span className={`text-lg font-bold ${priceTextClass(noPrice)}`}>{noPrice}c</span>
                </div>
              </div>

              {/* Metadata row */}
              <div className="flex items-center justify-between text-xs text-text-tertiary border-t border-border-subtle pt-2">
                <span>vol: {formatVol(m.volume)}</span>
                <span>exp: {formatCloseDate(m.close_time)}</span>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4 text-xs">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="px-2 py-1 border border-border-subtle text-text-secondary hover:text-accent-green hover:border-accent-green disabled:opacity-30 disabled:cursor-not-allowed"
          >
            &lt; prev
          </button>
          <span className="text-text-secondary">
            page {page + 1}/{totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            className="px-2 py-1 border border-border-subtle text-text-secondary hover:text-accent-green hover:border-accent-green disabled:opacity-30 disabled:cursor-not-allowed"
          >
            next &gt;
          </button>
        </div>
      )}
    </div>
  );
}
