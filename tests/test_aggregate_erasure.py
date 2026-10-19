"""Controlled aggregate reads through both HTTP erasure doors; no live providers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.candidates.store import CandidateStore
from tests.conftest import make_services
from tests.test_profile_sources_store import _sig
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report
from tests.test_screening_batches_api import _client


VIEWS = ("sources", "me", "access-log", "consents")


@pytest.fixture
def services(database, settings):
    _, factory = database
    return make_services(settings, candidates=CandidateStore(factory))


def seed(services, email):
    cid = services.candidates.create_bare_candidate(email_hash=services.auth.hash_email(email))
    key = services.candidates.issue_access_key(cid)
    services.profile_sources._store.save_signal(cid, _sig("private-" + cid))
    services.report_store.save(_report(candidate_id=cid))
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_read")
    return cid, {"X-Candidate-Key": key}


def path(view, cid):
    return f"/candidates/{cid}/sources" if view == "sources" else f"/portal/{view}"


def boundary(services, view, stage):
    if stage == "source":
        return services.profile_sources, "list_sources"
    if stage == "early":
        return ((services.profile_sources, "list_sources") if view == "sources"
                else (services.portal, {"me": "my_data", "access-log": "access_log",
                                        "consents": "consents"}[view]))
    return {
        "sources": (services.profile_sources._store, "signals_for_candidate"),
        "me": (services.ledger, "consents_for_candidate"),
        "access-log": (services.ledger, "audit_for_candidate"),
        "consents": (services.ledger, "consents_for_candidate"),
    }[view]


@pytest.mark.parametrize("door", ["portal", "admin"])
@pytest.mark.parametrize(("view", "stage"),
                         [(view, stage) for view in VIEWS for stage in ("early", "loaded")]
                         + [("me", "source")])
def test_erasure_during_aggregate_has_safe_http_refusal(services, monkeypatch, door, stage, view):
    cid, headers = seed(services, "erase@example.in")
    keeper, keep_headers = seed(services, "keep@example.in")
    owner, method = boundary(services, view, stage)
    actual = getattr(owner, method)
    ready, release = Event(), Event()

    def hold(candidate_id, *args, **kwargs):
        if candidate_id != cid:
            return actual(candidate_id, *args, **kwargs)
        result = actual(candidate_id, *args, **kwargs) if stage == "loaded" else None
        ready.set()
        assert release.wait(20)
        return result if stage == "loaded" else actual(candidate_id, *args, **kwargs)

    monkeypatch.setattr(owner, method, hold)
    # Separate ASGI loops let erasure progress while the reader is held.
    with _client(services) as reader, _client(services) as eraser:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(reader.get, path(view, cid), headers=headers)
            try:
                assert ready.wait(20)
                endpoint = "/portal/me" if door == "portal" else f"/candidates/{cid}"
                deleted = eraser.delete(endpoint, headers=headers)
                assert deleted.status_code == 200 and deleted.json()["deleted"]
            finally:
                release.set()
            response = pending.result(timeout=20)
        assert response.status_code == 404
        assert response.json() == {"detail": "candidate not found"}
        assert reader.get(path(view, keeper), headers=keep_headers).status_code == 200
        assert reader.get("/portal/me", headers=headers).status_code == 401
    assert services.candidates.get_candidate(cid) is None
    assert services.profile_sources._store.signals_for_candidate(cid) == []
    assert services.report_store.for_candidate(cid) == []


@pytest.mark.parametrize("view", VIEWS)
def test_unrelated_lookup_failure_is_not_reported_as_erasure(services, monkeypatch, view):
    cid, headers = seed(services, "keep@example.in")
    owner, method = boundary(services, view, "loaded")

    def fail(*args, **kwargs):
        raise LookupError("synthetic unrelated lookup failure")

    monkeypatch.setattr(owner, method, fail)
    with _client(services) as client:
        assert client.get(path(view, cid), headers=headers).status_code == 500
    assert services.candidates.get_candidate(cid) is not None


@pytest.mark.parametrize("view", VIEWS)
def test_erasure_after_final_read_leaves_only_a_response_snapshot(services, monkeypatch, view):
    cid, headers = seed(services, "snapshot@example.in")
    owner, method = boundary(services, view, "loaded")
    actual = getattr(owner, method)
    get_candidate = services.candidates.get_candidate
    armed = False

    def loaded(*args, **kwargs):
        nonlocal armed
        result = actual(*args, **kwargs)
        armed = True
        return result

    def last_read(candidate_id):
        nonlocal armed
        result = get_candidate(candidate_id)
        if armed and candidate_id == cid:
            armed = False
            assert services.portal.erase(cid)["deleted"]
        return result

    monkeypatch.setattr(owner, method, loaded)
    monkeypatch.setattr(services.candidates, "get_candidate", last_read)
    with _client(services) as client:
        response = client.get(path(view, cid), headers=headers)
        assert response.status_code == 200
        assert response.json()
        assert get_candidate(cid) is None
        assert client.get("/portal/me", headers=headers).status_code == 401


@pytest.mark.parametrize("door", ["portal", "admin"])
@pytest.mark.parametrize("intervening", ["insert", "delete"])
def test_erasure_report_receipt_counts_predelete_snapshot(services, monkeypatch, door, intervening):
    """The receipt can differ from rows swept without weakening cascade erasure."""
    cid, headers = seed(services, "count-snapshot@example.in")
    keeper, _ = seed(services, "count-keeper@example.in")
    actual = services.report_store.for_candidate
    at_delete = []

    def counted(candidate_id):
        rows = actual(candidate_id)
        if candidate_id == cid:
            if intervening == "insert":
                services.report_store.save(_report(candidate_id=cid))
            else:
                assert services.report_store.delete(rows[0].id)
            at_delete.append(len(actual(cid)))
        return rows

    monkeypatch.setattr(services.report_store, "for_candidate", counted)
    with _client(services) as client:
        endpoint = "/portal/me" if door == "portal" else f"/candidates/{cid}"
        response = client.delete(endpoint, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"candidate_id": cid, "deleted": True, "reports_deleted": 1}
    assert at_delete == [2 if intervening == "insert" else 0]
    assert services.candidates.get_candidate(cid) is None
    assert actual(cid) == []
    assert len(actual(keeper)) == 1
