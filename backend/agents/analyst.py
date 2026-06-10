"""Analysis Agent.

Reads the collected sources and extracts discrete, evidence-backed *draft
claims*. Each draft claim cites the source ids it is drawn from. The analyst
is explicitly instructed to only assert things grounded in the provided
snippets — it must never invent a source id (requirement #18).
"""

from __future__ import annotations

from typing import Any

from services import llm_service
from services.logging_service import log
from workflow.state import GraphState

AGENT = "analyst"

SYSTEM = (
    "You are the Analysis Agent in a traceable research system for accountants "
    "and auditors. You read web-search source snippets and extract atomic, "
    "factual claims. Every claim must cite the ids of the sources that support "
    "it. NEVER invent a source id that is not in the provided list. Return "
    "STRICT JSON only."
)

USER_TMPL = """Question: {question}

Focus areas: {focus}

Sources (id :: title :: snippet):
{sources}

Extract 6-12 atomic claims that help answer the question. Return JSON:
{{
  "claims": [
    {{
      "text": "one clear, self-contained factual statement",
      "source_ids": ["S1", "S3"],
      "category": "finding | risk | control | reliability | other"
    }}
  ]
}}

Rules:
- Only use source ids from the list above.
- Each claim should be supported by at least one source id.
- Prefer specific, decision-useful statements over vague ones.
- Capture differing viewpoints as separate claims (they may conflict).
"""


def _format_sources(sources: list[dict[str, Any]]) -> str:
    lines = []
    for s in sources:
        snippet = (s.get("snippet") or "").replace("\n", " ")[:300]
        lines.append(f"{s['id']} :: {s.get('title', '')} :: {snippet}")
    return "\n".join(lines)


def run(state: GraphState) -> dict[str, Any]:
    run_id = state["run_id"]
    sources = state.get("sources", [])
    valid_ids = {s["id"] for s in sources}

    if not sources:
        log(run_id, AGENT, "No sources to analyse; producing no claims", level="warn")
        return {"draft_claims": []}

    log(run_id, AGENT, f"Analysing {len(sources)} sources")

    try:
        result = llm_service.complete_json(
            SYSTEM,
            USER_TMPL.format(
                question=state["question"],
                focus=", ".join(state.get("focus_areas", [])) or "n/a",
                sources=_format_sources(sources),
            ),
        )
        raw_claims = result.get("claims", [])
    except Exception as exc:  # noqa: BLE001
        log(run_id, AGENT, f"Analysis failed: {exc}", level="error")
        return {"draft_claims": []}

    draft_claims: list[dict[str, Any]] = []
    for i, c in enumerate(raw_claims, start=1):
        text = (c.get("text") or "").strip()
        if not text:
            continue
        # Drop any hallucinated source ids that aren't in our list.
        cited = [sid for sid in c.get("source_ids", []) if sid in valid_ids]
        draft_claims.append({
            "id": f"C{i}",
            "text": text,
            "source_ids": cited,
            "category": c.get("category", "other"),
        })

    log(run_id, AGENT, f"Extracted {len(draft_claims)} draft claims",
        data={"count": len(draft_claims)})
    return {"draft_claims": draft_claims}
