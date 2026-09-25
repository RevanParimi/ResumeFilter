"""Resolved identity must never be recreated by interrupted ingest work."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm.exc import StaleDataError

from app.candidates.models import CandidateRow, ResumeRow, ExtractionRow
from app.candidates.store import CandidateErasedError, CandidateStore
from app.core.db import make_session_factory
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.test_candidate_store import extraction
from tests.test_report_erasure_concurrency import database


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("order", ["erase_first", "write_first"])
def test_resolved_ingest_erasure(database, duplicate, order, log_output):
    engine, factory = database
    store = CandidateStore(factory)
    profile = extraction(email="synthetic@example.com")
    original = store.ingest(profile, "old resume")
    kept = store.ingest(extraction(email="kept@example.com"), "kept resume")
    writer_factory = make_session_factory(engine)
    writer = CandidateStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    hook = "before_flush" if order == "erase_first" else "after_commit"
    event.listen(writer_factory, hook, pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(writer.ingest, profile,
                                  "old resume" if duplicate else "private new resume")
        try:
            assert ready.wait(20)
            assert store.delete_candidate(original.candidate_id)
        finally:
            release.set()
        if order == "erase_first":
            # Assert the public domain refusal, not the ORM exception wording.
            with pytest.raises(CandidateErasedError, match="^candidate_erased$"):
                pending.result(timeout=20)
        else:
            outcome = pending.result(timeout=20)
            assert outcome.candidate_id == original.candidate_id
            assert outcome.duplicate_resume is duplicate

    with factory() as session:
        assert session.get(CandidateRow, original.candidate_id) is None
        assert list(session.scalars(select(ResumeRow.id))) == [kept.resume_id]
        assert list(session.scalars(select(ExtractionRow.id))) == [kept.extraction_id]
        assert session.scalar(select(CandidateRow).where(
            CandidateRow.email_hash == profile.profile.contact.email_hash)) is None
    assert store.latest_profile(kept.candidate_id) is not None
    assert "private new resume" not in log_output.text


def test_unrelated_stale_error_propagates(database):
    _, factory = database
    store = CandidateStore(factory)
    profile = extraction(email="synthetic@example.com")
    saved = store.ingest(profile, "original")

    def unrelated(*_):
        raise StaleDataError("synthetic unrelated stale failure")

    event.listen(factory, "before_flush", unrelated, once=True)
    with pytest.raises(StaleDataError):
        store.ingest(profile, "changed")
    assert store.get_candidate(saved.candidate_id).resume_count == 1
    assert store.ingest(profile, "retry").resume_version == 2


@pytest.mark.parametrize("door", ["admin", "org"])
@pytest.mark.parametrize("erase", ["admin", "portal"])
def test_upload_refuses_erased_resolved_identity(services, monkeypatch, door, erase, log_output):
    with TestClient(create_app(services), headers=ADMIN_HEADERS,
                    raise_server_exceptions=False) as client:
        org = services.ledger.create_organization("Synthetic agency")
        key = services.ledger.issue_api_key(org.id)
        headers = {} if door == "admin" else {"X-Org-Key": key}
        path = "/candidates" if door == "admin" else "/screening/candidates"
        body = {"resume_text": "Synthetic Person\nEmail: synthetic@example.com\nSkills: Python",
                "evaluate": False}
        original = client.post(path, headers=headers, json=body)
        assert original.status_code == 200
        cid = original.json()["candidate_id"]
        resolver = services.candidates._resolve_candidate
        resolved = []

        def erase_resolved(session, profile):
            row, matched_on = resolver(session, profile)
            resolved.append(row.id)
            if erase == "portal":
                assert services.portal.erase(row.id)["deleted"]
            else:
                assert services.candidates.delete_candidate(row.id)
            return row, matched_on

        with monkeypatch.context() as patch:
            patch.setattr(services.candidates, "_resolve_candidate", erase_resolved)
            response = client.post(path, headers=headers, json=body)
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": "candidate_erased"}
        assert resolved == [cid]  # No automatic re-resolution/recreation.
        assert services.candidates.get_candidate(cid) is None
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ResumeRow))) == []
            assert list(session.scalars(select(ExtractionRow))) == []
        assert "UPDATE candidates" not in log_output.text
        # A distinct new upload remains allowed by existing policy, under a new ID.
        retry = client.post(path, headers=headers, json=body)
        assert retry.status_code == 200
        assert retry.json()["candidate_id"] != cid
        assert retry.json()["matched_existing"] is False


@pytest.mark.parametrize("duplicate", [False, True])
def test_postgres_delete_waits_for_ingest_commit(database, duplicate):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    store = CandidateStore(factory)
    profile = extraction(email="synthetic@example.com")
    saved = store.ingest(profile, "original")
    writer_factory = make_session_factory(engine)
    deleter_factory = make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}

    def pause_after_update(session, *_):
        pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)

    def delete_started(session, transaction, connection):
        pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()

    event.listen(writer_factory, "after_flush", pause_after_update, once=True)
    event.listen(deleter_factory, "after_begin", delete_started, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(CandidateStore(writer_factory).ingest, profile,
                                  "original" if duplicate else "new private resume")
        try:
            assert ready.wait(20)
            erasing = executor.submit(CandidateStore(deleter_factory).delete_candidate,
                                      saved.candidate_id)
            assert deleting.wait(20)
            deadline = monotonic() + 10
            with engine.connect() as observer:
                while monotonic() < deadline:
                    blockers = observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                               {"pid": pids["deleter"]})
                    if pids["writer"] in blockers:
                        break
                else:
                    pytest.fail("erasure never waited on the ingest transaction")
            assert not erasing.done()
        finally:
            release.set()
        assert writing.result(timeout=20).candidate_id == saved.candidate_id
        assert erasing.result(timeout=20)
    with factory() as session:
        assert session.get(CandidateRow, saved.candidate_id) is None
        assert list(session.scalars(select(ResumeRow))) == []
        assert list(session.scalars(select(ExtractionRow))) == []


def test_batch_records_erased_ingest_refusal(services, monkeypatch, log_output):
    from tests.test_screening_batches_api import _key, _register

    _, key = _key(services)
    headers = {"X-Org-Key": key}
    resume = "Synthetic Person\nEmail: synthetic@example.com\nSkills: Python"
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        saved = client.post("/screening/candidates", headers=headers,
                            json={"resume_text": resume, "evaluate": False}).json()
        batch = _register(client, key, [resume]).json()["id"]
        resolver = services.candidates._resolve_candidate

        def erase(session, profile):
            row, matched_on = resolver(session, profile)
            assert services.candidates.delete_candidate(row.id)
            return row, matched_on

        monkeypatch.setattr(services.candidates, "_resolve_candidate", erase)
        ran = client.post(f"/screening/batches/{batch}/process", headers=headers)
        assert ran.status_code == 200
        assert ran.json()["failed"] == 1
        assert ran.json()["processed"] == 0
        rows = client.get(f"/screening/batches/{batch}/queue", headers=headers).json()["rows"]
        assert rows[0]["status"] == "failed"
        assert rows[0]["error"] == "candidate_erased"
        assert rows[0]["candidate_id"] is None
        assert services.candidates.get_candidate(saved["candidate_id"]) is None
        assert "batch_item_failed" not in log_output.text
