"""Admin feature materialization API operation.

The operation keeps the shared principal/CSRF gate; feature and
materialization contracts keep their existing product owners.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.dependencies import _services, require_api_key
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate


router = APIRouter(dependencies=[Depends(require_api_key)])


class MaterializeRequest(BaseModel):
    candidate_ids: Optional[list[str]] = None
    as_of: Optional[datetime] = None
    view_name: Optional[str] = None


class MaterializeResponse(BaseModel):
    view_name: str
    view_version: int
    as_of: Optional[datetime] = None
    materialized: int = 0
    skipped: int = 0


@router.post("/features/materialize", response_model=MaterializeResponse)
async def materialize_features(
    body: MaterializeRequest, request: Request
) -> MaterializeResponse:
    """Compute + persist feature vectors. ADMIN plane, deliberately.

    Materialization spans ALL candidates and is consent-masked per candidate
    (S4.2), so on the org plane one customer's call would compute vectors over
    every customer's people. It is an operator action.

    Until this route existed, `app/features/materialize.py` was reachable only
    from Python -- which made `GET /jobs/{id}/board`'s empty-pool state
    permanent for a self-registered org rather than transient.
    """
    services = _services(request)
    registry = get_feature_registry()
    view = default_view(registry, settings=services.settings)
    # Only the default view exists today. Refusing an unknown name is honest;
    # accepting it, materializing the default anyway and echoing the caller's
    # name back was a response claiming work that never happened.
    if body.view_name is not None and body.view_name != view.name:
        raise HTTPException(
            status_code=422,
            detail=f"unknown view '{body.view_name}'; only '{view.name}' exists",
        )

    ids = body.candidate_ids
    if ids is None:
        ids = services.candidates.list_candidate_ids(
            services.settings.materialize_max_candidates
        )

    snapshot_time = body.as_of if body.as_of is not None else datetime.now(timezone.utc)
    materialized = skipped = 0
    for candidate_id in ids:
        mv = materialize_candidate(
            candidate_id, view=view, registry=registry, as_of=snapshot_time,
            candidate_store=services.candidates,
            report_store=services.report_store,
            ledger_store=services.ledger,
        )
        if mv is None:
            # No context for this candidate (unknown id, or nothing to compute).
            skipped += 1
            continue
        if services.features.upsert_vector(mv) is None:
            # Erasure after computation is a skipped subject, like a missing ID.
            skipped += 1
        else:
            materialized += 1

    return MaterializeResponse(
        view_name=view.name, view_version=view.version, as_of=snapshot_time,
        materialized=materialized, skipped=skipped,
    )
