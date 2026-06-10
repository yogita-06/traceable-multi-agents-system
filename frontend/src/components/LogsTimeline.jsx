// Timestamped agent workflow timeline (requirement #3).

const LEVEL_STYLES = {
  info: "bg-brand-500",
  warn: "bg-amber-500",
  error: "bg-rose-500",
  retry: "bg-violet-500",
};

const AGENT_LABELS = {
  orchestrator: "Orchestrator",
  planner: "Planner",
  researcher: "Research",
  analyst: "Analysis",
  verifier: "Verifier",
  conflict_detector: "Conflict Detector",
  synthesizer: "Synthesis",
  evaluator: "Evaluator",
};

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function LogsTimeline({ logs }) {
  if (!logs?.length) return null;

  return (
    <div className="card p-6">
      <h3 className="text-lg font-bold text-slate-800">Agent Workflow Timeline</h3>
      <ol className="mt-4 space-y-0">
        {logs.map((log, i) => (
          <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
            <div className="flex flex-col items-center">
              <span
                className={`mt-1 h-3 w-3 shrink-0 rounded-full ${
                  LEVEL_STYLES[log.level] || "bg-slate-400"
                }`}
              />
              {i < logs.length - 1 && (
                <span className="w-px flex-1 bg-slate-200" />
              )}
            </div>
            <div className="flex-1 pb-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-700">
                  {AGENT_LABELS[log.agent] || log.agent}
                </span>
                <span className="font-mono text-xs text-slate-400">
                  {fmtTime(log.created_at)}
                </span>
                {log.level !== "info" && (
                  <span className="badge bg-slate-100 text-slate-500">
                    {log.level}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-sm text-slate-600">{log.message}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
