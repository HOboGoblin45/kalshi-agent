import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  TrendingUp,
  Bitcoin,
  DollarSign,
  Trophy,
  CloudRain,
} from "lucide-react";
import ProbabilityGauge from "./ProbabilityGauge";
import ConvictionBadge from "./ConvictionBadge";
import type { Market } from "../data/markets";

const catIcons: Record<string, typeof TrendingUp> = {
  Politics: TrendingUp,
  Crypto: Bitcoin,
  Finance: DollarSign,
  Sports: Trophy,
  Weather: CloudRain,
};

function formatVol(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v}`;
}

interface Props {
  market: Market;
  compact?: boolean;
}

export default function MarketCard({ market, compact }: Props) {
  const navigate = useNavigate();
  const Icon = catIcons[market.category] || TrendingUp;
  const yes = market.yesPrice;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.01 }}
      className={`card cursor-pointer transition-colors hover:border-white/15 ${compact ? "p-3" : ""}`}
      onClick={() => navigate(`/market/${market.id}`)}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="w-8 h-8 rounded-lg bg-bg-elevated flex items-center justify-center">
          <Icon size={16} className="text-text-secondary" />
        </div>
        <ProbabilityGauge value={yes} size={compact ? 40 : 48} />
      </div>

      <h3
        className={`font-semibold text-text-primary mb-2 line-clamp-2 ${compact ? "text-sm" : "text-[15px]"}`}
      >
        {market.question}
      </h3>

      <div className="flex items-center gap-2 text-xs text-text-secondary mb-3">
        <span className="font-mono">{formatVol(market.volume)}</span>
        <span>·</span>
        <span>{market.closeDate}</span>
      </div>

      {/* Probability bar */}
      <div className="w-full h-2 rounded-full overflow-hidden bg-bg-elevated flex mb-3">
        <motion.div
          className="h-full bg-accent-green rounded-l-full"
          initial={{ width: 0 }}
          animate={{ width: `${yes}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
        <motion.div
          className="h-full bg-accent-red rounded-r-full"
          initial={{ width: 0 }}
          animate={{ width: `${100 - yes}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      <div className="flex items-center justify-between">
        <ConvictionBadge level={market.conviction} />
        {!compact && (
          <span className="text-xs text-text-tertiary font-medium">
            Kalshi-Bot
          </span>
        )}
      </div>

      {compact && (
        <button
          className="mt-3 w-full h-9 rounded-xl text-sm font-semibold text-white"
          style={{ background: "var(--accent-color)" }}
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/market/${market.id}`);
          }}
        >
          View Market
        </button>
      )}
    </motion.div>
  );
}
