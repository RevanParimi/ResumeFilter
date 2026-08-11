"""The published grievance mechanism (S8.3 Phase B, spec §9)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def tuned(settings):
    return settings.model_copy(update={
        "grievance_officer_name": "R. Menon",
        "grievance_officer_email": "dpo@example.com",
        "grievance_officer_phone": "+91 80 4000 0000",
        "grievance_response_days": 30,
    })


@pytest.fixture
def client(tuned):
    """NO admin header, deliberately: the whole claim under test is that this
    route needs no credential at all."""
    services = make_services(tuned)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_the_grievance_contact_is_readable_WITHOUT_a_credential(client):
    """DPDP requires the mechanism to be PUBLISHED. A contact reachable only
    after login is not reachable by the person whose complaint is that they
    cannot log in."""
    r = client.get("/grievance")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"name", "email", "phone", "response_days"}
    assert body["email"] == "dpo@example.com"
    assert body["response_days"] == 30


def test_grievance_is_in_the_NAMED_public_set(client):
    """Widening PUBLIC_PATHS is the reviewable act it is meant to be. This
    asserts the route is public by being IN THE LIST, not by happening to
    answer 200 -- which a missing gate would also do."""
    from app.api.routes import PUBLIC_PATHS

    assert "/grievance" in PUBLIC_PATHS


def test_the_contact_carries_no_credential_and_no_internals(client):
    """A public route on a fraud platform is a surface. Four fields, all of
    them things we chose to publish."""
    body = client.get("/grievance").json()
    assert all(isinstance(v, (str, int)) for v in body.values())


def test_the_contact_is_echoed_in_the_portal_in_context(tuned):
    """So a candidate reading their own data sees who to complain to WITHOUT
    having to know a separate route exists."""
    services = make_services(tuned)
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers={"X-API-Key": "test-admin-key"}) as c:
        cid = c.post("/candidates", json={
            "resume_text": "Asha R\nEmail: g@e.com\nSKILLS\nPython\n",
            "evaluate": False,
        }).json()["candidate_id"]
        key = c.post(f"/candidates/{cid}/auth-key").json()["access_key"]
        me = c.get("/portal/me", headers={"X-Candidate-Key": key}).json()
        assert me["grievance"]["email"] == "dpo@example.com"
        assert me["grievance"]["response_days"] == 30


def test_an_unconfigured_contact_answers_blanks_rather_than_500(settings):
    """Locally the officer is unset, and the route must still be honest rather
    than crash. Prod cannot reach this state -- boot refuses (test_boot_config)."""
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        body = c.get("/grievance").json()
        assert body["email"] == ""
        assert body["response_days"] >= 1
