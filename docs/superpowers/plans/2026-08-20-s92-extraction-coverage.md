# S9.2 Extraction Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the extractor's silent drops loud — an advisory assessment that reports where the resume evidently states something the extracted profile does not carry — then fix the four drops it names.

**Architecture:** A pure `coverage.py` compares raw resume text to the extracted `CandidateProfile` using its own deliberately crude evidence detectors, never the extractor's. It is computed once inside `extract_profile`, so both the LLM and heuristic paths are measured by the same instrument, and rides to the `Report` by the path `resume_farm` already uses. Four one-line extractor fixes follow, each with the measured before/after as its test.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLAlchemy (untouched here), pytest. No new dependency.

**Spec:** [docs/superpowers/specs/2026-08-20-s92-extraction-coverage-design.md](../specs/2026-08-20-s92-extraction-coverage-design.md)

## Global Constraints

- **TDD, every test seen red first.** Fully offline — no network, no API key, no billed call.
- **Advisory only.** Coverage never changes a score, band, threshold or verdict, and is never a rejection signal. No auto-reject anywhere.
- **No new dependency, no migration, no new table, no new `ConsentPurpose`, no new erasure path.**
- **`coverage.py` may import only stdlib, `app.candidates.schema`, `app.candidates.sections` and `app.schemas.extraction`.** Importing `app.candidates.extractor` or `app.candidates.dates` is a plan violation — see Ruling R1.
- **Every check fires on empty, never on "fewer than expected"** (spec §3.3).
- **A refusal carries no gaps** — `insufficient_data` means no gaps at all, never an empty-looking clean result.
- Tunables in `config.yaml` with a `coverage_` prefix, mirrored on `Settings`. Secrets stay in `.env` with `DEE_*`.
- Commit messages: **no `Co-Authored-By` trailer.**
- Baseline to beat: **1996 passing** (`pytest -q`, exit 0), `main` at `016f91f`. Branch: `s92-extraction-coverage` (already created; the spec is committed at `d94930b`).

## Ruling R1 — the alias table is data, and data may be shared

Spec §3.1 forbids coverage from sharing the extractor's eyes. Writing the plan surfaced a case the spec did not resolve: the `section_unrecognized` check is *defined* in terms of what the extractor recognizes, so it cannot avoid knowing the alias list.

**Ruling:** the blind spot §3.1 warns about is shared *detection logic*, not shared *declarations*. Task 3 moves `_SECTION_ALIASES` into a new `app/candidates/sections.py` owned by neither module. Coverage imports the **table** and does its own crude header normalization; it must not import the extractor's normalization function, its regexes, or `dates.py`.

**And `section_unrecognized` is a hint, not a detector.** If the extractor's header handling breaks, the load-bearing check that fires is `experience_not_extracted` — which is fully independent and does not consult the alias table at all. Coverage's four "field empty despite evidence" checks are the instrument; the fifth explains *why* and is allowed to be imperfect.

## Ruling R2 — treat the code in this plan as intent, never as runnable

S9.1's plan carried reference code that was wrong **six times**, and execution caught every one while reading caught none. The names below were read out of the real files while writing this plan, but **verify every symbol against the file before trusting it**, and if a snippet does not fit reality, the reality wins — record the delta and continue.

Names verified on `016f91f`: `heuristic_profile`, `extract_profile`, `ExtractionResult(profile, method, warnings)`, `CandidateProfile`, `ContactInfo.email/.phone`, `ExtractedStr(value, confidence, span)`, `Settings`, `EvaluationState`, `EvaluationEngine.evaluate`, `Report`, `CandidateCreateResponse`, `Smoke/base_env/client/uvicorn_argv/wait_healthy` in `scripts/_smoke.py`, `FakeLLM(script=...)` in `tests/conftest.py`.

## File Structure

| File | Responsibility |
|---|---|
| `src/app/schemas/extraction.py` | **Create.** `CoverageBand`, `GapSeverity`, `CoverageGap`, `ExtractionCoverage` — the wire contract, mirroring `schemas/fabrication.py`'s shape |
| `src/app/candidates/sections.py` | **Create.** `SECTION_ALIASES` — the declaration, moved out of `extractor.py` (R1) |
| `src/app/candidates/coverage.py` | **Create.** The instrument: evidence scanners + `assess_coverage()` |
| `src/app/candidates/extractor.py` | **Modify.** Import the moved table; the four fixes; call `assess_coverage` in `extract_profile` |
| `src/app/candidates/schema.py` | **Modify.** `ExtractionResult.coverage` |
| `src/app/core/config.py` + `config.yaml` | **Modify.** Three `coverage_` knobs |
| `src/app/graph/state.py`, `graph/build.py`, `graph/nodes/report.py` | **Modify.** Thread coverage to the `Report`, one summary sentence at `major_gaps` |
| `src/app/schemas/report.py` | **Modify.** `Report.extraction_coverage` |
| `src/app/screening/ingest.py`, `src/app/api/routes.py` | **Modify.** Pass coverage to `evaluate`; surface it on the ingest response |
| `tests/test_extraction_coverage.py` | **Create.** The instrument's own tests |
| `tests/test_extraction_coverage_independence.py` | **Create.** The R1 guard |
| `tests/test_extractor_shape_corpus.py` | **Create.** One fixture per resume shape |
| `scripts/mutate_s92.py`, `scripts/smoke_s92.py` | **Create.** Committed mutation pass; live-server smoke |
| `CANDIDATES.md`, `SIGNALS.md`, `docs/ROADMAP.md` | **Modify.** Docs |

---

### Task 1: The wire contract

**Files:**
- Create: `src/app/schemas/extraction.py`
- Test: `tests/test_extraction_coverage.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CoverageBand` (StrEnum: `INSUFFICIENT_DATA="insufficient_data"`, `COMPLETE="complete"`, `MINOR_GAPS="minor_gaps"`, `MAJOR_GAPS="major_gaps"`); `GapSeverity` (StrEnum: `MINOR="minor"`, `MAJOR="major"`); `CoverageGap(id: str, detail: str, severity: GapSeverity = MINOR, field: Optional[str] = None, header: Optional[str] = None)`; `ExtractionCoverage(band: CoverageBand = INSUFFICIENT_DATA, gaps: list[CoverageGap] = [], checks_run: int = 0, truncated: bool = False, advisory: bool = True)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction_coverage.py
"""S9.2 extraction coverage: what the resume says that the profile does not carry."""

from app.schemas.extraction import (
    CoverageBand,
    CoverageGap,
    ExtractionCoverage,
    GapSeverity,
)


def test_default_assessment_is_a_refusal():
    """The default must be 'we could not say', never 'we looked and it was clean'.

    Same posture as CrossFieldAssessment, whose band defaults to
    INSUFFICIENT_DATA -- a result that could not be taken must not read as a
    result that came back fine.
    """
    cov = ExtractionCoverage()
    assert cov.band is CoverageBand.INSUFFICIENT_DATA
    assert cov.gaps == []
    assert cov.checks_run == 0
    assert cov.truncated is False
    assert cov.advisory is True


def test_gap_defaults_to_minor():
    gap = CoverageGap(id="section_unrecognized", detail="header 'Career History' not recognized")
    assert gap.severity is GapSeverity.MINOR
    assert gap.field is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.extraction'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/schemas/extraction.py
"""Extraction-coverage contracts (S9.2).

ADVISORY ONLY: coverage says what the PARSER may have missed, never anything
about the candidate. It feeds no score, no band and no verdict, and it is never
a rejection signal.

Lives in app/schemas/ rather than app/candidates/ so app/schemas/report.py
composes it the way it already composes app/schemas/fabrication.py -- the
Report's imports stay inside one package.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class CoverageBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    COMPLETE = "complete"
    MINOR_GAPS = "minor_gaps"
    MAJOR_GAPS = "major_gaps"


class GapSeverity(StrEnum):
    """MAJOR = a field the text evidently describes is entirely absent.
    MINOR = informational; the profile is populated but something was odd.

    Deliberately NOT app.schemas.fabrication.FindingSeverity: reusing that enum
    would couple extraction quality to fabrication semantics, and a coverage gap
    is a statement about our parser, not about the candidate.
    """

    MINOR = "minor"
    MAJOR = "major"


class CoverageGap(BaseModel):
    """One thing the resume appears to state that the profile does not carry."""

    id: str  # stable check id, e.g. "experience_not_extracted"
    detail: str
    severity: GapSeverity = GapSeverity.MINOR
    field: Optional[str] = None   # profile field involved, e.g. "experience"
    #: The literal section header, for `section_unrecognized` ONLY. The only
    #: place coverage quotes the resume; a header is not personal data and it is
    #: length-bounded, because the report body is stored (S7.2's claim_ref).
    header: Optional[str] = None


class ExtractionCoverage(BaseModel):
    """Did the extractor read what the resume actually says?

    A refusal (INSUFFICIENT_DATA) carries NO gaps -- see S9.1's SIGNALS.md: a
    measurement that could not be taken must not be readable as one that was.
    """

    band: CoverageBand = CoverageBand.INSUFFICIENT_DATA
    gaps: list[CoverageGap] = Field(default_factory=list)
    checks_run: int = 0
    truncated: bool = False   # gaps were capped at coverage_max_gaps
    advisory: bool = True     # mirrors Report: never a rejection signal
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/app/schemas/extraction.py tests/test_extraction_coverage.py
git commit -m "feat(s92): extraction-coverage contracts, defaulting to a refusal"
```

---

### Task 2: Config knobs

**Files:**
- Modify: `src/app/core/config.py` (add after the S2.4 fabrication block)
- Modify: `config.yaml`
- Test: `tests/test_extraction_coverage.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.coverage_min_chars: int = 200`, `Settings.coverage_max_header_chars: int = 60`, `Settings.coverage_max_gaps: int = 20`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extraction_coverage.py
from app.core.config import Settings


def test_coverage_knobs_have_conservative_defaults():
    s = Settings(_env_file=None)
    assert s.coverage_min_chars == 200
    assert s.coverage_max_header_chars == 60
    assert s.coverage_max_gaps == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extraction_coverage.py::test_coverage_knobs_have_conservative_defaults -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'coverage_min_chars'`

- [ ] **Step 3: Write minimal implementation**

In `src/app/core/config.py`, after the S2.4 fabrication-risk block:

```python
    # --- Signal quality (PI-9, S9.2): extraction coverage ----------------------
    # Does the extracted profile carry what the resume evidently says? ADVISORY:
    # a gap is a statement about the PARSER, never about the candidate, and it
    # feeds no score. Below coverage_min_chars the assessment REFUSES rather
    # than reporting a clean result on a document too short to judge.
    coverage_min_chars: int = 200
    coverage_max_header_chars: int = 60
    coverage_max_gaps: int = 20
```

In `config.yaml`, mirroring the block above (find the `fabrication risk` block and add after it):

```yaml
# --- Signal quality (PI-9, S9.2): extraction coverage ---
coverage_min_chars: 200          # below this -> band "insufficient_data", no gaps
coverage_max_header_chars: 60    # bound on the one quoted resume line
coverage_max_gaps: 20            # cap; `truncated` says so when it bites
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/app/core/config.py config.yaml tests/test_extraction_coverage.py
git commit -m "feat(s92): coverage knobs, mirrored in config.yaml"
```

---

### Task 3: Move the section-alias table (pure move, R1)

**Files:**
- Create: `src/app/candidates/sections.py`
- Modify: `src/app/candidates/extractor.py:58-73` (delete `_SECTION_ALIASES`, import it instead)
- Test: existing suite is the test — this task adds none

**Interfaces:**
- Consumes: nothing.
- Produces: `app.candidates.sections.SECTION_ALIASES: dict[str, tuple[str, ...]]` — identical content to the old `_SECTION_ALIASES`.

**This commit changes no behaviour.** Per the S8.7 pure-move discipline, a move and a logic edit never share a commit, so `git log --follow` and a reviewer can both tell a rename from a change.

- [ ] **Step 1: Create the new module**

```python
# src/app/candidates/sections.py
"""Resume section headers the extractor recognizes (S1.1), as data.

MOVED OUT OF extractor.py in S9.2 so app/candidates/coverage.py can ask what is
recognized WITHOUT importing the extractor. Spec §3.1 forbids coverage from
sharing the extractor's detection LOGIC; a declaration is not logic (plan
ruling R1), and this file deliberately contains no functions.
"""

from __future__ import annotations

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": ("education", "academics", "academic background", "qualifications"),
    "experience": (
        "experience", "work experience", "professional experience",
        "employment", "employment history", "work history",
    ),
    "skills": ("skills", "technical skills", "core skills", "skill set", "technologies"),
    "projects": ("projects", "personal projects", "key projects", "academic projects"),
    "certifications": (
        "certifications", "certificates", "licenses",
        "licenses & certifications", "courses & certifications",
    ),
}
```

- [ ] **Step 2: Delete the old definition and import the new one**

In `src/app/candidates/extractor.py`, delete the `_SECTION_ALIASES = {...}` literal and add to the imports:

```python
from app.candidates.sections import SECTION_ALIASES
```

Then replace the one use inside `_split_sections`:

```python
    alias_to_section = {
        alias: section
        for section, aliases in SECTION_ALIASES.items()
        for alias in aliases
    }
```

- [ ] **Step 3: Run the extractor suites to prove nothing moved but the file**

Run: `python -m pytest tests/test_candidate_extractor_heuristic.py tests/test_candidate_extractor_llm.py -q`
Expected: PASS, same count as before the move

- [ ] **Step 4: Commit**

```bash
git add src/app/candidates/sections.py src/app/candidates/extractor.py
git commit -m "refactor(s92): SECTION_ALIASES becomes data both modules can read

Pure move, no behaviour change. coverage.py must be able to ask what the
extractor recognizes without importing the extractor (spec 3.1, ruling R1),
and a declaration is not detection logic."
```

---

### Task 4: The evidence scanners

**Files:**
- Create: `src/app/candidates/coverage.py`
- Test: `tests/test_extraction_coverage.py`

**Interfaces:**
- Consumes: `SECTION_ALIASES` (Task 3).
- Produces: `is_header_shaped(line: str) -> bool`; `normalized_header(line: str) -> str`; `blocks(text: str) -> list[tuple[Optional[str], list[str]]]` — `(header_or_None, content_lines)`, first block's header is `None`; `looks_dated_role(line: str) -> bool`; `looks_academic(line: str) -> bool`; `known_aliases() -> dict[str, str]`. Module-private regexes `_EMAILISH` and `_PHONEISH` are used by Task 5.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extraction_coverage.py
from app.candidates.coverage import blocks, is_header_shaped, looks_academic, looks_dated_role


def test_header_shaped_accepts_real_headers_and_rejects_content():
    assert is_header_shaped("EXPERIENCE")
    assert is_header_shaped("Career History")
    assert is_header_shaped("Work Experience:")
    # Content lines are not headers.
    assert not is_header_shaped("- Senior Data Engineer, Acme Analytics (2019 - Present)")
    assert not is_header_shaped("priya@example.com")
    assert not is_header_shaped(
        "Built the ingestion pipeline handling four million events a day for the team"
    )


def test_blocks_groups_content_under_its_header():
    text = "Priya Sharma\n\nCAREER HISTORY\n- Engineer, Acme (2015 - 2019)\n"
    got = blocks(text)
    assert got[0][0] is None and got[0][1] == ["Priya Sharma"]
    assert got[1][0] == "CAREER HISTORY"
    assert got[1][1] == ["- Engineer, Acme (2015 - 2019)"]


def test_dated_role_needs_two_points_or_a_present_marker():
    assert looks_dated_role("Senior Data Engineer, Acme Analytics (2019 - Present)")
    assert looks_dated_role("- Data Engineer, Foo Systems (2015 - 2019)")
    assert not looks_dated_role("Data Engineer, Foo Systems")
    assert not looks_dated_role("Shipped 2019 revenue dashboards")  # one year, no range


def test_academic_lines_are_not_counted_as_roles():
    assert looks_academic("B.Tech in Computer Science, NIT Trichy, 2014 - 2018")
    assert looks_academic("Bachelor of Technology, VIT Vellore, 2015")
    assert looks_academic("CGPA: 8.6/10")
    assert not looks_academic("Senior Data Engineer, Acme Analytics (2019 - Present)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/candidates/coverage.py
"""Extraction coverage (S9.2): what the resume evidently says that the
extracted profile does not carry.

THIS MODULE DOES NOT SHARE THE EXTRACTOR'S EYES, and that is the whole design.
An instrument that detects evidence with the same code the extractor parses
with cannot see that code's blind spot: point this file at `_DEGREE` and the
moment S9.2 widens `_DEGREE` the education check stops firing, while leaving it
narrow makes the check agree with the extractor that there was nothing there.
Either way it reports `complete` on the exact resume it exists to catch.

So every scanner below is deliberately cruder than the extractor's: broad word
lists and a bare four-digit-year regex, owned here. `app.candidates.extractor`
and `app.candidates.dates` must never appear in this file's imports --
tests/test_extraction_coverage_independence.py fails the build if they do.

The one thing it does import is SECTION_ALIASES, which is a DECLARATION rather
than detection logic (plan ruling R1): the `section_unrecognized` gap is defined
in terms of what the extractor recognizes, so it cannot avoid knowing the list.
That gap is a HINT, not a detector -- if header handling breaks, the check that
actually fires is `experience_not_extracted`, which consults no table at all.
"""

from __future__ import annotations

import re
from typing import Optional

from app.candidates.sections import SECTION_ALIASES

#: Our own year scanner. Deliberately not app.candidates.dates.date_points.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_PRESENT = re.compile(r"\b(?:present|current|till date|to date|ongoing|now)\b", re.IGNORECASE)
#: Broader than the extractor's _DEGREE on purpose -- this is the check that has
#: to still fire when the extractor's regex is the thing that is wrong.
_DEGREE_WORDS = (
    "bachelor", "master", "b.tech", "btech", "m.tech", "mtech", "b.e", "b.sc",
    "m.sc", "bca", "mca", "mba", "bba", "b.com", "m.com", "b.a", "m.a",
    "phd", "ph.d", "diploma", "degree", "graduation", "post graduate",
)
_GRADEISH = re.compile(r"\b(?:cgpa|gpa|percentage|marks)\b|\d{2,3}(?:\.\d+)?\s*%", re.IGNORECASE)
_EMAILISH = re.compile(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
_PHONEISH = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")
_BULLETISH = re.compile(r"^[-•*·]\s*")


def is_header_shaped(line: str) -> bool:
    """A short, capitalised, undated line that reads like a section header."""
    s = _BULLETISH.sub("", line).strip().rstrip(":").strip()
    if not s or len(s) > 48:
        return False
    if _YEAR.search(s) or "@" in s:
        return False
    words = s.split()
    if not 1 <= len(words) <= 5:
        return False
    alpha = [w for w in words if w[:1].isalpha()]
    if not alpha:
        return False
    if s.isupper():
        return True
    return all(w[:1].isupper() for w in alpha)


def normalized_header(line: str) -> str:
    """Crude, coverage-owned header normalization: strip decoration and case.

    Intentionally NOT the extractor's version. If the two disagree, the
    disagreement is itself information (see the module docstring on R1).
    """
    s = _BULLETISH.sub("", line).strip().rstrip(":").strip()
    s = re.sub(r"\([^)]*\)", "", s)          # "WORK EXPERIENCE (5 YEARS)"
    s = re.sub(r"[ـ_\-–—=~]{2,}", "", s)      # "Experience ------"
    return " ".join(s.split()).strip(" :.-–—").lower()


def blocks(text: str) -> list[tuple[Optional[str], list[str]]]:
    """[(header or None, [content lines])]. The first block's header is None."""
    out: list[tuple[Optional[str], list[str]]] = [(None, [])]
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if is_header_shaped(line):
            out.append((line, []))
        else:
            out[-1][1].append(line)
    return out


def looks_academic(line: str) -> bool:
    """A degree word or a grade token -- education evidence, not a role."""
    low = line.lower()
    return any(w in low for w in _DEGREE_WORDS) or bool(_GRADEISH.search(line))


def looks_dated_role(line: str) -> bool:
    """Two year tokens, or one plus a Present-style marker."""
    years = _YEAR.findall(line)
    if len(years) >= 2:
        return True
    return len(years) == 1 and bool(_PRESENT.search(line))


def known_aliases() -> dict[str, str]:
    """alias -> section, from the shared declaration (R1)."""
    return {a: s for s, aliases in SECTION_ALIASES.items() for a in aliases}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/coverage.py tests/test_extraction_coverage.py
git commit -m "feat(s92): coverage's own evidence scanners, deliberately cruder than the extractor's"
```

---

### Task 5: `assess_coverage` — the five checks, the bands, the refusal

**Files:**
- Modify: `src/app/candidates/coverage.py`
- Test: `tests/test_extraction_coverage.py`

**Interfaces:**
- Consumes: Task 1's types, Task 4's scanners.
- Produces: `assess_coverage(text: str, profile: CandidateProfile, *, min_chars: int = 200, max_header_chars: int = 60, max_gaps: int = 20) -> ExtractionCoverage`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extraction_coverage.py
from app.candidates.coverage import assess_coverage
from app.candidates.schema import CandidateProfile, ContactInfo, EducationEntry, ExtractedStr, SkillItem

BULLETED = """Priya Sharma
Senior Data Engineer | Bengaluru
priya@example.com  +91 98765 43210

EXPERIENCE
- Senior Data Engineer, Acme Analytics (2019 - Present)
- Data Engineer, Foo Systems (2015 - 2019)

EDUCATION
B.Tech in Computer Science, IIT Delhi, CGPA: 8.6/10
"""


def _profile(**kw) -> CandidateProfile:
    return CandidateProfile(**kw)


def test_short_text_refuses_and_carries_no_gaps():
    """The refusal is the design. An empty-looking clean result would be a lie."""
    cov = assess_coverage("Priya Sharma\npriya@example.com", _profile(), min_chars=200)
    assert cov.band is CoverageBand.INSUFFICIENT_DATA
    assert cov.gaps == []
    assert cov.checks_run == 0


def test_dropped_experience_is_a_major_gap():
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="priya@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
    )  # experience deliberately empty -- the measured defect
    cov = assess_coverage(BULLETED, profile, min_chars=50)
    assert cov.band is CoverageBand.MAJOR_GAPS
    ids = {g.id for g in cov.gaps}
    assert "experience_not_extracted" in ids
    gap = next(g for g in cov.gaps if g.id == "experience_not_extracted")
    assert gap.severity is GapSeverity.MAJOR
    assert gap.field == "experience"


def test_a_genuine_fresher_reports_complete():
    """No work history is not a gap. This is the false positive that would
    make the whole instrument untrustworthy, so it gets its own test."""
    text = """Anita Rao
anita@example.com  +91 98765 43210

EDUCATION
B.Tech in Computer Science, VIT Vellore, 2019 - 2023, CGPA: 8.1/10

SKILLS
Python, SQL, Pandas

PROJECTS
Campus placement portal built with Django
"""
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="anita@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
    )
    cov = assess_coverage(text, profile, min_chars=50)
    assert cov.band is CoverageBand.COMPLETE
    assert cov.gaps == []


def test_unrecognized_header_is_minor_when_nothing_was_dropped():
    text = BULLETED.replace("EXPERIENCE", "CAREER HISTORY")
    profile = _profile(
        contact=ContactInfo(email=ExtractedStr(value="priya@example.com")),
        education=[EducationEntry(degree="B.Tech")],
        skills=[SkillItem(name="Python")],
        experience=[],
    )
    cov = assess_coverage(text, profile, min_chars=50)
    ids = {g.id for g in cov.gaps}
    assert "section_unrecognized" in ids
    hint = next(g for g in cov.gaps if g.id == "section_unrecognized")
    assert hint.severity is GapSeverity.MINOR
    assert hint.header == "CAREER HISTORY"


def test_header_quote_is_bounded():
    long_header = "Career " + "History " * 20
    text = f"Priya Sharma\npriya@example.com\n\n{long_header}\nSome content line here\n" + "x" * 300
    cov = assess_coverage(text, _profile(), min_chars=50, max_header_chars=20)
    for gap in cov.gaps:
        if gap.header is not None:
            assert len(gap.header) <= 20


def test_gaps_are_capped_and_say_so():
    text = BULLETED + "\n" + "\n".join(f"Section {i}\ncontent {i}" for i in range(30))
    cov = assess_coverage(text, _profile(), min_chars=50, max_gaps=3)
    assert len(cov.gaps) == 3
    assert cov.truncated is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: FAIL — `ImportError: cannot import name 'assess_coverage'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/app/candidates/coverage.py` — **move the three import lines up to the existing import block at the top of the file**, Python allows them here but nothing else in this repo does it:

```python
from app.candidates.schema import CandidateProfile
from app.schemas.extraction import (
    CoverageBand,
    CoverageGap,
    ExtractionCoverage,
    GapSeverity,
)

_EDU_HEADER = re.compile(r"education|academic|qualification", re.IGNORECASE)
_SKILL_HEADER = re.compile(r"skill|technolog|competenc|tech stack", re.IGNORECASE)


def assess_coverage(
    text: str,
    profile: CandidateProfile,
    *,
    min_chars: int = 200,
    max_header_chars: int = 60,
    max_gaps: int = 20,
) -> ExtractionCoverage:
    """Compare the resume text with what was extracted from it.

    Every check fires on EMPTY, never on 'fewer than expected' (spec 3.3):
    telling one role spanning two lines from two roles needs a magic ratio, and
    a false positive there accuses a correct extraction.
    """
    if len((text or "").strip()) < min_chars:
        return ExtractionCoverage()  # refusal: no band, no gaps, nothing to read

    parsed = blocks(text)
    aliases = known_aliases()
    gaps: list[CoverageGap] = []

    # 1. experience --------------------------------------------------------
    role_lines = [
        line
        for header, content in parsed
        for line in content
        if not (header and _EDU_HEADER.search(header))
        and looks_dated_role(line)
        and not looks_academic(line)
    ]
    if role_lines and not profile.experience:
        gaps.append(CoverageGap(
            id="experience_not_extracted",
            detail=(
                f"the resume has {len(role_lines)} dated role-shaped line(s) but no "
                f"experience entry was extracted"
            ),
            severity=GapSeverity.MAJOR,
            field="experience",
        ))

    # 2. education ---------------------------------------------------------
    edu_lines = [
        line for _, content in parsed for line in content if looks_academic(line)
    ]
    if edu_lines and not profile.education:
        gaps.append(CoverageGap(
            id="education_not_extracted",
            detail=(
                f"the resume has {len(edu_lines)} degree- or grade-bearing line(s) but "
                f"no education entry was extracted"
            ),
            severity=GapSeverity.MAJOR,
            field="education",
        ))

    # 3. skills ------------------------------------------------------------
    skill_content = [
        content for header, content in parsed
        if header and _SKILL_HEADER.search(header) and content
    ]
    if skill_content and not profile.skills:
        gaps.append(CoverageGap(
            id="skills_not_extracted",
            detail="the resume has a populated skills section but no skill was extracted",
            severity=GapSeverity.MAJOR,
            field="skills",
        ))

    # 4. contact -----------------------------------------------------------
    has_contact_text = bool(_EMAILISH.search(text) or _PHONEISH.search(text))
    if has_contact_text and profile.contact.email is None and profile.contact.phone is None:
        gaps.append(CoverageGap(
            id="contact_not_extracted",
            detail="the resume carries an email or phone but neither was extracted",
            severity=GapSeverity.MAJOR,
            field="contact",
        ))

    # 5. unrecognized headers (a HINT, not a detector -- see the docstring) --
    for header, content in parsed:
        if header is None or not content:
            continue
        if normalized_header(header) in aliases:
            continue
        gaps.append(CoverageGap(
            id="section_unrecognized",
            detail="a section header the extractor does not recognize",
            severity=GapSeverity.MINOR,
            header=header.strip()[:max_header_chars],
        ))

    truncated = len(gaps) > max_gaps
    kept = gaps[:max_gaps]
    if any(g.severity is GapSeverity.MAJOR for g in kept):
        band = CoverageBand.MAJOR_GAPS
    elif kept:
        band = CoverageBand.MINOR_GAPS
    else:
        band = CoverageBand.COMPLETE
    return ExtractionCoverage(
        band=band, gaps=kept, checks_run=5, truncated=truncated, advisory=True
    )
```

> **Note for the implementer:** `test_gaps_are_capped_and_say_so` may need its
> fixture adjusted once the cap logic is real — the point of the test is that
> `truncated` is `True` and `len(gaps) == max_gaps`, not the exact synthetic
> text. Adjust the fixture, never the assertion.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extraction_coverage.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/coverage.py tests/test_extraction_coverage.py
git commit -m "feat(s92): assess_coverage -- five checks, three bands, and a refusal that carries no gaps"
```

---

### Task 6: The independence guard (R1 / spec §3.1)

**Files:**
- Create: `tests/test_extraction_coverage_independence.py`

**Interfaces:**
- Consumes: `app.candidates.coverage`.
- Produces: nothing consumed by later tasks.

This is the test that keeps the sprint's central idea true after everyone has forgotten it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction_coverage_independence.py
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


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


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


def test_coverage_still_fires_when_the_extractor_is_blind():
    """The non-vacuous half: a shape the extractor CANNOT read, which coverage
    reads anyway. If someone re-points coverage at _DEGREE, this goes red."""
    from app.candidates.coverage import assess_coverage
    from app.candidates.extractor import heuristic_profile

    text = """Rahul Verma
rahul@example.com  +91 98765 43210

ACADEMIC BACKGROUND
Bachelor of Technology in Computer Science, VIT Vellore, 2015
Master of Business Administration, IIM Bangalore, 2019

SKILLS
Python, SQL
"""
    profile = heuristic_profile(text)
    cov = assess_coverage(text, profile, min_chars=50)
    assert {g.id for g in cov.gaps} >= {"education_not_extracted"} or profile.education, (
        "either the extractor read the spelled-out degrees, or coverage must say it did not"
    )
```

- [ ] **Step 2: Run test to verify it fails or passes for the right reason**

Run: `python -m pytest tests/test_extraction_coverage_independence.py -v`
Expected: PASS — but confirm the third test is **non-vacuous** by temporarily
returning `ExtractionCoverage()` from `assess_coverage` and seeing it go red.
Restore immediately.

- [ ] **Step 3: Commit**

```bash
git add tests/test_extraction_coverage_independence.py
git commit -m "test(s92): the instrument may not import the eyes it is auditing"
```

---

### Task 7: Wire coverage into `extract_profile` — one place, both doors

**Files:**
- Modify: `src/app/candidates/schema.py:166-172` (`ExtractionResult`)
- Modify: `src/app/candidates/extractor.py:563-595` (`extract_profile`)
- Test: `tests/test_extraction_coverage.py`

**Interfaces:**
- Consumes: `assess_coverage` (Task 5), `Settings` knobs (Task 2).
- Produces: `ExtractionResult.coverage: ExtractionCoverage`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extraction_coverage.py
import json

import pytest

from app.candidates.extractor import extract_profile
from app.services.llm import NullLLM
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_both_extraction_paths_are_measured_by_the_same_instrument():
    """The LLM path drops things too, and _is_empty is an ALL-of check that
    waves a partial LLM profile straight through. A rule applied at one door and
    not the other is this repo's signature defect (S7.1, S7.2, S7.3, S8.4a)."""
    settings = Settings(_env_file=None, openrouter_api_key="")

    heuristic = await extract_profile(BULLETED, llm=NullLLM(settings), settings=settings)

    # An LLM that returns a plausible profile with NO experience at all.
    payload = json.dumps({
        "full_name": {"value": "Priya Sharma", "confidence": 0.9, "source_excerpt": "Priya Sharma"},
        "contact": {"email": {"value": "priya@example.com", "confidence": 0.9,
                              "source_excerpt": "priya@example.com"}},
        "education": [{"degree": "B.Tech", "institution": "IIT Delhi", "confidence": 0.8,
                       "source_excerpt": "B.Tech"}],
        "skills": [{"name": "Python", "confidence": 0.8, "source_excerpt": "Python"}],
        "experience": [],
    })
    llm_result = await extract_profile(
        BULLETED, llm=FakeLLM({"RESUME:": payload}, settings), settings=settings
    )

    assert llm_result.method == "llm"
    assert heuristic.coverage.band is CoverageBand.MAJOR_GAPS
    assert llm_result.coverage.band is CoverageBand.MAJOR_GAPS
    assert "experience_not_extracted" in {g.id for g in heuristic.coverage.gaps}
    assert "experience_not_extracted" in {g.id for g in llm_result.coverage.gaps}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extraction_coverage.py::test_both_extraction_paths_are_measured_by_the_same_instrument -v`
Expected: FAIL — `AttributeError: 'ExtractionResult' object has no attribute 'coverage'`

- [ ] **Step 3: Write minimal implementation**

In `src/app/candidates/schema.py`:

```python
from app.schemas.extraction import ExtractionCoverage


class ExtractionResult(BaseModel):
    """Output of extract_profile(): the profile + how it was produced."""

    profile: CandidateProfile
    method: Literal["llm", "heuristic"]
    warnings: list[str] = Field(default_factory=list)
    #: S9.2: did the extractor read what the resume says? Computed HERE rather
    #: than in either path, so the LLM and heuristic doors are measured by one
    #: instrument. Defaults to a refusal.
    coverage: ExtractionCoverage = Field(default_factory=ExtractionCoverage)
```

In `src/app/candidates/extractor.py`, inside `extract_profile`, after
`normalize_profile(profile)` and before `hashing.apply_contact_hashes(...)`:

```python
    coverage = assess_coverage(
        resume_text,
        profile,
        min_chars=settings.coverage_min_chars,
        max_header_chars=settings.coverage_max_header_chars,
        max_gaps=settings.coverage_max_gaps,
    )
```

Add the import at the top: `from app.candidates.coverage import assess_coverage`,
add `coverage=coverage` to the returned `ExtractionResult(...)`, and add
`coverage=coverage.band.value` to the existing `log.info("profile_extracted", ...)` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extraction_coverage.py tests/test_candidate_extractor_heuristic.py tests/test_candidate_extractor_llm.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/schema.py src/app/candidates/extractor.py tests/test_extraction_coverage.py
git commit -m "feat(s92): measure coverage once, where both extraction paths meet"
```

---

### Task 8: Fix 1 — bulleted role lines are roles, not duties

**Files:**
- Modify: `src/app/candidates/extractor.py:251-290` (`_experience`)
- Test: `tests/test_extractor_shape_corpus.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change — `_experience(lines)` behaviour only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extractor_shape_corpus.py
"""One fixture per resume SHAPE (S9.2).

Each of these produced an empty section on main at 016f91f, measured. A future
extractor change that re-drops a shape fails here rather than in a smoke six
months later.
"""

from app.candidates.coverage import assess_coverage
from app.candidates.extractor import heuristic_profile
from app.schemas.extraction import CoverageBand

BULLETED_ROLES = """Priya Sharma
Senior Data Engineer | Bengaluru
priya@example.com  +91 98765 43210

EXPERIENCE
- Senior Data Engineer, Acme Analytics (2019 - Present)
- Data Engineer, Foo Systems (2015 - 2019)

EDUCATION
B.Tech in Computer Science, IIT Delhi, CGPA: 8.6/10
"""


def test_bulleted_role_lines_are_extracted_as_roles():
    p = heuristic_profile(BULLETED_ROLES)
    assert len(p.experience) == 2
    assert p.experience[0].title == "Senior Data Engineer"
    assert p.experience[0].employer == "Acme Analytics"
    assert p.experience[0].dates.is_current is True
    assert p.experience[1].employer == "Foo Systems"


def test_duties_under_a_role_are_still_duties():
    """The rule that must NOT break: a bulleted line under an unbulleted dated
    role is a duty, and must not become a second employment entry."""
    text = """Priya Sharma
priya@example.com

EXPERIENCE
Senior Data Engineer, Acme Analytics (2019 - Present)
- Rebuilt the ingestion path, cutting 2019 latency in half by 2020
- Led a team of four

EDUCATION
B.Tech in Computer Science, IIT Delhi, CGPA: 8.6/10
"""
    p = heuristic_profile(text)
    assert len(p.experience) == 1


def test_bulleted_shape_now_reports_complete_coverage():
    p = heuristic_profile(BULLETED_ROLES)
    cov = assess_coverage(BULLETED_ROLES, p, min_chars=50)
    assert cov.band is not CoverageBand.MAJOR_GAPS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extractor_shape_corpus.py -v`
Expected: FAIL — `assert len(p.experience) == 2` gets `0`

- [ ] **Step 3: Write minimal implementation**

Replace the per-line loop guard in `_experience` with a section-level decision:

```python
def _experience(lines: list[tuple[int, str]]) -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    dated = [(s, l) for s, l in lines if has_date_range(_BULLET.sub("", l))]
    # A duty list under a role ALWAYS has an unbulleted dated line above it. So
    # when every dated line in this section is bulleted, there is no role line
    # for them to be duties OF -- they are the roles (S9.2).
    all_dated_are_bullets = bool(dated) and all(_BULLET.match(l) for _, l in dated)
    for start, line in lines:
        content = _BULLET.sub("", line)
        if not has_date_range(content):
            continue
        if _BULLET.match(line) and not all_dated_are_bullets:
            continue  # a duty under a role
        ...  # the rest of the existing body is UNCHANGED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extractor_shape_corpus.py tests/test_candidate_extractor_heuristic.py -v`
Expected: PASS — including the pre-existing heuristic tests, which pin the duty rule

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/extractor.py tests/test_extractor_shape_corpus.py
git commit -m "fix(s92): an all-bulleted experience section is roles, not duties

Measured on 016f91f: '- Engineer, Acme (2015 - 2019)' yielded ZERO experience
entries, so years_experience was None and six downstream checks -- cross_field,
the feature store, interview questions, interview scoring, document forensics,
moonlighting -- ran vacuously and reported insufficient_data."
```

---

### Task 9: Fix 2 — header matching tolerates decoration, and learns the missing aliases

**Files:**
- Modify: `src/app/candidates/sections.py` (add aliases)
- Modify: `src/app/candidates/extractor.py:83-101` (`_split_sections`)
- Test: `tests/test_extractor_shape_corpus.py`

**Interfaces:**
- Consumes: `SECTION_ALIASES`.
- Produces: no signature change.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extractor_shape_corpus.py
import pytest

CAREER_HISTORY = BULLETED_ROLES.replace("EXPERIENCE", "CAREER HISTORY")


@pytest.mark.parametrize("header", [
    "CAREER HISTORY",
    "Employment Details",
    "ORGANIZATIONAL EXPERIENCE",
    "WORK EXPERIENCE (5 YEARS)",
    "Experience ------",
    "Work History:",
])
def test_experience_headers_real_resumes_use(header):
    text = BULLETED_ROLES.replace("EXPERIENCE", header)
    p = heuristic_profile(text)
    assert len(p.experience) == 2, f"header {header!r} lost the experience section"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extractor_shape_corpus.py -k headers -v`
Expected: FAIL on `CAREER HISTORY`, `Employment Details`, `ORGANIZATIONAL EXPERIENCE`, `WORK EXPERIENCE (5 YEARS)`, `Experience ------`

- [ ] **Step 3: Write minimal implementation**

In `src/app/candidates/sections.py`, extend the `experience` tuple:

```python
    "experience": (
        "experience", "work experience", "professional experience",
        "employment", "employment history", "work history",
        "career history", "employment details", "organizational experience",
        "organisational experience", "work summary", "professional summary",
    ),
```

In `src/app/candidates/extractor.py`, add a normalizer and use it in `_split_sections`:

```python
_HEADER_DECORATION = re.compile(r"\([^)]*\)|[_\-–—=~]{2,}")


def _header_key(line: str) -> str:
    """Section-header lookup key: decoration and punctuation removed (S9.2)."""
    s = _HEADER_DECORATION.sub("", line)
    return " ".join(s.split()).strip(" :.-–—").lower()
```

Then in `_split_sections` replace `key = line.rstrip(":").strip().lower()` with
`key = _header_key(line)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extractor_shape_corpus.py tests/test_candidate_extractor_heuristic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/sections.py src/app/candidates/extractor.py tests/test_extractor_shape_corpus.py
git commit -m "fix(s92): section headers survive decoration, and six real aliases arrive"
```

---

### Task 10: Fix 3 — spelled-out degrees

**Files:**
- Modify: `src/app/candidates/extractor.py:47-51` (`_DEGREE`)
- Test: `tests/test_extractor_shape_corpus.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extractor_shape_corpus.py
SPELLED_OUT_DEGREES = """Rahul Verma
rahul@example.com  +91 98765 43210

EDUCATION
Bachelor of Technology in Computer Science, VIT Vellore, 2015
Master of Business Administration, IIM Bangalore, 2019

SKILLS
Python, SQL
"""


def test_spelled_out_degrees_are_extracted():
    p = heuristic_profile(SPELLED_OUT_DEGREES)
    assert len(p.education) == 2
    assert "Bachelor" in (p.education[0].degree or "")
    assert p.education[0].institution == "VIT Vellore"


def test_bba_and_ba_are_degrees():
    text = SPELLED_OUT_DEGREES.replace(
        "Bachelor of Technology in Computer Science", "BBA in Marketing"
    )
    p = heuristic_profile(text)
    assert len(p.education) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extractor_shape_corpus.py -k degree -v`
Expected: FAIL — `assert len(p.education) == 2` gets `0`

- [ ] **Step 3: Write minimal implementation**

```python
_DEGREE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?e\b|m\.?e\b|b\.?sc|m\.?sc|bca|mca|mba|"
    r"bba|b\.?a\b|m\.?a\b|ph\.?d|b\.?com|m\.?com|diploma|"
    r"bachelors?|masters?)\b",
    re.IGNORECASE,
)
```

> **Watch the ordering.** `_education` splits on `[—–,]` and takes the first
> segment matching `_DEGREE` as the degree, then the next digit-free segment as
> the institution. `"Bachelor of Technology in Computer Science"` contains
> `" in "`, so the existing degree/field split applies unchanged — verify
> `field_of_study` lands as `"Computer Science"` and adjust the test's
> expectation to the truth if it does not, never the other way round.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extractor_shape_corpus.py tests/test_candidate_extractor_heuristic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/extractor.py tests/test_extractor_shape_corpus.py
git commit -m "fix(s92): the extractor learns degrees spelled out in words"
```

---

### Task 11: Fix 4 — labelled skill lines

**Files:**
- Modify: `src/app/candidates/extractor.py:293-305` (`_skills`)
- Test: `tests/test_extractor_shape_corpus.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extractor_shape_corpus.py
LABELLED_SKILLS = """Rahul Verma
rahul@example.com  +91 98765 43210

TECHNICAL SKILLS
Programming Languages: Python, Java, Go
Databases: PostgreSQL, MongoDB

EDUCATION
B.Tech in Computer Science, VIT Vellore, 2015
"""


def test_skill_category_labels_are_dropped():
    p = heuristic_profile(LABELLED_SKILLS)
    names = [s.name for s in p.skills]
    assert "Python" in names
    assert "PostgreSQL" in names
    assert not any(":" in n for n in names), f"category label survived: {names}"


def test_a_colon_inside_a_single_skill_is_not_a_label():
    """Only a SHORT leading label before the first comma is a category."""
    text = LABELLED_SKILLS.replace(
        "Programming Languages: Python, Java, Go", "Python, Java, Go"
    )
    p = heuristic_profile(text)
    assert "Python" in [s.name for s in p.skills]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extractor_shape_corpus.py -k skill -v`
Expected: FAIL — `category label survived: ['Programming Languages: Python', ...]`

- [ ] **Step 3: Write minimal implementation**

```python
_SKILL_LABEL = re.compile(r"^[A-Za-z][A-Za-z /&+-]{0,29}:\s*")


def _skills(lines: list[tuple[int, str]]) -> list[SkillItem]:
    items: list[SkillItem] = []
    seen: set[str] = set()
    for start, line in lines:
        content = _BULLET.sub("", line)
        # "Programming Languages: Python, Java" -- the label is a CATEGORY, not
        # a skill, and left in place it also poisons S1.4 normalization and
        # floods S6.3's curation queue with terms that can never map (S9.2).
        content = _SKILL_LABEL.sub("", content)
        ...  # the rest of the existing body is UNCHANGED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extractor_shape_corpus.py tests/test_candidate_extractor_heuristic.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/candidates/extractor.py tests/test_extractor_shape_corpus.py
git commit -m "fix(s92): a skill category label is not a skill"
```

---

### Task 12: Surface — `Report.extraction_coverage`, end to end

**Files:**
- Modify: `src/app/schemas/report.py` (new field + import)
- Modify: `src/app/graph/state.py` (new input field)
- Modify: `src/app/graph/build.py:72-90` (`evaluate` kwarg)
- Modify: `src/app/graph/nodes/report.py` (summary sentence + `Report(...)`)
- Modify: `src/app/screening/ingest.py:114-145` (pass it through)
- Modify: `src/app/api/routes.py:553-567` (`CandidateCreateResponse`)
- Test: `tests/test_extraction_coverage_report.py`

**Interfaces:**
- Consumes: `ExtractionCoverage`, `ExtractionResult.coverage`.
- Produces: `Report.extraction_coverage: Optional[ExtractionCoverage] = None`; `EvaluationState.extraction_coverage`; `EvaluationEngine.evaluate(..., extraction_coverage=None)`; `CandidateCreateResponse.extraction_coverage`.

**Spec delta, deliberate:** §6 named only the `Report` field. This task also puts
coverage on `CandidateCreateResponse`, for the reason the codebase already
recorded for `resume_farm` — bulk imports run with `evaluate=False` and produce
no report, so coverage would otherwise be computed and thrown away on exactly
the path that ingests the most resumes. It is not persisted for those, same as
`resume_farm`. No projection change: coverage carries no counterparty identity.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction_coverage_report.py
"""Coverage reaches the Report by the path resume_farm already uses (S9.2)."""

import pytest

from app.schemas.extraction import CoverageBand, ExtractionCoverage
from app.schemas.report import Report


def test_report_defaults_to_no_coverage():
    """None, not a refusal object: every pre-S9.2 stored report has no coverage
    at all, exactly as it has no ai_generation or cross_field."""
    assert Report().extraction_coverage is None


@pytest.mark.asyncio
async def test_coverage_lands_on_the_report(services):
    from app.graph.build import EvaluationEngine

    engine = EvaluationEngine(services)
    cov = ExtractionCoverage(band=CoverageBand.MAJOR_GAPS, checks_run=5)
    report = await engine.evaluate(
        resume_text="Priya Sharma\npriya@example.com\nSenior Data Engineer",
        domain="genai",
        extraction_coverage=cov,
    )
    assert report.extraction_coverage is not None
    assert report.extraction_coverage.band is CoverageBand.MAJOR_GAPS


@pytest.mark.asyncio
async def test_major_gaps_says_so_in_the_summary(services):
    from app.graph.build import EvaluationEngine

    engine = EvaluationEngine(services)
    report = await engine.evaluate(
        resume_text="Priya Sharma\npriya@example.com\nSenior Data Engineer",
        domain="genai",
        extraction_coverage=ExtractionCoverage(band=CoverageBand.MAJOR_GAPS, checks_run=5),
    )
    assert "could not be read" in report.summary.lower() or "not extracted" in report.summary.lower()
```

> **Implementer:** confirm the `services` fixture name in `tests/conftest.py`
> before running — use whatever the existing graph tests use.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extraction_coverage_report.py -v`
Expected: FAIL — `AttributeError: 'Report' object has no attribute 'extraction_coverage'`

- [ ] **Step 3: Write minimal implementation**

`src/app/schemas/report.py`:

```python
from app.schemas.extraction import ExtractionCoverage

    # S9.2: did the extractor read what the resume says? ADVISORY, and a
    # statement about the PARSER, never about the candidate. None for every
    # report written before S9.2 and for ad-hoc runs with no profile.
    extraction_coverage: Optional[ExtractionCoverage] = None
```

`src/app/graph/state.py`, beside `resume_farm`:

```python
    # S9.2: extraction coverage, computed in extract_profile (both doors) and
    # handed in the way resume_farm is -- the graph never re-derives it.
    extraction_coverage: Optional[ExtractionCoverage] = None
```

`src/app/graph/build.py`: add `extraction_coverage: Optional[ExtractionCoverage] = None`
to `evaluate`'s keyword-only parameters and `extraction_coverage=extraction_coverage`
to the `EvaluationState(...)` construction.

`src/app/graph/nodes/report.py`: import `CoverageBand` from `app.schemas.extraction` alongside the existing band imports, add `extraction_coverage=state.extraction_coverage`
to the `Report(...)` construction, and one summary sentence before it:

```python
        cov = state.extraction_coverage
        if cov is not None and cov.band is CoverageBand.MAJOR_GAPS:
            fields = sorted({g.field for g in cov.gaps if g.field})
            summary += (
                f" Extraction coverage: parts of this resume could not be read — "
                f"{', '.join(fields) or 'some sections'} appear in the document but "
                f"were not extracted, so checks over those fields report "
                f"insufficient data for a reason about the PARSER, not the candidate."
            )
```

`src/app/screening/ingest.py`: pass `extraction_coverage=result.coverage` into
`engine.evaluate(...)`, and add `extraction_coverage=result.coverage` to the
returned `IngestResult(...)` (adding the field to `IngestResult` first).

`src/app/api/routes.py`: add to `CandidateCreateResponse`:

```python
    # S9.2: computed at ingest so bulk imports (evaluate=False) still see it,
    # for the same reason resume_farm is here.
    extraction_coverage: Optional[ExtractionCoverage] = None
```

and populate it from the ingest result in `_ingest_one`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_extraction_coverage_report.py tests/test_openapi_contract.py -v`
Expected: PASS — `test_openapi_contract.py` must stay green; if it demands an
explicit model for the new field, model it rather than loosening the test

- [ ] **Step 5: Commit**

```bash
git add src/app/schemas/report.py src/app/graph/ src/app/screening/ingest.py src/app/api/routes.py tests/test_extraction_coverage_report.py
git commit -m "feat(s92): coverage reaches the report, and the ingest response"
```

---

### Task 13: The mutation pass

**Files:**
- Create: `scripts/mutate_s92.py`

**Interfaces:**
- Consumes: the finished `coverage.py` and the four fixes.
- Produces: an executable proof, exit 0 when every mutant dies.

Committed, in the S9.1 pattern — a count nobody can re-derive is a claim, not evidence.

- [ ] **Step 1: Write the harness**

```python
"""S9.2's mutation pass: deliberate one-line breaks that must all die.

The checks ARE the deliverable. A suite that survives mutating a refusal
direction or a severity is not testing them -- and a wrong coverage band still
returns a plausible-looking enum, which is the failure mode that hides longest.

Modelled on scripts/mutate_s91.py. Run from the repo root:
    python scripts/mutate_s92.py
Exit 0 means every mutant died. A SURVIVOR MEANS A TEST IS MISSING.
"""

import pathlib, subprocess, sys

C = pathlib.Path("src/app/candidates/coverage.py")
E = pathlib.Path("src/app/candidates/extractor.py")

MUTANTS = [
 ("refusal: report COMPLETE instead of refusing on short text", C,
  "        return ExtractionCoverage()  # refusal", "        return ExtractionCoverage(band=CoverageBand.COMPLETE)  #"),
 ("refusal: min_chars boundary flips to >", C,
  "if len((text or \"\").strip()) < min_chars:", "if len((text or \"\").strip()) > min_chars:"),
 ("experience: fire even when entries exist", C,
  "if role_lines and not profile.experience:", "if role_lines:"),
 ("experience: academic lines count as roles", C,
  "and not looks_academic(line)", ""),
 ("experience: gap downgraded to MINOR", C,
  "            severity=GapSeverity.MAJOR,\n            field=\"experience\",",
  "            severity=GapSeverity.MINOR,\n            field=\"experience\","),
 ("education: fire even when entries exist", C,
  "if edu_lines and not profile.education:", "if edu_lines:"),
 ("contact: require BOTH to be missing becomes either", C,
  "profile.contact.email is None and profile.contact.phone is None",
  "profile.contact.email is None or profile.contact.phone is None"),
 ("band: MAJOR gaps read as MINOR", C,
  "        band = CoverageBand.MAJOR_GAPS", "        band = CoverageBand.MINOR_GAPS"),
 ("band: gaps present still reads COMPLETE", C,
  "    elif kept:\n        band = CoverageBand.MINOR_GAPS",
  "    elif False:\n        band = CoverageBand.MINOR_GAPS"),
 ("cap: truncated never reported", C,
  "    truncated = len(gaps) > max_gaps", "    truncated = False"),
 ("header quote: unbounded", C,
  "header=header.strip()[:max_header_chars],", "header=header.strip(),"),
 ("dated role: one year alone counts", C,
  "    return len(years) == 1 and bool(_PRESENT.search(line))", "    return len(years) == 1"),
 ("fix1: all-bulleted sections go back to being duties", E,
  "        if _BULLET.match(line) and not all_dated_are_bullets:",
  "        if _BULLET.match(line):"),
 ("fix1: every bulleted section becomes roles", E,
  "    all_dated_are_bullets = bool(dated) and all(_BULLET.match(l) for _, l in dated)",
  "    all_dated_are_bullets = True"),
 ("fix2: header decoration no longer stripped", E,
  "            key = _header_key(line)",
  "            key = line.rstrip(\":\").strip().lower()"),
 ("fix4: skill category labels survive", E,
  "        content = _SKILL_LABEL.sub(\"\", content)", "        pass"),
]

SUITE = [
    "tests/test_extraction_coverage.py",
    "tests/test_extraction_coverage_independence.py",
    "tests/test_extraction_coverage_report.py",
    "tests/test_extractor_shape_corpus.py",
    "tests/test_candidate_extractor_heuristic.py",
]

dead = survived = 0
for name, path, old, new in MUTANTS:
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  ?? NOT APPLIED  {name}  (anchor missing in {path.name})")
        survived += 1
        continue
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    try:
        rc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", *SUITE],
            capture_output=True, text=True,
        ).returncode
    finally:
        path.write_text(src, encoding="utf-8")
    if rc == 0:
        print(f"  SURVIVED  {name}")
        survived += 1
    else:
        print(f"  dead      {name}")
        dead += 1

print(f"\n{dead}/{dead + survived} mutants dead")
sys.exit(0 if survived == 0 else 1)
```

- [ ] **Step 2: Run it**

Run: `python scripts/mutate_s92.py`
Expected: every mutant dead, exit 0. **A survivor means a missing test — write
the test, do not delete the mutant.** An anchor reported as missing means the
implementation drifted from this plan; re-anchor it against the real file.

- [ ] **Step 3: Confirm the tree is clean**

Run: `git status --porcelain`
Expected: no modification to `coverage.py` or `extractor.py` — the harness
restores each file from its own bytes.

- [ ] **Step 4: Commit**

```bash
git add scripts/mutate_s92.py
git commit -m "test(s92): the mutation pass, committed rather than claimed"
```

---

### Task 14: Smoke, docs, and the roadmap

**Files:**
- Create: `scripts/smoke_s92.py`
- Modify: `CANDIDATES.md` (new section), `SIGNALS.md` (one sentence), `docs/ROADMAP.md`
- Test: the smoke is the test

**Interfaces:**
- Consumes: everything above.
- Produces: `python scripts/smoke_s92.py` → exit 0.

- [ ] **Step 1: Write the smoke**

```python
"""S9.2 smoke: coverage over the wire, on a live server.

What a unit test cannot prove and this does:
  * the four resume shapes survive a REAL upload through POST /candidates,
    not a direct heuristic_profile() call;
  * `extraction_coverage` is what an operator actually RECEIVES AS JSON, on
    both the embedded report and the ingest response;
  * a refusal serializes with NO gaps -- the sprint's claim, asserted on the
    body rather than on a Python object;
  * an evaluate=false bulk import still reports coverage, which is the whole
    reason it sits on the response as well as on the report.

Run from the repo root:   python scripts/smoke_s92.py
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

S = Smoke("smoke_s92")
PORT = 8092
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}
ROOT = Path(__file__).resolve().parent.parent
```

Then the body — the shapes come from the test corpus, so the smoke and the unit
tests cannot drift apart:

```python
SHAPES = {
    "bulleted_roles": (BULLETED_ROLES, "experience", 2),
    "career_history_header": (CAREER_HISTORY, "experience", 2),
    "spelled_out_degrees": (SPELLED_OUT_DEGREES, "education", 2),
    "labelled_skills": (LABELLED_SKILLS, "skills", None),
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        url = f"sqlite:///{(scratch / 's92.db').as_posix()}"
        env = base_env(scratch, url, DEE_ADMIN_API_KEY=ADMIN)
        proc = subprocess.Popen(
            uvicorn_argv(PORT), env=env, cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            c = client(BASE, headers=ADMIN_H)
            if not S.check("server_healthy", wait_healthy(c)):
                return S.summary()

            for name, (text, field, expected) in SHAPES.items():
                r = c.post("/candidates", json={"resume_text": text, "domain": "genai"})
                if not S.check(f"{name}_uploaded", r.status_code == 200, f"HTTP {r.status_code}"):
                    continue
                body = r.json()
                cov = (body.get("report") or {}).get("extraction_coverage")
                S.check(f"{name}_coverage_present", cov is not None)
                S.check(
                    f"{name}_no_major_gap_after_the_fixes",
                    cov is not None and cov["band"] != "major_gaps",
                    f"band={cov and cov['band']} gaps={cov and [g['id'] for g in cov['gaps']]}",
                )

            # A refusal, over the wire, serializing with NO metric-shaped fields.
            r = c.post("/candidates", json={"resume_text": "Priya
priya@example.com",
                                            "domain": "genai"})
            cov = (r.json().get("report") or {}).get("extraction_coverage") or {}
            S.check("short_document_refuses", cov.get("band") == "insufficient_data",
                    f"band={cov.get('band')}")
            S.check("refusal_carries_no_gaps", cov.get("gaps") == [], f"gaps={cov.get('gaps')}")

            # evaluate=false produces no report -- coverage must still arrive.
            r = c.post("/candidates", json={"resume_text": BULLETED_ROLES,
                                            "domain": "genai", "evaluate": False})
            body = r.json()
            S.check("bulk_import_has_no_report", body.get("report") is None)
            S.check("bulk_import_still_reports_coverage",
                    (body.get("extraction_coverage") or {}).get("band") is not None)
        finally:
            proc.terminate()
            proc.wait(timeout=30)
    return S.summary()


if __name__ == "__main__":
    sys.exit(main())
```

**Target: 16 checks** (4 shapes x 3, plus 4 standalone). Import the four shape
constants from `tests/test_extractor_shape_corpus.py` rather than re-typing
them; if that import is awkward from `scripts/`, move the constants into
`tests/fixtures/` as files and read them from both places — **do not paste a
second copy**, which is the duplication `scripts/_smoke.py` exists to end.

Do not re-roll `Smoke`, `base_env`, `client`, `uvicorn_argv` or `wait_healthy`
— `tests/test_smoke_harness.py` has a drift guard over all 35 scripts and will
fail the build.

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_s92.py`
Expected: `16/16 OK`, exit 0

- [ ] **Step 3: Run the full suite and the regression smokes**

Run: `python -m pytest -q`
Expected: PASS, **≥ 1996 + the new tests**, zero failures

Run: `python scripts/smoke_s11.py && python scripts/smoke_s21.py && python scripts/smoke_s22.py && python scripts/smoke_s43.py && python scripts/smoke_s84b.py && python scripts/smoke_s91.py`
Expected: all green — S2.2 and S4.3 especially, since the extractor changed
underneath them

- [ ] **Step 4: Write the docs**

`CANDIDATES.md` gains a section: the five measured shapes, what coverage does,
the independence rule and why (§3.1), and the explicit statement that a gap is
a statement about the parser and never about the candidate.

`SIGNALS.md` gains one sentence in §3 naming extraction coverage as a confound
the harness does not yet filter on, pointing at spec §9's non-goal.

`docs/ROADMAP.md`: status board entry for S9.2 under PI-9, and a "Current state"
entry with the measured numbers, the rulings, and anything the plan got wrong.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_s92.py CANDIDATES.md SIGNALS.md docs/ROADMAP.md
git commit -m "test(s92): smoke over the wire, and the docs

Four resume shapes uploaded through a real POST /candidates, because every
check in the S8.6 review that fetched an asset instead of the page passed for
the wrong reason."
```

---

## Definition of done

- [ ] `pytest -q` green, count ≥ 1996 plus the new tests
- [ ] `python scripts/mutate_s92.py` → every mutant dead
- [ ] `python scripts/smoke_s92.py` → 16/16
- [ ] The regression smokes named in Task 14 step 3 all green
- [ ] `git status --porcelain` clean
- [ ] Branch `s92-extraction-coverage` **not merged and not pushed** without review
