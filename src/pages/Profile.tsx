import { useStore } from "../store/useStore";

export default function Profile() {
  const { agentState, toggleAgent } = useStore();
  const balance = agentState ? agentState.balance + (agentState.poly_balance || 0) : 0;

  return (
    <div className="p-2 md:p-3 max-w-3xl mx-auto">
      <div className="card mb-3 text-center py-3">
        <pre className="text-accent-green text-[10px] leading-tight term-glow inline-block">
{`  _  __   _   _    ___ _  _ ___
 | |/ /  /_\\ | |  / __| || |_ _|
 | ' <  / _ \\| |__\\__ \\ __ || |
 |_|\\_\\/_/ \\_\\____|___/_||_|___|`}
        </pre>
        <div className="mt-2">
          <span className={`text-[10px] font-bold ${agentState?.enabled ? "text-accent-green" : "text-accent-red"}`}>
            {agentState?.enabled ? "[ACTIVE]" : "[INACTIVE]"}
          </span>
        </div>
      </div>

      <div className="space-y-2">
        <Section title="AGENT CONTROL">
          <div className="px-2 py-1.5 flex items-center justify-between">
            <span className="text-xs text-text-secondary">agent_enabled</span>
            <button
              onClick={toggleAgent}
              className={`text-[10px] font-bold px-2 py-0.5 border transition-colors ${
                agentState?.enabled
                  ? "border-accent-green text-accent-green hover:bg-accent-green hover:text-bg-base"
                  : "border-accent-red text-accent-red hover:bg-accent-red hover:text-bg-base"
              }`}
            >
              {agentState?.enabled ? "[ ON ]" : "[ OFF ]"}
            </button>
          </div>
          <Row label="status" value={agentState?.status || "--"} />
          <Row label="environment" value={agentState?.environment || "--"} />
          <Row label="trading_mode" value={agentState?.dry_run ? "DRY-RUN" : "LIVE"} />
          <Row label="scan_interval" value={agentState ? `${agentState.scan_interval}m` : "--"} />
          <Row label="ai_interval" value={agentState ? `${agentState.ai_interval}m` : "--"} />
        </Section>

        <Section title="ACCOUNT">
          <Row label="combined_bal" value={`$${balance.toFixed(2)}`} />
          <Row label="kalshi_bal" value={agentState ? `$${agentState.balance.toFixed(2)}` : "--"} />
          <Row label="poly_bal" value={agentState ? `$${(agentState.poly_balance || 0).toFixed(2)}` : "--"} />
          <div className="px-2 py-1.5 flex items-center justify-between">
            <span className="text-xs text-text-secondary">api_status</span>
            <span className={`text-[10px] font-bold ${agentState ? "text-accent-green" : "text-accent-red"}`}>
              {agentState ? "[CONNECTED]" : "[DISCONNECTED]"}
            </span>
          </div>
        </Section>

        {agentState && (
          <Section title="PERFORMANCE">
            <Row label="win_rate" value={String(agentState.risk.win_rate)} />
            <Row label="total_trades" value={String(agentState.risk.total)} />
            <Row label="day_pnl" value={String(agentState.risk.day_pnl)} />
            <Row label="day_trades" value={`${agentState.risk.day_trades}/${agentState.max_daily}`} />
            <Row label="exposure" value={String(agentState.risk.exposure)} />
            <Row label="arb_opps" value={String(agentState.arb_opps)} />
          </Section>
        )}

        {agentState?.feed_health && (
          <Section title="FEED HEALTH">
            {Object.entries(agentState.feed_health).map(([venue, info]: [string, any]) => (
              <div key={venue} className="px-2 py-1.5 flex items-center justify-between">
                <span className="text-xs text-text-secondary">{venue}</span>
                <div className="flex items-center gap-2">
                  <span className={`inline-block w-2 h-2 rounded-full ${
                    info.status === "healthy" ? "bg-accent-green" :
                    info.status === "degraded" ? "bg-accent-gold animate-pulse" :
                    "bg-text-tertiary"
                  }`} />
                  <span className={`text-[10px] font-bold ${
                    info.status === "healthy" ? "text-accent-green" :
                    info.status === "degraded" ? "text-accent-gold" :
                    "text-text-tertiary"
                  }`}>
                    [{info.status?.toUpperCase() || "UNKNOWN"}]
                  </span>
                  {info.errors > 0 && (
                    <span className="text-[10px] text-accent-red">{info.errors} err</span>
                  )}
                </div>
              </div>
            ))}
            <Row label="stale_markets" value={String(agentState.stale_markets ?? 0)} />
          </Section>
        )}

        <Section title="ABOUT">
          <Row label="version" value="v7 hardened" />
          <Row label="dashboard" value="localhost:9000" />
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">-- {title} --</div>
      <div className="card divide-y divide-border-subtle p-0 overflow-hidden">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  return (
    <div className="w-full px-2 py-1.5 flex items-center justify-between">
      <span className="text-xs text-text-secondary">{label}</span>
      {value && <span className="text-[11px] text-accent-green font-bold">{value}</span>}
    </div>
  );
}
