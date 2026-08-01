"""API surface tests — TestClient over injected offline services (FR-6..FR-15)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services

RESUME = (
    "- Fine-tuned GPT-4 to improve accuracy.\n"
    "- Built production RAG at scale for support tickets.\n"
)


@pytest.fixture
def api(settings, flywheel):
    """TestClient wired to fully offline services (NullLLM, in-memory stores)."""
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
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


# ── hardening (FR-11..FR-15) ──────────────────────────────────────────────────
def test_oversize_resume_text_422(api):
    client, services = api
    too_big = "x" * (services.settings.max_resume_chars + 1)
    resp = client.post("/evaluate", json={"resume_text": too_big})
    assert resp.status_code == 422
    assert "max_resume_chars" in resp.text


def test_oversize_pdf_b64_422(api):
    client, services = api
    too_big = "A" * (services.settings.max_pdf_b64_chars + 1)
    resp = client.post("/evaluate", json={"resume_pdf_b64": too_big})
    assert resp.status_code == 422
    assert "max_pdf_b64_chars" in resp.text


def test_unknown_domain_422_lists_registered(api):
    client, _ = api
    resp = client.post(
        "/evaluate", json={"resume_text": RESUME, "domain": "astrology"}
    )
    assert resp.status_code == 422
    assert "genai" in resp.text


def test_request_id_generated_and_echoed(api):
    client, _ = api
    generated = client.get("/healthz")
    assert generated.headers.get("x-request-id", "").startswith("req_")

    echoed = client.get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
    assert echoed.headers["x-request-id"] == "trace-abc-123"


def test_healthz_payload(api):
    client, _ = api
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "null"  # offline fixture has no key
    assert "genai" in body["domains"]
    assert body["version"] and body["env"] == "local"


def test_domains_endpoint(api):
    client, _ = api
    body = client.get("/domains").json()
    keys = {d["key"] for d in body}
    assert "genai" in keys
    genai = next(d for d in body if d["key"] == "genai")
    assert genai["display_name"] and "fine_tuning" in genai["claim_types"]


def test_auth_enforced_when_key_configured(settings, flywheel):
    from pydantic import SecretStr

    locked = settings.model_copy(update={"api_auth_key": SecretStr("s3cret")})
    services = make_services(locked, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/evaluate", json={"resume_text": RESUME}).status_code == 401
        assert client.get("/report/rep_x").status_code == 401
        # healthz and root stay open for probes/humans.
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 200
        ok = client.post(
            "/evaluate", json={"resume_text": RESUME}, headers={"X-API-Key": "s3cret"}
        )
        assert ok.status_code == 200


def test_auth_refuses_when_no_key_is_sent(api):
    """S8.1: this was `test_auth_open_by_default`, and it was the test PINNING
    the fail-open defect in place. The suite now runs with a configured admin
    key, and a client that sends none is refused."""
    client, _ = api
    bare = TestClient(client.app, raise_server_exceptions=False)
    with bare:
        assert bare.post("/evaluate", json={"resume_text": RESUME}).status_code == 401


def test_unhandled_error_returns_generic_500(api):
    client, _ = api

    class Boom:
        async def evaluate(self, **kwargs):
            raise RuntimeError("secret internals leak")

    client.app.state.engine = Boom()
    resp = client.post("/evaluate", json={"resume_text": RESUME})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "internal_error"
    assert "secret internals" not in resp.text
