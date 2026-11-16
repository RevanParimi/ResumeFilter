"""Candidate portal, consent/access and erasure.

Candidate operations resolve their subject through the shared principal/CSRF gate;
services retain erasure policy.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from app.api.candidates import ErasureResponse
from app.api.dependencies import _services, require_candidate
from app.api.ledger import ConsentRevokedResponse
from app.core.blocking import ExecutionPending, ExecutionUnavailable
from app.ledger.schema import ConsentGrant, ConsentPurpose
from app.portal.schema import AccessLogEntry, ConsentView, MyData
from app.portal.service import PortalSubjectErasedError
from app.profile_sources.store import SourceSubjectErasedError


candidate_router = APIRouter()
log = structlog.get_logger(__name__)


async def _portal_read(request: Request, operation, *args):
    try:
        return await _services(request).portal_reads.run(operation, *args)
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        raise HTTPException(status_code=503, detail='portal_read_pending',
                            headers={'Retry-After': '1'}) from None
    except (PortalSubjectErasedError, SourceSubjectErasedError):
        raise
    except Exception as exc:
        # Preserve the generic correlated 500 while keeping worker/SQL details
        # out of the application's traceback logger.
        rid = getattr(request.state, 'request_id', '')
        log.error('portal_read_failed', request_id=rid, error_type=type(exc).__name__)
        return JSONResponse(status_code=500, content={'detail': 'internal_error', 'request_id': rid},
                            headers={'X-Request-ID': rid} if rid else None)


async def _portal_write(request: Request, operation, *args, **kwargs):
    try:
        return await _services(request).portal_writes.run(operation, *args, **kwargs)
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        raise HTTPException(status_code=503, detail='portal_write_pending',
                            headers={'Retry-After': '1'}) from None
    except LookupError:
        raise
    except Exception as exc:
        rid = getattr(request.state, 'request_id', '')
        log.error('portal_write_failed', request_id=rid, error_type=type(exc).__name__)
        return JSONResponse(status_code=500, content={'detail': 'internal_error', 'request_id': rid},
                            headers={'X-Request-ID': rid} if rid else None)


# ── Candidate DPDP portal (S6.4) ─────────────────────────────────────────────
# Candidate plane (X-Candidate-Key). First-party access / transparency / consent
# control / erasure over the candidate's own data. No new ConsentPurpose — auth
# == identity of the data subject. Every route acts on the resolved candidate_id.


@candidate_router.get("/portal/me", response_model=MyData)
async def portal_me(request: Request, candidate_id: str = Depends(require_candidate)) -> MyData:
    try:
        return await _portal_read(request, _services(request).portal.my_data, candidate_id)
    except (PortalSubjectErasedError, SourceSubjectErasedError):
        raise HTTPException(status_code=404, detail="candidate not found") from None


@candidate_router.get("/portal/access-log", response_model=list[AccessLogEntry])
async def portal_access_log(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[AccessLogEntry]:
    try:
        return await _portal_read(request, _services(request).portal.access_log, candidate_id)
    except PortalSubjectErasedError:
        raise HTTPException(status_code=404, detail="candidate not found") from None


@candidate_router.get("/portal/consents", response_model=list[ConsentView])
async def portal_list_consents(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[ConsentView]:
    try:
        return await _portal_read(request, _services(request).portal.consents, candidate_id)
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
        return await _portal_write(request, _services(request).portal.grant,
            candidate_id, purpose=req.purpose, org_id=req.org_id, expires_at=req.expires_at
        )
    except LookupError as exc:  # unknown org_id
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@candidate_router.post("/portal/consents/{consent_id}/revoke", response_model=ConsentRevokedResponse)
async def portal_revoke_consent(
    consent_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> ConsentRevokedResponse:
    try:
        revoked = await _portal_write(request, _services(request).portal.revoke, candidate_id, consent_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="consent grant not found") from exc
    if isinstance(revoked, JSONResponse):
        return revoked
    return {"consent_id": consent_id, "revoked": revoked}


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
