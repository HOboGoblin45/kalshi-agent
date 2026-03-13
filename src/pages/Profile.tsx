import { Check } from "lucide-react";
import { useStore } from "../store/useStore";

export default function Profile() {
  const { settings, setAccentColor, agentState, toggleAgent } = useStore();
  const balance = agentState ? agentState.balance + (agentState.poly_balance || 0) : 0;

  const accentColors = [
    { key: "blue" as const, color: "#0A84FF" },
    { key: "green" as const, color: "#30D158" },
    { key: "purple" as const, color: "#BF5AF2" },
    { key: "orange" as const, color: "#FF9F0A" },
  ];

  return (
    <div className="p-2 md:p-2.5 max-w-3xl mx-auto">
      <div className="flex flex-col items-center mb-3">
        <div className="w-12 h-12 rounded-full flex items-center justify-center text-base font-bold mb-1.5" style={{ background: "var(--accent-color)" }}>
          KA
        </div>
        <h2 className="text-base font-bold">Kalshi Agent</h2>
        <span className="mt-1 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent-green/15 text-accent-green">
          {agentState?.enabled ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      <div className="space-y-2">
        <Section title="Agent Control">
          <div className="px-2.5 py-2 flex items-center justify-between">
            <span className="text-xs text-text-primary">Agent Enabled</span>
            <button
              onClick={toggleAgent}
                className={`w-10 h-5.5 rounded-full relative transition-colors ${
                agentState?.enabled ? "bg-accent-green" : "bg-bg-cell"
              }`}
            >
              <span
                className={`absolute top-0.5 w-4.5 h-4.5 rounded-full bg-white shadow transition-transform ${
                  agentState?.enabled ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>
          <Row label="Status" value={agentState?.status || "--"} />
          <Row label="Environment" value={agentState?.environment || "--"} />
          <Row label="Trading Mode" value={agentState?.dry_run ? "DRY-RUN" : "LIVE"} />
          <Row label="Scan Interval" value={agentState ? `${agentState.scan_interval}m` : "--"} />
          <Row label="AI Interval" value={agentState ? `${agentState.ai_interval}m` : "--"} />
        </Section>

        <Section title="Account">
          <Row label="Combined Balance" value={`$${balance.toFixed(2)}`} />
          <Row label="Kalshi Balance" value={agentState ? `$${agentState.balance.toFixed(2)}` : "--"} />
          <Row label="Polymarket Balance" value={agentState ? `$${(agentState.poly_balance || 0).toFixed(2)}` : "--"} />
          <div className="px-2.5 py-2 flex items-center justify-between">
            <span className="text-xs text-text-primary">API Status</span>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${agentState ? "bg-accent-green" : "bg-accent-red"}`} />
              <span className={`text-xs ${agentState ? "text-accent-green" : "text-accent-red"}`}>
                {agentState ? "Connected" : "Disconnected"}
              </span>
            </div>
          </div>
        </Section>

        {agentState && (
          <Section title="Performance">
            <Row label="Win Rate" value={String(agentState.risk.win_rate)} />
            <Row label="Total Trades" value={String(agentState.risk.total)} />
            <Row label="Today P&L" value={String(agentState.risk.day_pnl)} />
            <Row label="Today Trades" value={`${agentState.risk.day_trades}/${agentState.max_daily}`} />
            <Row label="Exposure" value={String(agentState.risk.exposure)} />
            <Row label="Arb Opportunities" value={String(agentState.arb_opps)} />
          </Section>
        )}

        <Section title="Appearance">
          <div className="px-3 py-2.5">
            <p className="text-sm text-text-primary mb-2">Accent Color</p>
            <div className="flex gap-2">
              {accentColors.map((c) => (
                <button
                  key={c.key}
                  onClick={() => setAccentColor(c.key)}
                  className="w-7 h-7 rounded-full border-2 flex items-center justify-center transition-transform"
                  style={{
                    backgroundColor: c.color,
                    borderColor: settings.accentColor === c.key ? "#FFFFFF" : "transparent",
                    transform: settings.accentColor === c.key ? "scale(1.1)" : "scale(1)",
                  }}
                >
                  {settings.accentColor === c.key && <Check size={12} className="text-white" />}
                </button>
              ))}
            </div>
          </div>
        </Section>

        <Section title="About">
          <Row label="Version" value="v6 Cross-Platform Arbitrage" />
          <Row label="Dashboard" value="localhost:9000" />
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-[9px] font-semibold text-text-secondary uppercase tracking-wider mb-1 px-1">{title}</h2>
      <div className="card divide-y divide-border-subtle p-0 overflow-hidden">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  return (
    <div className="w-full px-2.5 py-2 flex items-center justify-between">
      <span className="text-xs text-text-primary">{label}</span>
      {value && <span className="text-[11px] text-text-secondary font-mono">{value}</span>}
    </div>
  );
}
