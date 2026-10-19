"""Remaining product handlers and ordered API assembly.

Authentication, report, candidate and screening workflows live in separate API modules.
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
    PUBLIC_PATHS, _rate_limited, _services,
    require_any_principal, require_api_key, require_candidate, require_org,
)
from app.auth.schema import AdminUser
from app.services.email import EmailSendFailed
from app.verification.otp import DeliveryUnavailable
from app.domains.base import get_domain, list_domains
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.ranking import apply_filters, score
from app.features.ranking_schema import FeatureFilter, RankingSpec, SearchResult
from app.features.serving import current_consent_vectors
from app.ratelimit.service import RateLimited
from app.comp import bands
from app.comp.schema import (
    CITY_TIERS, ROLE_FAMILIES, CompBandEstimate, CompBenchmark, SeniorityBand,
)
from app.dashboard.schema import CandidateCard, DashboardOverview, RequisitionBoard
from app.matching.schema import (
    JobRequisition, JobRequisitionInput, MatchResult, RequisitionStatus,
)
from app.ledger.schema import (
    CodingPlatform,
    CodingRoundResult,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    ObservedOffer,
    Organization,
    ReputationAssessment,
)
from app.interview.questions import NothingToAskError
from app.interview.schema import (
    InterviewQuestion, InterviewSession, InterviewSummary,
)
from app.interview.service import AnswerTooLargeError, SessionConflictError
from app.ledger.store import ConsentError
from app.profile_sources.store import SourceSubjectErasedError
from app.curation.schema import (
    CurationAction, CurationDecision, CurationStatus, UnmappedPage,
)
from app.curation.service import AliasConflictError
from app.curation.store import StaleReviewError
from app.portal.schema import AccessLogEntry, ConsentView, MyData
from app.portal.service import PortalSubjectErasedError
from app.retention.schema import SweepReport
from app.retention.sweep import run_sweep
from app.signal_quality.labels import LedgerLabelSource, OutcomesLabelSource
from app.signal_quality.schema import SignalQualityReport
from app.signal_quality.service import measure
from app.rights.schema import (
    CorrectionField, GrievanceContact, RequestAlreadyResolved, RequestKind,
    RequestRefused, RequestStatus, RequestView, ResolvedBy,
    build_grievance_contact,
)
from app.verification.documents import DocumentParseError
from app.verification.schema import (
    CLAIM_REF_MAX_CHARS, ClaimEvidence, DocumentFinding, DocumentType,
    IdentityAssurance, Verification, VerificationMethod, VerificationStatus,
)
from app.verification.service import (
    DestinationError, DocumentTooLargeError, MethodNotPermittedError,
)
from app.verification.store import ChallengeError
from app.screening.pagination import InvalidCursor, clamp_limit
from app.services.llm import NullLLM
from app.services.speech import SpeechFailed, SpeechUnavailable


# ── Response models for what used to be `-> dict` (S8.4 Phase B, Task 13) ────
# MEASURED before this sprint: 38 of 90 operations advertised
# {"type":"object","additionalProperties":true}, which generates
# Record<string, any> and puts every client back to guessing. These models
# describe the bodies that ALREADY EXIST -- not one field was added, removed or
# renamed. Where a shape is shared (an acknowledgement, the auth 202) one model
# is shared, because trading an untyped client for an unreadable one is not a
# trade worth making.


class OrgDeletedResponse(BaseModel):
    org_id: str
    deleted: bool


class AdminUserDeletedResponse(BaseModel):
    admin_user_id: str
    deleted: bool


class ConsentRevokedResponse(BaseModel):
    consent_id: str
    revoked: bool


class OrgKeyResponse(BaseModel):
    """Returned ONCE at issuance; only the hash is stored."""

    org_id: str
    api_key: str


class OrgInterviewAssessments(BaseModel):
    """The org-facing interview read: summaries only, no transcript (S7.3)."""

    attempts: int = 0
    assessments: list[InterviewSummary] = Field(default_factory=list)


class StartVerificationResponse(BaseModel):
    verification: Verification
    #: local env + verif_otp_debug_echo ONLY; production can never echo.
    debug_code: Optional[str] = None


class VerificationListResponse(BaseModel):
    verifications: list[Verification] = Field(default_factory=list)
    assurance: IdentityAssurance
    #: S7.2: a SECOND number beside assurance, never folded into it.
    claims: ClaimEvidence


class DocumentSubmitResponse(BaseModel):
    verification: Verification
    findings: list[DocumentFinding] = Field(default_factory=list)
    claims: ClaimEvidence


class InterviewTurnResponse(BaseModel):
    """The candidate-plane interview body: the session plus what to ask next.
    `next_question` is None when the session is finished."""

    session: InterviewSession
    next_question: Optional[InterviewQuestion] = None


class InterviewListResponse(BaseModel):
    interviews: list[InterviewSummary] = Field(default_factory=list)


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


class OrgCreateRequest(BaseModel):
    name: str


class OrgCreateResponse(BaseModel):
    org: Organization
    api_key: str  # returned once; only its hash is stored


@router.post("/ledger/orgs", response_model=OrgCreateResponse)
async def create_org(req: OrgCreateRequest, request: Request) -> OrgCreateResponse:
    ledger = _services(request).ledger
    try:
        org = ledger.create_organization(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrgCreateResponse(org=org, api_key=ledger.issue_api_key(org.id))


@router.get("/ledger/orgs", response_model=list[Organization])
async def list_orgs(request: Request) -> list[Organization]:
    return _services(request).ledger.list_organizations()


@router.post("/ledger/orgs/{org_id}/api-key", response_model=OrgKeyResponse)
async def rotate_org_key(org_id: str, request: Request) -> OrgKeyResponse:
    try:
        api_key = _services(request).ledger.issue_api_key(org_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"org_id": org_id, "api_key": api_key}


@router.delete("/ledger/orgs/{org_id}", response_model=OrgDeletedResponse)
async def delete_org(org_id: str, request: Request) -> OrgDeletedResponse:
    if not _services(request).ledger.delete_organization(org_id):
        raise HTTPException(status_code=404, detail="organization not found")
    return {"org_id": org_id, "deleted": True}


class ReliabilityRequest(BaseModel):
    weight: float = Field(ge=0.0)


@router.post("/ledger/orgs/{org_id}/reliability", response_model=Organization)
async def set_org_reliability(
    org_id: str, req: ReliabilityRequest, request: Request
) -> Organization:
    """Admin: set an org's per-org reliability multiplier for S3.4 reputation
    aggregation (neutral default 1.0). A negative weight is a 422 at the
    boundary."""
    try:
        return _services(request).ledger.set_org_reliability(org_id, req.weight)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ConsentGrantRequest(BaseModel):
    purpose: ConsentPurpose
    org_id: Optional[str] = None  # None = any member org
    expires_at: Optional[datetime] = None  # None ⇒ default TTL


@router.post("/ledger/candidates/{candidate_id}/consent", response_model=ConsentGrant)
async def grant_consent(
    candidate_id: str, req: ConsentGrantRequest, request: Request
) -> ConsentGrant:
    ledger = _services(request).ledger
    try:
        return ledger.grant_consent(
            candidate_id=candidate_id,
            purpose=req.purpose,
            org_id=req.org_id,
            expires_at=req.expires_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ledger/consent/{consent_id}/revoke", response_model=ConsentRevokedResponse)
async def revoke_consent(consent_id: str, request: Request) -> ConsentRevokedResponse:
    revoked = _services(request).ledger.revoke_consent(consent_id)
    return {"consent_id": consent_id, "revoked": revoked}


@router.get("/ledger/candidates/{candidate_id}/consent", response_model=ConsentDecision)
async def consent_status(
    candidate_id: str, request: Request, org_id: str, purpose: ConsentPurpose
) -> ConsentDecision:
    try:
        return _services(request).ledger.consent_status(
            candidate_id, org_id=org_id, purpose=purpose
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Compose already-scoped screening routes at their original org-plane position.
org_router.routes.extend(screening_router.routes)


class RecordSubmitRequest(BaseModel):
    candidate_id: str
    stage: InterviewStage
    outcome: InterviewOutcome
    interviewed_at: datetime
    summary: Optional[str] = None


@org_router.post("/ledger/records", response_model=InterviewRecord)
async def submit_record(
    req: RecordSubmitRequest, request: Request, org_id: str = Depends(require_org)
) -> InterviewRecord:
    ledger = _services(request).ledger
    try:
        return ledger.submit_interview_record(
            org_id=org_id,
            candidate_id=req.candidate_id,
            stage=req.stage,
            outcome=req.outcome,
            interviewed_at=req.interviewed_at,
            summary=req.summary,
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class EventAppendRequest(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)


@org_router.post("/ledger/records/{record_id}/events", response_model=EvaluationEvent)
async def append_event(
    record_id: str,
    req: EventAppendRequest,
    request: Request,
    org_id: str = Depends(require_org),
) -> EvaluationEvent:
    ledger = _services(request).ledger
    record = ledger.get_record(record_id)
    if record is None or record.org_id != org_id:
        raise HTTPException(status_code=404, detail="record not found")
    return ledger.append_event(record_id, event_type=req.event_type, payload=req.payload)


@org_router.get(
    "/ledger/candidates/{candidate_id}/records", response_model=list[InterviewRecord]
)
async def query_records(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> list[InterviewRecord]:
    """Query-time ledger_read enforcement. The store audits every attempt."""
    ledger = _services(request).ledger
    try:
        return ledger.query_records_for_org(org_id=org_id, candidate_id=candidate_id)
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CodingRoundSubmitRequest(BaseModel):
    candidate_id: str
    platform: CodingPlatform
    score: float = Field(ge=0)
    taken_at: datetime
    assessment_name: Optional[str] = None
    platform_name: Optional[str] = None
    max_score: Optional[float] = Field(default=None, ge=0)
    percentile: Optional[float] = Field(default=None, ge=0, le=100)
    problem_tags: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)


@org_router.post("/ledger/coding-rounds", response_model=CodingRoundResult)
async def submit_coding_round(
    req: CodingRoundSubmitRequest, request: Request, org_id: str = Depends(require_org)
) -> CodingRoundResult:
    ledger = _services(request).ledger
    try:
        return ledger.submit_coding_round(
            org_id=org_id,
            candidate_id=req.candidate_id,
            platform=req.platform,
            score=req.score,
            taken_at=req.taken_at,
            assessment_name=req.assessment_name,
            platform_name=req.platform_name,
            max_score=req.max_score,
            percentile=req.percentile,
            problem_tags=req.problem_tags,
            raw=req.raw,
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@org_router.get(
    "/ledger/candidates/{candidate_id}/coding-rounds",
    response_model=list[CodingRoundResult],
)
async def query_coding_rounds(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> list[CodingRoundResult]:
    """Query-time ledger_read enforcement. The store audits every attempt."""
    ledger = _services(request).ledger
    try:
        return ledger.query_coding_rounds_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@org_router.get(
    "/ledger/candidates/{candidate_id}/reputation",
    response_model=ReputationAssessment,
)
async def candidate_reputation(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> ReputationAssessment:
    """Advisory cross-company reputation. Query-time ledger_read enforcement;
    the store audits every attempt. Never a rejection signal."""
    ledger = _services(request).ledger
    try:
        return ledger.reputation_for_org(org_id=org_id, candidate_id=candidate_id)
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Demand side: job requisitions + role-conditioned matching (S5.1) ─────────
# Org plane (X-Org-Key). Requisitions are org-owned; match is advisory and
# audits every surfaced candidate as a disclosure. Consent was masked at S4.2.


class JobUpdateRequest(BaseModel):
    status: Optional[RequisitionStatus] = None
    spec: Optional[JobRequisitionInput] = None


class JobMatchRequest(BaseModel):
    as_of: Optional[datetime] = None
    limit: Optional[int] = Field(default=None, ge=1)


@org_router.post("/jobs", response_model=JobRequisition)
async def create_job(
    req: JobRequisitionInput, request: Request, org_id: str = Depends(require_org)
) -> JobRequisition:
    try:
        return _services(request).jobs.create_requisition(org_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@org_router.get("/jobs", response_model=list[JobRequisition])
async def list_jobs(request: Request, org_id: str = Depends(require_org)) -> list[JobRequisition]:
    return _services(request).jobs.list_requisitions(org_id)


@org_router.get("/jobs/{req_id}", response_model=JobRequisition)
async def get_job(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> JobRequisition:
    r = _services(request).jobs.get_requisition(org_id, req_id)
    if r is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    return r


@org_router.patch("/jobs/{req_id}", response_model=JobRequisition)
async def update_job(
    req_id: str, body: JobUpdateRequest, request: Request, org_id: str = Depends(require_org)
) -> JobRequisition:
    try:
        r = _services(request).jobs.update_requisition(
            org_id, req_id, status=body.status, spec=body.spec
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if r is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    return r


@org_router.post(
    "/jobs/{req_id}/match",
    response_model=MatchResult,
    description=(
        "Top-N advisory ranking. NOT paginated: the pool is re-ranked on every request, so there is no stable key to page on and a cursor would promise an ordering this endpoint cannot keep. Use `limit`."
    ),
)
async def match_job(
    req_id: str, body: JobMatchRequest, request: Request, org_id: str = Depends(require_org)
) -> MatchResult:
    jobs = _services(request).jobs
    try:
        result = jobs.run_match(org_id, req_id, as_of=body.as_of, limit=body.limit)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    if result.pool_size == 0:
        # 200, not 422: an empty feature store is a server-side state and the
        # caller cannot fix it. Mirrors GET /candidates/{id}/card's
        # 200-with-status pattern (SCREENING.md (batch processing)).
        return result.model_copy(update={"reason": "no_materialized_candidates"})
    return result


# ── Comp intelligence (S5.2) ─────────────────────────────────────────────────
# Org plane (X-Org-Key). Advisory static bands blended with consent-gated
# ledger-observed offers. Submit an offer, estimate a role, benchmark a req.


class OfferSubmitRequest(BaseModel):
    candidate_id: str
    role_family: str
    seniority: SeniorityBand
    city_tier: str
    ctc_fixed: float = Field(ge=0)
    ctc_variable: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    offered_at: datetime


@org_router.post("/ledger/offers", response_model=ObservedOffer)
async def submit_offer(
    req: OfferSubmitRequest, request: Request, org_id: str = Depends(require_org)
) -> ObservedOffer:
    if req.role_family not in ROLE_FAMILIES or req.city_tier not in CITY_TIERS:
        raise HTTPException(status_code=400, detail="invalid role_family or city_tier")
    ledger = _services(request).ledger
    try:
        return ledger.submit_observed_offer(
            org_id=org_id, candidate_id=req.candidate_id, role_family=req.role_family,
            seniority=req.seniority.value, city_tier=req.city_tier,
            ctc_fixed=req.ctc_fixed, ctc_variable=req.ctc_variable,
            currency=req.currency, offered_at=req.offered_at,
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CompEstimateRequest(BaseModel):
    skills: tuple[str, ...] = ()
    title: Optional[str] = None
    years_experience: Optional[float] = Field(default=None, ge=0)
    location_tiers: Optional[tuple[str, ...]] = None
    remote: bool = False
    role_family: Optional[str] = None
    seniority: Optional[SeniorityBand] = None


@org_router.post("/comp/estimate", response_model=CompBenchmark)
async def comp_estimate(
    body: CompEstimateRequest, request: Request, org_id: str = Depends(require_org)
) -> CompBenchmark:
    """One shape from both comp endpoints (S8.4 Phase B §1.12).

    `GET /jobs/{id}/comp` has always returned a CompBenchmark WRAPPING the
    estimate; this returned the bare estimate, and during the UI wiring session
    assuming one shape rendered a band made entirely of dashes. The three
    positioning fields are None because there is no requisition to position
    against -- honest, where a 0.0 would read as 'exactly at market'.
    """
    services = _services(request)
    try:
        signal = bands.role_signal_from_input(
            skills=body.skills, title=body.title, years=body.years_experience,
            location_tiers=body.location_tiers, remote=body.remote,
            role_family=body.role_family, seniority=body.seniority, settings=services.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CompBenchmark(
        estimate=services.comp.estimate(signal, org_id=org_id),
        requisition_band=None, position=None, delta_pct=None,
        reasoning="ad-hoc estimate: no requisition to position against",
    )


@org_router.get("/jobs/{req_id}/comp", response_model=CompBenchmark)
async def job_comp(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> CompBenchmark:
    services = _services(request)
    req = services.jobs.get_requisition(org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    return services.comp.benchmark(req, org_id=org_id)


# ── Employer dashboard (S5.3) ────────────────────────────────────────────────
# Org plane (X-Org-Key). Read-only composition over jobs/comp/ledger. Advisory;
# no new state, no new consent purpose, no new audit path (the card reuses the
# ledger's already-audited reads and degrades per section on missing consent).


@org_router.get("/dashboard/overview", response_model=DashboardOverview)
async def dashboard_overview(
    request: Request, org_id: str = Depends(require_org)
) -> DashboardOverview:
    return _services(request).dashboard.overview(org_id)


@org_router.get("/jobs/{req_id}/board", response_model=RequisitionBoard)
async def job_board(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> RequisitionBoard:
    board = _services(request).dashboard.board(org_id, req_id)
    if board is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    if board.match.pool_size == 0:
        # The SAME change as match_job above, in the same commit: fixing one
        # entry point and leaving the other is this repo's signature defect.
        board = board.model_copy(update={
            "match": board.match.model_copy(
                update={"reason": "no_materialized_candidates"}
            )
        })
    return board


@org_router.get("/candidates/{candidate_id}/card", response_model=CandidateCard)
async def candidate_card(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> CandidateCard:
    try:
        return _services(request).dashboard.card(org_id, candidate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Candidate DPDP portal (S6.4) ─────────────────────────────────────────────
# Candidate plane (X-Candidate-Key). First-party access / transparency / consent
# control / erasure over the candidate's own data. No new ConsentPurpose — auth
# == identity of the data subject. Every route acts on the resolved candidate_id.


@candidate_router.get("/portal/me", response_model=MyData)
async def portal_me(request: Request, candidate_id: str = Depends(require_candidate)) -> MyData:
    try:
        return _services(request).portal.my_data(candidate_id)
    except (PortalSubjectErasedError, SourceSubjectErasedError):
        raise HTTPException(status_code=404, detail="candidate not found") from None


@candidate_router.get("/portal/access-log", response_model=list[AccessLogEntry])
async def portal_access_log(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[AccessLogEntry]:
    try:
        return _services(request).portal.access_log(candidate_id)
    except PortalSubjectErasedError:
        raise HTTPException(status_code=404, detail="candidate not found") from None


@candidate_router.get("/portal/consents", response_model=list[ConsentView])
async def portal_list_consents(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[ConsentView]:
    try:
        return _services(request).portal.consents(candidate_id)
    except PortalSubjectErasedError:
        raise HTTPException(status_code=404, detail="candidate not found") from None


class PortalConsentGrantRequest(BaseModel):
    purpose: ConsentPurpose
    org_id: Optional[str] = None
    expires_at: Optional[datetime] = None


@candidate_router.post("/portal/consents", response_model=ConsentGrant)
async def portal_grant_consent(
    req: PortalConsentGrantRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> ConsentGrant:
    try:
        return _services(request).portal.grant(
            candidate_id, purpose=req.purpose, org_id=req.org_id, expires_at=req.expires_at
        )
    except LookupError as exc:  # unknown org_id
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@candidate_router.post("/portal/consents/{consent_id}/revoke", response_model=ConsentRevokedResponse)
async def portal_revoke_consent(
    consent_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> ConsentRevokedResponse:
    try:
        revoked = _services(request).portal.revoke(candidate_id, consent_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="consent grant not found") from exc
    return {"consent_id": consent_id, "revoked": revoked}


class CorrectionSubmitRequest(BaseModel):
    """`field` is the enum, so a field nobody implemented is a 422 from the
    model before any handler runs."""

    field: CorrectionField
    requested_value: str = ""
    note: str = ""


class GrievanceSubmitRequest(BaseModel):
    note: str = ""


@candidate_router.post("/portal/corrections", response_model=RequestView)
async def portal_submit_correction(
    req: CorrectionSubmitRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> RequestView:
    """File a correction request. It is REVIEWED, never applied on submission.

    On a fraud-screening platform, a subject write path onto the data the risk
    score is computed from is an edit box over the evidence (spec 0.3). What
    DPDP requires is the mechanism, and the mechanism starts here.
    """
    try:
        return _services(request).rights.submit(
            candidate_id,
            kind=RequestKind.CORRECTION,
            field=req.field,
            requested_value=req.requested_value,
            note=req.note,
            now=datetime.now(timezone.utc),
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    except RequestRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        # The subject erased themselves mid-call. 404, which by then is true.
        raise HTTPException(status_code=404, detail="candidate not found") from exc


@candidate_router.post("/portal/grievances", response_model=RequestView)
async def portal_submit_grievance(
    req: GrievanceSubmitRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> RequestView:
    try:
        return _services(request).rights.submit(
            candidate_id,
            kind=RequestKind.GRIEVANCE,
            field=None,
            requested_value="",
            note=req.note,
            now=datetime.now(timezone.utc),
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    except RequestRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        # The subject erased themselves mid-call. 404, which by then is true.
        raise HTTPException(status_code=404, detail="candidate not found") from exc


@candidate_router.get("/portal/requests", response_model=list[RequestView])
async def portal_list_requests(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[RequestView]:
    """The subject's own requests, both kinds. Cross-candidate isolation is
    structural: the id comes from the resolver, never from a query param."""
    return _services(request).rights.for_candidate(candidate_id)


@candidate_router.delete("/portal/me", response_model=ErasureResponse)
async def portal_erase(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> ErasureResponse:
    """DPDP erasure, self-service.

    The SAME service call the admin plane makes, deliberately: erasure now has
    two entry points and every step -- the report count, the login challenges
    that cannot cascade, the candidate row itself -- lives in
    ``PortalService.erase`` so neither door can forget what the other does.

    Afterwards both the access key and every session stop authenticating: the
    credential and ``auth_sessions`` both CASCADE with the candidate row.
    """
    return _services(request).portal.erase(candidate_id)


# ── Identity verification, candidate plane (S7.1) ───────────────────────────
# Candidate-initiated by design. Every handler resolves candidate_id from the
# key — never a path/body param — so cross-candidate isolation is structural.


class StartVerificationRequest(BaseModel):
    """`destination` is required for OTP methods and must match the contact
    hash already on the candidate's record."""

    method: VerificationMethod
    destination: str | None = None


class ConfirmVerificationRequest(BaseModel):
    code: str


class ManualReviewRequest(BaseModel):
    """Operator-recorded verification outcome. `evidence_digest` is a hash of
    whatever was checked out of band -- never the artifact itself."""

    outcome: VerificationStatus
    note: str | None = None
    evidence_digest: str | None = None


@candidate_router.post("/portal/verifications", response_model=StartVerificationResponse)
async def start_verification(
    req: StartVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> StartVerificationResponse:
    services = _services(request)
    try:
        verification, code = services.verification.start(
            candidate_id, req.method, destination=req.destination
        )
    except DeliveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from None
    except EmailSendFailed:
        raise HTTPException(status_code=503, detail="email_send_failed") from None
    except DestinationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MethodNotPermittedError as exc:  # e.g. self-awarding a manual review
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ChallengeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    body: dict = {"verification": verification.model_dump(mode="json")}
    # Double-guarded: local env AND the knob. Exists so the sprint smoke can
    # drive the two-step flow over plain HTTP; production can never echo.
    if (
        code is not None
        and services.settings.env == "local"
        and services.settings.verif_otp_debug_echo
    ):
        body["debug_code"] = code
    return body


@candidate_router.post("/portal/verifications/{verification_id}/confirm", response_model=Verification)
async def confirm_verification(
    verification_id: str,
    req: ConfirmVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> Verification:
    services = _services(request)
    try:
        verification = services.verification.confirm(
            candidate_id, verification_id, req.code
        )
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="verification not found") from exc
    except ChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return verification.model_dump(mode="json")


@candidate_router.get("/portal/verifications", response_model=VerificationListResponse)
async def list_verifications(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> VerificationListResponse:
    services = _services(request)
    verifications, assurance = services.verification.list_for_candidate(candidate_id)
    return {
        "verifications": [v.model_dump(mode="json") for v in verifications],
        "assurance": assurance.model_dump(mode="json"),
        # S7.2: a SECOND number beside the first, never folded into it.
        "claims": services.verification.claims_for_candidate(
            candidate_id
        ).model_dump(mode="json"),
    }


@org_router.get("/verification/candidates/{candidate_id}/assurance", response_model=IdentityAssurance)
async def org_candidate_assurance(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> IdentityAssurance:
    """Consent-gated identity assurance. Every attempt — allowed or denied — is
    audited by the store. Returns the advisory roll-up only: never the evidence
    digests, the destination hashes, or the individual attempt rows."""
    try:
        assurance = _services(request).verification.assurance_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return assurance.model_dump(mode="json")


# ── Employment-claim documents, candidate plane (S7.2) ──────────────────────
# First-party intake: the candidate submits their OWN letter or payslip. The
# document is parsed in memory and discarded — only a sha256 digest and finding
# CODES survive the request. Org-supplied documents ABOUT a candidate are
# third-party data under DPDP and are deliberately out of scope.


class SubmitDocumentRequest(BaseModel):
    """`content_b64` is a base64 PDF or plain-text body. It is parsed in memory
    and discarded -- only a sha256 digest and finding CODES are stored.
    `claim_ref` is a free-text LABEL (employer + interval), never a selector:
    the candidate is always resolved from the key."""

    doc_type: DocumentType
    content_b64: str
    # Bounded to the column width: SQLite would happily store a whole document
    # in an unbounded VARCHAR(128), and this table's design claim is that no
    # column can hold one. The service enforces the same cap for non-HTTP
    # callers.
    claim_ref: str | None = Field(default=None, max_length=CLAIM_REF_MAX_CHARS)


@candidate_router.post("/portal/documents", response_model=DocumentSubmitResponse)
async def submit_document(
    req: SubmitDocumentRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> DocumentSubmitResponse:
    services = _services(request)
    try:
        verification, findings, claims = services.verification.submit_document(
            candidate_id, req.doc_type, req.content_b64, claim_ref=req.claim_ref
        )
    except DocumentTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MethodNotPermittedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "verification": verification.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in findings],
        "claims": claims.model_dump(mode="json"),
    }


@org_router.get("/verification/candidates/{candidate_id}/claims", response_model=ClaimEvidence)
async def org_candidate_claims(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> ClaimEvidence:
    """Consent-gated employment-claim evidence. Every attempt — allowed or
    denied — is audited by the store. Returns the advisory roll-up only: never
    an evidence digest, never a claim_ref, never a document."""
    try:
        claims = _services(request).verification.claims_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return claims.model_dump(mode="json")


# ── AI interviews, candidate plane (S7.3) ───────────────────────────────────
# The interview asks the depth report's OWN probes. Every handler resolves the
# candidate from the key, never a path or body param. Audio is transcribed in
# memory and discarded (only a sha256 digest survives); the TRANSCRIPT is kept
# and is the candidate's to read here — it is never in an org payload.


class StartInterviewRequest(BaseModel):
    domain: str = "genai"


class SubmitAnswerRequest(BaseModel):
    """Exactly one of `text` / `audio_b64`. `question_id` is REQUIRED: an answer
    must name the question it answers, so two racing clients cannot collapse
    into one turn (409 on a mismatch)."""

    question_id: str
    text: str | None = None
    audio_b64: str | None = None
    mime: str | None = None


def _interview_body(session, following) -> InterviewTurnResponse:
    return InterviewTurnResponse(session=session, next_question=following)


@candidate_router.post("/portal/interviews", response_model=InterviewTurnResponse)
async def start_interview(
    req: StartInterviewRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> InterviewTurnResponse:
    services = _services(request)
    try:
        session = services.interview.start(candidate_id, domain_key=req.domain)
    except NothingToAskError as exc:   # nothing on file worth asking about
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:            # unknown domain key
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _interview_body(session, services.interview.next_question(session))


@candidate_router.get("/portal/interviews", response_model=InterviewListResponse)
async def list_interviews(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> InterviewListResponse:
    summaries = _services(request).interview.list_for_candidate(candidate_id)
    return {"interviews": [s.model_dump(mode="json") for s in summaries]}


@candidate_router.get("/portal/interviews/{session_id}", response_model=InterviewTurnResponse)
async def get_interview(
    session_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> InterviewTurnResponse:
    """The candidate's own full view — transcripts included. It is their data,
    and an advisory score whose basis they cannot read is not advisory."""
    services = _services(request)
    try:
        session = services.interview.get(candidate_id, session_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="interview not found") from exc
    return _interview_body(session, services.interview.next_question(session))


@candidate_router.post("/portal/interviews/{session_id}/answers", response_model=InterviewTurnResponse)
async def submit_answer(
    session_id: str,
    req: SubmitAnswerRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> InterviewTurnResponse:
    services = _services(request)
    try:
        session, following = await services.interview.answer(
            candidate_id, session_id, question_id=req.question_id,
            text=req.text, audio_b64=req.audio_b64, mime=req.mime,
        )
    except RateLimited as exc:
        # Audio answers only (S8.3): the ASR path is the S7.3 review's named
        # spend surface. A typed answer is never refused here.
        raise _rate_limited(exc) from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AnswerTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpeechUnavailable as exc:
        # The designed no-key path, said out loud: answer in text instead.
        raise HTTPException(
            status_code=422, detail="speech_unavailable: answer this question in text"
        ) from exc
    except SpeechFailed as exc:
        # Nothing was recorded, so retrying costs the candidate nothing.
        raise HTTPException(status_code=422, detail="speech_failed: no answer saved; record again or answer in text") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interview not found") from exc
    except ValueError as exc:          # no body, or bad base64
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _interview_body(session, following)


@candidate_router.post("/portal/interviews/{session_id}/finish", response_model=InterviewTurnResponse)
async def finish_interview(
    session_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> InterviewTurnResponse:
    services = _services(request)
    try:
        session = services.interview.finish(candidate_id, session_id)
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interview not found") from exc
    return _interview_body(session, None)


@org_router.get("/interview/candidates/{candidate_id}/assessments", response_model=OrgInterviewAssessments)
async def org_candidate_interviews(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> OrgInterviewAssessments:
    """Consent-gated interview assessments (INTERVIEW_READ — a new purpose, not
    a widening of verification_read). Every attempt — allowed or denied — is
    audited by the store. Headers only: bands, dimensions, proxy band,
    timestamps. NEVER the candidate's words."""
    try:
        summaries = _services(request).interview.assessments_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "attempts": len(summaries),
        "assessments": [s.model_dump(mode="json") for s in summaries],
    }


@router.post("/candidates/{candidate_id}/verifications/manual-review", response_model=Verification)
async def record_manual_review(
    candidate_id: str, req: ManualReviewRequest, request: Request
) -> Verification:
    """Admin plane: an operator checked something out of band (L3 REVIEWED).
    Only a digest of what was checked is stored, never the artifact."""
    try:
        verification = _services(request).verification.record_manual_review(
            candidate_id,
            outcome=req.outcome,
            note=req.note,
            evidence_digest=req.evidence_digest,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return verification.model_dump(mode="json")


# ── Talent search / ranking (S4.3) ──────────────────────────────────────────
# Admin plane (X-API-Key): platform-internal search over materialized feature
# vectors. Advisory — it narrows and orders, never auto-rejects.


class TalentSearchRequest(BaseModel):
    """Advisory talent search over materialized feature vectors (admin plane).

    ``ranking`` is required and non-empty. ``view_name``/``view_version`` default
    to the materialized default view; ``as_of`` defaults to its newest cut. Only
    the features referenced in ``filters``/``ranking`` are validated against the
    registry.
    """

    ranking: RankingSpec
    filters: list[FeatureFilter] = Field(default_factory=list)
    view_name: Optional[str] = None
    view_version: Optional[int] = None
    as_of: Optional[datetime] = None
    limit: Optional[int] = Field(default=None, ge=1)


@router.post(
    "/talent/search",
    response_model=SearchResult,
    description=(
        "Top-N advisory ranking. NOT paginated: the pool is re-ranked on every request, so there is no stable key to page on and a cursor would promise an ordering this endpoint cannot keep. Use `limit`."
    ),
)
async def talent_search(req: TalentSearchRequest, request: Request) -> SearchResult:
    """Filter + rank the materialized pool by a composite score. Advisory: it
    narrows and orders, never auto-rejects. Current platform ledger_read consent
    masks gated values before filters and scoring, independently of as_of."""
    services = _services(request)
    registry = get_feature_registry()

    # Resolve specs per referenced feature; an unknown name is a 400.
    referenced = {t.feature for t in req.ranking.terms} | {f.feature for f in req.filters}
    specs_by_name = {}
    for name in referenced:
        try:
            specs_by_name[name] = registry.get(name).spec
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    view_name = req.view_name or services.settings.feat_default_view
    view_version = (
        req.view_version
        if req.view_version is not None
        else default_view(registry, settings=services.settings).version
    )
    as_of = req.as_of or services.features.latest_as_of(view_name, view_version)

    pool = (
        services.features.latest_vectors_for_view(view_name, view_version, as_of=as_of)
        if as_of is not None
        else []
    )
    vectors = current_consent_vectors(
        [mv.vector for mv in pool], registry=registry, ledger_store=services.ledger,
    )

    try:
        filtered = apply_filters(vectors, req.filters, specs_by_name)
        ranked = score(filtered, req.ranking, specs_by_name)
    except (ValueError, KeyError, TypeError) as exc:
        # TypeError: a filter value whose type can't be compared to the feature
        # (e.g. a numeric feature vs a string) — a client error, not a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    limit = req.limit or services.settings.search_default_limit
    return SearchResult(
        advisory=True,
        as_of=as_of,
        view_name=view_name,
        view_version=view_version,
        pool_size=len(vectors),
        filtered_size=len(filtered),
        ranked=tuple(ranked[:limit]),
    )


class MaterializeRequest(BaseModel):
    candidate_ids: Optional[list[str]] = None
    as_of: Optional[datetime] = None
    view_name: Optional[str] = None


class MaterializeResponse(BaseModel):
    view_name: str
    view_version: int
    as_of: Optional[datetime] = None
    materialized: int = 0
    skipped: int = 0


@router.post("/features/materialize", response_model=MaterializeResponse)
async def materialize_features(
    body: MaterializeRequest, request: Request
) -> MaterializeResponse:
    """Compute + persist feature vectors. ADMIN plane, deliberately.

    Materialization spans ALL candidates and is consent-masked per candidate
    (S4.2), so on the org plane one customer's call would compute vectors over
    every customer's people. It is an operator action.

    Until this route existed, `app/features/materialize.py` was reachable only
    from Python -- which made `GET /jobs/{id}/board`'s empty-pool state
    permanent for a self-registered org rather than transient.
    """
    services = _services(request)
    registry = get_feature_registry()
    view = default_view(registry, settings=services.settings)
    # Only the default view exists today. Refusing an unknown name is honest;
    # accepting it, materializing the default anyway and echoing the caller's
    # name back was a response claiming work that never happened.
    if body.view_name is not None and body.view_name != view.name:
        raise HTTPException(
            status_code=422,
            detail=f"unknown view '{body.view_name}'; only '{view.name}' exists",
        )

    ids = body.candidate_ids
    if ids is None:
        ids = services.candidates.list_candidate_ids(
            services.settings.materialize_max_candidates
        )

    snapshot_time = body.as_of if body.as_of is not None else datetime.now(timezone.utc)
    materialized = skipped = 0
    for candidate_id in ids:
        mv = materialize_candidate(
            candidate_id, view=view, registry=registry, as_of=snapshot_time,
            candidate_store=services.candidates,
            report_store=services.report_store,
            ledger_store=services.ledger,
        )
        if mv is None:
            # No context for this candidate (unknown id, or nothing to compute).
            skipped += 1
            continue
        if services.features.upsert_vector(mv) is None:
            # Erasure after computation is a skipped subject, like a missing ID.
            skipped += 1
        else:
            materialized += 1

    return MaterializeResponse(
        view_name=view.name, view_version=view.version, as_of=snapshot_time,
        materialized=materialized, skipped=skipped,
    )


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


class ResolveRequest(BaseModel):
    """One operator decision.

    `apply` defaults to FALSE. Recording a decision is the common case and the
    safe one; writing onto a person's identity row is the exception, and the
    exception is the one that should have to be asked for.
    """

    status: RequestStatus
    resolution: str = ""
    apply: bool = False


@router.get("/admin/requests", response_model=list[RequestView])
async def list_data_principal_requests(
    request: Request,
    status: Optional[RequestStatus] = None,
    limit: Optional[int] = None,
) -> list[RequestView]:
    """The operator's queue, OLDEST first -- a complaint that has waited
    longest is the one that should be answered next.

    Not tenant-scoped, deliberately: an operator handling DPDP requests has to
    see the queue, not one organisation's slice of it. These are requests from
    data principals to the PLATFORM, and no org is a party to them.

    `limit` goes through `clamp_limit`, the same helper every other paged read
    uses. It took a raw int until the Phase B review: `?limit=-1` reaches
    SQLite as an UNLIMITED select, so a bound that looked present returned the
    whole table -- of every data principal's complaints, free text included.
    """
    services = _services(request)
    try:
        bounded = clamp_limit(limit, services.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return services.rights.list_by_status(status, bounded)


@router.post("/admin/requests/{request_id}/resolve", response_model=RequestView)
async def resolve_data_principal_request(
    request_id: str, req: ResolveRequest, request: Request
) -> RequestView:
    """Decide one request, and record who decided.

    THREE outcomes, three statuses, picked by exception TYPE and never by
    matching on message text -- a translation keyed on wording breaks the first
    time somebody rewords a sentence. The `except` clauses are ordered
    subclass-first, or the 409 would be unreachable: RequestAlreadyResolved IS
    a RequestRefused.
    """
    services = _services(request)
    principal = request.state.principal
    admin_user_id = principal.admin_user_id if principal else None
    try:
        return services.rights.resolve(
            request_id,
            status=req.status,
            resolution=req.resolution,
            apply=req.apply,
            # A machine key has no human behind it. Recording OPERATOR_KEY
            # rather than leaving a bare NULL is what keeps "the shared
            # credential did this" distinguishable from "the admin who did has
            # since been deleted" (the S8.5 recorded_by argument).
            resolved_by=(
                ResolvedBy.ADMIN_USER if admin_user_id else ResolvedBy.OPERATOR_KEY
            ),
            admin_user_id=admin_user_id,
            now=datetime.now(timezone.utc),
        )
    except RequestAlreadyResolved as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RequestRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="request not found") from exc


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
