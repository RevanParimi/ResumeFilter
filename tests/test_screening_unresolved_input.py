"""Unknown screening input must not resurrect subjects after erasure."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import delete, event, select, text as sql_text, update
from app.candidates.models import CandidateRow, ResumeRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.reports.models import ReportRow
from app.reports.store import SqlReportStore
from app.screening.ingest import IngestRefused
from app.screening.models import BatchItemRow, ScreeningInputRow, ScreeningErasureStateRow
from app.screening.store import ScreeningStore
from tests.test_candidate_store import extraction
from tests.test_report_erasure_concurrency import database
from tests.test_screening_batches_api import _client, _key, _register
from tests.test_screening_durable_input import Interrupted, NOW, prepare
from tests.test_report_store import _report


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["before_extraction", "resolved_failure", "resolved_interruption"])
async def test_no_automatic_recreation_from_unlinked_input(services, monkeypatch, stage):
    import app.candidates.extractor as extractor
    org, _ = _key(services)
    text = "Synthetic Person\nEmail: unresolved@example.com\nSkills: Python"
    profile = await extractor.extract_profile(text, llm=services.llm, settings=services.settings)
    saved = services.candidates.ingest(profile, text, org_id=org)
    batch = services.screening.register(org, name="Synthetic", domain="genai", texts=[text], created_by_org_user_id=None)
    class Engine:
        async def evaluate(self, **kwargs):
            return _report()
    resolver = services.candidates._resolve_candidate
    def fail(session, profile):
        row, matched = resolver(session, profile)
        assert row.id == saved.candidate_id
        if stage == "resolved_interruption":
            raise Interrupted()
        raise RuntimeError("synthetic first ingest failure")
    if stage != "before_extraction":
        with monkeypatch.context() as patch:
            patch.setattr(services.candidates, "_resolve_candidate", fail)
            if stage == "resolved_interruption":
                with pytest.raises(Interrupted):
                    await services.screening.process(org, batch.id, engine=Engine())
            else:
                result = await services.screening.process(org, batch.id, engine=Engine())
                assert (result.processed, result.failed) == (0, 1)
    assert services.portal.erase(saved.candidate_id)["deleted"]
    with services.candidates._session_factory() as session:
        row = session.scalars(select(BatchItemRow)).one()
        assert row.raw_text == text
        assert session.get(ScreeningInputRow, row.id) is None
        if stage == "resolved_interruption":
            row.claimed_at -= timedelta(days=1)
            session.commit()
    if stage == "resolved_failure":
        assert services.screening.retry(org, batch.id).requeued == 0
    row = services.screening.queue(org, batch.id, cursor=None, limit=10).rows[0]
    assert row.status.value == "failed" and row.error == "fresh_upload_required"
    assert "upload" in row.reason.lower()
    result = await services.screening.process(org, batch.id, engine=Engine())
    with services.candidates._session_factory() as session:
        recreated = list(session.scalars(select(CandidateRow.id)))
    assert not recreated, "automatic recovery recreated an erased candidate from unlinked input"


def guarded_ingest(factory, org, item):
    store = ScreeningStore(factory)
    def guard(session):
        if not store.check_input_generation(session, item):
            raise IngestRefused("fresh_upload_required")
    def bind(session, outcome):
        if not store.retain_ingested_input(session, org, item, outcome):
            raise IngestRefused("input_unavailable")
    return CandidateStore(factory).ingest(extraction(email="bound@example.com"), item.raw_text,
        org_id=org, before_write=guard, before_commit=bind)


@pytest.mark.asyncio
async def test_erasure_while_extraction_runs_refuses_stale_memory(services, monkeypatch):
    import app.candidates.extractor as extractor
    org, _ = _key(services)
    text = "Synthetic person\nEmail: inflight@example.com"
    original = extractor.extract_profile
    profile = await original(text, llm=services.llm, settings=services.settings)
    saved = services.candidates.ingest(profile, text, org_id=org)
    batch = services.screening.register(org, name="In flight", domain="genai", texts=[text],
                                         created_by_org_user_id=None)
    async def erase(*args, **kwargs):
        result = await original(*args, **kwargs)
        assert services.portal.erase(saved.candidate_id)["deleted"]
        return result
    monkeypatch.setattr(extractor, "extract_profile", erase)
    ran = await services.screening.process(org, batch.id, engine=None)
    assert (ran.processed, ran.failed) == (0, 1)
    assert services.screening.queue(org, batch.id, cursor=None, limit=10).rows[0].error == "fresh_upload_required"
    with services.candidates._session_factory() as session:
        assert list(session.scalars(select(CandidateRow))) == []


@pytest.mark.parametrize("parent", ["candidate", "resume", "report"])
@pytest.mark.parametrize("rollback", [False, True])
def test_bulk_erasure_and_rollback_order_unresolved_input(database, parent, rollback):
    _, factory = database
    org, batch, item = prepare(factory)
    saved = CandidateStore(factory).ingest(extraction(), "subject text", org_id=org)
    report = _report(candidate_id=saved.candidate_id)
    SqlReportStore(factory).save(report, org_id=org)
    model, identity = {"candidate": (CandidateRow, saved.candidate_id),
                       "resume": (ResumeRow, saved.resume_id), "report": (ReportRow, report.id)}[parent]
    with factory() as session:
        initial = session.get(ScreeningErasureStateRow, 1).generation
        session.execute(delete(model).where(model.id == identity))
        if rollback:
            session.rollback()
        else:
            session.commit()
    with factory() as session:
        generation = session.get(ScreeningErasureStateRow, 1).generation
        row = session.get(BatchItemRow, item.id)
        assert row.raw_text == item.raw_text and row.text_sha256
        assert (generation == initial) is rollback
    store = ScreeningStore(factory)
    if rollback:
        assert guarded_ingest(factory, org, item).resume_id
    else:
        assert store.counts(org, batch, now=NOW).failed == 1
        assert store.requeue_failed(org, batch) == (0, 1)
        with pytest.raises(IngestRefused, match="fresh_upload_required"):
            guarded_ingest(factory, org, item)


def test_empty_delete_does_not_pause_input(database):
    _, factory = database
    org, _, item = prepare(factory)
    with factory() as session:
        session.execute(delete(CandidateRow).where(CandidateRow.id == "missing"))
        session.commit()
    assert guarded_ingest(factory, org, item).resume_id


def test_postgres_erase_waits_before_subject_write(database):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    org, _, item = prepare(factory)
    saved = CandidateStore(factory).ingest(extraction(email="bound@example.com"), "older", org_id=org)
    writer, deleter = make_session_factory(engine), make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}
    def pause(session, *_):
        pids["writer"] = session.connection().scalar(sql_text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)
    def started(session, transaction, connection):
        pids["deleter"] = connection.scalar(sql_text("SELECT pg_backend_pid()"))
        deleting.set()
    event.listen(writer, "before_flush", pause, once=True)
    event.listen(deleter, "after_begin", started, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(guarded_ingest, writer, org, item)
        try:
            assert ready.wait(20)
            erasing = executor.submit(CandidateStore(deleter).delete_candidate, saved.candidate_id)
            assert deleting.wait(20)
            with engine.connect() as observer:
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    if pids["writer"] in observer.scalar(sql_text("SELECT pg_blocking_pids(:pid)"),
                                                         {"pid": pids["deleter"]}):
                        break
                else:
                    pytest.fail("erasure did not wait for pre-write generation lock")
            assert not erasing.done()
        finally:
            release.set()
        assert writing.result(timeout=20).candidate_id == saved.candidate_id
        assert erasing.result(timeout=20)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None


def test_api_pauses_unrelated_unlinked_input_but_allows_fresh_upload(services):
    org, key = _key(services)
    other_org, other_key = _key(services, "Other")
    saved = services.candidates.ingest(extraction(), "subject", org_id=org)
    with _client(services) as http:
        batches = [(key, _register(http, key, ["Synthetic engineer"]).json()["id"]),
                   (other_key, _register(http, other_key, ["Other engineer"]).json()["id"])]
        assert services.portal.erase(saved.candidate_id)["deleted"]
        for api_key, batch in batches:
            headers = {"X-Org-Key": api_key}
            path = f"/screening/batches/{batch}"
            detail = http.get(path, headers=headers).json()
            assert detail["counts"]["failed"] == 1 and detail["counts"]["pending"] == 0
            queue = http.get(path + "/queue", headers=headers).json()["rows"][0]
            assert queue["error"] == "fresh_upload_required" and "Upload" in queue["reason"]
            assert queue["advisory"] and queue["human_review_required"]
            assert http.post(path + "/retry", headers=headers).json()["skipped"] == 1
            assert http.post(path + "/process", headers=headers).json()["processed"] == 0
        assert http.get(f"/screening/batches/{batches[0][1]}", headers={"X-Org-Key": other_key}).status_code == 404
        fresh = _register(http, key, ["Synthetic engineer"]).json()["id"]
        ran = http.post(f"/screening/batches/{fresh}/process", headers={"X-Org-Key": key})
        assert ran.status_code == 200 and ran.json()["processed"] == 1


def test_populated_guard_migration_preserves_and_quarantines_legacy_input(database):
    import runpy
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    engine, factory = database
    org, batch, item = prepare(factory)
    saved = guarded_ingest(factory, org, item)
    store = ScreeningStore(factory)
    store.add_items(org, batch, texts=["historical raw input"])
    migration = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                  "alembic/versions/0026_screening_erasure_guard.py"))
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration["downgrade"]()
            assert conn.scalar(sql_text("SELECT count(*) FROM screening_item_inputs")) == 1
            migration["upgrade"]()
    with factory() as session:
        rows = list(session.scalars(select(BatchItemRow)))
        assert all(r.status == "failed" and r.error == "fresh_upload_required" for r in rows)
        assert session.get(ScreeningInputRow, item.id).resume_id == saved.resume_id
        assert any(r.raw_text == "historical raw input" for r in rows)
    assert store.requeue_failed(org, batch) == (0, 2)
    with pytest.raises(RuntimeError, match="requires_review_before_downgrade"):
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration["downgrade"]()
    # Failed downgrade changed neither schema nor quarantined data.
    assert store.requeue_failed(org, batch) == (0, 2)


def test_quarantined_text_expires_on_original_retention_window(services):
    from app.retention.sweep import run_sweep
    factory = services.candidates._session_factory
    org, batch, item = prepare(factory)
    with factory() as session:
        session.execute(update(BatchItemRow).where(BatchItemRow.id == item.id).values(
            created_at=NOW - timedelta(days=2)))
        session.add(CandidateRow(id="erased-for-retention"))
        session.commit()
    assert services.candidates.delete_candidate("erased-for-retention")
    store = ScreeningStore(factory)
    assert store.requeue_failed(org, batch) == (0, 1)
    settings = services.settings.model_copy(update={"ret_batch_item_days": 1})
    run_sweep(factory, settings, now=NOW, dry_run=True)
    with factory() as session:
        assert session.get(BatchItemRow, item.id).raw_text == item.raw_text
    run_sweep(factory, settings, now=NOW, dry_run=False)
    with factory() as session:
        assert session.get(BatchItemRow, item.id).raw_text == ""
    # With the text gone, a never-finalized processing row is no longer a
    # retained unresolved input. It still cannot be requeued with any input.
    assert store.requeue_failed(org, batch)[0] == 0


def test_unrelated_erasure_does_not_pause_bound_resume_retry(database):
    _, factory = database
    org, batch, item = prepare(factory)
    saved = guarded_ingest(factory, org, item)
    assert CandidateStore(factory).delete_candidate("b")
    store = ScreeningStore(factory)
    assert store.fail(item.id, lease=item.claimed_at, error="internal_error", at=NOW)
    assert store.requeue_failed(org, batch) == (1, 0)
    retry = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    assert retry.expected_resume_id == saved.resume_id
    # Production retry retains its precise resume capability across an unrelated
    # global generation change; it cannot resolve a replacement identity.
    from tests.test_screening_durable_input import ingest_bound
    assert ingest_bound(factory, org, retry).resume_id == saved.resume_id
