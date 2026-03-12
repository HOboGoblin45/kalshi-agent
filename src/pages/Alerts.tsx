import { useStore } from "../store/useStore";

export default function Alerts() {
  const agentState = useStore((s) => s.agentState);
  const logs = agentState?.log || [];

  // Show recent log entries as alerts
  const recentLogs = logs.slice().reverse().slice(0, 50);

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl md:text-3xl font-bold mb-4">Activity Log</h1>

      {agentState && (
        <div className="card mb-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-xs text-text-secondary">Status</p>
              <p className="font-semibold">{agentState.status}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">Last Scan</p>
              <p className="font-mono font-semibold">{agentState.last_scan}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">Next Scan</p>
              <p className="font-mono font-semibold">{agentState.next_scan}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">Scans</p>
              <p className="font-mono font-semibold">{agentState.scan_count}</p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-1">
        {recentLogs.map((log, i) => (
          <div
            key={i}
            className="flex gap-3 py-2 px-3 rounded-lg hover:bg-white/5 text-sm"
          >
            <span className="text-text-tertiary font-mono text-xs shrink-0 mt-0.5">
              {log.time}
            </span>
            <span
              className={`text-xs break-words ${
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
        <div className="text-center py-16 text-text-secondary">
          <p className="text-lg font-medium">No activity yet</p>
          <p className="text-sm mt-1">Logs will appear here once the agent starts scanning</p>
        </div>
      )}
    </div>
  );
}
