import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  TrendingUp,
  Brain,
  Zap,
  Bell,
  User,
  Settings,
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
  const unread = useStore((s) => s.alerts.filter((a) => !a.read).length);
  const displayName = useStore((s) => s.settings.displayName);
  const initials = displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  return (
    <aside className="hidden md:flex flex-col w-[220px] h-full bg-bg-surface border-r border-border-subtle shrink-0">
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
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                isActive
                  ? "bg-white/10 text-text-primary"
                  : "text-text-secondary hover:text-text-primary hover:bg-white/5"
              }`
            }
          >
            <item.icon size={18} />
            <span>{item.label}</span>
            {item.to === "/alerts" && unread > 0 && (
              <span className="ml-auto bg-accent-red text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center">
                {unread}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-border-subtle">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-accent-blue flex items-center justify-center text-sm font-bold">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary truncate">
              {displayName}
            </p>
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent-gold/15 text-accent-gold">
              PRO
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
  const unread = useStore((s) => s.alerts.filter((a) => !a.read).length);

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
          <div className="relative">
            <item.icon size={20} />
            {item.to === "/alerts" && unread > 0 && (
              <span className="absolute -top-1 -right-2 bg-accent-red text-white text-[8px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                {unread}
              </span>
            )}
          </div>
          <span>{item.label.split(" ")[0]}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function TopBar() {
  const balance = useStore((s) => s.portfolio.balance);
  const unread = useStore((s) => s.alerts.filter((a) => !a.read).length);
  const location = useLocation();

  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-4 md:px-6 border-b border-border-subtle bg-bg-surface/80 backdrop-blur-xl sticky top-0 z-30">
      <div className="flex items-center gap-2 md:hidden">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs" style={{ background: "var(--accent-color)" }}>
          K
        </div>
        <span className="font-bold">Kalshi-Bot</span>
      </div>
      <div className="hidden md:block" />
      <div className="flex items-center gap-4">
        <span className="font-mono text-sm font-semibold text-text-primary">
          ${balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
        </span>
        <NavLink to="/alerts" className="relative text-text-secondary hover:text-text-primary">
          <Bell size={20} />
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 bg-accent-red text-white text-[8px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
              {unread}
            </span>
          )}
        </NavLink>
      </div>
    </header>
  );
}

export default function Layout() {
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
