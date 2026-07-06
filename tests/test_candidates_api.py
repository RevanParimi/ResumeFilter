"""Candidate API surface (S1.3) — offline: NullLLM ⇒ heuristic extraction,
rule-driven depth-eval. TestClient over injected in-memory services."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.candidates.store import CandidateStore
from app.main import create_app
from tests.conftest import make_services

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
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


# ── services wiring ───────────────────────────────────────────────────────────
def test_services_bundle_has_working_candidate_store(services):
    assert isinstance(services.candidates, CandidateStore)
    # Live schema behind it (create_all in the test fake), not a stub.
    assert services.candidates.get_candidate("no-such-id") is None


# ── POST /candidates ──────────────────────────────────────────────────────────
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
