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
  Target,
} from "lucide-react";
import { useStore } from "../store/useStore";

const navItems = [
  { to: "/", icon: TrendingUp, label: "Markets", cmd: "mkt" },
  { to: "/bot", icon: Brain, label: "Bot Intel", cmd: "bot" },
  { to: "/positions", icon: Zap, label: "Positions", cmd: "pos" },
  { to: "/alerts", icon: Bell, label: "Logs", cmd: "log" },
  { to: "/calibration", icon: Target, label: "Calibrate", cmd: "cal" },
  { to: "/profile", icon: User, label: "Config", cmd: "cfg" },
];

function Sidebar() {
  return (
    <aside className="hidden md:flex flex-col w-[240px] h-full bg-bg-surface border-r border-border-subtle shrink-0">
      <div className="px-4 py-4 border-b border-border-subtle">
        <pre className="text-accent-green text-xs leading-tight term-glow select-none">
{`  _  __   _   _    ___ _  _ ___
 | |/ /  /_\\ | |  / __| || |_ _|
 | ' <  / _ \\| |__\\__ \\ __ || |
 |_|\\_\\/_/ \\_\\____|___/_||_|___|`}
        </pre>
        <div className="text-xs text-text-tertiary mt-1">v6.0 // terminal agent</div>
      </div>

      <nav className="flex-1 px-3 mt-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 text-sm transition-colors hover-glitch ${
                isActive
                  ? "bg-accent-green text-bg-base font-bold"
                  : "text-text-secondary hover:text-accent-green hover:bg-bg-elevated"
              }`
            }
          >
            <span className="text-xs w-4 opacity-60">&gt;</span>
            <item.icon size={18} strokeWidth={2} />
            <span className="uppercase tracking-wider">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-tertiary">user@kalshi:~$</span>
          <span className="text-accent-green animate-cursor">_</span>
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <ModeBadge />
          <NavLink to="/profile" className="text-text-tertiary hover:text-accent-green">
            <Settings size={16} />
          </NavLink>
        </div>
      </div>
    </aside>
  );
}

function MobileTabBar() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-bg-surface border-t border-border-subtle flex items-center justify-around h-14 px-1">
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 text-[9px] font-medium py-1 px-2 uppercase tracking-wider ${
              isActive ? "text-accent-green term-glow" : "text-text-tertiary"
            }`
          }
        >
          <item.icon size={16} strokeWidth={2} />
          <span>{item.cmd}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function TopBar() {
  const agentState = useStore((s) => s.agentState);
  const balance = agentState ? agentState.balance + (agentState.poly_balance || 0) : 0;
  const isDryRun = Boolean(agentState?.dry_run);

  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-4 md:px-5 border-b border-border-subtle bg-bg-surface sticky top-0 z-30">
      <div className="flex items-center gap-2 md:hidden">
        <span className="text-accent-green font-bold text-sm term-glow">KALSHI</span>
      </div>
      <div className="hidden md:flex items-center gap-3 text-xs text-text-tertiary">
        <span>sys://dashboard</span>
        <span className="text-border-subtle">|</span>
        <FeedHealthBar />
      </div>
      <div className="flex items-center gap-4 text-sm">
        {isDryRun && (
          <span className="text-xs font-bold px-2 py-1 border border-accent-gold text-accent-gold">
            DRY-RUN
          </span>
        )}
        {agentState && (
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold ${agentState.enabled ? "text-accent-green pulse-green" : "text-accent-red"}`}>
              {agentState.enabled ? "[OK]" : "[OFF]"}
            </span>
            {agentState.scan_progress && agentState.scan_progress.phase !== "idle" && agentState.scan_progress.pct < 100 ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-accent-green">{agentState.scan_progress.phase}</span>
                <div className="w-20 h-2 bg-bg-elevated border border-border-subtle overflow-hidden">
                  <div
                    className="h-full bg-accent-green transition-all duration-500"
                    style={{ width: `${agentState.scan_progress.pct}%` }}
                  />
                </div>
                <span className="text-xs text-text-tertiary">{agentState.scan_progress.pct}%</span>
              </div>
            ) : (
              <span className="text-xs text-text-tertiary">{agentState.status}</span>
            )}
          </div>
        )}
        <span className="text-base text-accent-green font-bold term-glow">
          ${balance.toFixed(2)}
        </span>
      </div>
    </header>
  );
}

function ModeBadge() {
  const agentState = useStore((s) => s.agentState);
  const isDryRun = Boolean(agentState?.dry_run);
  return (
    <span className={`text-xs font-bold ${isDryRun ? "text-accent-gold" : "text-accent-red animate-pulse"}`}>
      {isDryRun ? "[DRY-RUN]" : "[LIVE]"}
    </span>
  );
}

function FeedHealthBar() {
  const agentState = useStore((s) => s.agentState);
  const feedHealth = agentState?.feed_health;
  const staleCount = agentState?.stale_markets ?? 0;
  if (!feedHealth) return null;

  return (
    <div className="flex items-center gap-3 text-[10px]">
      {Object.entries(feedHealth).map(([venue, info]: [string, any]) => (
        <div key={venue} className="flex items-center gap-1">
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${
            info.status === "healthy" ? "bg-accent-green" :
            info.status === "degraded" ? "bg-accent-gold animate-pulse" :
            "bg-text-tertiary"
          }`} />
          <span className="text-text-tertiary uppercase">{venue}</span>
          {info.errors > 0 && (
            <span className="text-accent-red">({info.errors}err)</span>
          )}
        </div>
      ))}
      {staleCount > 0 && (
        <span className="text-accent-gold">{staleCount} stale</span>
      )}
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="flex items-center justify-center h-screen bg-bg-base">
      <div className="text-center">
        <Loader2 size={24} className="mx-auto text-accent-green animate-spin mb-3" />
        <p className="text-text-secondary text-xs">connecting to agent...</p>
        <span className="text-accent-green animate-cursor">_</span>
      </div>
    </div>
  );
}

function ErrorScreen({ error }: { error: string }) {
  return (
    <div className="flex items-center justify-center h-screen bg-bg-base">
      <div className="text-center max-w-md card">
        <AlertCircle size={24} className="mx-auto text-accent-red mb-3" />
        <p className="text-accent-red font-bold text-sm mb-2">[ERR] AGENT NOT RUNNING</p>
        <p className="text-text-secondary text-xs mb-3">{error}</p>
        <div className="text-[11px] text-text-tertiary bg-bg-elevated border border-border-subtle p-2">
          <span className="text-accent-gold">$</span> python kalshi-agent.py --config kalshi-config.json
        </div>
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
        <main className="flex-1 overflow-y-auto pb-16 md:pb-2">
          <Outlet />
        </main>
      </div>
      <MobileTabBar />
      <div className="crt-overlay" />
    </div>
  );
}
