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

from app.main import UI_ASSETS, create_app

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


def test_the_mount_serves_only_the_allowlist(services):
    """FOUND IN THE SECOND REVIEW, and it is the FIRST fix's own shape one file
    over. That fix moved `PLAN.md` and `UI-SPEC.md` out and left a guard that
    globs `*.md` -- a denylist of one extension, which can only name what
    somebody already thought of. Three files walked straight past it, measured
    over the wire at 200:

      * `Veritas v1 (Broadsheet).dc.html` (42KB) -- the design direction
        `docs/ui/PLAN.md` records as REJECTED ("reads like a PDF"). The first
        fix relocated the document DESCRIBING the rejected design and left the
        rejected design itself served.
      * `.thumbnail` (18KB) and `uploads/*.png` (659KB) -- gitignored
        design-tool droppings. Gitignore is not a mount rule: `StaticFiles`
        reads the filesystem, so an ignored file is served exactly like a
        tracked one, and these two come BACK every time the design tool runs.

    So the rule is an allowlist rather than a list of known-bad paths. Adding a
    UI asset is now a reviewable act -- the same argument this repo already
    applies to PUBLIC_PATHS and MOUNTS.

    Asserted over the WIRE against whatever is on this disk right now, not as a
    property of the tracked tree: two of the three offenders are gitignored, so
    a tree assertion would either be blind to them or fail on every machine that
    has run the design tool. What has to be true is that the server refuses
    them.
    """
    root = ROOT / "frontend"
    client = TestClient(create_app(services))
    served = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if not p.is_file() or rel.parts[0] in UI_ASSETS:
            continue
        if client.get("/ui/" + rel.as_posix()).status_code == 200:
            served.append(rel.as_posix())
    assert served == [], (
        f"{served} are being served to the public internet. Either add the "
        "top-level name to app.main.UI_ASSETS -- deliberately, in a diff "
        "somebody reads -- or move the file out of frontend/."
    )


def test_the_allowlist_is_enforced_by_THE_SERVER_not_just_the_tree(services):
    """The check above can only see files that exist when the suite runs. This
    one pins the RULE.

    A file dropped into `frontend/` after the last test run is served anyway --
    that is exactly how `.thumbnail` and `uploads/` got there -- so the refusal
    has to live in the mount, not in a lint. Written against a file that is in
    no directory listing anyone has reviewed, so it proves the server's
    behaviour rather than today's contents.
    """
    stray = ROOT / "frontend" / "not-an-asset.txt"
    stray.write_text("secret-ish", encoding="utf-8")
    try:
        client = TestClient(create_app(services))
        assert client.get("/ui/not-an-asset.txt").status_code == 404
        assert client.get("/ui/api.js").status_code == 200
    finally:
        stray.unlink()


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
