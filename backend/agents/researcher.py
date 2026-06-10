"""Research Agent.

Gathers sources through a resilient, multi-tier search strategy so the system
never produces 0 sources just because one provider is down:

    Tier 1: DuckDuckGo full web search (with caching + retries).
    Tier 2: Wikipedia API fallback (free, key-less) for general knowledge.
    Tier 3: Curated trusted-source pack for accounting/audit/AI questions
            (services.fallback_sources) — real titles, URLs and snippets.

Tiers 2 and 3 only activate when the live web search returns too few sources.

Collected candidates are then **relevance-filtered** (services.relevance_service):
sources whose semantic relevance to the question is below the threshold (0.7)
are rejected, while authoritative standard-setters (AICPA, PCAOB, IAASB, IFAC,
NIST, ISO) are always prioritised. Only the survivors are assigned a stable
source id (S1, S2, ...), persisted and passed downstream.
"""

from __future__ import annotations

from typing import Any

import models
from services import fallback_sources, relevance_service, search_service
from services.logging_service import log
from workflow.state import GraphState

AGENT = "researcher"


def _dedupe_key(url: str, title: str) -> str:
    return (url or title or "").strip().lower()


def run(state: GraphState) -> dict[str, Any]:
    run_id = state["run_id"]
    question = state["question"]
    queries: list[str] = list(state.get("plan", []))
    revision = state.get("revision_count", 0)

    # Carry forward already-collected (already-filtered) sources across passes.
    sources: list[dict[str, Any]] = list(state.get("sources", []))
    seen = {_dedupe_key(s["url"], s["title"]) for s in sources}
    index = state.get("next_source_index", 1)

    if revision:
        queries = queries + [f"{question} evidence study",
                             f"{question} regulator guidance"]
        log(run_id, AGENT, f"Revision pass #{revision}: widening search", level="retry")

    # Fast-demo mode: cap the number of live queries and fail over quickly so
    # the whole run stays under ~30s even when DuckDuckGo is timing out.
    fast = search_service.is_fast_mode()
    query_limit = search_service.live_query_limit()
    threshold = search_service.fallback_threshold()
    if fast:
        log(run_id, AGENT, "Fast demo mode active", level="info",
            data={"max_live_queries": query_limit, "timeout_s": 6})
    live_queries = queries[:query_limit] if query_limit else queries

    # Candidates are collected in-memory first, then relevance-filtered before
    # any id assignment / persistence.
    candidates: list[dict[str, Any]] = []

    def add_candidate(r: dict[str, Any], query: str, *, cached: bool,
                      tier: str) -> bool:
        key = _dedupe_key(r.get("url", ""), r.get("title", ""))
        if not key or key in seen:
            return False
        seen.add(key)
        candidates.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("snippet", ""),
            "query": query,
            "cached": cached,
            "tier": tier,
        })
        return True

    # ------------------------------------------------------------------
    # Tier 1 — DuckDuckGo (capped to `live_queries` in fast mode)
    # ------------------------------------------------------------------
    if fast and query_limit:
        log(run_id, AGENT, f"DuckDuckGo limited to {query_limit} queries")
    log(run_id, AGENT, f"Researching {len(live_queries)} queries via DuckDuckGo")
    ddg_failures = 0
    for q in live_queries:
        outcome = search_service.search(q, max_results=5)
        if outcome.error:
            ddg_failures += 1
            log(run_id, AGENT, f"DuckDuckGo failed for {q!r}: {outcome.error}",
                level="warn")
            continue
        status = "CACHE HIT" if outcome.cache_hit else "CACHE MISS"
        log(run_id, AGENT,
            f"{status} for {q!r} -> {len(outcome.results)} results",
            data={"cache_hit": outcome.cache_hit, "query": q, "tier": "duckduckgo"})
        for r in outcome.results:
            add_candidate(r, q, cached=outcome.cache_hit, tier="duckduckgo")

    web_count = len(candidates)

    # ------------------------------------------------------------------
    # Fallback tiers — activate immediately when live web search is too thin
    # (fast mode: < 3 candidates; normal: < 5).
    # ------------------------------------------------------------------
    if web_count < threshold:
        if fast:
            log(run_id, AGENT,
                f"Fallback activated after timeout/low results "
                f"({ddg_failures} query failures, {web_count} web sources)",
                level="warn")
        elif ddg_failures:
            log(run_id, AGENT,
                f"DuckDuckGo failed/returned too few results "
                f"({ddg_failures} query failures, {web_count} sources); "
                "activating fallback search", level="warn")
        else:
            log(run_id, AGENT,
                f"Only {web_count} web sources found; activating fallback search",
                level="warn")

        # Tier 2 — Wikipedia API (also capped to `live_queries` in fast mode)
        log(run_id, AGENT, "Fallback tier 2: querying Wikipedia API")
        for q in live_queries:
            wiki = search_service.wikipedia_search(q, max_results=3)
            if wiki.error:
                log(run_id, AGENT, f"Wikipedia fallback failed for {q!r}: "
                    f"{wiki.error}", level="warn")
                continue
            if wiki.results:
                status = "CACHE HIT" if wiki.cache_hit else "CACHE MISS"
                log(run_id, AGENT,
                    f"Wikipedia {status} for {q!r} -> {len(wiki.results)} results",
                    data={"tier": "wikipedia", "query": q,
                          "cache_hit": wiki.cache_hit})
            for r in wiki.results:
                add_candidate(r, q, cached=wiki.cache_hit, tier="wikipedia")

        # Tier 3 — curated trusted-source pack (domain-gated)
        trusted = fallback_sources.get_trusted_sources(question)
        if trusted:
            log(run_id, AGENT,
                f"Fallback tier 3: injecting {len(trusted)} curated trusted "
                "sources for in-domain question",
                data={"tier": "trusted_pack"})
            for r in trusted:
                add_candidate(r, "trusted-source-pack", cached=False,
                              tier="trusted_pack")
        else:
            log(run_id, AGENT,
                "Question not in accounting/audit/AI domain; "
                "skipping curated trusted-source pack")

    # ------------------------------------------------------------------
    # Relevance filtering — reject off-topic sources, prioritise standard-setters
    # ------------------------------------------------------------------
    kept, rejected = relevance_service.filter_sources(question, candidates, run_id)
    log(run_id, AGENT,
        f"Relevance filter kept {len(kept)}/{len(candidates)} candidates "
        f"({rejected} rejected below threshold)",
        data={"kept": len(kept), "rejected": rejected})

    # Assign stable ids + persist only the relevant survivors.
    for c in kept:
        sid = f"S{index}"
        index += 1
        source = {
            "id": sid,
            "title": c["title"],
            "url": c["url"],
            "snippet": c["snippet"],
            "query": c["query"],
            "cached": c["cached"],
            "relevance": c.get("relevance", 0.0),
        }
        sources.append(source)
        models.add_source(run_id, sid, source["title"], source["url"],
                          source["snippet"], source["query"], source["cached"],
                          relevance=source["relevance"])

    log(run_id, AGENT, f"Collected {len(sources)} relevant sources total",
        data={"count": len(sources), "web_candidates": web_count})

    if not sources:
        log(run_id, AGENT,
            "No sufficiently relevant sources found", level="warn")

    return {"sources": sources, "next_source_index": index}
