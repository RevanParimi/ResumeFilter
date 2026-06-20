"""HTTP surface: POST /evaluate, GET /report/{id}.

The response is an ADVISORY assessment with human_review_required=True. It never
auto-rejects. Reports are held in an in-memory store for M0 (swap for a DB later).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.schemas.report import Report

router = APIRouter()


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
    engine = request.app.state.engine
    store: dict[str, Report] = request.app.state.report_store
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"evaluation_failed: {exc}") from exc

    store[report.id] = report
    return report


@router.get("/report/{report_id}", response_model=Report)
async def get_report(report_id: str, request: Request) -> Report:
    store: dict[str, Report] = request.app.state.report_store
    report = store.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
