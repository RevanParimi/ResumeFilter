"""Post-ingest fingerprint writes on real, isolated competing connections."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.candidates.models import FingerprintRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.test_candidate_store import extraction
from tests.test_fingerprint_store import _fp
from tests.test_report_erasure_concurrency import database


@pytest.mark.parametrize("parent", ["candidate", "resume"])
@pytest.mark.parametrize("order", ["erase_first", "write_first"])
def test_fingerprint_erasure_and_retry(database, parent, order, log_output):
    engine, factory = database
    store = CandidateStore(factory)
    saved = store.ingest(extraction(email="erased@example.com"), "private resume")
    kept = store.ingest(extraction(email="kept@example.com"), "kept resume")
    fp = _fp([11, 22, 33])
    store.save_fingerprint(fp, resume_id=kept.resume_id, candidate_id=kept.candidate_id)
    writer_factory = make_session_factory(engine)
    writer = CandidateStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "before_flush" if order == "erase_first" else "after_commit",
                 pause, once=True)

    def write():
        return writer.save_fingerprint(fp, resume_id=saved.resume_id,
                                       candidate_id=saved.candidate_id)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(write)
        try:
            assert ready.wait(20)
            if parent == "candidate":
                assert store.delete_candidate(saved.candidate_id)
            else:
                assert store.delete_resume(saved.resume_id)
        finally:
            release.set()
        if order == "erase_first":
            with pytest.raises(RuntimeError, match=f"^{parent}_erased$"):
                pending.result(timeout=20)
        else:
            assert pending.result(timeout=20) is True
    for _ in range(2):
        with pytest.raises(RuntimeError, match=f"^{parent}_erased$"):
            write()
    with factory() as session:
        rows = list(session.scalars(select(FingerprintRow)))
        assert [(r.resume_id, r.candidate_id, r.signature) for r in rows] == [
            (kept.resume_id, kept.candidate_id, fp.values)]
    assert (store.get_candidate(saved.candidate_id) is None) == (parent == "candidate")
    assert store.latest_profile(kept.candidate_id) is not None
    assert "INSERT INTO resume_fingerprints" not in log_output.text


def test_concurrent_duplicate_fingerprints_are_idempotent(database):
    engine, factory = database
    store = CandidateStore(factory)
    saved = store.ingest(extraction(), "resume")
    writer_factory = make_session_factory(engine)
    ready, release = Event(), Event()
    fp = _fp([1, 2, 3])

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "before_flush", pause, once=True)
    kwargs = {"resume_id": saved.resume_id, "candidate_id": saved.candidate_id}
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(CandidateStore(writer_factory).save_fingerprint, fp, **kwargs)
        try:
            assert ready.wait(20)
            assert store.save_fingerprint(fp, **kwargs) is True
        finally:
            release.set()
        assert pending.result(timeout=20) is False
    assert store.save_fingerprint(fp, **kwargs) is False
    with factory() as session:
        rows = list(session.scalars(select(FingerprintRow)))
        assert len(rows) == 1 and rows[0].signature == fp.values


@pytest.mark.parametrize("parent", ["candidate", "resume"])
def test_postgres_erasure_waits_for_fingerprint_commit(database, parent):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    saved = CandidateStore(factory).ingest(extraction(), "resume")
    writer_factory = make_session_factory(engine)
    deleter_factory = make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}

    def pause(session, *_):
        pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)

    def delete_started(session, transaction, connection):
        pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()

    event.listen(writer_factory, "after_flush", pause, once=True)
    event.listen(deleter_factory, "after_begin", delete_started, once=True)
    deleter = CandidateStore(deleter_factory)
    erase = (lambda: deleter.delete_candidate(saved.candidate_id)) if parent == "candidate" else (
        lambda: deleter.delete_resume(saved.resume_id))
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(CandidateStore(writer_factory).save_fingerprint,
                                  _fp([1, 2, 3]), resume_id=saved.resume_id,
                                  candidate_id=saved.candidate_id)
        try:
            assert ready.wait(20)
            erasing = executor.submit(erase)
            assert deleting.wait(20)
            deadline = monotonic() + 10
            with engine.connect() as observer:
                while monotonic() < deadline:
                    blockers = observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                               {"pid": pids["deleter"]})
                    if pids["writer"] in blockers:
                        break
                else:
                    pytest.fail("erasure never waited on the fingerprint transaction")
            assert not erasing.done()
        finally:
            release.set()
        assert writing.result(timeout=20) is True
        assert erasing.result(timeout=20)
    with factory() as session:
        assert list(session.scalars(select(FingerprintRow))) == []


@pytest.mark.parametrize("duplicate", [False, True])
def test_fingerprint_rejects_wrong_owner(database, duplicate):
    _, factory = database
    store = CandidateStore(factory)
    saved = store.ingest(extraction(), "resume")
    fp = _fp([1, 2, 3])
    if duplicate:
        store.save_fingerprint(fp, resume_id=saved.resume_id, candidate_id=saved.candidate_id)
    with pytest.raises(ValueError, match="^resume_candidate_mismatch$"):
        store.save_fingerprint(fp, resume_id=saved.resume_id, candidate_id="b")
    with factory() as session:
        assert not list(session.scalars(select(FingerprintRow).where(
            FingerprintRow.candidate_id == "b")))


@pytest.mark.parametrize("concurrent_duplicate", [False, True])
def test_unrelated_fingerprint_integrity_error_propagates(database, concurrent_duplicate):
    engine, factory = database
    store = CandidateStore(factory)
    saved = store.ingest(extraction(), "resume")
    kwargs = {"resume_id": saved.resume_id, "candidate_id": saved.candidate_id}

    def invalid_signature(session, *_):
        if concurrent_duplicate:
            CandidateStore(make_session_factory(engine)).save_fingerprint(_fp([1, 2, 3]), **kwargs)
        for row in session.new:
            if isinstance(row, FingerprintRow):
                row.shingle_count = None  # Actual NOT NULL constraint failure.

    event.listen(factory, "before_flush", invalid_signature, once=True)
    with pytest.raises(IntegrityError):
        store.save_fingerprint(_fp([1, 2, 3]), **kwargs)
    assert store.save_fingerprint(_fp([1, 2, 3]), **kwargs) is (not concurrent_duplicate)


@pytest.mark.parametrize("parent", ["candidate", "resume"])
@pytest.mark.parametrize("door", ["admin", "org", "batch"])
def test_ingest_maps_fingerprint_erasure(services, monkeypatch, farm_resume_a, parent, door,
                                       log_output):
    from tests.test_screening_batches_api import _key, _register

    _, key = _key(services)
    headers = {} if door == "admin" else {"X-Org-Key": key}
    save = services.candidates.save_fingerprint
    erased = []

    def erase_then_save(fp, *, resume_id, candidate_id):
        erased.append((candidate_id, resume_id))
        if parent == "candidate":
            assert services.portal.erase(candidate_id)["deleted"]
        else:
            assert services.candidates.delete_resume(resume_id)
        return save(fp, resume_id=resume_id, candidate_id=candidate_id)

    def no_comparison(*args, **kwargs):
        pytest.fail("refused fingerprint ingest continued to comparison/evaluation")

    monkeypatch.setattr(services.candidates, "save_fingerprint", erase_then_save)
    monkeypatch.setattr(services.candidates, "similar_resumes", no_comparison)
    with TestClient(create_app(services), headers=ADMIN_HEADERS,
                    raise_server_exceptions=False) as client:
        if door == "batch":
            batch = _register(client, key, [farm_resume_a]).json()["id"]
            response = client.post(f"/screening/batches/{batch}/process", headers=headers)
            assert response.status_code == 200
            assert response.json()["failed"] == 1 and response.json()["processed"] == 0
            row = client.get(f"/screening/batches/{batch}/queue", headers=headers).json()["rows"][0]
            assert row["error"] == f"{parent}_erased"
            assert row["candidate_id"] is None
        else:
            path = "/candidates" if door == "admin" else "/screening/candidates"
            response = client.post(path, headers=headers,
                                   json={"resume_text": farm_resume_a, "evaluate": True})
            assert response.status_code == 422, response.text
            assert response.json() == {"detail": f"{parent}_erased"}
        assert len(erased) == 1
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(FingerprintRow))) == []
    assert "batch_item_failed" not in log_output.text
    assert "INSERT INTO resume_fingerprints" not in log_output.text
