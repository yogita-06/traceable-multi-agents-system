"""Search-result caching backed by the ``search_cache`` SQLite table.

Caching is keyed by the normalised query string. Callers get a clear
hit/miss signal so the agents can log it (requirement #6).
"""

from __future__ import annotations

from typing import Any

import models


def _normalise(query: str) -> str:
    return " ".join(query.lower().split())


def get(query: str) -> list[dict[str, Any]] | None:
    """Return cached results for ``query`` or ``None`` on a miss."""
    return models.cache_get(_normalise(query))


def set(query: str, results: list[dict[str, Any]]) -> None:
    models.cache_set(_normalise(query), results)
