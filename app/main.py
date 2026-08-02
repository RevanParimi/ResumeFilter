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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    auth_router, candidate_router, org_router, public_router, router,
)
from app.core.boot import verify_launch_config
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.migrate import upgrade_to_head
from app.graph.build import EvaluationEngine
from app.services import Services, build_default_services

log = get_logger("main")


def create_app(services: Optional[Services] = None) -> FastAPI:
    """Build the app; pass a Services bundle to inject fakes (tests)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        # Refuse to serve a misconfigured deployment rather than serve an open
        # admin plane (S8.1). Runs for injected services too: a test that boots
        # without a credential is exactly the blind spot this closes.
        boot_settings = services.settings if services is not None else get_settings()
        verify_launch_config(boot_settings)
        # Injected services (tests) already own a schema; only a real boot
        # migrates. Blocker 1: this ran nowhere, so a fresh container started
        # against no schema at all.
        if services is None and boot_settings.db_migrate_on_boot:
            upgrade_to_head(boot_settings)
        svc = services or build_default_services()
        app.state.services = svc
        app.state.engine = EvaluationEngine(svc)
        log.info(
            "startup_complete",
            llm=type(svc.llm).__name__,
            db=svc.settings.candidates_db_url.split("://", 1)[0],
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
    app.include_router(org_router)
    app.include_router(candidate_router)
    app.include_router(public_router)
    app.include_router(auth_router)

    # CORS (S8.2). Fail-CLOSED: with no configured origin the middleware is not
    # installed at all, so nothing cross-site can reach the API. Never "*" —
    # browsers forbid a wildcard alongside credentials, and leaning on that as
    # the guard leaves a defect waiting to be "fixed" by silencing the console
    # error. Prod refuses to BOOT with a wildcard (app/core/boot.py).
    cors_settings = services.settings if services is not None else get_settings()
    if cors_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_settings.cors_allowed_origins),
            allow_credentials=True,      # the session cookie has to ride along
            allow_methods=["*"],
            allow_headers=["*", "X-CSRF-Token"],
        )

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
                "POST /candidates",
                "GET /candidates/{id}",
                "GET /candidates/{id}/resumes",
                "GET /candidates/{id}/reports",
                "DELETE /candidates/{id}",
                "DELETE /candidates/{id}/resumes/{resume_id}",
                "POST /candidates/{id}/sources/github",
                "GET /candidates/{id}/sources",
                "POST /candidates/{id}/auth-key",
                "GET /portal/me",
                "GET /portal/access-log",
                "GET /portal/consents",
                "POST /portal/consents",
                "POST /portal/consents/{id}/revoke",
                "DELETE /portal/me",
                "GET /report/{id}",
                "POST /report/{id}/outcome",
                "GET /report/{id}/outcomes",
                "GET /domains",
                "GET /healthz",
                "POST /ledger/orgs",
                "GET /ledger/orgs",
                "POST /ledger/orgs/{id}/api-key",
                "DELETE /ledger/orgs/{id}",
                "POST /ledger/candidates/{id}/consent",
                "POST /ledger/consent/{id}/revoke",
                "GET /ledger/candidates/{id}/consent",
                "POST /ledger/records",
                "POST /ledger/records/{id}/events",
                "GET /ledger/candidates/{id}/records",
                "POST /ledger/coding-rounds",
                "GET /ledger/candidates/{id}/coding-rounds",
                "GET /ledger/candidates/{id}/reputation",
                "POST /ledger/orgs/{id}/reliability",
                "POST /talent/search",
                "GET /dashboard/overview",
                "GET /jobs/{id}/board",
                "GET /candidates/{id}/card",
            ],
        }

    return app


app = create_app()
