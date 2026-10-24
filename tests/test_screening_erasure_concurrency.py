"""Screening completion at real database and HTTP boundaries, with fake providers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import IntegrityError

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore
from app.reports.models import ReportRow
from app.reports.store import SqlReportStore
from app.screening.ingest import IngestRefused
from app.screening.models import BatchItemRow, ScreeningInputRow
from app.screening.schema import ItemSignals
from app.screening.store import CompletionOutcome, ScreeningStore
from tests.test_candidate_store import extraction
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report
from tests.test_screening_batches_api import _client, _key, _register

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def terminal_clock(monkeypatch):
    clock = [NOW]
    monkeypatch.setattr("app.screening.store._utcnow", lambda: clock[0], raising=False)
    return clock


def persistence_case(factory, operation):
    org = LedgerStore(factory).create_organization("Synthetic persistence").id
    store = ScreeningStore(factory)
    batch = store.create_batch(org, name="Synthetic", domain="genai",
        created_by_org_user_id=None, texts=["private resume"])
    item = store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0]
    if operation != "input":
        persist_input_or_report(factory, org, item, "input")
        if operation == "report":
            persist_input_or_report(factory, org, item, "report")
        if operation == "retry":
            item = store.claim(org, batch, limit=1, now=NOW + timedelta(seconds=901),
                               timeout_seconds=900)[0]
    return org, item


def persist_input_or_report(factory, org, item, operation):
    store = ScreeningStore(factory)
    def bind(session, value):
        admitted = (store.bind_input_report(session, org, item, value) if operation == "report"
                    else store.retain_ingested_input(session, org, item, value))
        if not admitted:
            raise IngestRefused("input_unavailable")
    if operation == "report":
        with factory() as session:
            cid = session.scalar(select(ResumeRow.candidate_id).join(
                ScreeningInputRow, ScreeningInputRow.resume_id == ResumeRow.id).where(
                    ScreeningInputRow.id == item.id))
        SqlReportStore(factory).save(_report(candidate_id=cid), org_id=org, before_commit=bind)
    else:
        CandidateStore(factory).ingest(extraction(email="persistence@example.com"), item.raw_text,
            org_id=org, expected_resume_id=item.expected_resume_id, before_commit=bind)


def persistence_snapshot(factory):
    with factory() as session:
        return {model.__tablename__: session.execute(select(model.__table__).order_by(model.id)).all()
                for model in (CandidateRow, ResumeRow, ExtractionRow, ReportRow,
                              BatchItemRow, ScreeningInputRow)}


@pytest.mark.parametrize("operation", ["input", "retry", "report"])
@pytest.mark.parametrize("age", [899, 900, 900.000001])
def test_persistence_requires_unexpired_lease(database, terminal_clock, operation, age):
    _, factory = database
    org, item = persistence_case(factory, operation)
    before = persistence_snapshot(factory)
    terminal_clock[0] = item.claimed_at + timedelta(seconds=age)
    if age > 900:
        with pytest.raises(IngestRefused, match="input_unavailable"):
            persist_input_or_report(factory, org, item, operation)
        assert persistence_snapshot(factory) == before
    else:
        persist_input_or_report(factory, org, item, operation)
        with factory() as session:
            ref = session.get(ScreeningInputRow, item.id)
            assert ref.created_at == session.get(BatchItemRow, item.id).created_at
            assert (ref.report_id is not None) == (operation == "report")
            assert session.get(BatchItemRow, item.id).raw_text == ""


@pytest.mark.parametrize("operation", ["input", "retry", "report"])
def test_persistence_expiry_after_private_write_rolls_back(database, terminal_clock, operation):
    engine, factory = database
    org, item = persistence_case(factory, operation)
    before = persistence_snapshot(factory)
    terminal_clock[0] = item.claimed_at
    writer = make_session_factory(engine)
    advanced = []
    def advance():
        advanced.append(True)
        terminal_clock[0] = item.claimed_at + timedelta(seconds=901)
    def after_flush(session, _):
        if any(isinstance(row, ScreeningInputRow) for row in session.new):
            advance()
    def after_execute(state):
        result = state.invoke_statement()
        if state.bind_mapper is not None and state.bind_mapper.class_ is ScreeningInputRow:
            if (operation == "retry" and state.is_select) or (operation == "report" and state.is_update):
                advance()
        return result
    event.listen(writer, "after_flush", after_flush)
    event.listen(writer, "do_orm_execute", after_execute, retval=True)
    with pytest.raises(IngestRefused, match="input_unavailable"):
        persist_input_or_report(writer, org, item, operation)
    assert advanced, "test must expire after the private-input operation"
    assert persistence_snapshot(factory) == before


@pytest.mark.parametrize("operation", ["input", "retry", "report"])
def test_persistence_waiting_for_lock_uses_fresh_clock(database, terminal_clock, operation):
    engine, factory = database
    org, item = persistence_case(factory, operation)
    before = persistence_snapshot(factory)
    terminal_clock[0] = item.claimed_at
    writer = make_session_factory(engine)
    ready, pids = Event(), {}
    def started(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids["writer"] = connection.scalar(text("SELECT pg_backend_pid()"))
        ready.set()
    event.listen(writer, "after_begin", started)
    with factory() as blocker, ThreadPoolExecutor(max_workers=1) as executor:
        blocker.execute(update(BatchItemRow).where(BatchItemRow.id == item.id)
                        .values(claimed_at=BatchItemRow.claimed_at))
        if engine.dialect.name == "postgresql":
            pids["blocker"] = blocker.scalar(text("SELECT pg_backend_pid()"))
        pending = executor.submit(persist_input_or_report, writer, org, item, operation)
        try:
            assert ready.wait(20)
            if engine.dialect.name == "postgresql":
                deadline = monotonic() + 10
                with engine.connect() as observer:
                    while monotonic() < deadline:
                        if pids["blocker"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                              {"pid": pids["writer"]}):
                            break
                    else:
                        pytest.fail("persistence did not wait for the competing connection")
            assert not pending.done()
            terminal_clock[0] = item.claimed_at + timedelta(seconds=901)
        finally:
            blocker.rollback()
        with pytest.raises(IngestRefused, match="input_unavailable"):
            pending.result(timeout=20)
    assert persistence_snapshot(factory) == before


@pytest.mark.parametrize("operation", ["done", "fail"])
@pytest.mark.parametrize("age", [899, 900, 900.000001])
def test_terminal_transition_requires_unexpired_lease(database, terminal_clock, operation, age):
    _, factory = database
    org, batch, item, kwargs = seed(factory, retain_input=True)
    terminal_clock[0] = NOW + timedelta(seconds=age)
    store = ScreeningStore(factory)
    if operation == "done":
        result = store.complete(item.id, **kwargs)
        assert result is (CompletionOutcome.DONE if age <= 900 else CompletionOutcome.REFUSED)
    else:
        result = store.fail(item.id, lease=item.claimed_at, error="internal_error", at=NOW)
        assert result is (age <= 900)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        if age > 900:
            assert row.status == "processing" and row.processed_at is None
            assert row.candidate_id is row.report_id is row.error is None
            assert session.get(ScreeningInputRow, item.id).resume_id == kwargs["resume_id"]
        else:
            assert row.status == ("done" if operation == "done" else "failed")
    if age > 900:
        assert store.counts(org, batch, now=terminal_clock[0]).pending == 1


@pytest.mark.parametrize("operation", ["done", "fail"])
def test_terminal_expiry_after_write_rolls_back_input_and_status(database, terminal_clock, operation):
    engine, factory = database
    _, _, item, kwargs = seed(factory, retain_input=True)
    writer = make_session_factory(engine)

    def advance(state):
        result = state.invoke_statement()
        if state.is_delete:
            terminal_clock[0] += timedelta(seconds=901)
        return result

    event.listen(writer, "do_orm_execute", advance, retval=True)
    store = ScreeningStore(writer)
    if operation == "done":
        assert store.complete(item.id, **kwargs) is CompletionOutcome.REFUSED
    else:
        assert not store.fail(item.id, lease=item.claimed_at, error="resume_erased", at=NOW)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "processing" and row.processed_at is None and row.error is None
        assert session.get(ScreeningInputRow, item.id).resume_id == kwargs["resume_id"]


@pytest.mark.parametrize("phase", ["rollback", "cleanup_write"])
def test_erasure_cleanup_rechecks_expiry_after_rollback(database, terminal_clock, phase):
    engine, factory = database
    _, _, item, kwargs = seed(factory)
    assert erase(factory, "candidate", kwargs)
    writer = make_session_factory(engine)
    if phase == "rollback":
        event.listen(writer, "after_rollback", lambda *_: terminal_clock.__setitem__(0,
            NOW + timedelta(seconds=901)), once=True)
    else:
        def advance(state):
            result = state.invoke_statement()
            if state.is_delete:
                terminal_clock[0] = NOW + timedelta(seconds=901)
            return result
        event.listen(writer, "do_orm_execute", advance, retval=True)
    assert ScreeningStore(writer).complete(item.id, **kwargs) is CompletionOutcome.REFUSED
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "processing" and row.raw_text == "private resume" and row.error is None


@pytest.mark.parametrize("operation", ["done", "fail"])
def test_terminal_waiting_for_lock_uses_fresh_clock(database, terminal_clock, operation):
    engine, factory = database
    _, _, item, kwargs = seed(factory, retain_input=True)
    writer = make_session_factory(engine)
    ready = Event()
    pids = {}

    def started(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids["writer"] = connection.scalar(text("SELECT pg_backend_pid()"))
        ready.set()

    event.listen(writer, "after_begin", started, once=True)
    with factory() as blocker, ThreadPoolExecutor(max_workers=1) as executor:
        blocker.execute(update(BatchItemRow).where(BatchItemRow.id == item.id)
                        .values(claimed_at=BatchItemRow.claimed_at))
        if engine.dialect.name == "postgresql":
            pids["blocker"] = blocker.scalar(text("SELECT pg_backend_pid()"))
        store = ScreeningStore(writer)
        pending = executor.submit(store.complete, item.id, **kwargs) if operation == "done" else executor.submit(
            store.fail, item.id, lease=item.claimed_at, error="internal_error", at=NOW)
        try:
            assert ready.wait(20)
            if engine.dialect.name == "postgresql":
                deadline = monotonic() + 10
                with engine.connect() as observer:
                    while monotonic() < deadline:
                        if pids["blocker"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                              {"pid": pids["writer"]}):
                            break
                    else:
                        pytest.fail("terminal write did not wait for the competing connection")
            assert not pending.done()
            terminal_clock[0] = NOW + timedelta(seconds=901)
        finally:
            blocker.rollback()
        assert pending.result(timeout=20) is (CompletionOutcome.REFUSED if operation == "done" else False)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "processing" and row.processed_at is None
        assert session.get(ScreeningInputRow, item.id).resume_id == kwargs["resume_id"]


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
        if state.is_update:
            state.statement = state.statement.values(status=None)

    event.listen(writer_factory, "do_orm_execute", invalidate)
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
