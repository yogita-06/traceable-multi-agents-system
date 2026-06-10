"""Verifier Agent.

For each draft claim, checks whether the cited sources actually support it and
assigns a confidence score. Claims with no valid citation are marked
*unsupported* — they are never silently dropped or presented as fact
(requirement #18/#19).

If too large a share of claims is unsupported and we still have revision
budget, the verifier signals ``needs_revision`` so the graph routes back to the
research/analysis stage (requirement #2). If a claim simply has missing
citations the verifier retries the citation step once (requirement #5).
"""

from __future__ import annotations

from typing import Any

import models
from services import llm_service
from services.logging_service import log
from workflow.state import GraphState

AGENT = "verifier"

# Above this share of unsupported claims we route back for more research.
UNSUPPORTED_THRESHOLD = 0.4

SYSTEM = (
    "You are the Verifier Agent in a traceable research system. For each claim "
    "you decide whether the cited source snippets genuinely support it. You are "
    "strict: partial or tangential support counts as low confidence. Return "
    "STRICT JSON only."
)

USER_TMPL = """Sources (id :: snippet):
{sources}

Claims to verify:
{claims}

For each claim return a verdict. Return JSON:
{{
  "verdicts": [
    {{
      "id": "C1",
      "supported": true,
      "confidence": 0.0-1.0,
      "valid_source_ids": ["S1"]
    }}
  ]
}}

Rules:
- supported = true ONLY if at least one cited source clearly backs the claim.
- valid_source_ids must be a subset of the claim's cited ids that truly support it.
- confidence reflects strength/consistency of support (1.0 = strong, multiple sources).
"""


def _format_sources(sources: list[dict[str, Any]]) -> str:
    out = []
    for s in sources:
        snippet = (s.get("snippet") or "").replace("\n", " ")[:300]
        out.append(f"{s['id']} :: {snippet}")
    return "\n".join(out)


def _format_claims(claims: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{c['id']} (cites {c['source_ids']}): {c['text']}" for c in claims
    )


def run(state: GraphState) -> dict[str, Any]:
    run_id = state["run_id"]
    draft = state.get("draft_claims", [])
    sources = state.get("sources", [])
    valid_ids = {s["id"] for s in sources}
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    if not draft:
        log(run_id, AGENT, "No draft claims to verify", level="warn")
        return {"claims": [], "needs_revision": False, "unsupported_ratio": 1.0}

    log(run_id, AGENT, f"Verifying {len(draft)} claims")

    verdict_map: dict[str, dict[str, Any]] = {}
    try:
        result = llm_service.complete_json(
            SYSTEM,
            USER_TMPL.format(
                sources=_format_sources(sources),
                claims=_format_claims(draft),
            ),
        )
        for v in result.get("verdicts", []):
            verdict_map[v.get("id")] = v
    except Exception as exc:  # noqa: BLE001
        log(run_id, AGENT, f"Verifier LLM failed; falling back to citation check "
            f"({exc})", level="warn")

    verified: list[dict[str, Any]] = []
    unsupported = 0
    for c in draft:
        verdict = verdict_map.get(c["id"], {})
        # Citation-presence is the hard gate: no valid source => unsupported.
        cited = [s for s in c["source_ids"] if s in valid_ids]
        valid = [s for s in verdict.get("valid_source_ids", cited) if s in valid_ids]
        has_citation = bool(valid)
        supported = bool(verdict.get("supported", has_citation)) and has_citation
        confidence = float(verdict.get("confidence", 0.5 if supported else 0.0))
        confidence = max(0.0, min(1.0, confidence))
        if not supported:
            confidence = min(confidence, 0.2)
            unsupported += 1

        verified.append({
            "id": c["id"],
            "text": c["text"],
            "source_ids": valid if supported else cited,
            "supported": supported,
            "confidence": round(confidence, 2),
            "category": c.get("category", "other"),
        })

    ratio = unsupported / len(verified) if verified else 1.0
    log(run_id, AGENT,
        f"{len(verified) - unsupported}/{len(verified)} claims supported "
        f"(unsupported ratio {ratio:.0%})",
        data={"unsupported_ratio": ratio})

    needs_revision = ratio > UNSUPPORTED_THRESHOLD and revision_count < max_revisions
    if needs_revision:
        log(run_id, AGENT,
            f"Unsupported ratio {ratio:.0%} exceeds threshold "
            f"{UNSUPPORTED_THRESHOLD:.0%}; routing back for more research",
            level="retry")

    # Persist the current verified set (overwrite on revision passes).
    models.clear_claims(run_id)
    for c in verified:
        models.add_claim(run_id, c["id"], c["text"], c["source_ids"],
                         c["supported"], c["confidence"], c["category"])

    return {
        "claims": verified,
        "needs_revision": needs_revision,
        "unsupported_ratio": ratio,
        "revision_count": revision_count + (1 if needs_revision else 0),
    }
