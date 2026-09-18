"""Real competing connections; events select the interleaving, never sleeps."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Event
import uuid

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.reports.models import OutcomeRow, ReportRow
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import SqlReportStore, SubjectErasedError
from tests.test_report_store import _report


@pytest.fixture(params=["sqlite", "postgresql"])
def database(request, tmp_path):
    bootstrap = None
    schema = None
    if request.param == "sqlite":
        engine = make_engine("sqlite:///" + (tmp_path / "race.db").as_posix())
    else:
        url = os.environ.get("DEE_TEST_DB_URL", "").strip()
        if not url:
            pytest.skip("Disposable PostgreSQL DEE_TEST_DB_URL not configured")
        bootstrap = create_engine(url)
        schema = "r1_race_" + uuid.uuid4().hex
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        factory = make_session_factory(engine)
        with factory() as session:
            session.add_all([CandidateRow(id="a"), CandidateRow(id="b")])
            session.commit()
        yield engine, factory
    finally:
        engine.dispose()
        if bootstrap is not None:
            with bootstrap.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            bootstrap.dispose()


def _outcome(report_id, notes="synthetic private outcome sentinel"):
    return OutcomeRecord(report_id=report_id, notes=notes,
                         outcome=OutcomeLabel.INCONCLUSIVE,
                         recorded_by=OutcomeSource.OPERATOR)


@pytest.mark.parametrize("operation", ["insert", "update", "outcome"])
def test_erasure_between_read_and_flush(database, operation, log_output):
    engine, factory = database
    reports = SqlReportStore(factory)
    a = _report(candidate_id="a", summary="synthetic private claim sentinel")
    b = _report(candidate_id="b")
    reports.save(b)
    reports.add_outcome(_outcome(b.id, "keep B"))
    if operation != "insert":
        reports.save(a)
    stale = a.model_copy(update={"summary": "synthetic private revised sentinel"})
    writer_factory = make_session_factory(engine)
    writer = SqlReportStore(writer_factory)
    ready, release = Event(), Event()

    def pause(session, *_):
        ready.set()
        assert release.wait(20), "erasure did not release writer"

    event.listen(writer_factory, "before_flush", pause)
    write = (lambda: writer.add_outcome(_outcome(a.id))) if operation == "outcome" else (
        lambda: writer.save(stale))
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(write)
            try:
                assert ready.wait(20), "writer did not reach flush"
                assert CandidateStore(factory).delete_candidate("a")
            finally:
                release.set()
            if operation == "outcome":
                assert pending.result(timeout=20) is False
            else:
                with pytest.raises(SubjectErasedError):
                    pending.result(timeout=20)
    finally:
        event.remove(writer_factory, "before_flush", pause)

    # Retry the same stale work after erasure, including the former UPDATE.
    if operation == "outcome":
        assert write() is False
    else:
        with pytest.raises(SubjectErasedError):
            write()
    assert reports.get(a.id) is None
    assert reports.outcomes(a.id) == []
    assert reports.get(b.id) == b
    assert [o.notes for o in reports.outcomes(b.id)] == ["keep B"]
    assert "integrity_race" in log_output.text or "write_race" in log_output.text
    for private in ("synthetic private", "Fine-tuned Llama", "INSERT INTO", "UPDATE reports"):
        assert private not in log_output.text


@pytest.mark.parametrize("door", ["operator", "organization"])
def test_outcome_api_returns_404_when_erased_after_authorization(services, monkeypatch, door):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.conftest import ADMIN_HEADERS

    factory = services.candidates._session_factory
    with factory() as session:
        session.add_all([CandidateRow(id="a"), CandidateRow(id="b")])
        session.commit()
    org = services.ledger.create_organization("Synthetic agency")
    key = services.ledger.issue_api_key(org.id)
    a, b = _report(candidate_id="a"), _report(candidate_id="b")
    for report in (a, b):
        services.report_store.save(report, org_id=org.id)
    services.report_store.add_outcome(_outcome(b.id, "keep B"))
    original = services.report_store.add_outcome
    calls = []

    def erase_then_write(rec):
        calls.append(rec.report_id)
        assert services.portal.erase("a")["deleted"]
        return original(rec)

    monkeypatch.setattr(services.report_store, "add_outcome", erase_then_write)
    path = f"/report/{a.id}/outcome" if door == "operator" else f"/screening/reports/{a.id}/outcome"
    headers = ADMIN_HEADERS if door == "operator" else {"X-Org-Key": key}
    with TestClient(create_app(services), raise_server_exceptions=False) as client:
        for _ in range(2):
            response = client.post(path, headers=headers, json={
                "outcome": "inconclusive", "notes": "synthetic private outcome sentinel",
            })
            assert response.status_code == 404
            assert "synthetic private" not in response.text
    assert calls == [a.id]  # first request reached persistence; retry failed on read
    assert services.report_store.get(a.id) is None
    assert services.report_store.outcomes(a.id) == []
    assert services.report_store.get(b.id) == b
    assert [o.notes for o in services.report_store.outcomes(b.id)] == ["keep B"]


def test_committed_report_and_outcome_are_swept_by_erasure(database):
    engine, factory = database
    committed, deleted = Event(), Event()
    a = _report(candidate_id="a")
    reports = SqlReportStore(factory)
    b = _report(candidate_id="b")
    reports.save(b)

    def write_first():
        writer = SqlReportStore(make_session_factory(engine))
        writer.save(a)
        assert writer.add_outcome(_outcome(a.id))
        committed.set()
        assert deleted.wait(20)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(write_first)
        try:
            assert committed.wait(20)
            assert CandidateStore(factory).delete_candidate("a")
        finally:
            deleted.set()
        pending.result(timeout=20)
    with factory() as session:
        assert list(session.scalars(select(ReportRow.id))) == [b.id]
        assert list(session.scalars(select(OutcomeRow.id))) == []


def test_unrelated_integrity_error_is_not_erasure(database, log_output):
    _, factory = database
    reports = SqlReportStore(factory)
    with pytest.raises(IntegrityError):
        reports.save(_report(candidate_id="a"), org_id="missing-org")
    a = _report(candidate_id="a")
    reports.save(a)
    bad = _outcome(a.id).model_copy(update={"org_id": "missing-org"})
    with pytest.raises(IntegrityError):
        reports.add_outcome(bad)
    for private in ("Fine-tuned Llama", "synthetic private", "INSERT INTO"):
        assert private not in log_output.text


def test_report_only_deletion_does_not_claim_candidate_erasure(database):
    engine, factory = database
    reports = SqlReportStore(factory)
    a = _report(candidate_id="a")
    reports.save(a)
    writer_factory = make_session_factory(engine)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "before_flush", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(SqlReportStore(writer_factory).save,
                                      a.model_copy(update={"summary": "changed"}))
            try:
                assert ready.wait(20)
                assert reports.delete(a.id)
            finally:
                release.set()
            with pytest.raises(StaleDataError):
                pending.result(timeout=20)
    finally:
        event.remove(writer_factory, "before_flush", pause)
    assert CandidateStore(factory).get_candidate("a") is not None
    assert reports.get(a.id) is None
