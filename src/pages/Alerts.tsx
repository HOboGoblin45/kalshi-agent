import { useStore } from "../store/useStore";

export default function Alerts() {
  const agentState = useStore((s) => s.agentState);
  const logs = agentState?.log || [];
  const recentLogs = logs.slice().reverse().slice(0, 60);

  return (
    <div className="p-2 md:p-3 max-w-4xl mx-auto">
      <h1 className="text-sm font-bold uppercase tracking-wider term-glow mb-2">+--- ACTIVITY LOG ---+</h1>

      {agentState && (
        <div className="card mb-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px]">
            <Info label="STATUS" value={agentState.status} />
            <Info label="LAST_SCAN" value={agentState.last_scan} />
            <Info label="NEXT_SCAN" value={agentState.next_scan} />
            <Info label="SCAN_COUNT" value={String(agentState.scan_count)} />
          </div>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="px-2 py-1 border-b border-border-subtle text-[10px] text-text-tertiary uppercase tracking-wider">
          -- stdout ({recentLogs.length} lines) --
        </div>
        <div className="p-2 space-y-0">
          {recentLogs.map((log, i) => (
            <div key={i} className="flex gap-2 py-0.5 text-[11px] hover:bg-bg-elevated">
              <span className="text-text-tertiary text-[10px] shrink-0 w-[52px]">{log.time}</span>
              <span
                className={`break-words ${
                  log.level === "ERROR"
                    ? "text-accent-red"
                    : log.level === "WARNING"
                      ? "text-accent-gold"
                      : "text-text-secondary"
                }`}
              >
                {log.level === "ERROR" && "[ERR] "}
                {log.level === "WARNING" && "[WARN] "}
                {log.msg}
              </span>
            </div>
          ))}
        </div>
      </div>

      {recentLogs.length === 0 && (
        <div className="text-center py-10 text-text-secondary card mt-2">
          <p className="text-xs">[INFO] no activity yet</p>
          <p className="text-[10px] text-text-tertiary mt-1">logs appear once agent starts scanning...</p>
        </div>
      )}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-text-tertiary uppercase">{label}</p>
      <p className="font-bold text-accent-green">{value}</p>
    </div>
  );
}
