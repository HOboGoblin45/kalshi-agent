import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, DollarSign, Sparkles, BarChart3, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../store/useStore";

const typeIcons: Record<string, { icon: typeof Bot; color: string }> = {
  price: { icon: DollarSign, color: "bg-orange-500/20 text-orange-400" },
  "bot-rec": { icon: Sparkles, color: "bg-accent-blue/20 text-accent-blue" },
  odds: { icon: BarChart3, color: "bg-bg-cell text-text-secondary" },
  resolve: { icon: AlertCircle, color: "bg-accent-red/20 text-accent-red" },
};

const digestText =
  "Good morning, John! I've been analyzing markets overnight and found 3 high-conviction opportunities. The Fed Rate Cut market has seen a significant shift — YES contracts jumped to 72¢ following softer-than-expected jobs data. The S&P 500 ATH market is showing strong momentum with institutional buying. I also noticed increased volatility in crypto prediction markets ahead of the Bitcoin halving anniversary. I recommend reviewing your open positions and considering the new Fed Rate Cut opportunity. Your portfolio is performing well with a 68% win rate across 142 trades.";

export default function Alerts() {
  const navigate = useNavigate();
  const { alerts, markAlertRead, dismissAlert } = useStore();
  const [expanded, setExpanded] = useState(false);

  const todayAlerts = alerts.filter((a) => a.group === "Today");
  const yesterdayAlerts = alerts.filter((a) => a.group === "Yesterday");

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl md:text-3xl font-bold mb-4">Alerts</h1>

      {/* Bot Digest */}
      <div className="card mb-6 border-accent-blue/20">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl shrink-0 flex items-center justify-center" style={{ background: "var(--accent-color)" }}>
            <Bot size={20} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-sm">Bot Digest</h3>
                <p className="text-xs text-text-secondary">from Kalshi-Bot · 2m ago</p>
              </div>
            </div>
            <p className={`text-sm text-text-secondary mt-2 leading-relaxed ${expanded ? "" : "line-clamp-2"}`}>
              {digestText}
            </p>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs font-medium mt-2 hover:text-text-primary"
              style={{ color: "var(--accent-color)" }}
            >
              {expanded ? "Show less" : "Read more"}
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
        </div>
      </div>

      {/* Alert groups */}
      {[
        { title: "Today", items: todayAlerts },
        { title: "Yesterday", items: yesterdayAlerts },
      ].map(
        ({ title, items }) =>
          items.length > 0 && (
            <div key={title} className="mb-6">
              <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
                {title}
              </h2>
              <div className="space-y-2">
                <AnimatePresence mode="popLayout">
                  {items.map((alert) => {
                    const { icon: Icon, color } = typeIcons[alert.type];
                    return (
                      <motion.div
                        key={alert.id}
                        layout
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, x: -200 }}
                        className="card flex items-center gap-3 cursor-pointer hover:border-white/15 transition-colors group relative"
                        onClick={() => {
                          markAlertRead(alert.id);
                          navigate(`/market/${alert.marketId}`);
                        }}
                      >
                        {!alert.read && (
                          <span className="absolute left-2 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full" style={{ background: "var(--accent-color)" }} />
                        )}
                        <div className={`w-9 h-9 rounded-lg shrink-0 flex items-center justify-center ${color}`}>
                          <Icon size={16} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm truncate ${alert.read ? "text-text-secondary" : "font-semibold text-text-primary"}`}>
                            {alert.title}
                          </p>
                          <p className="text-xs text-text-tertiary truncate">{alert.subtitle}</p>
                        </div>
                        <span className="text-xs text-text-tertiary shrink-0">{alert.timestamp}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            dismissAlert(alert.id);
                          }}
                          className="opacity-0 group-hover:opacity-100 text-xs text-accent-red font-medium px-2 py-1 rounded-lg hover:bg-accent-red/10 transition-opacity"
                        >
                          Dismiss
                        </button>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            </div>
          )
      )}

      {alerts.length === 0 && (
        <div className="text-center py-16 text-text-secondary">
          <p className="text-lg font-medium">No alerts</p>
          <p className="text-sm mt-1">You're all caught up!</p>
        </div>
      )}
    </div>
  );
}
