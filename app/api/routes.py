"""HTTP surface: evaluate, fetch reports, and record human outcomes.

Every response is ADVISORY with human_review_required=True — the engine never
auto-rejects. Reports are persisted through the injected ReportStore; human
outcomes close the flywheel loop (claim → probe → verdict → OUTCOME).
"""

from __future__ import annotations

import base64
import binascii
import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator

from app import __version__
from app.auth.csrf import csrf_matches
from app.auth.schema import (
    AuthPlane, LoginPurpose, Principal, PrincipalKind, PrincipalVia, SessionView,
)
from app.auth.service import (
    ChallengeRefused, EmailUnavailableError, RegistrationRefused,
)
from app.candidates.extractor import extract_profile
from app.candidates.schema import CandidateProfile
from app.candidates.store import MatchedOn, ResumeSummary
from app.core.pdf import pdf_b64_to_text
from app.domains.base import get_domain, list_domains
from app.fabrication.similarity import assess_resume_farm, fingerprint_text
from app.features import default_view, get_feature_registry
from app.features.ranking import apply_filters, score
from app.features.ranking_schema import FeatureFilter, RankingSpec, SearchResult
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
from app.interview.service import AnswerTooLargeError, SessionConflictError
from app.ledger.store import ConsentError
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm
from app.portal.schema import AccessLogEntry, ConsentView, MyData
from app.verification.documents import DocumentParseError
from app.verification.schema import (
    CLAIM_REF_MAX_CHARS, DocumentType, VerificationMethod, VerificationStatus,
)
from app.verification.service import (
    DestinationError, DocumentTooLargeError, MethodNotPermittedError,
)
from app.verification.store import ChallengeError
from app.schemas.fabrication import ResumeFarmAssessment
from app.schemas.report import Report
from app.screening.projection import redact_ingest_response_for_org
from app.services import Services
from app.services.llm import NullLLM
from app.services.speech import SpeechFailed, SpeechUnavailable
from app.reports.schema import OutcomeLabel, OutcomeRecord
from app.reports.store import SubjectErasedError


def _services(request: Request) -> Services:
    return request.app.state.services


# Paths that establish no principal, by definition. Everything else must go
# through one of the four resolvers below, and tests/test_route_table_guard.py
# fails the build if it does not. WIDENING THIS SET IS THE REVIEWABLE ACT —
# it is how "someone forgot a gate" becomes "someone edited a named list".
PUBLIC_PATHS: set[str] = {
    "/", "/healthz", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json",
    "/auth/org/signup", "/auth/org/login", "/auth/org/verify",
    "/auth/candidate/signup", "/auth/candidate/login", "/auth/candidate/verify",
    "/auth/admin/login", "/auth/admin/verify",
}


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _accept(request: Request, principal: Principal) -> Principal:
    """Record the principal and enforce CSRF in ONE place.

    CSRF lives inside the resolvers rather than beside them as its own
    dependency, and that is a correctness decision, not tidiness: FastAPI runs
    router-level dependencies BEFORE route-level ones, so a separate
    ``Depends(require_csrf)`` on ``org_router`` would execute before
    ``require_org`` had established the principal, read ``via`` as unset, and
    skip the check on every request — a fail-open that tests using cookies
    would never notice. Here the ordering cannot be got wrong.

    The exemption keys on ``principal.via``, NEVER on "was a header present":
    otherwise a browser carrying a session cookie plus an attacker-supplied
    ``X-Org-Key`` would skip CSRF entirely. ``AuthService.resolve`` prefers the
    session when both arrive, so the stronger requirement always wins.
    """
    request.state.principal = principal
    if request.method not in _SAFE_METHODS and principal.via == PrincipalVia.SESSION:
        settings = _services(request).settings
        if not csrf_matches(
            request.cookies.get(settings.csrf_cookie_name),
            request.headers.get("X-CSRF-Token"),
        ):
            raise HTTPException(
                status_code=403, detail="missing or invalid CSRF token"
            )
    return principal


async def require_api_key(request: Request) -> Principal:
    """Admin-plane gate (FR-15). Fail-CLOSED since S8.1; session-capable since S8.2.

    Since S8.2 every plane resolves through ONE service call, so a gate cannot
    be forgotten at a second door — the bug shape that shipped as a real defect
    in S7.1, S7.2 and S7.3, and which sessions would otherwise multiply by two.

    An unset ``DEE_API_AUTH_KEY`` is still the MOST refusing state (enforced in
    ``AuthService._from_key``), and ``verify_launch_config`` stops the process
    before it can serve in that state at all.
    """
    principal = _services(request).auth.resolve(
        kind=PrincipalKind.ADMIN,
        session_token=_session_cookie(request),
        header_key=request.headers.get("X-API-Key"),
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing admin credential")
    return _accept(request, principal)


async def require_org(request: Request) -> str:
    """Resolve the caller to ONE organization (S3.2), by session or by key.

    The return type is unchanged — every handler still receives ``org_id: str``
    — which is why sessions reached all 63 endpoints without editing one.
    """
    principal = _services(request).auth.resolve(
        kind=PrincipalKind.ORG,
        session_token=_session_cookie(request),
        header_key=request.headers.get("X-Org-Key"),
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing X-Org-Key")
    return _accept(request, principal).org_id


async def require_candidate(request: Request) -> str:
    """Resolve the caller to ONE candidate (S6.4), by session or by key.

    Always enforced — the portal is the data principal's private surface, and
    cross-candidate isolation stays structural because handlers still receive
    the id from here rather than from a path or body param.
    """
    principal = _services(request).auth.resolve(
        kind=PrincipalKind.CANDIDATE,
        session_token=_session_cookie(request),
        header_key=request.headers.get("X-Candidate-Key"),
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing X-Candidate-Key")
    return _accept(request, principal).candidate_id


async def require_any_principal(request: Request) -> Principal:
    """The cross-plane resolver, for the session-lifecycle routes only.

    A candidate, an org user and an operator all need to see and revoke their
    own sessions through one route. Without a name for that, those four routes
    would need three copies each or would sit outside the route-table guard —
    and a route outside the guard is the entire problem.

    SESSION ONLY: a header key has no session to list or revoke, so it 401s
    here rather than resolving to something that pretends to work.
    """
    principal = _services(request).auth.resolve_any(
        session_token=_session_cookie(request)
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="a session is required")
    return _accept(request, principal)


def _session_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(_services(request).settings.session_cookie_name)


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
# Login surfaces. Dependency-free by definition: they run BEFORE a principal
# exists, which is why every path here is listed in PUBLIC_PATHS.
auth_router = APIRouter()


class EvaluateRequest(BaseModel):
    """Exactly one of resume_text / resume_pdf_b64 is required."""

    resume_text: str | None = None
    resume_pdf_b64: str | None = None
    github_url: str | None = Field(default=None, description="First-party link only.")
    portfolio_url: str | None = Field(default=None, description="First-party link only.")
    domain: str = "genai"

    @model_validator(mode="after")
    def _need_one_source(self) -> "EvaluateRequest":
        if not (self.resume_text or self.resume_pdf_b64):
            raise ValueError("Provide resume_text or resume_pdf_b64.")
        return self


@router.post("/evaluate", response_model=Report)
async def evaluate(req: EvaluateRequest, request: Request) -> Report:
    services = _services(request)
    engine = request.app.state.engine

    # Input caps (FR-11): reject oversize payloads before any work happens.
    caps = services.settings
    if req.resume_text and len(req.resume_text) > caps.max_resume_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_text exceeds max_resume_chars={caps.max_resume_chars}",
        )
    if req.resume_pdf_b64 and len(req.resume_pdf_b64) > caps.max_pdf_b64_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_pdf_b64 exceeds max_pdf_b64_chars={caps.max_pdf_b64_chars}",
        )
    # Domain pre-check (FR-12): fail fast, never run the graph on a bad domain.
    try:
        get_domain(req.domain)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        report = await engine.evaluate(
            resume_text=req.resume_text,
            resume_pdf_b64=req.resume_pdf_b64,
            github_url=req.github_url,
            portfolio_url=req.portfolio_url,
            domain=req.domain,
        )
    except KeyError as exc:  # unknown domain
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    services.report_store.save(report)
    return report


class CandidateCreateRequest(BaseModel):
    """Exactly one of resume_text / resume_pdf_b64 is required."""

    resume_text: str | None = None
    resume_pdf_b64: str | None = None
    domain: str = "genai"
    # Auto depth-eval is the default (S1.3 mandate); clients doing bulk import
    # can opt out and evaluate later.
    evaluate: bool = True

    @model_validator(mode="after")
    def _need_one_source(self) -> "CandidateCreateRequest":
        if not (self.resume_text or self.resume_pdf_b64):
            raise ValueError("Provide resume_text or resume_pdf_b64.")
        return self


class CandidateCreateResponse(BaseModel):
    """What one upload did (S1.2 IngestOutcome) + the advisory report, if run."""

    candidate_id: str
    resume_id: str
    resume_version: int
    matched_existing: bool
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool
    extraction_method: str  # "llm" | "heuristic"
    report: Optional[Report] = None
    # S2.3: cross-candidate near-duplicate signals, computed at ingest so bulk
    # imports (evaluate=False) still see them. Advisory, like everything else.
    resume_farm: Optional[ResumeFarmAssessment] = None


async def _ingest_one(
    req: CandidateCreateRequest, request: Request, *, org_id: Optional[str] = None
) -> CandidateCreateResponse:
    """Upload → extract → store → (auto) depth-eval, for ONE resume.

    Shared by the admin route (no owner) and the org route (owner = caller).
    Kept as one function on purpose: duplicating it would be the
    one-rule-two-doors shape in the sprint that exists to eliminate it.
    """
    services = _services(request)

    caps = services.settings
    if req.resume_text and len(req.resume_text) > caps.max_resume_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_text exceeds max_resume_chars={caps.max_resume_chars}",
        )
    if req.resume_pdf_b64 and len(req.resume_pdf_b64) > caps.max_pdf_b64_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_pdf_b64 exceeds max_pdf_b64_chars={caps.max_pdf_b64_chars}",
        )
    try:
        get_domain(req.domain)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    text = req.resume_text
    if not text and req.resume_pdf_b64:
        try:
            text = pdf_b64_to_text(req.resume_pdf_b64)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"pdf_parse_failed: {exc}"
            ) from exc
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="empty_resume")

    result = await extract_profile(text, llm=services.llm, settings=services.settings)
    outcome = services.candidates.ingest(result, text, org_id=org_id)

    # S2.3: fingerprint + farm check. Lives HERE, not in a graph node: the
    # comparison must exclude the uploader's own candidate (re-uploads and new
    # versions are legitimate), and the graph deliberately never learns the
    # candidate identity.
    farm = ResumeFarmAssessment()  # insufficient_data when the text is too short
    fp = fingerprint_text(text, services.settings)
    if fp is not None:
        services.candidates.save_fingerprint(
            fp, resume_id=outcome.resume_id, candidate_id=outcome.candidate_id
        )
        matches, corpus = services.candidates.similar_resumes(
            fp,
            exclude_candidate_id=outcome.candidate_id,
            threshold=services.settings.rf_similar_threshold,
            limit=services.settings.rf_max_matches,
        )
        farm = assess_resume_farm(
            matches,
            shingle_count=fp.shingle_count,
            corpus_size=corpus,
            settings=services.settings,
        )

    report: Optional[Report] = None
    if req.evaluate:
        report = await request.app.state.engine.evaluate(
            resume_text=text,
            domain=req.domain,
            candidate_profile=result.profile,
            resume_farm=farm,
        )
        report.candidate_id = outcome.candidate_id
        # DPDP: a derived report must not outlive the erasure of its subject.
        # Since S8.1 the foreign key REFUSES the orphan outright, and an erasure
        # landing after the save cascades the row away — so both halves of this
        # race are the database's job, not a compensating delete we remember.
        try:
            services.report_store.save(report, org_id=org_id)
        except SubjectErasedError:
            report = None
        else:
            if services.candidates.get_candidate(outcome.candidate_id) is None:
                report = None

    return CandidateCreateResponse(
        candidate_id=outcome.candidate_id,
        resume_id=outcome.resume_id,
        resume_version=outcome.resume_version,
        matched_existing=outcome.matched_existing,
        matched_on=outcome.matched_on,
        duplicate_resume=outcome.duplicate_resume,
        extraction_method=result.method,
        report=report,
        resume_farm=farm,
    )


@router.post("/candidates", response_model=CandidateCreateResponse)
async def create_candidate(
    req: CandidateCreateRequest, request: Request
) -> CandidateCreateResponse:
    """Admin plane: no owner. Cross-tenant by design -- this is the operator's
    view, and S8.4 deliberately left it alone."""
    return await _ingest_one(req, request)


class CandidateDetail(BaseModel):
    """Store summary + the newest extracted profile (hashes only — no raw PII)."""

    id: str
    full_name: Optional[str] = None
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resume_count: int = 0
    latest_profile: Optional[CandidateProfile] = None


class CandidateResumesResponse(BaseModel):
    candidate_id: str
    resumes: list[ResumeSummary]


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(candidate_id: str, request: Request) -> CandidateDetail:
    services = _services(request)
    summary = services.candidates.get_candidate(candidate_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return CandidateDetail(
        **summary.model_dump(),
        latest_profile=services.candidates.latest_profile(candidate_id),
    )


@router.get("/candidates/{candidate_id}/resumes", response_model=CandidateResumesResponse)
async def list_candidate_resumes(
    candidate_id: str, request: Request
) -> CandidateResumesResponse:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return CandidateResumesResponse(
        candidate_id=candidate_id,
        resumes=services.candidates.list_resumes(candidate_id),
    )


@router.get("/candidates/{candidate_id}/reports", response_model=list[Report])
async def list_candidate_reports(candidate_id: str, request: Request) -> list[Report]:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return services.report_store.for_candidate(candidate_id)


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(candidate_id: str, request: Request) -> dict:
    """DPDP erasure: candidate + resumes (raw text) + extractions + all reports
    derived from them. Hard delete — there is nothing to un-delete.

    Since S8.1 the reports go with the candidate through
    ``reports.candidate_id ON DELETE CASCADE``, not through a call this handler
    has to remember. ``reports_deleted`` is a COUNT READ taken before the
    delete: an entry point that forgets it loses a number in a response, not a
    person's data.
    """
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    # ONE erasure path, shared with the portal handler below. Erasure has two
    # entry points, and a rule applied at one and not the other is this repo's
    # recurring defect (S7.1, S7.2, S7.3) -- so the steps live in the service.
    return services.portal.erase(candidate_id)


@router.delete("/candidates/{candidate_id}/resumes/{resume_id}")
async def delete_candidate_resume(
    candidate_id: str, resume_id: str, request: Request
) -> dict:
    """DPDP erasure of ONE resume version (+ its extractions). The candidate
    row and other versions stay; ownership is checked so one candidate's URL
    can never erase another's data."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    owned = {r.id for r in services.candidates.list_resumes(candidate_id)}
    if resume_id not in owned:
        raise HTTPException(status_code=404, detail="resume not found for candidate")
    services.candidates.delete_resume(resume_id)
    return {"resume_id": resume_id, "deleted": True}


@router.post("/candidates/{candidate_id}/auth-key")
async def issue_candidate_key(candidate_id: str, request: Request) -> dict:
    """Admin/system mints (or rotates) a candidate's portal access key, returned
    ONCE. First-party self-serve registration is a productionization concern
    (PI-8); this is the offline-deterministic issuance path."""
    services = _services(request)
    try:
        access_key = services.candidates.issue_access_key(candidate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="candidate not found") from exc
    return {"candidate_id": candidate_id, "access_key": access_key}


class GitHubSourceRequest(BaseModel):
    handle: Optional[str] = None


class LinkedInSourceRequest(BaseModel):
    export_b64: str


class ProfileSourcesResponse(BaseModel):
    candidate_id: str
    sources: list[ProfileSourceSignal]


@router.post(
    "/candidates/{candidate_id}/sources/github", response_model=ProfileSourceSignal
)
async def ingest_github_source(
    candidate_id: str, req: GitHubSourceRequest, request: Request
) -> ProfileSourceSignal:
    """Ingest a candidate's public GitHub handle as an advisory skill signal
    (S6.1). A missing/unreachable handle returns 200 with method='unavailable';
    a handle that can't be resolved at all is 400."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    try:
        return await services.profile_sources.ingest_github(candidate_id, handle=req.handle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/candidates/{candidate_id}/sources/linkedin", response_model=ProfileSourceSignal
)
async def ingest_linkedin_source(
    candidate_id: str, req: LinkedInSourceRequest, request: Request
) -> ProfileSourceSignal:
    """Ingest a candidate's uploaded LinkedIn data export (base64 ZIP) as an
    advisory skill signal (S6.2). Malformed transport (bad base64 / oversize) is
    422; a valid file with no recognizable LinkedIn CSVs returns 200 with
    method='unavailable'."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    if len(req.export_b64) > services.settings.max_linkedin_b64_chars:
        raise HTTPException(
            status_code=422,
            detail=f"export_b64 exceeds max_linkedin_b64_chars={services.settings.max_linkedin_b64_chars}",
        )
    try:
        data = base64.b64decode(req.export_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid_base64") from exc
    return await services.profile_sources.ingest_linkedin(candidate_id, data)


@router.get(
    "/candidates/{candidate_id}/sources", response_model=ProfileSourcesResponse
)
async def list_candidate_sources(
    candidate_id: str, request: Request, source_type: Optional[ProfileSourceType] = None
) -> ProfileSourcesResponse:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return ProfileSourcesResponse(
        candidate_id=candidate_id,
        sources=services.profile_sources.list_sources(candidate_id, source_type),
    )


# ── Normalization curation loop (S6.3) ───────────────────────────────────────
# Admin-plane review of unmapped skill terms surfaced by the profile-source
# adapters. Resolving a term feeds the deterministic normalize_skill overlay.
# (Candidate/org auth is S6.4; until then this rides the shared X-API-Key.)


class CurationResolveRequest(BaseModel):
    norm_key: str
    action: CurationAction
    canonical: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None
    decided_by: Optional[str] = None


@router.get("/curation/skills/unmapped", response_model=list[UnmappedTerm])
async def list_unmapped_terms(
    request: Request,
    status: Optional[CurationStatus] = None,
    limit: Optional[int] = None,
) -> list[UnmappedTerm]:
    return _services(request).curation.list_unmapped(status, limit)


@router.post("/curation/skills/resolve", response_model=UnmappedTerm)
async def resolve_unmapped_term(
    req: CurationResolveRequest, request: Request
) -> UnmappedTerm:
    services = _services(request)
    try:
        return services.curation.resolve(
            req.norm_key, req.action, canonical=req.canonical, category=req.category,
            note=req.note, decided_by=req.decided_by,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.post("/ledger/orgs/{org_id}/api-key")
async def rotate_org_key(org_id: str, request: Request) -> dict:
    try:
        api_key = _services(request).ledger.issue_api_key(org_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"org_id": org_id, "api_key": api_key}


@router.delete("/ledger/orgs/{org_id}")
async def delete_org(org_id: str, request: Request) -> dict:
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


@router.post("/ledger/consent/{consent_id}/revoke")
async def revoke_consent(consent_id: str, request: Request) -> dict:
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


# ── Screening (S8.4 Phase A) ────────────────────────────────────────────────
# The wedge, reachable by the org that bought it: upload one resume, read back
# its own (redacted) report, list its own reports about one person. Batch
# upload is Phase B.


@org_router.post("/screening/candidates", response_model=CandidateCreateResponse)
async def screening_create_candidate(
    req: CandidateCreateRequest, request: Request, org_id: str = Depends(require_org)
) -> CandidateCreateResponse:
    """The wedge, on the plane that bought it (S8.4 §3.2).

    Synchronous like its admin twin -- this is the one-off upload. Batch is
    Phase B. The resume and its report are stamped with the caller's org.

    ``_ingest_one`` scans the whole platform's fingerprints for the resume
    farm check (fraud detection has to, by design); redact the response here
    before it leaves the org plane so a caller never sees another customer's
    candidate_id/resume_id. The admin twin (create_candidate) returns the
    same read unredacted on purpose -- that is the operator's cross-tenant
    support view.
    """
    resp = await _ingest_one(req, request, org_id=org_id)
    return redact_ingest_response_for_org(resp)


@org_router.get("/screening/reports/{report_id}", response_model=Report)
async def screening_get_report(
    report_id: str, request: Request, org_id: str = Depends(require_org)
) -> Report:
    """404 -- never 403 -- for a report this org did not commission: a 403
    would confirm it exists."""
    found = _services(request).screening_scope.report(org_id, report_id)
    if found is None:
        raise HTTPException(status_code=404, detail="report not found")
    return found


@org_router.get(
    "/screening/candidates/{candidate_id}/reports", response_model=list[Report]
)
async def screening_candidate_reports(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> list[Report]:
    """This org's own reports about one person. A person they have never
    uploaded yields an empty list, not a 404."""
    return _services(request).screening_scope.reports_for_candidate(
        org_id, candidate_id
    )


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


@org_router.post("/jobs/{req_id}/match", response_model=MatchResult)
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
        raise HTTPException(status_code=422, detail="no materialized candidates to match")
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


@org_router.post("/comp/estimate", response_model=CompBandEstimate)
async def comp_estimate(
    body: CompEstimateRequest, request: Request, org_id: str = Depends(require_org)
) -> CompBandEstimate:
    services = _services(request)
    try:
        signal = bands.role_signal_from_input(
            skills=body.skills, title=body.title, years=body.years_experience,
            location_tiers=body.location_tiers, remote=body.remote,
            role_family=body.role_family, seniority=body.seniority, settings=services.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return services.comp.estimate(signal, org_id=org_id)


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
        raise HTTPException(status_code=422, detail="no materialized candidates to match")
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
    return _services(request).portal.my_data(candidate_id)


@candidate_router.get("/portal/access-log", response_model=list[AccessLogEntry])
async def portal_access_log(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[AccessLogEntry]:
    return _services(request).portal.access_log(candidate_id)


@candidate_router.get("/portal/consents", response_model=list[ConsentView])
async def portal_list_consents(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[ConsentView]:
    return _services(request).portal.consents(candidate_id)


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


@candidate_router.post("/portal/consents/{consent_id}/revoke")
async def portal_revoke_consent(
    consent_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    try:
        revoked = _services(request).portal.revoke(candidate_id, consent_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="consent grant not found") from exc
    return {"consent_id": consent_id, "revoked": revoked}


@candidate_router.delete("/portal/me")
async def portal_erase(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
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


@candidate_router.post("/portal/verifications")
async def start_verification(
    req: StartVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
    services = _services(request)
    try:
        verification, code = services.verification.start(
            candidate_id, req.method, destination=req.destination
        )
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


@candidate_router.post("/portal/verifications/{verification_id}/confirm")
async def confirm_verification(
    verification_id: str,
    req: ConfirmVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
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


@candidate_router.get("/portal/verifications")
async def list_verifications(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
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


@org_router.get("/verification/candidates/{candidate_id}/assurance")
async def org_candidate_assurance(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> dict:
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


@candidate_router.post("/portal/documents")
async def submit_document(
    req: SubmitDocumentRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
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


@org_router.get("/verification/candidates/{candidate_id}/claims")
async def org_candidate_claims(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> dict:
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


def _interview_body(session, following) -> dict:
    return {
        "session": session.model_dump(mode="json"),
        "next_question": following.model_dump(mode="json") if following else None,
    }


@candidate_router.post("/portal/interviews")
async def start_interview(
    req: StartInterviewRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
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


@candidate_router.get("/portal/interviews")
async def list_interviews(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    summaries = _services(request).interview.list_for_candidate(candidate_id)
    return {"interviews": [s.model_dump(mode="json") for s in summaries]}


@candidate_router.get("/portal/interviews/{session_id}")
async def get_interview(
    session_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    """The candidate's own full view — transcripts included. It is their data,
    and an advisory score whose basis they cannot read is not advisory."""
    services = _services(request)
    try:
        session = services.interview.get(candidate_id, session_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="interview not found") from exc
    return _interview_body(session, services.interview.next_question(session))


@candidate_router.post("/portal/interviews/{session_id}/answers")
async def submit_answer(
    session_id: str,
    req: SubmitAnswerRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
    services = _services(request)
    try:
        session, following = await services.interview.answer(
            candidate_id, session_id, question_id=req.question_id,
            text=req.text, audio_b64=req.audio_b64, mime=req.mime,
        )
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AnswerTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpeechUnavailable as exc:
        # The designed no-key path, said out loud: answer in text instead.
        raise HTTPException(
            status_code=422, detail=f"speech_unavailable: {exc}"
        ) from exc
    except SpeechFailed as exc:
        # Nothing was recorded, so retrying costs the candidate nothing.
        raise HTTPException(status_code=422, detail=f"speech_failed: {exc}") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interview not found") from exc
    except ValueError as exc:          # no body, or bad base64
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _interview_body(session, following)


@candidate_router.post("/portal/interviews/{session_id}/finish")
async def finish_interview(
    session_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    services = _services(request)
    try:
        session = services.interview.finish(candidate_id, session_id)
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interview not found") from exc
    return _interview_body(session, None)


@org_router.get("/interview/candidates/{candidate_id}/assessments")
async def org_candidate_interviews(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> dict:
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


@router.post("/candidates/{candidate_id}/verifications/manual-review")
async def record_manual_review(
    candidate_id: str, req: ManualReviewRequest, request: Request
) -> dict:
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


@router.post("/talent/search", response_model=SearchResult)
async def talent_search(req: TalentSearchRequest, request: Request) -> SearchResult:
    """Filter + rank the materialized pool by a composite score. Advisory: it
    narrows and orders, never auto-rejects. Consent was masked at materialization
    (S4.2), so a withheld feature is already null and simply drops out of scoring."""
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
        services.features.vectors_for_view(view_name, view_version, as_of=as_of)
        if as_of is not None
        else []
    )
    vectors = [mv.vector for mv in pool]

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


@router.get("/report/{report_id}", response_model=Report)
async def get_report(report_id: str, request: Request) -> Report:
    report = _services(request).report_store.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


class OutcomeRequest(BaseModel):
    """A human closing the loop on a report (or one claim within it)."""

    outcome: OutcomeLabel
    claim_id: Optional[str] = None
    notes: str = ""


@router.post("/report/{report_id}/outcome")
async def record_outcome(report_id: str, req: OutcomeRequest, request: Request) -> dict:
    services = _services(request)
    report = services.report_store.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    if req.claim_id is not None:
        known = {v.claim_id for v in report.verdicts}
        if req.claim_id not in known:
            raise HTTPException(
                status_code=422,
                detail=f"claim '{req.claim_id}' is not part of report '{report_id}'",
            )

    rec = OutcomeRecord(
        report_id=report_id, claim_id=req.claim_id, outcome=req.outcome, notes=req.notes
    )
    services.report_store.add_outcome(rec)
    # Same sink as the evaluation rows, so training joins read one stream.
    services.flywheel.log(
        {
            "record_type": "outcome",
            "report_id": report_id,
            "claim_id": req.claim_id,
            "outcome": req.outcome.value,
            "notes": req.notes,
        }
    )
    return {
        "report_id": report_id,
        "claim_id": req.claim_id,
        "outcome": req.outcome.value,
        "recorded_at": rec.recorded_at.isoformat(),
    }


@router.get("/report/{report_id}/outcomes")
async def list_outcomes(report_id: str, request: Request) -> dict:
    services = _services(request)
    if services.report_store.get(report_id) is None:
        raise HTTPException(status_code=404, detail="report not found")
    return {
        "report_id": report_id,
        "outcomes": [o.model_dump(mode="json") for o in services.report_store.outcomes(report_id)],
    }


@router.get("/domains")
async def domains() -> list[dict]:
    """Registered evaluation domains (FR-9)."""
    out = []
    for key in list_domains():
        d = get_domain(key)
        out.append(
            {"key": d.key, "display_name": d.display_name, "claim_types": d.claim_types}
        )
    return out


@public_router.get("/healthz")
async def healthz(request: Request) -> dict:
    """Liveness + effective mode (FR-10). Open — load balancers don't have keys."""
    services = _services(request)
    return {
        "status": "ok",
        "version": __version__,
        "env": services.settings.env,
        "llm_mode": "null" if isinstance(services.llm, NullLLM) else "live",
        "domains": list_domains(),
    }


# ── Auth: email-OTP signup / login / sessions (S8.2) ─────────────────────────
# Every route below either sits in PUBLIC_PATHS (it runs BEFORE a principal
# exists) or depends on require_any_principal. The route-table guard enforces
# that there is no third option.


class OrgSignupRequest(BaseModel):
    email: str
    organization_name: str = Field(min_length=1, max_length=200)


class EmailOnlyRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    email: str
    code: str


#: Signup and login always answer 202, whether or not the address is known. An
#: endpoint that reveals which addresses are registered is an enumeration
#: oracle, and it is the kind only an attacker ever notices.
_ACCEPTED = {"status": "accepted"}


def _set_session_cookies(
    response: Response, *, token: str, csrf: str, settings
) -> None:
    """One helper for both cookies so their flags cannot drift between planes.

    The session cookie is httpOnly, so XSS cannot read it. The CSRF cookie
    deliberately is NOT, because the browser client has to read it to echo it
    back in X-CSRF-Token. That asymmetry IS the double-submit scheme, not an
    oversight -- a reviewer seeing httponly=False here should read on, not fix.
    """
    common = dict(
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(settings.session_cookie_name, token, httponly=True, **common)
    response.set_cookie(settings.csrf_cookie_name, csrf, httponly=False, **common)


def _request_code(
    request: Request,
    *,
    email: str,
    plane: AuthPlane,
    purpose: LoginPurpose,
    payload: Optional[dict] = None,
) -> dict:
    """Shared signup/login handler for all three planes."""
    try:
        _services(request).auth.request_code(
            email=email,
            plane=plane,
            purpose=purpose,
            payload=payload,
            at=datetime.now(timezone.utc),
        )
    except EmailUnavailableError as exc:
        # An honest 503 rather than a 202 that leaves someone waiting forever for
        # a code that was never sent (the NullSpeech posture from S7.3).
        raise HTTPException(status_code=503, detail="email_unavailable") from exc
    except ChallengeRefused:
        # Includes the cooldown case, and answering 202 anyway keeps the response
        # uniform. A cooldown can only be triggered by an address that HAS an
        # account, so surfacing it would be the enumeration oracle by another
        # door. The previously sent code is still live and still in their inbox,
        # so the user loses nothing.
        pass
    return dict(_ACCEPTED)


def _verify(
    request: Request, response: Response, *, email: str, code: str, plane: AuthPlane
) -> dict:
    services = _services(request)
    try:
        token, csrf, principal = services.auth.verify_code(
            email=email,
            plane=plane,
            code=code,
            at=datetime.now(timezone.utc),
            user_agent=request.headers.get("user-agent"),
        )
    except RegistrationRefused as exc:
        # The code was RIGHT. This is a registration failure, and reporting it
        # as invalid_code is what locked users out of their own signup.
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    except ChallengeRefused as exc:
        # ONE status and ONE detail for every CODE failure mode. Distinguishing
        # expired from wrong from exhausted tells a brute-forcer which of their
        # assumptions was right, which is precisely the help not to give.
        raise HTTPException(status_code=400, detail="invalid_code") from exc
    _set_session_cookies(response, token=token, csrf=csrf, settings=services.settings)
    return {
        "principal": principal.kind.value,
        "csrf_token": csrf,
        "organization_id": principal.org_id,
    }


@auth_router.post("/auth/org/signup", status_code=202)
async def auth_org_signup(req: OrgSignupRequest, request: Request) -> dict:
    """Refuse a taken org name HERE, before a code is ever sent (S8.4 §2.1).

    The old behaviour answered 202, mailed a real code, and then rejected that
    CORRECT code at verify as `invalid_code` -- because org creation happens in
    `_establish`, and every ChallengeRefused collapsed into one message. The
    user burned their attempts and could not onboard.

    This does not re-open the enumeration oracle. What that oracle protects is
    whether an ADDRESS has an account, and this check never looks at the
    address: an unknown address still gets 202 exactly like a known one.
    """
    if not _services(request).auth.organization_name_available(req.organization_name):
        raise HTTPException(status_code=409, detail="organization_name_taken")
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.ORG,
        purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": req.organization_name},
    )


@auth_router.post("/auth/org/login", status_code=202)
async def auth_org_login(req: EmailOnlyRequest, request: Request) -> dict:
    return _request_code(
        request, email=req.email, plane=AuthPlane.ORG, purpose=LoginPurpose.LOGIN
    )


@auth_router.post("/auth/org/verify")
async def auth_org_verify(
    req: VerifyRequest, request: Request, response: Response
) -> dict:
    return _verify(
        request, response, email=req.email, code=req.code, plane=AuthPlane.ORG
    )


@auth_router.post("/auth/candidate/signup", status_code=202)
async def auth_candidate_signup(req: EmailOnlyRequest, request: Request) -> dict:
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.SIGNUP,
    )


@auth_router.post("/auth/candidate/login", status_code=202)
async def auth_candidate_login(req: EmailOnlyRequest, request: Request) -> dict:
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN,
    )


@auth_router.post("/auth/candidate/verify")
async def auth_candidate_verify(
    req: VerifyRequest, request: Request, response: Response
) -> dict:
    return _verify(
        request, response, email=req.email, code=req.code, plane=AuthPlane.CANDIDATE
    )


# NOTE: there is deliberately NO /auth/admin/signup. Operators are created by an
# existing operator through POST /admin/users, behind the shared admin key.


@auth_router.post("/auth/admin/login", status_code=202)
async def auth_admin_login(req: EmailOnlyRequest, request: Request) -> dict:
    return _request_code(
        request, email=req.email, plane=AuthPlane.ADMIN, purpose=LoginPurpose.LOGIN
    )


@auth_router.post("/auth/admin/verify")
async def auth_admin_verify(
    req: VerifyRequest, request: Request, response: Response
) -> dict:
    return _verify(
        request, response, email=req.email, code=req.code, plane=AuthPlane.ADMIN
    )


# -- session lifecycle: cross-plane, session-only ----------------------------


@auth_router.get("/auth/me")
async def auth_me(principal: Principal = Depends(require_any_principal)) -> dict:
    """What the browser client calls on load to learn who it is."""
    return {
        "kind": principal.kind.value,
        "organization_id": principal.org_id,
        "session_id": principal.session_id,
    }


@auth_router.post("/auth/logout")
async def auth_logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_any_principal),
) -> dict:
    services = _services(request)
    revoked = services.auth.logout(principal)
    response.delete_cookie(services.settings.session_cookie_name, path="/")
    response.delete_cookie(services.settings.csrf_cookie_name, path="/")
    return {"logged_out": revoked}


@auth_router.get("/auth/sessions", response_model=list[SessionView])
async def auth_sessions(
    request: Request, principal: Principal = Depends(require_any_principal)
) -> list[SessionView]:
    """The caller's own live sessions. Ownership resolves from the session, never
    from a parameter, so another principal's devices are simply unreachable."""
    return _services(request).auth.sessions_for(principal)


@auth_router.post("/auth/sessions/{session_id}/revoke")
async def auth_revoke_session(
    session_id: str,
    request: Request,
    principal: Principal = Depends(require_any_principal),
) -> dict:
    """Unknown and not-owned both 404 -- indistinguishable, so a session id
    cannot be probed (the S6.4 rule)."""
    if not _services(request).auth.revoke_session(principal, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "revoked": True}


# -- operator accounts (admin plane; decision 0.3) ---------------------------


class AdminUserRequest(BaseModel):
    email: str
    label: str = ""


@router.post("/admin/users")
async def create_admin_user(req: AdminUserRequest, request: Request) -> dict:
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


@router.get("/admin/users")
async def list_admin_users(request: Request) -> list[dict]:
    return [
        a.model_dump(mode="json")
        for a in _services(request).auth.list_admin_users()
    ]


@router.delete("/admin/users/{admin_user_id}")
async def delete_admin_user(admin_user_id: str, request: Request) -> dict:
    """A hard delete: their sessions CASCADE away with them."""
    if not _services(request).auth.delete_admin_user(admin_user_id):
        raise HTTPException(status_code=404, detail="operator not found")
    return {"admin_user_id": admin_user_id, "deleted": True}
