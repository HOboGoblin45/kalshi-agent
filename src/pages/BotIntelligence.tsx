import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Mic, Star, AlertTriangle, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../store/useStore";
import { markets } from "../data/markets";
import MarketCard from "../components/MarketCard";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";
import type { ChatMessage } from "../store/useStore";

const suggestedPrompts = [
  "What should I trade today?",
  "Biggest opportunities",
  "Explain my P&L",
];

const insightCards = [
  {
    icon: Star,
    title: "Top Pick Today",
    short: "Fed Rate Cut — 72¢ YES, +8% edge",
    detail:
      "The Fed Rate Cut market is currently priced at 72¢ YES, but our models estimate an 80% probability of a cut at the June FOMC meeting. Recent economic data supports this view with inflation cooling and employment softening. This represents an 8% edge opportunity with high conviction.",
  },
  {
    icon: AlertTriangle,
    title: "Risk Alert",
    short: "Bitcoin volatility spike expected",
    detail:
      "Bitcoin options markets are pricing in elevated volatility ahead of the halving anniversary. Our models detect increased correlation between BTC price and the Bitcoin $100K prediction market. Consider reducing position size or adding hedges if you hold YES contracts.",
  },
  {
    icon: Sparkles,
    title: "Market Prediction",
    short: "S&P 500 ATH likely by end of Q2",
    detail:
      "Based on historical patterns and current earnings momentum, our model assigns an 88% probability to the S&P 500 hitting a new all-time high before June 30. The market is pricing this at 81¢, suggesting a 7% edge. Institutional flows remain supportive.",
  },
];

function getBotResponse(text: string): { text: string; marketCards?: string[] } {
  const lower = text.toLowerCase();
  if (lower.includes("trade") || lower.includes("should i") || lower.includes("top pick")) {
    return {
      text: "Based on my analysis, the Fed Rate Cut market is your best opportunity right now. I'm seeing an 8% edge — the market is pricing YES at 72¢ but my models put the probability at 80%. Here's the market:",
      marketCards: ["fed-rate-june"],
    };
  }
  if (lower.includes("p&l") || lower.includes("profit") || lower.includes("performance")) {
    return {
      text: "Here's your P&L summary: You're up $2,847.21 today (+2.28%). Your portfolio is valued at $127,849.32 with a balance of $12,450.00. Your win rate stands at 68% across 142 total trades. Your best performer today is the Fed Rate Cut position (+$1,050).",
    };
  }
  if (lower.includes("opportunit") || lower.includes("biggest")) {
    return {
      text: "I've identified two high-conviction opportunities for you right now. Both show significant edges between my model probability and market price:",
      marketCards: ["fed-rate-june", "sp500-ath-q2"],
    };
  }
  return {
    text: "I've analyzed the current market landscape. There are 847 active markets being tracked, with 3 high-conviction signals right now. The political markets are seeing increased volume ahead of midterm positioning, and weather derivatives are showing unusual activity due to updated NOAA forecasts. Want me to dive deeper into any sector?",
  };
}

export default function BotIntelligence() {
  const { portfolio, botStatus, chatMessages, addChatMessage, setRiskMode } = useStore();
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [insightModal, setInsightModal] = useState<number | null>(null);
  const [scanCount, setScanCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();

  useEffect(() => {
    let count = 0;
    const interval = setInterval(() => {
      count += Math.floor(Math.random() * 40) + 10;
      if (count >= botStatus.marketsScanned) {
        setScanCount(botStatus.marketsScanned);
        clearInterval(interval);
      } else {
        setScanCount(count);
      }
    }, 50);
    return () => clearInterval(interval);
  }, [botStatus.marketsScanned]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chatMessages, typing]);

  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      const userMsg: ChatMessage = {
        id: `u-${Date.now()}`,
        sender: "user",
        text: text.trim(),
        timestamp: Date.now(),
      };
      addChatMessage(userMsg);
      setInput("");
      setTyping(true);

      setTimeout(() => {
        const response = getBotResponse(text);
        const botMsg: ChatMessage = {
          id: `b-${Date.now()}`,
          sender: "bot",
          text: response.text,
          marketCards: response.marketCards,
          timestamp: Date.now(),
        };
        addChatMessage(botMsg);
        setTyping(false);
      }, 800);
    },
    [addChatMessage]
  );

  const riskModes = ["Conservative", "Balanced", "Aggressive"] as const;

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 p-4 md:p-6 space-y-4">
        {/* Status card */}
        <div className="card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent-green pulse-green" />
            <span className="text-sm text-text-secondary">
              Scanning <span className="font-mono text-text-primary font-semibold">{scanCount}</span> markets
            </span>
          </div>
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-text-secondary">Win Rate </span>
              <span className="font-mono font-semibold">{portfolio.winRate}%</span>
            </div>
            <div>
              <span className="text-text-secondary">P&L </span>
              <span className="font-mono font-semibold text-accent-green">
                +${portfolio.todayPnl.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-text-secondary">Trades </span>
              <span className="font-mono font-semibold">{portfolio.totalTrades}</span>
            </div>
          </div>
        </div>

        {/* Risk mode selector */}
        <div className="flex bg-bg-surface rounded-xl p-1 border border-border-subtle">
          {riskModes.map((mode) => (
            <button
              key={mode}
              onClick={() => setRiskMode(mode)}
              className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                botStatus.riskMode === mode
                  ? "text-white shadow"
                  : "text-text-secondary hover:text-text-primary"
              }`}
              style={
                botStatus.riskMode === mode
                  ? { background: "var(--accent-color)" }
                  : undefined
              }
            >
              {mode}
            </button>
          ))}
        </div>

        {/* AI Insight Strip */}
        <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-none">
          {insightCards.map((card, i) => (
            <button
              key={i}
              onClick={() => setInsightModal(i)}
              className="card shrink-0 w-60 text-left hover:border-white/15 transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <card.icon size={16} className="text-accent-gold" />
                <span className="text-xs font-semibold text-accent-gold">{card.title}</span>
              </div>
              <p className="text-sm text-text-primary">{card.short}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 md:px-6 space-y-4 pb-4">
        {chatMessages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`flex gap-2 max-w-[80%] ${msg.sender === "user" ? "flex-row-reverse" : ""}`}>
              {msg.sender === "bot" && (
                <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-bold" style={{ background: "var(--accent-color)" }}>
                  K
                </div>
              )}
              <div>
                <div
                  className={`px-4 py-3 rounded-2xl text-sm ${
                    msg.sender === "user"
                      ? "text-white rounded-br-md"
                      : "bg-bg-elevated text-text-primary rounded-bl-md"
                  }`}
                  style={msg.sender === "user" ? { background: "var(--accent-color)" } : undefined}
                >
                  {msg.text}
                </div>
                {msg.marketCards && (
                  <div className="mt-2 space-y-2">
                    {msg.marketCards.map((id) => {
                      const m = markets.find((x) => x.id === id);
                      return m ? <MarketCard key={id} market={m} compact /> : null;
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        <AnimatePresence>
          {typing && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2"
            >
              <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-bold" style={{ background: "var(--accent-color)" }}>
                K
              </div>
              <div className="bg-bg-elevated px-4 py-3 rounded-2xl rounded-bl-md flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-2 h-2 rounded-full bg-text-secondary"
                    style={{
                      animation: "typing-bounce 1.2s infinite",
                      animationDelay: `${i * 0.15}s`,
                    }}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input area */}
      <div className="shrink-0 p-4 md:px-6 border-t border-border-subtle glass">
        <div className="flex gap-2 mb-3 overflow-x-auto scrollbar-none">
          {suggestedPrompts.map((p) => (
            <button
              key={p}
              onClick={() => sendMessage(p)}
              className="px-3 py-1.5 rounded-full text-xs font-medium bg-bg-surface border border-border-subtle text-text-secondary hover:text-text-primary whitespace-nowrap"
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => toast("Voice input not available", "info")}
            className="text-text-tertiary hover:text-text-primary"
          >
            <Mic size={20} />
          </button>
          <input
            type="text"
            placeholder="Ask Kalshi-Bot anything..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
            className="flex-1 h-10 px-4 rounded-xl bg-bg-surface border border-border-subtle text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-white/20"
          />
          <button
            onClick={() => sendMessage(input)}
            className="w-10 h-10 rounded-xl flex items-center justify-center text-white"
            style={{ background: "var(--accent-color)" }}
          >
            <Send size={16} />
          </button>
        </div>
      </div>

      {/* Insight modal */}
      <Modal open={insightModal !== null} onClose={() => setInsightModal(null)}>
        {insightModal !== null && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              {(() => {
                const Icon = insightCards[insightModal].icon;
                return <Icon size={20} className="text-accent-gold" />;
              })()}
              <h3 className="text-lg font-bold">{insightCards[insightModal].title}</h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">
              {insightCards[insightModal].detail}
            </p>
            <button
              onClick={() => setInsightModal(null)}
              className="mt-4 w-full h-11 rounded-xl text-sm font-semibold text-white"
              style={{ background: "var(--accent-color)" }}
            >
              Dismiss
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}
