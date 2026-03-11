import { create } from "zustand";

export interface Position {
  id: string;
  marketId: string;
  marketQuestion: string;
  side: "YES" | "NO";
  shares: number;
  avgPrice: number;
  currentPrice: number;
  closeDate: string;
  status: "open" | "pending" | "settled";
  settledPnl?: number;
}

export interface Alert {
  id: string;
  type: "price" | "bot-rec" | "odds" | "resolve";
  title: string;
  subtitle: string;
  timestamp: string;
  group: "Today" | "Yesterday";
  read: boolean;
  marketId: string;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "bot";
  text: string;
  marketCards?: string[];
  timestamp: number;
}

interface AppState {
  portfolio: {
    balance: number;
    totalValue: number;
    todayPnl: number;
    todayPnlPct: number;
    winRate: number;
    totalTrades: number;
  };
  positions: Position[];
  alerts: Alert[];
  botStatus: {
    isScanning: boolean;
    marketsScanned: number;
    riskMode: "Conservative" | "Balanced" | "Aggressive";
    autoTrade: boolean;
    maxPositionSize: number;
  };
  settings: {
    notifications: {
      priceAlerts: boolean;
      botRecs: boolean;
      oddsMovement: boolean;
      resolving: boolean;
    };
    accentColor: "blue" | "green" | "purple" | "orange";
    displayName: string;
  };
  chatMessages: ChatMessage[];

  // Actions
  setRiskMode: (mode: "Conservative" | "Balanced" | "Aggressive") => void;
  setAutoTrade: (v: boolean) => void;
  setMaxPositionSize: (v: number) => void;
  setNotification: (key: keyof AppState["settings"]["notifications"], v: boolean) => void;
  setAccentColor: (c: AppState["settings"]["accentColor"]) => void;
  setDisplayName: (n: string) => void;
  addPosition: (p: Position) => void;
  removePosition: (id: string) => void;
  addSharesToPosition: (id: string, shares: number) => void;
  markAlertRead: (id: string) => void;
  dismissAlert: (id: string) => void;
  addChatMessage: (m: ChatMessage) => void;
}

export const useStore = create<AppState>((set) => ({
  portfolio: {
    balance: 12450.0,
    totalValue: 127849.32,
    todayPnl: 2847.21,
    todayPnlPct: 2.28,
    winRate: 68,
    totalTrades: 142,
  },
  positions: [
    {
      id: "pos-1",
      marketId: "fed-rate-june",
      marketQuestion: "Will the Fed cut interest rates at the June 2026 FOMC meeting?",
      side: "YES",
      shares: 150,
      avgPrice: 65,
      currentPrice: 72,
      closeDate: "Jun 18, 2026",
      status: "open",
    },
    {
      id: "pos-2",
      marketId: "btc-100k-q2",
      marketQuestion: "Will Bitcoin exceed $100,000 before July 1, 2026?",
      side: "YES",
      shares: 200,
      avgPrice: 52,
      currentPrice: 58,
      closeDate: "Jul 1, 2026",
      status: "open",
    },
    {
      id: "pos-3",
      marketId: "sp500-ath-q2",
      marketQuestion: "Will the S&P 500 hit a new all-time high in Q2 2026?",
      side: "YES",
      shares: 100,
      avgPrice: 74,
      currentPrice: 81,
      closeDate: "Jun 30, 2026",
      status: "open",
    },
    {
      id: "pos-4",
      marketId: "dem-house-2026",
      marketQuestion: "Will Democrats win the House in the 2026 midterm elections?",
      side: "NO",
      shares: 80,
      avgPrice: 48,
      currentPrice: 45,
      closeDate: "Nov 3, 2026",
      status: "pending",
    },
    {
      id: "pos-5",
      marketId: "world-cup-usa",
      marketQuestion: "Will the USA advance past the group stage in the 2026 World Cup?",
      side: "YES",
      shares: 120,
      avgPrice: 70,
      currentPrice: 76,
      closeDate: "Jul 19, 2026",
      status: "pending",
    },
    {
      id: "pos-6",
      marketId: "hurricane-season-above",
      marketQuestion: "Will the 2026 Atlantic hurricane season be above average?",
      side: "YES",
      shares: 50,
      avgPrice: 55,
      currentPrice: 67,
      closeDate: "Nov 30, 2026",
      status: "settled",
      settledPnl: 600,
    },
    {
      id: "pos-7",
      marketId: "trump-approval-50",
      marketQuestion: "Will Trump's approval rating exceed 50% by April 2026?",
      side: "NO",
      shares: 75,
      avgPrice: 70,
      currentPrice: 69,
      closeDate: "Apr 30, 2026",
      status: "settled",
      settledPnl: -82.5,
    },
  ],
  alerts: [
    {
      id: "a1",
      type: "price",
      title: "Fed Rate Market moved +5%",
      subtitle: "YES price jumped to 72¢",
      timestamp: "12m ago",
      group: "Today",
      read: false,
      marketId: "fed-rate-june",
    },
    {
      id: "a2",
      type: "bot-rec",
      title: "New recommendation: BUY YES",
      subtitle: "S&P 500 ATH market — high conviction",
      timestamp: "45m ago",
      group: "Today",
      read: false,
      marketId: "sp500-ath-q2",
    },
    {
      id: "a3",
      type: "odds",
      title: "Bitcoin market odds shifted",
      subtitle: "YES dropped from 62¢ to 58¢",
      timestamp: "1h ago",
      group: "Today",
      read: false,
      marketId: "btc-100k-q2",
    },
    {
      id: "a4",
      type: "resolve",
      title: "Hurricane season market updated",
      subtitle: "New weather data released",
      timestamp: "3h ago",
      group: "Today",
      read: true,
      marketId: "hurricane-season-above",
    },
    {
      id: "a5",
      type: "price",
      title: "NBA Finals odds tightened",
      subtitle: "Celtics YES moved from 40¢ to 44¢",
      timestamp: "Yesterday",
      group: "Yesterday",
      read: true,
      marketId: "nba-finals-celtics",
    },
    {
      id: "a6",
      type: "bot-rec",
      title: "Bot closed position automatically",
      subtitle: "Took profit on World Cup USA market",
      timestamp: "Yesterday",
      group: "Yesterday",
      read: true,
      marketId: "world-cup-usa",
    },
  ],
  botStatus: {
    isScanning: true,
    marketsScanned: 847,
    riskMode: "Balanced",
    autoTrade: false,
    maxPositionSize: 500,
  },
  settings: {
    notifications: {
      priceAlerts: true,
      botRecs: true,
      oddsMovement: true,
      resolving: true,
    },
    accentColor: "blue",
    displayName: "John Doe",
  },
  chatMessages: [
    {
      id: "cm-1",
      sender: "bot",
      text: "Welcome back, John! I've been scanning 847 markets overnight. I found 3 high-conviction opportunities for you today. Want me to walk you through them?",
      timestamp: Date.now() - 60000,
    },
  ],

  // Actions
  setRiskMode: (mode) =>
    set((s) => ({ botStatus: { ...s.botStatus, riskMode: mode } })),
  setAutoTrade: (v) =>
    set((s) => ({ botStatus: { ...s.botStatus, autoTrade: v } })),
  setMaxPositionSize: (v) =>
    set((s) => ({ botStatus: { ...s.botStatus, maxPositionSize: v } })),
  setNotification: (key, v) =>
    set((s) => ({
      settings: {
        ...s.settings,
        notifications: { ...s.settings.notifications, [key]: v },
      },
    })),
  setAccentColor: (c) =>
    set((s) => {
      const colorMap = {
        blue: "#0A84FF",
        green: "#30D158",
        purple: "#BF5AF2",
        orange: "#FF9F0A",
      };
      document.documentElement.style.setProperty("--accent-color", colorMap[c]);
      return { settings: { ...s.settings, accentColor: c } };
    }),
  setDisplayName: (n) =>
    set((s) => ({ settings: { ...s.settings, displayName: n } })),
  addPosition: (p) => set((s) => ({ positions: [...s.positions, p] })),
  removePosition: (id) =>
    set((s) => ({ positions: s.positions.filter((p) => p.id !== id) })),
  addSharesToPosition: (id, shares) =>
    set((s) => ({
      positions: s.positions.map((p) =>
        p.id === id ? { ...p, shares: p.shares + shares } : p
      ),
    })),
  markAlertRead: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) => (a.id === id ? { ...a, read: true } : a)),
    })),
  dismissAlert: (id) =>
    set((s) => ({ alerts: s.alerts.filter((a) => a.id !== id) })),
  addChatMessage: (m) =>
    set((s) => ({ chatMessages: [...s.chatMessages, m] })),
}));
