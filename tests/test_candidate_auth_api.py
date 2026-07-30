from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


def _client(settings):
    # NOTE: this repo's installed Starlette/FastAPI only runs the app's
    # lifespan (which sets app.state.services) when the TestClient is used as
    # a context manager (see every other tests/test_*_api.py `with _client(...)
    # as client:` fixture). We keep the brief's tuple-return shape but enter
    # the context manually so every route in this file — including the ones
    # Task 9 still owes — resolves `_services(request)` correctly.
    services = make_services(settings)
    client = TestClient(create_app(services), raise_server_exceptions=False)
    client.__enter__()
    return client, services


def _make_candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text": "Dev\nEmail: d@e.com\nSKILLS\nPython\n",
                                         "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_admin_mints_candidate_key_and_it_authenticates(settings):
    client, _ = _client(settings)
    cid = _make_candidate(client)
    r = client.post(f"/candidates/{cid}/auth-key")
    assert r.status_code == 200
    key = r.json()["access_key"]
    assert r.json()["candidate_id"] == cid and key
    # the key authenticates on a portal route
    ok = client.get("/portal/me", headers={"X-Candidate-Key": key})
    assert ok.status_code == 200


def test_mint_unknown_candidate_404(settings):
    client, _ = _client(settings)
    r = client.post("/candidates/nope/auth-key")
    assert r.status_code == 404


# NOTE (task-8 discovery, documented in task-8-report.md): this test is also
# expected-red until Task 9 lands `GET /portal/me` on candidate_router. FastAPI
# never invokes a route dependency (require_candidate) for a path with zero
# registered routes — an unmatched path 404s before any dependency runs — so
# both assertions below currently see 404, not 401. This mirrors (does not add
# to) the single documented gap: once Task 9 adds the route, this test and
# `test_admin_mints_candidate_key_and_it_authenticates` go green together.
def test_portal_route_without_key_is_401(settings):
    client, _ = _client(settings)
    assert client.get("/portal/me").status_code == 401
    assert client.get("/portal/me", headers={"X-Candidate-Key": "bad"}).status_code == 401
