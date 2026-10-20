"""Admin feature materialization and advisory talent search API operations.

Historical cuts retain current-consent serving and the shared principal/CSRF gate.
Feature, materialization and ranking contracts keep their existing product owners.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import _services, require_api_key
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.ranking import apply_filters, score
from app.features.ranking_schema import FeatureFilter, RankingSpec, SearchResult
from app.features.serving import current_consent_vectors


router = APIRouter(dependencies=[Depends(require_api_key)])


# ── Talent search / ranking (S4.3) ──────────────────────────────────────────
# Admin plane (X-API-Key): platform-internal search over materialized feature
# vectors. Advisory — it narrows and orders, never auto-rejects.


class TalentSearchRequest(BaseModel):
    """Advisory talent search over materialized feature vectors (admin plane).

    ``ranking`` is required and non-empty. ``view_name``/``view_version`` default
    to the materialized default view; ``as_of`` defaults to its newest cut. Only
    the features referenced in ``filters``/``ranking`` are validated against the
    registry.
    """

    ranking: RankingSpec
    filters: list[FeatureFilter] = Field(default_factory=list)
    view_name: Optional[str] = None
    view_version: Optional[int] = None
    as_of: Optional[datetime] = None
    limit: Optional[int] = Field(default=None, ge=1)


@router.post(
    "/talent/search",
    response_model=SearchResult,
    description=(
        "Top-N advisory ranking. NOT paginated: the pool is re-ranked on every request, so there is no stable key to page on and a cursor would promise an ordering this endpoint cannot keep. Use `limit`."
    ),
)
async def talent_search(req: TalentSearchRequest, request: Request) -> SearchResult:
    """Filter + rank the materialized pool by a composite score. Advisory: it
    narrows and orders, never auto-rejects. Current platform ledger_read consent
    masks gated values before filters and scoring, independently of as_of."""
    services = _services(request)
    registry = get_feature_registry()

    # Resolve specs per referenced feature; an unknown name is a 400.
    referenced = {t.feature for t in req.ranking.terms} | {f.feature for f in req.filters}
    specs_by_name = {}
    for name in referenced:
        try:
            specs_by_name[name] = registry.get(name).spec
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    view_name = req.view_name or services.settings.feat_default_view
    view_version = (
        req.view_version
        if req.view_version is not None
        else default_view(registry, settings=services.settings).version
    )
    as_of = req.as_of or services.features.latest_as_of(view_name, view_version)

    pool = (
        services.features.latest_vectors_for_view(view_name, view_version, as_of=as_of)
        if as_of is not None
        else []
    )
    vectors = current_consent_vectors(
        [mv.vector for mv in pool], registry=registry, ledger_store=services.ledger,
    )

    try:
        filtered = apply_filters(vectors, req.filters, specs_by_name)
        ranked = score(filtered, req.ranking, specs_by_name)
    except (ValueError, KeyError, TypeError) as exc:
        # TypeError: a filter value whose type can't be compared to the feature
        # (e.g. a numeric feature vs a string) — a client error, not a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    limit = req.limit or services.settings.search_default_limit
    return SearchResult(
        advisory=True,
        as_of=as_of,
        view_name=view_name,
        view_version=view_version,
        pool_size=len(vectors),
        filtered_size=len(filtered),
        ranked=tuple(ranked[:limit]),
    )


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
