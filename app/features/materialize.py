"""Materialize a FeatureView over a point-in-time context (PI-4 / S4.2).

Pure orchestration: slice the context (build_context), compute the view, then
apply the per-candidate consent decision -- consent-tagged features (ledger.* /
reputation.*, i.e. spec.requires_consent) are nulled unless an active ledger_read
grant governs the candidate at as_of. First-party features always survive. The
consent decision itself is audited in LedgerStore.materialization_consent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from app.features.context import build_context
from app.features.registry import FeatureRegistry
from app.features.schema import FeatureVector, FeatureView


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MaterializedVector:
    vector: FeatureVector
    consent_state: dict
    materialized_at: datetime


def materialize_candidate(
    candidate_id: str,
    *,
    view: FeatureView,
    registry: FeatureRegistry,
    as_of: Optional[datetime] = None,
    candidate_store,
    report_store,
    ledger_store,
) -> Optional[MaterializedVector]:
    ctx = build_context(
        candidate_id,
        candidate_store=candidate_store,
        report_store=report_store,
        ledger_store=ledger_store,
        as_of=as_of,
    )
    if ctx is None:
        return None

    vector = registry.compute_view(view, ctx)
    decision = ledger_store.materialization_consent(candidate_id, at=ctx.as_of)

    if decision.allowed:
        consent_state = {"allowed": True, "consent_id": decision.grant_id}
    else:
        consent_state = {"allowed": False, "reason": decision.reason}
        consent_names = [
            rf.spec.name for rf in view.resolve(registry) if rf.spec.requires_consent
        ]
        if consent_names:
            values = dict(vector.values)
            missing = list(vector.missing)
            for name in consent_names:
                values[name] = None
                if name not in missing:
                    missing.append(name)
            vector = vector.model_copy(update={"values": values, "missing": tuple(missing)})

    return MaterializedVector(vector=vector, consent_state=consent_state, materialized_at=_utcnow())


def materialize_all(
    candidate_ids: Iterable[str],
    *,
    view: FeatureView,
    registry: FeatureRegistry,
    as_of: Optional[datetime] = None,
    candidate_store,
    report_store,
    ledger_store,
) -> list[MaterializedVector]:
    out: list[MaterializedVector] = []
    for cid in candidate_ids:
        mv = materialize_candidate(
            cid, view=view, registry=registry, as_of=as_of,
            candidate_store=candidate_store, report_store=report_store, ledger_store=ledger_store,
        )
        if mv is not None:
            out.append(mv)
    return out
