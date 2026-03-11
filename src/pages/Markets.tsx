import { useState } from "react";
import { Search } from "lucide-react";
import { motion } from "framer-motion";
import MarketCard from "../components/MarketCard";
import { markets, type Market } from "../data/markets";

const categories = ["All", "Politics", "Crypto", "Finance", "Sports", "Weather"] as const;

export default function Markets() {
  const [search, setSearch] = useState("");
  const [cat, setCat] = useState<string>("All");

  const filtered = markets.filter((m) => {
    const matchSearch = m.question.toLowerCase().includes(search.toLowerCase());
    const matchCat = cat === "All" || m.category === cat;
    return matchSearch && matchCat;
  });

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl md:text-3xl font-bold">Markets</h1>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-accent-green pulse-green" />
          <span className="text-xs font-semibold text-accent-green bg-accent-green/15 px-2 py-0.5 rounded-full">
            LIVE
          </span>
        </div>
      </div>

      {/* Search */}
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

      {/* Filter chips */}
      <div className="flex gap-2 overflow-x-auto pb-4 scrollbar-none">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setCat(c)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
              cat === c
                ? "text-white"
                : "bg-bg-surface text-text-secondary border border-border-subtle hover:bg-bg-elevated"
            }`}
            style={cat === c ? { background: "var(--accent-color)" } : undefined}
          >
            {c}
          </button>
        ))}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((m) => (
          <MarketCard key={m.id} market={m} />
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16 text-text-secondary">
          <p className="text-lg font-medium">No markets found</p>
          <p className="text-sm mt-1">Try a different search or filter</p>
        </div>
      )}
    </div>
  );
}
