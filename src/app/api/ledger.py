"""Ledger organization and consent administration routes.

Admin authentication is router-scoped and uses the shared principal and
cookie/CSRF boundary.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import _services, require_api_key
from app.ledger.schema import (
    ConsentDecision, ConsentGrant, ConsentPurpose, Organization,
)


router = APIRouter(dependencies=[Depends(require_api_key)])


class OrgDeletedResponse(BaseModel):
    org_id: str
    deleted: bool


class ConsentRevokedResponse(BaseModel):
    consent_id: str
    revoked: bool


class OrgKeyResponse(BaseModel):
    """Returned ONCE at issuance; only the hash is stored."""

    org_id: str
    api_key: str


class OrgCreateRequest(BaseModel):
    name: str


class OrgCreateResponse(BaseModel):
    org: Organization
    api_key: str  # returned once; only its hash is stored


@router.post("/ledger/orgs", response_model=OrgCreateResponse)
async def create_org(req: OrgCreateRequest, request: Request) -> OrgCreateResponse:
    ledger = _services(request).ledger
    try:
        org = ledger.create_organization(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrgCreateResponse(org=org, api_key=ledger.issue_api_key(org.id))


@router.get("/ledger/orgs", response_model=list[Organization])
async def list_orgs(request: Request) -> list[Organization]:
    return _services(request).ledger.list_organizations()


@router.post("/ledger/orgs/{org_id}/api-key", response_model=OrgKeyResponse)
async def rotate_org_key(org_id: str, request: Request) -> OrgKeyResponse:
    try:
        api_key = _services(request).ledger.issue_api_key(org_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"org_id": org_id, "api_key": api_key}


@router.delete("/ledger/orgs/{org_id}", response_model=OrgDeletedResponse)
async def delete_org(org_id: str, request: Request) -> OrgDeletedResponse:
    if not _services(request).ledger.delete_organization(org_id):
        raise HTTPException(status_code=404, detail="organization not found")
    return {"org_id": org_id, "deleted": True}


class ReliabilityRequest(BaseModel):
    weight: float = Field(ge=0.0)


@router.post("/ledger/orgs/{org_id}/reliability", response_model=Organization)
async def set_org_reliability(
    org_id: str, req: ReliabilityRequest, request: Request
) -> Organization:
    """Admin: set an org's per-org reliability multiplier for S3.4 reputation
    aggregation (neutral default 1.0). A negative weight is a 422 at the
    boundary."""
    try:
        return _services(request).ledger.set_org_reliability(org_id, req.weight)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ConsentGrantRequest(BaseModel):
    purpose: ConsentPurpose
    org_id: Optional[str] = None  # None = any member org
    expires_at: Optional[datetime] = None  # None ⇒ default TTL


@router.post("/ledger/candidates/{candidate_id}/consent", response_model=ConsentGrant)
async def grant_consent(
    candidate_id: str, req: ConsentGrantRequest, request: Request
) -> ConsentGrant:
    ledger = _services(request).ledger
    try:
        return ledger.grant_consent(
            candidate_id=candidate_id,
            purpose=req.purpose,
            org_id=req.org_id,
            expires_at=req.expires_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ledger/consent/{consent_id}/revoke", response_model=ConsentRevokedResponse)
async def revoke_consent(consent_id: str, request: Request) -> ConsentRevokedResponse:
    revoked = _services(request).ledger.revoke_consent(consent_id)
    return {"consent_id": consent_id, "revoked": revoked}


@router.get("/ledger/candidates/{candidate_id}/consent", response_model=ConsentDecision)
async def consent_status(
    candidate_id: str, request: Request, org_id: str, purpose: ConsentPurpose
) -> ConsentDecision:
    try:
        return _services(request).ledger.consent_status(
            candidate_id, org_id=org_id, purpose=purpose
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
