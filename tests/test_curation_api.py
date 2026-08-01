import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


def _client(services):
    return TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS)


def _candidate(client) -> str:
    r = client.post("/candidates", json={
        "resume_text": "Dev\nEmail: dev@example.com\nSKILLS\nPython\n", "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def _linkedin_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nCOBOL\n")
        zf.writestr("Profile.csv", "Headline,Industry\nEngineer,IT\n")
    return base64.b64encode(buf.getvalue()).decode()


def test_unmapped_queue_lists_captured_term(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.get("/curation/skills/unmapped?status=pending")
        assert r.status_code == 200
        keys = [t["norm_key"] for t in r.json()]
        assert "cobol" in keys


def test_resolve_create_then_term_no_longer_pending(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.post("/curation/skills/resolve", json={
            "norm_key": "cobol", "action": "create", "canonical": "cobol", "category": "language"})
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"
        pending = client.get("/curation/skills/unmapped?status=pending").json()
        assert "cobol" not in [t["norm_key"] for t in pending]


def test_resolve_unknown_term_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/curation/skills/resolve", json={"norm_key": "ghost", "action": "ignore"})
        assert r.status_code == 404


def test_resolve_invalid_decision_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.post("/curation/skills/resolve", json={
            "norm_key": "cobol", "action": "map", "canonical": "not_a_real_skill"})
        assert r.status_code == 422
