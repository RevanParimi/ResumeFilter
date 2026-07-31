from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ledger.schema import InterviewOutcome, InterviewStage
from tests.conftest import make_services


@pytest.fixture
def _setup(settings):
    # NOTE (mirrors tests/test_candidate_auth_api.py `_client`): a plain
    # TestClient does not run the app lifespan, so app.state.services is never
    # set and every request 500s. Enter via a pytest fixture wrapping a `with`
    # block so every route here resolves `_services(request)` correctly, AND
    # the lifespan shutdown (closing the background portal thread) runs on
    # fixture teardown even if the test body raises.
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as client:
        yield client, services


def _candidate_with_key(client, email="d@e.com"):
    # NOTE: candidate identity resolution (S1.1) matches on email_hash, so two
    # uploads sharing an email resolve to the SAME candidate_id (by design —
    # that's how resume-version dedup works). test_cross_candidate_isolation
    # needs two genuinely DISTINCT candidates, so it passes distinct emails;
    # every other caller keeps the brief's original single shared default.
    cid = client.post("/candidates", json={
        "resume_text": f"Dev\nEmail: {email}\nSKILLS\nPython\n", "evaluate": False,
    }).json()["candidate_id"]
    key = client.post(f"/candidates/{cid}/auth-key").json()["access_key"]
    return cid, {"X-Candidate-Key": key}


def test_portal_me_returns_access_view(_setup):
    client, _ = _setup
    cid, h = _candidate_with_key(client)
    r = client.get("/portal/me", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["candidate_id"] == cid
    assert len(body["resumes"]) == 1
    assert body["retention"]["sweep_active"] is False
    assert body["retention"]["windows"]  # posture present


def test_portal_access_log_shows_org_disclosure(_setup):
    client, services = _setup
    cid, h = _candidate_with_key(client)
    org = services.ledger.create_organization("Acme")
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_write", org_id=org.id)
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_read", org_id=org.id)
    services.ledger.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    services.ledger.query_records_for_org(org_id=org.id, candidate_id=cid)
    r = client.get("/portal/access-log", headers=h)
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()}
    assert "record.query" in actions and "record.submit" in actions
    q = next(e for e in r.json() if e["action"] == "record.query")
    assert q["actor_name"] == "Acme" and q["allowed"] is True


def test_portal_first_party_grant_then_revoke(_setup):
    client, _ = _setup
    cid, h = _candidate_with_key(client)
    g = client.post("/portal/consents", headers=h, json={"purpose": "ledger_read"})
    assert g.status_code == 200
    gid = g.json()["id"]
    assert client.get("/portal/consents", headers=h).status_code == 200
    rv = client.post(f"/portal/consents/{gid}/revoke", headers=h)
    assert rv.status_code == 200 and rv.json()["revoked"] is True
    # state now revoked
    states = {c["grant"]["id"]: c["state"] for c in client.get("/portal/consents", headers=h).json()}
    assert states[gid] == "revoked"


def test_grant_unknown_org_404(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    r = client.post("/portal/consents", headers=h, json={"purpose": "ledger_read", "org_id": "ghost"})
    assert r.status_code == 404


def test_cross_candidate_isolation(_setup):
    client, services = _setup
    a, ha = _candidate_with_key(client, email="a@e.com")
    b, hb = _candidate_with_key(client, email="b@e.com")
    assert a != b
    g_b = services.ledger.grant_consent(candidate_id=b, purpose="ledger_read")
    # A revoking B's grant → 404, B's grant untouched
    assert client.post(f"/portal/consents/{g_b.id}/revoke", headers=ha).status_code == 404
    assert services.ledger.get_grant(g_b.id).revoked_at is None
    # A's /portal/me never contains B
    assert client.get("/portal/me", headers=ha).json()["candidate_id"] == a


def test_self_erase_kills_the_key(_setup):
    client, _ = _setup
    cid, h = _candidate_with_key(client)
    d = client.delete("/portal/me", headers=h)
    assert d.status_code == 200 and d.json()["deleted"] is True
    # key no longer authenticates
    assert client.get("/portal/me", headers=h).status_code == 401
