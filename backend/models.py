"""Repository functions — typed read/write helpers over the SQLite tables.

Keeping all SQL here means the agents and API layer never touch raw queries;
they call intention-revealing functions such as ``add_source`` or
``set_evaluation``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import database as db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------
def create_run(question: str) -> str:
    run_id = new_id("run_")
    ts = _now()
    db.execute(
        "INSERT INTO runs (id, question, status, created_at, updated_at) "
        "VALUES (?, ?, 'running', ?, ?)",
        (run_id, question, ts, ts),
    )
    return run_id


def update_run(run_id: str, *, status: str | None = None,
               final_answer: Any = None, error: str | None = None) -> None:
    fields, params = [], []
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if final_answer is not None:
        fields.append("final_answer = ?")
        params.append(db.dumps(final_answer))
    if error is not None:
        fields.append("error = ?")
        params.append(error)
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(run_id)
    db.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", tuple(params))


def get_run(run_id: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM runs WHERE id = ?", (run_id,))
    if row:
        row["final_answer"] = db.loads(row.get("final_answer"))
    return row


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return db.query_all(
        "SELECT id, question, status, created_at FROM runs "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
def add_source(run_id: str, source_id: str, title: str, url: str,
               snippet: str, query: str, cached: bool,
               relevance: float = 0.0) -> None:
    db.execute(
        "INSERT OR REPLACE INTO sources "
        "(id, run_id, title, url, snippet, query, cached, relevance, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, run_id, title, url, snippet, query, int(cached),
         float(relevance), _now()),
    )


def get_sources(run_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM sources WHERE run_id = ? ORDER BY id", (run_id,)
    )
    for r in rows:
        r["cached"] = bool(r["cached"])
    return rows


# ---------------------------------------------------------------------------
# claims
# ---------------------------------------------------------------------------
def add_claim(run_id: str, claim_id: str, text: str, source_ids: list[str],
              supported: bool, confidence: float, category: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO claims "
        "(id, run_id, text, source_ids, supported, confidence, category, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (claim_id, run_id, text, db.dumps(source_ids), int(supported),
         float(confidence), category, _now()),
    )


def get_claims(run_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM claims WHERE run_id = ? ORDER BY id", (run_id,)
    )
    for r in rows:
        r["source_ids"] = db.loads(r["source_ids"], [])
        r["supported"] = bool(r["supported"])
    return rows


def clear_claims(run_id: str) -> None:
    """Used when the verifier routes back and claims are regenerated."""
    db.execute("DELETE FROM claims WHERE run_id = ?", (run_id,))


# ---------------------------------------------------------------------------
# agent_logs
# ---------------------------------------------------------------------------
def add_log(run_id: str, agent: str, message: str, level: str = "info",
            data: Any = None) -> dict[str, Any]:
    ts = _now()
    db.execute(
        "INSERT INTO agent_logs (run_id, agent, level, message, data, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, agent, level, message, db.dumps(data) if data is not None else None, ts),
    )
    return {"agent": agent, "level": level, "message": message,
            "data": data, "created_at": ts}


def get_logs(run_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM agent_logs WHERE run_id = ? ORDER BY id", (run_id,)
    )
    for r in rows:
        r["data"] = db.loads(r.get("data"))
    return rows


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------
def add_conflict(run_id: str, topic: str, summary: str, side_a: str,
                 side_a_sources: list[str], side_b: str,
                 side_b_sources: list[str], confidence: float = 0.0) -> None:
    db.execute(
        "INSERT INTO conflicts "
        "(id, run_id, topic, summary, side_a, side_a_sources, side_b, "
        " side_b_sources, confidence, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id("cf_"), run_id, topic, summary, side_a,
         db.dumps(side_a_sources), side_b, db.dumps(side_b_sources),
         float(confidence), _now()),
    )


def get_conflicts(run_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM conflicts WHERE run_id = ? ORDER BY created_at", (run_id,)
    )
    for r in rows:
        r["side_a_sources"] = db.loads(r["side_a_sources"], [])
        r["side_b_sources"] = db.loads(r["side_b_sources"], [])
    return rows


def clear_conflicts(run_id: str) -> None:
    db.execute("DELETE FROM conflicts WHERE run_id = ?", (run_id,))


# ---------------------------------------------------------------------------
# evaluations
# ---------------------------------------------------------------------------
def set_evaluation(run_id: str, metrics: dict[str, Any]) -> None:
    db.execute(
        "INSERT OR REPLACE INTO evaluations "
        "(run_id, citation_coverage, num_claims, num_supported, num_unsupported, "
        " conflict_count, source_count, reliability_score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, metrics["citation_coverage"], metrics["num_claims"],
         metrics["num_supported"], metrics["num_unsupported"],
         metrics["conflict_count"], metrics["source_count"],
         metrics["reliability_score"], _now()),
    )


def get_evaluation(run_id: str) -> dict[str, Any] | None:
    return db.query_one("SELECT * FROM evaluations WHERE run_id = ?", (run_id,))


# ---------------------------------------------------------------------------
# search_cache
# ---------------------------------------------------------------------------
def cache_get(query: str) -> list[dict[str, Any]] | None:
    row = db.query_one("SELECT results FROM search_cache WHERE query = ?", (query,))
    return db.loads(row["results"]) if row else None


def cache_set(query: str, results: list[dict[str, Any]]) -> None:
    db.execute(
        "INSERT OR REPLACE INTO search_cache (query, results, created_at) "
        "VALUES (?, ?, ?)",
        (query, db.dumps(results), _now()),
    )
