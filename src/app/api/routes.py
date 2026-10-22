"""Remaining product handlers and ordered API assembly.

Auth, reports, candidates, screening, ledger, employer, features, portal, verification,
interviews, curation and operator tools have API modules.
Shared request/auth dependencies keep the same principal and CSRF boundaries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app import __version__
# Compatibility aliases retain callable identity for existing route guards.
from app.api.auth import auth_router
from app.api.curation import router as curation_router
from app.api.operator import (
    metrics_router as operator_metrics_router, retention_router as operator_retention_router,
    router as operator_router,
)
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
from app.domains.base import get_domain, list_domains
from app.profile_sources.store import SourceSubjectErasedError
from app.rights.schema import (
    GrievanceContact, build_grievance_contact,
)
from app.services.llm import NullLLM


# ── Response models for what used to be `-> dict` (S8.4 Phase B, Task 13) ────
# MEASURED before this sprint: 38 of 90 operations advertised
# {"type":"object","additionalProperties":true}, which generates
# Record<string, any> and puts every client back to guessing. These models
# describe the bodies that ALREADY EXIST -- not one field was added, removed or
# renamed. Where a shape is shared (an acknowledgement, the auth 202) one model
# is shared, because trading an untyped client for an unreadable one is not a
# trade worth making.


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


router.routes.extend(curation_router.routes)


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


router.routes.extend(operator_metrics_router.routes)


router.routes.extend(portal_admin_router.routes)


router.routes.extend(operator_retention_router.routes)


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


router.routes.extend(operator_router.routes)
