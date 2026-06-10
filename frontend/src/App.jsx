import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import QuestionInput from "./components/QuestionInput.jsx";
import AnswerView from "./components/AnswerView.jsx";
import SourcesPanel from "./components/SourcesPanel.jsx";
import TraceabilityTable from "./components/TraceabilityTable.jsx";
import LogsTimeline from "./components/LogsTimeline.jsx";
import LiveWorkflow from "./components/LiveWorkflow.jsx";
import EvaluationCard from "./components/EvaluationCard.jsx";
import ConflictSection from "./components/ConflictSection.jsx";

function Header() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-lg font-bold text-white">
            T
          </div>
          <div>
            <h1 className="text-base font-bold text-slate-800">
              Traceable Multi-Agent Research Assistant
            </h1>
            <p className="text-xs text-slate-500">
              Audit-ready, source-backed answers · built for the TruePaper AI challenge
            </p>
          </div>
        </div>
        <span className="hidden rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 sm:block">
          Free stack · LangGraph · Groq · DuckDuckGo
        </span>
      </div>
    </header>
  );
}

function ErrorBanner({ message }) {
  return (
    <div className="card border-rose-200 bg-rose-50 p-4">
      <p className="text-sm font-semibold text-rose-700">Something went wrong</p>
      <p className="mt-1 text-sm text-rose-600">{message}</p>
    </div>
  );
}

// Poll interval while a run is in progress (requirement: every 1 second).
const POLL_MS = 1000;

export default function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  // Latest polled bundle while the workflow is still running (live progress).
  const [live, setLive] = useState(null);

  const pollRef = useRef(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  // Clear any in-flight poller if the component unmounts.
  useEffect(() => stopPolling, []);

  const handleRun = async (question) => {
    stopPolling();
    setLoading(true);
    setError(null);
    setResult(null);
    setLive({ status: "running", logs: [], sources: [], claims: [] });

    let runId;
    try {
      const start = await api.runQuestion(question);
      runId = start.run_id;
    } catch (e) {
      setError(e.message);
      setLoading(false);
      setLive(null);
      return;
    }

    // Poll the full run bundle until the workflow finishes.
    const poll = async () => {
      try {
        const data = await api.getRun(runId);
        if (data.status === "completed" || data.status === "failed") {
          stopPolling();
          setLoading(false);
          setLive(null);
          if (data.status === "failed") {
            setError(data.error || "The run failed.");
          }
          setResult(data);
        } else {
          setLive(data); // still running — update live progress
        }
      } catch {
        // Transient network/poll error — keep trying on the next tick.
      }
    };

    poll(); // fetch once immediately so the dashboard fills in quickly
    pollRef.current = setInterval(poll, POLL_MS);
  };

  const reset = () => {
    stopPolling();
    setResult(null);
    setError(null);
    setLive(null);
    setLoading(false);
  };

  const showResults = result && result.status !== "failed";

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-6xl px-4 py-8">
        {/* Home view */}
        {!showResults && (
          <div className="mx-auto max-w-2xl">
            <QuestionInput onSubmit={handleRun} loading={loading} />
            {loading && live && (
              <div className="mt-6 space-y-6">
                <LiveWorkflow run={live} />
                {live.logs?.length > 0 && <LogsTimeline logs={live.logs} />}
              </div>
            )}
            {error && !loading && (
              <div className="mt-6">
                <ErrorBanner message={error} />
              </div>
            )}
          </div>
        )}

        {/* Results view */}
        {showResults && (
          <div>
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Question
                </p>
                <h2 className="mt-1 text-xl font-bold text-slate-800">
                  {result.question}
                </h2>
                <p className="mt-1 font-mono text-xs text-slate-400">
                  run {result.run_id}
                </p>
              </div>
              <button
                onClick={reset}
                className="shrink-0 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-brand-500 hover:text-brand-600"
              >
                ← New question
              </button>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              {/* Main column */}
              <div className="space-y-6 lg:col-span-2">
                <AnswerView answer={result.final_answer} />
                <ConflictSection conflicts={result.conflicts} />
                <TraceabilityTable claims={result.claims} sources={result.sources} />
                <LogsTimeline logs={result.logs} />
              </div>
              {/* Sidebar */}
              <div className="space-y-6">
                <EvaluationCard evaluation={result.evaluation} />
                <SourcesPanel sources={result.sources} />
              </div>
            </div>
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-6xl px-4 py-8 text-center text-xs text-slate-400">
        100% free & open-source stack · React · FastAPI · LangGraph · Groq ·
        DuckDuckGo · SQLite
      </footer>
    </div>
  );
}
