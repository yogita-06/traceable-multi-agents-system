"""LangGraph workflow wiring the seven agents into a stateful graph.

Topology (not a linear script — it contains a conditional feedback loop):

    START
      -> planner
      -> researcher  <-------------------+
      -> analyst                         |
      -> verifier                        |
           |                             |
           |-- needs_revision? --yes-----+   (back to researcher)
           |
           +-- no --> conflict_detector
                          -> synthesizer
                          -> evaluator
                          -> END

The conditional edge after the verifier implements requirement #2: if too many
claims are unsupported and revision budget remains, the graph routes back to
the research/analysis stage to gather more evidence; otherwise it proceeds to
conflict detection and synthesis.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents import (analyst, conflict_detector, evaluator, planner, researcher,
                    synthesizer, verifier)
from services.logging_service import log
from workflow.state import GraphState


def _route_after_verifier(state: GraphState) -> str:
    """Conditional edge: loop back to research or continue to synthesis."""
    if state.get("needs_revision"):
        return "revise"
    return "continue"


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("planner", planner.run)
    graph.add_node("researcher", researcher.run)
    graph.add_node("analyst", analyst.run)
    graph.add_node("verifier", verifier.run)
    graph.add_node("conflict_detector", conflict_detector.run)
    graph.add_node("synthesizer", synthesizer.run)
    graph.add_node("evaluator", evaluator.run)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "analyst")
    graph.add_edge("analyst", "verifier")

    # Conditional feedback loop after verification.
    graph.add_conditional_edges(
        "verifier",
        _route_after_verifier,
        {"revise": "researcher", "continue": "conflict_detector"},
    )

    graph.add_edge("conflict_detector", "synthesizer")
    graph.add_edge("synthesizer", "evaluator")
    graph.add_edge("evaluator", END)

    return graph.compile()


# Compile once at import time and reuse.
COMPILED_GRAPH = build_graph()


def run_workflow(run_id: str, question: str, max_revisions: int = 2) -> GraphState:
    """Execute the full agent workflow synchronously and return final state."""
    initial: GraphState = {
        "run_id": run_id,
        "question": question,
        "sources": [],
        "next_source_index": 1,
        "revision_count": 0,
        "max_revisions": max_revisions,
        "needs_revision": False,
        "error": None,
    }
    log(run_id, "orchestrator", "Workflow started")
    # recursion_limit guards against unexpected loops; revision budget is the
    # real control, but this is a hard safety net.
    final_state = COMPILED_GRAPH.invoke(initial, {"recursion_limit": 25})
    log(run_id, "orchestrator", "Workflow finished")
    return final_state
