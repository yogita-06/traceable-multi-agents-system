// Sources panel — every collected source with its id, link and cache status.

export default function SourcesPanel({ sources }) {
  if (!sources?.length) {
    return (
      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-800">Sources</h3>
        <p className="mt-2 text-sm text-slate-500">No sources were collected.</p>
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-800">Sources</h3>
        <span className="badge bg-slate-100 text-slate-600">{sources.length} total</span>
      </div>
      <div className="mt-4 space-y-3">
        {sources.map((s) => (
          <div key={s.id} className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-center gap-2">
              <span className="badge bg-brand-100 text-brand-700">{s.id}</span>
              {typeof s.relevance === "number" && s.relevance > 0 && (
                <span className="badge bg-emerald-100 text-emerald-700">
                  {Math.round(s.relevance * 100)}% relevant
                </span>
              )}
              {s.cached && (
                <span className="badge bg-amber-100 text-amber-700">cached</span>
              )}
            </div>
            <a
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="mt-1.5 block text-sm font-semibold text-slate-800 hover:text-brand-600"
            >
              {s.title || s.url}
            </a>
            <p className="mt-1 line-clamp-2 text-xs text-slate-500">{s.snippet}</p>
            <p className="mt-1 truncate text-xs text-slate-400">{s.url}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
