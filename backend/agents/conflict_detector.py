"""Conflict Detector Agent.

Detects *genuine* contradictions among the supported claims and records each
with the sources backing either side and a confidence score. Conflicts are
surfaced in the final answer rather than hidden (requirement #4).

A conflict is only real when two supported positions directly contradict:
    * Source A supports proposition X and Source B explicitly supports NOT X, or
    * Source A recommends an action and Source B recommends the opposite.

Crucially, *absence* of evidence is never a conflict. Missing information,
silence, "not mentioned" or "no evidence" on one side does NOT contradict a
positive claim on the other side. These pseudo-conflicts are filtered out both
by prompt instruction and by a defensive post-check.
"""

from __future__ import annotations

import re
from typing import Any

import models
from services import llm_service
from services.logging_service import log
from workflow.state import GraphState

AGENT = "conflict_detector"

# Below this contradiction confidence we treat it as "not a real conflict".
CONFIDENCE_THRESHOLD = 0.5

# Phrases that signal "this side is just silence / absence of evidence", which
# must never be treated as a contradicting position.
_ABSENCE_PATTERNS = re.compile(
    r"\b(no\s+mention|not\s+mention|does\s+not\s+(mention|address|discuss|cover|"
    r"state|say)|doesn't\s+(mention|address|discuss)|not\s+(addressed|discussed|"
    r"mentioned|covered|stated|specified|referenced)|silent|silence|lack(s|ing)?"
    r"\s+(of\s+)?(evidence|information|mention|data)|no\s+(evidence|information|"
    r"data)|absence\s+of|unmentioned|not\s+specified)\b",
    re.IGNORECASE,
)

SYSTEM = (
    "You are the Conflict Detector Agent. You report ONLY genuine, direct "
    "contradictions between two supported claims. A conflict exists only when "
    "one source supports a proposition X and another source explicitly supports "
    "NOT X, OR when one source recommends an action and another recommends the "
    "opposite action. Missing information, silence, or 'a source does not "
    "mention it' is NEVER a conflict. Return STRICT JSON only."
)

USER_TMPL = """Claims (id :: text :: sources):
{claims}

Identify ONLY genuine direct contradictions. Return JSON:
{{
  "conflicts": [
    {{
      "topic": "short label for the disagreement",
      "summary": "1-2 sentence neutral description of the direct contradiction",
      "side_a": "explicit position A (proposition X or action A)",
      "side_a_sources": ["S1"],
      "side_b": "explicit OPPOSING position B (NOT X or opposite action)",
      "side_b_sources": ["S2"],
      "confidence": 0.0
    }}
  ]
}}

Strict rules:
- A conflict requires BOTH sides to make an explicit, sourced claim that
  directly contradicts the other.
- side_a and side_b must each be backed by at least one real source id.
- DO NOT create a conflict when one side merely lacks information, is silent,
  or "does not mention" the topic. Absence of evidence is not a contradiction.
- "confidence" (0.0-1.0) = how clearly the two positions directly contradict.
  Use < 0.5 if you are unsure it is a true contradiction.
- If there are no genuine contradictions, return {{"conflicts": []}}.
"""


def _is_absence(text: str) -> bool:
    return bool(_ABSENCE_PATTERNS.search(text or ""))


def run(state: GraphState) -> dict[str, Any]:
    run_id = state["run_id"]
    claims = [c for c in state.get("claims", []) if c["supported"]]
    valid_ids = {c["id"] for c in state.get("claims", [])}
    # Map of real source ids actually attached to supported claims.
    real_source_ids = {sid for c in claims for sid in c["source_ids"]}

    models.clear_conflicts(run_id)

    if len(claims) < 2:
        log(run_id, AGENT, "Too few supported claims to compare; "
            "No material conflicts detected.")
        return {"conflicts": []}

    log(run_id, AGENT, f"Scanning {len(claims)} supported claims for conflicts")

    claims_str = "\n".join(
        f"{c['id']} :: {c['text']} :: {c['source_ids']}" for c in claims
    )
    try:
        result = llm_service.complete_json(SYSTEM, USER_TMPL.format(claims=claims_str))
        raw = result.get("conflicts", [])
    except Exception as exc:  # noqa: BLE001
        log(run_id, AGENT, f"Conflict detection failed: {exc}", level="warn")
        return {"conflicts": []}

    conflicts: list[dict[str, Any]] = []
    rejected = 0
    for c in raw:
        topic = (c.get("topic") or "").strip()
        side_a = (c.get("side_a") or "").strip()
        side_b = (c.get("side_b") or "").strip()
        # Keep only source ids that are real (no hallucinated citations).
        a_sources = [s for s in c.get("side_a_sources", []) if s in real_source_ids]
        b_sources = [s for s in c.get("side_b_sources", []) if s in real_source_ids]
        try:
            confidence = float(c.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        # --- Validation gauntlet: reject pseudo-conflicts -----------------
        reason = None
        if not topic or not side_a or not side_b:
            reason = "incomplete (missing topic/side)"
        elif not a_sources or not b_sources:
            reason = "a side has no real supporting source (absence is not conflict)"
        elif set(a_sources) == set(b_sources):
            reason = ("both sides cite the same source(s); a single source is "
                      "not a source-vs-source contradiction")
        elif _is_absence(side_a) or _is_absence(side_b):
            reason = "one side is silence/absence of evidence, not a contradiction"
        elif confidence < CONFIDENCE_THRESHOLD:
            reason = f"contradiction confidence {confidence:.2f} below threshold"

        if reason:
            rejected += 1
            log(run_id, AGENT, f"Rejected pseudo-conflict {topic!r}: {reason}",
                level="info")
            continue

        conflict = {
            "topic": topic,
            "summary": c.get("summary", ""),
            "side_a": side_a,
            "side_a_sources": a_sources,
            "side_b": side_b,
            "side_b_sources": b_sources,
            "confidence": round(confidence, 2),
        }
        conflicts.append(conflict)
        models.add_conflict(run_id, topic, conflict["summary"], conflict["side_a"],
                            conflict["side_a_sources"], conflict["side_b"],
                            conflict["side_b_sources"], conflict["confidence"])

    if conflicts:
        log(run_id, AGENT,
            f"Detected {len(conflicts)} genuine conflict(s) "
            f"({rejected} pseudo-conflict(s) rejected)",
            data={"count": len(conflicts), "rejected": rejected})
    else:
        log(run_id, AGENT,
            f"No material conflicts detected. ({rejected} pseudo-conflict(s) "
            "rejected)", data={"count": 0, "rejected": rejected})
    return {"conflicts": conflicts}
