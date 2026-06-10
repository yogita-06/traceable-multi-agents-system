"""SQLite persistence layer.

Uses the Python standard-library ``sqlite3`` module (no external ORM) so the
project stays 100% free and dependency-light. A thin set of helper functions
provides connection handling, schema creation and JSON-friendly row access.

Tables (see ``init_db`` for the full DDL):
    runs, sources, claims, agent_logs, conflicts, evaluations, search_cache
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------------
_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./traceable.db")
# Strip the SQLAlchemy-style prefix if the user copied it from .env.example.
DB_PATH = _DB_URL.replace("sqlite:///", "").replace("sqlite://", "") or "./traceable.db"

# A single write lock keeps SQLite happy under FastAPI's threadpool.
_write_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection and committing on success."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    question      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'running',
    final_answer  TEXT,                 -- JSON blob of the structured answer
    error         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,       -- e.g. S1, S2 (unique per run)
    run_id      TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    snippet     TEXT,
    query       TEXT,                   -- the search query that surfaced it
    cached      INTEGER DEFAULT 0,      -- 1 if served from cache
    relevance   REAL DEFAULT 0.0,       -- 0..1 semantic relevance to question
    created_at  TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS claims (
    id            TEXT PRIMARY KEY,     -- e.g. C1, C2 (unique per run)
    run_id        TEXT NOT NULL,
    text          TEXT NOT NULL,
    source_ids    TEXT,                 -- JSON array of source ids
    supported     INTEGER DEFAULT 0,    -- 1 supported, 0 unsupported
    confidence    REAL DEFAULT 0.0,     -- 0..1
    category      TEXT,                 -- finding | risk | control | other
    created_at    TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    agent       TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'info',   -- info | warn | error | retry
    message     TEXT NOT NULL,
    data        TEXT,                            -- optional JSON payload
    created_at  TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conflicts (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    topic           TEXT NOT NULL,
    summary         TEXT,
    side_a          TEXT,               -- statement of position A
    side_a_sources  TEXT,               -- JSON array of source ids
    side_b          TEXT,
    side_b_sources  TEXT,
    confidence      REAL DEFAULT 0.0,   -- 0..1 strength of the contradiction
    created_at      TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evaluations (
    run_id              TEXT PRIMARY KEY,
    citation_coverage   REAL,
    num_claims          INTEGER,
    num_supported       INTEGER,
    num_unsupported     INTEGER,
    conflict_count      INTEGER,
    source_count        INTEGER,
    reliability_score   REAL,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS search_cache (
    query       TEXT PRIMARY KEY,
    results     TEXT NOT NULL,          -- JSON array of {title,url,snippet}
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_run   ON sources(run_id);
CREATE INDEX IF NOT EXISTS idx_claims_run    ON claims(run_id);
CREATE INDEX IF NOT EXISTS idx_logs_run      ON agent_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_run ON conflicts(run_id);
"""


def init_db() -> None:
    """Create all tables/indexes if they do not already exist."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Lightweight, idempotent column migrations for pre-existing databases."""
    conflict_cols = {r["name"] for r in conn.execute("PRAGMA table_info(conflicts)")}
    if "confidence" not in conflict_cols:
        conn.execute("ALTER TABLE conflicts ADD COLUMN confidence REAL DEFAULT 0.0")

    source_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sources)")}
    if "relevance" not in source_cols:
        conn.execute("ALTER TABLE sources ADD COLUMN relevance REAL DEFAULT 0.0")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def execute(sql: str, params: tuple = ()) -> None:
    """Run a write statement under the global write lock."""
    with _write_lock, get_conn() as conn:
        conn.execute(sql, params)


def query_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def query_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
