import { useState, useRef, useEffect, useCallback } from "react";
import { Send } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "../store/useStore";
import type { ChatMessage } from "../store/useStore";

function getBotResponse(text: string, agentState: ReturnType<typeof useStore.getState>["agentState"]): string {
  const s = agentState;
  if (!s) return "Agent is not connected. Start the agent first.";

  const lower = text.toLowerCase();
  const balance = s.balance + (s.poly_balance || 0);

  if (lower.includes("status") || lower.includes("how") || lower.includes("running")) {
    return `Agent is ${s.enabled ? "ENABLED" : "DISABLED"}. Status: ${s.status}. Balance: $${balance.toFixed(2)}. Scans completed: ${s.scan_count}. Win rate: ${s.risk.win_rate}. Today P&L: ${s.risk.day_pnl}.`;
  }
  if (lower.includes("trade") || lower.includes("should i") || lower.includes("top pick")) {
    const trades = s.trades;
    if (trades.length === 0) return "No trades have been placed yet. The agent is scanning markets and will trade when it finds opportunities with edge.";
    const last = trades[trades.length - 1];
    return `Last trade: ${last.side.toUpperCase()} ${last.contracts}x ${last.title || last.ticker} @${last.price_cents}¢ (edge: ${last.edge}%, confidence: ${last.confidence}%). Total trades today: ${s.risk.day_trades}.`;
  }
  if (lower.includes("p&l") || lower.includes("profit") || lower.includes("performance")) {
    return `Today P&L: ${s.risk.day_pnl}. Win rate: ${s.risk.win_rate}. Total trades: ${s.risk.total}. Exposure: ${s.risk.exposure}. Balance: $${balance.toFixed(2)}.`;
  }
  if (lower.includes("balance") || lower.includes("money")) {
    return `Kalshi balance: $${s.balance.toFixed(2)}. Polymarket: $${(s.poly_balance || 0).toFixed(2)}. Combined: $${balance.toFixed(2)}.`;
  }
  if (lower.includes("scan") || lower.includes("market")) {
    return `${s.scan_count} scans completed. Arb scan every ${s.scan_interval}m, AI debate every ${s.ai_interval}m. Found ${s.arb_opps} arbitrage opportunities. Status: ${s.status}.`;
  }
  return `Agent status: ${s.status}. Balance: $${balance.toFixed(2)}. ${s.scan_count} scans done. ${s.risk.day_trades} trades today. Ask me about trades, P&L, balance, or scan status.`;
}

export default function BotIntelligence() {
  const agentState = useStore((s) => s.agentState);
  const { chatMessages, addChatMessage } = useStore();
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chatMessages, typing]);

  // Initial welcome message
  useEffect(() => {
    if (chatMessages.length === 0 && agentState) {
      const balance = agentState.balance + (agentState.poly_balance || 0);
      addChatMessage({
        id: "welcome",
        sender: "bot",
        text: `Agent is ${agentState.enabled ? "running" : "paused"}. Balance: $${balance.toFixed(2)}. Status: ${agentState.status}. Ask me anything about trades, P&L, or market scans.`,
        timestamp: Date.now(),
      });
    }
  }, [agentState, chatMessages.length, addChatMessage]);

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
        const response = getBotResponse(text, agentState);
        const botMsg: ChatMessage = {
          id: `b-${Date.now()}`,
          sender: "bot",
          text: response,
          timestamp: Date.now(),
        };
        addChatMessage(botMsg);
        setTyping(false);
      }, 400);
    },
    [addChatMessage, agentState]
  );

  const suggestedPrompts = [
    "What's the agent status?",
    "Show recent trades",
    "What's my P&L?",
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 p-4 md:p-6 space-y-4">
        {/* Status card */}
        <div className="card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${agentState?.enabled ? "bg-accent-green pulse-green" : "bg-accent-red"}`} />
            <span className="text-sm text-text-secondary">
              {agentState?.status || "Connecting..."}
            </span>
          </div>
          {agentState && (
            <div className="flex items-center gap-6 text-sm">
              <div>
                <span className="text-text-secondary">Win Rate </span>
                <span className="font-mono font-semibold">{agentState.risk.win_rate}</span>
              </div>
              <div>
                <span className="text-text-secondary">P&L </span>
                <span className="font-mono font-semibold">{agentState.risk.day_pnl}</span>
              </div>
              <div>
                <span className="text-text-secondary">Scans </span>
                <span className="font-mono font-semibold">{agentState.scan_count}</span>
              </div>
            </div>
          )}
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
            </div>
          </div>
        ))}

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
          <input
            type="text"
            placeholder="Ask about trades, P&L, markets..."
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
    </div>
  );
}
