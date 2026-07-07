"""HTTP surface: evaluate, fetch reports, and record human outcomes.

Every response is ADVISORY with human_review_required=True — the engine never
auto-rejects. Reports are persisted through the injected ReportStore; human
outcomes close the flywheel loop (claim → probe → verdict → OUTCOME).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app import __version__
from app.candidates.extractor import extract_profile
from app.candidates.schema import CandidateProfile
from app.candidates.store import MatchedOn, ResumeSummary
from app.core.pdf import pdf_b64_to_text
from app.domains.base import get_domain, list_domains
from app.schemas.report import Report
from app.services import Services
from app.services.llm import NullLLM
from app.services.report_store import OutcomeLabel, OutcomeRecord


def _services(request: Request) -> Services:
    return request.app.state.services


async def require_api_key(
    request: Request, x_api_key: Optional[str] = Header(default=None)
) -> None:
    """Shared-secret gate (FR-15). No key configured → open (local/dev)."""
    expected = _services(request).settings.api_auth_key.get_secret_value()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


# Everything except "/" and /healthz sits behind the (optional) API key.
router = APIRouter(dependencies=[Depends(require_api_key)])
public_router = APIRouter()


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


@router.post("/candidates", response_model=CandidateCreateResponse)
async def create_candidate(
    req: CandidateCreateRequest, request: Request
) -> CandidateCreateResponse:
    """Upload → extract → store → (auto) depth-eval. The graph stays
    candidate-unaware: the API stamps report.candidate_id after evaluation."""
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
    outcome = services.candidates.ingest(result, text)

    report: Optional[Report] = None
    if req.evaluate:
        report = await request.app.state.engine.evaluate(
            resume_text=text, domain=req.domain
        )
        report.candidate_id = outcome.candidate_id
        services.report_store.save(report)
        # DPDP: if the candidate was erased while the eval ran, a derived
        # report must not outlive the erasure — drop it and return nothing.
        if services.candidates.get_candidate(outcome.candidate_id) is None:
            services.report_store.delete(report.id)
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
    )


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
    derived from them. Hard delete — there is nothing to un-delete."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    reports_deleted = services.report_store.delete_for_candidate(candidate_id)
    services.candidates.delete_candidate(candidate_id)
    return {
        "candidate_id": candidate_id,
        "deleted": True,
        "reports_deleted": reports_deleted,
    }


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
