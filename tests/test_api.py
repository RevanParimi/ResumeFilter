"""API surface tests — TestClient over injected offline services (FR-6..FR-15)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services

RESUME = (
    "- Fine-tuned GPT-4 to improve accuracy.\n"
    "- Built production RAG at scale for support tickets.\n"
)


@pytest.fixture
def api(settings, flywheel):
    """TestClient wired to fully offline services (NullLLM, in-memory stores)."""
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


def _evaluate(client) -> dict:
    resp = client.post("/evaluate", json={"resume_text": RESUME})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── persistence (FR-6) ────────────────────────────────────────────────────────
def test_evaluate_then_get_report(api):
    client, services = api
    report = _evaluate(client)
    assert report["advisory"] is True and report["human_review_required"] is True

    got = client.get(f"/report/{report['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == report["id"]
    # Persisted through the store, not a per-process dict.
    assert services.report_store.get(report["id"]) is not None


def test_get_missing_report_404(api):
    client, _ = api
    assert client.get("/report/rep_nope").status_code == 404


# ── outcome loop (FR-7, FR-8) ─────────────────────────────────────────────────
def test_report_level_outcome_recorded_and_fed_to_flywheel(api):
    client, services = api
    report = _evaluate(client)

    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "inconclusive", "notes": "screen pending"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report_id"] == report["id"]
    assert body["claim_id"] is None
    assert body["outcome"] == "inconclusive"

    wheel_outcomes = [
        r for r in services.flywheel.records if r.get("record_type") == "outcome"
    ]
    assert len(wheel_outcomes) == 1
    assert wheel_outcomes[0]["report_id"] == report["id"]


def test_claim_level_outcome(api):
    client, _ = api
    report = _evaluate(client)
    claim_id = report["verdicts"][0]["claim_id"]

    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "verified_fabricated", "claim_id": claim_id},
    )
    assert resp.status_code == 200
    assert resp.json()["claim_id"] == claim_id

    outs = client.get(f"/report/{report['id']}/outcomes")
    assert outs.status_code == 200
    listed = outs.json()["outcomes"]
    assert len(listed) == 1 and listed[0]["outcome"] == "verified_fabricated"


def test_outcome_unknown_claim_422(api):
    client, _ = api
    report = _evaluate(client)
    resp = client.post(
        f"/report/{report['id']}/outcome",
        json={"outcome": "verified_genuine", "claim_id": "clm_not_there"},
    )
    assert resp.status_code == 422


def test_outcome_unknown_report_404(api):
    client, _ = api
    resp = client.post(
        "/report/rep_nope/outcome", json={"outcome": "verified_genuine"}
    )
    assert resp.status_code == 404
