"""Stale training inputs must be omitted when the subject disappears."""

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.features import default_view, get_feature_registry
from app.features.export import export_training_csv, export_training_parquet, ParquetUnavailable
from app.features.materialize import MaterializedVector
from app.features.schema import FeatureVector
from app.features.training import build_training_set
from app.ledger.models import AuditLogRow
from app.ledger.store import LedgerStore
from tests.test_report_erasure_concurrency import database

T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def inputs(factory, allowed=True):
    ledger = LedgerStore(factory)
    org = ledger.create_organization("Synthetic org")
    vectors = []
    for cid in ("a", "b"):
        ledger.grant_consent(candidate_id=cid, purpose="ledger_write", org_id=org.id,
                             now=T - timedelta(days=1))
        ledger.submit_interview_record(org_id=org.id, candidate_id=cid, stage="hm",
            outcome="hired", interviewed_at=T + timedelta(days=1))
        vectors.append(MaterializedVector(vector=FeatureVector(candidate_id=cid,
            as_of=T, view_name="core_v1", view_version=1, values={}, missing=()),
            consent_state={"allowed": allowed}, materialized_at=T))
    return ledger, vectors


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("order", ["erase_first", "audit_first"])
def test_training_audit_commit_order(database, allowed, order):
    engine, factory = database
    writer_factory = make_session_factory(engine)
    ledger = LedgerStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    hook = "before_flush" if order == "erase_first" else "after_commit"
    event.listen(writer_factory, hook, pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(ledger.audit_training_label, "a", allowed=allowed, as_of=T)
            try:
                assert ready.wait(20)
                assert CandidateStore(factory).delete_candidate("a")
            finally:
                release.set()
            if order == "erase_first":
                with pytest.raises(LookupError, match="candidate_unavailable"):
                    pending.result(timeout=20)
            else:
                assert pending.result(timeout=20) is None
    finally:
        event.remove(writer_factory, hook, pause)
    with pytest.raises(LookupError, match="candidate_unavailable"):
        ledger.audit_training_label("a", allowed=allowed, as_of=T)
    assert ledger.audit_for_candidate("a") == []
    assert ledger.audit_training_label("b", allowed=allowed, as_of=T) is None


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("boundary", ["absent", "before_flush", "after_commit", "later_example", "no_audit", "no_audit_after_read"])
def test_builder_omits_erased_vectors_and_cached_labels(database, monkeypatch, tmp_path, allowed, boundary):
    engine, factory = database
    ledger, vectors = inputs(factory, allowed)
    writer = make_session_factory(engine)
    monkeypatch.setattr(ledger, "_session_factory", writer)
    candidates = CandidateStore(factory)
    audit = not boundary.startswith("no_audit")
    initial = vectors

    def erase(*_):
        assert candidates.delete_candidate("a")

    if boundary in ("absent", "no_audit"):
        erase()
    elif boundary in ("before_flush", "after_commit"):
        event.listen(writer, boundary, erase, once=True)
    elif boundary == "later_example":
        original = ledger.audit_training_label

        def erase_earlier(cid, **kwargs):
            if cid == "b" and candidates.get_candidate("a") is not None:
                erase()
            return original(cid, **kwargs)
        monkeypatch.setattr(ledger, "audit_training_label", erase_earlier)
    else:
        # Pause after both outcome queries, retaining an in-memory hired label.
        original = ledger.coding_rounds_for_candidate

        def read_then_erase(cid):
            rows = original(cid)
            if cid == "a" and candidates.get_candidate("a") is not None:
                erase()
            return rows
        monkeypatch.setattr(ledger, "coding_rounds_for_candidate", read_then_erase)
        if not allowed:
            # Withheld subjects never read outcomes. Erase during input iteration.
            def stream():
                yield vectors[0]
                erase()
                yield vectors[1]
            initial = stream()

    if not allowed:
        def forbidden(*_):
            pytest.fail("withheld outcomes must not be read")
        monkeypatch.setattr(ledger, "records_for_candidate", forbidden)
        monkeypatch.setattr(ledger, "coding_rounds_for_candidate", forbidden)

    examples = build_training_set(initial, ledger_store=ledger, audit=audit)
    assert [ex.vector.candidate_id for ex in examples] == ["b"]
    label = examples[0].label
    assert label.withheld is (not allowed)
    assert label.hired is (True if allowed else None)
    assert build_training_set(vectors, ledger_store=ledger, audit=audit) == examples
    assert ledger.audit_for_candidate("a") == []
    joins = [x for x in ledger.audit_for_candidate("b") if x.action == "training.label"]
    assert bool(joins) is audit
    if audit:
        assert joins[-1].details == {"allowed": allowed, "as_of": T.isoformat()}
    registry = get_feature_registry()
    view = default_view(registry)
    path = tmp_path / "training.csv"
    export_training_csv(examples, view=view, path=str(path))
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["candidate_id"] for row in rows] == ["b"]
    assert rows[0]["label_withheld"] == str(not allowed)
    path = tmp_path / "training.parquet"
    try:
        export_training_parquet(examples, view=view, registry=registry, path=str(path))
    except ParquetUnavailable:
        assert not path.exists()
    else:
        import pyarrow.parquet as pq
        assert pq.read_table(path).column("candidate_id").to_pylist() == ["b"]


def test_unrelated_audit_errors_propagate(database, monkeypatch):
    _, factory = database
    ledger, vectors = inputs(factory)

    def invalid(session, *_):
        for row in session.new:
            if isinstance(row, AuditLogRow):
                row.action = None

    event.listen(factory, "before_flush", invalid, once=True)
    with pytest.raises(IntegrityError):
        build_training_set(vectors, ledger_store=ledger)
    assert CandidateStore(factory).get_candidate("a") is not None
    assert not [a for a in ledger.audit_for_candidate("a") if a.action == "training.label"]
    assert len(build_training_set(vectors, ledger_store=ledger)) == 2

    def broken(*args, **kwargs):
        raise LookupError("unrelated lookup failure")
    monkeypatch.setattr(ledger, "audit_training_label", broken)
    with pytest.raises(LookupError, match="unrelated lookup failure"):
        build_training_set(vectors, ledger_store=ledger)


def test_postgres_training_audit_blocks_erasure(database):
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
        pending = executor.submit(LedgerStore(writer).audit_training_label, "a", allowed=True, as_of=T)
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
                    pytest.fail("erasure did not wait for training audit FK lock")
            assert not erasing.done()
        finally:
            release.set()
        assert pending.result(timeout=20) is None
        assert erasing.result(timeout=20)
    assert LedgerStore(factory).audit_for_candidate("a") == []
