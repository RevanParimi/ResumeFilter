"""Candidates api regressions, grouped by behavior."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.candidates.store import CandidateStore
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


# Candidates api

RESUME = """Asha Rao
Email: asha.rao@example.com | Phone: +91 98765 43210

EXPERIENCE
- Senior ML Engineer, Acme AI (2021 - Present)
- Fine-tuned transformer models and built production RAG pipelines.

SKILLS
Python, PyTorch, LangChain
"""


@pytest.fixture
def api(settings, flywheel):
    """TestClient wired to fully offline services (NullLLM, in-memory stores)."""
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services


def test_services_bundle_has_working_candidate_store(services):
    assert isinstance(services.candidates, CandidateStore)
    # Live schema behind it (create_all in the test fake), not a stub.
    assert services.candidates.get_candidate("no-such-id") is None


def test_create_candidate_ingests_and_links_report(api):
    client, services = api
    resp = client.post("/candidates", json={"resume_text": RESUME})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidate_id"] and body["resume_id"]
    assert body["resume_version"] == 1
    assert body["matched_existing"] is False
    assert body["extraction_method"] == "heuristic"  # NullLLM abstains offline
    # Auto depth-eval ran, stayed advisory, and is linked to the candidate.
    assert body["report"] is not None
    assert body["report"]["candidate_id"] == body["candidate_id"]
    assert body["report"]["advisory"] is True
    assert body["report"]["human_review_required"] is True
    # Persisted through BOTH stores, not just echoed on the wire.
    assert services.candidates.get_candidate(body["candidate_id"]) is not None
    stored = services.report_store.get(body["report"]["id"])
    assert stored is not None and stored.candidate_id == body["candidate_id"]


def test_linked_report_retrievable_via_report_endpoint(api):
    client, _ = api
    body = client.post("/candidates", json={"resume_text": RESUME}).json()
    got = client.get(f"/report/{body['report']['id']}")
    assert got.status_code == 200
    assert got.json()["candidate_id"] == body["candidate_id"]


def test_same_text_is_duplicate_resume_same_candidate(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    again = client.post("/candidates", json={"resume_text": RESUME}).json()
    assert again["candidate_id"] == first["candidate_id"]
    assert again["duplicate_resume"] is True
    assert again["resume_version"] == 1


def test_updated_text_matches_identity_as_new_version(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    second = client.post(
        "/candidates", json={"resume_text": RESUME + "\n- AWS certified (2026)."}
    ).json()
    assert second["candidate_id"] == first["candidate_id"]
    assert second["matched_existing"] is True
    assert second["matched_on"] == "email_hash"
    assert second["resume_version"] == 2


def test_evaluate_false_skips_depth_eval(api):
    client, services = api
    body = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()
    assert body["report"] is None
    assert services.report_store.for_candidate(body["candidate_id"]) == []
    # Ingestion still happened.
    assert services.candidates.get_candidate(body["candidate_id"]) is not None


def test_candidates_oversize_resume_422(api):
    client, services = api
    too_big = "x" * (services.settings.max_resume_chars + 1)
    resp = client.post("/candidates", json={"resume_text": too_big})
    assert resp.status_code == 422
    assert "max_resume_chars" in resp.text


def test_candidates_unknown_domain_422(api):
    client, _ = api
    resp = client.post(
        "/candidates", json={"resume_text": RESUME, "domain": "astrology"}
    )
    assert resp.status_code == 422
    assert "genai" in resp.text


def test_candidates_requires_a_source_422(api):
    client, _ = api
    assert client.post("/candidates", json={}).status_code == 422


def test_candidate_detail_includes_latest_profile(api):
    client, _ = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]
    resp = client.get(f"/candidates/{cid}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == cid
    assert detail["resume_count"] == 1
    assert detail["email_hash"]
    assert detail["latest_profile"] is not None
    assert detail["latest_profile"]["contact"]["email_hash"] == detail["email_hash"]


def test_candidate_detail_404(api):
    client, _ = api
    assert client.get("/candidates/no-such-id").status_code == 404


def test_list_candidate_resumes(api):
    client, _ = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]
    client.post(
        "/candidates",
        json={"resume_text": RESUME + "\n- New project shipped.", "evaluate": False},
    )
    resp = client.get(f"/candidates/{cid}/resumes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_id"] == cid
    assert [r["version"] for r in body["resumes"]] == [1, 2]
    assert client.get("/candidates/no-such-id/resumes").status_code == 404


def test_list_candidate_reports(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid = first["candidate_id"]
    resp = client.get(f"/candidates/{cid}/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) == 1
    assert reports[0]["id"] == first["report"]["id"]
    assert reports[0]["candidate_id"] == cid
    assert client.get("/candidates/no-such-id/reports").status_code == 404


RESUME_B = """Ravi Kumar
Email: ravi.kumar@example.com

SKILLS
Java, Spring
"""


def test_delete_candidate_erases_store_and_reports(api):
    client, services = api
    body = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid, report_id = body["candidate_id"], body["report"]["id"]

    resp = client.delete(f"/candidates/{cid}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["deleted"] is True
    assert payload["reports_deleted"] == 1
    # Everything derived from the resume is gone (DPDP erasure).
    assert client.get(f"/candidates/{cid}").status_code == 404
    assert client.get(f"/report/{report_id}").status_code == 404
    assert services.candidates.get_candidate(cid) is None


def test_delete_missing_candidate_404(api):
    client, _ = api
    assert client.delete("/candidates/no-such-id").status_code == 404


def test_delete_one_resume_keeps_candidate(api):
    client, _ = api
    client.post("/candidates", json={"resume_text": RESUME, "evaluate": False})
    second = client.post(
        "/candidates",
        json={"resume_text": RESUME + "\n- Extra line.", "evaluate": False},
    ).json()
    cid = second["candidate_id"]

    resp = client.delete(f"/candidates/{cid}/resumes/{second['resume_id']}")
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    versions = [
        r["version"] for r in client.get(f"/candidates/{cid}/resumes").json()["resumes"]
    ]
    assert versions == [1]
    assert client.get(f"/candidates/{cid}").status_code == 200


def test_delete_resume_of_another_candidate_404(api):
    client, _ = api
    a = client.post("/candidates", json={"resume_text": RESUME, "evaluate": False}).json()
    b = client.post("/candidates", json={"resume_text": RESUME_B, "evaluate": False}).json()
    assert a["candidate_id"] != b["candidate_id"]  # distinct contacts ⇒ distinct people
    # A's resume under B's candidate id must not delete anything.
    resp = client.delete(f"/candidates/{b['candidate_id']}/resumes/{a['resume_id']}")
    assert resp.status_code == 404
    assert client.get(f"/candidates/{a['candidate_id']}/resumes").json()["resumes"] != []


def test_report_not_persisted_if_candidate_erased_during_eval(api):
    """DPDP: a depth-eval racing a candidate erasure must not leave a report."""
    client, services = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]

    real_engine = client.app.state.engine

    class EraseMidEval:
        async def evaluate(self, **kwargs):
            report = await real_engine.evaluate(**kwargs)
            services.candidates.delete_candidate(cid)  # erasure lands mid-flight
            return report

    client.app.state.engine = EraseMidEval()
    response = client.post("/candidates", json={"resume_text": RESUME})
    assert response.status_code == 422
    assert response.json() == {"detail": "candidate_erased"}
    assert services.report_store.for_candidate(cid) == []


# Candidate auth api

@pytest.fixture
def _client(settings):
    # NOTE: this repo's installed Starlette/FastAPI only runs the app's
    # lifespan (which sets app.state.services) when the TestClient is used as
    # a context manager (see every other tests/test_*_api.py `with _client(...)
    # as client:` fixture). We keep the brief's tuple-return shape but do the
    # entering via a pytest fixture wrapping a `with` block, so every route in
    # this file — including the ones Task 9 still owes — resolves
    # `_services(request)` correctly, AND the lifespan shutdown (closing the
    # background portal thread) runs on fixture teardown even if the test
    # body raises.
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services


def _make_candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text": "Dev\nEmail: d@e.com\nSKILLS\nPython\n",
                                         "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_admin_mints_candidate_key_and_it_authenticates(_client):
    client, _ = _client
    cid = _make_candidate(client)
    r = client.post(f"/candidates/{cid}/auth-key")
    assert r.status_code == 200
    key = r.json()["access_key"]
    assert r.json()["candidate_id"] == cid and key
    # the key authenticates on a portal route
    ok = client.get("/portal/me", headers={"X-Candidate-Key": key})
    assert ok.status_code == 200


def test_mint_unknown_candidate_404(_client):
    client, _ = _client
    r = client.post("/candidates/nope/auth-key")
    assert r.status_code == 404


def test_portal_route_without_key_is_401(_client):
    client, _ = _client
    assert client.get("/portal/me").status_code == 401
    assert client.get("/portal/me", headers={"X-Candidate-Key": "bad"}).status_code == 401
