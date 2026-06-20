"""FastAPI entrypoint.

    uv run uvicorn app.main:app --reload

Builds one EvaluationEngine (compiled graph + services) at startup and an
in-memory report store. Domains self-register on import.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.logging import configure_logging, get_logger
from app.graph.build import EvaluationEngine
from app.schemas.report import Report

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.engine = EvaluationEngine()
    app.state.report_store = {}  # type: dict[str, Report]
    log.info("startup_complete", domain_default="genai")
    yield
    log.info("shutdown")


app = FastAPI(
    title="depth-eval-engine",
    version="0.1.0",
    description="Advisory resume depth & authenticity evaluator (M0: GenAI). "
    "Human-in-the-loop; never auto-rejects.",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "depth-eval-engine",
        "advisory": True,
        "human_review_required": True,
        "endpoints": ["POST /evaluate", "GET /report/{id}", "GET /healthz"],
    }
