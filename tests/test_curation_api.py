import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services
from tests.curation_helpers import saved_source
from tests.curation_helpers import saved_source


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
            "expected_revision": client.get("/curation/skills/unmapped").json()["terms"][0]["review_revision"],
            "norm_key": "cobol", "action": "create", "alias": "COBOL", "canonical": "cobol", "category": "language"})
        assert r.status_code == 200
        assert r.json()["action"] == "create"
        pending = client.get("/curation/skills/unmapped?status=pending").json()
        assert "cobol" not in [t["norm_key"] for t in pending["terms"]]


def test_resolve_unknown_term_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/curation/skills/resolve", json={"norm_key": "ghost", "action": "ignore", "expected_revision": "0" * 64})
        assert r.status_code == 404


def test_resolve_invalid_decision_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.post("/curation/skills/resolve", json={
            "expected_revision": client.get("/curation/skills/unmapped").json()["terms"][0]["review_revision"],
            "norm_key": "cobol", "action": "map", "canonical": "not_a_real_skill"})
        assert r.status_code == 422


def test_unmapped_terms_page_with_a_cursor(services, admin_headers):
    """S8.4 Phase B: the curation queue pages. `limit` keeps working -- this
    endpoint has callers."""
    from app.main import create_app
    from fastapi.testclient import TestClient

    _, source = saved_source(services.candidates._session_factory)
    _, source = saved_source(services.candidates._session_factory)
    for i in range(3):
        services.curation.record_unmapped(f"Term {i}", source_id=source)

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


def test_api_stale_review_cannot_consume_replacement(services, admin_headers):
    """Two reviews of a key must not target a later submission of that key."""
    _, source = saved_source(services.candidates._session_factory)
    services.curation.record_unmapped("Review raw", source_id=source)
    with TestClient(create_app(services), headers=admin_headers) as client:
        old, = client.get("/curation/skills/unmapped").json()["terms"]
        revision = old.get("review_revision")
        assert isinstance(revision, str) and len(revision) == 64, "queue must identify the exact reviewed snapshot"
        ignore = dict(norm_key="review raw", action="ignore", expected_revision=revision)
        assert client.post("/curation/skills/resolve", json=ignore).status_code == 200
        services.curation.record_unmapped("Review raw", source_id=source)
        fresh, = client.get("/curation/skills/unmapped").json()["terms"]
        assert fresh["review_revision"] != revision
        stale = client.post("/curation/skills/resolve", json=ignore)
        assert stale.status_code == 409
        assert stale.json() == {"detail": "review snapshot changed; refresh before deciding"}
        assert client.get("/curation/skills/unmapped").json()["terms"] == [fresh]
        assert client.post("/curation/skills/resolve", json=ignore | {
            "expected_revision": fresh["review_revision"]}).status_code == 200
        assert client.post("/curation/skills/resolve", json=ignore).status_code == 404


def test_api_revision_validation_and_alias_rollback(services, admin_headers):
    from app.curation.models import CurationAliasRow, CurationObservationRow
    from sqlalchemy import select

    _, source = saved_source(services.candidates._session_factory)
    for name in ("First raw", "Second raw"):
        services.curation.record_unmapped(name, source_id=source)
    with TestClient(create_app(services), headers=admin_headers) as client:
        snapshots = {t["norm_key"]: t for t in client.get("/curation/skills/unmapped").json()["terms"]}
        body = dict(norm_key="first raw", action="map", alias="Approved revision",
                    canonical="python", category="language")
        for invalid in ("", "x" * 64, "0" * 63, "0" * 65, 123):
            assert client.post("/curation/skills/resolve", json=body | {"expected_revision": invalid}).status_code == 422
        receipt = client.post("/curation/skills/resolve", json=body | {
            "expected_revision": snapshots["first raw"]["review_revision"]})
        assert receipt.status_code == 200
        assert set(receipt.json()) == {"action", "alias", "canonical", "category", "decided_at", "admin_user_id"}
        assert receipt.json()["admin_user_id"] is None
        conflict = client.post("/curation/skills/resolve", json=body | {
            "norm_key": "second raw", "expected_revision": snapshots["second raw"]["review_revision"]})
        assert conflict.status_code == 409 and conflict.json() == {"detail": "approved alias already exists"}
        with services.candidates._session_factory() as session:
            assert len(session.scalars(select(CurationObservationRow)).all()) == 1
            assert len(session.scalars(select(CurationAliasRow)).all()) == 1

        assert client.post("/curation/skills/resolve", json={"norm_key": "second raw", "action": "ignore",
            "expected_revision": snapshots["second raw"]["review_revision"]}).status_code == 200


def test_http_resolution_requires_revision_before_mutation(services, admin_headers):
    _, source = saved_source(services.candidates._session_factory)
    services.curation.record_unmapped("Required review raw", source_id=source)
    with TestClient(create_app(services), headers=admin_headers) as client:
        before = client.get("/curation/skills/unmapped").json()
        body = dict(norm_key="required review raw", action="ignore")
        for extra in ({}, {"expected_revision": None}):
            response = client.post("/curation/skills/resolve", json=body | extra)
            assert response.status_code == 422, "HTTP decisions must require the reviewed snapshot"
            assert client.get("/curation/skills/unmapped").json() == before
