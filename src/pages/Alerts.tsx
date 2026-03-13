import { useStore } from "../store/useStore";

export default function Alerts() {
  const agentState = useStore((s) => s.agentState);
  const logs = agentState?.log || [];
  const recentLogs = logs.slice().reverse().slice(0, 80);

  return (
    <div className="p-4 md:p-5 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Activity Log</h1>

      {agentState && (
        <div className="card mb-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <Info label="Status" value={agentState.status} />
            <Info label="Last Scan" value={agentState.last_scan} mono />
            <Info label="Next Scan" value={agentState.next_scan} mono />
            <Info label="Scans" value={String(agentState.scan_count)} mono />
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {recentLogs.map((log, i) => (
          <div key={i} className="flex gap-3 py-2 px-3 rounded-lg hover:bg-white/5 text-sm border border-transparent hover:border-border-subtle">
            <span className="text-text-tertiary font-mono text-xs shrink-0 mt-0.5">{log.time}</span>
            <span
              className={`break-words ${
                log.level === "ERROR"
                  ? "text-accent-red"
                  : log.level === "WARNING"
                    ? "text-accent-gold"
                    : "text-text-secondary"
              }`}
            >
              {log.msg}
            </span>
          </div>
        ))}
      </div>

      {recentLogs.length === 0 && (
        <div className="text-center py-10 text-text-secondary">
          <p className="text-base font-medium">No activity yet</p>
          <p className="text-sm mt-1">Logs appear here once the agent starts scanning.</p>
        </div>
      )}
    </div>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={`${mono ? "font-mono" : ""} font-semibold`}>{value}</p>
    </div>
  );
}
