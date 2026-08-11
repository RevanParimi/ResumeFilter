"""The operator reviews, decides, and is recorded deciding (S8.3 Phase B)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rights.schema import ResolvedBy
from tests.conftest import ADMIN_HEADERS, make_services


@pytest.fixture
def _setup(settings):
    services = make_services(settings)
    with TestClient(
        create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS
    ) as client:
        yield client, services


def _candidate_with_key(client, email="d@e.com"):
    cid = client.post("/candidates", json={
        "resume_text": f"Asha R\nEmail: {email}\nSKILLS\nPython\n", "evaluate": False,
    }).json()["candidate_id"]
    key = client.post(f"/candidates/{cid}/auth-key").json()["access_key"]
    return cid, {"X-Candidate-Key": key}


def _file_correction(client, headers, field="full_name", value="Asha Rao"):
    return client.post("/portal/corrections", headers=headers,
                       json={"field": field, "requested_value": value}).json()


def test_both_admin_routes_need_the_admin_credential(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        assert c.get("/admin/requests").status_code == 401
        assert c.post("/admin/requests/x/resolve", json={}).status_code == 401


def test_the_operator_lists_open_requests(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    _file_correction(client, h)
    listed = client.get("/admin/requests?status=open").json()
    assert len(listed) == 1
    assert listed[0]["field"] == "full_name"
    assert listed[0]["current_value"] == "Asha R"


def test_the_operator_sees_EVERY_candidates_requests(_setup):
    """The admin plane is not tenant-scoped -- an operator handling complaints
    has to see the queue, not one person's slice of it."""
    client, _ = _setup
    _, one = _candidate_with_key(client, email="one@e.com")
    _, two = _candidate_with_key(client, email="two@e.com")
    client.post("/portal/grievances", headers=one, json={"note": "a"})
    client.post("/portal/grievances", headers=two, json={"note": "b"})
    assert {r["note"] for r in client.get("/admin/requests").json()} == {"a", "b"}


def test_resolving_with_apply_updates_the_candidate_and_the_portal_shows_it(_setup):
    client, services = _setup
    cid, h = _candidate_with_key(client)
    submitted = _file_correction(client, h)
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "resolved", "resolution": "checked the ID",
                          "apply": True})
    assert r.status_code == 200 and r.json()["applied"] is True

    me = client.get("/portal/me", headers=h).json()
    assert me["requests"][0]["status"] == "resolved"
    assert me["requests"][0]["applied"] is True
    # The IDENTITY row is what moved. `profile` is the EXTRACTION's view and is
    # deliberately untouched (spec §8.2), so assert the column directly.
    assert services.candidates.get_candidate(cid).full_name == "Asha Rao"


def test_applying_an_email_correction_is_422_and_names_the_reason(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = _file_correction(client, h, field="email",
                                 value="new@example.com")
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "resolved", "resolution": "ok", "apply": True})
    assert r.status_code == 422
    assert "login" in r.json()["detail"].lower()


def test_an_email_correction_can_still_be_resolved_without_apply(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = _file_correction(client, h, field="email",
                                 value="new@example.com")
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "resolved",
                          "resolution": "changed by hand after an ID check",
                          "apply": False})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved" and r.json()["applied"] is False


def test_an_unknown_request_id_is_404(_setup):
    client, _ = _setup
    r = client.post("/admin/requests/nope/resolve",
                    json={"status": "resolved", "resolution": "x", "apply": False})
    assert r.status_code == 404


def test_resolving_twice_is_409(_setup):
    """409 and not 422: a second decision on a decided request is a different
    operator mistake from an impermissible one, and collapsing them makes the
    second unactionable."""
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = client.post("/portal/grievances", headers=h,
                            json={"note": "nobody answered"}).json()
    body = {"status": "resolved", "resolution": "called them", "apply": False}
    assert client.post(f"/admin/requests/{submitted['id']}/resolve",
                       json=body).status_code == 200
    assert client.post(f"/admin/requests/{submitted['id']}/resolve",
                       json=body).status_code == 409


def test_a_decision_without_a_reason_is_422(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = _file_correction(client, h)
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    json={"status": "rejected", "resolution": "  ", "apply": False})
    assert r.status_code == 422


def test_a_machine_key_resolution_is_recorded_as_a_KEY_not_as_a_person(_setup):
    """S8.5's `recorded_by` argument at a second table: the shared admin key
    has no human behind it, and a null admin_user_id alone would be
    indistinguishable from an admin who was later deleted."""
    client, services = _setup
    _, h = _candidate_with_key(client)
    submitted = client.post("/portal/grievances", headers=h,
                            json={"note": "x"}).json()
    client.post(f"/admin/requests/{submitted['id']}/resolve",
                json={"status": "resolved", "resolution": "done", "apply": False})

    row = services.rights.list_by_status(None, limit=10)[0]
    assert row.resolved_by is ResolvedBy.OPERATOR_KEY
    # And the subject is told the KIND of decider, never a person's identity.
    shown = client.get("/portal/requests", headers=h).json()[0]
    assert shown["resolved_by"] == "operator_key"


def test_the_resolution_appears_in_the_subjects_access_log(_setup):
    client, _ = _setup
    _, h = _candidate_with_key(client)
    submitted = client.post("/portal/grievances", headers=h,
                            json={"note": "x"}).json()
    client.post(f"/admin/requests/{submitted['id']}/resolve",
                json={"status": "resolved", "resolution": "done", "apply": False})
    log = client.get("/portal/access-log", headers=h).json()
    actions = [e["action"] for e in log
               if e["entity_type"] == "data_principal_request"]
    assert sorted(actions) == ["request.resolve", "request.submit"]


def test_an_unknown_status_filter_is_refused_by_the_MODEL(_setup):
    client, _ = _setup
    assert client.get("/admin/requests?status=pending").status_code == 422
