"""S8.4 Phase B: another organisation's batch does not exist.

Every route, not a sample: the Phase A leak got in through the ONE org-facing
surface nobody enumerated, so this file enumerates them.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def test_every_batch_route_is_404_for_another_org_and_matches_absence(
    services, genuine_resume
):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        bid = _register(c, key_a, [genuine_resume]).json()["id"]
        b = {"X-Org-Key": key_b}

        cases = [
            ("get", f"/screening/batches/{bid}", "/screening/batches/nope"),
            ("get", f"/screening/batches/{bid}/queue", "/screening/batches/nope/queue"),
            ("get", f"/screening/batches/{bid}/summary", "/screening/batches/nope/summary"),
            ("post", f"/screening/batches/{bid}/process", "/screening/batches/nope/process"),
            ("delete", f"/screening/batches/{bid}", "/screening/batches/nope"),
        ]
        for method, theirs, absent in cases:
            got = getattr(c, method)(theirs, headers=b)
            missing = getattr(c, method)(absent, headers=b)
            assert got.status_code == 404, f"{method} {theirs} -> {got.status_code}"
            assert got.json() == missing.json(), (
                f"{method} {theirs}: a different body from a genuinely absent "
                f"batch confirms this one exists"
            )


def test_listing_shows_only_my_own_batches(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        _register(c, key_a, [genuine_resume], name="A's batch")
        mine = c.get("/screening/batches", headers={"X-Org-Key": key_b}).json()
        assert mine["batches"] == []


def test_a_cursor_from_another_org_reaches_nothing(services, genuine_resume):
    """A cursor is a sort position, not a capability -- the org filter is what
    protects the boundary, so a stolen cursor buys nothing."""
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        # TWO batches, so a limit=1 page actually has a next_cursor to steal.
        _register(c, key_a, [genuine_resume], name="first")
        _register(c, key_a, [genuine_resume + "\nRef 2"], name="second")
        page = c.get("/screening/batches?limit=1", headers={"X-Org-Key": key_a}).json()
        stolen = page["next_cursor"]
        assert stolen, "two batches and limit=1 must produce a cursor"

        theirs = c.get(f"/screening/batches?cursor={stolen}",
                       headers={"X-Org-Key": key_b})
        assert theirs.status_code == 200
        assert theirs.json()["batches"] == []


def test_all_batch_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/batches").status_code == 401
        assert c.post("/screening/batches", json={}).status_code == 401
        assert c.get("/screening/batches/x/queue").status_code == 401
        assert c.post("/screening/batches/x/process").status_code == 401
        assert c.delete("/screening/batches/x").status_code == 401
