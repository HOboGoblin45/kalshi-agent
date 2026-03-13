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

function termBar(pct: number, width = 30): string {
  const filled = Math.round((pct / 100) * width);
  return "[" + "|".repeat(filled) + ".".repeat(width - filled) + "]";
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
      <div className="p-3 text-center card m-3">
        <p className="text-accent-red text-xs">[ERR] market not found</p>
        <button onClick={() => navigate("/")} className="mt-2 text-[10px] text-accent-green hover:underline">
          &lt;-- back to markets
        </button>
      </div>
    );
  }

  const yesPrice = market.yes_bid ?? market.last_price ?? 50;

  return (
    <div className="p-2 md:p-3 max-w-4xl mx-auto">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-[10px] text-text-tertiary hover:text-accent-green mb-2">
        <ArrowLeft size={12} />
        cd ..
      </button>

      <h1 className="text-xs font-bold text-accent-green term-glow mb-1 leading-snug">{market.title}</h1>
      {market.subtitle && <p className="text-[10px] text-text-secondary mb-1">{market.subtitle}</p>}
      <p className="text-[10px] text-text-tertiary mb-3">resolves:{formatCloseDate(market.close_time)} | vol:{formatVol(market.volume)}</p>

      <div className="card mb-3">
        <div className="flex items-center justify-center gap-6 py-2">
          <div className="text-center">
            <p className="text-[10px] text-text-tertiary">YES</p>
            <p className="text-2xl font-bold text-accent-green term-glow">{yesPrice}c</p>
          </div>
          <div className="text-2xl text-text-tertiary">/</div>
          <div className="text-center">
            <p className="text-[10px] text-text-tertiary">NO</p>
            <p className="text-2xl font-bold text-accent-red">{100 - yesPrice}c</p>
          </div>
        </div>
        <div className="text-center text-[11px] text-accent-green mt-1">
          {termBar(yesPrice)} {yesPrice}%
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        {[
          { label: "YES_BID", value: market.yes_bid != null ? `${market.yes_bid}c` : "--" },
          { label: "YES_ASK", value: market.yes_ask != null ? `${market.yes_ask}c` : "--" },
          { label: "LAST_PRICE", value: market.last_price != null ? `${market.last_price}c` : "--" },
          { label: "VOLUME", value: formatVol(market.volume) },
        ].map((s) => (
          <div key={s.label} className="card text-center">
            <p className="text-[10px] text-text-tertiary">{s.label}</p>
            <p className="font-bold text-xs text-accent-green">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="card mb-3">
        <div className="text-[10px] text-text-tertiary mb-1.5 uppercase tracking-wider">-- metadata --</div>
        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
          <KV label="ticker" value={market.ticker} />
          <KV label="event" value={market.event_ticker} />
          <KV label="status" value={market.status} />
          <KV label="platform" value={market.platform || "kalshi"} />
        </div>
      </div>

      {marketTrades.length > 0 && (
        <div className="card">
          <div className="text-[10px] text-text-tertiary mb-1.5 uppercase tracking-wider">-- bot trades --</div>
          <div className="space-y-0">
            {marketTrades.map((t, i) => (
              <div key={i} className="flex items-center justify-between text-[11px] py-1 border-b border-border-subtle/50 last:border-0">
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
      <p className="text-[10px] text-text-tertiary">{label}</p>
      <p className="text-xs text-accent-green">{value}</p>
    </div>
  );
}
