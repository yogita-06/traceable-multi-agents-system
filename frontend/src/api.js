// Thin API client.
//
// In local dev, leave VITE_API_BASE_URL unset: BASE falls back to the relative
// "/api" path, which the Vite dev server proxies to the FastAPI backend.
//
// In production (static hosting, no proxy), set VITE_API_BASE_URL at BUILD time
// to the backend's full API base, e.g.
//   https://traceable-multi-agents-system.onrender.com/api
// Vite inlines import.meta.env.VITE_* values at build time.
const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

// Marker error so the UI can show a dedicated "still running" message when a
// request exceeds the client-side timeout (the backend keeps working).
export const TIMEOUT_ERROR = "CLIENT_TIMEOUT";

async function request(path, options = {}, timeoutMs = 0) {
  const controller = new AbortController();
  const timer =
    timeoutMs > 0
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null;

  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options,
    });
  } catch (e) {
    if (e.name === "AbortError") throw new Error(TIMEOUT_ERROR);
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => request("/health"),
  // Starts the run and returns { run_id, status: "running" } immediately.
  // The workflow then runs in the background; the UI polls getRun for progress.
  runQuestion: (question) =>
    request(
      "/run",
      { method: "POST", body: JSON.stringify({ question }) },
      15000
    ),
  // Full run bundle: status, logs, sources, claims, conflicts, evaluation,
  // and (once complete) final_answer. Polled every second while running.
  getRun: (runId) => request(`/runs/${runId}`),
  listRuns: () => request("/runs"),
};
