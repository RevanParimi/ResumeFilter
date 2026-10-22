"""Remaining product handlers and ordered API assembly.

Auth, reports, candidates, screening, ledger, employer, features, portal, verification
and interviews have API modules.
Shared request/auth dependencies keep the same principal and CSRF boundaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app import __version__
# Compatibility aliases retain callable identity for existing route guards.
from app.api.auth import auth_router
from app.api.interviews import (
    candidate_router as interview_candidate_router, org_router as interview_org_router,
)
from app.api.verification import (
    candidate_router as verification_candidate_router, org_router as verification_org_router,
    router as verification_admin_router,
)
from app.api.employer import org_router as employer_router
from app.api.features import router as feature_router
from app.api.portal import candidate_router as portal_candidate_router, router as portal_admin_router
from app.api.ledger import (
    router as ledger_admin_router, org_router as ledger_org_router,
)
from app.api.screening import org_router as screening_router
from app.api.candidates import (
    CandidateCreateRequest, CandidateCreateResponse, ErasureResponse, _ingest_one,
    router as candidate_admin_router,
)
from app.api.reports import (
    OutcomeListResponse, OutcomeRecordedResponse, OutcomeRequest,
    _outcome_flywheel_record, _outcome_recorded, evaluation_router, report_router,
)
from app.api.dependencies import (
    PUBLIC_PATHS, _services,
    require_any_principal, require_api_key, require_candidate, require_org,
)
from app.auth.schema import AdminUser
from app.domains.base import get_domain, list_domains
from app.profile_sources.store import SourceSubjectErasedError
from app.curation.schema import (
    CurationAction, CurationDecision, CurationStatus, UnmappedPage,
)
from app.curation.service import AliasConflictError
from app.curation.store import StaleReviewError
from app.retention.schema import SweepReport
from app.retention.sweep import run_sweep
from app.signal_quality.labels import LedgerLabelSource, OutcomesLabelSource
from app.signal_quality.schema import SignalQualityReport
from app.signal_quality.service import measure
from app.rights.schema import (
    GrievanceContact, build_grievance_contact,
)
from app.screening.pagination import InvalidCursor
from app.services.llm import NullLLM


# ── Response models for what used to be `-> dict` (S8.4 Phase B, Task 13) ────
# MEASURED before this sprint: 38 of 90 operations advertised
# {"type":"object","additionalProperties":true}, which generates
# Record<string, any> and puts every client back to guessing. These models
# describe the bodies that ALREADY EXIST -- not one field was added, removed or
# renamed. Where a shape is shared (an acknowledgement, the auth 202) one model
# is shared, because trading an untyped client for an unreadable one is not a
# trade worth making.


class AdminUserDeletedResponse(BaseModel):
    admin_user_id: str
    deleted: bool


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


# Everything except "/" and /healthz sits behind the admin credential.
# CSRF is enforced inside require_api_key itself (see _accept), so there is no
# second dependency here whose ordering could be got wrong.
router = APIRouter(dependencies=[Depends(require_api_key)])
public_router = APIRouter()
# Org-authenticated data plane (X-Org-Key or an org-user session), separate from
# the admin router so an org never needs the platform's shared secret to submit
# or query its own data.
org_router = APIRouter()
# Candidate-authenticated DPDP portal plane (X-Candidate-Key or a candidate
# session). Every route acts on the candidate resolved from the credential —
# never a path/body param.
candidate_router = APIRouter()


# Compose existing APIRoutes without an extra inherited dependency context.
router.routes.extend(evaluation_router.routes)


router.routes.extend(candidate_admin_router.routes)


# ── Normalization curation loop (S6.3) ───────────────────────────────────────
# Admin-plane review of unmapped skill terms surfaced by the profile-source
# adapters. Resolving a term feeds the deterministic normalize_skill overlay.
# The admin router authenticates operator sessions/keys and enforces session CSRF.


class CurationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    norm_key: str = Field(min_length=1, max_length=128)
    action: CurationAction
    alias: Optional[str] = Field(default=None, min_length=1, max_length=128)
    canonical: Optional[str] = Field(default=None, min_length=1, max_length=64)
    category: Optional[str] = Field(default=None, min_length=1, max_length=32)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get(
    "/curation/skills/unmapped", response_model=UnmappedPage,
    description=(
        "The unmapped-term review queue. Cursor-paginated; pass `next_cursor` back as `cursor`. NOTE the sort key "
        "(occurrences, last_seen) is mutable, so paging is stable against "
        "inserts and not against re-observation."
    ),
)
async def list_unmapped_terms(
    request: Request,
    status: Optional[CurationStatus] = None,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> UnmappedPage:
    try:
        return _services(request).curation.list_unmapped(status, limit, cursor=cursor)
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/curation/skills/resolve", response_model=CurationDecision)
async def resolve_unmapped_term(
    req: CurationResolveRequest, request: Request
) -> CurationDecision:
    services = _services(request)
    try:
        return services.curation.resolve(
            req.norm_key, req.action, alias=req.alias, canonical=req.canonical,
            category=req.category, admin_user_id=request.state.principal.admin_user_id,
            expected_revision=req.expected_revision,
        )
    except StaleReviewError:
        raise HTTPException(status_code=409, detail="review snapshot changed; refresh before deciding") from None
    except AliasConflictError:
        raise HTTPException(status_code=409, detail="approved alias already exists") from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="term not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Evaluation ledger (S3.2) ────────────────────────────────────────────────
# Org lifecycle + consent are ADMIN operations (shared-secret X-API-Key gate).
# Org data operations (records/events/query) authenticate with an org's own key
# on `org_router` below.


router.routes.extend(ledger_admin_router.routes)


# Compose already-scoped screening routes at their original org-plane position.
org_router.routes.extend(screening_router.routes)


org_router.routes.extend(ledger_org_router.routes)


org_router.routes.extend(employer_router.routes)


candidate_router.routes.extend(portal_candidate_router.routes)


candidate_router.routes.extend(verification_candidate_router.routes)
org_router.routes.extend(verification_org_router.routes)


candidate_router.routes.extend(interview_candidate_router.routes)
org_router.routes.extend(interview_org_router.routes)


router.routes.extend(verification_admin_router.routes)


router.routes.extend(feature_router.routes)


# Keep the existing admin route order; dependencies are already on each route.
router.routes.extend(report_router.routes)


@router.get("/metrics", response_model=str, response_class=PlainTextResponse)
async def metrics(request: Request) -> PlainTextResponse:
    """Prometheus text exposition (S8.3 Phase A).

    On the ADMIN router, so `require_api_key` is inherited rather than
    remembered and the route-table guard covers it with no edit.

    `response_model=str` is honest -- the body IS a string -- and it keeps
    tests/test_openapi_contract.py's every-route-declares-a-model rule intact
    without carving out an exemption for one route.
    """
    return PlainTextResponse(
        _services(request).metrics.render(),
        media_type="text/plain; version=0.0.4",
    )


router.routes.extend(portal_admin_router.routes)


class SweepRequest(BaseModel):
    """``dry_run`` DEFAULTS TO TRUE.

    This is the most destructive call in the repo, and defaulting it the other
    way would make an empty body -- the easiest thing to send by accident, and
    what a mistyped curl sends -- delete production data. A cron passes
    ``{"dry_run": false}`` explicitly, which is one word of evidence that
    somebody meant it.
    """

    dry_run: bool = True


@router.post("/admin/retention/sweep", response_model=SweepReport)
async def retention_sweep(req: SweepRequest, request: Request) -> SweepReport:
    """Run (or preview) the retention sweep. Admin plane.

    There is no scheduler in the application, so this route and
    ``python -m app.retention.sweep`` are the only two ways the sweep ever
    runs. Both go through ``run_sweep``, so the refusal below cannot be
    enforced at one door and forgotten at the other.
    """
    services = _services(request)
    if not req.dry_run and not services.settings.retention_sweep_enabled:
        # 409, not 403: the CONFIGURATION is in the wrong state, and the
        # operator's fix is a knob rather than a credential. A dry run is still
        # allowed, because a count is safe and is how they see what would go.
        raise HTTPException(status_code=409, detail="retention_sweep_disabled")
    return run_sweep(
        services.session_factory,
        services.settings,
        now=datetime.now(timezone.utc),
        dry_run=req.dry_run,
        metrics=services.metrics,
    )


@router.get("/domains", response_model=list[DomainInfo])
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


# -- operator accounts (admin plane; decision 0.3) ---------------------------


class AdminUserRequest(BaseModel):
    email: str
    label: str = ""


@router.post("/admin/users", response_model=AdminUser)
async def create_admin_user(req: AdminUserRequest, request: Request) -> AdminUser:
    """Bootstrap reuses the shared key rather than inventing a mechanism.

    X-API-Key already exists and already fails closed (S8.1), so it becomes the
    machine/root credential while operator accounts become the human one -- the
    two-modes-per-plane rule applied to the admin plane. No boot-time side
    effects, no DEE_ADMIN_BOOTSTRAP_EMAIL, no chicken-and-egg.
    """
    services = _services(request)
    email_hash = services.auth.hash_email(req.email)
    if services.auth.find_admin_user(email_hash) is not None:
        raise HTTPException(status_code=409, detail="operator already exists")
    return services.auth.create_admin_user(
        email_hash=email_hash, label=req.label
    ).model_dump(mode="json")


@router.get("/admin/signal-quality", response_model=SignalQualityReport)
async def signal_quality_report(
    request: Request,
    source: Literal["outcomes", "ledger"] = "outcomes",
    include_operator_labels: bool = False,
) -> SignalQualityReport:
    """Do the advisory numbers predict what a human concluded? Admin plane.

    ADMIN ONLY, AND THERE IS NO ORG-PLANE VARIANT. This report is cross-tenant
    by construction: an organisation must not be able to learn how well the
    fraud screen performs against other organisations' candidates. The honest
    per-org version ("how is it doing on MY pipeline") is a different question
    with its own sample-size problem, and inventing it here would ship a number
    computed from a handful of rows.

    Expect refusals. Below the sample floor, on a one-class sample, or for a
    signal this source cannot score, each signal says so and carries no numbers
    at all -- see app/signal_quality/service.py.
    """
    services = _services(request)
    if source == "ledger":
        label_source = LedgerLabelSource(services.report_store, services.ledger)
    else:
        label_source = OutcomesLabelSource(
            services.report_store, include_operator_labels=include_operator_labels
        )
    return measure(
        label_source,
        min_samples=services.settings.min_signal_quality_samples,
        bins=services.settings.signal_quality_curve_bins,
    )


@router.get("/admin/users", response_model=list[AdminUser])
async def list_admin_users(request: Request) -> list[AdminUser]:
    return [
        a.model_dump(mode="json")
        for a in _services(request).auth.list_admin_users()
    ]


@router.delete("/admin/users/{admin_user_id}", response_model=AdminUserDeletedResponse)
async def delete_admin_user(admin_user_id: str, request: Request) -> AdminUserDeletedResponse:
    """A hard delete: their sessions CASCADE away with them."""
    if not _services(request).auth.delete_admin_user(admin_user_id):
        raise HTTPException(status_code=404, detail="operator not found")
    return {"admin_user_id": admin_user_id, "deleted": True}
