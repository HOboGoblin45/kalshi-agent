import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
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
    return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return dt;
  }
}

export default function MarketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const markets = useStore((s) => s.markets);
  const trades = useStore((s) => s.trades);

  const market = markets.find((m) => m.ticker === id);
  const marketTrades = trades.filter((t) => t.ticker === id);

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

  const yesPrice = market.yes_bid ?? market.last_price ?? 50;

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary mb-4"
      >
        <ArrowLeft size={16} />
        Back
      </button>

      <h1 className="text-xl md:text-2xl font-bold mb-1">{market.title}</h1>
      {market.subtitle && (
        <p className="text-sm text-text-secondary mb-2">{market.subtitle}</p>
      )}
      <p className="text-sm text-text-tertiary mb-6">
        Resolves {formatCloseDate(market.close_time)} · Vol {formatVol(market.volume)}
      </p>

      {/* Price display */}
      <div className="card mb-4">
        <div className="flex items-center justify-center gap-8 py-4">
          <ProbabilityGauge value={yesPrice} size={80} />
          <div className="text-center">
            <p className="text-xs text-text-secondary mb-1">YES Price</p>
            <p className="font-mono text-3xl font-bold text-accent-green">{yesPrice}¢</p>
          </div>
          <div className="text-center">
            <p className="text-xs text-text-secondary mb-1">NO Price</p>
            <p className="font-mono text-3xl font-bold text-accent-red">{100 - yesPrice}¢</p>
          </div>
        </div>

        <div className="w-full h-3 rounded-full overflow-hidden bg-bg-elevated flex">
          <div className="h-full bg-accent-green rounded-l-full" style={{ width: `${yesPrice}%` }} />
          <div className="h-full bg-accent-red rounded-r-full" style={{ width: `${100 - yesPrice}%` }} />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {[
          { label: "YES Bid", value: market.yes_bid != null ? `${market.yes_bid}¢` : "--" },
          { label: "YES Ask", value: market.yes_ask != null ? `${market.yes_ask}¢` : "--" },
          { label: "Last Price", value: market.last_price != null ? `${market.last_price}¢` : "--" },
          { label: "Volume", value: formatVol(market.volume) },
        ].map((s) => (
          <div key={s.label} className="card text-center">
            <p className="text-xs text-text-secondary">{s.label}</p>
            <p className="font-mono font-bold text-lg">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Ticker info */}
      <div className="card mb-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-text-secondary">Ticker</p>
            <p className="font-mono text-xs">{market.ticker}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary">Event</p>
            <p className="font-mono text-xs">{market.event_ticker}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary">Status</p>
            <p className="text-xs">{market.status}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary">Platform</p>
            <p className="text-xs">{market.platform || "kalshi"}</p>
          </div>
        </div>
      </div>

      {/* Bot trades on this market */}
      {marketTrades.length > 0 && (
        <div className="card">
          <h3 className="font-semibold mb-3">Bot Trades on This Market</h3>
          <div className="space-y-2">
            {marketTrades.map((t, i) => (
              <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-border-subtle/50 last:border-0">
                <div>
                  <span className={`font-bold ${t.side === "yes" ? "text-accent-green" : "text-accent-red"}`}>
                    {t.side.toUpperCase()}
                  </span>
                  <span className="text-text-secondary ml-2">{t.contracts}x @{t.price_cents}¢</span>
                </div>
                <div className="text-xs text-text-secondary">
                  Edge: {t.edge}% · Conf: {t.confidence}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
