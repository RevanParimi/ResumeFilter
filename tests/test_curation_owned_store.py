"""Owned lifecycle behavior on migrated, disposable SQLite and PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import MetaData, Table, event, select, text
from sqlalchemy.exc import IntegrityError

from app.core.db import make_session_factory
from app.curation.schema import CurationAction
from app.curation.store import CurationStore
from tests.test_curation_storage_migration import NOW, migrated, seed, tables  # noqa: F401


@pytest.fixture
def owned(migrated, monkeypatch):
    engine, _ = migrated
    t = tables(engine)
    seed(engine, t)
    clock = [NOW]
    monkeypatch.setattr("app.curation.store._utcnow", lambda: clock[0], raising=False)
    return CurationStore(make_session_factory(engine)), engine, t, clock


def capture(store, source="source-a", name="COBOL!"):
    return store.record_observation(name, source_id=source)


def approve(store, key="cobol", **kwargs):
    return store.resolve_observations(key, action=CurationAction.CREATE,
        alias="Approved COBOL", canonical="cobol", category="language", **kwargs)


def raw_rows(engine, t):
    with engine.connect() as conn:
        return conn.execute(select(t["curation_observations"])).mappings().all()


def test_owned_capture_requires_saved_source_and_preserves_repeat_lifetimes(owned):
    store, engine, t, clock = owned
    assert capture(store, "missing") is False
    assert capture(store)
    original = raw_rows(engine, t)[0]
    clock[0] += timedelta(days=29)
    assert capture(store)
    rows = raw_rows(engine, t)
    assert len(rows) == 2
    assert next(r for r in rows if r["id"] == original["id"]) == original
    clock[0] += timedelta(days=1)
    term = store.get_observation("cobol")
    assert term.occurrences == 1 and term.first_seen == NOW + timedelta(days=29)
    assert store.purge_expired() == 1
    assert len(raw_rows(engine, t)) == 1


def test_survivor_snapshot_recomputes_every_aggregate_and_hides_legacy(owned):
    store, engine, t, clock = owned
    with engine.begin() as conn:
        conn.execute(t["profile_sources"].update().where(t["profile_sources"].c.id == "source-b")
                     .values(source_type="github"))
    capture(store, "source-b", "Cobol")
    clock[0] += timedelta(hours=1)
    capture(store, name="COBOL!")
    from tests.curation_helpers import legacy_term
    legacy_term(store._session_factory)
    term = store.get_observation("cobol")
    assert term.display_name == "COBOL!" and term.occurrences == 2
    assert term.source_types == ["github", "linkedin"]
    with engine.begin() as conn:
        conn.execute(t["candidates"].delete().where(t["candidates"].c.id == "a"))
    terms, cursor = store.list_observations()
    assert cursor is None and len(terms) == 1
    assert terms[0].display_name == "Cobol" and terms[0].occurrences == 1
    assert terms[0].source_types == ["github"]
    assert terms[0].first_seen == terms[0].last_seen == NOW
    assert store.get_observation("legacy") is None
    with engine.begin() as conn:
        conn.execute(t["profile_sources"].delete().where(t["profile_sources"].c.id == "source-b"))
    assert store.list_observations() == ([], None)


def test_expiry_exact_cutoff_read_resolve_and_purge_are_distinct(owned):
    store, engine, t, clock = owned
    capture(store)
    clock[0] += timedelta(days=30) - timedelta(microseconds=1)
    assert store.get_observation("cobol") is not None
    clock[0] += timedelta(microseconds=1)
    assert store.get_observation("cobol") is None
    assert store.list_observations() == ([], None)
    assert len(raw_rows(engine, t)) == 1  # hiding is not physical deletion
    with pytest.raises(LookupError, match="term not found"):
        approve(store)
    assert raw_rows(engine, t) == []
    assert store.load_owned_overlay() == {}
    assert store.purge_expired() == 0


def test_explicit_promotion_keeps_only_approved_vocabulary_and_survives_erasure(owned):
    store, engine, t, _ = owned
    capture(store)
    capture(store, "source-b", "Cobol")
    result = approve(store)
    assert result.alias == "Approved COBOL" and result.action == CurationAction.CREATE
    assert result.admin_user_id is None
    assert raw_rows(engine, t) == []
    assert store.get_observation("cobol") is None
    with engine.begin() as conn:
        conn.execute(t["candidates"].delete())
    overlay = store.load_owned_overlay()
    assert "cobol" not in overlay  # raw key is not implicitly approved
    assert overlay["approved cobol"].canonical == "cobol"
    with engine.connect() as conn:
        rows = conn.execute(select(t["curation_aliases"])).mappings().all()
    assert len(rows) == 1 and rows[0]["alias"] == "Approved COBOL"
    assert "note" not in rows[0] and "decided_by" not in rows[0]
    with pytest.raises(LookupError, match="term not found"):
        approve(store)


def test_ignore_deletes_raw_and_allows_later_submission(owned):
    store, engine, t, _ = owned
    capture(store)
    decision = store.resolve_observations("cobol", action=CurationAction.IGNORE)
    assert decision.alias is None and decision.canonical is None
    assert raw_rows(engine, t) == [] and store.load_owned_overlay() == {}
    assert capture(store)
    assert store.get_observation("cobol").occurrences == 1


@pytest.mark.parametrize("values", [
    {"alias": None}, {"alias": "\tCOBOL"}, {"alias": " " * 129},
    {"alias": "!!!"}, {"canonical": ""}, {"canonical": "x" * 65},
    {"category": None}, {"category": "x" * 33}, {"action": "bad"},
    {"action": CurationAction.IGNORE},
])
def test_invalid_decision_cannot_delete_raw(owned, values):
    store, engine, t, _ = owned
    capture(store)
    args = dict(action=CurationAction.CREATE, alias="Approved COBOL",
                canonical="cobol", category="language") | values
    with pytest.raises(ValueError):
        store.resolve_observations("cobol", **args)
    assert len(raw_rows(engine, t)) == 1 and store.load_owned_overlay() == {}


def test_failed_approval_rolls_back_deletion_and_alias_conflict_is_explicit(owned):
    store, engine, t, _ = owned
    capture(store)
    with pytest.raises(IntegrityError):
        approve(store, admin_user_id="invented")
    assert len(raw_rows(engine, t)) == 1
    approve(store)
    capture(store)
    with pytest.raises(IntegrityError):
        approve(store)
    assert len(raw_rows(engine, t)) == 1
    assert store.load_owned_overlay()["approved cobol"].canonical == "cobol"


@pytest.mark.parametrize("name", ["", "!!!", " " * 129, "x" * 129, "\tCOBOL", "COBOL\x00"])
def test_raw_input_refused_without_storage(owned, name):
    store, engine, t, _ = owned
    assert not capture(store, name=name)
    assert raw_rows(engine, t) == []


def test_pagination_ties_expiry_and_survivor_order(owned):
    store, _, _, clock = owned
    for name in ("Zulu", "Alpha", "Bravo"):
        capture(store, name=name)
    first, cursor = store.list_observations(limit=1)
    assert [t.norm_key for t in first] == ["alpha"] and cursor
    second, cursor = store.list_observations(limit=1, cursor=cursor)
    assert [t.norm_key for t in second] == ["bravo"] and cursor
    third, cursor = store.list_observations(limit=1, cursor=cursor)
    assert [t.norm_key for t in third] == ["zulu"] and cursor is None
    clock[0] += timedelta(days=30)
    assert store.list_observations() == ([], None)
    with pytest.raises(ValueError):
        store.list_observations(cursor="malformed")
    with pytest.raises(ValueError):
        store.list_observations(limit=0)


def test_legacy_overlay_compatibility_and_new_alias_precedence(owned):
    store, engine, t, clock = owned
    from tests.curation_helpers import legacy_term
    legacy_term(store._session_factory, "approved cobol", status="resolved",
                canonical="python", category="language")
    with engine.connect() as conn:
        before = conn.execute(select(t["unmapped_terms"])).mappings().all()
    assert store.load_owned_overlay()["approved cobol"].canonical == "python"
    capture(store)
    approve(store)
    assert store.load_owned_overlay()["approved cobol"].canonical == "cobol"
    assert not capture(store, name="Approved COBOL")
    clock[0] += timedelta(days=31)
    store.purge_expired()
    with engine.connect() as conn:
        assert conn.execute(select(t["unmapped_terms"])).mappings().all() == before
    from app.candidates.normalize.skills import normalize_skill, set_curated_overlay
    set_curated_overlay(store.load_owned_overlay())
    assert normalize_skill("Approved COBOL").canonical == "cobol"
    assert normalize_skill("Python").canonical == "python"


def test_map_operator_identity_static_precedence_and_mixed_expiry(owned):
    store, engine, t, clock = owned
    admin = Table("admin_users", MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        conn.execute(admin.insert().values(id="operator", email_hash="synthetic", label="", created_at=NOW))
    capture(store)
    clock[0] += timedelta(days=29)
    capture(store, "source-b", "Cobol")
    clock[0] += timedelta(days=1)
    receipt = store.resolve_observations("cobol", action=CurationAction.MAP,
        alias="Python", canonical="cobol", category="language", admin_user_id="operator")
    assert receipt.admin_user_id == "operator" and raw_rows(engine, t) == []
    from app.candidates.normalize.skills import normalize_skill, set_curated_overlay
    set_curated_overlay(store.load_owned_overlay())
    assert normalize_skill("Python").canonical == "python"  # static wins even over this stored mapping
    with engine.begin() as conn:
        conn.execute(admin.delete())
    with engine.connect() as conn:
        approved = conn.execute(select(t["curation_aliases"])).mappings().one()
    assert approved["admin_user_id"] is None and approved["alias"] == "Python"


def test_decision_refuses_free_text_reviewer_fields(owned):
    store, engine, t, _ = owned
    capture(store)
    for field in ("note", "decided_by"):
        with pytest.raises(TypeError):
            store.resolve_observations("cobol", action=CurationAction.IGNORE,
                                       **{field: "Synthetic private text"})
    assert len(raw_rows(engine, t)) == 1


def competing_store(engine, ready, pids, operation):
    """Expose the real competing backend PID before starting its store action."""
    with engine.connect() as conn:
        pids.append(conn.scalar(text("SELECT pg_backend_pid()")))
        conn.commit()
        ready.set()
        return operation(CurationStore(make_session_factory(conn)))


def assert_blocked(engine, pending, ready, pids):
    assert ready.wait(10)
    deadline = monotonic() + 10
    with engine.connect() as conn:
        while monotonic() < deadline:
            if conn.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pids[0]}):
                assert not pending.done()
                return
    pytest.fail("competing store operation never blocked")


@pytest.mark.parametrize("target", ["candidates", "profile_sources"])
@pytest.mark.parametrize("operation", ["capture", "resolve"])
def test_postgres_delete_first_refuses_late_capture_or_promotion(owned, target, operation):
    store, engine, t, _ = owned
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    capture(store)
    ready, pids = Event(), []
    with ThreadPoolExecutor(max_workers=1) as pool, engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(t[target].delete().where(t[target].c.id ==
                         ("a" if target == "candidates" else "source-a")))
            pending = pool.submit(competing_store, engine, ready, pids,
                                  capture if operation == "capture" else approve)
            assert_blocked(engine, pending, ready, pids)
            transaction.commit()
            if operation == "capture":
                assert pending.result(timeout=10) is False
            else:
                with pytest.raises(LookupError, match="term not found"):
                    pending.result(timeout=10)
        finally:
            if transaction.is_active:
                transaction.rollback()
    assert raw_rows(engine, t) == [] and store.load_owned_overlay() == {}
    assert capture(store, "source-b")  # unrelated contributor remains usable


@pytest.mark.parametrize("competing", ["resolve", "delete", "purge"])
def test_postgres_resolution_claim_wins_without_recreating_raw(owned, monkeypatch, competing):
    store, engine, t, clock = owned
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    capture(store)
    claimed, release, ready, pids = Event(), Event(), Event(), []

    def pause_after_claim():
        # resolve's clock is sampled only after its atomic DELETE returns.
        claimed.set()
        assert release.wait(15)
        return NOW

    monkeypatch.setattr("app.curation.store._utcnow", pause_after_claim)
    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(approve, store)
        try:
            assert claimed.wait(10)
            # Only the winner pauses; the contender uses the ordinary test clock.
            clock[0] = NOW + timedelta(days=31) if competing == "purge" else NOW
            monkeypatch.setattr("app.curation.store._utcnow", lambda: clock[0])

            def contend(other):
                if competing == "resolve":
                    return approve(other)
                if competing == "purge":
                    return other.purge_expired()
                with other._session_factory.begin() as session:
                    session.execute(t["candidates"].delete().where(t["candidates"].c.id == "a"))

            pending = pool.submit(competing_store, engine, ready, pids, contend)
            assert_blocked(engine, pending, ready, pids)
            release.set()
            assert winner.result(timeout=10).alias == "Approved COBOL"
            if competing == "resolve":
                with pytest.raises(LookupError, match="term not found"):
                    pending.result(timeout=10)
            else:
                pending.result(timeout=10)
        finally:
            release.set()
    assert raw_rows(engine, t) == []
    assert store.load_owned_overlay()["approved cobol"].canonical == "cobol"


@pytest.mark.parametrize("purge_first", [False, True])
def test_postgres_expiry_during_lock_wait_refuses_approval(owned, purge_first):
    store, engine, t, clock = owned
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    capture(store)
    clock[0] = NOW + timedelta(days=30) - timedelta(seconds=1)
    ready, pids = Event(), []
    with ThreadPoolExecutor(max_workers=1) as pool, engine.connect() as conn:
        transaction = conn.begin()
        try:
            if purge_first:
                conn.execute(t["curation_observations"].delete())
            else:
                conn.execute(select(t["curation_observations"]).with_for_update())
            pending = pool.submit(competing_store, engine, ready, pids, approve)
            assert_blocked(engine, pending, ready, pids)
            clock[0] += timedelta(seconds=1)
            transaction.commit()
            with pytest.raises(LookupError, match="term not found"):
                pending.result(timeout=10)
        finally:
            if transaction.is_active:
                transaction.rollback()
    assert raw_rows(engine, t) == [] and store.load_owned_overlay() == {}


def test_source_write_rollback_cannot_be_captured(owned):
    store, engine, t, _ = owned
    with engine.connect() as conn:
        transaction = conn.begin()
        conn.execute(t["profile_sources"].insert().values(id="refused", candidate_id="a",
            source_type="github", identifier="synthetic", signal={}, method="parsed",
            fetched_at=NOW, created_at=NOW))
        transaction.rollback()
    assert capture(store, "refused") is False
    assert raw_rows(engine, t) == []


def test_postgres_capture_first_is_swept_by_waiting_erasure(owned):
    store, engine, t, _ = owned
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    inserted, release, ready, pids = Event(), Event(), Event(), []

    def pause_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO curation_observations"):
            inserted.set()
            assert release.wait(15)

    event.listen(engine, "after_cursor_execute", pause_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(capture, store)
            try:
                assert inserted.wait(10)

                def erase(other):
                    with other._session_factory.begin() as session:
                        session.execute(t["candidates"].delete().where(t["candidates"].c.id == "a"))

                pending = pool.submit(competing_store, engine, ready, pids, erase)
                assert_blocked(engine, pending, ready, pids)
                release.set()
                assert writer.result(timeout=10)
                pending.result(timeout=10)
            finally:
                release.set()
    finally:
        event.remove(engine, "after_cursor_execute", pause_insert)
    assert raw_rows(engine, t) == []
    assert capture(store, "source-b")
