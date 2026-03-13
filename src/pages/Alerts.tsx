import { useStore } from "../store/useStore";

export default function Alerts() {
  const agentState = useStore((s) => s.agentState);
  const logs = agentState?.log || [];
  const recentLogs = logs.slice().reverse().slice(0, 60);
  const progress = agentState?.scan_progress;
  const isScanning = progress && progress.phase !== "idle" && progress.pct < 100;

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

      {/* Scan Progress Bar */}
      {isScanning && progress && (
        <div className="card mb-3">
          <div className="flex items-center justify-between text-[10px] mb-1.5">
            <span className="text-accent-green font-bold uppercase tracking-wider">
              {progress.phase}
            </span>
            <span className="text-text-tertiary">
              Phase {progress.current_phase}/{progress.total_phases} -- {progress.pct}%
            </span>
          </div>
          <div className="w-full h-2 bg-bg-elevated border border-border-subtle overflow-hidden">
            <div
              className="h-full bg-accent-green transition-all duration-500 ease-out"
              style={{ width: `${progress.pct}%` }}
            />
          </div>
          {progress.step && (
            <div className="text-[10px] text-text-tertiary mt-1 animate-pulse">
              {progress.step}
            </div>
          )}
        </div>
      )}

      {/* AI Scan Summary */}
      {agentState?.scan_summary && (
        <div className="card mb-3 border-accent-green/30">
          <div className="text-[10px] text-accent-green font-bold uppercase tracking-wider mb-1">
            +--- AI SCAN SUMMARY ---+
          </div>
          <p className="text-[11px] text-text-secondary leading-relaxed whitespace-pre-wrap">
            {agentState.scan_summary}
          </p>
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
