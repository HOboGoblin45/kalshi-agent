import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
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
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return dt;
  }
}

function priceTextClass(pct: number): string {
  if (pct >= 70) return "text-accent-green";
  if (pct <= 30) return "text-accent-red";
  return "text-accent-gold";
}

function priceColor(pct: number): string {
  if (pct >= 70) return "green";
  if (pct <= 30) return "red";
  return "amber";
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
      <div className="p-4 text-center card m-4">
        <p className="text-accent-red text-sm">[ERR] market not found</p>
        <button onClick={() => navigate("/")} className="mt-2 text-xs text-accent-green hover:underline">
          &lt;-- back to markets
        </button>
      </div>
    );
  }

  const yesPrice = market.yes_bid ?? market.last_price ?? 50;
  const noPrice = 100 - yesPrice;
  const color = priceColor(yesPrice);
  const spread = (market.yes_ask != null && market.yes_bid != null)
    ? market.yes_ask - market.yes_bid
    : null;

  return (
    <div className="p-3 md:p-4 max-w-4xl mx-auto">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-accent-green mb-3">
        <ArrowLeft size={14} />
        cd ..
      </button>

      {/* Title */}
      <h1 className="text-base font-bold text-accent-green term-glow mb-1 leading-snug">{market.title}</h1>
      {market.subtitle && <p className="text-xs text-text-secondary mb-1">{market.subtitle}</p>}
      <p className="text-xs text-text-tertiary mb-4">
        resolves: {formatCloseDate(market.close_time)} | vol: {formatVol(market.volume)}
        {spread != null && ` | spread: ${spread}c`}
      </p>

      {/* Main price card */}
      <div className={`card card-${color} mb-4`}>
        <div className="flex items-center justify-center gap-8 py-3">
          <div className="text-center">
            <p className="text-xs text-text-secondary mb-1">YES</p>
            <p className={`text-3xl font-bold ${priceTextClass(yesPrice)} term-glow`}>{yesPrice}c</p>
          </div>
          <div className="text-2xl text-text-tertiary">/</div>
          <div className="text-center">
            <p className="text-xs text-text-secondary mb-1">NO</p>
            <p className={`text-3xl font-bold ${priceTextClass(noPrice)}`}>{noPrice}c</p>
          </div>
        </div>
        {/* Price bar */}
        <div className="price-bar mt-2">
          <div className={`price-bar-fill ${color}`} style={{ width: `${yesPrice}%` }} />
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {[
          { label: "YES BID", value: market.yes_bid != null ? `${market.yes_bid}c` : "--" },
          { label: "YES ASK", value: market.yes_ask != null ? `${market.yes_ask}c` : "--" },
          { label: "LAST PRICE", value: market.last_price != null ? `${market.last_price}c` : "--" },
          { label: "VOLUME", value: formatVol(market.volume) },
        ].map((s) => (
          <div key={s.label} className="card text-center py-3">
            <p className="text-[11px] text-text-tertiary mb-1">{s.label}</p>
            <p className="font-bold text-sm text-accent-green">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Metadata */}
      <div className="card mb-4">
        <div className="text-xs text-text-tertiary mb-2 uppercase tracking-wider">-- metadata --</div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <KV label="ticker" value={market.ticker} />
          <KV label="event" value={market.event_ticker} />
          <KV label="status" value={market.status} />
          <KV label="platform" value={market.platform || "kalshi"} />
        </div>
      </div>

      {/* Bot trades */}
      {marketTrades.length > 0 && (
        <div className="card">
          <div className="text-xs text-text-tertiary mb-2 uppercase tracking-wider">-- bot trades --</div>
          <div className="space-y-0">
            {marketTrades.map((t, i) => (
              <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-border-subtle/50 last:border-0">
                <div>
                  <span className={`font-bold ${t.side === "yes" ? "text-accent-green" : "text-accent-red"}`}>{t.side.toUpperCase()}</span>
                  <span className="text-text-tertiary ml-2">{t.contracts}x @{t.price_cents}c</span>
                </div>
                <div className="text-text-tertiary">edge:{t.edge}% conf:{t.confidence}%</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-text-tertiary">{label}</p>
      <p className="text-sm text-accent-green truncate">{value}</p>
    </div>
  );
}
