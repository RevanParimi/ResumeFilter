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

from app.main import UI_ASSETS, create_app
from tests.test_route_table_guard import _mounts

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
    mounts = [m for m in _mounts(app) if m.path == "/ui"]
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


def test_the_documented_entry_point_actually_loads(services):
    """DEPLOY.md step 7 tells the operator to open `/ui`. It 404'd.

    FOUND IN THE HAND-RUN CORRECTNESS PASS, and it survived four review passes
    because every check on this mount fetched an ASSET: the smoke, this file's
    own unauthenticated-access test and the CI image job all asked for
    `api.js`, which proves a JavaScript file is reachable and not that the UI
    loads. `/ui/` returned 404 for two independent reasons -- StaticFiles runs
    with html=False and there is no index.html, and the allowlist keys on the
    first path segment, which Starlette hands over as "." for a directory.

    Asserted through the redirect, because `/ui` is the string a human is told
    to type and a 307 to a 404 is still a 404 to them.
    """
    client = TestClient(create_app(services))
    resp = client.get("/ui")
    assert resp.status_code == 200, "DEPLOY.md step 7 tells operators to open /ui"
    assert "veritas" in resp.text.lower()
    # Not just "some HTML": the shell that will actually talk to the API.
    assert "api.js" in resp.text


def test_the_entry_point_keeps_its_trailing_slash(services):
    """LOAD-BEARING, and the reason this is served at `/ui/` rather than `/ui`.

    The document references its script RELATIVELY (`src="./api.js"`). From
    `/ui/` that resolves to `/ui/api.js`; from `/ui` it would resolve to
    `/api.js`, which is not mounted -- the shell would load and then fail to
    find the only file that talks to the API. Starlette's redirect is what
    makes the documented URL correct, so it is pinned rather than assumed.
    """
    client = TestClient(create_app(services), follow_redirects=False)
    resp = client.get("/ui")
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/ui/")
    assert 'src="./api.js"' in client.get("/ui/").text


def test_the_entry_document_is_itself_allowlisted(services):
    """The index is served BY NAME, so it has to be a name the allowlist
    already permits -- otherwise the two rules disagree and the fix would
    depend on which one runs first."""
    from app.main import UI_ENTRY
    assert UI_ENTRY in UI_ASSETS


def test_serving_the_index_does_not_weaken_the_allowlist(services):
    """The directory case is the ONLY thing that changed. A traversal that
    normalises to a bare "." must not become a way to ask for anything else."""
    client = TestClient(create_app(services))
    assert client.get("/ui/not-an-asset.txt").status_code == 404
    assert client.get("/ui/_ds").status_code == 404      # a directory, not a file
