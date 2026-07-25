"""S3.2 ledger HTTP surface — offline TestClient over injected in-memory stores."""

from __future__ import annotations

import asyncio
import pytest
from fastapi.testclient import TestClient

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.ledger.store import LedgerStore
from app.main import create_app
from tests.conftest import make_services

RESUME = """Asha Rao
Email: asha.rao@example.com | Phone: +91 98765 43210

EXPERIENCE
- Senior ML Engineer, Acme AI (2021 - Present)

SKILLS
Python, PyTorch
"""


async def _ingest_candidate(services, text=RESUME):
    result = await extract_profile(text, llm=services.llm, settings=services.settings)
    return services.candidates.ingest(result, text).candidate_id


def test_services_bundle_has_ledger_sharing_candidate_db(services):
    assert isinstance(services.ledger, LedgerStore)
    assert isinstance(services.candidates, CandidateStore)


@pytest.fixture
def api(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


def test_create_org_returns_one_time_key_and_lists_without_keys(api):
    client, _ = api
    resp = client.post("/ledger/orgs", json={"name": "Acme Talent"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["org"]["name"] == "Acme Talent" and body["org"]["status"] == "active"
    assert isinstance(body["api_key"], str) and body["api_key"]
    listed = client.get("/ledger/orgs").json()
    assert [o["name"] for o in listed] == ["Acme Talent"]
    assert "api_key" not in listed[0] and "api_key_hash" not in listed[0]


def test_create_org_duplicate_name_conflicts(api):
    client, _ = api
    client.post("/ledger/orgs", json={"name": "Dup Co"})
    assert client.post("/ledger/orgs", json={"name": "Dup Co"}).status_code == 409


def test_rotate_and_delete_org(api):
    client, _ = api
    org = client.post("/ledger/orgs", json={"name": "Rot Co"}).json()["org"]
    rotated = client.post(f"/ledger/orgs/{org['id']}/api-key")
    assert rotated.status_code == 200 and rotated.json()["api_key"]
    assert client.post("/ledger/orgs/no-such/api-key").status_code == 404
    assert client.delete(f"/ledger/orgs/{org['id']}").status_code == 200
    assert client.delete(f"/ledger/orgs/{org['id']}").status_code == 404


def test_org_endpoints_behind_admin_key(settings, flywheel):
    from pydantic import SecretStr
    locked = settings.model_copy(update={"api_auth_key": SecretStr("s3cret")})
    services = make_services(locked, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/ledger/orgs", json={"name": "X"}).status_code == 401
        ok = client.post("/ledger/orgs", json={"name": "X"}, headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200


def test_grant_revoke_and_status_consent(api):
    client, services = api
    cid = asyncio.run(_ingest_candidate(services))
    org = client.post("/ledger/orgs", json={"name": "Consent Co"}).json()["org"]

    granted = client.post(
        f"/ledger/candidates/{cid}/consent",
        json={"purpose": "ledger_read", "org_id": org["id"]},
    )
    assert granted.status_code == 200, granted.text
    grant = granted.json()
    assert grant["purpose"] == "ledger_read" and grant["org_id"] == org["id"]

    status = client.get(
        f"/ledger/candidates/{cid}/consent",
        params={"org_id": org["id"], "purpose": "ledger_read"},
    ).json()
    assert status["allowed"] is True and status["grant_id"] == grant["id"]

    revoked = client.post(f"/ledger/consent/{grant['id']}/revoke").json()
    assert revoked["revoked"] is True
    assert client.post(f"/ledger/consent/{grant['id']}/revoke").json()["revoked"] is False

    after = client.get(
        f"/ledger/candidates/{cid}/consent",
        params={"org_id": org["id"], "purpose": "ledger_read"},
    ).json()
    assert after["allowed"] is False


def test_consent_endpoints_404_on_unknown_candidate(api):
    client, _ = api
    org = client.post("/ledger/orgs", json={"name": "Ghost Co"}).json()["org"]
    assert client.post(
        "/ledger/candidates/nope/consent",
        json={"purpose": "ledger_read", "org_id": org["id"]},
    ).status_code == 404
    assert client.get(
        "/ledger/candidates/nope/consent",
        params={"org_id": org["id"], "purpose": "ledger_read"},
    ).status_code == 404


def _org_with_key(client):
    body = client.post("/ledger/orgs", json={"name": f"Org {id(client)}"}).json()
    return body["org"]["id"], body["api_key"]


def _setup_org_candidate(api, *, read=False):
    client, services = api
    cid = asyncio.run(_ingest_candidate(services))
    body = client.post("/ledger/orgs", json={"name": "Data Co"}).json()
    org_id, key = body["org"]["id"], body["api_key"]
    client.post(f"/ledger/candidates/{cid}/consent",
                json={"purpose": "ledger_write", "org_id": org_id})
    if read:
        client.post(f"/ledger/candidates/{cid}/consent",
                    json={"purpose": "ledger_read", "org_id": org_id})
    return client, cid, org_id, key


def test_submit_record_requires_valid_org_key(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    payload = {"candidate_id": cid, "stage": "tech", "outcome": "advanced",
               "interviewed_at": "2026-07-20T10:00:00+00:00"}
    assert client.post("/ledger/records", json=payload).status_code == 401
    assert client.post("/ledger/records", json=payload,
                       headers={"X-Org-Key": "wrong"}).status_code == 401
    ok = client.post("/ledger/records", json=payload, headers={"X-Org-Key": key})
    assert ok.status_code == 200, ok.text
    assert ok.json()["candidate_id"] == cid and ok.json()["consent_id"]


def test_submit_record_without_write_consent_is_403(api):
    client, services = api
    cid = asyncio.run(_ingest_candidate(services))
    _, key = _org_with_key(client)  # org exists but no consent granted
    payload = {"candidate_id": cid, "stage": "tech", "outcome": "advanced",
               "interviewed_at": "2026-07-20T10:00:00+00:00"}
    resp = client.post("/ledger/records", json=payload, headers={"X-Org-Key": key})
    assert resp.status_code == 403


def test_submit_record_unknown_candidate_is_404(api):
    client = api[0]
    _, key = _org_with_key(client)
    payload = {"candidate_id": "no-such", "stage": "tech", "outcome": "advanced",
               "interviewed_at": "2026-07-20T10:00:00+00:00"}
    assert client.post("/ledger/records", json=payload,
                       headers={"X-Org-Key": key}).status_code == 404


def test_append_event_ownership_enforced(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    rec = client.post(
        "/ledger/records",
        json={"candidate_id": cid, "stage": "tech", "outcome": "advanced",
              "interviewed_at": "2026-07-20T10:00:00+00:00"},
        headers={"X-Org-Key": key},
    ).json()
    ok = client.post(f"/ledger/records/{rec['id']}/events",
                     json={"event_type": "score", "payload": {"value": 4}},
                     headers={"X-Org-Key": key})
    assert ok.status_code == 200 and ok.json()["record_id"] == rec["id"]
    # A different org cannot append to this record.
    other = client.post("/ledger/orgs", json={"name": "Other Co"}).json()["api_key"]
    resp = client.post(f"/ledger/records/{rec['id']}/events",
                       json={"event_type": "score", "payload": {"value": 1}},
                       headers={"X-Org-Key": other})
    assert resp.status_code == 404


def test_query_records_requires_read_consent_and_audits(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    services = api[1]
    client.post(
        "/ledger/records",
        json={"candidate_id": cid, "stage": "tech", "outcome": "advanced",
              "interviewed_at": "2026-07-20T10:00:00+00:00"},
        headers={"X-Org-Key": key},
    )
    resp = client.get(f"/ledger/candidates/{cid}/records", headers={"X-Org-Key": key})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1 and resp.json()[0]["candidate_id"] == cid
    reads = [a for a in services.ledger.audit_for_candidate(cid) if a.action == "record.query"]
    assert reads and reads[-1].details["allowed"] is True


def test_query_records_denied_without_read_consent(api):
    # write consent only (read=False) → query is forbidden and audited denied.
    client, cid, org_id, key = _setup_org_candidate(api, read=False)
    services = api[1]
    resp = client.get(f"/ledger/candidates/{cid}/records", headers={"X-Org-Key": key})
    assert resp.status_code == 403
    reads = [a for a in services.ledger.audit_for_candidate(cid) if a.action == "record.query"]
    assert reads and reads[-1].details["allowed"] is False


def test_query_records_bad_key_and_unknown_candidate(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    assert client.get(f"/ledger/candidates/{cid}/records").status_code == 401
    assert client.get("/ledger/candidates/nope/records",
                      headers={"X-Org-Key": key}).status_code == 404


# ── S3.3 coding-round endpoints ──────────────────────────────────────────────


def _coding_payload(cid):
    return {
        "candidate_id": cid, "platform": "hackerrank", "score": 740.0,
        "max_score": 850.0, "percentile": 88.0,
        "problem_tags": ["arrays", "dynamic-programming"],
        "taken_at": "2026-07-24T10:00:00+00:00", "assessment_name": "SDE Screen",
        "raw": {"attempts": 1},
    }


def test_submit_coding_round_requires_valid_org_key(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    payload = _coding_payload(cid)
    assert client.post("/ledger/coding-rounds", json=payload).status_code == 401
    assert client.post("/ledger/coding-rounds", json=payload,
                       headers={"X-Org-Key": "wrong"}).status_code == 401
    ok = client.post("/ledger/coding-rounds", json=payload, headers={"X-Org-Key": key})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["candidate_id"] == cid and body["consent_id"]
    assert body["platform"] == "hackerrank" and body["percentile"] == 88.0
    assert body["problem_tags"] == ["arrays", "dynamic-programming"]


def test_submit_coding_round_without_write_consent_is_403(api):
    client, services = api
    cid = asyncio.run(_ingest_candidate(services))
    _, key = _org_with_key(client)  # org exists, no consent granted
    resp = client.post("/ledger/coding-rounds", json=_coding_payload(cid),
                       headers={"X-Org-Key": key})
    assert resp.status_code == 403


def test_submit_coding_round_unknown_candidate_is_404(api):
    client = api[0]
    _, key = _org_with_key(client)
    payload = _coding_payload("no-such")
    assert client.post("/ledger/coding-rounds", json=payload,
                       headers={"X-Org-Key": key}).status_code == 404


def test_submit_coding_round_rejects_bad_percentile(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    payload = _coding_payload(cid)
    payload["percentile"] = 150  # out of range → 422 validation error
    assert client.post("/ledger/coding-rounds", json=payload,
                       headers={"X-Org-Key": key}).status_code == 422


def test_query_coding_rounds_requires_read_consent_and_audits(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    services = api[1]
    client.post("/ledger/coding-rounds", json=_coding_payload(cid),
                headers={"X-Org-Key": key})
    resp = client.get(f"/ledger/candidates/{cid}/coding-rounds",
                      headers={"X-Org-Key": key})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1 and resp.json()[0]["candidate_id"] == cid
    reads = [a for a in services.ledger.audit_for_candidate(cid)
             if a.action == "coding_round.query"]
    assert reads and reads[-1].details["allowed"] is True


def test_query_coding_rounds_denied_without_read_consent(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=False)  # write only
    services = api[1]
    resp = client.get(f"/ledger/candidates/{cid}/coding-rounds",
                      headers={"X-Org-Key": key})
    assert resp.status_code == 403
    reads = [a for a in services.ledger.audit_for_candidate(cid)
             if a.action == "coding_round.query"]
    assert reads and reads[-1].details["allowed"] is False


def test_query_coding_rounds_bad_key_and_unknown_candidate(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    assert client.get(f"/ledger/candidates/{cid}/coding-rounds").status_code == 401
    assert client.get("/ledger/candidates/nope/coding-rounds",
                      headers={"X-Org-Key": key}).status_code == 404
