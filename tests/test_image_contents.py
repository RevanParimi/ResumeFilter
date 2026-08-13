"""The Dockerfile's COPY list is a HAND-MAINTAINED LIST of what the app needs
at runtime, and this repo has found four of those drifted in three sprints:
conftest's model imports (a test that passed in its file and failed alone),
alembic/env.py's imports (six missing -- autogenerate would have emitted DROP
TABLE for six live tables), the RateLimited->429 translation copied four times,
and test_ratelimit_wiring's LIMITED tuple.

It had already drifted here: frontend/ was missing, which was invisible while
nothing served the UI and becomes a blank page the moment the mount lands.

WHAT IS DERIVED AND WHAT IS A FLOOR. The static mount root comes from the LIVE
APP and the migration directory from alembic.ini, because those are configured
elsewhere and are the two that can move without anyone touching this file. The
package and config floor is literal. Same shape as test_ratelimit_wiring, which
discovers limited services off the container and keeps a named tuple as a floor
so a service that silently LOSES its limiter still fails.

AND THERE IS A SECOND LIST. `.dockerignore` can quietly cancel a COPY: the
Dockerfile says `COPY frontend ./frontend`, the ignore file says `frontend/`,
and the build produces exactly the blank page the COPY was added to prevent.
Two hand-maintained lists that must agree is the precise shape of every drift
above, so the last test here reads both.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

from starlette.routing import Mount

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]

#: Paths the image must contain no matter what any config says.
FLOOR = {"app", "config.yaml", "alembic.ini"}


def _copied_sources() -> set[str]:
    """Every source path in a `COPY <src> <dst>` line, normalised."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    out: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"\s*COPY\s+(?!--)(\S+)\s+(\S+)\s*$", line)
        if m:
            out.add(m.group(1).strip("./").rstrip("/"))
    return out


def _ignored_patterns() -> set[str]:
    """Non-comment, non-negated entries in .dockerignore, normalised."""
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    out: set[str] = set()
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or entry.startswith("!"):
            continue
        out.add(entry.strip("./").rstrip("/"))
    return out


def test_the_floor_is_copied():
    missing = FLOOR - _copied_sources()
    assert missing == set(), f"Dockerfile never COPYs {sorted(missing)}"


def test_the_static_mount_root_is_copied(services):
    """DERIVED from the running app: if someone moves the UI directory, this
    fails without anyone remembering to edit a list."""
    app = create_app(services)
    roots = {
        Path(r.app.directory).resolve().relative_to(ROOT).as_posix()
        for r in app.routes
        if isinstance(r, Mount) and hasattr(r.app, "directory")
    }
    assert roots, "no static mount found -- this guard would pass vacuously"
    assert roots <= _copied_sources(), (
        f"the app serves {sorted(roots)} but the image never COPYs it: "
        "the UI would be a 404 in the container"
    )


def test_the_migration_directory_is_copied():
    """DERIVED from alembic.ini, because migrate-on-boot fails at RUNTIME
    without it -- after the container reports itself started."""
    cfg = configparser.ConfigParser()
    cfg.read(ROOT / "alembic.ini", encoding="utf-8")
    loc = cfg["alembic"]["script_location"].strip().strip("./").rstrip("/")
    assert loc in _copied_sources(), f"alembic script_location {loc!r} is not COPYed"


def test_dockerignore_does_not_cancel_a_copy():
    """The two lists must agree, and only one of them is read by the tests
    above.

    Deliberately NOT a docker pattern engine: this catches an ignore entry that
    is exactly a COPYed path or a parent directory of one -- `frontend`,
    `frontend/`, `./frontend`, `app` -- which is the way this actually gets
    broken (someone excludes a directory to slim the context). A wildcard that
    happens to match is out of scope and is caught one layer out by Task 7's CI
    build, which is the only check that runs a real docker.
    """
    ignored = _ignored_patterns()
    cancelled = sorted(
        src
        for src in _copied_sources()
        for anc in [src, *(p.as_posix() for p in Path(src).parents if p.as_posix() != ".")]
        if anc in ignored
    )
    assert cancelled == [], (
        f".dockerignore excludes {cancelled}, which the Dockerfile COPYs. "
        "The build would silently produce an image missing them."
    )
