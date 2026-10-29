"""Admin candidate intake, resume management and advisory profile sources.

Employer intake shares the DTOs and HTTP adapter; portal erasure shares its DTO.
Authentication and CSRF remain in the central request dependencies.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator

from app.api.dependencies import _services, require_api_key
from app.candidates.schema import CandidateProfile
from app.candidates.store import MatchedOn, ResumeSummary
from app.core.blocking import ExecutionPending, ExecutionUnavailable
from app.core.resume import ResumeInputError, read_resume_input_async
from app.domains.base import get_domain
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
from app.profile_sources.store import SourceSignalErasedError, SourceSubjectErasedError
from app.schemas.extraction import ExtractionCoverage
from app.schemas.fabrication import ResumeFarmAssessment
from app.schemas.report import Report
from app.screening.ingest import IngestRefused, ingest_deps, ingest_resume


# The same admin gate applies to aggregate and standalone registration.
router = APIRouter(dependencies=[Depends(require_api_key)])


class ErasureResponse(BaseModel):
    """DPDP erasure, from both entry points. `reports_deleted` is a COUNT READ
    taken before the delete -- a number in a response, not a person's data."""

    candidate_id: str
    deleted: bool
    reports_deleted: int = 0


class ResumeDeletedResponse(BaseModel):
    resume_id: str
    deleted: bool


class CandidateKeyResponse(BaseModel):
    """Returned ONCE at issuance; only the hash is stored."""

    candidate_id: str
    access_key: str


class CandidateCreateRequest(BaseModel):
    """At least one of resume_text / resume_pdf_b64; resume_text wins when
    both are sent (same rule as BatchItemInput, on purpose)."""

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
    # S9.2: computed at ingest so bulk imports (evaluate=False) still see it,
    # for the same reason resume_farm is here.
    extraction_coverage: Optional[ExtractionCoverage] = None


async def _ingest_one(
    req: CandidateCreateRequest, request: Request, *, org_id: Optional[str] = None
) -> CandidateCreateResponse:
    """HTTP adapter over the ONE ingest core (app/screening/ingest.py).

    Shared by the admin route (no owner) and the org route (owner = caller).
    The pipeline itself moved out so the batch processor runs the same code:
    duplicating it would be the one-rule-two-doors shape in the sprint that
    exists to eliminate it.
    """
    services = _services(request)
    # Kept in the route so the 422 detail stays byte-identical to what clients
    # (and five smokes) already assert.
    try:
        get_domain(req.domain)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        text = await read_resume_input_async(executor=services.pdf, resume_text=req.resume_text,
            resume_pdf_b64=req.resume_pdf_b64, settings=services.settings)
    except ResumeInputError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from None

    try:
        result = await ingest_resume(
            ingest_deps(services), request.app.state.engine,
            text=text, domain=req.domain, evaluate=req.evaluate, org_id=org_id,
            executor=services.candidate_ingests,
        )
    except (ExecutionPending, ExecutionUnavailable) as exc:
        raise _ingest_execution_refused(exc) from None
    except IngestRefused as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc

    return CandidateCreateResponse(
        candidate_id=result.candidate_id,
        resume_id=result.resume_id,
        resume_version=result.resume_version,
        matched_existing=result.matched_existing,
        matched_on=result.matched_on,
        duplicate_resume=result.duplicate_resume,
        extraction_method=result.extraction_method,
        report=result.report,
        resume_farm=result.resume_farm,
        extraction_coverage=result.extraction_coverage,
    )


def _ingest_execution_refused(exc):
    # The initial transaction may still commit. Return no IDs or partial success,
    # and never restart fingerprinting/evaluation when a late worker completes.
    detail = 'candidate_ingest_pending' if isinstance(exc, ExecutionPending) else str(exc)
    return HTTPException(status_code=503, detail=detail, headers={'Retry-After': '1'})


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
    summary, profile = await _candidate_record(request, _candidate_snapshot,
        services.candidates, candidate_id, services.candidates.latest_profile)
    return CandidateDetail(
        **summary.model_dump(),
        latest_profile=profile,
    )


@router.get("/candidates/{candidate_id}/resumes", response_model=CandidateResumesResponse)
async def list_candidate_resumes(
    candidate_id: str, request: Request
) -> CandidateResumesResponse:
    services = _services(request)
    _summary, resumes = await _candidate_record(request, _candidate_snapshot,
        services.candidates, candidate_id, services.candidates.list_resumes)
    return CandidateResumesResponse(
        candidate_id=candidate_id,
        resumes=resumes,
    )


@router.get("/candidates/{candidate_id}/reports", response_model=list[Report])
async def list_candidate_reports(candidate_id: str, request: Request) -> list[Report]:
    services = _services(request)
    _summary, reports = await _candidate_record(request, _candidate_snapshot,
        services.candidates, candidate_id, services.report_store.for_candidate)
    return reports


@router.delete("/candidates/{candidate_id}", response_model=ErasureResponse)
async def delete_candidate(candidate_id: str, request: Request) -> ErasureResponse:
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


@router.delete("/candidates/{candidate_id}/resumes/{resume_id}", response_model=ResumeDeletedResponse)
async def delete_candidate_resume(
    candidate_id: str, resume_id: str, request: Request
) -> ResumeDeletedResponse:
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


@router.post("/candidates/{candidate_id}/auth-key", response_model=CandidateKeyResponse)
async def issue_candidate_key(candidate_id: str, request: Request) -> CandidateKeyResponse:
    """Admin/system mints (or rotates) a candidate's portal access key, returned
    ONCE. First-party self-serve registration is a productionization concern
    (PI-8); this is the offline-deterministic issuance path."""
    services = _services(request)
    access_key = await _candidate_record(request, _candidate_key, services.candidates, candidate_id)
    return {"candidate_id": candidate_id, "access_key": access_key}


def _candidate_snapshot(candidates, candidate_id, read):
    summary = candidates.get_candidate(candidate_id)
    if summary is None:
        raise LookupError()
    result = read(candidate_id)
    if candidates.get_candidate(candidate_id) is None:
        raise LookupError()
    return summary, result


def _candidate_key(candidates, candidate_id):
    key = candidates.issue_access_key(candidate_id)
    if candidates.get_candidate(candidate_id) is None:
        raise LookupError()
    return key


async def _candidate_record(request: Request, operation, *args):
    try:
        return await _services(request).candidate_records.run(operation, *args)
    except LookupError:
        raise HTTPException(status_code=404, detail='candidate not found') from None
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        # Rotation may commit after the caller stops waiting, invalidating its
        # old key without delivering the replacement. Never replay or echo it.
        raise HTTPException(status_code=503, detail='candidate_record_pending',
                            headers={'Retry-After': '1'}) from None


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
    except (SourceSubjectErasedError, SourceSignalErasedError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
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
    try:
        return await services.profile_sources.ingest_linkedin(candidate_id, data)
    except (SourceSubjectErasedError, SourceSignalErasedError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get(
    "/candidates/{candidate_id}/sources", response_model=ProfileSourcesResponse
)
async def list_candidate_sources(
    candidate_id: str, request: Request, source_type: Optional[ProfileSourceType] = None
) -> ProfileSourcesResponse:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    try:
        return ProfileSourcesResponse(
            candidate_id=candidate_id,
            sources=services.profile_sources.list_sources(candidate_id, source_type),
        )
    except SourceSubjectErasedError:
        raise HTTPException(status_code=404, detail="candidate not found") from None
