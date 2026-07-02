"""FastAPI entrypoint.

    uv run uvicorn app.main:app --reload

:func:`create_app` builds the app around one Services bundle + EvaluationEngine
(injected by tests, built from settings in production) so the whole HTTP
surface is testable fully offline. Domains self-register on import.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import public_router, router
from app.core.logging import configure_logging, get_logger
from app.graph.build import EvaluationEngine
from app.services import Services, build_default_services

log = get_logger("main")


def create_app(services: Optional[Services] = None) -> FastAPI:
    """Build the app; pass a Services bundle to inject fakes (tests)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        svc = services or build_default_services()
        app.state.services = svc
        app.state.engine = EvaluationEngine(svc)
        log.info(
            "startup_complete",
            llm=type(svc.llm).__name__,
            report_db=getattr(svc.report_store, "path", "memory"),
            env=svc.settings.env,
        )
        yield
        log.info("shutdown")

    app = FastAPI(
        title="depth-eval-engine",
        version=__version__,
        description="Advisory resume depth & authenticity evaluator. "
        "Human-in-the-loop; never auto-rejects.",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(public_router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Bind a request ID into every log line; emit one access line."""
        rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        status = 500  # what the client sees if call_next raises
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            log.info(
                "access",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            structlog.contextvars.clear_contextvars()

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        """Generic 500: full traceback in the logs, nothing internal on the wire."""
        rid = getattr(request.state, "request_id", "")
        log.error("unhandled_error", request_id=rid, error=repr(exc), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_error", "request_id": rid},
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.get("/")
    async def root() -> dict:
        return {
            "service": "depth-eval-engine",
            "advisory": True,
            "human_review_required": True,
            "endpoints": [
                "POST /evaluate",
                "GET /report/{id}",
                "POST /report/{id}/outcome",
                "GET /report/{id}/outcomes",
                "GET /domains",
                "GET /healthz",
            ],
        }

    return app


app = create_app()
