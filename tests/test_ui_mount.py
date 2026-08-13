"""The UI is served BY THE API, same origin (S8.6 spec 2).

Same-origin was chosen by the user over a separate static service. It does not
ship an untested posture -- it RETIRES one: the browser check has always run
both servers on localhost (cross-ORIGIN but same-SITE) with samesite=lax and
secure=false, so config.yaml's SameSite=None had never been exercised anywhere.
The next commit acts on that -- the shipped default is now `lax`, the posture
every check already runs (tests/test_cookie_posture.py).
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


#: Filenames the mount is allowed to expose that are not runtime assets.
#: `_ds/` is a VENDORED third-party design-system bundle; its readmes describe
#: the bundle, not veritas, and editing a vendored tree to satisfy our own rule
#: buys nothing. Everything else under frontend/ is served to the public
#: internet the moment this deploys.
_VENDORED = "_ds"


def test_the_mount_serves_no_internal_documentation(services):
    """FOUND IN REVIEW, after the merge. The guard one file over was widened to
    say "a mount is an unauthenticated surface" -- and then nobody checked WHAT
    this one exposes.

    `StaticFiles` serves the whole directory, so `frontend/PLAN.md` and
    `frontend/UI-SPEC.md` answered 200 to anyone at `/ui/PLAN.md`: the tenancy
    model, the roadmap decisions, the rejected design direction and a
    screen-by-screen inventory of what is and is not built.

    Not sensitive in the credentials sense, and that is not the bar -- the bar
    is that the public surface is INTENTIONAL. They live in docs/ui/ now.

    Deliberately a check on the DIRECTORY, not on two paths: `.dockerignore`'s
    `*.md` does not match a nested path (Go filepath.Match, `*` does not cross
    a separator), so the container would have shipped them even though the
    ignore file looks like it covers markdown. Moving them out is a fix that
    does not depend on anyone reading that subtlety correctly.
    """
    stray = [
        p.name for p in (ROOT / "frontend").rglob("*.md")
        if _VENDORED not in p.parts
    ]
    assert stray == [], (
        f"{stray} sit inside the served directory and would be public. "
        "Documentation belongs in docs/, not in the static mount."
    )


def test_the_documentation_really_is_unreachable(services):
    """The property above, over the wire -- because the rule that matters is
    what the server answers, not what the tree looks like."""
    client = TestClient(create_app(services))
    for path in ("/ui/PLAN.md", "/ui/UI-SPEC.md"):
        assert client.get(path).status_code == 404, path


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
