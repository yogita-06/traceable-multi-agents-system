"""Planner Agent.

Decomposes the user's open-ended question into a focused research plan: a
small set of web-search queries plus the high-level focus areas the final
workpaper-style answer should cover. Tailored to an accounting / audit /
compliance context (the TruePaper AI domain).
"""

from __future__ import annotations

from typing import Any

from services import llm_service
from services.logging_service import log
from workflow.state import GraphState

AGENT = "planner"

SYSTEM = (
    "You are the Planner Agent in a traceable multi-agent research system used "
    "by accountants and auditors (think SMSF audit workpapers). Given an "
    "open-ended question, you break it into a concrete research plan. "
    "Return STRICT JSON only."
)

USER_TMPL = """Question: {question}

Produce a research plan as JSON with this exact shape:
{{
  "focus_areas": ["3-5 short themes the final answer must cover"],
  "queries": ["4-6 specific web search queries that will surface evidence"]
}}

Rules:
- Queries should be specific and varied (definitions, risks, controls,
  regulator/standards guidance, real-world examples).
- Bias queries toward authoritative accounting/audit/compliance sources.
- Keep each query under 12 words.
"""


def _fallback_plan(question: str) -> dict[str, Any]:
    """Deterministic plan if the LLM is unavailable — keeps the run alive."""
    return {
        "focus_areas": ["overview", "risks", "controls", "reliability"],
        "queries": [
            question,
            f"{question} risks",
            f"{question} controls best practices",
            f"{question} audit accounting guidance",
        ],
    }


def run(state: GraphState) -> dict[str, Any]:
    run_id, question = state["run_id"], state["question"]
    log(run_id, AGENT, f"Planning research for: {question!r}")

    try:
        plan = llm_service.complete_json(SYSTEM, USER_TMPL.format(question=question))
        queries = [q.strip() for q in plan.get("queries", []) if q.strip()]
        focus = [f.strip() for f in plan.get("focus_areas", []) if f.strip()]
        if not queries:
            raise ValueError("planner returned no queries")
    except Exception as exc:  # noqa: BLE001
        log(run_id, AGENT, f"LLM planning failed ({exc}); using fallback plan",
            level="warn")
        fb = _fallback_plan(question)
        queries, focus = fb["queries"], fb["focus_areas"]

    log(run_id, AGENT, f"Plan ready: {len(queries)} queries, {len(focus)} focus areas",
        data={"queries": queries, "focus_areas": focus})
    return {"plan": queries, "focus_areas": focus}
