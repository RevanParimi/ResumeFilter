"""Employer requisitions, compensation and dashboard API operations.

Every operation resolves its organization through the shared principal/CSRF gate.
Matching, compensation, ledger and dashboard contracts retain their product owners.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import _services, require_org
from app.comp import bands
from app.comp.schema import CITY_TIERS, ROLE_FAMILIES, CompBenchmark, SeniorityBand
from app.dashboard.schema import CandidateCard, DashboardOverview, RequisitionBoard
from app.ledger.schema import ObservedOffer
from app.ledger.store import ConsentError
from app.matching.schema import (
    JobRequisition, JobRequisitionInput, MatchResult, RequisitionStatus,
)


org_router = APIRouter()


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
