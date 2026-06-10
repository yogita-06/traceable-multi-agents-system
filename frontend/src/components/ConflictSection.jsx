// Conflict analysis section (requirement #4): surfaces disagreements and the
// sources supporting each side. Uncertainty is shown, not hidden.

function SideCard({ label, position, sources, tone }) {
  return (
    <div className={`flex-1 rounded-xl border p-3 ${tone}`}>
      <div className="text-xs font-bold uppercase tracking-wide opacity-70">
        {label}
      </div>
      <p className="mt-1 text-sm">{position || "—"}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {(sources || []).map((s) => (
          <span key={s} className="badge bg-white/70 text-slate-700">
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ConflictSection({ conflicts }) {
  if (!conflicts?.length) {
    return (
      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-800">Conflict Analysis</h3>
        <p className="mt-2 inline-flex items-center gap-2 text-sm text-emerald-700">
          <span className="badge bg-emerald-100 text-emerald-700">✓</span>
          No material conflicts detected.
        </p>
        <p className="mt-2 text-xs text-slate-400">
          A conflict is only reported when two sourced claims directly
          contradict each other. Missing information or silence on a topic is
          not treated as a conflict.
        </p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-800">Conflict Analysis</h3>
        <span className="badge bg-amber-100 text-amber-700">
          {conflicts.length} conflict{conflicts.length > 1 ? "s" : ""}
        </span>
      </div>
      <div className="mt-4 space-y-4">
        {conflicts.map((c, i) => (
          <div key={i} className="rounded-xl border border-amber-200 bg-amber-50/40 p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="font-semibold text-slate-800">{c.topic}</div>
              {typeof c.confidence === "number" && (
                <span className="badge bg-amber-100 text-amber-700">
                  {Math.round(c.confidence * 100)}% contradiction confidence
                </span>
              )}
            </div>
            {c.summary && <p className="mt-1 text-sm text-slate-600">{c.summary}</p>}
            <div className="mt-3 flex flex-col gap-3 sm:flex-row">
              <SideCard
                label="Position A"
                position={c.side_a}
                sources={c.side_a_sources}
                tone="border-emerald-200 bg-emerald-50"
              />
              <SideCard
                label="Position B"
                position={c.side_b}
                sources={c.side_b_sources}
                tone="border-rose-200 bg-rose-50"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
