"""Screening completion at real database and HTTP boundaries, with fake providers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore
from app.reports.store import SqlReportStore
from app.screening.models import BatchItemRow, ScreeningInputRow
from app.screening.schema import ItemSignals
from app.screening.store import CompletionOutcome, ScreeningStore
from tests.test_candidate_store import extraction
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report
from tests.test_screening_batches_api import _client, _key, _register

NOW = datetime.now(timezone.utc)


def seed(factory, *, retain_input=False):
    org = LedgerStore(factory).create_organization("Synthetic agency").id
    saved = CandidateStore(factory).ingest(extraction(), "private resume", org_id=org)
    report = _report(candidate_id=saved.candidate_id)
    SqlReportStore(factory).save(report, org_id=org)
    store = ScreeningStore(factory)
    batch = store.create_batch(org, name="Synthetic", domain="genai",
                               created_by_org_user_id=None, texts=["private resume"])
    item = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    if retain_input:
        with factory() as session:
            assert store.retain_ingested_input(session, org, item, saved)
            session.commit()
    kwargs = dict(lease=item.claimed_at, candidate_id=saved.candidate_id,
                  resume_id=saved.resume_id, report_id=report.id,
                  risk_score=0.4, signals=ItemSignals(risk_confidence=0.6), at=NOW)
    return org, batch, item, kwargs


def erase(factory, parent, kwargs):
    if parent == "report":
        return SqlReportStore(factory).delete(kwargs["report_id"])
    return getattr(CandidateStore(factory), f"delete_{parent}")(kwargs[f"{parent}_id"])


def assert_scrubbed(factory, item_id, parent):
    with factory() as session:
        row = session.get(BatchItemRow, item_id)
        assert row.status == "failed" and row.error == f"{parent}_erased"
        assert row.raw_text == row.text_sha256 == ""
        assert row.candidate_id is row.resume_id is row.report_id is None
        assert row.signals is row.risk_score is None


@pytest.mark.parametrize("parent", ["candidate", "resume", "report"])
@pytest.mark.parametrize("order", ["erase_first", "write_first"])
def test_completion_erasure_order_and_retry(database, parent, order, log_output):
    engine, factory = database
    org, batch, item, kwargs = seed(factory)
    other = ScreeningStore(factory).create_batch(org, name="Keep", domain="genai",
                                                created_by_org_user_id=None, texts=["keep"])
    writer_factory = make_session_factory(engine)
    store = ScreeningStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "do_orm_execute" if order == "erase_first" else "after_commit",
                 pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(store.complete, item.id, **kwargs)
        try:
            assert ready.wait(20)
            assert erase(factory, parent, kwargs)
        finally:
            release.set()
        expected = CompletionOutcome.DONE if order == "write_first" else CompletionOutcome.FAILED
        assert pending.result(timeout=20) is expected
    assert store.complete(item.id, **kwargs) is CompletionOutcome.REFUSED
    if order == "erase_first":
        assert_scrubbed(factory, item.id, parent)
        assert store.requeue_failed(org, batch) == (0, 1)
        assert store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900) == []
    else:
        with factory() as session:
            row = session.get(BatchItemRow, item.id)
            assert row.status == "done" and row.raw_text == ""
            assert getattr(row, f"{parent}_id") is None
            assert row.risk_score == 0.4  # Existing anonymous scalar retention policy.
    assert store.all_items(org, other, now=NOW)[0].raw_text == "keep"
    assert CandidateStore(factory).get_candidate("b") is not None
    assert "UPDATE batch_items" not in log_output.text
    assert "private resume" not in log_output.text


@pytest.mark.parametrize("parent", ["candidate", "resume", "report"])
def test_postgres_deletion_waits_for_completion(database, parent):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    _, _, item, kwargs = seed(factory)
    writer_factory, deleter_factory = make_session_factory(engine), make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}

    def pause(session):
        pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)

    def delete_started(session, transaction, connection):
        pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()

    event.listen(writer_factory, "before_commit", pause, once=True)
    event.listen(deleter_factory, "after_begin", delete_started, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(ScreeningStore(writer_factory).complete, item.id, **kwargs)
        try:
            assert ready.wait(20)
            erasing = executor.submit(erase, deleter_factory, parent, kwargs)
            assert deleting.wait(20)
            deadline = monotonic() + 10
            with engine.connect() as observer:
                while monotonic() < deadline:
                    if pids["writer"] in observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["deleter"]}
                    ):
                        break
                else:
                    pytest.fail("deletion never waited on completion")
            assert not erasing.done()
        finally:
            release.set()
        assert writing.result(timeout=20) is CompletionOutcome.DONE
        assert erasing.result(timeout=20)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "done" and getattr(row, f"{parent}_id") is None


@pytest.mark.parametrize("replacement", ["paused_input", "deleted_batch"])
def test_erasure_cleanup_rechecks_lease_after_rollback(database, replacement):
    engine, factory = database
    org, batch, item, kwargs = seed(factory)
    assert erase(factory, "candidate", kwargs)
    writer_factory = make_session_factory(engine)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "after_rollback", pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        writing = executor.submit(ScreeningStore(writer_factory).complete, item.id, **kwargs)
        try:
            assert ready.wait(20)
            other = ScreeningStore(factory)
            if replacement == "deleted_batch":
                assert other.delete_batch(org, batch)
            else:
                later = NOW + timedelta(seconds=901)
                # Erasure now quarantines unresolved input. Claim invalidates
                # the old lease without erasing ambiguous retained text.
                assert other.claim(org, batch, limit=1, now=later, timeout_seconds=900) == []
        finally:
            release.set()
        assert writing.result(timeout=20) is CompletionOutcome.REFUSED
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        if replacement == "deleted_batch":
            assert row is None
        else:
            assert row.status == "failed" and row.error == "fresh_upload_required"
            assert row.raw_text == item.raw_text and row.claimed_at is None


@pytest.mark.parametrize("winner", ["processing", "done", "failed"])
def test_erasure_cleanup_acknowledges_nothing_after_private_input_reclaimed(database, winner):
    engine, factory = database
    org, batch, item, kwargs = seed(factory, retain_input=True)
    assert erase(factory, "report", kwargs)
    writer_factory = make_session_factory(engine)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "after_rollback", pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        writing = executor.submit(ScreeningStore(writer_factory).complete, item.id, **kwargs)
        try:
            assert ready.wait(20)
            store = ScreeningStore(factory)
            later = NOW + timedelta(seconds=901)
            claimed = store.claim(org, batch, limit=1, now=later, timeout_seconds=900)
            assert len(claimed) == 1 and claimed[0].expected_resume_id == kwargs["resume_id"]
            if winner == "done":
                assert store.complete(item.id, **{**kwargs, "lease": claimed[0].claimed_at,
                    "report_id": None, "risk_score": 0.9, "at": later}) is CompletionOutcome.DONE
            elif winner == "failed":
                assert store.fail(item.id, lease=claimed[0].claimed_at, error="internal_error", at=later)
        finally:
            release.set()
        assert writing.result(timeout=20) is CompletionOutcome.REFUSED
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == winner and as_utc(row.claimed_at) == claimed[0].claimed_at
        assert row.error == ("internal_error" if winner == "failed" else None)
        assert row.risk_score == (0.9 if winner == "done" else None)
        retained = session.get(ScreeningInputRow, item.id)
        assert row.raw_text == ""
        if winner == "done":
            assert retained is None
        else:
            assert retained is not None and retained.resume_id == kwargs["resume_id"]
    if winner == "failed":
        assert store.requeue_failed(org, batch) == (1, 0)


@pytest.mark.parametrize("erased", [False, True], ids=["success-commit", "cleanup-commit"])
def test_completion_does_not_acknowledge_a_rolled_back_commit(database, erased):
    engine, factory = database
    _, _, item, kwargs = seed(factory)
    if erased:
        assert erase(factory, "candidate", kwargs)
    writer_factory = make_session_factory(engine)

    def refuse_commit(*_):
        raise RuntimeError("synthetic commit refusal")

    event.listen(writer_factory, "before_commit", refuse_commit, once=True)
    with pytest.raises(RuntimeError, match="synthetic commit refusal"):
        ScreeningStore(writer_factory).complete(item.id, **kwargs)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "processing" and row.processed_at is None
        assert row.raw_text == "private resume" and row.error is None


@pytest.mark.parametrize("erased", [False, True])
def test_unrelated_completion_constraint_error_propagates(database, erased):
    engine, factory = database
    _, _, item, kwargs = seed(factory)
    if erased:
        assert erase(factory, "candidate", kwargs)
    writer_factory = make_session_factory(engine)

    def invalidate(state):
        state.statement = state.statement.values(status=None)

    event.listen(writer_factory, "do_orm_execute", invalidate, once=True)
    with pytest.raises(IntegrityError):
        ScreeningStore(writer_factory).complete(item.id, **kwargs)
    with factory() as session:
        assert session.get(BatchItemRow, item.id).raw_text == "private resume"


@pytest.mark.parametrize("parent", ["candidate", "resume", "report"])
def test_process_reports_erasure_without_retaining_input(services, monkeypatch, genuine_resume, parent):
    org, key = _key(services)
    _, other_key = _key(services, "Other")
    store = services.screening._store
    complete = store.complete

    def erase_then_complete(item_id, **kwargs):
        assert erase(services.candidates._session_factory, parent, kwargs)
        return complete(item_id, **kwargs)

    monkeypatch.setattr(store, "complete", erase_then_complete)
    with _client(services) as http:
        batch = _register(http, key, [genuine_resume]).json()["id"]
        path = f"/screening/batches/{batch}"
        headers = {"X-Org-Key": key}
        ran = http.post(path + "/process", headers=headers)
        assert ran.status_code == 200
        assert (ran.json()["processed"], ran.json()["failed"], ran.json()["remaining"]) == (0, 1, 0)
        row = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert row["error"] == f"{parent}_erased" and row["signals"] is None
        assert row["advisory"] and row["human_review_required"]
        assert_scrubbed(services.candidates._session_factory, row["item_id"], parent)
        retry = http.post(path + "/retry", headers=headers).json()
        assert (retry["requeued"], retry["skipped"]) == (0, 1)
        assert http.post(path + "/process", headers=headers).json()["processed"] == 0
        assert http.get(path + "/queue", headers={"X-Org-Key": other_key}).status_code == 404


def test_process_does_not_count_lost_completion_as_success(services, monkeypatch, genuine_resume):
    org, key = _key(services)
    store = services.screening._store
    complete = store.complete
    batch_id = []
    stolen = []

    def steal_then_complete(item_id, **kwargs):
        later = kwargs["lease"] + timedelta(seconds=services.settings.screening_claim_timeout_seconds + 1)
        stolen.extend(store.claim(org, batch_id[0], limit=1, now=later,
                                  timeout_seconds=services.settings.screening_claim_timeout_seconds))
        assert len(stolen) == 1 and stolen[0].id == item_id
        return complete(item_id, **kwargs)

    monkeypatch.setattr(store, "complete", steal_then_complete)
    with _client(services) as http:
        batch = _register(http, key, [genuine_resume]).json()["id"]
        batch_id.append(batch)
        result = http.post(f"/screening/batches/{batch}/process", headers={"X-Org-Key": key}).json()
        assert (result["processed"], result["failed"], result["remaining"]) == (0, 0, 1)
        row = http.get(f"/screening/batches/{batch}/queue", headers={"X-Org-Key": key}).json()["rows"][0]
        assert row["status"] == "processing" and row["error"] is None


def test_erasure_during_report_save_still_refuses_completion(services, monkeypatch, genuine_resume):
    _, key = _key(services)
    save = services.report_store.save

    def erase_then_save(report, **kwargs):
        assert services.candidates.delete_candidate(report.candidate_id)
        return save(report, **kwargs)

    monkeypatch.setattr(services.report_store, "save", erase_then_save)
    with _client(services) as http:
        batch = _register(http, key, [genuine_resume]).json()["id"]
        headers = {"X-Org-Key": key}
        path = f"/screening/batches/{batch}"
        result = http.post(path + "/process", headers=headers)
        assert result.status_code == 200
        assert (result.json()["processed"], result.json()["failed"]) == (0, 1)
        row = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert_scrubbed(services.candidates._session_factory, row["item_id"], "candidate")
