// Structured final answer (requirement #11): executive summary, key findings,
// evidence-backed claims, limitations, conclusion.
//
// The LLM does not always return the exact shape we ask for — a field that
// should be a list of strings sometimes comes back as a list of objects like
// { finding, source } or { claim, source_ids, confidence }. Rendering such an
// object directly as a React child throws "Objects are not valid as a React
// child" and white-screens the app. `renderValue` defensively normalises ANY
// value (string, number, array, object, null) into safe JSX.

function ConfidenceBadge({ value }) {
  const num = typeof value === "number" ? value : parseFloat(value);
  if (Number.isNaN(num)) return null;
  // Accept both 0–1 and 0–100 scales.
  const pct = Math.round(num <= 1 ? num * 100 : num);
  const tone =
    pct >= 70
      ? "bg-emerald-100 text-emerald-700"
      : pct >= 40
      ? "bg-amber-100 text-amber-700"
      : "bg-rose-100 text-rose-700";
  return <span className={`badge ${tone}`}>{pct}% confidence</span>;
}

function AdoptionBadge({ value }) {
  const v = String(value || "").toLowerCase();
  const tone = v.startsWith("y")
    ? "bg-emerald-100 text-emerald-700"
    : v.startsWith("n")
    ? "bg-rose-100 text-rose-700"
    : "bg-amber-100 text-amber-700";
  const label = v.startsWith("y") ? "Yes" : v.startsWith("n") ? "No" : "Conditional";
  return <span className={`badge ${tone} text-sm`}>{label}</span>;
}

const TYPE_LABELS = {
  research: "Research question",
  risk_assessment: "Risk assessment",
  recommendation: "Recommendation",
  comparison: "Comparison",
  decision_support: "Decision support",
};

function SourceBadges({ value }) {
  // `value` may be a single id/string or an array of ids.
  const ids = (Array.isArray(value) ? value : [value]).filter(
    (s) => s !== null && s !== undefined && s !== ""
  );
  if (ids.length === 0) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1">
      {ids.map((s, i) => (
        <span key={i} className="badge bg-brand-100 text-brand-700">
          {String(s)}
        </span>
      ))}
    </span>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-6 first:mt-0">
      <h4 className="text-xs font-bold uppercase tracking-wider text-brand-600">
        {title}
      </h4>
      <div className="mt-2 text-sm leading-relaxed text-slate-700">{children}</div>
    </div>
  );
}

// First non-empty value among the given keys.
function pick(obj, keys) {
  for (const k of keys) {
    if (obj[k] !== null && obj[k] !== undefined && obj[k] !== "") return obj[k];
  }
  return undefined;
}

// Safely turn any value into renderable JSX. Never returns a raw object.
function renderValue(value, key = 0) {
  // 1. null / undefined → nothing
  if (value === null || value === undefined) return null;

  // 2. primitives → render directly
  if (typeof value === "string" || typeof value === "number") {
    return <span>{value}</span>;
  }
  if (typeof value === "boolean") {
    return <span>{value ? "Yes" : "No"}</span>;
  }

  // 3. arrays → render each item as a list
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return (
      <ul className="list-disc space-y-1 pl-5">
        {value.map((item, i) => (
          <li key={i}>{renderValue(item, i)}</li>
        ))}
      </ul>
    );
  }

  // 4. objects → render by recognised shape, never as a raw child
  if (typeof value === "object") {
    // 4a. { finding, source } shape
    const finding = pick(value, ["finding", "text", "claim", "point", "statement"]);
    const sources = pick(value, ["source", "sources", "source_ids", "source_id"]);
    const confidence = pick(value, ["confidence", "score"]);

    if (finding !== undefined) {
      return (
        <span className="inline">
          <span>{renderValue(finding)}</span>
          {sources !== undefined && <SourceBadges value={sources} />}
          {confidence !== undefined && (
            <span className="ml-1 align-middle">
              <ConfidenceBadge value={confidence} />
            </span>
          )}
        </span>
      );
    }

    // 4b. object with only a source/confidence but no finding text
    if (sources !== undefined || confidence !== undefined) {
      return (
        <span className="inline">
          {sources !== undefined && <SourceBadges value={sources} />}
          {confidence !== undefined && <ConfidenceBadge value={confidence} />}
        </span>
      );
    }

    // 4c. unknown shape → render key/value rows instead of crashing
    const entries = Object.entries(value);
    if (entries.length === 0) return null;
    return (
      <div className="space-y-0.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex flex-wrap gap-1 text-sm">
            <span className="font-medium text-slate-500">{k}:</span>
            <span className="text-slate-700">{renderValue(v)}</span>
          </div>
        ))}
      </div>
    );
  }

  // 5. anything else → stringify defensively
  return <span>{String(value)}</span>;
}

// Render a possibly-list field as a bulleted list, normalising each item.
function renderList(value) {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  if (items.length === 0) return null;
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item, i) => (
        <li key={i}>{renderValue(item, i)}</li>
      ))}
    </ul>
  );
}

export default function AnswerView({ answer }) {
  if (!answer || typeof answer !== "object") return null;

  const findings = answer.key_findings;
  const claims = Array.isArray(answer.evidence_backed_claims)
    ? answer.evidence_backed_claims
    : [];
  const limitations = answer.limitations;

  const hasRecommendation =
    answer.recommendation ||
    answer.recommend_adoption ||
    answer.recommendation_confidence !== undefined;

  return (
    <div className="card p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-bold text-slate-800">Final Answer</h3>
        {answer.question_type && (
          <span className="badge bg-slate-100 text-slate-600">
            {TYPE_LABELS[answer.question_type] || answer.question_type}
          </span>
        )}
      </div>

      {answer.executive_summary && (
        <Section title="Executive Summary">{renderValue(answer.executive_summary)}</Section>
      )}

      {answer.direct_answer && (
        <Section title="Direct Answer">
          <div className="rounded-xl border-l-4 border-brand-500 bg-brand-50/60 p-4 text-slate-800">
            {renderValue(answer.direct_answer)}
          </div>
        </Section>
      )}

      {hasRecommendation && (
        <Section title="Recommendation">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap items-center gap-3">
              {answer.recommend_adoption && (
                <span className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Would I recommend adoption?
                  </span>
                  <AdoptionBadge value={answer.recommend_adoption} />
                </span>
              )}
              {answer.recommendation_confidence !== undefined && (
                <span className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Confidence
                  </span>
                  <ConfidenceBadge value={answer.recommendation_confidence} />
                </span>
              )}
            </div>
            {answer.recommendation && (
              <p className="mt-3 text-sm text-slate-700">
                {renderValue(answer.recommendation)}
              </p>
            )}
          </div>
        </Section>
      )}

      {(Array.isArray(answer.supporting_evidence)
        ? answer.supporting_evidence.length > 0
        : !!answer.supporting_evidence) && (
        <Section title="Supporting Evidence">
          {renderList(answer.supporting_evidence)}
        </Section>
      )}

      {(Array.isArray(answer.risks) ? answer.risks.length > 0 : !!answer.risks) && (
        <Section title="Risks">
          <div className="text-slate-700">{renderList(answer.risks)}</div>
        </Section>
      )}

      {(Array.isArray(answer.controls)
        ? answer.controls.length > 0
        : !!answer.controls) && (
        <Section title="Key Controls Required Before Adoption">
          <div className="text-slate-700">{renderList(answer.controls)}</div>
        </Section>
      )}

      {(Array.isArray(findings) ? findings.length > 0 : !!findings) && (
        <Section title="Key Findings">{renderList(findings)}</Section>
      )}

      {claims.length > 0 && (
        <Section title="Evidence-Backed Claims">
          <div className="space-y-3">
            {claims.map((c, i) => {
              // Each claim should be an object, but guard against strings too.
              if (typeof c !== "object" || c === null) {
                return (
                  <div
                    key={i}
                    className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700"
                  >
                    {renderValue(c)}
                  </div>
                );
              }
              const text = pick(c, ["text", "claim", "finding", "statement"]);
              const sourceIds = pick(c, ["source_ids", "sources", "source"]);
              const ids = Array.isArray(sourceIds)
                ? sourceIds
                : sourceIds
                ? [sourceIds]
                : [];
              return (
                <div
                  key={c.id ?? i}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm text-slate-700">
                      {text !== undefined ? renderValue(text) : renderValue(c)}
                    </p>
                    {c.confidence !== undefined && (
                      <ConfidenceBadge value={c.confidence} />
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {c.category && (
                      <span className="text-xs font-medium text-slate-400">
                        {renderValue(c.category)}
                      </span>
                    )}
                    {ids.map((s, j) => (
                      <span key={j} className="badge bg-brand-100 text-brand-700">
                        {String(s)}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {(Array.isArray(limitations) ? limitations.length > 0 : !!limitations) && (
        <Section title="Limitations">
          <div className="text-slate-600">{renderList(limitations)}</div>
        </Section>
      )}

      {answer.final_conclusion && (
        <Section title="Final Conclusion">{renderValue(answer.final_conclusion)}</Section>
      )}
    </div>
  );
}
