"""Pydantic request/response schemas for the FastAPI layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=500,
                          description="The open-ended question to research.")


class SourceOut(BaseModel):
    id: str
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    query: str | None = None
    cached: bool = False
    relevance: float = 0.0


class ClaimOut(BaseModel):
    id: str
    text: str
    source_ids: list[str] = []
    supported: bool = False
    confidence: float = 0.0
    category: str | None = None


class LogOut(BaseModel):
    agent: str
    level: str
    message: str
    data: Any | None = None
    created_at: str


class ConflictOut(BaseModel):
    topic: str
    summary: str | None = None
    side_a: str | None = None
    side_a_sources: list[str] = []
    side_b: str | None = None
    side_b_sources: list[str] = []
    confidence: float = 0.0


class EvaluationOut(BaseModel):
    citation_coverage: float
    num_claims: int
    num_supported: int
    num_unsupported: int
    conflict_count: int
    source_count: int
    reliability_score: float


class RunStartResponse(BaseModel):
    """Returned immediately by POST /api/run; the workflow runs in the background."""
    run_id: str
    status: str = "running"


class RunResponse(BaseModel):
    run_id: str
    question: str
    status: str
    final_answer: dict[str, Any] | None = None
    error: str | None = None
    sources: list[SourceOut] = []
    claims: list[ClaimOut] = []
    conflicts: list[ConflictOut] = []
    logs: list[LogOut] = []
    evaluation: EvaluationOut | None = None
