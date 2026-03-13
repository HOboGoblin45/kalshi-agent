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
    return new Date(dt).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
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
      <div className="p-4 text-center">
        <p className="text-text-secondary">Market not found</p>
        <button onClick={() => navigate("/")} className="mt-2 text-sm" style={{ color: "var(--accent-color)" }}>
          Back to Markets
        </button>
      </div>
    );
  }

  const yesPrice = market.yes_bid ?? market.last_price ?? 50;

  return (
    <div className="p-2 md:p-2.5 max-w-4xl mx-auto">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-[11px] text-text-secondary hover:text-text-primary mb-1.5">
        <ArrowLeft size={12} />
        Back
      </button>

      <h1 className="text-base md:text-lg font-bold mb-1 leading-tight">{market.title}</h1>
      {market.subtitle && <p className="text-[11px] text-text-secondary mb-1">{market.subtitle}</p>}
      <p className="text-[11px] text-text-tertiary mb-2">Resolves {formatCloseDate(market.close_time)} | Vol {formatVol(market.volume)}</p>

      <div className="card mb-2.5">
        <div className="flex items-center justify-center gap-4 py-1.5">
          <ProbabilityGauge value={yesPrice} size={58} />
          <PriceBlock label="YES" value={`${yesPrice}c`} color="text-accent-green" />
          <PriceBlock label="NO" value={`${100 - yesPrice}c`} color="text-accent-red" />
        </div>

        <div className="w-full h-1.5 rounded-full overflow-hidden bg-bg-elevated flex">
          <div className="h-full bg-accent-green rounded-l-full" style={{ width: `${yesPrice}%` }} />
          <div className="h-full bg-accent-red rounded-r-full" style={{ width: `${100 - yesPrice}%` }} />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2.5">
        {[
          { label: "YES Bid", value: market.yes_bid != null ? `${market.yes_bid}c` : "--" },
          { label: "YES Ask", value: market.yes_ask != null ? `${market.yes_ask}c` : "--" },
          { label: "Last Price", value: market.last_price != null ? `${market.last_price}c` : "--" },
          { label: "Volume", value: formatVol(market.volume) },
        ].map((s) => (
          <div key={s.label} className="card text-center">
            <p className="text-[10px] text-text-secondary">{s.label}</p>
            <p className="font-mono font-bold text-xs">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="card mb-2.5">
        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
          <KV label="Ticker" value={market.ticker} mono />
          <KV label="Event" value={market.event_ticker} mono />
          <KV label="Status" value={market.status} />
          <KV label="Platform" value={market.platform || "kalshi"} />
        </div>
      </div>

      {marketTrades.length > 0 && (
        <div className="card">
          <h3 className="font-semibold mb-1.5 text-xs">Bot Trades on This Market</h3>
          <div className="space-y-0.5">
            {marketTrades.map((t, i) => (
              <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-border-subtle/50 last:border-0">
                <div>
                  <span className={`font-bold ${t.side === "yes" ? "text-accent-green" : "text-accent-red"}`}>{t.side.toUpperCase()}</span>
                  <span className="text-text-secondary ml-1.5">{t.contracts}x @{t.price_cents}c</span>
                </div>
                <div className="text-text-secondary">Edge {t.edge}% | Conf {t.confidence}%</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PriceBlock({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="text-center">
      <p className="text-[10px] text-text-secondary mb-0.5">{label} Price</p>
      <p className={`font-mono text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

function KV({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[10px] text-text-secondary">{label}</p>
      <p className={`${mono ? "font-mono" : ""} text-xs`}>{value}</p>
    </div>
  );
}
