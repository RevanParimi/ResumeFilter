"""S8.4 Phase B: materialization gets an HTTP route, and an empty feature store
stops being the client's fault.

Before this, `app/features/materialize.py` was reachable only from Python, so a
self-registered org's board 422'd PERMANENTLY -- there was no call it could make
to fix it.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _org_key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_an_empty_feature_store_gives_200_with_a_reason_not_422(services):
    """Both former 422 sites, in one test, because fixing one and leaving the
    other is this repo's signature defect."""
    _, key = _org_key(services)
    with _client(services) as c:
        job = c.post("/jobs", headers={"X-Org-Key": key}, json={
            "title": "Senior Engineer", "must_have_skills": ["python"],
        })
        assert job.status_code == 200, job.text
        req_id = job.json()["id"]

        match = c.post(f"/jobs/{req_id}/match", headers={"X-Org-Key": key}, json={})
        assert match.status_code == 200
        assert match.json()["pool_size"] == 0
        assert match.json()["ranked"] == []
        assert match.json()["reason"] == "no_materialized_candidates"

        board = c.get(f"/jobs/{req_id}/board", headers={"X-Org-Key": key})
        assert board.status_code == 200
        assert board.json()["match"]["reason"] == "no_materialized_candidates"


def test_materialize_route_fills_the_pool(services, genuine_resume):
    with _client(services) as c:
        up = c.post("/candidates", json={"resume_text": genuine_resume, "domain": "genai"})
        assert up.status_code == 200

        run = c.post("/features/materialize", json={})
        assert run.status_code == 200, run.text
        assert run.json()["materialized"] >= 1

    _, key = _org_key(services)
    with _client(services) as c:
        req_id = c.post("/jobs", headers={"X-Org-Key": key},
                        json={"title": "Senior Engineer",
                              "must_have_skills": ["python"]}).json()["id"]
        match = c.post(f"/jobs/{req_id}/match", headers={"X-Org-Key": key}, json={})
        assert match.json()["pool_size"] >= 1
        assert match.json()["reason"] is None, "a successful match states no reason"


def test_materialize_accepts_an_explicit_candidate_list(services, genuine_resume):
    with _client(services) as c:
        cid = c.post("/candidates",
                     json={"resume_text": genuine_resume, "domain": "genai"}).json()["candidate_id"]
        run = c.post("/features/materialize", json={"candidate_ids": [cid]})
        assert run.json()["materialized"] == 1

        unknown = c.post("/features/materialize", json={"candidate_ids": ["nope"]})
        assert unknown.status_code == 200
        assert unknown.json()["materialized"] == 0 and unknown.json()["skipped"] == 1


def test_an_unknown_view_name_is_refused_not_echoed(services):
    """The route accepted any view_name, materialized the DEFAULT view anyway,
    and echoed the caller's name back -- a response that says it did something
    it did not do."""
    with _client(services) as c:
        r = c.post("/features/materialize", json={"view_name": "not_a_view"})
        assert r.status_code == 422
        assert "not_a_view" in str(r.json()["detail"])

        ok = c.post("/features/materialize",
                    json={"view_name": services.settings.feat_default_view})
        assert ok.status_code == 200
        assert ok.json()["view_name"] == services.settings.feat_default_view


def test_materialize_is_admin_only(services):
    _, key = _org_key(services)
    with _client(services) as c:
        assert c.post("/features/materialize", json={},
                      headers={"X-Org-Key": key, "X-API-Key": "wrong"}).status_code == 401
