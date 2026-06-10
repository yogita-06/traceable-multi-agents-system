"""Shared graph state passed between LangGraph nodes."""

from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    question: str

    # Planner output
    plan: list[str]                  # search queries / sub-questions
    focus_areas: list[str]           # high-level themes to cover

    # Researcher output
    sources: list[dict[str, Any]]    # {id,title,url,snippet,query,cached}
    next_source_index: int           # running counter for S-ids

    # Analyst output (draft claims awaiting verification)
    draft_claims: list[dict[str, Any]]

    # Verifier output (verified claims)
    claims: list[dict[str, Any]]     # {id,text,source_ids,supported,confidence,category}

    # Conflict detector output
    conflicts: list[dict[str, Any]]

    # Synthesis output
    final_answer: dict[str, Any]

    # Evaluator output
    evaluation: dict[str, Any]

    # Control / routing
    revision_count: int              # how many times we've routed back
    max_revisions: int
    needs_revision: bool
    unsupported_ratio: float
    error: str | None
