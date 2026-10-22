"""Public service information and admin-only registered domain metadata.

Router segments preserve the original registration order and auth boundaries.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel, Field

from app import __version__
from app.api.dependencies import _services, require_api_key
from app.domains.base import get_domain, list_domains
from app.rights.schema import GrievanceContact, build_grievance_contact
from app.services.llm import NullLLM


public_router = APIRouter()
domain_router = APIRouter(dependencies=[Depends(require_api_key)])
# The service description stays last, after auth and the UI mount.
service_router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
    llm_mode: str
    domains: list[str] = Field(default_factory=list)


class DomainInfo(BaseModel):
    key: str
    display_name: str
    claim_types: list[str] = Field(default_factory=list)


class ServiceInfo(BaseModel):
    service: str
    advisory: bool = True
    human_review_required: bool = True
    endpoints: list[str] = Field(default_factory=list)


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


def _unadvertised_paths(app: FastAPI) -> frozenset[str]:
    """FastAPI's own documentation surface, plus "/" itself: the paths ``GET /``
    must never list, because they describe the API rather than being part of
    it and a caller reading the list is already at "/".

    DERIVED FROM THE APP, not typed out, for the same reason as the list it
    filters. The literal that stood here transcribed four paths out of
    ``PUBLIC_PATHS`` by hand -- a fourth copy of one list, planted one line
    away from the hand-maintained list whose eight-PI drift is the defect this
    endpoint was rewritten to fix. Read off ``app`` these follow a rename or a
    ``docs_url=None`` on their own.

    AND NOTE WHAT ACTUALLY DOES THE WORK. FastAPI registers its docs surface
    with ``add_route``, which builds a starlette ``Route``; ``_iter_api_routes``
    yields only ``APIRoute``. So all four doc paths are already excluded BY
    TYPE and never reach this set -- measured, not assumed -- and "/" is the
    only entry that filters anything today. Kept as a belt because derivation
    made it free to keep, and because the type filter is FastAPI's private
    choice rather than a promise to us.
    """
    return frozenset(
        {"/"}
        | {
            url
            for url in (
                app.docs_url,
                app.redoc_url,
                app.openapi_url,
                app.swagger_ui_oauth2_redirect_url,
            )
            if url
        }
    )


def _advertised_endpoints(app: FastAPI) -> list[str]:
    """The `endpoints` field of ``GET /``, DERIVED from the live route table.

    This field was hand-maintained for eight PIs and was carried as a known
    drift through S8.3 Phase A, Phase B and S8.5 -- each time correctly,
    because typing the missing entries in would make an unmaintained list look
    maintained. The real fix, named in the note this replaces, is derivation.

    Mounts are excluded, and for free: ``_iter_api_routes`` yields only
    APIRoutes, and a static UI directory is not an API entry point. HEAD and
    OPTIONS are excluded because Starlette adds them to every GET -- keeping
    them would triple the list with entries no caller writes by hand, and a
    list that reads as noise is what would push the next person back to a
    literal. The admin plane is INCLUDED: it always was, and hiding it would be
    obscurity on a plane that is already credential-gated, while making the
    list wrong again.
    """
    unadvertised = _unadvertised_paths(app)
    seen: set[str] = set()
    for route in _iter_api_routes(app.routes):
        if route.path in unadvertised:
            continue
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            seen.add(f"{method} {route.path}")
    return sorted(seen, key=lambda e: (e.split(" ", 1)[1], e))


@domain_router.get("/domains", response_model=list[DomainInfo])
async def domains() -> list[DomainInfo]:
    """Registered evaluation domains (FR-9)."""
    out = []
    for key in list_domains():
        d = get_domain(key)
        out.append(
            {"key": d.key, "display_name": d.display_name, "claim_types": d.claim_types}
        )
    return out


@public_router.get("/grievance", response_model=GrievanceContact)
async def grievance(request: Request) -> GrievanceContact:
    """The published grievance mechanism. PUBLIC by design (spec §9).

    On `public_router` and named in PUBLIC_PATHS, which is the reviewable act
    that widening that set is meant to be. It discloses four operator-chosen
    fields and reads nothing about any data principal, and prod refuses to boot
    with the email unset so this can never be a 200 that says nothing.
    """
    return build_grievance_contact(_services(request).settings)


@public_router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> HealthResponse:
    """Liveness + effective mode (FR-10). Open — load balancers don't have keys."""
    services = _services(request)
    return {
        "status": "ok",
        "version": __version__,
        "env": services.settings.env,
        "llm_mode": "null" if isinstance(services.llm, NullLLM) else "live",
        "domains": list_domains(),
    }


@service_router.get("/", response_model=ServiceInfo)
async def root(request: Request) -> ServiceInfo:
    return ServiceInfo(**{
        "service": "depth-eval-engine",
        "advisory": True,
        "human_review_required": True,
        # DERIVED (S8.6). Carried as a known drift through S8.3 Phase A,
        # Phase B and S8.5 -- see _advertised_endpoints for why patching
        # the literal was refused three times before it was replaced.
        "endpoints": _advertised_endpoints(request.app),
    })
