"""S8.4 Phase A: the org-plane wedge routes. Two agencies, one candidate."""

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


def _key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_org_can_upload_and_read_its_own_report(services, genuine_resume):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        assert up.status_code == 200, up.text
        body = up.json()
        report_id = body["report"]["id"]

        got = c.get(f"/screening/reports/{report_id}", headers={"X-Org-Key": key})
        assert got.status_code == 200
        assert got.json()["id"] == report_id


def test_another_orgs_report_is_404_not_403(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        report_id = up.json()["report"]["id"]

        theirs = c.get(f"/screening/reports/{report_id}", headers={"X-Org-Key": key_b})
        absent = c.get("/screening/reports/does-not-exist", headers={"X-Org-Key": key_b})

        assert theirs.status_code == 404
        assert absent.status_code == 404
        assert theirs.json() == absent.json(), (
            "a 403 -- or a different body -- would confirm the report exists"
        )


def test_screening_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/reports/x").status_code == 401
        assert c.post("/screening/candidates", json={}).status_code == 401


def test_reports_for_a_candidate_are_scoped_to_the_caller(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        cand = up.json()["candidate_id"]

        mine = c.get(f"/screening/candidates/{cand}/reports", headers={"X-Org-Key": key_a})
        theirs = c.get(f"/screening/candidates/{cand}/reports", headers={"X-Org-Key": key_b})

        assert mine.status_code == 200 and len(mine.json()) == 1
        assert theirs.status_code == 200 and theirs.json() == [], (
            "an empty list, not a 404: 'I have no reports on them' is not "
            "'they do not exist'"
        )


def test_the_org_report_is_redacted_but_complete(services, farm_resume_a, farm_resume_b):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        c.post("/screening/candidates", headers={"X-Org-Key": key},
               json={"resume_text": farm_resume_a, "domain": "genai"})
        second = c.post("/screening/candidates", headers={"X-Org-Key": key},
                        json={"resume_text": farm_resume_b, "domain": "genai"})
        report_id = second.json()["report"]["id"]

        body = c.get(f"/screening/reports/{report_id}",
                     headers={"X-Org-Key": key}).json()
        for m in body["resume_farm"]["matches"]:
            assert m["candidate_id"] is None and m["resume_id"] is None
            assert m["similarity"] > 0
        # The org still gets the full report.
        assert "verdicts" in body and "fabrication_risk" in body


def test_admin_upload_stays_unowned_and_invisible_to_orgs(services, genuine_resume,
                                                          admin_headers):
    org_id, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/candidates", headers=admin_headers,
                    json={"resume_text": genuine_resume, "domain": "genai"})
        report_id = up.json()["report"]["id"]

        assert c.get(f"/report/{report_id}", headers=admin_headers).status_code == 200
        assert c.get(f"/screening/reports/{report_id}",
                     headers={"X-Org-Key": key}).status_code == 404
