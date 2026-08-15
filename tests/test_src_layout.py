"""`app` must resolve from `src/`, and from nowhere else.

S8.7 moves the package. Three ways that fails SILENTLY, all of which leave a
GREEN suite:

1. A STALE EDITABLE INSTALL. The venv at `.resume/` holds
   `_editable_impl_depth_eval_engine.pth`, generated at install time against
   the OLD layout. Until `pip install -e .` is re-run it can resolve `app` to
   a path the tree no longer has.
2. A MISSING PYTHONPATH in some context nobody checked -- the ~20 smoke
   scripts launch `python -m uvicorn app.main:app` as SUBPROCESSES with
   `cwd=ROOT`, so pytest's `pythonpath` never reaches them.
3. A LEFTOVER `app/` AT THE REPOSITORY ROOT -- the worst outcome of a
   half-completed `git mv`, because every import resolves to it quietly and
   the whole suite passes against code that is no longer the code.

Derived from the live module object rather than a hand-maintained list, which
is the shape this repo has had to learn five times (conftest vs alembic/env.py,
the Dockerfile vs .dockerignore, the /ui denylist twice, and
test_ratelimit_wiring's LIMITED tuple).
"""

from __future__ import annotations

from pathlib import Path

import app

ROOT = Path(__file__).resolve().parents[1]


def test_the_package_resolves_from_src():
    resolved = Path(app.__file__).resolve()
    assert resolved.parents[1] == ROOT / "src", (
        f"`import app` resolved to {resolved} -- expected it under "
        f"{ROOT / 'src'}. A stale editable install, a missing PYTHONPATH, or "
        f"a leftover app/ at the repo root would all look like this."
    )


def test_no_package_directory_survives_at_the_repo_root():
    """The half-completed move. `import app` above could still be correct
    while a partial copy sits at the root shadowing nothing yet."""
    assert not (ROOT / "app").exists(), (
        "app/ still exists at the repository root after the move to src/app/"
    )
