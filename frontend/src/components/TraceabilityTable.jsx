// Claim -> source traceability table (requirement #3). Shows every claim, its
// support status, confidence and the source ids/links backing it.

export default function TraceabilityTable({ claims, sources }) {
  if (!claims?.length) {
    return (
      <div className="card p-6">
        <h3 className="text-lg font-bold text-slate-800">Claim → Source Traceability</h3>
        <p className="mt-2 text-sm text-slate-500">No claims were produced.</p>
      </div>
    );
  }

  const sourceById = Object.fromEntries((sources || []).map((s) => [s.id, s]));

  return (
    <div className="card p-6">
      <h3 className="text-lg font-bold text-slate-800">Claim → Source Traceability</h3>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
              <th className="py-2 pr-3">Claim</th>
              <th className="px-3">Status</th>
              <th className="px-3">Confidence</th>
              <th className="pl-3">Sources</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 align-top">
                <td className="py-3 pr-3">
                  <span className="mr-1 font-mono text-xs text-slate-400">{c.id}</span>
                  {c.text}
                </td>
                <td className="px-3">
                  {c.supported ? (
                    <span className="badge bg-emerald-100 text-emerald-700">
                      supported
                    </span>
                  ) : (
                    <span className="badge bg-rose-100 text-rose-700">
                      unsupported
                    </span>
                  )}
                </td>
                <td className="px-3 font-medium text-slate-700">
                  {Math.round(c.confidence * 100)}%
                </td>
                <td className="pl-3">
                  <div className="flex flex-wrap gap-1">
                    {c.source_ids.length === 0 && (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                    {c.source_ids.map((sid) => {
                      const src = sourceById[sid];
                      return src?.url ? (
                        <a
                          key={sid}
                          href={src.url}
                          target="_blank"
                          rel="noreferrer"
                          title={src.title}
                          className="badge bg-brand-100 text-brand-700 hover:bg-brand-600 hover:text-white"
                        >
                          {sid}
                        </a>
                      ) : (
                        <span key={sid} className="badge bg-slate-100 text-slate-500">
                          {sid}
                        </span>
                      );
                    })}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
