"""Multi-tier web search with caching, retries and a fast-demo mode.

Search reliability strategy (never depends on a single provider):

    1. DuckDuckGo  — primary, free, key-less full web search.
    2. Wikipedia   — free, key-less API fallback for general knowledge.
    3. Trusted pack — curated authoritative sources (handled by the researcher
                      via ``services.fallback_sources``) when 1 & 2 yield nothing.

Fast-demo mode (``FAST_DEMO_MODE=true``) keeps the whole run snappy (< 30s) by
capping each live query at a short timeout and doing a single attempt so a dead
provider can't burn minutes on retry backoff. The researcher additionally caps
the *number* of live queries and fails over to the fallback tiers quickly.

* Results from tiers 1 & 2 are cached in SQLite by query (requirement #6); a
  cache hit skips the network entirely.
* On total failure each function returns an empty list rather than raising, so
  the workflow never crashes because search was unavailable (requirement #18).
"""

from __future__ import annotations

import html
import os
import re
import time
from typing import Any, Callable
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from services import cache_service

load_dotenv()

# Realistic UA so Wikipedia/DuckDuckGo don't reject the request.
_USER_AGENT = (
    "TraceableResearchAssistant/1.0 (https://example.com; free educational use)"
)

# ---------------------------------------------------------------------------
# Fast-demo configuration
# ---------------------------------------------------------------------------
FAST_DEMO_MODE = os.getenv("FAST_DEMO_MODE", "true").strip().lower() in (
    "1", "true", "yes", "on")

# Per-query network timeout (seconds) and attempt count, by mode.
FAST_TIMEOUT = 6
NORMAL_TIMEOUT = 10
FAST_ATTEMPTS = 1
NORMAL_ATTEMPTS = 3

# Max number of *live* search queries (DuckDuckGo / Wikipedia) per pass.
FAST_MAX_LIVE_QUERIES = 2
# Below this many web sources, the researcher activates the fallback tiers.
FAST_FALLBACK_THRESHOLD = 3
NORMAL_FALLBACK_THRESHOLD = 5


def is_fast_mode() -> bool:
    return FAST_DEMO_MODE


def live_query_limit() -> int | None:
    """How many live queries the researcher may run (None = unlimited)."""
    return FAST_MAX_LIVE_QUERIES if FAST_DEMO_MODE else None


def fallback_threshold() -> int:
    return FAST_FALLBACK_THRESHOLD if FAST_DEMO_MODE else NORMAL_FALLBACK_THRESHOLD


def _timeout() -> int:
    return FAST_TIMEOUT if FAST_DEMO_MODE else NORMAL_TIMEOUT


def _attempts() -> int:
    return FAST_ATTEMPTS if FAST_DEMO_MODE else NORMAL_ATTEMPTS


class SearchOutcome:
    """Container returned by search functions describing what happened."""

    def __init__(self, results: list[dict[str, Any]], cache_hit: bool,
                 source: str = "duckduckgo", error: str | None = None):
        self.results = results
        self.cache_hit = cache_hit
        self.source = source          # which tier produced the results
        self.error = error


def _with_retries(fn: Callable[[], Any]) -> Any:
    """Run ``fn`` with a small, mode-aware retry budget.

    Fast mode uses a single attempt (no backoff) so a hanging provider can't
    exceed its per-query timeout; normal mode retries with light backoff.
    """
    attempts = _attempts()
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if i < attempts - 1:
                time.sleep(min(2 ** i, 4))
    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tier 1 — DuckDuckGo
# ---------------------------------------------------------------------------
def _ddg_search(query: str, max_results: int) -> list[dict[str, Any]]:
    """Raw DuckDuckGo call with a bounded per-query timeout."""
    from duckduckgo_search import DDGS

    results: list[dict[str, Any]] = []
    # DDGS timeout bounds the underlying HTTP request to _timeout() seconds.
    with DDGS(timeout=_timeout()) as ddgs:
        for r in ddgs.text(query, max_results=max_results, safesearch="moderate"):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", "") or r.get("url", ""),
                "snippet": r.get("body", ""),
            })
    return results


def search(query: str, max_results: int = 5) -> SearchOutcome:
    """Tier-1 search: cache first, then DuckDuckGo (bounded timeout)."""
    cached = cache_service.get(query)
    if cached is not None:
        return SearchOutcome(cached, cache_hit=True, source="cache")

    try:
        results = _with_retries(lambda: _ddg_search(query, max_results))
    except Exception as exc:  # noqa: BLE001 - never crash on search
        return SearchOutcome([], cache_hit=False, source="duckduckgo",
                             error=str(exc))

    if results:
        cache_service.set(query, results)
    return SearchOutcome(results, cache_hit=False, source="duckduckgo")


# ---------------------------------------------------------------------------
# Tier 2 — Wikipedia API (free, key-less)
# ---------------------------------------------------------------------------
def _clean_html(text: str) -> str:
    """Strip the HTML markup Wikipedia returns in search snippets."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def _wikipedia_search(query: str, max_results: int) -> list[dict[str, Any]]:
    """Query the Wikipedia search API and return real article hits."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": max_results,
        "format": "json",
        "srprop": "snippet",
    }
    headers = {"User-Agent": _USER_AGENT}
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=_timeout(), headers=headers) as client:
        resp = client.get("https://en.wikipedia.org/w/api.php", params=params)
        resp.raise_for_status()
        data = resp.json()
        for hit in data.get("query", {}).get("search", []):
            title = hit.get("title", "")
            snippet = _clean_html(hit.get("snippet", ""))
            if not title:
                continue
            url = f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            results.append({
                "title": f"Wikipedia — {title}",
                "url": url,
                "snippet": snippet or f"Wikipedia article on {title}.",
            })
    return results


def wikipedia_search(query: str, max_results: int = 5) -> SearchOutcome:
    """Tier-2 fallback search via the Wikipedia API (cached, bounded timeout)."""
    cache_key = f"wiki::{query}"
    cached = cache_service.get(cache_key)
    if cached is not None:
        return SearchOutcome(cached, cache_hit=True, source="wikipedia")

    try:
        results = _with_retries(lambda: _wikipedia_search(query, max_results))
    except Exception as exc:  # noqa: BLE001
        return SearchOutcome([], cache_hit=False, source="wikipedia",
                             error=str(exc))

    if results:
        cache_service.set(cache_key, results)
    return SearchOutcome(results, cache_hit=False, source="wikipedia")
