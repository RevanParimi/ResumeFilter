"""Retry input must share the lifetime of the successfully ingested resume."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import delete, event, select, text, update

from app.candidates.models import CandidateRow, ResumeRow
from app.candidates.store import CandidateErasedError, CandidateStore, ResumeErasedError
from app.core.db import make_session_factory
from app.graph.build import EvaluationEngine
from app.ledger.store import LedgerStore
from app.retention.sweep import run_sweep
from app.screening.ingest import IngestRefused
from app.screening.models import BatchItemRow, ScreeningInputRow
from app.screening.store import ScreeningStore
from tests.test_candidate_store import extraction
from tests.test_report_erasure_concurrency import database
from tests.test_screening_batches_api import _client, _key, _register


class Interrupted(BaseException):
    """Worker interruption bypasses the service's ordinary error handler."""


@pytest.mark.asyncio
@pytest.mark.parametrize("parent", ["candidate", "resume"])
@pytest.mark.parametrize("interrupted", [False, True])
async def test_ingested_input_erases_without_worker_cleanup(services, parent, interrupted):
    org, _ = _key(services)
    batch = services.screening.register(org, name="Synthetic", domain="genai",
        texts=["Synthetic engineer\nSkills: Python"], created_by_org_user_id=None)

    class FailingEngine:
        async def evaluate(self, **kwargs):
            if interrupted:
                raise Interrupted()
            raise RuntimeError("synthetic provider failure")

    if interrupted:
        with pytest.raises(Interrupted):
            await services.screening.process(org, batch.id, engine=FailingEngine())
    else:
        ran = await services.screening.process(org, batch.id, engine=FailingEngine())
        assert (ran.processed, ran.failed) == (0, 1)
    factory = services.candidates._session_factory
    with factory() as session:
        resume = session.scalars(select(ResumeRow)).one()
        rid, cid = resume.id, resume.candidate_id
    assert getattr(services.candidates, f"delete_{parent}")(cid if parent == "candidate" else rid)
    with factory() as session:
        row = session.scalars(select(BatchItemRow)).one()
        assert row.raw_text == row.text_sha256 == ""
        if interrupted:
            row.claimed_at -= timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
            session.commit()
    if not interrupted:
        retry = services.screening.retry(org, batch.id)
        assert (retry.requeued, retry.skipped) == (0, 1)
    await services.screening.process(org, batch.id, engine=EvaluationEngine(services))
    with factory() as session:
        assert list(session.scalars(select(ResumeRow))) == []
        if parent == "candidate":
            assert list(session.scalars(select(CandidateRow))) == []


def test_ordinary_retry_reuses_exact_resume_without_contact_identity(services, monkeypatch):
    _, key = _key(services)
    _, other_key = _key(services, "Other")
    headers = {"X-Org-Key": key}

    async def fail(*args, **kwargs):
        raise RuntimeError("synthetic provider failure")

    with _client(services) as http:
        batch = _register(http, key, ["Synthetic engineer\nSkills: Python"]).json()["id"]
        path = f"/screening/batches/{batch}"
        with monkeypatch.context() as patch:
            patch.setattr(EvaluationEngine, "evaluate", fail)
            ran = http.post(path + "/process", headers=headers)
        assert ran.status_code == 200 and ran.json()["failed"] == 1
        queue = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert queue["candidate_id"] is queue["resume_id"] is None
        with services.candidates._session_factory() as session:
            original = session.scalars(select(ResumeRow)).one()
            rid, cid = original.id, original.candidate_id
        assert http.post(path + "/retry", headers={"X-Org-Key": other_key}).status_code == 404
        assert http.post(path + "/retry", headers=headers).json()["requeued"] == 1
        ran = http.post(path + "/process", headers=headers)
        assert ran.status_code == 200 and ran.json()["processed"] == 1
        queue = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert (queue["candidate_id"], queue["resume_id"]) == (cid, rid)
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ResumeRow.id))) == [rid]
            assert list(session.scalars(select(ScreeningInputRow))) == []


NOW = datetime.now(timezone.utc)


def prepare(factory):
    org = LedgerStore(factory).create_organization("Synthetic agency").id
    store = ScreeningStore(factory)
    batch = store.create_batch(org, name="Synthetic", domain="genai",
                               texts=["private resume"], created_by_org_user_id=None)
    item = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    return org, batch, item


def bind(store, session, org, item, outcome):
    if not store.retain_ingested_input(session, org, item, outcome):
        raise IngestRefused("input_unavailable")


def ingest_bound(factory, org, item):
    store = ScreeningStore(factory)
    return CandidateStore(factory).ingest(extraction(email="bound@example.com"), item.raw_text, org_id=org,
        expected_resume_id=item.expected_resume_id,
        before_commit=lambda s, o: bind(store, s, org, item, o))


def test_ingest_and_input_binding_rollback_together(database):
    engine, factory = database
    org, _, item = prepare(factory)
    writer = make_session_factory(engine)

    def interrupt(*_):
        raise Interrupted()

    event.listen(writer, "before_commit", interrupt, once=True)
    with pytest.raises(Interrupted):
        ingest_bound(writer, org, item)
    with factory() as session:
        assert list(session.scalars(select(ScreeningInputRow))) == []
        assert list(session.scalars(select(ResumeRow))) == []
        assert session.get(BatchItemRow, item.id).raw_text == item.raw_text
    saved = ingest_bound(factory, org, item)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id).resume_id == saved.resume_id
        assert session.get(BatchItemRow, item.id).raw_text == ""


@pytest.mark.parametrize("replacement", ["new_lease", "deleted_batch"])
def test_abandoned_ingest_cannot_bind_input_or_commit(database, replacement):
    engine, factory = database
    org, batch, item = prepare(factory)
    ready, release = Event(), Event()
    writer = make_session_factory(engine)

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer, "before_flush", pause, once=True)

    with ThreadPoolExecutor(max_workers=1) as executor:
        writing = executor.submit(CandidateStore(writer).ingest, extraction(), item.raw_text,
            org_id=org, before_commit=lambda s, o: bind(ScreeningStore(writer), s, org, item, o))
        try:
            assert ready.wait(20)
            other = ScreeningStore(factory)
            if replacement == "new_lease":
                other.claim(org, batch, limit=1, now=NOW + timedelta(seconds=901), timeout_seconds=900)
            else:
                assert other.delete_batch(org, batch)
        finally:
            release.set()
        with pytest.raises(IngestRefused, match="input_unavailable"):
            writing.result(timeout=20)
    with factory() as session:
        assert list(session.scalars(select(ScreeningInputRow))) == []
        assert list(session.scalars(select(ResumeRow))) == []


@pytest.mark.parametrize("parent", ["candidate", "resume"])
def test_retry_cannot_recreate_a_parent_erased_after_read(database, parent):
    engine, factory = database
    org, batch, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    store = ScreeningStore(factory)
    assert store.fail(item.id, lease=item.claimed_at, error="internal_error", at=NOW)
    assert store.requeue_failed(org, batch) == (1, 0)
    retry = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    assert retry.raw_text == item.raw_text
    writer = make_session_factory(engine)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer, "before_flush", pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        writing = executor.submit(ingest_bound, writer, org, retry)
        try:
            assert ready.wait(20)
            assert getattr(CandidateStore(factory), f"delete_{parent}")(
                saved.candidate_id if parent == "candidate" else saved.resume_id)
        finally:
            release.set()
        with pytest.raises(CandidateErasedError if parent == "candidate" else ResumeErasedError):
            writing.result(timeout=20)
    with factory() as session:
        assert list(session.scalars(select(ResumeRow))) == []
        assert list(session.scalars(select(ScreeningInputRow))) == []
        assert session.get(BatchItemRow, item.id).raw_text == ""


@pytest.mark.parametrize("parent", ["candidate", "resume"])
@pytest.mark.parametrize("retrying", [False, True])
def test_postgres_erasure_waits_for_bound_ingest_commit(database, parent, retrying):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    org, batch, item = prepare(factory)
    saved = CandidateStore(factory).ingest(extraction(email="bound@example.com"), item.raw_text, org_id=org)
    if retrying:
        ingest_bound(factory, org, item)
        item = ScreeningStore(factory).claim(org, batch, limit=1,
            now=NOW + timedelta(seconds=901), timeout_seconds=900)[0]
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
        writing = executor.submit(ingest_bound, writer, org, item)
        try:
            assert ready.wait(20)
            erasing = executor.submit(getattr(CandidateStore(deleter), f"delete_{parent}"),
                saved.candidate_id if parent == "candidate" else saved.resume_id)
            assert deleting.wait(20)
            deadline = monotonic() + 10
            with engine.connect() as observer:
                while monotonic() < deadline:
                    if pids["writer"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                        {"pid": pids["deleter"]}):
                        break
                else:
                    pytest.fail("erasure did not wait for the bound ingest commit")
            assert not erasing.done()
        finally:
            release.set()
        assert writing.result(timeout=20).resume_id == saved.resume_id
        assert erasing.result(timeout=20)
    with factory() as session:
        assert list(session.scalars(select(ScreeningInputRow))) == []
        assert session.get(BatchItemRow, item.id).raw_text == ""


@pytest.mark.parametrize("retained", [False, True])
def test_swept_claim_cannot_restore_retry_input(database, retained):
    _, factory = database
    org, batch, item = prepare(factory)
    if retained:
        ingest_bound(factory, org, item)
        item = ScreeningStore(factory).claim(org, batch, limit=1,
            now=NOW + timedelta(seconds=901), timeout_seconds=900)[0]
    with factory() as session:
        session.execute(delete(ScreeningInputRow))
        session.execute(update(BatchItemRow).values(raw_text=""))
        session.commit()
    with pytest.raises(IngestRefused, match="input_unavailable"):
        ingest_bound(factory, org, item)
    with factory() as session:
        assert list(session.scalars(select(ScreeningInputRow))) == []
        assert session.get(BatchItemRow, item.id).raw_text == ""
        if not retained:
            assert list(session.scalars(select(ResumeRow))) == []


def test_retention_sweep_removes_retry_reference_without_removing_resume(services):
    factory = services.candidates._session_factory
    org, batch, item = prepare(factory)
    old = NOW - timedelta(days=2)
    with factory() as session:
        session.execute(update(BatchItemRow).where(BatchItemRow.id == item.id).values(created_at=old))
        session.commit()
    saved = ingest_bound(factory, org, item)
    store = ScreeningStore(factory)
    store.fail(item.id, lease=item.claimed_at, error="internal_error", at=NOW)
    settings = services.settings.model_copy(update={"ret_batch_item_days": 1, "ret_resume_days": 1000})
    preview = run_sweep(factory, settings, now=NOW, dry_run=True)
    assert next(c.affected for c in preview.by_class if c.data_class == "batch_item_text") == 1
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is not None
    applied = run_sweep(factory, settings, now=NOW, dry_run=False)
    assert next(c.affected for c in applied.by_class if c.data_class == "batch_item_text") == 1
    assert store.requeue_failed(org, batch) == (0, 1)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
        assert session.get(ResumeRow, saved.resume_id).raw_text == item.raw_text
        assert session.get(BatchItemRow, item.id).status == "failed"
    again = run_sweep(factory, settings, now=NOW, dry_run=False)
    assert next(c.affected for c in again.by_class if c.data_class == "batch_item_text") == 0


def test_populated_migration_preserves_live_input_and_cannot_restore_erased_input(database):
    import runpy
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    engine, factory = database
    org, batch, item = prepare(factory)
    kept = ingest_bound(factory, org, item)
    store = ScreeningStore(factory)
    store.add_items(org, batch, texts=["erased input"])
    erased_item = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    erased = CandidateStore(factory).ingest(extraction(email="erased@example.com"),
        erased_item.raw_text, org_id=org,
        before_commit=lambda s, o: bind(store, s, org, erased_item, o))
    assert CandidateStore(factory).delete_candidate(erased.candidate_id)
    store.add_items(org, batch, texts=["legacy unlinked input"])
    migration = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                  "alembic/versions/0024_screening_retry_input.py"))
    report_migration = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                  "alembic/versions/0025_screening_input_report.py"))
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            report_migration["downgrade"]()
            migration["downgrade"]()
        rows = connection.execute(text("SELECT id, raw_text, text_sha256 FROM batch_items")).all()
        values = {row.id: (row.raw_text, row.text_sha256) for row in rows}
        assert values[item.id][0] == item.raw_text and values[item.id][1]
        assert values[erased_item.id] == ("", "")
        assert any(row.raw_text == "legacy unlinked input" for row in rows)
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
            report_migration["upgrade"]()
    with factory() as session:
        assert session.get(ResumeRow, kept.resume_id).raw_text == item.raw_text
        assert list(session.scalars(select(ScreeningInputRow))) == []  # No guessed backfill.
        assert session.get(BatchItemRow, erased_item.id).raw_text == ""


def test_retry_cannot_use_another_tenants_resume(database):
    _, factory = database
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    other = LedgerStore(factory).create_organization("Other").id
    with pytest.raises(ResumeErasedError):
        CandidateStore(factory).ingest(extraction(), item.raw_text,
            org_id=other, expected_resume_id=saved.resume_id)
    with factory() as session:
        assert list(session.scalars(select(ResumeRow.id))) == [saved.resume_id]


def test_retry_rejects_changed_input_without_rewriting_resume(database):
    _, factory = database
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    with pytest.raises(ValueError, match="retry_input_mismatch"):
        CandidateStore(factory).ingest(extraction(), "different input",
            org_id=org, expected_resume_id=saved.resume_id)
    with factory() as session:
        assert session.get(ResumeRow, saved.resume_id).raw_text == item.raw_text


@pytest.mark.parametrize("error", ["candidate_erased", "resume_erased", "report_erased"])
def test_explicit_refusal_removes_the_private_reference(database, error):
    _, factory = database
    org, batch, item = prepare(factory)
    ingest_bound(factory, org, item)
    store = ScreeningStore(factory)
    assert store.fail(item.id, lease=item.claimed_at, error=error, at=NOW)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
    assert store.requeue_failed(org, batch) == (0, 1)


def test_stale_worker_cannot_delete_new_claims_retry_reference(database):
    _, factory = database
    org, batch, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    store = ScreeningStore(factory)
    retry = store.claim(org, batch, limit=1, now=NOW + timedelta(seconds=901), timeout_seconds=900)[0]
    assert not store.fail(item.id, lease=item.claimed_at, error="candidate_erased", at=NOW)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id).resume_id == saved.resume_id
    assert ingest_bound(factory, org, retry).resume_id == saved.resume_id


@pytest.mark.asyncio
@pytest.mark.parametrize("parent", ["candidate", "resume"])
async def test_interrupted_completion_rollback_cannot_leave_erased_input(services, monkeypatch, parent):
    org, _ = _key(services)
    batch = services.screening.register(org, name="Synthetic", domain="genai",
        texts=["Synthetic engineer\nSkills: Python"], created_by_org_user_id=None)
    store = services.screening._store
    original = store.complete

    def interrupt(*_):
        raise Interrupted()

    def erase_then_complete(item_id, **kwargs):
        assert getattr(services.candidates, f"delete_{parent}")(kwargs[f"{parent}_id"])
        event.listen(store._session_factory, "after_rollback", interrupt, once=True)
        return original(item_id, **kwargs)

    monkeypatch.setattr(store, "complete", erase_then_complete)
    with pytest.raises(Interrupted):
        await services.screening.process(org, batch.id, engine=EvaluationEngine(services))
    with services.candidates._session_factory() as session:
        item = session.scalars(select(BatchItemRow)).one()
        assert item.raw_text == item.text_sha256 == ""
        assert session.get(ScreeningInputRow, item.id) is None


def test_unrelated_binding_integrity_failure_rolls_back_ingest(database):
    from sqlalchemy.exc import IntegrityError

    engine, factory = database
    org, _, item = prepare(factory)
    writer = make_session_factory(engine)

    def invalidate(session, *_):
        for row in session.new:
            if isinstance(row, ScreeningInputRow):
                row.resume_id = None

    event.listen(writer, "before_flush", invalidate)
    with pytest.raises(IntegrityError):
        ingest_bound(writer, org, item)
    with factory() as session:
        assert list(session.scalars(select(ResumeRow))) == []
        assert list(session.scalars(select(ScreeningInputRow))) == []
        assert session.get(BatchItemRow, item.id).raw_text == item.raw_text
