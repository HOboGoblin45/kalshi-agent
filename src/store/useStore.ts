import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
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
  clearChatMessages: () => void;
  toggleAgent: () => Promise<void>;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  timestamp: number;
}

const colorMap = {
  blue: "#0A84FF",
  green: "#30D158",
  purple: "#BF5AF2",
  orange: "#FF9F0A",
} as const;

function applyAccentColor(c: keyof typeof colorMap) {
  if (typeof document !== "undefined") {
    document.documentElement.style.setProperty("--accent-color", colorMap[c]);
  }
}

export const useStore = create<AppState>()(
  persist(
    (set, get) => ({
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
        applyAccentColor(c);
        set((s) => ({ settings: { ...s.settings, accentColor: c } }));
      },

      addChatMessage: (m) =>
        set((s) => ({
          chatMessages: [...s.chatMessages, m].slice(-150),
        })),

      clearChatMessages: () => set({ chatMessages: [] }),

      toggleAgent: async () => {
        try {
          const res = await api.toggle();
          if (res?.enabled === undefined) {
            throw new Error("Toggle rejected by dashboard (check local access/token).");
          }
          await get().fetchAll();
        } catch (e) {
          const msg = e instanceof Error ? e.message : "Toggle failed";
          console.error("Toggle failed:", e);
          set({ error: msg });
        }
      },
    }),
    {
      name: "kalshi-ui-store",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        settings: state.settings,
        chatMessages: state.chatMessages,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.settings?.accentColor) {
          applyAccentColor(state.settings.accentColor);
        }
      },
    }
  )
);
