"""Structured, timestamped agent logging.

Every agent writes through ``log`` so the UI can render a single ordered
timeline. Logs are persisted to ``agent_logs`` and mirrored to stdout.
"""

from __future__ import annotations

from typing import Any

import models


def log(run_id: str, agent: str, message: str, level: str = "info",
        data: Any = None) -> None:
    entry = models.add_log(run_id, agent, message, level=level, data=data)
    print(f"[{entry['created_at']}] [{agent}] [{level.upper()}] {message}")
