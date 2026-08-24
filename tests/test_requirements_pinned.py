"""requirements.txt is the LOCK; pyproject.toml is the supported RANGE.

WHY THIS GUARD EXISTS. Every dependency was an unbounded `>=` until FastAPI
0.141 deleted ``fastapi.dependencies.utils.get_flat_dependant``. CI resolved
0.141.1 while the development machine had 0.138.0, so five test modules failed
at COLLECTION time in CI while 2086 tests were green locally. The same
unbounded resolution reaches the Dockerfile, so two image builds a week apart
could ship different frameworks into production.

Pinning fixed that once. This file is what stops it coming back: a pin that
goes unbounded, or a lock that drifts out of the range pyproject advertises, is
invisible to every other test in the suite -- the failure only shows up on
another machine, which is the whole problem.

Same shape as tests/test_migrations.py's metadata drift guard and
tests/test_route_table_guard.py: derive from the live artifact, so nobody has
to remember to extend a hand-written list.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
PYPROJECT = ROOT / "pyproject.toml"


def _requirement_lines() -> list[str]:
    """Every real requirement line, comments and blanks stripped."""
    out = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _locked() -> dict[str, Requirement]:
    return {r.name.lower(): r for r in (Requirement(l) for l in _requirement_lines())}


def _declared() -> dict[str, Requirement]:
    """pyproject's direct dependencies, runtime + the dev extra."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    specs = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specs.extend(extra)
    return {r.name.lower(): r for r in (Requirement(s) for s in specs)}


def test_the_lock_is_not_empty():
    """A parser that silently matched nothing would make every test below
    vacuous -- they are all `for x in <collection>` and pass on empty."""
    assert len(_locked()) >= 15, f"only parsed {len(_locked())} requirements"


def test_every_dependency_is_pinned_to_an_exact_version():
    """`>=` is what let CI and this machine install different FastAPIs."""
    unpinned = []
    for name, req in _locked().items():
        specs = list(req.specifier)
        if len(specs) != 1 or specs[0].operator != "==":
            unpinned.append(f"{name}: {req.specifier or '(no specifier at all)'}")
    assert not unpinned, "requirements.txt must pin exactly:\n  " + "\n  ".join(unpinned)


def test_every_pin_satisfies_the_range_pyproject_advertises():
    """The two files are edited by different hands at different times. A lock
    outside its declared range means `pip install -e .` and
    `pip install -r requirements.txt` build DIFFERENT environments -- this
    repo's recurring defect (a rule at one door and not the other) wearing a
    packaging costume.
    """
    declared = _declared()
    problems = []
    for name, req in _locked().items():
        if name not in declared:
            continue
        version = Version(str(req.specifier).lstrip("="))
        if not declared[name].specifier.contains(version, prereleases=True):
            problems.append(
                f"{name}=={version} violates pyproject's "
                f"{declared[name].specifier}"
            )
    assert not problems, "lock/range drift:\n  " + "\n  ".join(problems)


def test_the_two_files_describe_the_same_dependency_set():
    """A dependency in one file and not the other is a dependency nobody is
    reasoning about as a whole. Names only -- the versions are the tests above.
    """
    locked, declared = set(_locked()), set(_declared())
    assert locked == declared, (
        f"only in requirements.txt: {sorted(locked - declared)}\n"
        f"only in pyproject.toml:  {sorted(declared - locked)}"
    )


def test_the_extras_that_change_what_is_installed_are_locked_too():
    """`uvicorn[standard]` and `psycopg[binary]` pull in whole extra dependency
    sets. Dropping the extra installs a DIFFERENT thing under the same version,
    and psycopg without [binary] needs a compiler that the image does not have.
    """
    locked = _locked()
    assert locked["uvicorn"].extras == {"standard"}, locked["uvicorn"]
    assert locked["psycopg"].extras == {"binary"}, locked["psycopg"]
