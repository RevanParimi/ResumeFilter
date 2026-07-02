"""HTTP surface: evaluate, fetch reports, and record human outcomes.

Every response is ADVISORY with human_review_required=True — the engine never
auto-rejects. Reports are persisted through the injected ReportStore; human
outcomes close the flywheel loop (claim → probe → verdict → OUTCOME).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app import __version__
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
