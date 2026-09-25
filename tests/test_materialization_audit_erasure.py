"""Erasure at the consent-audit boundary must cancel just that subject."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.features.models import FeatureVectorRow
from app.ledger.models import AuditLogRow
from app.ledger.store import LedgerStore
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.test_interview_erasure import _candidate
from tests.test_report_erasure_concurrency import database


NOW = datetime.now(timezone.utc)


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("order", ["erase_first", "audit_first"])
def test_audit_erasure_order(database, allowed, order, log_output):
    engine, factory = database
    ledger = LedgerStore(factory)
    if allowed:
        ledger.grant_consent(candidate_id="a", purpose="ledger_read", now=NOW)
    writer_factory = make_session_factory(engine)
    writer = LedgerStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    hook = "before_flush" if order == "erase_first" else "after_commit"
    event.listen(writer_factory, hook, pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(writer.materialization_consent, "a", at=NOW)
            try:
                assert ready.wait(20)
                assert CandidateStore(factory).delete_candidate("a")
            finally:
                release.set()
            if order == "erase_first":
                with pytest.raises(LookupError):
                    pending.result(timeout=20)
            else:
                assert pending.result(timeout=20).allowed is allowed
    finally:
        event.remove(writer_factory, hook, pause)
    with pytest.raises(LookupError):
        writer.materialization_consent("a", at=NOW)
    assert ledger.audit_for_candidate("a") == []
    assert not ledger.materialization_consent("b", at=NOW).allowed
    assert [a.action for a in ledger.audit_for_candidate("b")] == ["feature.materialize"]
    assert "INSERT INTO" not in log_output.text


def test_unrelated_integrity_error_propagates(database):
    _, factory = database
    ledger = LedgerStore(factory)

    def invalid(session, *_):
        for row in session.new:
            if isinstance(row, AuditLogRow):
                row.action = None

    event.listen(factory, "before_flush", invalid, once=True)
    with pytest.raises(IntegrityError):
        ledger.materialization_consent("a", at=NOW)
    assert CandidateStore(factory).get_candidate("a") is not None
    assert ledger.audit_for_candidate("a") == []
    assert not ledger.materialization_consent("a", at=NOW).allowed


@pytest.mark.parametrize("door", ["admin", "portal"])
@pytest.mark.parametrize("boundary", ["before_check", "before_flush", "after_commit"])
@pytest.mark.parametrize("allowed", [False, True])
def test_api_skips_subject_erased_during_consent_audit(services, monkeypatch, door, boundary, allowed):
    cid, _ = _candidate(services)
    bid, _ = _candidate(services, "Surviving candidate")
    if allowed:
        services.ledger.grant_consent(candidate_id=cid, purpose="ledger_read",
                                      now=NOW - timedelta(days=1))
    original = services.ledger.materialization_consent
    writer_factory = make_session_factory(services.candidates._session_factory.kw["bind"])
    monkeypatch.setattr(services.ledger, "_session_factory", writer_factory)

    def erase(*_):
        if door == "portal":
            assert services.portal.erase(cid)["deleted"]
        else:
            assert services.candidates.delete_candidate(cid)

    if boundary == "before_check":
        def erase_then_check(candidate_id, **kwargs):
            if candidate_id == cid:
                erase()
            return original(candidate_id, **kwargs)
        monkeypatch.setattr(services.ledger, "materialization_consent", erase_then_check)
    else:
        event.listen(writer_factory, boundary, erase, once=True)

    body = {"candidate_ids": [cid, "missing", bid]}
    with TestClient(create_app(services), headers=ADMIN_HEADERS,
                    raise_server_exceptions=False) as client:
        for _ in range(2):
            response = client.post("/features/materialize", json=body)
            assert response.status_code == 200, response.text
            assert (response.json()["materialized"], response.json()["skipped"]) == (1, 2)
            assert cid not in response.text and "INSERT INTO" not in response.text
    assert services.ledger.audit_for_candidate(cid) == []
    with services.candidates._session_factory() as session:
        assert set(session.scalars(select(FeatureVectorRow.candidate_id))) == {bid}
    assert any(a.action == "feature.materialize" for a in services.ledger.audit_for_candidate(bid))


def test_materializer_does_not_hide_unrelated_lookup_error(services, monkeypatch):
    from app.features import default_view, get_feature_registry
    from app.features.materialize import materialize_candidate
    cid, _ = _candidate(services)

    def broken(*args, **kwargs):
        raise LookupError("unrelated lookup failure")

    monkeypatch.setattr(services.ledger, "materialization_consent", broken)
    registry = get_feature_registry()
    with pytest.raises(LookupError, match="unrelated lookup failure"):
        materialize_candidate(cid, view=default_view(registry, settings=services.settings),
            registry=registry, candidate_store=services.candidates,
            report_store=services.report_store, ledger_store=services.ledger)


def test_postgres_audit_flush_orders_before_erasure(database):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    writer, deleter = make_session_factory(engine), make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}

    def pause(session, *_):
        pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)

    def started(session, transaction, connection):
        pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()

    event.listen(writer, "after_flush", pause, once=True)
    event.listen(deleter, "after_begin", started, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(LedgerStore(writer).materialization_consent, "a", at=NOW)
        try:
            assert ready.wait(20)
            erasing = executor.submit(CandidateStore(deleter).delete_candidate, "a")
            assert deleting.wait(20)
            with engine.connect() as observer:
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    if pids["writer"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                         {"pid": pids["deleter"]}):
                        break
                else:
                    pytest.fail("erasure did not wait for audit foreign-key lock")
            assert not erasing.done()
        finally:
            release.set()
        assert not pending.result(timeout=20).allowed
        assert erasing.result(timeout=20)
    assert LedgerStore(factory).audit_for_candidate("a") == []
