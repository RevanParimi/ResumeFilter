"""The instrument must not share the extractor's eyes (spec 3.1, ruling R1).

An evidence detector imported from the thing being measured cannot see that
thing's blind spot. This is enforced, not documented -- widening the extractor's
_DEGREE in this same sprint is exactly the change that would otherwise switch
the education check off without a single test going red.
"""

import ast
from pathlib import Path

import pytest

COVERAGE_PY = Path(__file__).parent.parent / "src" / "app" / "candidates" / "coverage.py"

FORBIDDEN = {"app.candidates.extractor", "app.candidates.dates"}
#: A declaration, not detection logic -- ruling R1.
ALLOWED_APP_IMPORTS = {
    "app.candidates.schema",
    "app.candidates.sections",
    "app.schemas.extraction",
}


def _check_imports(tree: ast.AST) -> set[str]:
    """Ruling R12: relative imports are BANNED outright, not resolved.

    Without this, 'from . import extractor' has node.module=None and is
    silently dropped by the `and node.module` guard below, while
    'from .extractor import heuristic_profile' lands in `found` as the bare
    name 'extractor' -- which matches neither FORBIDDEN (an absolute dotted
    name) nor the "app."-prefix filter in test_coverage_imports_no_other_app_module.
    Both forbidden forms would pass both guards silently, and a relative
    import is the idiomatic (editor-autosuggested) form for reaching a
    sibling module in the same package. coverage.py has no legitimate
    relative import, so a blanket ban is simpler and safer than writing
    resolution logic for what a relative import would actually point to.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, (
                f"relative import (level={node.level}, module={node.module!r}) "
                f"forbidden -- ruling R12: absolute imports only"
            )
            if node.module:
                found.add(node.module)
    return found


def _imported_modules(path: Path) -> set[str]:
    return _check_imports(ast.parse(path.read_text(encoding="utf-8")))


def test_coverage_does_not_import_the_extractor_or_its_date_parser():
    imported = _imported_modules(COVERAGE_PY)
    assert not (imported & FORBIDDEN), (
        f"coverage.py imports {imported & FORBIDDEN}; see spec 3.1 -- an instrument "
        f"that detects evidence with the extractor's own code is blind exactly where "
        f"the extractor is"
    )


def test_coverage_imports_no_other_app_module():
    app_imports = {m for m in _imported_modules(COVERAGE_PY) if m.startswith("app.")}
    assert app_imports <= ALLOWED_APP_IMPORTS, f"unexpected app imports: {app_imports - ALLOWED_APP_IMPORTS}"


def test_relative_import_of_the_extractor_cannot_dodge_the_guard():
    """Ruling R12, the non-vacuous half of the ban: proves the level check
    actually rejects both escape-hatch forms identified in review --
    'from . import extractor' (module=None) and 'from .extractor import x'
    (module='extractor', matching neither FORBIDDEN nor the app.-prefix
    filter). Asserted against a parsed source STRING, never a real file, so
    this test can never leave a broken module behind."""
    with pytest.raises(AssertionError):
        _check_imports(ast.parse("from . import extractor\n"))
    with pytest.raises(AssertionError):
        _check_imports(ast.parse("from .extractor import heuristic_profile\n"))


def test_coverage_still_fires_when_the_extractor_is_blind():
    """The non-vacuous half: a shape the extractor CANNOT read, which coverage
    reads anyway. If someone re-points coverage at _DEGREE, this goes red.

    Ruling R11 (controller, task 6): the brief's original assertion --
    `{g.id for g in cov.gaps} >= {"education_not_extracted"} or profile.education`
    -- is a disjunction that Task 10 of this same sprint silently empties.
    Task 10 widens the extractor's _DEGREE regex to read spelled-out degrees,
    so `profile.education` becomes non-empty for this exact fixture and the
    assertion is satisfied by the right-hand disjunct forever after, without
    assess_coverage's own detector ever having to fire. A test a later task in
    the same sprint quietly empties is worse than no test.

    Replaced with a direct assertion that coverage's own evidence scanner
    (looks_academic) recognises a spelled-out degree on its own terms, plus an
    assess_coverage call against a profile whose education is deliberately,
    permanently empty -- so the gap must fire regardless of what the extractor
    does or ever learns to read.
    """
    from app.candidates.coverage import assess_coverage, looks_academic
    from app.candidates.schema import CandidateProfile

    spelled_out = "Bachelor of Technology in Computer Science, VIT Vellore, 2015"
    # Coverage's own detector, exercised directly -- no extractor involved.
    assert looks_academic(spelled_out)

    text = f"""Rahul Verma
rahul@example.com  +91 98765 43210

ACADEMIC BACKGROUND
{spelled_out}
Master of Business Administration, IIM Bangalore, 2019

SKILLS
Python, SQL
"""
    # profile.education is empty ON PURPOSE: this test does not care whether
    # the extractor can read spelled-out degrees (Task 10 makes it able to),
    # only that coverage's own scanner reports the gap when it is empty.
    profile = CandidateProfile()
    cov = assess_coverage(text, profile, min_chars=50)
    assert "education_not_extracted" in {g.id for g in cov.gaps}
