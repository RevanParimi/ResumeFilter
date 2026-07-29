import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.github import GitHubUserRaw
from tests.conftest import FakeGitHub, make_services


def _client(services):
    return TestClient(create_app(services), raise_server_exceptions=False)


def _candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text":
        "Dev\nEmail: dev@example.com\nSKILLS\nPython\n", "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_post_github_source_available(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/github", json={"handle": "octocat"})
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "api"
        assert body["identifier"] == "octocat"
        assert any(s["canonical"] == "python" for s in body["skills"])

        lst = client.get(f"/candidates/{cid}/sources")
        assert lst.status_code == 200
        assert len(lst.json()["sources"]) == 1


def test_post_github_source_unavailable_is_200(settings):
    gh = FakeGitHub(user_signals={"ghost": GitHubUserRaw(login="ghost", available=False, warnings=["not found"])})
    services = make_services(settings, github=gh)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/github", json={"handle": "ghost"})
        assert r.status_code == 200
        assert r.json()["method"] == "unavailable"


def test_post_github_source_no_handle_is_400(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)  # resume has no github link
        r = client.post(f"/candidates/{cid}/sources/github", json={})
        assert r.status_code == 400


def test_post_github_source_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/candidates/nope/sources/github", json={"handle": "octocat"})
        assert r.status_code == 404


def test_get_sources_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.get("/candidates/nope/sources")
        assert r.status_code == 404


def _linkedin_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nLeadership\n")
        zf.writestr("Positions.csv", "Company Name,Title,Finished On\nInfosys,Python Dev,\n")
        zf.writestr("Profile.csv", "Headline,Industry\nPython Engineer,IT\n")
    return base64.b64encode(buf.getvalue()).decode()


def test_post_linkedin_source_available(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "export"
        assert body["source_type"] == "linkedin_export"
        assert any(s["canonical"] == "python" for s in body["skills"])
        assert body["activity"]["employers"] == ["Infosys"]

        lst = client.get(f"/candidates/{cid}/sources?source_type=linkedin_export")
        assert lst.status_code == 200
        assert len(lst.json()["sources"]) == 1


def test_post_linkedin_wrong_zip_is_200_unavailable(settings, fake_github):
    services = make_services(settings, github=fake_github)
    b64 = base64.b64encode(_wrong_zip()).decode()
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": b64})
        assert r.status_code == 200
        assert r.json()["method"] == "unavailable"


def _wrong_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Ad_Targeting.csv", "Member Age\n25\n")
    return buf.getvalue()


def test_post_linkedin_bad_base64_is_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": "!!!not base64!!!"})
        assert r.status_code == 422


def test_post_linkedin_oversize_is_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        big = "A" * (services.settings.max_linkedin_b64_chars + 1)
        r = client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": big})
        assert r.status_code == 422


def test_post_linkedin_unknown_candidate_is_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/candidates/nope/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert r.status_code == 404
