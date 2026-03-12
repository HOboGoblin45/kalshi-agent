import { create } from "zustand";
import { api, type AgentState, type KalshiMarket, type KalshiPosition, type Trade } from "../api";

interface AppState {
  // Live data from backend
  agentState: AgentState | null;
  markets: KalshiMarket[];
  positions: KalshiPosition[];
  trades: Trade[];
  loading: boolean;
  error: string | null;
  lastFetch: number;

  // Local UI settings
  settings: {
    accentColor: "blue" | "green" | "purple" | "orange";
  };

  // Chat messages (local only)
  chatMessages: ChatMessage[];

  // Actions
  fetchAll: () => Promise<void>;
  setAccentColor: (c: AppState["settings"]["accentColor"]) => void;
  addChatMessage: (m: ChatMessage) => void;
  toggleAgent: () => Promise<void>;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: number;
}

export const useStore = create<AppState>((set, get) => ({
  agentState: null,
  markets: [],
  positions: [],
  trades: [],
  loading: true,
  error: null,
  lastFetch: 0,

  settings: {
    accentColor: "blue",
  },

  chatMessages: [],

  fetchAll: async () => {
    try {
      const [state, markets, positions] = await Promise.all([
        api.getState(),
        api.getMarkets(),
        api.getPositions(),
      ]);
      set({
        agentState: state,
        markets,
        positions,
        trades: state.trades,
        loading: false,
        error: null,
        lastFetch: Date.now(),
      });
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : "Failed to connect to agent",
      });
    }
  },

  setAccentColor: (c) => {
    const colorMap = {
      blue: "#0A84FF",
      green: "#30D158",
      purple: "#BF5AF2",
      orange: "#FF9F0A",
    };
    document.documentElement.style.setProperty("--accent-color", colorMap[c]);
    set((s) => ({ settings: { ...s.settings, accentColor: c } }));
  },

  addChatMessage: (m) =>
    set((s) => ({ chatMessages: [...s.chatMessages, m] })),

  toggleAgent: async () => {
    try {
      await api.toggle();
      await get().fetchAll();
    } catch (e) {
      console.error("Toggle failed:", e);
    }
  },
}));
