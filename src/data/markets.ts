export interface Market {
  id: string;
  question: string;
  category: "Politics" | "Crypto" | "Finance" | "Sports" | "Weather";
  yesPrice: number;
  volume: number;
  closeDate: string;
  conviction: "high" | "medium" | "low" | "watching";
  botEdge: number;
  modelProb: number;
  stats: { last: number; high: number; low: number };
  chartData: {
    "1H": { time: string; price: number }[];
    "1D": { time: string; price: number }[];
    "1W": { time: string; price: number }[];
    "1M": { time: string; price: number }[];
  };
}

const mkChart = (base: number, variance: number, points: number) =>
  Array.from({ length: points }, (_, i) => ({
    time: `${i}`,
    price: Math.max(1, Math.min(99, base + (Math.random() - 0.45) * variance * ((i + 1) / points))),
  }));

export const markets: Market[] = [
  {
    id: "fed-rate-june",
    question: "Will the Fed cut interest rates at the June 2026 FOMC meeting?",
    category: "Finance",
    yesPrice: 72,
    volume: 8_400_000,
    closeDate: "Jun 18, 2026",
    conviction: "high",
    botEdge: 8,
    modelProb: 80,
    stats: { last: 70, high: 74, low: 65 },
    chartData: {
      "1H": mkChart(72, 3, 12),
      "1D": mkChart(72, 8, 24),
      "1W": mkChart(68, 12, 7),
      "1M": mkChart(60, 20, 30),
    },
  },
  {
    id: "btc-100k-q2",
    question: "Will Bitcoin exceed $100,000 before July 1, 2026?",
    category: "Crypto",
    yesPrice: 58,
    volume: 12_300_000,
    closeDate: "Jul 1, 2026",
    conviction: "medium",
    botEdge: 5,
    modelProb: 63,
    stats: { last: 56, high: 62, low: 48 },
    chartData: {
      "1H": mkChart(58, 4, 12),
      "1D": mkChart(58, 10, 24),
      "1W": mkChart(52, 15, 7),
      "1M": mkChart(45, 25, 30),
    },
  },
  {
    id: "trump-approval-50",
    question: "Will Trump's approval rating exceed 50% by April 2026?",
    category: "Politics",
    yesPrice: 31,
    volume: 5_600_000,
    closeDate: "Apr 30, 2026",
    conviction: "low",
    botEdge: -3,
    modelProb: 28,
    stats: { last: 33, high: 38, low: 28 },
    chartData: {
      "1H": mkChart(31, 3, 12),
      "1D": mkChart(31, 6, 24),
      "1W": mkChart(34, 10, 7),
      "1M": mkChart(38, 15, 30),
    },
  },
  {
    id: "nba-finals-celtics",
    question: "Will the Boston Celtics win the 2026 NBA Finals?",
    category: "Sports",
    yesPrice: 44,
    volume: 3_200_000,
    closeDate: "Jun 22, 2026",
    conviction: "medium",
    botEdge: 6,
    modelProb: 50,
    stats: { last: 42, high: 48, low: 38 },
    chartData: {
      "1H": mkChart(44, 3, 12),
      "1D": mkChart(44, 8, 24),
      "1W": mkChart(40, 12, 7),
      "1M": mkChart(35, 18, 30),
    },
  },
  {
    id: "hurricane-season-above",
    question: "Will the 2026 Atlantic hurricane season be above average?",
    category: "Weather",
    yesPrice: 67,
    volume: 1_800_000,
    closeDate: "Nov 30, 2026",
    conviction: "high",
    botEdge: 10,
    modelProb: 77,
    stats: { last: 65, high: 70, low: 58 },
    chartData: {
      "1H": mkChart(67, 2, 12),
      "1D": mkChart(67, 5, 24),
      "1W": mkChart(63, 10, 7),
      "1M": mkChart(55, 18, 30),
    },
  },
  {
    id: "eth-merge-shanghai",
    question: "Will Ethereum surpass $5,000 before Q3 2026?",
    category: "Crypto",
    yesPrice: 39,
    volume: 6_700_000,
    closeDate: "Sep 30, 2026",
    conviction: "watching",
    botEdge: 2,
    modelProb: 41,
    stats: { last: 37, high: 45, low: 32 },
    chartData: {
      "1H": mkChart(39, 4, 12),
      "1D": mkChart(39, 9, 24),
      "1W": mkChart(42, 12, 7),
      "1M": mkChart(48, 20, 30),
    },
  },
  {
    id: "sp500-ath-q2",
    question: "Will the S&P 500 hit a new all-time high in Q2 2026?",
    category: "Finance",
    yesPrice: 81,
    volume: 9_100_000,
    closeDate: "Jun 30, 2026",
    conviction: "high",
    botEdge: 7,
    modelProb: 88,
    stats: { last: 79, high: 83, low: 72 },
    chartData: {
      "1H": mkChart(81, 2, 12),
      "1D": mkChart(81, 6, 24),
      "1W": mkChart(76, 10, 7),
      "1M": mkChart(70, 18, 30),
    },
  },
  {
    id: "dem-house-2026",
    question: "Will Democrats win the House in the 2026 midterm elections?",
    category: "Politics",
    yesPrice: 55,
    volume: 15_200_000,
    closeDate: "Nov 3, 2026",
    conviction: "medium",
    botEdge: 4,
    modelProb: 59,
    stats: { last: 53, high: 58, low: 47 },
    chartData: {
      "1H": mkChart(55, 3, 12),
      "1D": mkChart(55, 7, 24),
      "1W": mkChart(52, 10, 7),
      "1M": mkChart(48, 15, 30),
    },
  },
  {
    id: "world-cup-usa",
    question: "Will the USA advance past the group stage in the 2026 World Cup?",
    category: "Sports",
    yesPrice: 76,
    volume: 4_500_000,
    closeDate: "Jul 19, 2026",
    conviction: "high",
    botEdge: 9,
    modelProb: 85,
    stats: { last: 74, high: 78, low: 68 },
    chartData: {
      "1H": mkChart(76, 2, 12),
      "1D": mkChart(76, 5, 24),
      "1W": mkChart(72, 10, 7),
      "1M": mkChart(65, 16, 30),
    },
  },
  {
    id: "la-heat-wave",
    question: "Will Los Angeles experience a heat wave exceeding 110°F in summer 2026?",
    category: "Weather",
    yesPrice: 42,
    volume: 950_000,
    closeDate: "Sep 22, 2026",
    conviction: "low",
    botEdge: -1,
    modelProb: 41,
    stats: { last: 44, high: 48, low: 36 },
    chartData: {
      "1H": mkChart(42, 3, 12),
      "1D": mkChart(42, 7, 24),
      "1W": mkChart(45, 10, 7),
      "1M": mkChart(50, 14, 30),
    },
  },
];
