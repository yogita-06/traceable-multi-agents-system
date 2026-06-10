"""Evaluator Agent.

Computes the evaluation report (requirement #7) and an overall reliability
score, then persists it. The metrics are deterministic — derived directly
from the verified claims, conflicts and sources — so the report is itself
auditable.
"""

from __future__ import annotations

from typing import Any

import models
from services.logging_service import log
from workflow.state import GraphState

AGENT = "evaluator"


def _reliability_score(coverage: float, num_claims: int, avg_conf: float,
                       conflict_count: int) -> float:
    """Blend citation coverage, average confidence and conflict penalty.

    Returns a 0-100 score. Conflicts modestly reduce reliability because they
    signal unresolved uncertainty, but never zero it out (uncertainty is
    legitimate, not failure).
    """
    if num_claims == 0:
        return 0.0
    base = 0.6 * coverage + 0.4 * avg_conf          # 0..1
    penalty = min(0.15, 0.05 * conflict_count)      # cap conflict penalty
    return round(max(0.0, base - penalty) * 100, 1)


def run(state: GraphState) -> dict[str, Any]:
    run_id = state["run_id"]
    claims = state.get("claims", [])
    sources = state.get("sources", [])
    conflicts = state.get("conflicts", [])

    num_claims = len(claims)
    supported = [c for c in claims if c["supported"]]
    num_supported = len(supported)
    num_unsupported = num_claims - num_supported
    coverage = (num_supported / num_claims) if num_claims else 0.0
    avg_conf = (sum(c["confidence"] for c in supported) / num_supported
                if num_supported else 0.0)

    metrics: dict[str, Any] = {
        "citation_coverage": round(coverage * 100, 1),
        "num_claims": num_claims,
        "num_supported": num_supported,
        "num_unsupported": num_unsupported,
        "conflict_count": len(conflicts),
        "source_count": len(sources),
        "reliability_score": _reliability_score(
            coverage, num_claims, avg_conf, len(conflicts)),
    }

    models.set_evaluation(run_id, metrics)
    log(run_id, AGENT,
        f"Evaluation: coverage {metrics['citation_coverage']}%, "
        f"reliability {metrics['reliability_score']}/100",
        data=metrics)
    return {"evaluation": metrics}
