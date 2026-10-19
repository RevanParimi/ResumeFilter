"""Review preconditions on actual migrated SQLite/PostgreSQL observations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import select

from app.curation.schema import CurationAction
from tests.test_curation_owned_store import (  # noqa: F401
    owned, capture, raw_rows, approve, competing_store, assert_blocked,
)
from tests.test_curation_storage_migration import migrated, NOW  # noqa: F401


def test_revisions_identify_replacements_with_identical_visible_aggregates(owned):
    store, engine, t, _ = owned
    capture(store)
    first = store.get_observation("cobol")
    assert store.get_observation("cobol").review_revision == first.review_revision
    assert len(first.review_revision) == 64
    with engine.connect() as conn:
        observation = conn.execute(select(t["curation_observations"])).mappings().one()
    assert observation["id"] not in first.review_revision
    store.resolve_observations("cobol", action=CurationAction.IGNORE,
                               expected_revision=first.review_revision)
    capture(store)
    second = store.get_observation("cobol")
    assert first.model_dump(exclude={"review_revision"}) == second.model_dump(exclude={"review_revision"})
    assert first.review_revision != second.review_revision
    from app.curation.store import StaleReviewError
    with pytest.raises(StaleReviewError):
        approve(store, expected_revision=first.review_revision)
    assert len(raw_rows(engine, t)) == 1 and store.load_owned_overlay() == {}
    approve(store, expected_revision=second.review_revision)
    assert raw_rows(engine, t) == []
    with pytest.raises(LookupError):
        approve(store, expected_revision=first.review_revision)


@pytest.mark.parametrize("change", ["capture", "erase", "expiry", "display"])
@pytest.mark.parametrize("action", [CurationAction.IGNORE, CurationAction.MAP])
def test_changed_live_sets_roll_back_stale_claims(owned, change, action):
    from app.curation.store import StaleReviewError

    store, engine, t, clock = owned
    capture(store)
    clock[0] += timedelta(days=1)
    capture(store, "source-b")
    prior = store.get_observation("cobol")
    if change == "capture":
        capture(store)
    elif change == "erase":
        with engine.begin() as conn:
            conn.execute(t["candidates"].delete().where(t["candidates"].c.id == "a"))
    elif change == "expiry":
        clock[0] = NOW + timedelta(days=30)
    else:
        with engine.begin() as conn:
            conn.execute(t["curation_observations"].update().values(display_name="Changed raw"))
    fresh = store.get_observation("cobol")
    assert fresh.review_revision != prior.review_revision
    before = raw_rows(engine, t)
    vocabulary = {} if action == CurationAction.IGNORE else {
        "alias": "Approved revision", "canonical": "python", "category": "language"}
    with pytest.raises(StaleReviewError):
        store.resolve_observations("cobol", action=action, expected_revision=prior.review_revision, **vocabulary)
    assert raw_rows(engine, t) == before and store.load_owned_overlay() == {}
    store.resolve_observations("cobol", action=action, expected_revision=fresh.review_revision, **vocabulary)
    assert raw_rows(engine, t) == []


def test_unrelated_capture_and_expired_history_do_not_invalidate_review(owned):
    store, engine, t, clock = owned
    capture(store)
    clock[0] += timedelta(days=29)
    capture(store)
    clock[0] += timedelta(days=1)
    snapshot = store.get_observation("cobol")
    assert snapshot.occurrences == 1
    capture(store, name="Unrelated raw")
    assert store.get_observation("cobol").review_revision == snapshot.review_revision
    approve(store, expected_revision=snapshot.review_revision)
    assert [r["norm_key"] for r in raw_rows(engine, t)] == ["unrelated raw"]


def test_revision_is_bound_to_term_and_absent_expired_compatibility(owned):
    from app.curation.store import StaleReviewError

    store, engine, t, clock = owned
    capture(store)
    capture(store, name="Different raw")
    revision = store.get_observation("different raw").review_revision
    with pytest.raises(StaleReviewError):
        approve(store, expected_revision=revision)
    assert len(raw_rows(engine, t)) == 2
    revision = store.get_observation("cobol").review_revision
    clock[0] += timedelta(days=30)
    with pytest.raises(LookupError, match="term not found"):
        approve(store, expected_revision=revision)
    assert [r["norm_key"] for r in raw_rows(engine, t)] == ["different raw"]
    assert store.load_owned_overlay() == {}


@pytest.mark.parametrize("change", ["erase", "expiry"])
def test_postgres_stale_revision_rechecked_after_actual_lock_wait(owned, change):
    from app.curation.store import StaleReviewError

    store, engine, t, clock = owned
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    capture(store)
    clock[0] += timedelta(days=1)
    capture(store, "source-b")
    clock[0] = NOW + timedelta(days=30) - timedelta(seconds=1)
    revision = store.get_observation("cobol").review_revision
    ready, pids = Event(), []
    with ThreadPoolExecutor(max_workers=1) as pool, engine.connect() as conn:
        transaction = conn.begin()
        try:
            if change == "erase":
                conn.execute(t["profile_sources"].delete().where(t["profile_sources"].c.id == "source-a"))
            else:
                conn.execute(select(t["curation_observations"]).with_for_update())
            pending = pool.submit(competing_store, engine, ready, pids,
                lambda other: approve(other, expected_revision=revision))
            assert_blocked(engine, pending, ready, pids)
            if change == "expiry":
                clock[0] += timedelta(seconds=1)
            transaction.commit()
            with pytest.raises(StaleReviewError):
                pending.result(timeout=10)
        finally:
            if transaction.is_active:
                transaction.rollback()
    assert len(raw_rows(engine, t)) == (1 if change == "erase" else 2)
    assert store.load_owned_overlay() == {}
    approve(store, expected_revision=store.get_observation("cobol").review_revision)
    assert raw_rows(engine, t) == []


def test_postgres_two_guarded_reviewers_have_one_winner(owned, monkeypatch):
    store, engine, t, _ = owned
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    capture(store)
    revision = store.get_observation("cobol").review_revision
    claimed, release, ready, pids = Event(), Event(), Event(), []

    def pause_after_claim():
        claimed.set()
        assert release.wait(15)
        return NOW

    monkeypatch.setattr("app.curation.store._utcnow", pause_after_claim)
    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(approve, store, expected_revision=revision)
        try:
            assert claimed.wait(10)
            monkeypatch.setattr("app.curation.store._utcnow", lambda: NOW)
            loser = pool.submit(competing_store, engine, ready, pids,
                lambda other: other.resolve_observations("cobol", action=CurationAction.IGNORE,
                    expected_revision=revision))
            assert_blocked(engine, loser, ready, pids)
            release.set()
            assert winner.result(timeout=10).alias == "Approved COBOL"
            with pytest.raises(LookupError, match="term not found"):
                loser.result(timeout=10)
        finally:
            release.set()
    assert raw_rows(engine, t) == []
    assert store.load_owned_overlay()["approved cobol"].canonical == "cobol"
