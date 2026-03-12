import { NavLink, Outlet } from "react-router-dom";
import {
  TrendingUp,
  Brain,
  Zap,
  Bell,
  User,
  Settings,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { useStore } from "../store/useStore";

const navItems = [
  { to: "/", icon: TrendingUp, label: "Markets" },
  { to: "/bot", icon: Brain, label: "Bot Intelligence" },
  { to: "/positions", icon: Zap, label: "Live Positions" },
  { to: "/alerts", icon: Bell, label: "Alerts" },
  { to: "/profile", icon: User, label: "Profile" },
];

function Sidebar() {
  return (
    <aside className="hidden md:flex flex-col w-[200px] h-full bg-bg-surface border-r border-border-subtle shrink-0">
      <div className="p-4 flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm" style={{ background: "var(--accent-color)" }}>
          K
        </div>
        <span className="font-bold text-lg">Kalshi-Bot</span>
      </div>

      <nav className="flex-1 px-2 mt-2 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-white/10 text-text-primary"
                  : "text-text-secondary hover:text-text-primary hover:bg-white/5"
              }`
            }
          >
            <item.icon size={18} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-border-subtle">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-accent-blue flex items-center justify-center text-sm font-bold">
            KA
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary truncate">
              Kalshi Agent
            </p>
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent-gold/15 text-accent-gold">
              LIVE
            </span>
          </div>
          <NavLink to="/profile" className="text-text-tertiary hover:text-text-primary">
            <Settings size={16} />
          </NavLink>
        </div>
      </div>
    </aside>
  );
}

function MobileTabBar() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 glass border-t border-border-subtle flex items-center justify-around h-16 px-2">
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 text-[10px] font-medium py-1 px-2 relative ${
              isActive ? "text-accent-blue" : "text-text-secondary"
            }`
          }
        >
          <item.icon size={20} />
          <span>{item.label.split(" ")[0]}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function TopBar() {
  const agentState = useStore((s) => s.agentState);
  const balance = agentState ? agentState.balance + (agentState.poly_balance || 0) : 0;

  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-3 md:px-5 border-b border-border-subtle bg-bg-surface/80 backdrop-blur-xl sticky top-0 z-30">
      <div className="flex items-center gap-2 md:hidden">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs" style={{ background: "var(--accent-color)" }}>
          K
        </div>
        <span className="font-bold">Kalshi-Bot</span>
      </div>
      <div className="hidden md:block" />
      <div className="flex items-center gap-4">
        {agentState && (
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${agentState.enabled ? "bg-accent-green pulse-green" : "bg-accent-red"}`} />
            <span className="text-xs text-text-secondary">{agentState.status}</span>
          </div>
        )}
        <span className="font-mono text-sm font-semibold text-text-primary">
          ${balance.toFixed(2)}
        </span>
      </div>
    </header>
  );
}

function LoadingScreen() {
  return (
    <div className="flex items-center justify-center h-screen bg-bg-base">
      <div className="text-center">
        <Loader2 size={32} className="mx-auto text-accent-blue animate-spin mb-4" />
        <p className="text-text-secondary text-sm">Connecting to agent...</p>
      </div>
    </div>
  );
}

function ErrorScreen({ error }: { error: string }) {
  return (
    <div className="flex items-center justify-center h-screen bg-bg-base">
      <div className="text-center max-w-sm">
        <AlertCircle size={32} className="mx-auto text-accent-red mb-4" />
        <p className="text-text-primary font-semibold mb-2">Agent Not Running</p>
        <p className="text-text-secondary text-sm mb-4">{error}</p>
        <p className="text-text-tertiary text-xs">
          Start the agent with: <code className="bg-bg-elevated px-2 py-1 rounded">python kalshi-agent.py --config kalshi-config.json</code>
        </p>
      </div>
    </div>
  );
}

export default function Layout() {
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const agentState = useStore((s) => s.agentState);

  if (loading && !agentState) return <LoadingScreen />;
  if (error && !agentState) return <ErrorScreen error={error} />;

  return (
    <div className="flex h-screen bg-bg-base text-text-primary">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto pb-20 md:pb-4">
          <Outlet />
        </main>
      </div>
      <MobileTabBar />
    </div>
  );
}
