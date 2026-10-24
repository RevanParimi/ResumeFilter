"""Report-only erasure must survive interrupted batch completion cleanup."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import delete, event, select, text, update

from app.candidates.models import ResumeRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.reports.models import ReportRow
from app.reports.store import SqlReportStore
from app.screening.ingest import IngestRefused
from app.screening.models import BatchItemRow, ScreeningBatchRow, ScreeningInputRow
from app.screening.store import CompletionOutcome, ScreeningStore
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report
from tests.test_screening_batches_api import _client, _key, _register
from tests.test_screening_durable_input import Interrupted, NOW, ingest_bound, prepare


@pytest.fixture(autouse=True)
def persistence_clock(monkeypatch):
    monkeypatch.setattr("app.screening.store._utcnow", lambda: NOW)


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
    with factory() as session:
        facts = session.get(ScreeningInputRow, item.id).ingest_facts
        assert facts["version"] == 1

    def interrupt(*_):
        raise Interrupted()

    event.listen(writer, "before_commit", interrupt, once=True)
    with pytest.raises(Interrupted):
        save_bound(writer, org, item, report)
    with factory() as session:
        assert session.get(ReportRow, report.id) is None
        assert session.get(ScreeningInputRow, item.id).report_id is None
        assert session.get(ScreeningInputRow, item.id).ingest_facts == facts
    save_bound(factory, org, item, report)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id).report_id == report.id
        assert session.get(ScreeningInputRow, item.id).ingest_facts == facts


@pytest.mark.parametrize("same_id", [False, True], ids=["replacement", "same-id-mutation"])
def test_first_report_checkpoint_cannot_be_replaced_or_resaved(database, same_id):
    _, factory = database
    org, _, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    first = _report(candidate_id=saved.candidate_id)
    save_bound(factory, org, item, first)
    replacement = (first.model_copy(update={"summary": "must roll back"}) if same_id
                   else _report(candidate_id=saved.candidate_id))
    with pytest.raises(IngestRefused, match="input_unavailable"):
        save_bound(factory, org, item, replacement)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id).report_id == first.id
        assert list(session.scalars(select(ReportRow.id))) == [first.id]
        assert session.get(ReportRow, first.id).body == first.model_dump(mode="json")


def checkpoint(factory):
    org, batch, item = prepare(factory)
    saved = ingest_bound(factory, org, item)
    report = _report(candidate_id=saved.candidate_id)
    save_bound(factory, org, item, report)
    item = ScreeningStore(factory).claim(org, batch, limit=1,
        now=NOW + timedelta(seconds=901), timeout_seconds=900)[0]
    return org, batch, item, saved, report


@pytest.mark.parametrize("operation", ["first-save", "recovery"])
def test_competing_checkpoint_transactions_commit_one_result(database, operation):
    engine, factory = database
    if operation == "recovery":
        org, batch, item, _, report = checkpoint(factory)
        def perform(sessions):
            return ScreeningStore(sessions).recover_report(org, item, input_ttl_days=90,
                now=lambda: item.claimed_at)
    else:
        org, batch, item = prepare(factory)
        saved = ingest_bound(factory, org, item)
        report = _report(candidate_id=saved.candidate_id)
        def perform(sessions):
            return save_bound(sessions, org, item, report if sessions is writer
                              else _report(candidate_id=saved.candidate_id))
    writer, competitor = make_session_factory(engine), make_session_factory(engine)
    ready, release, started = Event(), Event(), Event()
    pids = {}
    def pause(session):
        if engine.dialect.name == "postgresql":
            pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)
    def begin(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids["competitor"] = connection.scalar(text("SELECT pg_backend_pid()"))
        started.set()
    event.listen(writer, "before_commit", pause, once=True)
    event.listen(competitor, "after_begin", begin, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(perform, writer)
        try:
            assert ready.wait(20)
            second = executor.submit(perform, competitor)
            assert started.wait(20)
            if engine.dialect.name == "postgresql":
                deadline = monotonic() + 10
                with engine.connect() as observer:
                    while monotonic() < deadline:
                        if pids["writer"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                             {"pid": pids["competitor"]}):
                            break
                    else:
                        pytest.fail("competing checkpoint transaction did not wait")
            assert not second.done()
        finally:
            release.set()
        if operation == "recovery":
            assert first.result(timeout=20) is CompletionOutcome.DONE
            assert second.result(timeout=20) is CompletionOutcome.REFUSED
        else:
            first.result(timeout=20)
            with pytest.raises(IngestRefused, match="input_unavailable"):
                second.result(timeout=20)
    with factory() as session:
        assert list(session.scalars(select(ReportRow.id))) == [report.id]
        row = session.get(BatchItemRow, item.id)
        ref = session.get(ScreeningInputRow, item.id)
        if operation == "recovery":
            assert row.status == "done" and row.report_id == report.id and ref is None
        else:
            assert row.status == "processing" and ref.report_id == report.id
    assert ScreeningStore(factory).counts(org, batch, now=item.claimed_at).done == int(operation == "recovery")


def test_recovery_commits_original_report_facts_and_no_new_ingest(database):
    from app.candidates.models import ExtractionRow
    _, factory = database
    org, batch, item, saved, report = checkpoint(factory)
    with factory() as session:
        before = list(session.scalars(select(ExtractionRow.id)))
        facts = session.get(ScreeningInputRow, item.id).ingest_facts
    store = ScreeningStore(factory)
    assert store.recover_report(org, item, input_ttl_days=90, now=lambda: item.claimed_at) is CompletionOutcome.DONE
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert (row.status, row.candidate_id, row.resume_id, row.report_id) == (
            "done", saved.candidate_id, saved.resume_id, report.id)
        assert all(row.signals[name] == facts[name] for name in (
            "matched_existing", "matched_on", "duplicate_resume"))
        assert list(session.scalars(select(ReportRow.id))) == [report.id]
        assert list(session.scalars(select(ExtractionRow.id))) == before
        assert session.get(ScreeningInputRow, item.id) is None
    assert store.counts(org, batch, now=item.claimed_at).done == 1
    assert store.recover_report(org, item, input_ttl_days=90, now=lambda: item.claimed_at) is CompletionOutcome.REFUSED


@pytest.mark.parametrize("age", [899, 900, 900.000001])
def test_recovery_requires_live_lease_and_retains_checkpoint_on_refusal(database, age):
    _, factory = database
    org, batch, item, _, report = checkpoint(factory)
    outcome = ScreeningStore(factory).recover_report(org, item, input_ttl_days=90,
        now=lambda: item.claimed_at + timedelta(seconds=age))
    assert outcome is (CompletionOutcome.DONE if age <= 900 else CompletionOutcome.REFUSED)
    with factory() as session:
        assert session.get(ReportRow, report.id) is not None
        if age > 900:
            assert session.get(BatchItemRow, item.id).status == "processing"
            assert session.get(ScreeningInputRow, item.id).report_id == report.id


@pytest.mark.parametrize("extra", [0, 0.000001])
def test_recovery_private_ttl_uses_original_timestamp_and_equality(database, extra):
    _, factory = database
    org, _, item, _, report = checkpoint(factory)
    with factory() as session:
        session.get(ScreeningInputRow, item.id).created_at = item.claimed_at - timedelta(days=90, seconds=extra)
        session.commit()
    store = ScreeningStore(factory)
    if extra:
        with pytest.raises(IngestRefused, match="fresh_upload_required"):
            store.recover_report(org, item, input_ttl_days=90, now=lambda: item.claimed_at)
        with factory() as session:
            assert session.get(ScreeningInputRow, item.id).report_id == report.id
            assert session.get(BatchItemRow, item.id).status == "processing"
    else:
        assert store.recover_report(org, item, input_ttl_days=90, now=lambda: item.claimed_at) is CompletionOutcome.DONE


@pytest.mark.parametrize("change", ["unknown", "empty", "future", "bool-version", "string-flag", "missing", "extra",
    "report-owner", "resume-owner", "candidate", "domain", "body-id", "body-subject", "body-domain", "non-advisory"])
def test_recovery_invalid_checkpoint_refuses_without_new_report_or_state(database, change):
    _, factory = database
    org, _, item, saved, report = checkpoint(factory)
    other = LedgerStore(factory).create_organization("Other checkpoint owner").id
    with factory() as session:
        ref = session.get(ScreeningInputRow, item.id)
        facts = dict(ref.ingest_facts)
        if change == "unknown": ref.ingest_facts = None
        elif change == "empty": ref.ingest_facts = {}
        elif change == "future": ref.ingest_facts = {**facts, "version": 2}
        elif change == "bool-version":
            # ORM dirty comparison treats True == 1; force the malformed JSON
            # into storage so this tests the actual persisted version type.
            session.execute(update(ScreeningInputRow).where(ScreeningInputRow.id == item.id)
                            .values(ingest_facts={**facts, "version": True}))
        elif change == "string-flag": ref.ingest_facts = {**facts, "matched_existing": "false"}
        elif change == "missing": ref.ingest_facts = {k:v for k,v in facts.items() if k != "matched_on"}
        elif change == "extra": ref.ingest_facts = {**facts, "extra": "untrusted"}
        elif change == "report-owner": session.get(ReportRow, report.id).org_id = other
        elif change == "resume-owner": session.get(ResumeRow, saved.resume_id).org_id = other
        elif change == "candidate": session.get(ReportRow, report.id).candidate_id = "b"
        elif change == "domain": session.get(ReportRow, report.id).domain = "different"
        else:
            row = session.get(ReportRow, report.id)
            field, value = {"body-id": ("id", "wrong-id"), "body-subject": ("candidate_id", "b"),
                "body-domain": ("domain", "different"), "non-advisory": ("human_review_required", False)}[change]
            row.body = {**row.body, field: value}
        session.commit()
    with pytest.raises(IngestRefused, match="fresh_upload_required"):
        ScreeningStore(factory).recover_report(org, item, input_ttl_days=90, now=lambda: item.claimed_at)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "processing" and row.error is row.report_id is row.signals is None
        assert session.get(ScreeningInputRow, item.id).report_id == report.id
        assert list(session.scalars(select(ReportRow.id))) == [report.id]


@pytest.mark.parametrize("parent", ["candidate", "resume", "report", "sweep"])
def test_recovery_missing_checkpoint_requires_fresh_upload_and_cannot_restore_it(database, parent):
    _, factory = database
    org, _, item, saved, report = checkpoint(factory)
    if parent == "sweep":
        with factory() as session:
            session.execute(delete(ScreeningInputRow).where(ScreeningInputRow.id == item.id))
            session.commit()
    elif parent == "report": assert SqlReportStore(factory).delete(report.id)
    else: assert getattr(CandidateStore(factory), f"delete_{parent}")(getattr(saved, f"{parent}_id"))
    with pytest.raises(IngestRefused, match="fresh_upload_required"):
        ScreeningStore(factory).recover_report(org, item, input_ttl_days=90, now=lambda: item.claimed_at)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
        assert session.get(BatchItemRow, item.id).status == "processing"


@pytest.mark.parametrize("phase", ["lease", "ttl", "commit"])
def test_recovery_expiry_or_interruption_after_write_rolls_back_checkpoint_and_queue(database, phase):
    engine, factory = database
    org, _, item, _, report = checkpoint(factory)
    clock = [item.claimed_at]
    if phase == "ttl":
        with factory() as session:
            session.get(ScreeningInputRow, item.id).created_at = item.claimed_at - timedelta(days=90)
            session.commit()
    writer = make_session_factory(engine)
    def advance(state):
        result = state.invoke_statement()
        if state.is_delete:
            clock[0] += timedelta(seconds=901 if phase == "lease" else 1)
        return result
    if phase == "commit":
        def interrupt(*_): raise Interrupted()
        event.listen(writer, "before_commit", interrupt, once=True)
    else: event.listen(writer, "do_orm_execute", advance, retval=True)
    recover = lambda: ScreeningStore(writer).recover_report(org, item, input_ttl_days=90, now=lambda: clock[0])
    if phase == "lease": assert recover() is CompletionOutcome.REFUSED
    else:
        with pytest.raises(Interrupted if phase == "commit" else IngestRefused): recover()
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.status == "processing" and row.report_id is row.processed_at is None
        assert session.get(ScreeningInputRow, item.id).report_id == report.id
        assert session.get(ReportRow, report.id) is not None


@pytest.mark.parametrize("lock", ["item", "input", "report"])
def test_recovery_waiting_for_lock_rechecks_fresh_clock(database, lock):
    engine, factory = database
    org, _, item, _, report = checkpoint(factory)
    clock = [item.claimed_at]
    writer = make_session_factory(engine)
    ready, pids = Event(), {}
    def started(session, transaction, connection):
        if engine.dialect.name == "postgresql": pids["writer"] = connection.scalar(text("SELECT pg_backend_pid()"))
        ready.set()
    event.listen(writer, "after_begin", started, once=True)
    with factory() as blocker, ThreadPoolExecutor(max_workers=1) as executor:
        model, identity, field = {"item": (BatchItemRow, item.id, "claimed_at"),
            "input": (ScreeningInputRow, item.id, "ingest_facts"),
            "report": (ReportRow, report.id, "body")}[lock]
        blocker.execute(update(model).where(model.id == identity).values(**{field:getattr(model, field)}))
        if engine.dialect.name == "postgresql": pids["blocker"] = blocker.scalar(text("SELECT pg_backend_pid()"))
        pending = executor.submit(ScreeningStore(writer).recover_report, org, item, input_ttl_days=90, now=lambda: clock[0])
        try:
            assert ready.wait(20)
            if engine.dialect.name == "postgresql":
                deadline = monotonic() + 10
                with engine.connect() as observer:
                    while monotonic() < deadline:
                        if pids["blocker"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid":pids["writer"]}): break
                    else: pytest.fail("recovery did not wait for the competing connection")
            assert not pending.done()
            clock[0] += timedelta(seconds=901)
        finally: blocker.rollback()
        assert pending.result(timeout=20) is CompletionOutcome.REFUSED
    with factory() as session:
        assert session.get(BatchItemRow, item.id).status == "processing"
        assert session.get(ScreeningInputRow, item.id).report_id == report.id


@pytest.mark.parametrize("parent", ["candidate", "resume", "report"])
def test_erasure_waits_for_recovery_commit_then_preserves_done_count(database, parent):
    engine, factory = database
    org, batch, item, saved, report = checkpoint(factory)
    writer, deleter = make_session_factory(engine), make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}
    def pause(session):
        if engine.dialect.name == "postgresql": pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)
    def started(session, transaction, connection):
        if engine.dialect.name == "postgresql": pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()
    event.listen(writer, "before_commit", pause, once=True)
    event.listen(deleter, "after_begin", started, once=True)
    erase = ((lambda: SqlReportStore(deleter).delete(report.id)) if parent == "report" else
             lambda: getattr(CandidateStore(deleter), f"delete_{parent}")(getattr(saved, f"{parent}_id")))
    with ThreadPoolExecutor(max_workers=2) as executor:
        recovering = executor.submit(ScreeningStore(writer).recover_report, org, item,
            input_ttl_days=90, now=lambda: item.claimed_at)
        try:
            assert ready.wait(20)
            erasing = executor.submit(erase)
            assert deleting.wait(20)
            if engine.dialect.name == "postgresql":
                deadline = monotonic() + 10
                with engine.connect() as observer:
                    while monotonic() < deadline:
                        if pids["writer"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid":pids["deleter"]}): break
                    else: pytest.fail("erasure did not wait for recovery commit")
            assert not erasing.done()
        finally: release.set()
        assert recovering.result(timeout=20) is CompletionOutcome.DONE
        assert erasing.result(timeout=20)
    assert ScreeningStore(factory).counts(org, batch, now=item.claimed_at).done == 1
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
        assert session.get(BatchItemRow, item.id).status == "done"


def test_postgres_sweep_between_recovery_reads_cannot_restore_checkpoint(database):
    engine, factory = database
    if engine.dialect.name != "postgresql": pytest.skip("PostgreSQL competing private-row write")
    org, _, item, _, report = checkpoint(factory)
    writer = make_session_factory(engine)
    ready, release, paused = Event(), Event(), []
    def pause(state):
        result = state.invoke_statement()
        if state.is_select and state.bind_mapper is not None and state.bind_mapper.class_ is ScreeningInputRow and not paused:
            paused.append(True)
            ready.set()
            assert release.wait(20)
        return result
    event.listen(writer, "do_orm_execute", pause, retval=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        recovering = executor.submit(ScreeningStore(writer).recover_report, org, item,
            input_ttl_days=90, now=lambda: item.claimed_at)
        try:
            assert ready.wait(20)
            with factory() as session:
                session.execute(delete(ScreeningInputRow).where(ScreeningInputRow.id == item.id))
                session.commit()
        finally: release.set()
        with pytest.raises(IngestRefused, match="fresh_upload_required"): recovering.result(timeout=20)
    with factory() as session:
        assert session.get(ScreeningInputRow, item.id) is None
        assert session.get(ReportRow, report.id) is not None
        assert session.get(BatchItemRow, item.id).status == "processing"


def test_recovery_is_scoped_to_owner_and_supports_saved_custom_domains(database):
    from dataclasses import replace
    _, factory = database
    org, batch, item, _, report = checkpoint(factory)
    other = LedgerStore(factory).create_organization("Other recovery org").id
    store = ScreeningStore(factory)
    assert store.recover_report(other, item, input_ttl_days=90, now=lambda: item.claimed_at) is CompletionOutcome.REFUSED
    with factory() as session:
        session.get(ScreeningBatchRow, batch).domain = "custom_domain"
        row = session.get(ReportRow, report.id)
        row.domain = "custom_domain"
        row.body = {**row.body, "domain":"custom_domain"}
        session.commit()
    assert store.recover_report(org, replace(item, domain="custom_domain"), input_ttl_days=90,
        now=lambda: item.claimed_at) is CompletionOutcome.DONE


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
        return CompletionOutcome.FAILED

    with _client(services) as http:
        batch = _register(http, key, ["Synthetic engineer\nSkills: Python"]).json()["id"]
        path = f"/screening/batches/{batch}"
        with monkeypatch.context() as patch:
            patch.setattr(store, "complete", fail)
            response = http.post(path + "/process", headers=headers)
        assert response.status_code == 200
        assert (response.json()["processed"], response.json()["failed"], response.json()["remaining"]) == (0, 1, 0)
        assert http.get(path, headers=headers).json()["counts"] == {
            "pending": 0, "processing": 0, "failed": 1, "done": 0,
        }
        with services.candidates._session_factory() as session:
            ref = session.scalars(select(ScreeningInputRow)).one()
            rid, report_id = ref.resume_id, ref.report_id
            assert report_id is not None
            original_facts = ref.ingest_facts
        assert http.post(path + "/retry", headers={"X-Org-Key": other_key}).status_code == 404
        assert http.post(path + "/retry", headers=headers).json()["requeued"] == 1
        async def must_not_evaluate(*args, **kwargs):
            raise AssertionError("saved report recovery must not evaluate")
        import app.candidates.extractor as extractor
        from app.graph.build import EvaluationEngine
        with monkeypatch.context() as patch:
            patch.setattr(EvaluationEngine, "evaluate", must_not_evaluate)
            patch.setattr(extractor, "extract_profile", must_not_evaluate)
            recovered = http.post(path + "/process", headers=headers)
        assert recovered.status_code == 200
        assert (recovered.json()["processed"], recovered.json()["failed"], recovered.json()["remaining"]) == (1, 0, 0)
        row = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert row["resume_id"] == rid and row["report_id"] == report_id
        assert all(row["signals"][name] == original_facts[name]
                   for name in ("matched_existing", "matched_on", "duplicate_resume"))
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ReportRow.id))) == [report_id]
        assert http.post(path + "/process", headers=headers).json()["processed"] == 0
        assert services.report_store.delete(row["report_id"])
        after = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert after == {**row, "report_id": None}
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ScreeningInputRow))) == []


def test_http_unknown_saved_facts_require_fresh_upload_without_provider_or_duplicate(services, monkeypatch):
    from app.graph.build import EvaluationEngine
    import app.candidates.extractor as extractor
    _, key = _key(services)
    _, other_key = _key(services, "Other recovery tenant")
    headers = {"X-Org-Key": key}
    store = services.screening._store
    with _client(services) as http:
        bid = _register(http, key, ["Synthetic private checkpoint\nSkills: Python"]).json()["id"]
        path = f"/screening/batches/{bid}"
        with monkeypatch.context() as patch:
            patch.setattr(store, "complete", lambda *args, **kwargs: CompletionOutcome.REFUSED)
            first = http.post(path + "/process", headers=headers).json()
        assert (first["processed"], first["failed"], first["remaining"]) == (0, 0, 1)
        with services.candidates._session_factory() as session:
            ref = session.scalars(select(ScreeningInputRow)).one()
            rid = ref.report_id
            ref.ingest_facts = None
            session.get(BatchItemRow, ref.id).claimed_at -= timedelta(days=1)
            session.commit()
        async def unreachable(*args, **kwargs): raise AssertionError("checkpoint refusal must not call providers")
        with monkeypatch.context() as patch:
            patch.setattr(extractor, "extract_profile", unreachable)
            patch.setattr(EvaluationEngine, "evaluate", unreachable)
            response = http.post(path + "/process", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert (body["processed"], body["failed"], body["remaining"]) == (0, 1, 0)
        row = http.get(path + "/queue", headers=headers).json()["rows"][0]
        assert row["status"] == "failed" and row["error"] == "fresh_upload_required"
        assert row["candidate_id"] is row["resume_id"] is row["report_id"] is row["signals"] is None
        assert http.post(path + "/retry", headers=headers).json() == {"batch_id":bid, "requeued":0, "skipped":1}
        assert http.post(path + "/process", headers={"X-Org-Key": other_key}).status_code == 404
        assert http.get(f"/screening/reports/{rid}", headers=headers).status_code == 200
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ReportRow.id))) == [rid]
            assert session.scalars(select(ScreeningInputRow)).one().ingest_facts is None


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
