"""S3.2 ledger HTTP surface — offline TestClient over injected in-memory stores."""

from __future__ import annotations

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
