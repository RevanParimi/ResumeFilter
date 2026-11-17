"""Employer requisitions and advisory role boards.

Every operation resolves its organization through the shared principal/CSRF gate.
Matching contracts retain their product owner.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.dependencies import _services, require_org
from app.matching.schema import (
    JobRequisition, JobRequisitionInput, RequisitionBoard, RequisitionStatus,
)


org_router = APIRouter()


# ── Demand side: job requisitions + role-conditioned matching (S5.1) ─────────
# Org plane (X-Org-Key). Requisitions are org-owned; match is advisory and
# audits every surfaced candidate as a disclosure. Consent was masked at S4.2.


class JobUpdateRequest(BaseModel):
    status: Optional[RequisitionStatus] = None
    spec: Optional[JobRequisitionInput] = None


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


# ── Employer role board (S5.3) ───────────────────────────────────────────────
# Org plane (X-Org-Key). Read-only composition over requisitions and matching. Advisory; no new
# state, no new consent purpose, no new audit path.


@org_router.get("/jobs/{req_id}/board", response_model=RequisitionBoard)
async def job_board(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> RequisitionBoard:
    board = _services(request).jobs.board(org_id, req_id)
    if board is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    if board.match.pool_size == 0:
        board = board.model_copy(update={
            "match": board.match.model_copy(
                update={"reason": "no_materialized_candidates"}
            )
        })
    return board
