"""Invalid resumes must fail before graph/model work or durable intake writes."""

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.graph.build import EvaluationEngine
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.pdf_helpers import resume_pdf

TABLES = ("candidates", "resumes", "extractions", "resume_fingerprints", "reports",
          "screening_batches", "batch_items", "screening_item_inputs")


def counts(services):
    with services.session_factory() as session:
        return {table: session.scalar(text(f"SELECT count(*) FROM {table}")) for table in TABLES}


def invalid_inputs():
    valid = resume_pdf()
    return [
        ({"resume_text": " \t\r\n\u2003"}, "empty_resume"),
        ({"resume_pdf_b64": base64.b64encode(b"sensitive-not-a-pdf").decode()}, "pdf_parse_failed"),
        ({"resume_pdf_b64": base64.b64encode(base64.b64decode(valid)[:100]).decode()}, "pdf_parse_failed"),
        ({"resume_pdf_b64": valid[:20] + "!" + valid[20:]}, "pdf_parse_failed"),
        ({"resume_pdf_b64": resume_pdf(encrypted=True)}, "pdf_parse_failed"),
        ({"resume_pdf_b64": resume_pdf("")}, "pdf_no_readable_text"),
        ({"resume_pdf_b64": resume_pdf(image_only=True)}, "pdf_no_readable_text"),
        ({"resume_pdf_b64": resume_pdf(" " * 10)}, "pdf_no_readable_text"),
    ]


@pytest.mark.parametrize("path", ["/evaluate", "/candidates", "/screening/candidates", "/screening/batches"])
@pytest.mark.parametrize("payload,reason", invalid_inputs())
def test_invalid_resume_refuses_every_http_door_without_writes(services, path, payload, reason):
    org = services.ledger.create_organization("Synthetic Boundary")
    key = services.ledger.issue_api_key(org.id)
    before = counts(services)
    if path.endswith("/batches"):
        payload = {"items": [{"resume_text": "Readable preceding item"}, payload]}
        reason = "item 1: " + reason
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, "X-Org-Key": key}) as http:
        response = http.post(path, json=payload)
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": reason}
    assert counts(services) == before


@pytest.mark.parametrize("path", ["/evaluate", "/candidates", "/screening/candidates", "/screening/batches"])
def test_decoded_pdf_text_over_cap_is_refused_before_writes(services, path):
    services.settings.max_resume_chars = 32
    org = services.ledger.create_organization("Synthetic Boundary")
    key = services.ledger.issue_api_key(org.id)
    payload = {"resume_pdf_b64": resume_pdf("x" * 33)}
    before = counts(services)
    if path.endswith("/batches"):
        payload = {"items": [payload]}
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, "X-Org-Key": key}) as http:
        response = http.post(path, json=payload)
    assert response.status_code == 422, response.text
    assert "max_resume_chars" in response.json()["detail"]
    assert counts(services) == before


@pytest.mark.parametrize("payload", [{"resume_text": "  "},
    {"resume_pdf_b64": base64.b64encode(b"private PDF garbage").decode()},
    {"resume_pdf_b64": resume_pdf(image_only=True)},
    {"resume_text": "x" * 33}, {"resume_pdf_b64": resume_pdf("x" * 33)}])
async def test_direct_engine_refuses_without_model_work(services, monkeypatch, payload):
    services.settings.max_resume_chars = 32
    async def forbidden(**kwargs):
        pytest.fail("invalid resume reached an external model")
    monkeypatch.setattr(services.llm, "acomplete_json", forbidden)
    # The boundary exception is introduced by the fix; no import failure counts
    # as the reproducer. A successful report is the original defect here.
    with pytest.raises(ValueError):
        await EvaluationEngine(services).evaluate(**payload)


@pytest.mark.parametrize("source", ["text", "markdown", "pdf"])
def test_readable_sparse_inputs_are_advisory_not_unreadable(services, source):
    readable = "Python" if source != "markdown" else "# Skills\nPython"
    payload = {"resume_pdf_b64": resume_pdf(readable)} if source == "pdf" else {"resume_text": readable}
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as http:
        response = http.post("/evaluate", json=payload)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["advisory"] and report["human_review_required"]
        assert report["fabrication_risk"]["band"] == "insufficient_data"
        assert http.get(f'/report/{report["id"]}').json() == report


@pytest.mark.parametrize("value", [" \t\n", "x" * 33])
def test_direct_batch_registration_refuses_invalid_text_before_writes(services, value):
    services.settings.max_resume_chars = 32
    org = services.ledger.create_organization("Synthetic Boundary")
    before = counts(services)
    with pytest.raises(ValueError):
        services.screening.register(org.id, name="invalid", domain="genai",
            texts=["Readable preceding item", value], created_by_org_user_id=None)
    assert counts(services) == before


@pytest.mark.parametrize("path", ["/evaluate", "/candidates", "/screening/candidates", "/screening/batches"])
@pytest.mark.parametrize("pdf", [False, True])
def test_exact_text_boundary_is_accepted_in_every_door(services, path, pdf):
    services.settings.max_resume_chars = 32
    org = services.ledger.create_organization("Synthetic Boundary")
    key = services.ledger.issue_api_key(org.id)
    value = "x" * 32
    payload = {"resume_pdf_b64": resume_pdf(value)} if pdf else {"resume_text": value}
    if path.endswith("/batches"):
        payload = {"items": [payload]}
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, "X-Org-Key": key}) as http:
        response = http.post(path, json=payload)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", ["/evaluate", "/candidates", "/screening/candidates", "/screening/batches"])
def test_encoded_pdf_cap_accepts_exact_and_refuses_over(services, path):
    pdf = resume_pdf()
    services.settings.max_pdf_b64_chars = len(pdf)
    org = services.ledger.create_organization("Synthetic Boundary")
    key = services.ledger.issue_api_key(org.id)
    payload = {"resume_pdf_b64": pdf}
    if path.endswith("/batches"):
        payload = {"items": [payload]}
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, "X-Org-Key": key}) as http:
        assert http.post(path, json=payload).status_code == 200
        before = counts(services)
        services.settings.max_pdf_b64_chars -= 1
        response = http.post(path, json=payload)
    assert response.status_code == 422
    assert "max_pdf_b64_chars" in response.json()["detail"]
    assert counts(services) == before


@pytest.mark.parametrize("path", ["/evaluate", "/candidates", "/screening/candidates", "/screening/batches"])
def test_private_parser_exceptions_are_not_public_or_graph_log_details(services, monkeypatch, log_events, path):
    def broken(_, **kwargs):
        raise RuntimeError("private-document-content-and-path")
    monkeypatch.setattr("app.core.resume.pdf_b64_to_text", broken)
    org = services.ledger.create_organization("Synthetic Boundary")
    key = services.ledger.issue_api_key(org.id)
    payload = {"resume_pdf_b64": resume_pdf()}
    if path.endswith("/batches"):
        payload = {"items": [payload]}
    with TestClient(create_app(services), headers={**ADMIN_HEADERS, "X-Org-Key": key}) as http:
        response = http.post(path, json=payload)
    assert response.status_code == 422
    assert "private-document-content-and-path" not in response.text + str(log_events)
    assert all(value == 0 for value in counts(services).values())


def test_text_precedence_and_empty_text_fallback_are_preserved(services):
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as http:
        assert http.post("/evaluate", json={"resume_text": "Python", "resume_pdf_b64": "junk"}).status_code == 200
        assert http.post("/evaluate", json={"resume_text": "", "resume_pdf_b64": resume_pdf()}).status_code == 200
        response = http.post("/evaluate", json={"resume_text": "  ", "resume_pdf_b64": resume_pdf()})
        assert response.status_code == 422 and response.json()["detail"] == "empty_resume"


def test_pdf_padding_counts_toward_the_decoded_text_cap(services):
    services.settings.max_resume_chars = 32
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as http:
        for value in (" " * 33, "x" + " " * 32):
            response = http.post("/evaluate", json={"resume_pdf_b64": resume_pdf(value)})
            assert response.status_code == 422
            assert "max_resume_chars" in response.json()["detail"]
    assert all(value == 0 for value in counts(services).values())
