"""Erasure of cached matches cancels disclosure without losing survivors."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, text
from sqlalchemy.exc import IntegrityError

from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.features.store import FeatureStore
from app.ledger.models import AuditLogRow
from app.ledger.store import LedgerStore
from app.main import create_app
from app.matching import store as matching
from app.matching.schema import JobRequisitionInput
from app.matching.store import JobStore
from tests.conftest import ADMIN_HEADERS
from tests.test_job_store_match import AS_OF, _seed_candidate, _settings
from tests.test_report_erasure_concurrency import database


def seed(factory):
    candidates = CandidateStore(factory)
    ledger, features = LedgerStore(factory), FeatureStore(factory)
    jobs = JobStore(make_session_factory(factory.kw["bind"]), candidate_store=candidates,
                    feature_store=features, settings=_settings())
    org = ledger.create_organization("Synthetic owner")
    ids = [_seed_candidate(candidates, features, ledger, name, f"{name}@example.com", skills)
           for name, skills in (("Strong", ("python", "django")),
                                ("Weak", ("python",)), ("Other", ("java",)))]
    req = jobs.create_requisition(org.id, JobRequisitionInput(
        title="Engineer", must_have_skills=("python", "django")))
    baseline = jobs.run_match(org.id, req.id, as_of=AS_OF)
    with factory() as session:
        session.execute(delete(AuditLogRow).where(AuditLogRow.action == "match.surface"))
        session.commit()
    return candidates, ledger, jobs, org, req, ids, baseline


def disclosures(ledger, cid):
    return [a for a in ledger.audit_for_candidate(cid) if a.action == "match.surface"]


@pytest.mark.parametrize("boundary", ["ranked", "before_flush", "after_commit"])
@pytest.mark.parametrize("limit", [1, 3])
def test_cached_match_erasure(database, monkeypatch, boundary, limit):
    _, factory = database
    candidates, ledger, jobs, org, req, ids, baseline = seed(factory)
    erased = ids[0]

    def erase(*_):
        assert candidates.delete_candidate(erased)

    if boundary == "ranked":
        original = matching._match_engine

        def rank_then_erase(*args):
            result = original(*args)
            erase()
            return result
        monkeypatch.setattr(matching, "_match_engine", rank_then_erase)
    else:
        event.listen(jobs._session_factory, boundary, erase, once=True)
    result = jobs.run_match(org.id, req.id, as_of=AS_OF, limit=limit)
    remaining = [m for m in baseline.ranked if m.candidate_id != erased]
    expected = remaining[:limit] if boundary != "after_commit" else [
        m for m in baseline.ranked[:limit] if m.candidate_id != erased]
    assert list(result.ranked) == expected  # full scores, contributions and skill details
    assert (result.pool_size, result.filtered_size, result.advisory) == (2, 2, True)
    assert ledger.audit_for_candidate(erased) == []
    for index, match in enumerate(expected, start=1):
        rows = disclosures(ledger, match.candidate_id)
        assert len(rows) == 1 and rows[0].actor_id == org.id
        assert rows[0].details == {"score": match.score,
            "rank": index + (1 if boundary == "after_commit" else 0)}
    if boundary == "ranked":
        monkeypatch.setattr(matching, "_match_engine", original)
    retried = jobs.run_match(org.id, req.id, as_of=AS_OF, limit=limit)
    assert [m.candidate_id for m in retried.ranked] == ids[1:][:limit]


@pytest.mark.parametrize("target", ["all", "outside_limit", "filtered"])
def test_counts_exclude_erased_pool_members(database, monkeypatch, target):
    _, factory = database
    candidates, ledger, jobs, org, req, ids, _ = seed(factory)
    if target == "filtered":
        req = jobs.update_requisition(org.id, req.id, spec=JobRequisitionInput(
            title="Strict", must_have_skills=("python", "django"), min_skill_coverage=0.75))
    erased = ids if target == "all" else ids[1:]
    original = matching._match_engine

    def rank_then_erase(*args):
        result = original(*args)
        for cid in erased:
            assert candidates.delete_candidate(cid)
        return result
    monkeypatch.setattr(matching, "_match_engine", rank_then_erase)
    result = jobs.run_match(org.id, req.id, as_of=AS_OF, limit=1)
    assert result.pool_size == result.filtered_size == (0 if target == "all" else 1)
    assert [m.candidate_id for m in result.ranked] == ([] if target == "all" else ids[:1])
    assert all(ledger.audit_for_candidate(cid) == [] for cid in erased)


def test_each_retry_removes_new_erasure_without_duplicate_audits(database):
    _, factory = database
    candidates, ledger, jobs, org, req, ids, _ = seed(factory)
    pending = iter(ids[:2])

    def erase(session, *_):
        cid = next(pending, None)
        if cid is not None:
            assert candidates.delete_candidate(cid)
    event.listen(jobs._session_factory, "before_flush", erase)
    try:
        result = jobs.run_match(org.id, req.id, as_of=AS_OF, limit=1)
    finally:
        event.remove(jobs._session_factory, "before_flush", erase)
    assert [m.candidate_id for m in result.ranked] == ids[2:]
    assert result.pool_size == result.filtered_size == 1
    assert len(disclosures(ledger, ids[2])) == 1
    assert disclosures(ledger, ids[2])[0].details["rank"] == 1


def test_unrelated_integrity_failure_rolls_back_batch(database):
    _, factory = database
    _, ledger, jobs, org, req, ids, _ = seed(factory)

    def invalid(session, *_):
        for row in session.new:
            if isinstance(row, AuditLogRow):
                row.action = None
    event.listen(jobs._session_factory, "before_flush", invalid, once=True)
    with pytest.raises(IntegrityError):
        jobs.run_match(org.id, req.id, as_of=AS_OF)
    assert all(disclosures(ledger, cid) == [] for cid in ids)
    assert len(jobs.run_match(org.id, req.id, as_of=AS_OF).ranked) == 3


def test_unrelated_lookup_failure_is_not_erasure(database, monkeypatch):
    _, factory = database
    _, _, jobs, org, req, _, _ = seed(factory)

    def broken(*_):
        raise LookupError("unrelated lookup failure")
    monkeypatch.setattr(jobs._candidates, "profile_as_of", broken)
    with pytest.raises(LookupError, match="unrelated lookup failure"):
        jobs.run_match(org.id, req.id, as_of=AS_OF)


@pytest.mark.parametrize("route", ["match", "board"])
@pytest.mark.parametrize("boundary", ["before_flush", "after_commit"])
def test_api_all_erased_at_audit_returns_existing_empty_contract(services, monkeypatch, route, boundary):
    factory = services.candidates._session_factory
    candidates, ledger, jobs, org, req, ids, _ = seed(factory)
    key = ledger.issue_api_key(org.id)
    monkeypatch.setattr(services, "jobs", jobs)
    monkeypatch.setattr(services.dashboard, "_jobs", jobs)

    def erase(*_):
        for cid in ids:
            assert candidates.delete_candidate(cid)
    event.listen(jobs._session_factory, boundary, erase, once=True)
    with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as client:
        url, headers = f"/jobs/{req.id}/{route}", {"X-Org-Key": key}
        response = client.post(url, headers=headers, json={}) if route == "match" else client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json() if route == "match" else response.json()["match"]
        assert (body["ranked"], body["pool_size"], body["filtered_size"], body["reason"]) == (
            [], 0, 0, "no_materialized_candidates")
    assert all(ledger.audit_for_candidate(cid) == [] for cid in ids)


@pytest.mark.parametrize("boundary", ["before_flush", "after_commit"])
def test_competing_audit_and_erasure_connections(database, boundary):
    _, factory = database
    candidates, ledger, jobs, org, req, ids, _ = seed(factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)
    event.listen(jobs._session_factory, boundary, pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(jobs.run_match, org.id, req.id, as_of=AS_OF)
        try:
            assert ready.wait(20)
            assert candidates.delete_candidate(ids[0])
        finally:
            release.set()
        result = pending.result(timeout=20)
    assert [m.candidate_id for m in result.ranked] == ids[1:]
    assert ledger.audit_for_candidate(ids[0]) == []
    assert all(len(disclosures(ledger, cid)) == 1 for cid in ids[1:])


@pytest.mark.parametrize("route", ["match", "board"])
@pytest.mark.parametrize("boundary", ["before_flush", "after_commit"])
@pytest.mark.parametrize("door", ["admin", "portal"])
def test_api_omits_erased_disclosure_and_preserves_ownership(services, monkeypatch, route, boundary, door):
    factory = services.candidates._session_factory
    candidates, ledger, jobs, org, req, ids, _ = seed(factory)
    key = ledger.issue_api_key(org.id)
    other = ledger.create_organization("Other owner")
    other_key = ledger.issue_api_key(other.id)
    monkeypatch.setattr(services, "jobs", jobs)
    monkeypatch.setattr(services.dashboard, "_jobs", jobs)

    def erase(*_):
        if door == "portal":
            assert services.portal.erase(ids[0])["deleted"]
        else:
            assert candidates.delete_candidate(ids[0])
    event.listen(jobs._session_factory, boundary, erase, once=True)
    with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as client:
        def call(headers):
            url = f"/jobs/{req.id}/{route}"
            return client.post(url, headers=headers, json={}) if route == "match" else client.get(url, headers=headers)
        assert call({}).status_code == 401
        assert call({"X-Org-Key": other_key}).status_code == 404
        assert candidates.get_candidate(ids[0]) is not None  # unauthorized calls never reached audit
        assert all(disclosures(ledger, cid) == [] for cid in ids)
        for _ in range(2):
            response = call({"X-Org-Key": key})
            assert response.status_code == 200, response.text
            body = response.json() if route == "match" else response.json()["match"]
            assert [m["candidate_id"] for m in body["ranked"]] == ids[1:]
            assert body["pool_size"] == body["filtered_size"] == 2
            assert body["advisory"] is True
            assert ids[0] not in response.text and "INSERT INTO" not in response.text
    assert ledger.audit_for_candidate(ids[0]) == []


def test_postgres_disclosure_fk_blocks_erasure(database):
    engine, factory = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock inspection")
    _, ledger, jobs, org, req, ids, _ = seed(factory)
    deleter = make_session_factory(engine)
    ready, release, deleting = Event(), Event(), Event()
    pids = {}

    def pause(session, *_):
        pids["writer"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20)

    def started(session, transaction, connection):
        pids["deleter"] = connection.scalar(text("SELECT pg_backend_pid()"))
        deleting.set()
    event.listen(jobs._session_factory, "after_flush", pause, once=True)
    event.listen(deleter, "after_begin", started, once=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(jobs.run_match, org.id, req.id, as_of=AS_OF)
        try:
            assert ready.wait(20)
            erasing = executor.submit(CandidateStore(deleter).delete_candidate, ids[0])
            assert deleting.wait(20)
            with engine.connect() as observer:
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    if pids["writer"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"),
                                                         {"pid": pids["deleter"]}):
                        break
                else:
                    pytest.fail("erasure did not wait for disclosure audit FK lock")
            assert not erasing.done()
        finally:
            release.set()
        pending.result(timeout=20)  # final snapshot may run on either side of delete commit
        assert erasing.result(timeout=20)
    assert ledger.audit_for_candidate(ids[0]) == []
    assert all(len(disclosures(ledger, cid)) == 1 for cid in ids[1:])
