"""Synthesis Agent.

Produces a senior-consultant-style answer that *directly answers the question*
rather than merely summarising what each source said.

Pipeline inside this agent:
    1. Classify the question type (research / risk_assessment / recommendation /
       comparison / decision_support) — this shapes the tone and which sections
       carry the most weight.
    2. Reason across the supported claims to derive a defensible conclusion
       (the "reasoning layer") instead of repeating sources one by one.
    3. Emit a structured report: Executive Summary, Direct Answer, Supporting
       Evidence (cited), Risks, Controls, Recommendation (with an adoption
       verdict + confidence), and a Source list.

Traceability is preserved: supporting evidence and the evidence-backed claims
carry source ids, unsupported claims are confined to limitations, and no new
facts are introduced beyond the supported claims.
"""

from __future__ import annotations

from typing import Any

from services import llm_service
from services.logging_service import log
from workflow.state import GraphState

AGENT = "synthesizer"

QUESTION_TYPES = (
    "research", "risk_assessment", "recommendation", "comparison",
    "decision_support",
)

# ---------------------------------------------------------------------------
# Step 1 — question classification
# ---------------------------------------------------------------------------
CLASSIFY_SYSTEM = (
    "You classify an accounting/audit research question into exactly one type. "
    "Return STRICT JSON only."
)

CLASSIFY_TMPL = """Question: {question}

Classify it into exactly one of:
- "research": seeks information/explanation about a topic.
- "risk_assessment": asks what could go wrong / what the risks are.
- "recommendation": asks what should be done / best practices / controls.
- "comparison": weighs options or asks which is better.
- "decision_support": asks whether to adopt/do something (yes/no/should we).

Return JSON: {{"question_type": "<one of the above>", "rationale": "short"}}
"""


def _classify(question: str, run_id: str) -> str:
    """Classify the question type, with a keyword heuristic fallback."""
    try:
        res = llm_service.complete_json(CLASSIFY_SYSTEM,
                                        CLASSIFY_TMPL.format(question=question))
        qtype = (res.get("question_type") or "").strip().lower()
        if qtype in QUESTION_TYPES:
            return qtype
    except Exception as exc:  # noqa: BLE001
        log(run_id, AGENT, f"Question classification LLM failed: {exc}", level="warn")

    q = question.lower()
    if any(w in q for w in ("should we", "should i", "is it", "are ", "can we",
                            "reliable enough", "worth")):
        return "decision_support"
    if any(w in q for w in ("risk", "danger", "threat", "what could go wrong")):
        return "risk_assessment"
    if any(w in q for w in ("recommend", "best practice", "controls", "how should",
                            "what should")):
        return "recommendation"
    if any(w in q for w in (" vs ", "versus", "compare", "better", "difference")):
        return "comparison"
    return "research"


# ---------------------------------------------------------------------------
# Step 2/3 — reasoning + structured synthesis
# ---------------------------------------------------------------------------
SYSTEM = (
    "You are a senior audit & assurance advisory consultant writing a concise, "
    "decision-useful report for an accounting firm's partners. You DIRECTLY "
    "answer the question by REASONING ACROSS the supported claims to reach a "
    "defensible conclusion — you do NOT simply restate what each source says. "
    "You write in a confident, professional consultant voice, are honest about "
    "uncertainty and conflicts, and never invent facts beyond the supported "
    "claims. Return STRICT JSON only."
)

USER_TMPL = """Question: {question}
Question type: {qtype}

Supported claims (id :: text :: sources :: confidence):
{claims}

Detected conflicts:
{conflicts}

Write a senior-consultant report as JSON with EXACTLY these keys:
{{
  "executive_summary": "2-3 sentences: the bottom line up front.",
  "direct_answer": "A direct, decisive answer to the EXACT question asked. "
                   "Reason to a conclusion; do not just summarise sources. "
                   "1-2 short paragraphs.",
  "supporting_evidence": [
    {{"point": "an evidence point that backs the answer", "source_ids": ["S1"]}}
  ],
  "risks": ["the key risks / downsides relevant to the question"],
  "controls": ["key controls or safeguards required before/while adopting"],
  "recommendation": "what the firm should actually do, in consultant voice",
  "recommend_adoption": "Yes | No | Conditional",
  "recommendation_confidence": 0.0,
  "final_conclusion": "one balanced closing paragraph"
}}

Rules:
- Lead with the answer. The "direct_answer" must resolve the question, not hedge
  into a source summary.
- Every supporting_evidence point must cite real source ids from the claims.
- "recommend_adoption": "Yes" (clearly beneficial), "No" (clearly not advisable),
  or "Conditional" (only with the listed controls / caveats). Pick the honest one.
- "recommendation_confidence": 0.0-1.0 — your confidence in the recommendation,
  lower it when evidence is thin or conflicts exist.
- For a "comparison" question, the recommendation states which option wins and why.
- Reflect conflicts and uncertainty rather than hiding them.
- Do not introduce facts not present in the supported claims.
"""


def _fallback_answer(question: str, qtype: str,
                     supported: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "executive_summary": (
            "Automated synthesis was unavailable; this is a provisional, "
            f"evidence-listed response to: {question}"),
        "direct_answer": (
            "A fully reasoned answer could not be generated automatically. The "
            "supported evidence below should be reviewed by a professional "
            "before relying on it."),
        "supporting_evidence": [
            {"point": c["text"], "source_ids": c["source_ids"]}
            for c in supported[:6]
        ],
        "risks": ["Synthesis step failed; conclusions are not reasoned."],
        "controls": ["Apply human professional judgment before acting."],
        "recommendation": "Treat as provisional and seek professional review.",
        "recommend_adoption": "Conditional",
        "recommendation_confidence": 0.2,
        "final_conclusion": "Provisional output — manual review required.",
    }


def _normalise_adoption(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v.startswith("y"):
        return "Yes"
    if v.startswith("n"):
        return "No"
    return "Conditional"


def _clamp01(value: Any, default: float = 0.5) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(1.0, f)), 2)


def run(state: GraphState) -> dict[str, Any]:
    run_id = state["run_id"]
    claims = state.get("claims", [])
    supported = [c for c in claims if c["supported"]]
    unsupported = [c for c in claims if not c["supported"]]
    conflicts = state.get("conflicts", [])
    sources = state.get("sources", [])

    # Step 1 — classify before generating (requirement #2).
    qtype = _classify(state["question"], run_id)
    log(run_id, AGENT, f"Question classified as '{qtype}'", data={"question_type": qtype})

    log(run_id, AGENT, f"Synthesising answer from {len(supported)} supported claims")

    claims_str = "\n".join(
        f"{c['id']} :: {c['text']} :: {c['source_ids']} :: {c['confidence']}"
        for c in supported
    ) or "(none)"
    conflicts_str = "\n".join(
        f"- {c['topic']}: {c.get('summary', '')}" for c in conflicts
    ) or "(none)"

    try:
        body = llm_service.complete_json(
            SYSTEM,
            USER_TMPL.format(question=state["question"], qtype=qtype,
                             claims=claims_str, conflicts=conflicts_str),
        )
    except Exception as exc:  # noqa: BLE001
        log(run_id, AGENT, f"Synthesis LLM failed; using fallback ({exc})",
            level="warn")
        body = _fallback_answer(state["question"], qtype, supported)

    # Normalise the reasoning-layer outputs.
    valid_ids = {s["id"] for s in sources}
    supporting_evidence = []
    for item in body.get("supporting_evidence", []) or []:
        if isinstance(item, dict):
            point = item.get("point") or item.get("text") or ""
            ev_sources = [s for s in (item.get("source_ids") or []) if s in valid_ids]
        else:
            point, ev_sources = str(item), []
        if point:
            supporting_evidence.append({"point": point, "source_ids": ev_sources})

    adoption = _normalise_adoption(body.get("recommend_adoption"))
    rec_conf = _clamp01(body.get("recommendation_confidence"))

    limitations = list(body.get("limitations", []) or [])
    if unsupported:
        limitations.append(
            f"{len(unsupported)} claim(s) could not be verified against any "
            "source and were excluded from the reasoning.")
    if not supported:
        limitations.append(
            "No source-backed claims were available, so the answer is low "
            "confidence.")

    # Build the fully-traceable consultant report.
    final_answer = {
        "question_type": qtype,
        "executive_summary": body.get("executive_summary", ""),
        "direct_answer": body.get("direct_answer", ""),
        "supporting_evidence": supporting_evidence,
        "risks": body.get("risks", []),
        "controls": body.get("controls", []),
        "recommendation": body.get("recommendation", ""),
        "recommend_adoption": adoption,
        "recommendation_confidence": rec_conf,
        "final_conclusion": body.get("final_conclusion", ""),
        # Traceability (preserved for the claim→source table & UI).
        "evidence_backed_claims": [
            {
                "id": c["id"],
                "text": c["text"],
                "source_ids": c["source_ids"],
                "confidence": c["confidence"],
                "category": c["category"],
            }
            for c in supported
        ],
        "conflicting_information": conflicts,
        "limitations": limitations,
        "source_list": [
            {"id": s["id"], "title": s["title"], "url": s["url"]}
            for s in sources
        ],
    }

    log(run_id, AGENT,
        f"Report synthesised: adoption={adoption} "
        f"(confidence {rec_conf}), {len(supporting_evidence)} evidence points",
        data={"question_type": qtype, "recommend_adoption": adoption,
              "recommendation_confidence": rec_conf})
    return {"final_answer": final_answer}
