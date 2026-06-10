# Traceable Multi-Agent Research Assistant

> An auditable, source-grounded research system that turns an open-ended question into a structured answer in which every claim is traceable to the evidence that supports it.

---

## 1. Project Overview

The Traceable Multi-Agent Research Assistant accepts an open-ended question, gathers
evidence from multiple retrieval sources, extracts atomic claims from that evidence,
verifies each claim against its cited sources, detects genuine contradictions, and
synthesises a structured answer. Every supported claim carries the IDs of the sources
that back it, a confidence score, and a full agent log timeline, so the path from
**question → evidence → claim → conclusion** can be reconstructed and audited after the
fact.

The system is built as seven cooperating agents wired into a LangGraph state machine
with a conditional feedback loop: if too much of the extracted evidence is unsupported,
the workflow routes itself back to the research stage before producing a final answer.

It is designed for a domain where being wrong quietly is unacceptable — accounting,
audit, and assurance workpapers — so the architecture favours *defensible* output over
*confident-sounding* output.

---

## 2. Problem Statement

A single LLM call answering an open-ended question has three failure modes that make it
unsuitable for professional use:

1. **It cannot show its work.** The answer is a paragraph, not a chain of evidence. You
   cannot tell which sentence came from which source, or whether any source exists.
2. **It hallucinates citations.** Asked to cite, a model will happily invent source IDs,
   URLs, and quotations that look plausible and are entirely fabricated.
3. **It flattens disagreement.** When sources conflict, a single pass tends to pick one
   side or average them into a vague consensus, hiding the conflict from the reader.

For an auditor assembling a workpaper, all three are disqualifying. The deliverable is
not "an answer" — it is "an answer plus the evidence trail that justifies it." This
project exists to produce that trail.

---

## 3. Why This Project Exists

This was built for the **TruePaper AI multi-agent challenge**. The challenge asks for a
system that can take an open-ended question, coordinate multiple agents to research it,
handle conflicting information, and produce a traceable answer.

The guiding principle throughout was: **a claim the system cannot trace to a source is
treated as a liability, not an asset.** Unsupported claims are never silently dropped to
make the output look cleaner, and they are never presented as fact. They are surfaced as
limitations. This single rule drives most of the architectural decisions below.

---

## 4. Design Goals

| Goal | What it means in practice |
| --- | --- |
| **Traceability first** | Every claim maps to source IDs, a confidence score, and a log line. No orphan claims. |
| **No fabricated evidence** | Source IDs that an agent invents are stripped at every boundary; only real, retrieved sources survive. |
| **Honest about uncertainty** | Conflicts and unsupported claims are reported, not hidden. Reliability is scored, not asserted. |
| **Never crash on degraded inputs** | A dead search provider, a missing LLM key, or unparseable model output degrades gracefully instead of failing the run. |
| **Auditable by construction** | Evaluation metrics are computed deterministically from the verified data, so the scorecard is itself reproducible. |
| **Free, self-hostable stack** | No paid APIs are required. Groq's free tier, DuckDuckGo, the Wikipedia API, and SQLite cover the whole pipeline. |

---

## 5. System Architecture

The system is a two-process application:

- **Backend** — a FastAPI service that owns the agent workflow, persistence, and the
  HTTP API. The agent pipeline runs in a background task; the API exposes the run
  lifecycle and per-run traceability resources.
- **Frontend** — a React + Vite single-page app that starts a run, polls run state once
  per second, and renders a live workflow dashboard followed by the final structured
  answer and its traceability tables.

```
                          ┌──────────────────────────────────────────────┐
                          │                  Frontend (React/Vite)         │
   Browser  ───────────►  │  QuestionInput → LiveWorkflow (1s polling) →   │
                          │  AnswerView · TraceabilityTable · Sources ·    │
                          │  Conflicts · Evaluation · Logs timeline        │
                          └───────────────┬────────────────────────────────┘
                                          │  /api  (Vite dev proxy → :8000)
                          ┌───────────────▼────────────────────────────────┐
                          │                Backend (FastAPI)                │
                          │  POST /api/run  → BackgroundTask                │
                          │  GET  /api/runs/{id}[/logs|/sources|/claims]    │
                          │                                                 │
                          │  ┌───────────────────────────────────────────┐ │
                          │  │      LangGraph workflow (7 agents)          │ │
                          │  └───────────────────────────────────────────┘ │
                          │  Services: llm · search · relevance · cache ·   │
                          │            fallback_sources · logging           │
                          └───────────────┬────────────────────────────────┘
                                          │
                          ┌───────────────▼────────────────────────────────┐
                          │  SQLite: runs · sources · claims · agent_logs · │
                          │          conflicts · evaluations · search_cache │
                          └─────────────────────────────────────────────────┘
                  External (free, key-less): Groq · DuckDuckGo · Wikipedia API
```

### Why a background task instead of a blocking request

The agent pipeline takes tens of seconds. `POST /api/run` creates the run, schedules the
workflow in a FastAPI `BackgroundTask`, and returns `{ run_id, status: "running" }`
immediately. The frontend then polls `GET /api/runs/{run_id}` once per second. Because
every agent writes its logs, sources, and claims to SQLite *as it runs*, polling yields
genuine live progress — the user watches the agents work step by step rather than
staring at a spinner. This avoids WebSockets entirely; simple polling is sufficient for a
single-run-per-user workload and is far easier to operate and reason about.

---

## 6. Agent Architecture

Seven agents, each with a single responsibility. Clear separation is deliberate: each
stage can be reasoned about, logged, and tested in isolation, and a failure in one stage
degrades locally instead of corrupting the whole answer.

| # | Agent | File | Responsibility |
| - | --- | --- | --- |
| 1 | **Planner** | `agents/planner.py` | Decomposes the question into 4–6 search queries and 3–5 focus areas. |
| 2 | **Research** | `agents/researcher.py` | Gathers sources via a multi-tier retrieval strategy, then relevance-filters them. |
| 3 | **Analysis** | `agents/analyst.py` | Extracts 6–12 atomic, source-cited draft claims from the snippets. |
| 4 | **Verifier** | `agents/verifier.py` | Checks each claim against its cited sources, assigns confidence, flags unsupported claims, and decides whether to loop back. |
| 5 | **Conflict Detector** | `agents/conflict_detector.py` | Finds genuine source-vs-source contradictions and rejects pseudo-conflicts. |
| 6 | **Synthesis** | `agents/synthesizer.py` | Classifies the question, reasons across supported claims, and emits the structured report. |
| 7 | **Evaluator** | `agents/evaluator.py` | Computes deterministic evaluation metrics and an overall reliability score. |

### Why multiple agents instead of one prompt

The work splits naturally into stages with different objectives, different prompts, and
different failure handling. Retrieval reliability has nothing to do with claim
verification logic; conflict detection needs a strict, adversarial prompt that would
pollute the synthesis prompt if merged. Separating them gives three concrete benefits:

- **Isolation of failure** — if the analyst returns garbage, the verifier still runs and
  marks the claims unsupported rather than the whole run collapsing.
- **Targeted prompting** — each agent's system prompt is tuned for one job (the verifier
  is told to be strict; the conflict detector is told absence is never a conflict).
- **Traceable boundaries** — each handoff is a place to log, validate, and strip
  hallucinated IDs, which is exactly where traceability is enforced.

---

## 7. Workflow Orchestration

The agents are wired into a **LangGraph `StateGraph`** (`workflow/graph.py`). The graph
is *not* a linear script — it contains a conditional feedback loop after verification:

```
START
  → planner
  → researcher  ◄─────────────────────────┐
  → analyst                                │ (revise)
  → verifier                               │
       │                                   │
       ├── needs_revision? ── yes ─────────┘
       │
       └── no → conflict_detector
                  → synthesizer
                  → evaluator
                  → END
```

The conditional edge (`_route_after_verifier`) reads `needs_revision` from the shared
state. If set, control returns to the researcher for another pass with widened queries;
otherwise it proceeds to conflict detection.

### Why LangGraph was chosen

The defining feature of this workflow is the **conditional loop back to research**. That
is a graph, not a pipeline. Three options were considered:

- **A hand-rolled `while` loop with `if/else`** — works, but the control flow, the shared
  state, and the per-stage logging end up tangled together and hard to extend.
- **A generic agent framework with autonomous tool-calling** — too much non-determinism;
  the whole point is a *fixed, auditable* topology where you can predict and log every
  transition.
- **LangGraph** — models exactly this: named nodes, explicit edges, a typed shared state
  (`GraphState`, a `TypedDict`), and first-class conditional edges. The topology is
  declared in one place and is easy to read and modify.

A `recursion_limit` of 25 is set as a hard safety net, but the real loop control is the
revision budget (`max_revisions = 2`), so the graph cannot loop indefinitely even if the
routing predicate misbehaves.

---

## 8. Traceability Design

Traceability is the core requirement, so it is enforced at every layer rather than bolted
on at the end.

**The chain:** `claim → source_ids → confidence → agent log`.

- Every source retrieved is assigned a stable, run-scoped ID (`S1`, `S2`, …) at the
  moment it survives relevance filtering, and is persisted with its title, URL, snippet,
  originating query, cache flag, and relevance score.
- Every claim is assigned a run-scoped ID (`C1`, `C2`, …) and stores the list of source
  IDs it cites, whether it is supported, and its confidence.
- **Hallucinated IDs are stripped at every boundary.** The analyst drops any cited
  source ID not in the retrieved set; the verifier re-validates against the real source
  IDs; the synthesizer drops any evidence/source ID not in the real source list; the
  conflict detector keeps only source IDs actually attached to supported claims.
- Every agent writes timestamped, structured log lines (`agent_logs`) through a single
  logging service, so the UI can render one ordered timeline of exactly what happened.

The final answer object carries the full traceability payload:
`evidence_backed_claims` (each with source IDs and confidence), `conflicting_information`,
`limitations`, and a `source_list`. Nothing in the answer references a source that does
not exist in that list.

### Why traceability matters

In an audit context the answer is evidence, and evidence that cannot be sourced is
worthless or worse — misleading. A reviewer must be able to click a claim and see the
source, the confidence, and when it was produced. The system is built so that this is
always possible and so that an unsourced statement can never masquerade as a sourced one.

---

## 9. Verification Design

The Verifier (`agents/verifier.py`) is the gatekeeper between "the model said it" and
"the system asserts it."

- For each draft claim, an LLM verdict decides whether the cited snippets genuinely
  support the claim and assigns a confidence (0–1).
- **Citation presence is the hard gate.** Regardless of the LLM verdict, a claim with no
  *valid* source ID is marked unsupported. Unsupported claims are capped at confidence
  0.2 and never dropped — they flow downstream and end up in the answer's limitations.
- If the LLM verdict call fails entirely, the verifier falls back to a pure
  citation-presence check, so verification still happens.
- The verifier computes the **unsupported ratio**. If it exceeds the threshold
  (`UNSUPPORTED_THRESHOLD = 0.4`) *and* revision budget remains, it sets `needs_revision`,
  which routes the graph back to research for more evidence.

### Why verification exists

The analyst is optimised to *extract* claims, which means it will sometimes over-reach or
attach a weak citation. Without a separate, adversarial check, those weak claims would
reach the final answer with the same authority as strong ones. The verifier exists to
break that symmetry: it is explicitly told to be strict, it treats partial or tangential
support as low confidence, and it has the authority to send the whole workflow back for
more evidence. Separating extraction from verification is what lets each be honest about
its own job.

---

## 10. Conflict Detection Design

The Conflict Detector (`agents/conflict_detector.py`) reports only **genuine, direct
contradictions** between two supported claims — where one source supports proposition X
and another explicitly supports NOT X, or one recommends an action and another recommends
the opposite.

The hard part is rejecting **pseudo-conflicts**. The system does this with both a prompt
instruction and a defensive post-check ("validation gauntlet"). A candidate conflict is
rejected when:

- it is incomplete (missing topic or a side);
- either side has no real supporting source (**absence of evidence is not a conflict**);
- both sides cite the same source (a single source is not a source-vs-source contradiction);
- either side's text matches an absence/silence pattern ("does not mention", "no
  evidence", "is silent", "not specified", …) via a dedicated regex;
- the contradiction confidence is below `CONFIDENCE_THRESHOLD = 0.5`.

### Why conflict detection exists

Real-world sources disagree, and that disagreement is itself decision-useful information
an auditor needs to see. But naive conflict detection produces mostly noise: it flags
"Source A says X; Source B doesn't mention X" as a conflict, when that is simply one
source being silent. Treating silence as contradiction would bury the few real conflicts
under dozens of fake ones. The validation gauntlet exists specifically to make the
detector trustworthy — when it reports a conflict, it is a real one.

---

## 11. Evaluation System

The Evaluator (`agents/evaluator.py`) produces a deterministic scorecard from the verified
data — no LLM call — so the report is itself auditable and reproducible.

Metrics computed and persisted:

| Metric | Definition |
| --- | --- |
| `citation_coverage` | % of claims that are supported. |
| `num_claims` / `num_supported` / `num_unsupported` | Raw claim counts. |
| `conflict_count` | Number of genuine conflicts detected. |
| `source_count` | Number of sources used. |
| `reliability_score` | 0–100 blended score (see below). |

**Reliability score** blends citation coverage and average confidence, with a capped
penalty for unresolved conflicts:

```
base    = 0.6 · citation_coverage + 0.4 · avg_confidence      # 0..1
penalty = min(0.15, 0.05 · conflict_count)                    # capped
score   = max(0, base − penalty) · 100                        # 0..100
```

Conflicts *reduce* reliability modestly but never zero it out — unresolved uncertainty is
a legitimate state, not a failure. With zero claims the score is 0.

### Why evaluation metrics were added

"Trust me" is not an acceptable answer in an audit setting. The evaluation system makes
the system's confidence in its own output explicit and quantitative, and because the
metrics are derived deterministically from the verified claims and conflicts, a reviewer
can recompute them by hand and get the same numbers.

---

## 12. Technology Stack

| Layer | Technology | Why |
| --- | --- | --- |
| Orchestration | **LangGraph 0.2.53** (+ `langchain-core`) | Native support for a stateful graph with a conditional loop. |
| API | **FastAPI 0.115** + **Uvicorn** | Async, typed, background tasks, auto Swagger docs. |
| Validation | **Pydantic 2.10** | Typed request/response schemas at the API boundary. |
| LLM | **Groq** (`llama-3.1-8b-instant` default) | Free tier, fast, JSON mode. Configurable model. |
| Web search | **DuckDuckGo** (`duckduckgo-search`) | Free, key-less primary web search. |
| Fallback search | **Wikipedia API** (via `httpx`) | Free, key-less general-knowledge fallback. |
| Persistence | **SQLite** (stdlib `sqlite3`, WAL mode) | Zero-config, dependency-light, auditable. |
| Frontend | **React 18 + Vite 5 + Tailwind 3** | Fast SPA tooling; polling-based live UI. |

The entire stack is free and self-hostable. No paid API key is required to run the system
end to end.

---

## 13. Folder Structure

```
traceable-multi-agents-system/
├── README.md
├── backend/
│   ├── main.py                     # FastAPI app: routes + background run execution
│   ├── database.py                 # SQLite connection, schema (DDL), generic helpers
│   ├── models.py                   # Typed repository functions over the tables
│   ├── schemas.py                  # Pydantic request/response models
│   ├── requirements.txt
│   ├── .env.example
│   ├── agents/
│   │   ├── planner.py              # 1. query/focus-area decomposition
│   │   ├── researcher.py           # 2. multi-tier retrieval + relevance filter
│   │   ├── analyst.py              # 3. atomic claim extraction
│   │   ├── verifier.py             # 4. claim verification + revision routing
│   │   ├── conflict_detector.py    # 5. genuine-contradiction detection
│   │   ├── synthesizer.py          # 6. question classification + structured report
│   │   └── evaluator.py            # 7. deterministic metrics + reliability score
│   ├── workflow/
│   │   ├── graph.py                # LangGraph wiring + conditional edge
│   │   └── state.py                # GraphState (shared TypedDict)
│   └── services/
│       ├── llm_service.py          # Groq JSON-mode calls + retry/parse
│       ├── search_service.py       # DuckDuckGo + Wikipedia + fast-demo mode
│       ├── relevance_service.py    # Semantic/lexical source relevance filtering
│       ├── fallback_sources.py     # Curated trusted-source pack (domain-gated)
│       ├── cache_service.py        # SQLite-backed search cache
│       └── logging_service.py      # Structured, timestamped agent logging
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js              # /api proxy → http://localhost:8000
    ├── tailwind.config.js
    ├── postcss.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx                 # Run lifecycle + 1s polling
        ├── api.js                  # Thin API client
        ├── index.css
        └── components/
            ├── QuestionInput.jsx
            ├── ExampleQuestions.jsx
            ├── LiveWorkflow.jsx     # Live progress bar + step highlight + counts
            ├── LogsTimeline.jsx     # Ordered agent log timeline
            ├── AnswerView.jsx       # Final structured answer
            ├── TraceabilityTable.jsx# Claim → source mapping
            ├── SourcesPanel.jsx
            ├── ConflictSection.jsx
            └── EvaluationCard.jsx
```

---

## 14. Database Schema

SQLite with WAL mode and a single write lock for safe access from the request thread and
the background workflow thread. Tables (see `database.py` for full DDL):

| Table | Purpose | Key columns |
| --- | --- | --- |
| `runs` | One row per research run. | `id`, `question`, `status` (`running`/`completed`/`failed`), `final_answer` (JSON), `error`, timestamps |
| `sources` | Retrieved, relevance-filtered sources. | `id` (`S1…`), `run_id`, `title`, `url`, `snippet`, `query`, `cached`, `relevance` |
| `claims` | Verified claims. | `id` (`C1…`), `run_id`, `text`, `source_ids` (JSON), `supported`, `confidence`, `category` |
| `agent_logs` | Ordered, timestamped agent log timeline. | `run_id`, `agent`, `level` (`info`/`warn`/`error`/`retry`), `message`, `data` (JSON) |
| `conflicts` | Genuine detected contradictions. | `run_id`, `topic`, `summary`, `side_a` + `side_a_sources`, `side_b` + `side_b_sources`, `confidence` |
| `evaluations` | Deterministic scorecard per run. | `run_id`, `citation_coverage`, claim counts, `conflict_count`, `source_count`, `reliability_score` |
| `search_cache` | Cached search results keyed by query. | `query`, `results` (JSON), `created_at` |

All child tables reference `runs(id)` with `ON DELETE CASCADE`. The schema is created on
startup and includes lightweight, idempotent column migrations for older databases.

---

## 15. API Endpoints

Base path: `/api`. Interactive Swagger docs are served at `/docs`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness + whether the LLM key is configured. |
| `POST` | `/api/run` | Create a run, start the workflow in the background, return immediately. |
| `GET` | `/api/runs` | List recent runs (most recent first). |
| `GET` | `/api/runs/{run_id}` | Full run bundle: status, answer, sources, claims, conflicts, logs, evaluation. |
| `GET` | `/api/runs/{run_id}/logs` | Agent log timeline for the run. |
| `GET` | `/api/runs/{run_id}/sources` | Sources panel data for the run. |
| `GET` | `/api/runs/{run_id}/claims` | Claim → source mapping for the run. |

### `POST /api/run`

Request:

```json
{ "question": "Are AI agents reliable enough to draft SMSF audit workpapers?" }
```

Response (returned immediately; the workflow runs in the background):

```json
{ "run_id": "run_a1b2c3d4e5f6", "status": "running" }
```

### `GET /api/runs/{run_id}`

Returns the full bundle. While running, `status` is `"running"` and `logs`/`sources`/
`claims` grow with each poll; on completion `status` becomes `"completed"` (or `"failed"`)
and `final_answer` + `evaluation` are populated. The frontend polls this endpoint every
second and stops when `status` is `completed` or `failed`.

---

## 16. Setup Instructions

### Prerequisites

- Python 3.10+ and Node.js 18+
- A free Groq API key — <https://console.groq.com/keys> (optional: the system degrades
  gracefully without one, but answers are far weaker)

### Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env          # then edit .env and add your GROQ_API_KEY
```

### Frontend

```bash
cd frontend
npm install
```

---

## 17. Environment Variables

Configured in `backend/.env` (copy from `backend/.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | — | Free Groq API key. If unset, LLM-dependent stages fall back gracefully. |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model ID. `llama-3.3-70b-versatile` gives stronger answers (slower). |
| `DATABASE_URL` | `sqlite:///./traceable.db` | SQLite file path (SQLAlchemy-style prefix is stripped). |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed CORS origin for the dev server. |
| `FAST_DEMO_MODE` | `true` | Caps live search (2 queries, 6s timeout, single attempt) so a run stays under ~30s. Set `false` for deeper, slower research. |
| `RELEVANCE_THRESHOLD` | `0.7` | Minimum semantic relevance for a non-priority source to be kept. |

---

## 18. Running Locally

Run the two processes in separate terminals.

**Terminal 1 — backend (port 8000):**

```bash
cd backend
# activate venv first
uvicorn main:app --reload
```

Backend: <http://localhost:8000> · Swagger docs: <http://localhost:8000/docs>

**Terminal 2 — frontend (port 5173):**

```bash
cd frontend
npm run dev
```

Frontend: <http://localhost:5173>. The Vite dev server proxies `/api` to the backend on
port 8000, so no CORS configuration is needed in development.

---

## 19. Example Questions

The system is tuned for accounting / audit / assurance / AI-in-audit questions, where the
curated trusted-source fallback is in-domain:

- "Are AI agents reliable enough to draft SMSF audit workpapers?"
- "What are the key risks of using automated tools to gather audit evidence?"
- "What internal controls should a firm have before adopting AI in the audit?"
- "How does the use of data analytics affect the sufficiency of audit evidence?"
- "Should an audit firm adopt AI-assisted workpaper review this year?"

Out-of-domain questions still run (via live web + Wikipedia), but the curated trusted
fallback pack is skipped because the question does not match the domain gate.

---

## 20. Example Output

The final answer is a structured JSON object. Abridged shape:

```json
{
  "question_type": "decision_support",
  "executive_summary": "AI agents can accelerate workpaper drafting but are not yet reliable enough to do so unsupervised...",
  "direct_answer": "Conditional. AI agents are suitable for first-draft assistance under defined controls, not for unsupervised authoring...",
  "supporting_evidence": [
    { "point": "Audit evidence standards require human evaluation of sufficiency and appropriateness.", "source_ids": ["S1", "S4"] }
  ],
  "risks": ["Over-reliance on unverified model output", "Loss of audit-trail traceability"],
  "controls": ["Human review of every AI-drafted conclusion", "Source-level traceability for each claim"],
  "recommendation": "Adopt AI for drafting under a human-in-the-loop control framework...",
  "recommend_adoption": "Conditional",
  "recommendation_confidence": 0.62,
  "final_conclusion": "On balance, conditional adoption with strong controls is defensible...",
  "evidence_backed_claims": [
    { "id": "C1", "text": "...", "source_ids": ["S1"], "confidence": 0.8, "category": "control" }
  ],
  "conflicting_information": [],
  "limitations": ["2 claim(s) could not be verified against any source and were excluded from the reasoning."],
  "source_list": [{ "id": "S1", "title": "AICPA & CIMA — Audit and Assurance Resources", "url": "https://www.aicpa-cima.com/topic/audit-assurance" }]
}
```

Alongside this, the run exposes the agent log timeline, the per-claim source mapping, the
detected conflicts, and the evaluation scorecard.

---

## 21. Reliability Features

The system is built to keep producing defensible output under degraded conditions.

- **Source relevance filtering** — every candidate source is scored 0–1 (Groq semantic
  judge, with a deterministic lexical-overlap fallback). Sources below the threshold
  (`0.7`) are rejected; authoritative standard-setters (AICPA, PCAOB, IAASB, IFAC, NIST,
  ISO, ISACA, COSO) are always prioritised.
- **Claim verification** — citation presence is a hard gate; unsupported claims are
  flagged and confined to limitations, never presented as fact.
- **Retry logic** — `llm_service.complete_json` retries up to 3 times with an
  increasingly explicit "valid JSON only" nudge when parsing fails; search retries with
  light backoff in normal mode.
- **Fallback retrieval** — three retrieval tiers (DuckDuckGo → Wikipedia → curated
  trusted-source pack) so the system never returns zero sources just because one provider
  is down or rate-limited.
- **Conflict detection** — genuine contradictions are surfaced; pseudo-conflicts (silence,
  shared-source, low-confidence) are filtered by a validation gauntlet.
- **Reliability scoring** — a deterministic 0–100 score blending citation coverage and
  average confidence with a capped conflict penalty.
- **Citation coverage** — the share of claims that survived verification, reported
  explicitly per run.
- **Search caching** — results are cached in SQLite by query; a cache hit skips the
  network entirely, making repeated/demo runs fast and deterministic.

### Why retries were implemented

LLMs in JSON mode still occasionally emit prose, code fences, or truncated objects, and
free search providers intermittently time out or rate-limit. A single attempt would turn
these transient, recoverable failures into run failures. Retries (with a stricter nudge
for the LLM, and bounded backoff for search) absorb the noise that is inherent to free,
shared infrastructure.

### Why fallback retrieval was implemented

Depending on a single search provider means the entire system's correctness depends on
that provider's uptime. DuckDuckGo rate-limits aggressively under load. The Wikipedia
fallback and the curated trusted-source pack guarantee the analyst always has *real,
citable* material to work with, so "the search API was down" never becomes "the audit
answer was empty." Crucially, the fallback sources are real and hand-verified — the
system never fabricates evidence to fill a gap.

---

## 22. Limitations

- **Retrieval breadth** — DuckDuckGo + Wikipedia + a curated pack is solid but not
  exhaustive; paywalled standards text and primary regulatory PDFs are not parsed.
- **Snippet-level analysis** — claims are extracted from search snippets, not full-text
  documents, which bounds the depth of evidence available to the analyst.
- **LLM-dependent stages** — planning, analysis, verification, conflict detection, and
  synthesis rely on the LLM; with no API key these degrade to deterministic fallbacks
  that are markedly weaker.
- **Domain tuning** — prompts and the trusted-source pack are tuned for accounting /
  audit / AI-assurance; out-of-domain questions work but get less specialised guidance.
- **Single-run UX** — the polling model assumes one active run per user; there is no
  multi-tenant queue or auth layer.
- **Fast-demo defaults** — `FAST_DEMO_MODE=true` trades research depth for speed; deeper
  research requires turning it off and accepting longer runs.

---

## 23. Future Improvements

- Full-text retrieval and document parsing (PDF/HTML) instead of snippet-only analysis.
- Pluggable retrieval providers (e.g. an academic or regulatory index) behind the
  existing tiered interface.
- Per-claim drill-down in the UI linking directly to the supporting source passage.
- Persisted run history and comparison across runs of the same question.
- Configurable verification strictness and revision budget per run.
- Authentication, rate limiting, and a job queue for multi-user deployment.
- An automated regression suite of question→expected-trace fixtures.

---

## 24. Screenshots

> Add screenshots to a `docs/screenshots/` directory and reference them here.

| View | Description |
| --- | --- |
| Question entry | `QuestionInput` with example questions. |
| Live workflow | `LiveWorkflow` progress bar (Planner → … → Evaluation), active-step highlight, live source/claim counts, and the streaming log timeline. |
| Structured answer | `AnswerView` with executive summary, direct answer, recommendation, and adoption verdict. |
| Traceability table | `TraceabilityTable` mapping each claim to its sources and confidence. |
| Conflicts & evaluation | `ConflictSection` and `EvaluationCard` (reliability score, citation coverage). |

```
docs/screenshots/
├── 01-question-entry.png
├── 02-live-workflow.png
├── 03-answer.png
├── 04-traceability.png
└── 05-evaluation.png
```

---

## 25. Demo

A complete demo run:

1. Start the backend (`uvicorn main:app --reload`) and frontend (`npm run dev`).
2. Open <http://localhost:5173>.
3. Submit: *"Are AI agents reliable enough to draft SMSF audit workpapers?"*
4. Watch the live workflow advance through the seven stages, with logs such as
   `Planner completed`, `DuckDuckGo failed`, `Fallback activated`, `Sources collected`,
   `Claims extracted`, `Verifier checking citations`, `Unsupported ratio high, routing
   back to research`, `Conflict detector rejected pseudo-conflicts`, `Final answer
   synthesised`, `Evaluation completed`.
5. Review the structured answer, the claim→source traceability table, any conflicts, and
   the reliability scorecard.

> With `FAST_DEMO_MODE=true` (default), a full run completes in roughly 20–30 seconds.

---

## 26. Lessons Learned

- **Traceability has to be enforced at every boundary, not validated at the end.** The
  only robust way to prevent fabricated citations was to strip unknown source IDs at each
  handoff (analyst, verifier, conflict detector, synthesizer) rather than trusting any
  single agent to behave.
- **The hard part of conflict detection is the false positives.** A naive detector
  flagged "silence" as contradiction constantly; the validation gauntlet (absence
  patterns, shared-source rejection, confidence floor) was what made the feature usable.
- **A feedback loop is worth the orchestration cost.** Letting the verifier route back to
  research measurably improved citation coverage on thin-evidence questions — and made
  LangGraph the right tool rather than a hand-rolled loop.
- **Free infrastructure fails often and unpredictably.** Most of the reliability code
  (retries, tiered fallback, caching, fast-demo timeouts) exists because DuckDuckGo and
  free LLM tiers fail in ways a single happy-path call would never survive.
- **Deterministic evaluation beats an LLM grading itself.** Computing the scorecard
  arithmetically from verified data made it reproducible and trustworthy in a way an
  LLM-judged score never could be.

---

## 27. Why This Matches the TruePaper AI Challenge

Each challenge requirement maps directly to a concrete component:

| Challenge requirement | Implementation |
| --- | --- |
| **Clear separation of agents** | Seven single-responsibility agents: Planner, Research, Analysis, Verifier, Conflict Detector, Synthesis, Evaluation (`backend/agents/`). |
| **Workflow orchestration** | LangGraph `StateGraph` with a conditional feedback edge after verification (`workflow/graph.py`). |
| **Open-ended question handling** | Planner decomposes the question into queries + focus areas; Synthesizer classifies it into one of five types to shape the answer. |
| **Multi-source research** | Tiered retrieval: DuckDuckGo → Wikipedia → curated trusted-source pack (`services/search_service.py`, `services/fallback_sources.py`). |
| **Handling conflicting information** | Dedicated Conflict Detector agent that reports genuine contradictions and rejects pseudo-conflicts. |
| **Traceability** | `claim → source_ids → confidence → agent log` mapping, persisted and rendered, with hallucinated IDs stripped at every boundary. |
| **Verification of claims** | Verifier agent with a hard citation gate, confidence scoring, and authority to loop back for more research. |
| **Reliability / self-assessment** | Deterministic Evaluator producing citation coverage and a 0–100 reliability score. |
| **Robustness** | Retries, tiered fallback retrieval, caching, graceful degradation with no API key, and a non-crashing failure path. |
| **Live observability** | Per-run agent log timeline streamed to a polling frontend dashboard. |

---

## 28. License

Released under the **MIT License**. The project depends only on free, openly licensed
components (Groq free tier, DuckDuckGo, the Wikipedia API, and open-source libraries).
