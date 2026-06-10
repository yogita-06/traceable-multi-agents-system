"""Source relevance filtering.

Live/fallback search can surface off-topic results (random Wikipedia pages,
stock-market pages, company pages, unrelated entities). This service scores how
semantically relevant each candidate source is to the question and rejects
anything below a minimum threshold (default 0.7).

Scoring strategy (free, no paid APIs):
    * Trusted standard-setters (AICPA, PCAOB, IAASB, IFAC, NIST, ISO) are always
      prioritised — they score 1.0 and are never rejected.
    * Other sources are scored 0..1 by the Groq LLM acting as a semantic
      relevance judge (one batched call). The judge is told to push company
      pages, stock-market pages and unrelated entities toward 0.
    * If the LLM is unavailable, a deterministic lexical-overlap fallback keeps
      the pipeline working.
"""

from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv

from services import llm_service
from services.logging_service import log

load_dotenv()

# Minimum semantic relevance to keep a source (requirement: 0.7).
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.7"))

# Authoritative standard-setters / frameworks to prioritise for audit/accounting
# questions. Matched against the source URL or title.
PRIORITY_PATTERNS = re.compile(
    r"\b(aicpa|aicpa-cima|pcaob|iaasb|ifac|nist|iso(?:/iec)?|isaca|coso)\b"
    r"|aicpa-cima\.com|pcaobus\.org|iaasb\.org|ifac\.org|nist\.gov|iso\.org",
    re.IGNORECASE,
)

# Obvious off-topic Wikipedia/company/markets patterns used as a defensive
# pre-filter for the lexical fallback (the LLM judge handles the general case).
_OFFTOPIC_PATTERNS = re.compile(
    r"\b(stock\s+exchange|share\s+price|war\s+of\s+independence|great\s+depression|"
    r"discography|filmography|football|dynasty|\(film\)|\(album\)|\(song\)|"
    r"national\s+park|mountain|river|monarch|emperor|dynasty)\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "for", "on", "and", "or", "is", "are",
    "what", "how", "why", "when", "which", "should", "can", "do", "does", "use",
    "using", "with", "be", "by", "as", "at", "that", "this", "these", "those",
    "their", "its", "it", "from", "about", "into", "main", "enough",
}


def is_priority_source(url: str, title: str) -> bool:
    blob = f"{url or ''} {title or ''}"
    return bool(PRIORITY_PATTERNS.search(blob))


# ---------------------------------------------------------------------------
# Lexical fallback
# ---------------------------------------------------------------------------
def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _lexical_score(question: str, source: dict[str, Any]) -> float:
    """Token-overlap relevance in 0..1 (recall of question terms)."""
    q = _tokens(question)
    if not q:
        return 0.0
    text = _tokens(f"{source.get('title', '')} {source.get('snippet', '')}")
    if not text:
        return 0.0
    if _OFFTOPIC_PATTERNS.search(f"{source.get('title', '')} {source.get('snippet', '')}"):
        return 0.0
    overlap = len(q & text)
    # Scale: matching ~half of the meaningful question terms is a strong signal.
    return round(min(1.0, overlap / max(1, len(q)) * 1.6), 2)


# ---------------------------------------------------------------------------
# LLM semantic judge
# ---------------------------------------------------------------------------
_JUDGE_SYSTEM = (
    "You are a relevance judge for an audit/accounting research system. You score "
    "how useful each source is for ANSWERING the user's question, from 0.0 to "
    "1.0. Pages about companies, stock markets, unrelated history, geography, "
    "biographies or entities unrelated to the question must score near 0.0. "
    "Sources directly about the question's subject score near 1.0. Return STRICT "
    "JSON only."
)

_JUDGE_TMPL = """Question: {question}

Sources (index :: title :: snippet):
{sources}

Score each source's relevance to answering the question. Return JSON:
{{"scores": [{{"index": 0, "relevance": 0.0}}]}}
"""


def _llm_scores(question: str, sources: list[dict[str, Any]]) -> dict[int, float] | None:
    if not sources or not llm_service.is_configured():
        return None
    listed = "\n".join(
        f"{i} :: {s.get('title', '')} :: {(s.get('snippet', '') or '')[:200]}"
        for i, s in enumerate(sources)
    )
    try:
        res = llm_service.complete_json(
            _JUDGE_SYSTEM, _JUDGE_TMPL.format(question=question, sources=listed))
    except Exception:  # noqa: BLE001
        return None
    scores: dict[int, float] = {}
    for item in res.get("scores", []) or []:
        try:
            idx = int(item.get("index"))
            rel = float(item.get("relevance"))
        except (TypeError, ValueError):
            continue
        scores[idx] = max(0.0, min(1.0, rel))
    return scores or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def filter_sources(question: str, candidates: list[dict[str, Any]], run_id: str,
                   threshold: float = RELEVANCE_THRESHOLD
                   ) -> tuple[list[dict[str, Any]], int]:
    """Return ``(kept, rejected_count)``.

    Each kept source gains a ``relevance`` field. Priority sources are always
    kept; others must meet ``threshold``.
    """
    if not candidates:
        return [], 0

    # Priority sources bypass the threshold entirely.
    priority_idx = {i for i, s in enumerate(candidates)
                    if is_priority_source(s.get("url", ""), s.get("title", ""))}
    to_score = [s for i, s in enumerate(candidates) if i not in priority_idx]

    llm = _llm_scores(question, to_score)
    using = "LLM semantic judge" if llm is not None else "lexical overlap"
    log(run_id, "researcher",
        f"Scoring source relevance via {using} (threshold {threshold})")

    kept: list[dict[str, Any]] = []
    rejected = 0
    score_cursor = 0
    for i, s in enumerate(candidates):
        if i in priority_idx:
            s["relevance"] = 1.0
            kept.append(s)
            continue
        if llm is not None:
            score = llm.get(score_cursor, _lexical_score(question, s))
        else:
            score = _lexical_score(question, s)
        score_cursor += 1
        s["relevance"] = round(score, 2)
        if score >= threshold:
            kept.append(s)
        else:
            rejected += 1
            log(run_id, "researcher",
                f"Rejected low-relevance source ({score:.2f} < {threshold}): "
                f"{(s.get('title') or s.get('url') or '')[:70]}", level="info")

    return kept, rejected
