// Evaluation report card (requirement #7).

function Metric({ label, value, suffix = "" }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <div className="text-2xl font-bold text-slate-800">
        {value}
        <span className="text-base font-medium text-slate-400">{suffix}</span>
      </div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
    </div>
  );
}

function scoreColor(score) {
  if (score >= 75) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-rose-600";
}

export default function EvaluationCard({ evaluation }) {
  if (!evaluation) return null;
  const e = evaluation;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-800">Evaluation Report</h3>
        <div className="text-right">
          <div className={`text-3xl font-extrabold ${scoreColor(e.reliability_score)}`}>
            {e.reliability_score}
            <span className="text-lg text-slate-400">/100</span>
          </div>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Reliability
          </div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Citation coverage" value={e.citation_coverage} suffix="%" />
        <Metric label="Claims" value={e.num_claims} />
        <Metric label="Supported" value={e.num_supported} />
        <Metric label="Unsupported" value={e.num_unsupported} />
        <Metric label="Conflicts" value={e.conflict_count} />
        <Metric label="Sources" value={e.source_count} />
      </div>
    </div>
  );
}
