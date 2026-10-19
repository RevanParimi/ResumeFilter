"""Serving authorization against isolated stores, including competing reads."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from app.features import get_feature_registry
from app.features.materialize import MaterializedVector
from app.features.ranking import apply_filters, score
from app.features.ranking_schema import FeatureFilter, FilterOp, RankingSpec, RankingTerm
from app.features.schema import FeatureVector
from app.features.serving import current_consent_vectors
from app.features.store import FeatureStore
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from tests.test_report_erasure_concurrency import database  # noqa: F401

CUT = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _seed(factory):
    ledger, features = LedgerStore(factory), FeatureStore(factory)
    a, b = ledger.create_organization("A"), ledger.create_organization("B")
    for cid, value in [("a", 0.9), ("b", 0.2)]:
        features.upsert_vector(MaterializedVector(
            FeatureVector(candidate_id=cid, as_of=CUT, view_name="core_v1", view_version=1,
                          values={"reputation.score": value, "candidate.num_skills": 3}),
            {"allowed": True}, CUT,
        ))
    return ledger, features, a, b


@pytest.mark.parametrize("scope", ["org_a", "org_b", "platform", "wildcard"])
def test_present_scope_is_per_candidate_not_cached(database, monkeypatch, scope):
    _, factory = database
    ledger, features, a, b = _seed(factory)
    monkeypatch.setattr("app.features.serving._utcnow", lambda: NOW)
    ledger.grant_consent(candidate_id="a", org_id=None if scope == "wildcard" else a.id,
                         purpose=ConsentPurpose.LEDGER_READ, now=CUT, expires_at=NOW + timedelta(days=1))
    # Another candidate's active, different-purpose grant is never a substitute.
    ledger.grant_consent(candidate_id="b", org_id=b.id, purpose=ConsentPurpose.VERIFICATION_READ,
                         now=CUT, expires_at=NOW + timedelta(days=1))
    org_id = b.id if scope in {"org_b", "wildcard"} else a.id if scope == "org_a" else None
    raw = features.latest_vectors_for_view("core_v1", 1, as_of=CUT)
    vectors = current_consent_vectors([mv.vector for mv in raw], registry=get_feature_registry(),
                                      ledger_store=ledger, org_id=org_id)
    by_id = {v.candidate_id: v for v in vectors}
    assert by_id["a"].values["reputation.score"] == (None if scope == "org_b" else 0.9)
    assert by_id["b"].values["reputation.score"] is None
    assert all(v.values["candidate.num_skills"] == 3 for v in vectors)
    assert all(mv.consent_state["allowed"] for mv in raw)


def test_revoke_committed_after_vector_read_is_seen_by_serving(database, monkeypatch):
    _, factory = database
    ledger, features, a, b = _seed(factory)
    monkeypatch.setattr("app.features.serving._utcnow", lambda: NOW)
    grant = ledger.grant_consent(candidate_id="a", org_id=a.id, purpose=ConsentPurpose.LEDGER_READ,
                                 now=CUT, expires_at=NOW + timedelta(days=1))
    ledger.grant_consent(candidate_id="b", org_id=b.id, purpose=ConsentPurpose.LEDGER_READ,
                         now=CUT, expires_at=NOW + timedelta(days=1))
    ready, release = Event(), Event()
    registry = get_feature_registry()
    specs = {"reputation.score": registry.get("reputation.score").spec}

    def serve():
        raw = features.latest_vectors_for_view("core_v1", 1, as_of=CUT)
        ready.set()
        assert release.wait(20), "revocation did not release serving"
        vectors = current_consent_vectors([mv.vector for mv in raw], registry=registry, ledger_store=ledger)
        selected = apply_filters(vectors, [FeatureFilter(feature="reputation.score", op=FilterOp.EXISTS)], specs)
        return score(selected, RankingSpec(terms=(RankingTerm(feature="reputation.score", weight=1),)), specs)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(serve)
        try:
            assert ready.wait(20), "serving did not read historical vectors"
            assert LedgerStore(factory).revoke_consent(grant.id, now=NOW)
        finally:
            release.set()
        rows = future.result(timeout=20)
    assert [r.candidate_id for r in rows] == ["b"]
    assert rows[0].contributions[0].raw == 0.2


def test_permission_storage_failure_does_not_authorize_cached_values(database, monkeypatch):
    _, factory = database
    ledger, features, _, _ = _seed(factory)
    def fail(_):
        raise RuntimeError("synthetic unavailable consent store")
    monkeypatch.setattr(ledger, "consents_for_candidate", fail)
    raw = features.latest_vectors_for_view("core_v1", 1, as_of=CUT)
    with pytest.raises(RuntimeError, match="unavailable consent store"):
        current_consent_vectors([mv.vector for mv in raw], registry=get_feature_registry(), ledger_store=ledger)


def test_expiry_is_checked_after_permission_read(database, monkeypatch):
    _, factory = database
    ledger, features, a, _ = _seed(factory)
    expires = NOW + timedelta(seconds=1)
    clock = [NOW]
    monkeypatch.setattr("app.features.serving._utcnow", lambda: clock[0])
    ledger.grant_consent(candidate_id="a", org_id=a.id, purpose=ConsentPurpose.LEDGER_READ,
                         now=CUT, expires_at=expires)
    original = ledger.consents_for_candidate
    def read(cid):
        grants = original(cid)
        clock[0] = expires
        return grants
    monkeypatch.setattr(ledger, "consents_for_candidate", read)
    raw = features.latest_vectors_for_view("core_v1", 1, as_of=CUT)
    vectors = current_consent_vectors([mv.vector for mv in raw], registry=get_feature_registry(), ledger_store=ledger)
    assert all(v.values["reputation.score"] is None for v in vectors)


def test_later_ungated_definition_cannot_unmask_older_gated_values(database, monkeypatch):
    from app.features.registry import FeatureRegistry
    from app.features.schema import FeatureDType, FeatureSource, FeatureSpec
    _, factory = database
    ledger, features, _, _ = _seed(factory)
    monkeypatch.setattr("app.features.serving._utcnow", lambda: NOW)
    registry = FeatureRegistry()
    for version, source, gated in [(1, FeatureSource.REPUTATION, True), (2, FeatureSource.CANDIDATE, False)]:
        registry.register(FeatureSpec(name="reputation.score", version=version, dtype=FeatureDType.NUMERIC,
                                      source=source, requires_consent=gated, description="version probe"), lambda _: 0.0)
    raw = features.latest_vectors_for_view("core_v1", 1, as_of=CUT)
    vectors = current_consent_vectors([mv.vector for mv in raw], registry=registry, ledger_store=ledger)
    assert all(v.values["reputation.score"] is None for v in vectors)
