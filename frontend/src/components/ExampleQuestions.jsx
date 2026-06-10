// Clickable accounting-focused sample questions (requirement #12).

const EXAMPLES = [
  "What are the main risks of using AI agents in audit workpapers?",
  "How can AI agents improve invoice reconciliation for accounting teams?",
  "What controls should firms use when adopting AI for financial document review?",
  "Are AI-generated audit workpapers reliable enough for accounting firms?",
];

export default function ExampleQuestions({ onPick, disabled }) {
  return (
    <div className="mt-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Try an example
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {EXAMPLES.map((q) => (
          <button
            key={q}
            disabled={disabled}
            onClick={() => onPick(q)}
            className="group rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 transition hover:border-brand-500 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="mr-2 text-brand-500 group-hover:text-brand-600">→</span>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
