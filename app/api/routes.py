"""HTTP surface: evaluate, fetch reports, and record human outcomes.

Every response is ADVISORY with human_review_required=True — the engine never
auto-rejects. Reports are persisted through the injected ReportStore; human
outcomes close the flywheel loop (claim → probe → verdict → OUTCOME).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.schemas.report import Report
from app.services import Services
from app.services.report_store import OutcomeLabel, OutcomeRecord

router = APIRouter()


def _services(request: Request) -> Services:
    return request.app.state.services


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


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
