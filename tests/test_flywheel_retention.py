"""New evaluation data stays in the erasable report/outcome store, not JSONL."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.flywheel import build_flywheel
from tests.conftest import ADMIN_HEADERS, make_services


def _resume(email):
    return (f"Candidate\nEmail: {email}\nSkills: Python\n"
            "- Built production RAG at scale for support tickets.\n")


@pytest.fixture
def retention_api(settings, tmp_path):
    path = tmp_path / "legacy" / "flywheel.jsonl"
    cfg = settings.model_copy(update={"flywheel_path": str(path)})
    services = make_services(cfg, flywheel=build_flywheel(cfg))
    with TestClient(create_app(services), headers=ADMIN_HEADERS,
                    raise_server_exceptions=False) as client:
        yield client, services, path


@pytest.mark.parametrize("erase_door", ["portal", "admin"])
def test_evaluate_outcome_erase_preserves_only_other_candidates_data(retention_api, erase_door):
    client, services, path = retention_api
    uploads = []
    for email in ("a@example.com", "b@example.com"):
        response = client.post("/candidates", json={"resume_text": _resume(email)})
        assert response.status_code == 200, response.text
        up = response.json()
        assert up["report"]["verdicts"]
        uploads.append(up)
        outcome = client.post(f"/report/{up['report']['id']}/outcome", json={
            "outcome": "candidate_clarified", "notes": f"Private note for {email}",
        })
        assert outcome.status_code == 200, outcome.text
    a, b = uploads
    if erase_door == "portal":
        key_response = client.post(f"/candidates/{a['candidate_id']}/auth-key")
        assert key_response.status_code == 200, key_response.text
        headers = {"X-Candidate-Key": key_response.json()["access_key"]}
        erased = client.delete("/portal/me", headers=headers)
        assert client.get("/portal/me", headers=headers).status_code == 401
    else:
        erased = client.delete(f"/candidates/{a['candidate_id']}")
    assert erased.status_code in (200, 204), erased.text
    assert services.report_store.get(a["report"]["id"]) is None
    assert services.report_store.outcomes(a["report"]["id"]) == []
    assert services.report_store.get(b["report"]["id"]) is not None
    assert services.report_store.outcomes(b["report"]["id"])[0].notes == "Private note for b@example.com"
    assert services.portal.erase(a["candidate_id"])["deleted"] is False
    assert not path.exists(), "new candidate data escaped SQL erasure into JSONL"


def test_standalone_report_and_outcome_have_no_unmanaged_copy(retention_api):
    client, services, path = retention_api
    response = client.post("/evaluate", json={"resume_text": _resume("standalone@example.com")})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["candidate_id"] is None  # no inferred identity binding
    assert client.post(f"/report/{report['id']}/outcome", json={
        "outcome": "inconclusive", "notes": "Standalone private note",
    }).status_code == 200
    assert services.report_store.delete(report["id"])
    assert client.get(f"/report/{report['id']}").status_code == 404
    assert services.report_store.outcomes(report["id"]) == []
    assert not path.exists(), "standalone evaluation wrote an unowned text copy"


def test_legacy_file_is_not_appended_or_deleted(settings, tmp_path):
    path = tmp_path / "existing.jsonl"
    original = b'{"claim_text":"synthetic legacy record"}\n'
    path.write_bytes(original)
    fw = build_flywheel(settings.model_copy(update={"flywheel_path": str(path)}))
    fw.log({"claim_text": "new private claim", "probes": ["new private probe"]})
    fw.log({"record_type": "outcome", "notes": "new private note"})
    assert path.read_bytes() == original  # legacy cleanup is a later, explicit task


def test_report_persistence_failure_does_not_leave_a_text_copy(retention_api, monkeypatch):
    client, services, path = retention_api
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic database failure")
    monkeypatch.setattr(services.report_store, "save", fail)
    response = client.post("/evaluate", json={"resume_text": _resume("a@example.com")})
    assert response.status_code == 500
    assert not path.exists(), "failed report save left a durable orphan"


def test_erasure_failure_is_not_reported_as_success(retention_api, monkeypatch):
    client, services, path = retention_api
    up = client.post("/candidates", json={"resume_text": _resume("a@example.com")}).json()
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic deletion failure")
    monkeypatch.setattr(services.candidates, "delete_candidate", fail)
    response = client.delete(f"/candidates/{up['candidate_id']}")
    assert response.status_code == 500
    assert services.report_store.get(up["report"]["id"]) is not None
    assert not path.exists()


def test_outcome_failure_preserves_report_without_an_extra_copy(retention_api, monkeypatch):
    client, services, path = retention_api
    response = client.post("/evaluate", json={"resume_text": _resume("a@example.com")})
    assert response.status_code == 200, response.text
    report_id = response.json()["id"]
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic outcome storage failure")
    monkeypatch.setattr(services.report_store, "add_outcome", fail)
    result = client.post(f"/report/{report_id}/outcome", json={
        "outcome": "inconclusive", "notes": "private outcome note",
    })
    assert result.status_code == 500
    assert services.report_store.get(report_id) is not None
    assert services.report_store.outcomes(report_id) == []
    assert not path.exists()
