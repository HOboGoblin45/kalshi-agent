import { useState, useRef, useEffect, useCallback } from "react";
import { Send } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "../store/useStore";
import type { ChatMessage } from "../store/useStore";

function getBotResponse(text: string, agentState: ReturnType<typeof useStore.getState>["agentState"]): string {
  const s = agentState;
  if (!s) return "[ERR] agent not connected. start agent first.";

  const lower = text.toLowerCase();
  const balance = s.balance + (s.poly_balance || 0);

  if (lower.includes("status") || lower.includes("how") || lower.includes("running")) {
    return `[STATUS] agent=${s.enabled ? "ENABLED" : "DISABLED"} | status=${s.status} | balance=$${balance.toFixed(2)} | scans=${s.scan_count} | win_rate=${s.risk.win_rate} | pnl=${s.risk.day_pnl}`;
  }
  if (lower.includes("trade") || lower.includes("should i") || lower.includes("top pick")) {
    const trades = s.trades;
    if (trades.length === 0) return "[INFO] no trades placed yet. agent scanning for edge...";
    const last = trades[trades.length - 1];
    return `[TRADE] last=${last.side.toUpperCase()} ${last.contracts}x ${last.title || last.ticker} @${last.price_cents}c | edge=${last.edge}% conf=${last.confidence}% | day_trades=${s.risk.day_trades}`;
  }
  if (lower.includes("p&l") || lower.includes("profit") || lower.includes("performance")) {
    return `[PERF] pnl=${s.risk.day_pnl} | win_rate=${s.risk.win_rate} | total=${s.risk.total} | exposure=${s.risk.exposure}`;
  }
  if (lower.includes("balance") || lower.includes("money")) {
    return `[BAL] kalshi=$${s.balance.toFixed(2)} | poly=$${(s.poly_balance || 0).toFixed(2)} | total=$${balance.toFixed(2)}`;
  }
  if (lower.includes("scan") || lower.includes("market")) {
    return `[SCAN] count=${s.scan_count} | arb_interval=${s.scan_interval}m | ai_interval=${s.ai_interval}m | arb_opps=${s.arb_opps}`;
  }
  return `[SYS] status=${s.status} | balance=$${balance.toFixed(2)} | day_trades=${s.risk.day_trades} -- query: status, trades, p&l, balance, scans`;
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
        text: `[INIT] agent=${agentState.enabled ? "running" : "paused"} | balance=$${balance.toFixed(2)} | status=${agentState.status}`,
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

  const suggestedPrompts = ["--status", "--trades", "--pnl"];

  return (
    <div className="flex flex-col h-full">
      {/* Status Bar */}
      <div className="shrink-0 p-2 md:p-2.5">
        <div className="card flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px]">
          <div className="flex items-center gap-2">
            <span className={`font-bold ${agentState?.enabled ? "text-accent-green pulse-green" : "text-accent-red"}`}>
              {agentState?.enabled ? "[OK]" : "[OFF]"}
            </span>
            <span className="text-text-tertiary">{agentState?.status || "connecting..."}</span>
          </div>
          <div className="flex items-center gap-3">
            {agentState && (
              <>
                <span className="text-text-tertiary">win:<span className="text-accent-green">{agentState.risk.win_rate}</span></span>
                <span className="text-text-tertiary">pnl:<span className="text-accent-green">{agentState.risk.day_pnl}</span></span>
                <span className="text-text-tertiary">scans:<span className="text-accent-green">{agentState.scan_count}</span></span>
              </>
            )}
            <button
              onClick={clearChatMessages}
              className="px-1.5 py-0.5 border border-border-subtle text-text-tertiary hover:text-accent-green hover:border-accent-green"
              aria-label="Clear chat history"
            >
              [ CLEAR ]
            </button>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-2 md:px-2.5 space-y-1 pb-2.5">
        {chatMessages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[90%] ${msg.sender === "user" ? "text-right" : ""}`}>
              {msg.sender === "bot" ? (
                <div className="text-[11px] text-accent-green py-1">
                  <span className="text-text-tertiary">kalshi&gt; </span>
                  {msg.text}
                </div>
              ) : (
                <div className="text-[11px] text-accent-gold py-1">
                  <span className="text-text-tertiary">you$ </span>
                  {msg.text}
                </div>
              )}
            </div>
          </div>
        ))}

        <AnimatePresence>
          {typing && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[11px] py-1">
              <span className="text-text-tertiary">kalshi&gt; </span>
              <span className="text-accent-green animate-cursor">_</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input Area */}
      <div className="shrink-0 p-2 md:px-2.5 border-t border-border-subtle bg-bg-surface">
        <div className="flex gap-1.5 mb-1.5 overflow-x-auto">
          {suggestedPrompts.map((p) => (
            <button
              key={p}
              onClick={() => sendMessage(p)}
              className="px-2 py-0.5 text-[10px] font-medium border border-border-subtle text-text-tertiary hover:text-accent-green hover:border-accent-green whitespace-nowrap"
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-text-tertiary shrink-0">$</span>
          <input
            type="text"
            placeholder="query agent..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
            className="flex-1 h-8 px-2 bg-transparent border border-border-subtle text-xs text-accent-green placeholder:text-text-tertiary focus:outline-none focus:border-accent-green"
          />
          <button
            onClick={() => sendMessage(input)}
            className="h-8 px-3 border border-accent-green text-accent-green text-[10px] font-bold hover:bg-accent-green hover:text-bg-base transition-colors"
          >
            <Send size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
