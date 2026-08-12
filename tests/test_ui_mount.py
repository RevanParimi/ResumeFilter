"""The UI is served BY THE API, same origin (S8.6 spec 2).

Same-origin was chosen by the user over a separate static service. It does not
ship an untested posture -- it RETIRES one: the browser check has always run
both servers on localhost (cross-ORIGIN but same-SITE) with samesite=lax and
secure=false, so config.yaml's shipped SameSite=None has never been exercised
anywhere.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_the_ui_is_served_without_authentication(services):
    """Correct, and the reason it must ALSO be visible to the guard: a login
    page behind a login is unreachable by the person who needs it -- the same
    argument as public GET /grievance one floor down."""
    client = TestClient(create_app(services))
    resp = client.get("/ui/api.js")
    assert resp.status_code == 200
    assert "veritas" in resp.text[:400].lower()


def test_the_mount_root_is_the_frontend_directory(services):
    """Starlette owns traversal defence; the root we hand it is ours."""
    app = create_app(services)
    mounts = [r for r in app.routes if isinstance(r, Mount) and r.path == "/ui"]
    assert len(mounts) == 1
    assert Path(mounts[0].app.directory).resolve() == (ROOT / "frontend").resolve()


def test_the_ui_mount_does_not_shadow_the_api(services):
    """/ui is a real prefix, not a catch-all: the API must still answer."""
    # `with`, unlike the two tests above: this is the one assertion in this
    # file that touches a route needing app.state.services, and that state is
    # only populated inside create_app's lifespan (app/main.py). Every other
    # test file in this repo enters TestClient as a context manager for the
    # same reason -- without it /healthz 500s on a bare AttributeError, not on
    # the thing this test exists to check.
    with TestClient(create_app(services)) as client:
        assert client.get("/healthz").status_code == 200
