"""Operator evaluation/report workflow and shared human-outcome contracts."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.api.dependencies import _services, require_api_key
from app.core.blocking import ExecutionPending, ExecutionUnavailable
from app.core.resume import ResumeInputError
from app.domains.base import get_domain
from app.reports.outcomes import OutcomeRefused, build_outcome
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import Report


# Separate registration groups retain their positions in the admin API sequence.
# Each route owns its admin dependency, including when included independently.
evaluation_router = APIRouter(dependencies=[Depends(require_api_key)])
report_router = APIRouter(dependencies=[Depends(require_api_key)])


class OutcomeRequest(BaseModel):
    """A human closing the loop on a report (or one claim within it).

    Defined up here with the two response models rather than beside the
    operator's route, because BOTH doors take it and FastAPI resolves a
    handler's annotations at decoration time -- the org-plane route is
    registered earlier in this file.

    `notes` is bounded by `max_outcome_notes_chars` inside `build_outcome`, not
    by a Field constraint here: the cap is config, and it must apply
    identically on both routes (S8.5 spec §4).
    """

    outcome: OutcomeLabel
    claim_id: Optional[str] = None
    notes: str = ""


class OutcomeRecordedResponse(BaseModel):
    report_id: str
    claim_id: Optional[str] = None
    outcome: str
    recorded_at: str


class OutcomeListResponse(BaseModel):
    report_id: str
    outcomes: list[OutcomeRecord] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    """At least one source; resume_text wins when both are supplied."""

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


@evaluation_router.post("/evaluate", response_model=Report)
async def evaluate(req: EvaluateRequest, request: Request) -> Report:
    services = _services(request)
    engine = request.app.state.engine

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
    except ResumeInputError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from None
    except KeyError as exc:  # unknown domain
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    services.report_store.save(report)
    # Report-only deletion can win after save, even without a candidate link.
    # This is a response snapshot, not a lock across HTTP delivery.
    if services.report_store.get(report.id) is None:
        raise HTTPException(status_code=422, detail="report_erased")
    return report


@report_router.get("/report/{report_id}", response_model=Report)
async def get_report(report_id: str, request: Request) -> Report:
    report = await _report_record(request, _services(request).report_store.get, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


async def _report_record(request: Request, operation, *args):
    try:
        return await _services(request).report_records.run(operation, *args)
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        # A late read retains admission but never writes or repeats evaluation.
        raise HTTPException(status_code=503, detail='report_record_pending',
                            headers={'Retry-After': '1'}) from None


def _report_history(store, report_id):
    if store.get(report_id) is None:
        return None
    outcomes = store.outcomes(report_id)
    return outcomes if store.get(report_id) is not None else None


def _outcome_flywheel_record(rec: OutcomeRecord) -> dict:
    """Minimal outcome event for the optional test observer.

    Production does not retain this event. Notes and labels live in SQL
    outcomes, erased via outcomes -> reports -> candidates CASCADE.

    It gains provenance instead: a calibration harness must be able to tell a
    customer's judgment from our own operator's, or it trains on its own echo.
    """
    return {
        "record_type": "outcome",
        "report_id": rec.report_id,
        "claim_id": rec.claim_id,
        "outcome": rec.outcome.value,
        "recorded_by": rec.recorded_by.value,
        "org_id": rec.org_id,
    }


def _outcome_recorded(rec: OutcomeRecord) -> OutcomeRecordedResponse:
    return OutcomeRecordedResponse(
        report_id=rec.report_id,
        claim_id=rec.claim_id,
        outcome=rec.outcome.value,
        recorded_at=rec.recorded_at.isoformat(),
    )


def _operator_outcome(store, report_id, **values):
    report = store.get(report_id)
    if report is None:
        return None
    rec = build_outcome(report, recorded_by=OutcomeSource.OPERATOR, **values)
    # Erasure can win between lookup and append; the store owns FK rollback.
    return rec if store.add_outcome(rec) else None


def _observe_outcome(observer, operation, *args, **kwargs):
    rec = operation(*args, **kwargs)
    if rec is not None:
        # The optional observer runs after the SQL commit, not atomically with it.
        try:
            observer.log(_outcome_flywheel_record(rec))
        except (OutcomeRefused, ExecutionUnavailable, ExecutionPending):
            # An observer's exception must not masquerade as input validation
            # or refusal before admission: the outcome is already committed.
            raise RuntimeError('outcome_observer_failed') from None
    return rec


async def _outcome_record(request: Request, operation, *args, **kwargs):
    services = _services(request)
    try:
        return await services.outcome_records.run(
            _observe_outcome, services.flywheel, operation, *args, **kwargs)
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        # Accepted work can still append. A history read, never replay, is recovery.
        raise HTTPException(status_code=503, detail='outcome_record_pending',
                            headers={'Retry-After': '1'}) from None
    except OutcomeRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@report_router.post("/report/{report_id}/outcome", response_model=OutcomeRecordedResponse)
async def record_outcome(report_id: str, req: OutcomeRequest, request: Request) -> OutcomeRecordedResponse:
    """The OPERATOR's door. The customer's is
    `POST /screening/reports/{id}/outcome`, and both go through
    `build_outcome` -- a rule enforced at one entry point and forgotten at the
    second is this repo's signature defect (S8.5 spec §3)."""
    services = _services(request)
    rec = await _outcome_record(request, _operator_outcome, services.report_store, report_id,
        outcome=req.outcome, claim_id=req.claim_id, notes=req.notes,
        max_notes_chars=services.settings.max_outcome_notes_chars)
    if rec is None:
        raise HTTPException(status_code=404, detail="report not found")
    return _outcome_recorded(rec)


@report_router.get("/report/{report_id}/outcomes", response_model=OutcomeListResponse)
async def list_outcomes(report_id: str, request: Request) -> OutcomeListResponse:
    services = _services(request)
    outcomes = await _report_record(request, _report_history, services.report_store, report_id)
    if outcomes is None:
        raise HTTPException(status_code=404, detail="report not found")
    return {
        "report_id": report_id,
        "outcomes": [o.model_dump(mode="json") for o in outcomes],
    }
