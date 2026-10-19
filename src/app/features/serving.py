"""Current authorization for serving historical feature values.

Admin search uses the platform's any-active-ledger_read basis. Employer matching
requires a grant for that organization (or a wildcard). Neither snapshot as_of
nor cached materialization consent authorizes a present use.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.features.registry import FeatureRegistry
from app.features.schema import FeatureVector
from app.ledger.consent import check_consent, has_any_active
from app.ledger.schema import ConsentDecision, ConsentPurpose
from app.ledger.store import LedgerStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def current_consent(
    candidate_id: str, *, ledger_store: LedgerStore, org_id: str | None = None,
) -> ConsentDecision:
    """Fresh ledger_read permission; historical cuts never authorize this use."""
    grants = ledger_store.consents_for_candidate(candidate_id)
    moment = _utcnow()
    if org_id is None:
        return has_any_active(grants, purpose=ConsentPurpose.LEDGER_READ, at=moment)
    return check_consent(grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_READ, at=moment)


def mask_consent_vector(
    vector: FeatureVector, *, registry: FeatureRegistry, allowed: bool,
) -> FeatureVector:
    """Apply a boundary's decision to a copy, including all registered versions."""
    if allowed:
        return vector
    gated = {spec.name for spec in registry.specs() if spec.requires_consent}
    withheld = sorted(gated.intersection(vector.values))
    if not withheld:
        return vector
    values = dict(vector.values)
    values.update({name: None for name in withheld})
    missing = tuple(dict.fromkeys((*vector.missing, *withheld)))
    return vector.model_copy(update={"values": values, "missing": missing})


def current_consent_vectors(
    vectors: list[FeatureVector],
    *,
    registry: FeatureRegistry,
    ledger_store: LedgerStore,
    org_id: str | None = None,
) -> list[FeatureVector]:
    """Mask before filtering/normalization/scoring; leave persisted cuts intact.

    Stored vectors lack per-member versions, so a name gated in any registered
    version remains gated. Permission is read freshly per candidate, with time
    checked after that read; errors propagate. This is a snapshot, not a lock
    across scoring or HTTP delivery. An allowed read cannot restore a value that
    was withheld when materialized.
    """
    gated = {spec.name for spec in registry.specs() if spec.requires_consent}
    result = []
    for vector in vectors:
        withheld = sorted(gated.intersection(vector.values))
        if not withheld:
            result.append(vector)
            continue
        decision = current_consent(vector.candidate_id, ledger_store=ledger_store, org_id=org_id)
        result.append(mask_consent_vector(vector, registry=registry, allowed=decision.allowed))
    return result
