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
from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app import __version__
from app.api.routes import (
    ServiceInfo, auth_router, candidate_router, org_router, public_router, router,
)
from app.core.boot import verify_launch_config
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.migrate import upgrade_to_head
from app.graph.build import EvaluationEngine
from app.services import Services, build_default_services

log = get_logger("main")


def _iter_api_routes(routes):
    """Every real APIRoute, recursing through the _IncludedRouter wrappers
    FastAPI 0.138 stores instead of flattening include_router. A naive
    `for route in app.routes` sees ONE route here."""
    from fastapi.routing import APIRoute

    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(original.routes)
        elif isinstance(route, APIRoute):
            yield route


def _route_template(request: Request) -> str:
    """The matched route's PATH TEMPLATE, or ``__unmatched__``.

    `request.scope["route"]` is set by the router before the endpoint runs, and
    BaseHTTPMiddleware shares that same scope dict, so it is visible here.

    This originally kept a fallback that re-resolved the match by scanning the
    route table, on the theory that the scope mutation might not be visible.
    The S8.3 review MEASURED it (starlette 1.3.1): the scan's successful branch
    never executes. Matched requests, 405s and 500s all return early because
    the router sets the route even on a partial match and even when the
    endpoint raises; 404s, redirects and CORS preflights all reach the scan and
    find nothing, because nothing FULL-matches those. So the fallback was
    unreachable defensive code, in a repo that treats declared-but-inert
    machinery as a defect -- which is this very branch's headline finding.

    What replaces it is a test, not a scan:
    tests/test_metrics.py::test_the_template_label_comes_from_the_request_scope
    fails loudly if a Starlette upgrade ever stops populating the scope, rather
    than letting every label silently degrade to __unmatched__.
    """
    return getattr(request.scope.get("route"), "path", None) or "__unmatched__"


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

    # The UI is served BY THIS API, same origin (S8.6 spec 2). Chosen over a
    # separate static host because it RETIRES an untested posture rather than
    # shipping one: config.yaml's SameSite=None has never been exercised by any
    # check in this repo -- the browser check runs both servers on localhost,
    # which is cross-ORIGIN but same-SITE, with samesite=lax.
    #
    # A Mount is NOT an APIRoute: no router dependency applies to it, so this
    # surface is unauthenticated. That is correct -- the shell has to load
    # before anyone can log in -- and it is why tests/test_route_table_guard.py
    # gained MOUNTS in the commit before this one. Widening that set is the
    # reviewable act, exactly as it is for PUBLIC_PATHS.
    _ui_dir = Path(__file__).resolve().parents[1] / "frontend"
    if _ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=_ui_dir), name="ui")

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
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            log.info(
                "access",
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=elapsed_ms,
            )
            # Label by the ROUTE TEMPLATE, never the raw path (S8.3 Phase A).
            # The raw path is one series per batch id, and a scanner walking
            # random URLs would be an unbounded memory leak dressed as
            # observability. Anything unmatched collapses to ONE label.
            services = getattr(app.state, "services", None)
            if services is not None:
                template = _route_template(request)
                services.metrics.increment(
                    "http_requests",
                    route=template,
                    method=request.method,
                    status=str(status),
                )
                services.metrics.observe_duration(template, elapsed_ms)
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

    @app.get("/", response_model=ServiceInfo)
    async def root() -> ServiceInfo:
        # A HAND-MAINTAINED HIGHLIGHTS LIST, not the route table, and it has
        # drifted: none of the org-plane `/screening/*` routes (S8.4 A+B, S8.5,
        # plus S8.3's `/retry`) appear below, neither does `GET /metrics`, and
        # neither do any of S8.3 Phase B's SEVEN (`/portal/corrections`,
        # `/portal/grievances`, `/portal/requests`, `/grievance`,
        # `/admin/retention/sweep`, `/admin/requests`,
        # `/admin/requests/{id}/resolve`).
        # Stated rather than patched, because adding entries would make an
        # unmaintained list look maintained -- the second hand-maintained list
        # is always the one that drifts (the S8.2 review's OPEN_PATHS/
        # PUBLIC_PATHS finding). `GET /openapi.json` is generated from the code
        # and is the authority; making this field derive from it is the real
        # fix and belongs with the docs/routes.md idea in ROADMAP.
        #
        # The S8.3 review widened this note rather than the list: the previous
        # wording named only the `/screening/*` gap, so a reader could have
        # concluded /metrics was covered. A comment that describes drift has to
        # describe all of it or it becomes the next thing that is out of date --
        # so Phase B widened it again rather than letting it go stale twice.
        # (Phase B DID fix two other hand-maintained lists this sprint, the 429
        # translation and test_ratelimit_wiring's LIMITED tuple. This one is
        # left alone because the fix is derivation, not typing; the other two
        # had no such option.)
        return ServiceInfo(**{
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
        })

    # OpenAPI: give every route the handler's own name as its operation_id.
    #
    # LAST, deliberately: the `@app.get` routes above (/, /healthz) are
    # registered after the include_router calls, so a loop placed beside those
    # calls silently misses them -- which is how this was first written and what
    # tests/test_openapi_contract.py caught.
    #
    # In a loop rather than 90 literals: a per-route operation_id= argument is
    # 90 chances to typo and no protection at all for route 91. FastAPI's
    # default is unique but unusable -- it derives
    # `list_candidate_reports_candidates__candidate_id__reports_get` from the
    # path -- and S8.4 exists partly so a typed client can be generated from
    # this document. tests/test_openapi_contract.py asserts uniqueness, which is
    # the one thing this loop cannot check for itself.
    for route in _iter_api_routes(app.routes):
        route.operation_id = route.name

    return app


app = create_app()
