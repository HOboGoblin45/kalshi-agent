import { useStore } from "../store/useStore";

export default function Alerts() {
  const agentState = useStore((s) => s.agentState);
  const logs = agentState?.log || [];
  const recentLogs = logs.slice().reverse().slice(0, 60);

  return (
    <div className="p-2 md:p-2.5 max-w-4xl mx-auto">
      <h1 className="text-base md:text-lg font-bold mb-2">Activity Log</h1>

      {agentState && (
        <div className="card mb-2.5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
            <Info label="Status" value={agentState.status} />
            <Info label="Last Scan" value={agentState.last_scan} mono />
            <Info label="Next Scan" value={agentState.next_scan} mono />
            <Info label="Scans" value={String(agentState.scan_count)} mono />
          </div>
        </div>
      )}

      <div className="space-y-0.5">
        {recentLogs.map((log, i) => (
          <div key={i} className="flex gap-1.5 py-1 px-2 rounded-md hover:bg-white/5 text-[11px]">
            <span className="text-text-tertiary font-mono text-[10px] shrink-0 mt-0.5">{log.time}</span>
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
          <p className="text-sm font-medium">No activity yet</p>
          <p className="text-xs mt-1">Logs appear here once the agent starts scanning.</p>
        </div>
      )}
    </div>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[10px] text-text-secondary">{label}</p>
      <p className={`${mono ? "font-mono" : ""} font-semibold`}>{value}</p>
    </div>
  );
}
