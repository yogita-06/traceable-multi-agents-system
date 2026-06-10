import { useState } from "react";
import ExampleQuestions from "./ExampleQuestions.jsx";

// Home-page question input with submit + example shortcuts.
export default function QuestionInput({ onSubmit, loading }) {
  const [value, setValue] = useState("");

  const submit = (e) => {
    e?.preventDefault();
    const q = value.trim();
    if (q.length >= 5) onSubmit(q);
  };

  return (
    <div className="card p-6 sm:p-8">
      <form onSubmit={submit}>
        <label className="block text-sm font-semibold text-slate-700">
          Ask an open-ended research question
        </label>
        <p className="mt-1 text-sm text-slate-500">
          The multi-agent system will plan, research, verify, and synthesise a
          fully source-backed answer.
        </p>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
          }}
          rows={3}
          disabled={loading}
          placeholder="e.g. What controls should firms use when adopting AI for financial document review?"
          className="mt-4 w-full resize-none rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-slate-50"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className="text-xs text-slate-400">⌘/Ctrl + Enter to run</span>
          <button
            type="submit"
            disabled={loading || value.trim().length < 5}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Running agents…" : "Run research"}
          </button>
        </div>
      </form>

      <ExampleQuestions onPick={(q) => onSubmit(q)} disabled={loading} />
    </div>
  );
}
