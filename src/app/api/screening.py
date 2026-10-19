"""Employer screening intake, scoped reports/outcomes and batch workflows.

Handlers establish their org principal explicitly through the shared dependency.
Candidate intake and human-outcome contracts retain their existing API owners.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.api.candidates import CandidateCreateRequest, CandidateCreateResponse, _ingest_one
from app.api.dependencies import _rate_limited, _services, require_org
from app.api.reports import (
    OutcomeListResponse, OutcomeRecordedResponse, OutcomeRequest,
    _outcome_flywheel_record, _outcome_recorded,
)
from app.core.resume import ResumeInputError, read_resume_input
from app.ratelimit.service import RateLimited
from app.reports.outcomes import OutcomeRefused
from app.schemas.report import Report
from app.screening.pagination import InvalidCursor
from app.screening.projection import redact_ingest_response_for_org
from app.screening.schema import (
    BatchDetail, BatchPage, BatchSummary, ProcessResult, QueuePage, RetryResult,
)


# The org dependency remains explicit on every operation, including standalone use.
org_router = APIRouter()


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


@org_router.post(
    "/screening/reports/{report_id}/outcome",
    response_model=OutcomeRecordedResponse,
)
async def screening_record_outcome(
    report_id: str, req: OutcomeRequest, request: Request,
    org_id: str = Depends(require_org),
) -> OutcomeRecordedResponse:
    """The customer closing the loop on a report they commissioned (S8.5).

    The twin of the operator's `POST /report/{id}/outcome`; both validate
    through `build_outcome`, so neither door can be bounded while the other is
    not.

    404 -- never 403 -- for a report this org did not commission, on a WRITE
    as much as on a read. The instinct on a refused write is 403, and it would
    confirm the report exists to anyone who guessed an id.
    """
    services = _services(request)
    try:
        rec = services.screening_scope.record_outcome(
            org_id, report_id,
            outcome=req.outcome,
            claim_id=req.claim_id,
            notes=req.notes,
            max_notes_chars=services.settings.max_outcome_notes_chars,
            org_user_id=_org_user_id(request),
        )
    except OutcomeRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if rec is None:
        raise HTTPException(status_code=404, detail="report not found")

    services.flywheel.log(_outcome_flywheel_record(rec))
    return _outcome_recorded(rec)


@org_router.get(
    "/screening/reports/{report_id}/outcomes",
    response_model=OutcomeListResponse,
    description="This organisation's own judgments on a report it commissioned, oldest first.",
)
async def screening_list_outcomes(
    report_id: str, request: Request, org_id: str = Depends(require_org)
) -> OutcomeListResponse:
    """THIS org's judgments -- not every judgment on the report.

    An operator's internal note about a customer's report lives on the same
    report, and the customer is not its audience. The admin twin
    (`GET /report/{id}/outcomes`) returns everything on purpose; that is the
    operator's cross-tenant support view.
    """
    found = _services(request).screening_scope.outcomes(org_id, report_id)
    if found is None:
        raise HTTPException(status_code=404, detail="report not found")
    return OutcomeListResponse(report_id=report_id, outcomes=found)


# ── Screening batches (S8.4 Phase B) ─────────────────────────────────────────
# The wedge at volume: register what you have, process it in bounded calls,
# read a ranked queue. Registration is a row insert; PROCESSING is the slow
# part and the client drives it, because there is no worker anywhere in app/
# (spec §0.3) and 500 nine-node graph runs cannot happen inside one request.


class BatchItemInput(BaseModel):
    """At least one of resume_text / resume_pdf_b64; resume_text wins when
    both are sent (same rule as CandidateCreateRequest, on purpose)."""

    resume_text: Optional[str] = None
    resume_pdf_b64: Optional[str] = None

    @model_validator(mode="after")
    def _need_one_source(self) -> "BatchItemInput":
        if not (self.resume_text or self.resume_pdf_b64):
            raise ValueError("Provide resume_text or resume_pdf_b64.")
        return self


class BatchCreateRequest(BaseModel):
    name: str = ""
    domain: str = "genai"
    items: list[BatchItemInput] = Field(default_factory=list)


class BatchDeleteResponse(BaseModel):
    batch_id: str
    deleted: bool


def _batch_texts(req: BatchCreateRequest, caps) -> list[str]:
    """Decode every item to text AT REGISTRATION -- cheap, deterministic, no LLM.

    A corrupt file therefore fails immediately rather than 400 items later, and
    it fails the WHOLE registration: a half-registered batch would leave the org
    unable to tell which files made it in.
    """
    # The count cap FIRST: it must cost arithmetic, not work. The service
    # re-checks it (the invariant lives there); this copy exists so an
    # over-cap batch is refused before a single PDF is decoded.
    cap = caps.screening_max_batch_items
    if len(req.items) > cap:
        raise HTTPException(
            status_code=422, detail=f"a batch holds at most {cap} items"
        )
    texts: list[str] = []
    for i, item in enumerate(req.items):
        try:
            text = read_resume_input(resume_text=item.resume_text,
                resume_pdf_b64=item.resume_pdf_b64, settings=caps)
        except ResumeInputError as exc:
            raise HTTPException(status_code=422, detail=f"item {i}: {exc.detail}") from None
        texts.append(text)
    return texts


def _org_user_id(request: Request) -> Optional[str]:
    """The human behind the call, or None for a machine credential."""
    principal = getattr(request.state, "principal", None)
    return getattr(principal, "org_user_id", None)


@org_router.post("/screening/batches", response_model=BatchDetail)
async def create_screening_batch(
    req: BatchCreateRequest, request: Request, org_id: str = Depends(require_org)
) -> BatchDetail:
    services = _services(request)
    texts = _batch_texts(req, services.settings)
    try:
        return services.screening.register(
            org_id, name=req.name, domain=req.domain, texts=texts,
            created_by_org_user_id=_org_user_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@org_router.get(
    "/screening/batches", response_model=BatchPage,
    description="Batches this organisation registered, newest first. Cursor-paginated; pass `next_cursor` back as `cursor`.",
)
async def list_screening_batches(
    request: Request,
    org_id: str = Depends(require_org),
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> BatchPage:
    try:
        return _services(request).screening.list(org_id, cursor=cursor, limit=limit)
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@org_router.get("/screening/batches/{batch_id}", response_model=BatchDetail)
async def get_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> BatchDetail:
    """404 -- never 403 -- for another org's batch."""
    found = _services(request).screening.get(org_id, batch_id)
    if found is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return found


@org_router.post("/screening/batches/{batch_id}/process", response_model=ProcessResult)
async def process_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> ProcessResult:
    """Bounded by `screening_max_items_per_call`. Call it until `remaining` is 0.

    An item whose claim goes stale becomes claimable again, so a batch
    interrupted by a redeploy heals on the next call rather than wedging.

    Bounded per CALLER too since S8.3: `screening_max_items_per_call` caps one
    request and says nothing about a client in a loop, and every call bills a
    model.
    """
    try:
        result = await _services(request).screening.process(
            org_id, batch_id, engine=request.app.state.engine
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return result


@org_router.post("/screening/batches/{batch_id}/retry", response_model=RetryResult)
async def retry_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> RetryResult:
    """Re-queue this batch's failed items, then call `process` as usual.

    It RE-QUEUES; it does not process. There is exactly one door that evaluates
    an item and this is not a second one -- which is also why an item with no
    remaining text is reported as `skipped` rather than quietly re-queued: a
    `requeued` count the next process call cannot honour is a lie.
    """
    result = _services(request).screening.retry(org_id, batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return result


@org_router.get(
    "/screening/batches/{batch_id}/queue", response_model=QueuePage,
    description="The fraud-screen queue, riskiest first. Cursor-paginated; pass `next_cursor` back as `cursor`.",
)
async def screening_batch_queue(
    batch_id: str,
    request: Request,
    org_id: str = Depends(require_org),
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> QueuePage:
    """The fraud-screen read-model: riskiest first, unscreened rows last."""
    try:
        page = _services(request).screening.queue(
            org_id, batch_id, cursor=cursor, limit=limit
        )
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if page is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return page


@org_router.get("/screening/batches/{batch_id}/summary", response_model=BatchSummary)
async def screening_batch_summary(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> BatchSummary:
    found = _services(request).screening.summary(org_id, batch_id)
    if found is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return found


@org_router.delete("/screening/batches/{batch_id}", response_model=BatchDeleteResponse)
async def delete_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> BatchDeleteResponse:
    """A real delete path on a new table, shipped in the sprint that creates it
    -- `batch_items.raw_text` is personal data with no candidate to cascade
    from (spec §4.2)."""
    if not _services(request).screening.delete(org_id, batch_id):
        raise HTTPException(status_code=404, detail="batch not found")
    return BatchDeleteResponse(batch_id=batch_id, deleted=True)
