"""Admin accounts, retention, metrics and advisory signal-quality reports.

Shared principal/CSRF dependencies guard every operation. Separate router
segments preserve the existing API registration order around other areas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.dependencies import _services, require_api_key
from app.auth.schema import AdminUser
from app.retention.schema import SweepReport
from app.retention.sweep import run_sweep
from app.signal_quality.labels import LedgerLabelSource, OutcomesLabelSource
from app.signal_quality.schema import SignalQualityReport
from app.signal_quality.service import measure


metrics_router = APIRouter(dependencies=[Depends(require_api_key)])
retention_router = APIRouter(dependencies=[Depends(require_api_key)])
router = APIRouter(dependencies=[Depends(require_api_key)])


class AdminUserDeletedResponse(BaseModel):
    admin_user_id: str
    deleted: bool


class SweepRequest(BaseModel):
    """``dry_run`` DEFAULTS TO TRUE.

    This is the most destructive call in the repo, and defaulting it the other
    way would make an empty body -- the easiest thing to send by accident, and
    what a mistyped curl sends -- delete production data. A cron passes
    ``{"dry_run": false}`` explicitly, which is one word of evidence that
    somebody meant it.
    """

    dry_run: bool = True


class AdminUserRequest(BaseModel):
    email: str
    label: str = ""


@metrics_router.get("/metrics", response_model=str, response_class=PlainTextResponse)
async def metrics(request: Request) -> PlainTextResponse:
    """Prometheus text exposition (S8.3 Phase A).

    On the ADMIN router, so `require_api_key` is inherited rather than
    remembered and the route-table guard covers it with no edit.

    `response_model=str` is honest -- the body IS a string -- and it keeps
    tests/test_openapi_contract.py's every-route-declares-a-model rule intact
    without carving out an exemption for one route.
    """
    return PlainTextResponse(
        _services(request).metrics.render(),
        media_type="text/plain; version=0.0.4",
    )


@retention_router.post("/admin/retention/sweep", response_model=SweepReport)
async def retention_sweep(req: SweepRequest, request: Request) -> SweepReport:
    """Run (or preview) the retention sweep. Admin plane.

    There is no scheduler in the application, so this route and
    ``python -m app.retention.sweep`` are the only two ways the sweep ever
    runs. Both go through ``run_sweep``, so the refusal below cannot be
    enforced at one door and forgotten at the other.
    """
    services = _services(request)
    if not req.dry_run and not services.settings.retention_sweep_enabled:
        # 409, not 403: the CONFIGURATION is in the wrong state, and the
        # operator's fix is a knob rather than a credential. A dry run is still
        # allowed, because a count is safe and is how they see what would go.
        raise HTTPException(status_code=409, detail="retention_sweep_disabled")
    return run_sweep(
        services.session_factory,
        services.settings,
        now=datetime.now(timezone.utc),
        dry_run=req.dry_run,
        metrics=services.metrics,
    )


@router.post("/admin/users", response_model=AdminUser)
async def create_admin_user(req: AdminUserRequest, request: Request) -> AdminUser:
    """Bootstrap reuses the shared key rather than inventing a mechanism.

    X-API-Key already exists and already fails closed (S8.1), so it becomes the
    machine/root credential while operator accounts become the human one -- the
    two-modes-per-plane rule applied to the admin plane. No boot-time side
    effects, no DEE_ADMIN_BOOTSTRAP_EMAIL, no chicken-and-egg.
    """
    services = _services(request)
    email_hash = services.auth.hash_email(req.email)
    if services.auth.find_admin_user(email_hash) is not None:
        raise HTTPException(status_code=409, detail="operator already exists")
    return services.auth.create_admin_user(
        email_hash=email_hash, label=req.label
    ).model_dump(mode="json")


@router.get("/admin/signal-quality", response_model=SignalQualityReport)
async def signal_quality_report(
    request: Request,
    source: Literal["outcomes", "ledger"] = "outcomes",
    include_operator_labels: bool = False,
) -> SignalQualityReport:
    """Do the advisory numbers predict what a human concluded? Admin plane.

    ADMIN ONLY, AND THERE IS NO ORG-PLANE VARIANT. This report is cross-tenant
    by construction: an organisation must not be able to learn how well the
    fraud screen performs against other organisations' candidates. The honest
    per-org version ("how is it doing on MY pipeline") is a different question
    with its own sample-size problem, and inventing it here would ship a number
    computed from a handful of rows.

    Expect refusals. Below the sample floor, on a one-class sample, or for a
    signal this source cannot score, each signal says so and carries no numbers
    at all -- see app/signal_quality/service.py.
    """
    services = _services(request)
    if source == "ledger":
        label_source = LedgerLabelSource(services.report_store, services.ledger)
    else:
        label_source = OutcomesLabelSource(
            services.report_store, include_operator_labels=include_operator_labels
        )
    return measure(
        label_source,
        min_samples=services.settings.min_signal_quality_samples,
        bins=services.settings.signal_quality_curve_bins,
    )


@router.get("/admin/users", response_model=list[AdminUser])
async def list_admin_users(request: Request) -> list[AdminUser]:
    return [
        a.model_dump(mode="json")
        for a in _services(request).auth.list_admin_users()
    ]


@router.delete("/admin/users/{admin_user_id}", response_model=AdminUserDeletedResponse)
async def delete_admin_user(admin_user_id: str, request: Request) -> AdminUserDeletedResponse:
    """A hard delete: their sessions CASCADE away with them."""
    if not _services(request).auth.delete_admin_user(admin_user_id):
        raise HTTPException(status_code=404, detail="operator not found")
    return {"admin_user_id": admin_user_id, "deleted": True}
