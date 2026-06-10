// Live agent-workflow dashboard shown while a run is in progress.
// Replaces the old static "Agents are researching…" spinner card with a
// real-time view driven by polling GET /api/runs/{run_id} once a second.

// The seven workflow stages, in execution order. `key` matches the `agent`
// field written by the backend logging service.
const STEPS = [
  { key: "planner", label: "Planner" },
  { key: "researcher", label: "Research" },
  { key: "analyst", label: "Analysis" },
  { key: "verifier", label: "Verifier" },
  { key: "conflict_detector", label: "Conflict" },
  { key: "synthesizer", label: "Synthesis" },
  { key: "evaluator", label: "Evaluation" },
];

const STEP_INDEX = Object.fromEntries(STEPS.map((s, i) => [s.key, i]));

export default function LiveWorkflow({ run }) {
  const logs = run?.logs ?? [];
  const sources = run?.sources ?? [];
  const claims = run?.claims ?? [];

  // The currently active stage is the one that logged most recently. If the
  // latest log is from a non-stage agent (e.g. "orchestrator"), fall back to
  // the furthest stage any log has reached so the bar never jumps backwards.
  let furthest = -1;
  for (const l of logs) {
    const idx = STEP_INDEX[l.agent];
    if (idx !== undefined && idx > furthest) furthest = idx;
  }
  const lastAgent = logs.length ? logs[logs.length - 1].agent : null;
  const lastIdx = lastAgent != null ? STEP_INDEX[lastAgent] : undefined;
  const currentIndex = lastIdx !== undefined ? lastIdx : furthest;

  const latest = logs.length ? logs[logs.length - 1] : null;
  const pct =
    currentIndex >= 0 ? ((currentIndex + 1) / STEPS.length) * 100 : 4;

  return (
    <div className="card p-6">
      {/* Heading + latest log message */}
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 shrink-0 animate-spin rounded-full border-4 border-brand-100 border-t-brand-600" />
        <div className="min-w-0">
          <p className="font-semibold text-slate-700">Agents are working…</p>
          <p className="truncate text-sm text-slate-500">
            {latest ? latest.message : "Starting workflow…"}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-6 h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-brand-600 transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Stepper: Planner → Research → … → Evaluation */}
      <ol className="mt-3 flex items-start justify-between gap-1">
        {STEPS.map((s, i) => {
          const done = i < currentIndex;
          const active = i === currentIndex;
          return (
            <li
              key={s.key}
              className="flex flex-1 flex-col items-center gap-1 text-center"
            >
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                  active
                    ? "bg-brand-600 text-white ring-4 ring-brand-100"
                    : done
                    ? "bg-brand-500 text-white"
                    : "bg-slate-200 text-slate-400"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={`text-[10px] font-medium leading-tight ${
                  active
                    ? "text-brand-700"
                    : done
                    ? "text-slate-600"
                    : "text-slate-400"
                }`}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>

      {/* Live counts */}
      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-center">
          <p className="text-2xl font-bold text-slate-800">{sources.length}</p>
          <p className="text-xs text-slate-500">Sources collected</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-center">
          <p className="text-2xl font-bold text-slate-800">{claims.length}</p>
          <p className="text-xs text-slate-500">Claims extracted</p>
        </div>
      </div>
    </div>
  );
}
