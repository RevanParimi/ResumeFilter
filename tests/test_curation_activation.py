"""Runtime activation: owned capture, authorized review and raw-free decisions."""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.candidates.normalize.skills import normalize_skill
from app.curation.models import CurationAliasRow, CurationObservationRow, UnmappedTermRow
from app.curation.schema import CurationAction
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.curation_helpers import legacy_term, saved_source
from tests.test_curation_input_boundary import candidate, export
from tests.test_auth_api import cfg, client, capture_path, _code  # noqa: F401


def rows(services, model):
    with services.candidates._session_factory() as session:
        return session.execute(select(model.__table__)).mappings().all()


def ingest(client, cid, name="Synthetic Raw!"):
    return client.post(f"/candidates/{cid}/sources/linkedin", headers=ADMIN_HEADERS,
        json={"export_b64": base64.b64encode(export([name])).decode()})


def test_capture_uses_committed_source_and_erasure_removes_raw(services):
    cid = candidate(services)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        assert ingest(client, cid).status_code == 200
        observed = rows(services, CurationObservationRow)
        assert len(observed) == 1, "automatic capture must use owned storage"
        assert rows(services, UnmappedTermRow) == []
        assert client.delete(f"/candidates/{cid}").status_code == 200
        assert rows(services, CurationObservationRow) == []
        assert client.get("/curation/skills/unmapped").json()["terms"] == []


def test_explicit_alias_receipt_and_legacy_isolation(services):
    factory = services.candidates._session_factory
    legacy_term(factory)
    legacy_term(factory, "old approved", status="resolved", canonical="python", category="language")
    services.curation.refresh_overlay()
    assert normalize_skill("old approved").canonical == "python"
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        cid = candidate(services)
        assert ingest(client, cid).status_code == 200
        assert [t["norm_key"] for t in client.get("/curation/skills/unmapped").json()["terms"]] == ["synthetic raw"]
        before = rows(services, UnmappedTermRow)
        revision = client.get("/curation/skills/unmapped").json()["terms"][0]["review_revision"]
        assert client.post("/curation/skills/resolve", json={"norm_key": "legacy", "action": "ignore", "expected_revision": "0" * 64}).status_code == 404
        for field in ("note", "decided_by", "admin_user_id"):
            assert client.post("/curation/skills/resolve", json={"norm_key": "synthetic raw", "action": "ignore",
                "expected_revision": revision,
                field: "Supplied private text"}).status_code == 422
        assert client.post("/curation/skills/resolve", json={"norm_key": "synthetic raw", "action": "map",
            "expected_revision": revision,
            "canonical": "python", "category": "language"}).status_code == 422
        response = client.post("/curation/skills/resolve", json={"norm_key": "synthetic raw", "action": "map",
            "expected_revision": revision,
            "alias": "Approved vocabulary", "canonical": "python", "category": "language"})
        assert response.status_code == 200
        assert response.json() == dict(action="map", alias="Approved vocabulary", canonical="python",
            category="language", decided_at=response.json()["decided_at"], admin_user_id=None)
        assert "synthetic raw" not in response.text.lower()
        assert rows(services, CurationObservationRow) == []
        assert rows(services, UnmappedTermRow) == before
        assert normalize_skill("Approved vocabulary").canonical == "python"
        assert normalize_skill("Synthetic Raw!") is None
        for status in ("resolved", "ignored"):
            assert client.get("/curation/skills/unmapped?status=" + status).json() == {"terms": [], "next_cursor": None}


def test_alias_conflict_is_safe_and_rolls_back(services):
    _, source = saved_source(services.candidates._session_factory)
    for raw in ("Alpha raw", "Beta raw"):
        services.curation.record_unmapped(raw, source_id=source)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        body = dict(action="map", alias="Approved alias", canonical="python", category="language")
        revisions = {t["norm_key"]: t["review_revision"] for t in client.get("/curation/skills/unmapped").json()["terms"]}
        assert client.post("/curation/skills/resolve", json=body | {"norm_key": "alpha raw", "expected_revision": revisions["alpha raw"]}).status_code == 200
        conflict = client.post("/curation/skills/resolve", json=body | {"norm_key": "beta raw", "expected_revision": revisions["beta raw"]})
        assert conflict.status_code == 409 and conflict.json() == {"detail": "approved alias already exists"}
        assert [t["norm_key"] for t in client.get("/curation/skills/unmapped").json()["terms"]] == ["beta raw"]


def test_expiry_ignore_reappearance_and_fixed_lifetimes(services, monkeypatch):
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr("app.curation.store._utcnow", lambda: clock[0])
    _, source = saved_source(services.candidates._session_factory)
    services.curation.record_unmapped("Raw term", source_id=source)
    clock[0] += timedelta(days=29)
    services.curation.record_unmapped("RAW TERM!", source_id=source)
    clock[0] += timedelta(days=1)
    term, = services.curation.list_unmapped().terms
    assert term.occurrences == 1 and term.display_name == "RAW TERM!"
    assert len(rows(services, CurationObservationRow)) == 2
    assert services.curation.purge_expired() == 1
    result = services.curation.resolve("raw term", CurationAction.IGNORE)
    assert result.alias is None and rows(services, CurationObservationRow) == []
    assert rows(services, CurationAliasRow) == []
    services.curation.record_unmapped("Raw term", source_id=source)
    clock[0] += timedelta(days=30)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        assert client.get("/curation/skills/unmapped").json()["terms"] == []
        response = client.post("/curation/skills/resolve", json={"norm_key": "raw term", "action": "ignore", "expected_revision": "0" * 64})
        assert response.status_code == 404 and response.json() == {"detail": "term not found"}
    assert rows(services, CurationObservationRow) == []


def test_operator_attribution_csrf_and_other_planes(client, capture_path):
    services = client.app_services
    _, source = saved_source(services.candidates._session_factory)
    services.curation.record_unmapped("Review raw", source_id=source)
    body = dict(norm_key="review raw", action="map", alias="Approved alias",
                canonical="python", category="language", expected_revision="0" * 64)
    assert client.get("/curation/skills/unmapped").status_code == 401
    assert client.post("/curation/skills/resolve", json=body).status_code == 401
    org = client.post("/ledger/orgs", headers=ADMIN_HEADERS, json={"name": "Synthetic tenant"}).json()
    for headers in ({"X-Org-Key": org["api_key"]}, {"X-API-Key": "wrong"}):
        assert client.get("/curation/skills/unmapped", headers=headers).status_code == 401
        assert client.post("/curation/skills/resolve", headers=headers, json=body).status_code == 401
    operator = client.post("/admin/users", headers=ADMIN_HEADERS, json={"email": "operator@example.com"}).json()
    assert client.post("/auth/admin/login", json={"email": "operator@example.com"}).status_code == 202
    login = client.post("/auth/admin/verify", json={"email": "operator@example.com", "code": _code(capture_path)})
    assert login.status_code == 200
    assert client.get("/curation/skills/unmapped").status_code == 200
    body["expected_revision"] = client.get("/curation/skills/unmapped").json()["terms"][0]["review_revision"]
    assert client.post("/curation/skills/resolve", json=body).status_code == 403
    assert len(rows(services, CurationObservationRow)) == 1
    approved = client.post("/curation/skills/resolve", json=body,
                           headers={"X-CSRF-Token": login.json()["csrf_token"]})
    assert approved.status_code == 200 and approved.json()["admin_user_id"] == operator["id"]
    assert rows(services, CurationAliasRow)[0]["admin_user_id"] == operator["id"]


@pytest.mark.parametrize("boundary", ["before_capture", "during_capture", "after_response_read"])
async def test_erasure_at_capture_and_response_boundaries(services, monkeypatch, boundary):
    cid = candidate(services)
    capture = services.curation.record_unmapped
    saved_check = services.profile_sources._store.require_saved_signal
    if boundary == "before_capture":
        def erase_before(name, **kwargs):
            services.candidates.delete_candidate(cid)
            return capture(name, **kwargs)
        monkeypatch.setattr(services.curation, "record_unmapped", erase_before)
    elif boundary == "during_capture":
        def erase_after(name, **kwargs):
            capture(name, **kwargs)
            services.candidates.delete_candidate(cid)
        monkeypatch.setattr(services.curation, "record_unmapped", erase_after)
    else:
        def erase_after_check(candidate_id, source_id):
            saved_check(candidate_id, source_id)
            services.candidates.delete_candidate(cid)
        monkeypatch.setattr(services.profile_sources._store, "require_saved_signal", erase_after_check)
    if boundary == "after_response_read":
        assert await services.profile_sources.ingest_linkedin(cid, export(["Raw term"]))
    else:
        with pytest.raises(LookupError, match="candidate not found"):
            await services.profile_sources.ingest_linkedin(cid, export(["Raw term"]))
    assert rows(services, CurationObservationRow) == []
    assert rows(services, UnmappedTermRow) == []


def test_response_failure_does_not_rollback_saved_source_or_linked_capture(services, monkeypatch):
    cid = candidate(services)
    def fail_check(*args):
        raise RuntimeError("synthetic response failure")
    monkeypatch.setattr(services.profile_sources._store, "require_saved_signal", fail_check)
    with TestClient(create_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as client:
        assert ingest(client, cid).status_code == 500
    assert len(rows(services, CurationObservationRow)) == 1
    assert len(services.profile_sources._store.signals_for_candidate(cid)) == 1
    services.candidates.delete_candidate(cid)
    assert rows(services, CurationObservationRow) == []


def test_two_tenant_uploads_contribute_only_surviving_owned_forms(services):
    from app.candidates.models import ResumeRow
    with TestClient(create_app(services)) as client:
        ids, orgs = [], []
        for name, raw in (("First", "Shared Raw!"), ("Second", "SHARED RAW")):
            org = client.post("/ledger/orgs", headers=ADMIN_HEADERS, json={"name": name}).json()
            orgs.append(org)
            created = client.post("/screening/candidates", headers={"X-Org-Key": org["api_key"]},
                json={"resume_text": f"{name}\nEmail: {name.lower()}@example.com\nSKILLS\nPython", "evaluate": False})
            assert created.status_code == 200
            cid = created.json()["candidate_id"]
            ids.append(cid)
            assert ingest(client, cid, raw).status_code == 200
        assert {r["org_id"] for r in rows(services, ResumeRow)} == {o["org"]["id"] for o in orgs}
        for org in orgs:
            assert client.get("/curation/skills/unmapped", headers={"X-Org-Key": org["api_key"]}).status_code == 401
        queue = client.get("/curation/skills/unmapped", headers=ADMIN_HEADERS).json()["terms"]
        assert len(queue) == 1 and queue[0]["occurrences"] == 2
        assert client.delete(f"/candidates/{ids[1]}", headers=ADMIN_HEADERS).status_code == 200
        term, = client.get("/curation/skills/unmapped", headers=ADMIN_HEADERS).json()["terms"]
        assert term["display_name"] == "Shared Raw!" and term["occurrences"] == 1
        assert services.candidates.get_candidate(ids[0]) is not None
        assert len(rows(services, CurationObservationRow)) == 1
