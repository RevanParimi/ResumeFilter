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
        keys = [t["norm_key"] for t in r.json()["terms"]]
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
        assert "cobol" not in [t["norm_key"] for t in pending["terms"]]


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


def test_unmapped_terms_page_with_a_cursor(services, admin_headers):
    """S8.4 Phase B: the curation queue pages. `limit` keeps working -- this
    endpoint has callers."""
    from app.main import create_app
    from fastapi.testclient import TestClient

    for i in range(3):
        services.curation.record_unmapped(f"Term {i}", source_type="github")

    with TestClient(create_app(services), headers=admin_headers) as c:
        first = c.get("/curation/skills/unmapped?limit=2")
        assert first.status_code == 200
        body = first.json()
        assert len(body["terms"]) == 2 and body["next_cursor"]

        second = c.get(f"/curation/skills/unmapped?cursor={body['next_cursor']}")
        keys = [t["norm_key"] for t in body["terms"] + second.json()["terms"]]
        assert len(keys) == len(set(keys)) == 3


def test_a_malformed_curation_cursor_is_422(services, admin_headers):
    from app.main import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app(services), headers=admin_headers,
                    raise_server_exceptions=False) as c:
        assert c.get("/curation/skills/unmapped?cursor=!!!").status_code == 422


def test_a_type_forged_curation_cursor_is_422(services, admin_headers):
    """Decodes fine, wrong types inside -- the shape that reached
    datetime.fromisoformat as a non-string and raised TypeError."""
    import base64
    import json

    from app.main import create_app
    from fastapi.testclient import TestClient

    def forge(values):
        raw = json.dumps(values).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    with TestClient(create_app(services), headers=admin_headers,
                    raise_server_exceptions=False) as c:
        for forged in (forge([1, 2, "k"]), forge(["x", "2026-08-07", 3]),
                       forge([1, "not-a-date", "k"])):
            r = c.get(f"/curation/skills/unmapped?cursor={forged}")
            assert r.status_code == 422, f"{forged} -> {r.status_code}"
