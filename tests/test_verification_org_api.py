"""S7.1 org + admin planes: disclosure is consent-gated; review is operator-only."""

import pytest
from fastapi.testclient import TestClient

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.main import create_app
from app.verification.schema import VerificationMethod
from tests.conftest import make_services


@pytest.fixture
def client(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c, services


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def _org(services):
    org = services.ledger.create_organization("Acme Corp")
    return org.id, services.ledger.issue_api_key(org.id)


def test_org_read_requires_an_org_key(client):
    c, services = client
    cid = _candidate(services)
    assert c.get(f"/verification/candidates/{cid}/assurance").status_code == 401


def test_org_read_without_consent_is_403(client):
    c, services = client
    cid = _candidate(services)
    _, org_key = _org(services)
    r = c.get(
        f"/verification/candidates/{cid}/assurance", headers={"X-Org-Key": org_key}
    )
    assert r.status_code == 403


def test_org_read_with_verification_read_consent_is_200(client):
    c, services = client
    cid = _candidate(services)
    org_id, org_key = _org(services)
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    services.ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    r = c.get(
        f"/verification/candidates/{cid}/assurance", headers={"X-Org-Key": org_key}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == 1
    assert body["advisory"] is True
    # The aggregate must not re-leak per-attempt evidence.
    assert "evidence_digest" not in body
    assert "destination_hash" not in body


def test_org_read_of_an_unknown_candidate_is_404(client):
    c, services = client
    _, org_key = _org(services)
    r = c.get(
        "/verification/candidates/nope/assurance", headers={"X-Org-Key": org_key}
    )
    assert r.status_code == 404


def test_admin_manual_review_records_a_reviewed_outcome(client):
    c, services = client
    cid = _candidate(services)
    r = c.post(
        f"/candidates/{cid}/verifications/manual-review",
        json={"outcome": "verified", "note": "passport seen in person"},
    )
    assert r.status_code == 200
    assert r.json()["assurance_level"] == 3  # REVIEWED
    assert services.verification.assurance_for_candidate(cid).level == 3


def test_admin_manual_review_of_an_unknown_candidate_is_404(client):
    c, _ = client
    r = c.post(
        "/candidates/nope/verifications/manual-review", json={"outcome": "verified"}
    )
    assert r.status_code == 404


def test_admin_manual_review_rejects_a_bad_outcome(client):
    c, services = client
    cid = _candidate(services)
    r = c.post(
        f"/candidates/{cid}/verifications/manual-review", json={"outcome": "maybe"}
    )
    assert r.status_code == 422
