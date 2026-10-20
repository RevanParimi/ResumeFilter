"""Candidate portal, consent/access and reviewed data-principal requests.

Candidate operations resolve their subject through the shared principal/CSRF gate.
Operator requests keep a separate admin gate; services retain erasure/review policy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.candidates import ErasureResponse
from app.api.dependencies import _rate_limited, _services, require_api_key, require_candidate
from app.api.ledger import ConsentRevokedResponse
from app.ledger.schema import ConsentGrant, ConsentPurpose
from app.portal.schema import AccessLogEntry, ConsentView, MyData
from app.portal.service import PortalSubjectErasedError
from app.profile_sources.store import SourceSubjectErasedError
from app.ratelimit.service import RateLimited
from app.rights.schema import (
    CorrectionField, RequestAlreadyResolved, RequestKind, RequestRefused,
    RequestStatus, RequestView, ResolvedBy,
)
from app.screening.pagination import clamp_limit


candidate_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_api_key)])


# ── Candidate DPDP portal (S6.4) ─────────────────────────────────────────────
# Candidate plane (X-Candidate-Key). First-party access / transparency / consent
# control / erasure over the candidate's own data. No new ConsentPurpose — auth
# == identity of the data subject. Every route acts on the resolved candidate_id.


@candidate_router.get("/portal/me", response_model=MyData)
async def portal_me(request: Request, candidate_id: str = Depends(require_candidate)) -> MyData:
    try:
        return _services(request).portal.my_data(candidate_id)
    except (PortalSubjectErasedError, SourceSubjectErasedError):
        raise HTTPException(status_code=404, detail="candidate not found") from None


@candidate_router.get("/portal/access-log", response_model=list[AccessLogEntry])
async def portal_access_log(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[AccessLogEntry]:
    try:
        return _services(request).portal.access_log(candidate_id)
    except PortalSubjectErasedError:
        raise HTTPException(status_code=404, detail="candidate not found") from None


@candidate_router.get("/portal/consents", response_model=list[ConsentView])
async def portal_list_consents(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[ConsentView]:
    try:
        return _services(request).portal.consents(candidate_id)
    except PortalSubjectErasedError:
        raise HTTPException(status_code=404, detail="candidate not found") from None


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


@candidate_router.post("/portal/consents/{consent_id}/revoke", response_model=ConsentRevokedResponse)
async def portal_revoke_consent(
    consent_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> ConsentRevokedResponse:
    try:
        revoked = _services(request).portal.revoke(candidate_id, consent_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="consent grant not found") from exc
    return {"consent_id": consent_id, "revoked": revoked}


class CorrectionSubmitRequest(BaseModel):
    """`field` is the enum, so a field nobody implemented is a 422 from the
    model before any handler runs."""

    field: CorrectionField
    requested_value: str = ""
    note: str = ""


class GrievanceSubmitRequest(BaseModel):
    note: str = ""


@candidate_router.post("/portal/corrections", response_model=RequestView)
async def portal_submit_correction(
    req: CorrectionSubmitRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> RequestView:
    """File a correction request. It is REVIEWED, never applied on submission.

    On a fraud-screening platform, a subject write path onto the data the risk
    score is computed from is an edit box over the evidence (spec 0.3). What
    DPDP requires is the mechanism, and the mechanism starts here.
    """
    try:
        return _services(request).rights.submit(
            candidate_id,
            kind=RequestKind.CORRECTION,
            field=req.field,
            requested_value=req.requested_value,
            note=req.note,
            now=datetime.now(timezone.utc),
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    except RequestRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        # The subject erased themselves mid-call. 404, which by then is true.
        raise HTTPException(status_code=404, detail="candidate not found") from exc


@candidate_router.post("/portal/grievances", response_model=RequestView)
async def portal_submit_grievance(
    req: GrievanceSubmitRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> RequestView:
    try:
        return _services(request).rights.submit(
            candidate_id,
            kind=RequestKind.GRIEVANCE,
            field=None,
            requested_value="",
            note=req.note,
            now=datetime.now(timezone.utc),
        )
    except RateLimited as exc:
        raise _rate_limited(exc) from exc
    except RequestRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        # The subject erased themselves mid-call. 404, which by then is true.
        raise HTTPException(status_code=404, detail="candidate not found") from exc


@candidate_router.get("/portal/requests", response_model=list[RequestView])
async def portal_list_requests(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[RequestView]:
    """The subject's own requests, both kinds. Cross-candidate isolation is
    structural: the id comes from the resolver, never from a query param."""
    return _services(request).rights.for_candidate(candidate_id)


@candidate_router.delete("/portal/me", response_model=ErasureResponse)
async def portal_erase(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> ErasureResponse:
    """DPDP erasure, self-service.

    The SAME service call the admin plane makes, deliberately: erasure now has
    two entry points and every step -- the report count, the login challenges
    that cannot cascade, the candidate row itself -- lives in
    ``PortalService.erase`` so neither door can forget what the other does.

    Afterwards both the access key and every session stop authenticating: the
    credential and ``auth_sessions`` both CASCADE with the candidate row.
    """
    return _services(request).portal.erase(candidate_id)


class ResolveRequest(BaseModel):
    """One operator decision.

    `apply` defaults to FALSE. Recording a decision is the common case and the
    safe one; writing onto a person's identity row is the exception, and the
    exception is the one that should have to be asked for.
    """

    status: RequestStatus
    resolution: str = ""
    apply: bool = False


@router.get("/admin/requests", response_model=list[RequestView])
async def list_data_principal_requests(
    request: Request,
    status: Optional[RequestStatus] = None,
    limit: Optional[int] = None,
) -> list[RequestView]:
    """The operator's queue, OLDEST first -- a complaint that has waited
    longest is the one that should be answered next.

    Not tenant-scoped, deliberately: an operator handling DPDP requests has to
    see the queue, not one organisation's slice of it. These are requests from
    data principals to the PLATFORM, and no org is a party to them.

    `limit` goes through `clamp_limit`, the same helper every other paged read
    uses. It took a raw int until the Phase B review: `?limit=-1` reaches
    SQLite as an UNLIMITED select, so a bound that looked present returned the
    whole table -- of every data principal's complaints, free text included.
    """
    services = _services(request)
    try:
        bounded = clamp_limit(limit, services.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return services.rights.list_by_status(status, bounded)


@router.post("/admin/requests/{request_id}/resolve", response_model=RequestView)
async def resolve_data_principal_request(
    request_id: str, req: ResolveRequest, request: Request
) -> RequestView:
    """Decide one request, and record who decided.

    THREE outcomes, three statuses, picked by exception TYPE and never by
    matching on message text -- a translation keyed on wording breaks the first
    time somebody rewords a sentence. The `except` clauses are ordered
    subclass-first, or the 409 would be unreachable: RequestAlreadyResolved IS
    a RequestRefused.
    """
    services = _services(request)
    principal = request.state.principal
    admin_user_id = principal.admin_user_id if principal else None
    try:
        return services.rights.resolve(
            request_id,
            status=req.status,
            resolution=req.resolution,
            apply=req.apply,
            # A machine key has no human behind it. Recording OPERATOR_KEY
            # rather than leaving a bare NULL is what keeps "the shared
            # credential did this" distinguishable from "the admin who did has
            # since been deleted" (the S8.5 recorded_by argument).
            resolved_by=(
                ResolvedBy.ADMIN_USER if admin_user_id else ResolvedBy.OPERATOR_KEY
            ),
            admin_user_id=admin_user_id,
            now=datetime.now(timezone.utc),
        )
    except RequestAlreadyResolved as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RequestRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="request not found") from exc
