"""Report-only erasure must survive interrupted batch completion cleanup."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import delete, event, select, text

from app.candidates.models import ResumeRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.reports.models import ReportRow
from app.reports.store import SqlReportStore
from app.screening.ingest import IngestRefused
from app.screening.models import BatchItemRow, ScreeningInputRow
from app.screening.store import ScreeningStore
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report
from tests.test_screening_batches_api import _client, _key, _register
from tests.test_screening_durable_input import Interrupted, NOW, ingest_bound, prepare


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_completion", "after_rollback"])
async def test_report_erasure_survives_interrupted_cleanup(services, monkeypatch, phase):
    org, _ = _key(services)
    batch = services.screening.register(org, name="Synthetic", domain="genai",
        texts=["Synthetic engineer\nSkills: Python"], created_by_org_user_id=None)
    factory = services.candidates._session_factory
    store = services.screening._store
    original = store.complete

    class Engine:
        async def evaluate(self, **kwargs):
            return _report()

    def interrupt(*_):
        raise Interrupted()

    def complete(*args, **kwargs):
        assert services.report_store.delete(kwargs["report_id"])
        if phase == "before_completion":
            raise Interrupted()
        event.listen(store._session_factory, "after_soft_rollback", interrupt, once=True)
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "complete", complete)
        with pytest.raises(Interrupted):
            await services.screening.process(org, batch.id, engine=Engine())
    with factory() as session:
        assert list(session.scalars(select(ReportRow))) == []
        assert len(list(session.scalars(select(ResumeRow)))) == 1
        assert list(session.scalars(select(ScreeningInputRow))) == []
        row = session.scalars(select(BatchItemRow)).one()
        assert row.raw_text == row.text_sha256 == ""
        row.claimed_at -= timedelta(days=1)
        session.commit()
    result = await services.screening.process(org, batch.id, engine=Engine())
    assert (result.processed, result.failed) == (0, 1)
    retry = services.screening.retry(org, batch.id)
    assert (retry.requeued, retry.skipped) == (0, 1)
    with factory() as session:
        assert list(session.scalars(select(ReportRow))) == []



def save_bound(factory, org, item, report):
    def bind(session, saved):
        if not ScreeningStore(factory).bind_input_report(session, org, item, saved):
            raise IngestRefused("input_unavailable")
    SqlReportStore(factory).save(report, org_id=org, before_commit=bind)


def test_unrelated_report_integrity_failure_preserves_existing_input(database):
    from sqlalchemy.exc import IntegrityError

    _, factory = database
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    original = _report(candidate_id=saved.candidate_id)
    save_bound(factory, org, item, original)
    invalid = _report(candidate_id=saved.candidate_id).model_copy(update={"domain": None})
    with pytest.raises(IntegrityError):
        save_bound(factory, org, item, invalid)
    with factory() as session:
        assert session.get(ReportRow, invalid.id) is None
        assert session.get(ScreeningInputRow, item.id).report_id == original.id


def test_report_and_binding_roll_back_together(database):
    engine, factory = database
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    report = _report(candidate_id=saved.candidate_id)
    writer = make_session_factory(engine)

    def interrupt(*_):
        raise Interrupted()

    event.listen(writer, "before_commit", interrupt, once=True)
    with pytest.raises(Interrupted):
        save_bound(writer, org, item, report)
    with factory() as session:
        assert session.get(ReportRow, report.id) is None
        assert session.get(ScreeningInputRow, item.id).report_id is None
    save_bound(factory, org, item, report)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id).report_id == report.id


@pytest.mark.parametrize("change", ["lease", "batch", "sweep", "resume", "report"])
def test_abandoned_report_cannot_commit_or_restore_input(database, change):
    engine, factory = database
    org, batch, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    old = _report(candidate_id=saved.candidate_id)
    save_bound(factory, org, item, old)
    report = _report(candidate_id=saved.candidate_id)
    writer = make_session_factory(engine)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer, "before_flush", pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        writing = executor.submit(save_bound, writer, org, item, report)
        try:
            assert ready.wait(20)
            store = ScreeningStore(factory)
            if change == "lease":
                store.claim(org, batch, limit=1, now=NOW + timedelta(seconds=901), timeout_seconds=900)
            elif change == "batch":
                assert store.delete_batch(org, batch)
            elif change == "sweep":
                with factory() as session:
                    session.execute(delete(ScreeningInputRow).where(ScreeningInputRow.id == item.id))
                    session.commit()
            elif change == "resume":
                assert CandidateStore(factory).delete_resume(saved.resume_id)
            else:
                assert SqlReportStore(factory).delete(old.id)
        finally:
            release.set()
        with pytest.raises(IngestRefused, match="input_unavailable"):
            writing.result(timeout=20)
    with factory() as session:
        assert session.get(ReportRow, report.id) is None
        ref = session.get(ScreeningInputRow, item.id)
        if change == "lease":
            assert ref.report_id == old.id
        else:
            assert ref is None


@pytest.mark.parametrize("mismatch", ["tenant", "candidate"])
def test_binding_rejects_wrong_report_ownership(database, mismatch):
    _, factory = database
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    other = LedgerStore(factory).create_organization("Other").id
    report = _report(candidate_id=saved.candidate_id if mismatch == "tenant" else "b")
    with pytest.raises(IngestRefused, match="input_unavailable"):
        save_bound(factory, other if mismatch == "tenant" else org, item, report)
    with factory() as session:
        assert session.get(ReportRow, report.id) is None
        assert session.get(ScreeningInputRow, item.id).report_id is None


def test_postgres_report_delete_waits_for_binding_commit(database):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    report = _report(candidate_id=saved.candidate_id)
    SqlReportStore(factory).save(report, org_id=org)
    writer, deleter = make_session_factory(engine), make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}

    def pause(session):
        pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)

    def started(session, transaction, connection):
        pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()

    event.listen(writer, "before_commit", pause, once=True)
    event.listen(deleter, "after_begin", started, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(save_bound, writer, org, item, report)
        try:
            assert ready.wait(20)
            erasing = executor.submit(SqlReportStore(deleter).delete, report.id)
            assert deleting.wait(20)
            deadline = monotonic() + 10
            with engine.connect() as observer:
                while monotonic() < deadline:
                    if pids["writer"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                        {"pid": pids["deleter"]}):
                        break
                else:
                    pytest.fail("report erasure did not wait for binding commit")
            assert not erasing.done()
        finally:
            release.set()
        writing.result(timeout=20)
        assert erasing.result(timeout=20)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
        assert session.get(ResumeRow, saved.resume_id) is not None


def test_http_interrupted_completion_retries_same_resume_and_preserves_completed_counts(services, monkeypatch):
    _, key = _key(services)
    _, other_key = _key(services, "Other")
    headers = {"X-Org-Key": key}
    store = services.screening._store

    # Simulate an ordinary completion failure after report save. It records a
    # failed item; retry remains possible while the bound report still exists.
    def fail(item_id, **kwargs):
        assert store.fail(item_id, lease=kwargs["lease"], error="internal_error", at=NOW)
        return False

    with _client(services) as http:
        batch = _register(http, key, ["Synthetic engineer\nSkills: Python"]).json()["id"]
        path = f"/screening/batches/{batch}"
        with monkeypatch.context() as patch:
            patch.setattr(store, "complete", fail)
            response = http.post(path + "/process", headers=headers)
        assert response.status_code == 200 and response.json()["failed"] == 1
        with services.candidates._session_factory() as session:
            ref = session.scalars(select(ScreeningInputRow)).one()
            rid, report_id = ref.resume_id, ref.report_id
            assert report_id is not None
        assert http.post(path + "/retry", headers={"X-Org-Key": other_key}).status_code == 404
        assert http.post(path + "/retry", headers=headers).json()["requeued"] == 1
        assert http.post(path + "/process", headers=headers).json()["processed"] == 1
        row = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert row["resume_id"] == rid and row["report_id"] != report_id
        assert services.report_store.delete(row["report_id"])
        after = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert after == {**row, "report_id": None}
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ScreeningInputRow))) == []


def test_populated_report_migration_preserves_input_without_inferred_links(database):
    import runpy
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    engine, factory = database
    org, batch, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    report = _report(candidate_id=saved.candidate_id)
    save_bound(factory, org, item, report)
    store = ScreeningStore(factory)
    store.add_items(org, batch, texts=["Second synthetic input"])
    erased_item = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    erased = ingest_bound(factory, org, erased_item)
    erased_report = _report(candidate_id=erased.candidate_id)
    save_bound(factory, org, erased_item, erased_report)
    assert SqlReportStore(factory).delete(erased_report.id)
    store.add_items(org, batch, texts=["Legacy ambiguous input"])
    migration = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                  "alembic/versions/0025_screening_input_report.py"))
    with engine.begin() as connection:
        before = connection.execute(text(
            "SELECT id, resume_id, created_at FROM screening_item_inputs")).all()
        with Operations.context(MigrationContext.configure(connection)):
            migration["downgrade"]()
            assert connection.execute(text(
                "SELECT id, resume_id, created_at FROM screening_item_inputs")).all() == before
            migration["upgrade"]()
        assert connection.execute(text(
            "SELECT id, resume_id, created_at FROM screening_item_inputs")).all() == before
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id).report_id is None
        assert session.get(ScreeningInputRow, erased_item.id) is None
        assert session.get(BatchItemRow, erased_item.id).raw_text == ""
        assert session.scalar(select(BatchItemRow.id).where(
            BatchItemRow.raw_text == "Legacy ambiguous input")) is not None
    # Only a new explicit save binds the restored schema's nullable link.
    save_bound(factory, org, item, report)
    assert SqlReportStore(factory).delete(report.id)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
        assert session.get(ResumeRow, saved.resume_id) is not None
