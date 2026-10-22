"""Operator review of source-owned unmapped terms and approved vocabulary.

Shared principal/CSRF dependencies guard both operations. Curation services own
revision checks, persistence and refresh of the deterministic skill overlay.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import _services, require_api_key
from app.curation.schema import (
    CurationAction, CurationDecision, CurationStatus, UnmappedPage,
)
from app.curation.service import AliasConflictError
from app.curation.store import StaleReviewError
from app.screening.pagination import InvalidCursor


router = APIRouter(dependencies=[Depends(require_api_key)])


class CurationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    norm_key: str = Field(min_length=1, max_length=128)
    action: CurationAction
    alias: Optional[str] = Field(default=None, min_length=1, max_length=128)
    canonical: Optional[str] = Field(default=None, min_length=1, max_length=64)
    category: Optional[str] = Field(default=None, min_length=1, max_length=32)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get(
    "/curation/skills/unmapped", response_model=UnmappedPage,
    description=(
        "The unmapped-term review queue. Cursor-paginated; pass `next_cursor` back as `cursor`. NOTE the sort key "
        "(occurrences, last_seen) is mutable, so paging is stable against "
        "inserts and not against re-observation."
    ),
)
async def list_unmapped_terms(
    request: Request,
    status: Optional[CurationStatus] = None,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> UnmappedPage:
    try:
        return _services(request).curation.list_unmapped(status, limit, cursor=cursor)
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/curation/skills/resolve", response_model=CurationDecision)
async def resolve_unmapped_term(
    req: CurationResolveRequest, request: Request
) -> CurationDecision:
    services = _services(request)
    try:
        return services.curation.resolve(
            req.norm_key, req.action, alias=req.alias, canonical=req.canonical,
            category=req.category, admin_user_id=request.state.principal.admin_user_id,
            expected_revision=req.expected_revision,
        )
    except StaleReviewError:
        raise HTTPException(status_code=409, detail="review snapshot changed; refresh before deciding") from None
    except AliasConflictError:
        raise HTTPException(status_code=409, detail="approved alias already exists") from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="term not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
