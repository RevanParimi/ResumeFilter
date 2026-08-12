"""The candidate plane files corrections and grievances (S8.3 Phase B)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


@pytest.fixture
def _setup(settings):
    # A plain TestClient does not run the app lifespan, so app.state.services
    # is never set and every request 500s -- enter through a `with` block, the
    # tests/test_portal_api.py pattern.
    services = make_services(settings)
    with TestClient(
        create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS
    ) as client:
        yield client, services


def _candidate_with_key(client, email="d@e.com"):
    cid = client.post("/candidates", json={
        "resume_text": f"Asha R\nEmail: {email}\nSKILLS\nPython\n", "evaluate": False,
    }).json()["candidate_id"]
    key = client.post(f"/candidates/{cid}/auth-key").json()["access_key"]
    return cid, {"X-Candidate-Key": key}


def _anon(client):
    """A client carrying NO admin header -- the fixture above sets one app-wide,
    which would otherwise make an unauthenticated assertion untestable."""
    return client


def test_every_request_route_needs_a_candidate_credential(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        assert c.post("/portal/corrections", json={}).status_code == 401
        assert c.post("/portal/grievances", json={}).status_code == 401
        assert c.get("/portal/requests").status_code == 401


def test_a_correction_round_trips(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/corrections", headers=h,
                    json={"field": "full_name", "requested_value": "Asha Rao"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open" and body["applied"] is False
    assert body["kind"] == "correction"

    listed = client.get("/portal/requests", headers=h).json()
    assert [x["id"] for x in listed] == [body["id"]]


def test_a_grievance_round_trips(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/grievances", headers=h,
                    json={"note": "nobody answered my correction"})
    assert r.status_code == 200
    assert r.json()["kind"] == "grievance"
    assert r.json()["field"] is None


def test_a_refused_submission_is_422_and_says_why(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/corrections", headers=h,
                    json={"field": "full_name", "requested_value": "   "})
    assert r.status_code == 422
    assert r.json()["detail"]


def test_an_unknown_field_is_refused_by_the_MODEL(_setup):
    """CorrectionField is an enum on the request body, so a field nobody
    implemented is a 422 from FastAPI before any handler runs."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/corrections", headers=h,
                    json={"field": "risk_score", "requested_value": "0"})
    assert r.status_code == 422


def test_the_submission_appears_in_the_candidates_own_access_log(_setup):
    """S3.1's rule -- surveillance is itself observable -- applied to the
    handling of the subject's own complaint, which is where it matters most."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    client.post("/portal/grievances", headers=h, json={"note": "nobody answered"})
    log = client.get("/portal/access-log", headers=h).json()
    assert any(e["entity_type"] == "data_principal_request" for e in log)


def test_a_candidate_never_sees_another_candidates_requests(_setup):
    client, _ = _setup
    _, mine = _candidate_with_key(client, email="one@e.com")
    _, theirs = _candidate_with_key(client, email="two@e.com")
    client.post("/portal/grievances", headers=mine, json={"note": "mine"})
    assert client.get("/portal/requests", headers=theirs).json() == []


def test_the_route_returns_429_when_the_budget_is_spent(_setup):
    client, services = _setup
    _, h = _candidate_with_key(client)
    limit = services.settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        assert client.post("/portal/grievances", headers=h,
                           json={"note": f"n{i}"}).status_code == 200
    over = client.post("/portal/grievances", headers=h, json={"note": "over"})
    assert over.status_code == 429
    assert over.headers["Retry-After"]
    assert over.json()["detail"] == "rate_limited"


def test_my_data_carries_the_subjects_own_requests(_setup):
    """The DPDP access view is everything the platform holds about the person
    that the portal surfaces. A complaint they filed is squarely that -- and a
    mechanism whose state they cannot see is not a mechanism."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    client.post("/portal/grievances", headers=h, json={"note": "nobody answered"})
    me = client.get("/portal/me", headers=h).json()
    assert [r["note"] for r in me["requests"]] == ["nobody answered"]


def test_my_data_has_no_requests_when_none_were_filed(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    assert client.get("/portal/me", headers=h).json()["requests"] == []
