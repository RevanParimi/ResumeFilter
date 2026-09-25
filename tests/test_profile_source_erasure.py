"""Source ingestion erasure at real SQL and HTTP boundaries, with fake providers."""

import base64
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import delete, event, text
from sqlalchemy.exc import IntegrityError

from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.profile_sources.models import ProfileSourceRow
from app.profile_sources.store import ProfileSourceStore
from app.services.github import GitHubRepoRaw, GitHubUserRaw
from tests.test_profile_sources_service import _bare_candidate, _linkedin_zip
from tests.test_profile_sources_store import _sig
from tests.test_report_erasure_concurrency import database
from tests.test_screening_batches_api import _client


def payload(kind):
    return {"handle": "synthetic"} if kind == "github" else {
        "export_b64": base64.b64encode(_linkedin_zip()).decode()}


@pytest.mark.parametrize("order", ["erase_first", "write_first"])
def test_insert_races_erasure_without_orphan_or_raw_error(database, order):
    engine, factory = database
    keep = ProfileSourceStore(factory)
    keep.save_signal("b", _sig("survivor"))
    writer_factory = make_session_factory(engine)
    writer = ProfileSourceStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "before_flush" if order == "erase_first" else "after_commit", pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(writer.save_signal, "a", _sig("synthetic-private-handle"))
        try:
            assert ready.wait(20)
            assert CandidateStore(factory).delete_candidate("a")
        finally:
            release.set()
        if order == "erase_first":
            with pytest.raises(LookupError, match="candidate not found"):
                pending.result(timeout=20)
        else:
            assert pending.result(timeout=20)
    with pytest.raises(LookupError, match="candidate not found"):
        writer.save_signal("a", _sig())
    assert keep.signals_for_candidate("a") == []
    assert [s.identifier for s in keep.signals_for_candidate("b")] == ["survivor"]


@pytest.mark.parametrize("missing", [False, True])
def test_unrelated_constraint_is_not_erasure_and_store_recovers(database, missing):
    _, factory = database
    if missing:
        CandidateStore(factory).delete_candidate("a")
    store = ProfileSourceStore(factory)
    invalid = _sig().model_copy(update={"identifier": None})
    with pytest.raises(IntegrityError):
        store.save_signal("a", invalid)
    assert store.save_signal("b", _sig("valid"))
    assert [s.identifier for s in store.signals_for_candidate("b")] == ["valid"]


def test_postgres_candidate_delete_waits_for_source_commit(database):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    writer_factory = make_session_factory(engine)
    writer = ProfileSourceStore(writer_factory)
    ready, release, deleting = Event(), Event(), Event()
    reader_factory = make_session_factory(engine)
    pids = []

    def pause(session, *_):
        ready.set()
        assert release.wait(20)

    def delete_candidate():
        with reader_factory() as session:
            pids.append(session.scalar(text("SELECT pg_backend_pid()")))
            deleting.set()
            session.execute(delete(CandidateRow).where(CandidateRow.id == "a"))
            session.commit()

    event.listen(writer_factory, "after_flush", pause, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writing = executor.submit(writer.save_signal, "a", _sig())
        removal = None
        try:
            assert ready.wait(20)
            removal = executor.submit(delete_candidate)
            assert deleting.wait(20)
            blocked = False
            deadline = monotonic() + 10
            with engine.connect() as connection:
                while monotonic() < deadline:
                    if connection.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pids[0]}):
                        blocked = True
                        break
            assert blocked and not removal.done()
        finally:
            release.set()
        assert writing.result(timeout=20)
        removal.result(timeout=20)
    assert writer.signals_for_candidate("a") == []
    assert CandidateStore(factory).get_candidate("b") is not None


@pytest.mark.parametrize("kind", ["github", "linkedin"])
@pytest.mark.parametrize("boundary", ["initial", "fetch", "flush", "commit", "source_only"])
def test_api_source_erasure_has_safe_refusal(services, monkeypatch, kind, boundary):
    from app.profile_sources import service as module

    cid = _bare_candidate(services.candidates)
    other = _bare_candidate(services.candidates)
    store = services.profile_sources._store
    store.save_signal(other, _sig("keep"))

    def erase():
        assert services.portal.erase(cid)["deleted"]

    if boundary == "initial":
        original = services.candidates.get_candidate
        first = True

        def checked(candidate_id):
            nonlocal first
            result = original(candidate_id)
            if first and candidate_id == cid:
                first = False
                erase()
            return result
        monkeypatch.setattr(services.candidates, "get_candidate", checked)
    elif boundary == "fetch":
        if kind == "github":
            original = services.profile_sources._github.gather_user_signal

            async def fetched(*args):
                result = await original(*args)
                erase()
                return result
            monkeypatch.setattr(services.profile_sources._github, "gather_user_signal", fetched)
        else:
            original = module.parse_linkedin_export

            def parsed(*args):
                result = original(*args)
                erase()
                return result
            monkeypatch.setattr(module, "parse_linkedin_export", parsed)
    elif boundary == "flush":
        def before_flush(session, *_):
            if any(isinstance(row, ProfileSourceRow) for row in session.new):
                erase()
        event.listen(store._session_factory, "before_flush", before_flush)
    else:
        original = store.save_signal

        def committed(*args):
            row_id = original(*args)
            if boundary == "commit":
                erase()
            else:
                with store._session_factory() as session:
                    session.execute(delete(ProfileSourceRow).where(ProfileSourceRow.id == row_id))
                    session.commit()
            return row_id
        monkeypatch.setattr(store, "save_signal", committed)
    try:
        with _client(services) as client:
            response = client.post(f"/candidates/{cid}/sources/{kind}", json=payload(kind))
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "source not found" if boundary == "source_only" else "candidate not found"}
        assert store.signals_for_candidate(cid) == []
        assert [s.identifier for s in store.signals_for_candidate(other)] == ["keep"]
        assert (services.candidates.get_candidate(cid) is not None) == (boundary == "source_only")
    finally:
        if boundary == "flush":
            event.remove(store._session_factory, "before_flush", before_flush)


@pytest.mark.parametrize("kind", ["github", "linkedin"])
@pytest.mark.parametrize("operation", ["save_signal", "require_saved_signal"])
def test_unrelated_lookup_error_is_not_a_404(services, monkeypatch, kind, operation):
    cid = _bare_candidate(services.candidates)

    def broken(*args):
        raise LookupError("synthetic private lookup detail")

    with _client(services) as client:
        with monkeypatch.context() as scoped:
            scoped.setattr(services.profile_sources._store, operation, broken)
            response = client.post(f"/candidates/{cid}/sources/{kind}", json=payload(kind))
        assert response.status_code == 500
        assert "synthetic private" not in response.text
        assert client.post(f"/candidates/{cid}/sources/{kind}", json=payload(kind)).status_code == 200


def test_final_guard_checks_storage_id_and_exact_ownership(database):
    _, factory = database
    store = ProfileSourceStore(factory)
    signal = _sig()
    row_id = store.save_signal("a", signal)
    assert row_id != signal.id
    assert store.require_saved_signal("a", row_id) is None
    with pytest.raises(LookupError, match="source not found"):
        store.require_saved_signal("a", signal.id)
    with pytest.raises(ValueError, match="source_candidate_mismatch"):
        store.require_saved_signal("b", row_id)
    CandidateStore(factory).delete_candidate("a")
    with pytest.raises(LookupError, match="candidate not found"):
        store.require_saved_signal("a", row_id)


@pytest.mark.parametrize("kind", ["github", "linkedin"])
def test_erasure_after_final_read_leaves_only_a_response_snapshot(services, monkeypatch, kind):
    cid = _bare_candidate(services.candidates)
    store = services.profile_sources._store
    original = store.require_saved_signal
    checked = []

    def check_then_erase(candidate_id, row_id):
        original(candidate_id, row_id)
        checked.append(row_id)
        assert services.portal.erase(candidate_id)["deleted"]

    monkeypatch.setattr(store, "require_saved_signal", check_then_erase)
    with _client(services) as client:
        response = client.post(f"/candidates/{cid}/sources/{kind}", json=payload(kind))
    assert response.status_code == 200 and len(checked) == 1
    assert services.candidates.get_candidate(cid) is None
    assert store.signals_for_candidate(cid) == []


@pytest.mark.parametrize("kind", ["github", "linkedin"])
def test_shared_curation_policy_survives_source_refusal_and_erasure(services, monkeypatch, kind):
    cid = _bare_candidate(services.candidates)
    other = _bare_candidate(services.candidates)
    if kind == "github":
        async def fetched(login):
            return GitHubUserRaw(login=login, available=True, repos=[GitHubRepoRaw(
                name="demo", language="SyntheticLang", languages={"SyntheticLang": 1000})])
        monkeypatch.setattr(services.profile_sources._github, "gather_user_signal", fetched)
        body = payload(kind)
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Skills.csv", "Name\nSyntheticLang\n")
        body = {"export_b64": base64.b64encode(buffer.getvalue()).decode()}
    store = services.profile_sources._store
    original = store.save_signal

    def erase_then_save(candidate_id, signal):
        assert services.portal.erase(candidate_id)["deleted"]
        return original(candidate_id, signal)

    with _client(services) as client:
        assert client.post(f"/candidates/{other}/sources/{kind}", json=body).status_code == 200
        with monkeypatch.context() as scoped:
            scoped.setattr(store, "save_signal", erase_then_save)
            response = client.post(f"/candidates/{cid}/sources/{kind}", json=body)
        assert response.status_code == 404
        assert store.signals_for_candidate(cid) == []
        terms = services.curation.list_unmapped().terms
        term = next(t for t in terms if t.norm_key == "syntheticlang")
        assert term.display_name == "SyntheticLang" and term.occurrences == 2
        assert term.source_types == ["github" if kind == "github" else "linkedin_export"]
        assert services.portal.erase(other)["deleted"]
        assert services.curation.list_unmapped().terms == terms


def test_erasure_during_implicit_handle_resolution_is_not_bad_input(services, monkeypatch):
    cid = _bare_candidate(services.candidates)

    def erased_profile(candidate_id):
        assert services.portal.erase(candidate_id)["deleted"]
        return None

    monkeypatch.setattr(services.candidates, "latest_profile", erased_profile)
    with _client(services) as client:
        response = client.post(f"/candidates/{cid}/sources/github", json={})
    assert response.status_code == 404
    assert response.json() == {"detail": "candidate not found"}
