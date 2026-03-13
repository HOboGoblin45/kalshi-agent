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
    return `Agent is ${s.enabled ? "ENABLED" : "DISABLED"}. Status: ${s.status}. Balance: $${balance.toFixed(2)}. Scans: ${s.scan_count}. Win rate: ${s.risk.win_rate}. P&L: ${s.risk.day_pnl}.`;
  }
  if (lower.includes("trade") || lower.includes("should i") || lower.includes("top pick")) {
    const trades = s.trades;
    if (trades.length === 0) return "No trades have been placed yet. The agent is still scanning for edge.";
    const last = trades[trades.length - 1];
    return `Last trade: ${last.side.toUpperCase()} ${last.contracts}x ${last.title || last.ticker} @${last.price_cents}c (edge ${last.edge}%, conf ${last.confidence}%). Trades today: ${s.risk.day_trades}.`;
  }
  if (lower.includes("p&l") || lower.includes("profit") || lower.includes("performance")) {
    return `Today P&L: ${s.risk.day_pnl}. Win rate: ${s.risk.win_rate}. Total trades: ${s.risk.total}. Exposure: ${s.risk.exposure}.`; 
  }
  if (lower.includes("balance") || lower.includes("money")) {
    return `Kalshi: $${s.balance.toFixed(2)}. Polymarket: $${(s.poly_balance || 0).toFixed(2)}. Combined: $${balance.toFixed(2)}.`;
  }
  if (lower.includes("scan") || lower.includes("market")) {
    return `${s.scan_count} scans completed. Arb every ${s.scan_interval}m, AI debate every ${s.ai_interval}m. Arb opportunities: ${s.arb_opps}.`; 
  }
  return `Status: ${s.status}. Balance: $${balance.toFixed(2)}. ${s.risk.day_trades} trades today. Ask about trades, P&L, balance, or scans.`;
}

export default function BotIntelligence() {
  const agentState = useStore((s) => s.agentState);
  const { chatMessages, addChatMessage, clearChatMessages } = useStore();
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chatMessages, typing]);

  useEffect(() => {
    if (chatMessages.length === 0 && agentState) {
      const balance = agentState.balance + (agentState.poly_balance || 0);
      addChatMessage({
        id: "welcome",
        sender: "bot",
        text: `Agent is ${agentState.enabled ? "running" : "paused"}. Balance: $${balance.toFixed(2)}. Status: ${agentState.status}.`,
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
      }, 250);
    },
    [addChatMessage, agentState]
  );

  const suggestedPrompts = ["Status?", "Recent trades", "What is my P&L?"];

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 p-2 md:p-2.5 space-y-2">
        <div className="card flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${agentState?.enabled ? "bg-accent-green pulse-green" : "bg-accent-red"}`} />
            <span className="text-[11px] text-text-secondary">{agentState?.status || "Connecting..."}</span>
          </div>
          <div className="flex items-center gap-2">
            {agentState && (
              <div className="flex items-center gap-2 text-[11px]">
              <Stat label="Win" value={agentState.risk.win_rate} />
              <Stat label="P&L" value={agentState.risk.day_pnl} />
              <Stat label="Scans" value={String(agentState.scan_count)} />
              </div>
            )}
            <button
              onClick={clearChatMessages}
              className="h-6 px-2 rounded-md border border-border-subtle text-[10px] text-text-secondary hover:text-text-primary"
              aria-label="Clear chat history"
            >
              Clear
            </button>
          </div>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-2 md:px-2.5 space-y-2 pb-2.5">
        {chatMessages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`flex gap-2 max-w-[86%] ${msg.sender === "user" ? "flex-row-reverse" : ""}`}>
              {msg.sender === "bot" && (
                <div className="w-5 h-5 rounded-full shrink-0 flex items-center justify-center text-[9px] font-bold" style={{ background: "var(--accent-color)" }}>
                  K
                </div>
              )}
              <div
                className={`px-2.5 py-1.5 rounded-lg text-[11px] ${
                  msg.sender === "user"
                    ? "text-white rounded-br-sm"
                    : "bg-bg-elevated text-text-primary rounded-bl-sm"
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
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
              <div className="w-5 h-5 rounded-full shrink-0 flex items-center justify-center text-[9px] font-bold" style={{ background: "var(--accent-color)" }}>
                K
              </div>
              <div className="bg-bg-elevated px-2.5 py-1.5 rounded-lg rounded-bl-sm flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-text-secondary"
                    style={{ animation: "typing-bounce 1.2s infinite", animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="shrink-0 p-2 md:px-2.5 border-t border-border-subtle glass">
        <div className="flex gap-1 mb-1.5 overflow-x-auto scrollbar-none">
          {suggestedPrompts.map((p) => (
            <button
              key={p}
              onClick={() => sendMessage(p)}
              className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-bg-surface border border-border-subtle text-text-secondary hover:text-text-primary whitespace-nowrap"
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Ask about trades, P&L, scans..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
            className="flex-1 h-8 px-2.5 rounded-md bg-bg-surface border border-border-subtle text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-white/20"
          />
          <button
            onClick={() => sendMessage(input)}
            className="w-8 h-8 rounded-md flex items-center justify-center text-white"
            style={{ background: "var(--accent-color)" }}
          >
            <Send size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-text-secondary">{label} </span>
      <span className="font-mono font-semibold">{value}</span>
    </div>
  );
}
