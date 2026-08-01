"""S5.2 comp endpoints: /comp/estimate, /ledger/offers, /jobs/{id}/comp (org plane)."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult, SkillItem,
)
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from app.ledger.schema import ConsentPurpose

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        yield c


def _org_key(services, name="Acme"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _candidate(services, name="Ann", email="ann@x.io"):
    saved = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value=name),
                contact=ContactInfo(email=ExtractedStr(value=email)),
                skills=[SkillItem(name="python", canonical="python")],
            ),
            method="heuristic",
        ),
        resume_text=email,
    )
    return saved.candidate_id


def test_estimate_static_only(services):
    _, key = _org_key(services)
    with _client(services) as c:
        resp = c.post("/comp/estimate", headers={"X-Org-Key": key},
                      json={"title": "Senior Backend Engineer", "years_experience": 7})
        assert resp.status_code == 200
        body = resp.json()
        assert body["advisory"] is True
        assert body["sources"] == ["static"]
        assert body["role_family"] == "backend_engineer"
        assert body["p25"] < body["p50"] < body["p75"]


def test_estimate_requires_org_key(services):
    with _client(services) as c:
        assert c.post("/comp/estimate", json={"title": "BE"}).status_code == 401


def test_submit_offer_requires_consent_then_succeeds(services):
    org_id, key = _org_key(services)
    cand_id = _candidate(services)
    payload = {
        "candidate_id": cand_id, "role_family": "backend_engineer",
        "seniority": "senior", "city_tier": "metro",
        "ctc_fixed": 2500000, "offered_at": NOW_ISO,
    }
    with _client(services) as c:
        r1 = c.post("/ledger/offers", headers={"X-Org-Key": key}, json=payload)
        assert r1.status_code == 403  # no ledger_write grant yet
        services.ledger.grant_consent(
            candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org_id,
            expires_at=NOW + timedelta(days=90),
        )
        r2 = c.post("/ledger/offers", headers={"X-Org-Key": key}, json=payload)
        assert r2.status_code == 200
        assert r2.json()["ctc_fixed"] == 2500000


def test_submit_offer_invalid_role_family_400(services):
    org_id, key = _org_key(services)
    cand_id = _candidate(services)
    services.ledger.grant_consent(
        candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org_id,
        expires_at=NOW + timedelta(days=90),
    )
    payload = {
        "candidate_id": cand_id, "role_family": "astronaut",
        "seniority": "senior", "city_tier": "metro", "ctc_fixed": 1, "offered_at": NOW_ISO,
    }
    with _client(services) as c:
        assert c.post("/ledger/offers", headers={"X-Org-Key": key}, json=payload).status_code == 400


def test_benchmark_cross_org_404_and_owned_ok(services):
    org_id, key = _org_key(services, "A")
    org_b = services.ledger.create_organization("B")
    key_b = services.ledger.issue_api_key(org_b.id)
    with _client(services) as c:
        req = c.post("/jobs", headers={"X-Org-Key": key}, json={
            "title": "Senior Backend Engineer", "must_have_skills": ["python"],
            "min_years_experience": 7, "location_tiers": ["metro"],
            "comp_band": {"ctc_min": 800000, "ctc_max": 900000},
        }).json()
        resp = c.get(f"/jobs/{req['id']}/comp", headers={"X-Org-Key": key})
        assert resp.status_code == 200
        body = resp.json()
        assert body["advisory"] is True
        assert body["position"] in {"below", "at", "above"}
        # a different org cannot benchmark it
        assert c.get(f"/jobs/{req['id']}/comp", headers={"X-Org-Key": key_b}).status_code == 404
