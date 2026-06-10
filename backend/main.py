"""FastAPI application — Traceable Multi-Agent Research Assistant."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import models
import schemas
from database import init_db
from services import llm_service
from services.logging_service import log
from workflow.graph import run_workflow

load_dotenv()

app = FastAPI(
    title="Traceable Multi-Agent Research Assistant",
    description="Source-backed, audit-ready answers for accounting & SMSF workpapers.",
    version="1.0.0",
)

# CORS: allow deployed frontend + local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://traceable-multi-agents-system-1.onrender.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _build_run_response(run_id: str) -> schemas.RunResponse:
    run = models.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    evaluation = models.get_evaluation(run_id)
    eval_out = None

    if evaluation:
        eval_out = schemas.EvaluationOut(
            citation_coverage=evaluation["citation_coverage"],
            num_claims=evaluation["num_claims"],
            num_supported=evaluation["num_supported"],
            num_unsupported=evaluation["num_unsupported"],
            conflict_count=evaluation["conflict_count"],
            source_count=evaluation["source_count"],
            reliability_score=evaluation["reliability_score"],
        )

    return schemas.RunResponse(
        run_id=run["id"],
        question=run["question"],
        status=run["status"],
        final_answer=run.get("final_answer"),
        error=run.get("error"),
        sources=[schemas.SourceOut(**s) for s in models.get_sources(run_id)],
        claims=[schemas.ClaimOut(**c) for c in models.get_claims(run_id)],
        conflicts=[schemas.ConflictOut(**c) for c in models.get_conflicts(run_id)],
        logs=[
            schemas.LogOut(
                agent=l["agent"],
                level=l["level"],
                message=l["message"],
                data=l["data"],
                created_at=l["created_at"],
            )
            for l in models.get_logs(run_id)
        ],
        evaluation=eval_out,
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_configured": llm_service.is_configured(),
    }


def _execute_run(run_id: str, question: str) -> None:
    try:
        state = run_workflow(run_id, question)

        models.update_run(
            run_id,
            status="completed",
            final_answer=state.get("final_answer"),
        )

    except llm_service.LLMError as exc:
        msg = str(exc)

        log(
            run_id,
            "orchestrator",
            f"Run failed: {msg}",
            level="error",
        )

        models.update_run(
            run_id,
            status="failed",
            error=msg,
        )

    except Exception as exc:
        msg = f"Unexpected error: {exc}"

        log(
            run_id,
            "orchestrator",
            msg,
            level="error",
        )

        models.update_run(
            run_id,
            status="failed",
            error=msg,
        )


@app.post("/api/run", response_model=schemas.RunStartResponse)
def create_run(
    req: schemas.RunRequest,
    background_tasks: BackgroundTasks,
) -> schemas.RunStartResponse:
    run_id = models.create_run(req.question)

    background_tasks.add_task(
        _execute_run,
        run_id,
        req.question,
    )

    return schemas.RunStartResponse(
        run_id=run_id,
        status="running",
    )


@app.get("/api/runs")
def list_runs() -> dict:
    return {
        "runs": models.list_runs(),
    }


@app.get("/api/runs/{run_id}", response_model=schemas.RunResponse)
def get_run(run_id: str) -> schemas.RunResponse:
    return _build_run_response(run_id)


@app.get("/api/runs/{run_id}/logs")
def get_logs(run_id: str) -> dict:
    if not models.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "logs": models.get_logs(run_id),
    }


@app.get("/api/runs/{run_id}/sources")
def get_sources(run_id: str) -> dict:
    if not models.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "sources": models.get_sources(run_id),
    }


@app.get("/api/runs/{run_id}/claims")
def get_claims(run_id: str) -> dict:
    if not models.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "claims": models.get_claims(run_id),
    }