# S2.2 — Cross-Field Forensics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an advisory `cross_field` pipeline node that runs deterministic date/structure forensics over the extracted `CandidateProfile` — timeline overlaps, timeline gaps, education↔employment overlap, seniority-vs-tenure — and surfaces the findings on the Report without touching claim verdicts or depth scoring.

**Architecture:** A pure module `app/fabrication/cross_field.py` holds interval math + four checks + fusion/banding (offline, reusable by S2.4). A new graph node `app/graph/nodes/cross_field.py` runs right after `ai_signals`. The graph stays candidate-store-unaware: `EvaluationState` gains an optional `candidate_profile` *input* which POST /candidates supplies from its extraction; when absent (POST /evaluate), the node derives one deterministically via `normalize_profile(heuristic_profile(text))`. The `report` node passes the assessment through onto `Report.cross_field` and logs one flywheel record. **No LLM anywhere in S2.2** — date arithmetic needs no model; the convention requires deterministic fallbacks for LLM steps, not LLMs everywhere. No DB migration: reports persist as full JSON bodies.

**Tech Stack:** Python 3.13, Pydantic v2, LangGraph, pytest (offline), FastAPI/uvicorn for the smoke.

## Global Constraints

- Branch: `s22-cross-field` (create from `main` at Task 1 Step 0).
- TDD, fully offline tests; `pytest -q` green before merge. Baseline: **225 tests**; this plan adds ~43 (→ ~268).
- **Advisory only — the conservative gate stays**: findings never change any `VerdictStatus`, `depth_score`, or `depth_band`. `CrossFieldAssessment.advisory` is always `True`. Fusion into calibration is S2.4, not here.
- False positives are the existential risk. Conservative date math is mandatory: year-only points shrink *inward* for overlap checks (every flagged overlap is a lower bound) and expand *outward* for tenure (career span is an upper bound, so seniority findings under-fire). Gaps are ALWAYS `minor` — career breaks are legitimate; copy must say so.
- All reviewer-facing copy must include the advisory framing ("observations for the reviewer to probe … never a rejection signal").
- Config: new tunables go in `config.yaml` AND as `Settings` fields (env override `DEE_*`); no secrets. Exact new tunables (copy verbatim): `xf_min_confidence: 0.50`, `xf_overlap_months_min: 3`, `xf_gap_months_min: 12`, `xf_edu_overlap_months_min: 12`, `xf_senior_min_months: 24`, `xf_lead_min_months: 48`.
- Severity escalation constants are code, not config: overlap becomes `major` at ≥ 12 months (`_OVERLAP_MAJOR_MONTHS`), education overlap at ≥ 24 (`_EDU_MAJOR_MONTHS`).
- No new tables, no Alembic migration, no changes to `app/domains/`, calibration, or the `ai_signals` node.
- Sprint ends with a local smoke (`scripts/smoke_s22.py`, uvicorn + HTTP, key-less AND live) and a ROADMAP.md update.
- Commit messages: NO Co-Authored-By trailer (user preference).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/schemas/fabrication.py` | Modify | Append S2.2 contracts: `FindingSeverity`, `ConsistencyBand`, `CrossFieldFinding`, `CrossFieldAssessment` |
| `app/fabrication/cross_field.py` | Create | Pure interval math + 4 checks + `assess_cross_field` + `band_for_findings` |
| `app/graph/nodes/cross_field.py` | Create | Graph node: profile (given or heuristic-derived) → assessment |
| `app/graph/state.py` | Modify | Add `candidate_profile` input + `cross_field` output fields |
| `app/graph/nodes/__init__.py` | Modify | Export `make_cross_field_node` |
| `app/graph/build.py` | Modify | Insert `cross_field` after `ai_signals`; `evaluate(candidate_profile=...)` |
| `app/api/routes.py` | Modify | POST /candidates passes `result.profile` into the engine |
| `app/schemas/report.py` | Modify | Add `Report.cross_field` (Optional) |
| `app/graph/nodes/report.py` | Modify | Pass-through + summary sentence (major only) + flywheel record |
| `app/core/config.py` | Modify | Six `xf_*` Settings fields |
| `config.yaml` | Modify | Same six keys, commented |
| `tests/fixtures/inconsistent_genai_resume.txt` | Create | Adversarial fixture (overlap + edu overlap + thin-tenure lead title) |
| `tests/conftest.py` | Modify | `inconsistent_resume` fixture |
| `tests/test_cross_field_schema.py` | Create | Task 1 tests |
| `tests/test_cross_field_timeline.py` | Create | Task 2 tests |
| `tests/test_cross_field_coherence.py` | Create | Task 3 tests |
| `tests/test_cross_field_assess.py` | Create | Task 4 tests |
| `tests/test_cross_field_node.py` | Create | Task 5 tests |
| `tests/test_report_cross_field.py` | Create | Task 6 tests |
| `tests/test_cross_field_integration.py` | Create | Task 7 tests |
| `scripts/smoke_s22.py` | Create | Task 8 smoke |
| `docs/ROADMAP.md` | Modify | Task 8 close-out |

---

### Task 1: Cross-field schemas

**Files:**
- Modify: `app/schemas/fabrication.py` (append after `AIGenerationAssessment`)
- Test: `tests/test_cross_field_schema.py`

**Interfaces:**
- Consumes: nothing new (pydantic only).
- Produces (every later task imports these exact names from `app.schemas.fabrication`):
  - `FindingSeverity` (StrEnum: `MINOR="minor"`, `MAJOR="major"`)
  - `ConsistencyBand` (StrEnum: `INSUFFICIENT_DATA="insufficient_data"`, `CONSISTENT="consistent"`, `MINOR_ISSUES="minor_issues"`, `MAJOR_ISSUES="major_issues"`)
  - `CrossFieldFinding(id: str, detail: str, severity: FindingSeverity = MINOR, score: float 0..1, entry_ids: list[str] = [])`
  - `CrossFieldAssessment(score: float = 0.0, confidence: float = 0.0, band: ConsistencyBand = INSUFFICIENT_DATA, findings: list[CrossFieldFinding] = [], reasoning: str = "", advisory: bool = True)`

- [ ] **Step 0: Create the branch**

```bash
git checkout main
git checkout -b s22-cross-field
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cross_field_schema.py`:

```python
"""S2.2 contracts: conservative defaults, bounds, JSON round-trip."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    ConsistencyBand,
    CrossFieldAssessment,
    CrossFieldFinding,
    FindingSeverity,
)


def test_defaults_are_conservative():
    a = CrossFieldAssessment()
    assert a.band is ConsistencyBand.INSUFFICIENT_DATA
    assert a.score == 0.0
    assert a.confidence == 0.0
    assert a.findings == []
    assert a.advisory is True  # hard mandate, mirrors Report


def test_finding_defaults_to_minor():
    f = CrossFieldFinding(id="timeline_gap", detail="d", score=0.3)
    assert f.severity is FindingSeverity.MINOR
    assert f.entry_ids == []


def test_score_bounds_enforced():
    with pytest.raises(ValidationError):
        CrossFieldFinding(id="x", detail="d", score=1.5)
    with pytest.raises(ValidationError):
        CrossFieldAssessment(confidence=-0.1)


def test_round_trips_through_json():
    a = CrossFieldAssessment(
        score=0.6,
        confidence=0.9,
        band=ConsistencyBand.MAJOR_ISSUES,
        findings=[
            CrossFieldFinding(
                id="timeline_overlap",
                detail="d",
                severity=FindingSeverity.MAJOR,
                score=0.8,
                entry_ids=["exp_1", "exp_2"],
            )
        ],
        reasoning="r",
    )
    again = CrossFieldAssessment.model_validate_json(a.model_dump_json())
    assert again == a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cross_field_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'CrossFieldAssessment'`

- [ ] **Step 3: Append the schemas**

Append to `app/schemas/fabrication.py` (after `AIGenerationAssessment`):

```python
class FindingSeverity(StrEnum):
    """S2.2 — how loudly a cross-field finding should be surfaced."""

    MINOR = "minor"  # context for a reviewer; often legitimate (e.g. career gaps)
    MAJOR = "major"  # a contradiction worth probing in conversation


class ConsistencyBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    CONSISTENT = "consistent"
    MINOR_ISSUES = "minor_issues"
    MAJOR_ISSUES = "major_issues"


class CrossFieldFinding(BaseModel):
    """One cross-field observation — human-readable, with the months behind it."""

    id: str  # stable check id, e.g. "timeline_overlap"
    detail: str
    severity: FindingSeverity = FindingSeverity.MINOR
    score: float = Field(ge=0.0, le=1.0)
    entry_ids: list[str] = Field(default_factory=list)  # profile entry ids involved


class CrossFieldAssessment(BaseModel):
    """The cross_field node's output: findings + band. Purely deterministic
    date/structure math over the extracted profile — no LLM by design."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)  # fused inconsistency
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: ConsistencyBand = ConsistencyBand.INSUFFICIENT_DATA
    findings: list[CrossFieldFinding] = Field(default_factory=list)
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal
```

Also update the module docstring's first paragraph to mention S2.2, e.g. append the line: `S2.2 — cross-field forensics: deterministic timeline/coherence findings.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cross_field_schema.py tests/test_fabrication_schema.py -q`
Expected: `8 passed` (4 new + 4 existing untouched)

- [ ] **Step 5: Commit**

```bash
git add app/schemas/fabrication.py tests/test_cross_field_schema.py
git commit -m "feat(schemas): cross-field forensics contracts (S2.2)"
```

---

### Task 2: Interval math + timeline checks (overlaps, gaps)

**Files:**
- Create: `app/fabrication/cross_field.py` (helpers + two checks; coherence checks arrive in Task 3, assessment in Task 4)
- Test: `tests/test_cross_field_timeline.py`

**Interfaces:**
- Consumes: `CrossFieldFinding`, `FindingSeverity` (Task 1); `DateRange`, `ExperienceEntry`, `EmploymentType` from `app.candidates.schema`.
- Produces (exact signatures Tasks 3–4 build on):
  - `narrow_interval(dates: DateRange, today: date) -> tuple[int, int] | None` — inclusive month indices the range *certainly* covers (year-only start → December, year-only end → January); `None` when unusable.
  - `wide_interval(dates: DateRange, today: date) -> tuple[int, int] | None` — widest plausible cover (year-only start → January, end → December).
  - `month_precise_interval(dates: DateRange, today: date) -> tuple[int, int] | None` — only when both endpoints are month-precise (an `is_current` end counts, resolved via `today`).
  - `overlap_months(a: tuple[int, int], b: tuple[int, int]) -> int`
  - `check_timeline_overlaps(experience: list[ExperienceEntry], *, today: date, min_months: int) -> list[CrossFieldFinding]`
  - `check_timeline_gaps(experience: list[ExperienceEntry], *, today: date, min_months: int) -> list[CrossFieldFinding]`
  - Constants `_NON_PRIMARY: set[EmploymentType]`, `_OVERLAP_MAJOR_MONTHS = 12`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cross_field_timeline.py`:

```python
"""Interval math + timeline checks — pure, offline, conservative by design."""

from datetime import date

from app.candidates.schema import DateRange, EmploymentType, ExperienceEntry
from app.fabrication.cross_field import (
    check_timeline_gaps,
    check_timeline_overlaps,
    month_precise_interval,
    narrow_interval,
    overlap_months,
    wide_interval,
)
from app.schemas.fabrication import FindingSeverity

TODAY = date(2026, 7, 1)


def _exp(start, end, *, current=False, etype=EmploymentType.FULL_TIME, title="Engineer"):
    return ExperienceEntry(
        title=title,
        employer="Acme",
        employment_type=etype,
        dates=DateRange(start=start, end=end, is_current=current),
    )


def test_narrow_interval_shrinks_year_only_points_inward():
    # 2018–2022 certainly covers only Dec 2018 .. Jan 2022.
    iv = narrow_interval(DateRange(start="2018", end="2022"), TODAY)
    assert iv == (2018 * 12 + 11, 2022 * 12 + 0)
    # Month-precise points are exact.
    assert narrow_interval(DateRange(start="2021-01", end="2022-08"), TODAY) == (
        2021 * 12 + 0,
        2022 * 12 + 7,
    )


def test_wide_interval_expands_year_only_points_outward():
    iv = wide_interval(DateRange(start="2018", end="2022"), TODAY)
    assert iv == (2018 * 12 + 0, 2022 * 12 + 11)


def test_intervals_unusable_without_start_or_end():
    assert narrow_interval(DateRange(), TODAY) is None
    assert narrow_interval(DateRange(start="2021-01"), TODAY) is None  # open, not current
    # is_current resolves the open end to today.
    iv = narrow_interval(DateRange(start="2021-01", is_current=True), TODAY)
    assert iv == (2021 * 12 + 0, 2026 * 12 + 6)
    # Same-year year-only range shrinks to nothing -> unusable, never flagged.
    assert narrow_interval(DateRange(start="2022", end="2022"), TODAY) is None


def test_month_precise_rejects_year_only_points():
    assert month_precise_interval(DateRange(start="2020", end="2022-01"), TODAY) is None
    assert month_precise_interval(DateRange(start="2020-03", end="2022"), TODAY) is None
    assert month_precise_interval(
        DateRange(start="2020-03", is_current=True), TODAY
    ) == (2020 * 12 + 2, 2026 * 12 + 6)


def test_overlap_months_math():
    assert overlap_months((0, 11), (6, 20)) == 6
    assert overlap_months((0, 5), (6, 10)) == 0  # adjacent, not overlapping


def test_overlap_fires_major_on_long_concurrent_primary_roles():
    a = _exp("2021-01", "2022-08")
    b = _exp("2020-06", "2022-08")
    findings = check_timeline_overlaps([a, b], today=TODAY, min_months=3)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "timeline_overlap"
    assert f.severity is FindingSeverity.MAJOR  # 20 months >= 12
    assert set(f.entry_ids) == {a.id, b.id}
    assert "20 months" in f.detail


def test_overlap_below_threshold_is_silent():
    a = _exp("2021-01", "2022-12")
    b = _exp("2022-11", "2023-12")  # 2-month overlap < min 3
    assert check_timeline_overlaps([a, b], today=TODAY, min_months=3) == []


def test_overlap_ignores_internships_and_freelance():
    a = _exp("2021-01", "2022-08")
    b = _exp("2020-06", "2022-08", etype=EmploymentType.INTERNSHIP)
    c = _exp("2020-06", "2022-08", etype=EmploymentType.FREELANCE)
    assert check_timeline_overlaps([a, b, c], today=TODAY, min_months=3) == []


def test_year_only_dates_cannot_false_positive_an_overlap():
    # 2020–2022 vs 2021–2023 look overlapping, but the certain overlap is only
    # Dec 2021 .. Jan 2022 = 2 months < 3 -> silent. Conservative by design.
    a = _exp("2020", "2022")
    b = _exp("2021", "2023")
    assert check_timeline_overlaps([a, b], today=TODAY, min_months=3) == []


def test_gap_fires_minor_only_and_reads_neutral():
    a = _exp("2019-01", "2020-12")
    b = _exp("2022-03", "2023-06")  # 14-month gap
    findings = check_timeline_gaps([a, b], today=TODAY, min_months=12)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "timeline_gap"
    assert f.severity is FindingSeverity.MINOR  # gaps are NEVER major
    assert "14-month" in f.detail
    assert "legitimate" in f.detail  # neutral copy mandated


def test_contiguous_roles_have_no_gap():
    a = _exp("2019-01", "2020-12")
    b = _exp("2021-01", "2023-06")
    assert check_timeline_gaps([a, b], today=TODAY, min_months=12) == []


def test_gaps_skip_year_only_dates_entirely():
    # Year precision can't measure a gap honestly -> never flagged.
    a = _exp("2018", "2019")
    b = _exp("2022", "2023")
    assert check_timeline_gaps([a, b], today=TODAY, min_months=12) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cross_field_timeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fabrication.cross_field'`

- [ ] **Step 3: Write the module**

Create `app/fabrication/cross_field.py`:

```python
"""Deterministic cross-field forensics (S2.2) — pure, offline, no LLM.

Checks the extracted CandidateProfile against itself: concurrent primary
roles, unexplained gaps, full-time work inside a bachelor's, and seniority
claims that outrun the visible career span. Conservative by construction:

* Year-only dates shrink INWARD for overlap checks (start -> December,
  end -> January), so every flagged overlap is a lower bound.
* Year-only dates expand OUTWARD for tenure (start -> January, end ->
  December), so career span is an upper bound and seniority under-fires.
* Gaps are always MINOR: career breaks are legitimate; the finding is
  context for a reviewer, never an accusation.
"""

from __future__ import annotations

import itertools
import re
from datetime import date

from app.candidates.schema import DateRange, EducationEntry, EmploymentType, ExperienceEntry
from app.schemas.fabrication import CrossFieldFinding, FindingSeverity

# Employment types that legitimately run concurrently with a primary role.
_NON_PRIMARY = {
    EmploymentType.INTERNSHIP,
    EmploymentType.PART_TIME,
    EmploymentType.FREELANCE,
    EmploymentType.CONTRACT,
}

_OVERLAP_MAJOR_MONTHS = 12  # a year+ of concurrent primary roles is probe-worthy

_POINT_RE = re.compile(r"(\d{4})(?:-(\d{2}))?$")


def _point(p: str | None) -> tuple[int, int | None] | None:
    """'YYYY-MM' -> (year, month); 'YYYY' -> (year, None); anything else None."""
    if not p:
        return None
    m = _POINT_RE.fullmatch(p)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)) if m.group(2) else None


def _idx(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _ym(idx: int) -> str:
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def _interval(
    dates: DateRange, today: date, *, start_fill: int, end_fill: int
) -> tuple[int, int] | None:
    """Shared interval builder; fills in the month for year-only points."""
    start = _point(dates.start)
    if start is None:
        return None
    s = _idx(start[0], start[1] or start_fill)
    end = _point(dates.end)
    if end is not None:
        e = _idx(end[0], end[1] or end_fill)
    elif dates.is_current:
        e = _idx(today.year, today.month)
    else:
        return None
    return (s, e) if s <= e else None


def narrow_interval(dates: DateRange, today: date) -> tuple[int, int] | None:
    """Months this range CERTAINLY covers — overlaps become lower bounds."""
    return _interval(dates, today, start_fill=12, end_fill=1)


def wide_interval(dates: DateRange, today: date) -> tuple[int, int] | None:
    """Widest plausible cover — tenure becomes an upper bound."""
    return _interval(dates, today, start_fill=1, end_fill=12)


def month_precise_interval(dates: DateRange, today: date) -> tuple[int, int] | None:
    """Only when both endpoints carry a month (is_current counts, via today)."""
    start = _point(dates.start)
    if start is None or start[1] is None:
        return None
    end = _point(dates.end)
    if end is not None:
        if end[1] is None:
            return None
        e = _idx(end[0], end[1])
    elif dates.is_current:
        e = _idx(today.year, today.month)
    else:
        return None
    s = _idx(start[0], start[1])
    return (s, e) if s <= e else None


def overlap_months(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)


def _label(e: ExperienceEntry) -> str:
    return " — ".join(x for x in (e.title, e.employer) if x) or e.id


def _primary(experience: list[ExperienceEntry]) -> list[ExperienceEntry]:
    return [e for e in experience if e.employment_type not in _NON_PRIMARY]


def check_timeline_overlaps(
    experience: list[ExperienceEntry], *, today: date, min_months: int
) -> list[CrossFieldFinding]:
    """Concurrent primary roles. UNKNOWN counts as primary (the heuristic
    extractor never labels full_time); the month threshold absorbs the noise."""
    dated = [
        (e, iv)
        for e in _primary(experience)
        if (iv := narrow_interval(e.dates, today)) is not None
    ]
    findings: list[CrossFieldFinding] = []
    for (a, ia), (b, ib) in itertools.combinations(dated, 2):
        months = overlap_months(ia, ib)
        if months < min_months:
            continue
        severity = (
            FindingSeverity.MAJOR
            if months >= _OVERLAP_MAJOR_MONTHS
            else FindingSeverity.MINOR
        )
        findings.append(
            CrossFieldFinding(
                id="timeline_overlap",
                severity=severity,
                score=min(1.0, months / 24),
                detail=(
                    f"'{_label(a)}' and '{_label(b)}' overlap by at least "
                    f"{months} months of concurrent primary employment"
                ),
                entry_ids=[a.id, b.id],
            )
        )
    return findings


def check_timeline_gaps(
    experience: list[ExperienceEntry], *, today: date, min_months: int
) -> list[CrossFieldFinding]:
    """Gaps between merged month-precise primary intervals. Year-only dates
    can't measure a gap honestly, so they are skipped — never flagged."""
    intervals = sorted(
        iv
        for e in _primary(experience)
        if (iv := month_precise_interval(e.dates, today)) is not None
    )
    merged: list[list[int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    findings: list[CrossFieldFinding] = []
    for (_, e1), (s2, _) in zip(merged, merged[1:]):
        gap = s2 - e1 - 1
        if gap < min_months:
            continue
        findings.append(
            CrossFieldFinding(
                id="timeline_gap",
                severity=FindingSeverity.MINOR,  # NEVER major: breaks are normal
                score=min(1.0, gap / 36),
                detail=(
                    f"{gap}-month gap between primary roles ({_ym(e1)} -> {_ym(s2)}); "
                    f"career breaks are legitimate — context only"
                ),
            )
        )
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cross_field_timeline.py -q`
Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add app/fabrication/cross_field.py tests/test_cross_field_timeline.py
git commit -m "feat(fabrication): interval math + timeline overlap/gap checks (S2.2)"
```

---

### Task 3: Coherence checks (education↔employment, seniority-vs-tenure)

**Files:**
- Modify: `app/fabrication/cross_field.py` (append two checks + their constants)
- Test: `tests/test_cross_field_coherence.py`

**Interfaces:**
- Consumes: Task 2 helpers (`narrow_interval`, `wide_interval`, `overlap_months`, `_primary`, `_label`).
- Produces (Task 4 relies on these exact names):
  - `check_education_overlap(education: list[EducationEntry], experience: list[ExperienceEntry], *, today: date, min_months: int) -> list[CrossFieldFinding]`
  - `check_seniority_vs_tenure(experience: list[ExperienceEntry], *, today: date, senior_min_months: int, lead_min_months: int) -> list[CrossFieldFinding]`
  - `is_bachelor(edu: EducationEntry) -> bool`
  - Constants `_EDU_MAJOR_MONTHS = 24`, `_LEAD_RE`, `_SENIOR_RE`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cross_field_coherence.py`:

```python
"""Education↔employment coherence + seniority-vs-tenure — pure, offline."""

from datetime import date

from app.candidates.schema import DateRange, EducationEntry, EmploymentType, ExperienceEntry
from app.fabrication.cross_field import (
    check_education_overlap,
    check_seniority_vs_tenure,
    is_bachelor,
)
from app.schemas.fabrication import FindingSeverity

TODAY = date(2026, 7, 1)


def _exp(start, end, *, etype=EmploymentType.FULL_TIME, title="Engineer"):
    return ExperienceEntry(
        title=title,
        employer="Acme",
        employment_type=etype,
        dates=DateRange(start=start, end=end),
    )


def _btech(start="2018", end="2022", level="bachelor"):
    return EducationEntry(
        degree="B.Tech in Computer Science",
        institution="NIT Trichy",
        degree_level=level,
        dates=DateRange(start=start, end=end),
    )


def test_is_bachelor_uses_canonical_level_and_keyword_fallback():
    assert is_bachelor(_btech()) is True
    assert is_bachelor(_btech(level=None)) is True  # falls back to "B.Tech" keyword
    master = EducationEntry(degree="M.Tech", degree_level="master")
    assert is_bachelor(master) is False


def test_edu_overlap_fires_on_fulltime_role_inside_bachelors():
    # Bachelor's 2018–2022 narrows to Dec 2018 .. Jan 2022; the role covers
    # Jun 2020 .. Jan 2022 of it = 20 months >= 12 -> minor (< 24).
    edu = _btech()
    exp = _exp("2020-06", "2022-08")
    findings = check_education_overlap([edu], [exp], today=TODAY, min_months=12)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "education_employment_overlap"
    assert f.severity is FindingSeverity.MINOR
    assert set(f.entry_ids) == {edu.id, exp.id}
    assert "20 months" in f.detail


def test_edu_overlap_major_at_two_years():
    edu = _btech(start="2018-07", end="2022-05")
    exp = _exp("2019-01", "2021-06")  # 30 months inside the degree
    findings = check_education_overlap([edu], [exp], today=TODAY, min_months=12)
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.MAJOR


def test_edu_overlap_ignores_masters_and_internships():
    # Part-time/executive master's programmes are common; internships during a
    # bachelor's are normal. Neither may fire.
    master = EducationEntry(degree="M.Tech", degree_level="master",
                            dates=DateRange(start="2019", end="2023"))
    intern = _exp("2020-06", "2021-08", etype=EmploymentType.INTERNSHIP)
    assert check_education_overlap([master], [_exp("2020-01", "2022-01")],
                                   today=TODAY, min_months=12) == []
    assert check_education_overlap([_btech()], [intern],
                                   today=TODAY, min_months=12) == []


def test_lead_title_with_thin_span_is_major():
    a = _exp("2020-06", "2022-08", title="Lead AI Engineer")
    b = _exp("2021-01", "2022-08")
    findings = check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "seniority_vs_tenure"
    assert f.severity is FindingSeverity.MAJOR  # lead-level claim, 27-month span
    assert f.entry_ids == [a.id]
    assert "27 months" in f.detail


def test_senior_title_with_thin_span_is_minor_only():
    # Title inflation at "senior" is common; keep it context, not accusation.
    a = _exp("2021-06", "2022-08", title="Senior Engineer")
    b = _exp("2022-01", "2022-12", title="Senior Engineer")
    findings = check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    )
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.MINOR


def test_adequate_span_is_silent():
    a = _exp("2018-01", "2021-12", title="Senior Engineer")
    b = _exp("2022-01", "2024-06", title="Lead Engineer")  # 78-month span
    assert check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    ) == []


def test_seniority_needs_two_dated_entries():
    # One dated entry could be a truncated resume -> conservative: skip.
    a = _exp("2024-01", "2025-06", title="Lead Engineer")
    assert check_seniority_vs_tenure(
        [a], today=TODAY, senior_min_months=24, lead_min_months=48
    ) == []


def test_plain_titles_never_fire():
    a = _exp("2023-01", "2023-12", title="Software Engineer")
    b = _exp("2024-01", "2024-12", title="ML Engineer")
    assert check_seniority_vs_tenure(
        [a, b], today=TODAY, senior_min_months=24, lead_min_months=48
    ) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cross_field_coherence.py -q`
Expected: FAIL — `ImportError: cannot import name 'check_education_overlap'`

- [ ] **Step 3: Append the checks**

Append to `app/fabrication/cross_field.py`:

```python
_EDU_MAJOR_MONTHS = 24  # two years of full-time work inside a degree

# Bachelor-only: part-time/executive master's programmes (WILP, distance MBA)
# are common in India, so postgraduate overlap is never flagged.
_BACHELOR_RE = re.compile(
    r"\b(b\.?\s?tech|b\.?e\b|b\.?sc|bca|bachelor)", re.IGNORECASE
)

# Seniority ladders. "lead-level" floors are for lead/principal/staff/head+.
_LEAD_RE = re.compile(
    r"\b(lead|principal|staff|head|director|vp|vice president|chief|cto)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE)


def is_bachelor(edu: EducationEntry) -> bool:
    """Canonical level (S1.4) first; keyword fallback for un-normalized rows."""
    if edu.degree_level is not None:
        return edu.degree_level == "bachelor"
    return bool(edu.degree and _BACHELOR_RE.search(edu.degree))


def check_education_overlap(
    education: list[EducationEntry],
    experience: list[ExperienceEntry],
    *,
    today: date,
    min_months: int,
) -> list[CrossFieldFinding]:
    """Primary employment running inside a bachelor's programme."""
    dated_exp = [
        (e, iv)
        for e in _primary(experience)
        if (iv := narrow_interval(e.dates, today)) is not None
    ]
    findings: list[CrossFieldFinding] = []
    for edu in education:
        if not is_bachelor(edu):
            continue
        edu_iv = narrow_interval(edu.dates, today)
        if edu_iv is None:
            continue
        for exp, exp_iv in dated_exp:
            months = overlap_months(edu_iv, exp_iv)
            if months < min_months:
                continue
            severity = (
                FindingSeverity.MAJOR
                if months >= _EDU_MAJOR_MONTHS
                else FindingSeverity.MINOR
            )
            findings.append(
                CrossFieldFinding(
                    id="education_employment_overlap",
                    severity=severity,
                    score=min(1.0, months / 24),
                    detail=(
                        f"primary role '{_label(exp)}' overlaps the bachelor's at "
                        f"{edu.institution or 'unknown institution'} by at least "
                        f"{months} months"
                    ),
                    entry_ids=[edu.id, exp.id],
                )
            )
    return findings


def check_seniority_vs_tenure(
    experience: list[ExperienceEntry],
    *,
    today: date,
    senior_min_months: int,
    lead_min_months: int,
) -> list[CrossFieldFinding]:
    """Claimed rank vs. the widest possible career span. Uses wide intervals
    (span is an upper bound) and requires >= 2 dated entries, so a truncated
    single-role resume never fires. Lead-level -> major; senior -> minor
    (title inflation at 'senior' is common — context, not accusation)."""
    intervals = [
        iv for e in experience if (iv := wide_interval(e.dates, today)) is not None
    ]
    if len(intervals) < 2:
        return []
    span = max(e for _, e in intervals) - min(s for s, _ in intervals) + 1

    def _first(pattern: re.Pattern[str], level: str) -> ExperienceEntry | None:
        return next(
            (
                e
                for e in experience
                if pattern.search(e.title or "") or (e.seniority or "") == level
            ),
            None,
        )

    lead = _first(_LEAD_RE, "staff")
    senior = _first(_SENIOR_RE, "senior")
    if lead is not None and span < lead_min_months:
        entry, floor, severity = lead, lead_min_months, FindingSeverity.MAJOR
    elif senior is not None and span < senior_min_months:
        entry, floor, severity = senior, senior_min_months, FindingSeverity.MINOR
    else:
        return []
    return [
        CrossFieldFinding(
            id="seniority_vs_tenure",
            severity=severity,
            score=min(1.0, 0.5 + 0.5 * (floor - span) / floor),
            detail=(
                f"'{entry.title}' claimed with roughly {span} months of total "
                f"career span (conservative floor for this level: {floor} months)"
            ),
            entry_ids=[entry.id],
        )
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cross_field_coherence.py tests/test_cross_field_timeline.py -q`
Expected: `21 passed`

- [ ] **Step 5: Commit**

```bash
git add app/fabrication/cross_field.py tests/test_cross_field_coherence.py
git commit -m "feat(fabrication): education-overlap + seniority-vs-tenure checks (S2.2)"
```

---

### Task 4: Assessment, banding, config knobs, adversarial fixture

**Files:**
- Modify: `app/fabrication/cross_field.py` (append `band_for_findings`, `assess_cross_field`)
- Modify: `app/core/config.py` (six `xf_*` fields), `config.yaml` (same keys)
- Create: `tests/fixtures/inconsistent_genai_resume.txt`
- Modify: `tests/conftest.py` (add `inconsistent_resume` fixture)
- Test: `tests/test_cross_field_assess.py`

**Interfaces:**
- Consumes: Tasks 2–3 checks; `CandidateProfile` from `app.candidates.schema`; `Settings` from `app.core.config`.
- Produces (Task 5 relies on these exact names):
  - `band_for_findings(findings: list[CrossFieldFinding], confidence: float, settings: Settings) -> ConsistencyBand`
  - `assess_cross_field(profile: CandidateProfile, settings: Settings, today: date | None = None) -> CrossFieldAssessment` — per evaluated check, contributes `max(finding scores, default 0.0)`; `score` = mean over evaluated checks; `confidence = min(0.9, 0.30 + 0.15 * evaluated)` (`0.0` when nothing evaluated — same formula as S2.1).
  - `Settings.xf_min_confidence/xf_overlap_months_min/xf_gap_months_min/xf_edu_overlap_months_min/xf_senior_min_months/xf_lead_min_months`
  - conftest fixture `inconsistent_resume: str`

- [ ] **Step 1: Create the adversarial fixture**

Create `tests/fixtures/inconsistent_genai_resume.txt` with EXACTLY this content. It is deliberately heuristic-extractable (non-bullet `Title at Employer, <dates>` experience lines; a degree line matching the extractor's degree/grade patterns) and carries no `Present` dates, so every derived number is stable regardless of the test run date. It trips: a 20-month primary-role overlap (major), a bachelor's↔employment overlap (minor, 20 months against the narrowed 2018–2022 degree), and a lead-level title on a 27-month career span (major):

```
Rohan Iyer — Lead GenAI Engineer
Bengaluru | rohan.iyer@example.com | +91 98450 12345

EXPERIENCE

Lead AI Engineer at DataSphere Analytics, Jan 2021 - Aug 2022
- Built retrieval pipelines over 40M documents with pgvector and a reranker
- Owned the LLM evaluation harness used across three product teams
- Cut inference cost by moving batch scoring onto quantized open-weight models

Senior GenAI Engineer at TechNova Solutions, Jun 2020 - Aug 2022
- Shipped a RAG assistant for support workflows end to end
- Fine-tuned open-weight models on curated internal ticket datasets
- Ran A/B evaluations against the hosted-API baseline before each release

EDUCATION

B.Tech in Computer Science — NIT Trichy, 2018 - 2022, CGPA 8.4/10

SKILLS

Python, PyTorch, LangChain, pgvector, AWS
```

Add to `tests/conftest.py` (next to the `ai_resume` fixture):

```python
@pytest.fixture
def inconsistent_resume() -> str:
    return (FIXTURES / "inconsistent_genai_resume.txt").read_text(encoding="utf-8")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_cross_field_assess.py`:

```python
"""Cross-field assessment + structural banding — pure, offline."""

from datetime import date

from app.candidates.extractor import heuristic_profile
from app.candidates.normalize import normalize_profile
from app.candidates.schema import CandidateProfile, DateRange, EmploymentType, ExperienceEntry, EducationEntry
from app.fabrication.cross_field import assess_cross_field, band_for_findings
from app.schemas.fabrication import ConsistencyBand, CrossFieldFinding, FindingSeverity

TODAY = date(2026, 7, 1)


def _consistent_profile() -> CandidateProfile:
    return CandidateProfile(
        education=[
            EducationEntry(degree="B.Tech", degree_level="bachelor",
                           dates=DateRange(start="2014", end="2018")),
        ],
        experience=[
            ExperienceEntry(title="Software Engineer", employer="A",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2019-01", end="2020-12")),
            ExperienceEntry(title="Senior Engineer", employer="B",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2021-02", end="2023-06")),
        ],
    )


def test_inconsistent_fixture_lands_in_major_issues(inconsistent_resume, settings):
    profile = normalize_profile(heuristic_profile(inconsistent_resume))
    a = assess_cross_field(profile, settings, today=TODAY)
    assert a.band is ConsistencyBand.MAJOR_ISSUES
    assert a.confidence == 0.9  # all four checks had enough data
    ids = {f.id for f in a.findings}
    assert {"timeline_overlap", "education_employment_overlap",
            "seniority_vs_tenure"} <= ids
    assert a.score > 0.4
    assert all(f.detail for f in a.findings)
    assert a.advisory is True


def test_consistent_profile_is_consistent(settings):
    a = assess_cross_field(_consistent_profile(), settings, today=TODAY)
    assert a.findings == []
    assert a.band is ConsistencyBand.CONSISTENT
    assert a.score == 0.0
    assert a.confidence >= settings.xf_min_confidence


def test_empty_profile_is_insufficient(settings):
    a = assess_cross_field(CandidateProfile(), settings, today=TODAY)
    assert a.band is ConsistencyBand.INSUFFICIENT_DATA
    assert a.confidence == 0.0


def test_minor_findings_never_reach_major_band(settings):
    minor = CrossFieldFinding(id="timeline_gap", detail="d", score=0.4,
                              severity=FindingSeverity.MINOR)
    assert band_for_findings([minor], 0.9, settings) is ConsistencyBand.MINOR_ISSUES
    major = CrossFieldFinding(id="timeline_overlap", detail="d", score=0.8,
                              severity=FindingSeverity.MAJOR)
    assert band_for_findings([major], 0.9, settings) is ConsistencyBand.MAJOR_ISSUES
    assert band_for_findings([], 0.9, settings) is ConsistencyBand.CONSISTENT


def test_low_confidence_never_asserts(settings):
    major = CrossFieldFinding(id="timeline_overlap", detail="d", score=0.9,
                              severity=FindingSeverity.MAJOR)
    assert band_for_findings([major], 0.3, settings) is ConsistencyBand.INSUFFICIENT_DATA


def test_reasoning_names_the_findings(settings):
    profile = _consistent_profile()
    profile.experience.append(
        ExperienceEntry(title="Engineer", employer="C",
                        employment_type=EmploymentType.FULL_TIME,
                        dates=DateRange(start="2021-06", end="2023-06"))
    )
    a = assess_cross_field(profile, settings, today=TODAY)
    assert "timeline_overlap" in a.reasoning


def test_settings_expose_xf_knobs(settings):
    assert settings.xf_min_confidence == 0.50
    assert settings.xf_overlap_months_min == 3
    assert settings.xf_gap_months_min == 12
    assert settings.xf_edu_overlap_months_min == 12
    assert settings.xf_senior_min_months == 24
    assert settings.xf_lead_min_months == 48
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_cross_field_assess.py -q`
Expected: FAIL — `ImportError: cannot import name 'assess_cross_field'`

- [ ] **Step 4: Implement assessment + banding + knobs**

Append to `app/fabrication/cross_field.py` (and add these two imports at the top of the file):

```python
from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.schemas.fabrication import ConsistencyBand, CrossFieldAssessment
```

(Merge with the existing `app.candidates.schema` / `app.schemas.fabrication` import lines rather than duplicating them.)

```python
def band_for_findings(
    findings: list[CrossFieldFinding], confidence: float, settings: Settings
) -> ConsistencyBand:
    """Structural, conservative banding: never assert below the confidence
    floor; MAJOR_ISSUES requires at least one major finding."""
    if confidence < settings.xf_min_confidence:
        return ConsistencyBand.INSUFFICIENT_DATA
    if any(f.severity is FindingSeverity.MAJOR for f in findings):
        return ConsistencyBand.MAJOR_ISSUES
    if findings:
        return ConsistencyBand.MINOR_ISSUES
    return ConsistencyBand.CONSISTENT


def assess_cross_field(
    profile: CandidateProfile, settings: Settings, today: date | None = None
) -> CrossFieldAssessment:
    """Run every check that has enough data; a checked-and-clean check still
    counts toward confidence (same shape as S2.1's assess_deterministic)."""
    today = today or date.today()
    findings: list[CrossFieldFinding] = []
    scores: list[float] = []

    def _run(check_findings: list[CrossFieldFinding]) -> None:
        scores.append(max((f.score for f in check_findings), default=0.0))
        findings.extend(check_findings)

    prim_narrow = [
        e for e in _primary(profile.experience)
        if narrow_interval(e.dates, today) is not None
    ]
    prim_precise = [
        e for e in _primary(profile.experience)
        if month_precise_interval(e.dates, today) is not None
    ]
    bachelors = [
        e for e in profile.education
        if is_bachelor(e) and narrow_interval(e.dates, today) is not None
    ]
    dated_any = [
        e for e in profile.experience if wide_interval(e.dates, today) is not None
    ]

    if len(prim_narrow) >= 2:
        _run(check_timeline_overlaps(
            profile.experience, today=today,
            min_months=settings.xf_overlap_months_min,
        ))
    if len(prim_precise) >= 2:
        _run(check_timeline_gaps(
            profile.experience, today=today,
            min_months=settings.xf_gap_months_min,
        ))
    if bachelors and prim_narrow:
        _run(check_education_overlap(
            profile.education, profile.experience, today=today,
            min_months=settings.xf_edu_overlap_months_min,
        ))
    if len(dated_any) >= 2:
        _run(check_seniority_vs_tenure(
            profile.experience, today=today,
            senior_min_months=settings.xf_senior_min_months,
            lead_min_months=settings.xf_lead_min_months,
        ))

    evaluated = len(scores)
    if not evaluated:
        return CrossFieldAssessment()
    confidence = min(0.9, 0.30 + 0.15 * evaluated)
    reasoning = f"[deterministic] {len(findings)} finding(s) across {evaluated} evaluated checks"
    if findings:
        reasoning += ": " + ", ".join(sorted({f.id for f in findings}))
    return CrossFieldAssessment(
        score=sum(scores) / evaluated,
        confidence=confidence,
        band=band_for_findings(findings, confidence, settings),
        findings=findings,
        reasoning=reasoning,
        advisory=True,
    )
```

Add to `app/core/config.py`, directly after the S2.1 `ai_*` block:

```python
    # --- Fabrication defense (PI-2, S2.2): cross-field forensics ----------------
    # Deterministic date/structure checks over the extracted profile. ADVISORY:
    # findings are observations for a reviewer to probe, never a rejection
    # signal. Month thresholds are lower bounds computed with conservative
    # interval math (year-only dates shrink inward for overlaps).
    xf_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    xf_overlap_months_min: int = 3
    xf_gap_months_min: int = 12
    xf_edu_overlap_months_min: int = 12
    xf_senior_min_months: int = 24
    xf_lead_min_months: int = 48
```

Add to `config.yaml`, directly after the S2.1 `ai_*` block:

```yaml
# --- Fabrication defense (PI-2) — S2.2 cross-field forensics -------------------
# Deterministic date/structure checks over the extracted profile. ADVISORY:
# findings are observations for a reviewer to probe, never a rejection signal.
xf_min_confidence: 0.50          # below this -> band "insufficient_data"
xf_overlap_months_min: 3         # concurrent primary roles flagged at >= this many months
xf_gap_months_min: 12            # gaps flagged at >= this (always minor/context)
xf_edu_overlap_months_min: 12    # primary work inside a bachelor's flagged at >= this
xf_senior_min_months: 24         # "senior" below this career span -> minor finding
xf_lead_min_months: 48           # lead/principal/head+ below this span -> major finding
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cross_field_assess.py tests/test_cross_field_timeline.py tests/test_cross_field_coherence.py -q`
Expected: `28 passed`. If `test_inconsistent_fixture_lands_in_major_issues` fails, debug the heuristic extraction first (`heuristic_profile` must lift both experience entries with month dates and the B.Tech with 2018–2022): the experience lines must stay non-bulleted `Title at Employer, Mon YYYY - Mon YYYY`, the degree line must keep the `B.Tech in … — … , 2018 - 2022, CGPA …` shape. Do not loosen the assertions.

- [ ] **Step 6: Run the full suite (config change must not break anything)**

Run: `pytest -q`
Expected: all green (~253 tests).

- [ ] **Step 7: Commit**

```bash
git add app/fabrication/cross_field.py app/core/config.py config.yaml tests/fixtures/inconsistent_genai_resume.txt tests/conftest.py tests/test_cross_field_assess.py
git commit -m "feat(fabrication): cross-field assessment, banding, config knobs + adversarial fixture"
```

---

### Task 5: cross_field graph node + state + engine/API pass-through

**Files:**
- Create: `app/graph/nodes/cross_field.py`
- Modify: `app/graph/state.py` (two new fields), `app/graph/nodes/__init__.py`, `app/graph/build.py` (`_PIPELINE`, docstring, `evaluate` kwarg), `app/api/routes.py` (POST /candidates passes the profile)
- Test: `tests/test_cross_field_node.py`

**Interfaces:**
- Consumes: `assess_cross_field` (Task 4); `heuristic_profile` (`app.candidates.extractor`), `normalize_profile` (`app.candidates.normalize`); `CandidateProfile`.
- Produces: `make_cross_field_node(services) -> async node(state) -> dict` returning `{"cross_field": CrossFieldAssessment}` (or `{}` when no resume text); state fields `EvaluationState.candidate_profile: Optional[CandidateProfile]` (input) and `EvaluationState.cross_field: Optional[CrossFieldAssessment]` (output); pipeline order `ingest → ai_signals → cross_field → claim_extraction → …`; `EvaluationEngine.evaluate(..., candidate_profile: Optional[CandidateProfile] = None)`. Task 6 reads `state.cross_field`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cross_field_node.py`:

```python
"""cross_field node: explicit profile, heuristic fallback, wiring."""

from app.candidates.schema import CandidateProfile, DateRange, EmploymentType, ExperienceEntry
from app.graph.build import _PIPELINE
from app.graph.nodes.cross_field import make_cross_field_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import ConsistencyBand


def _overlapping_profile() -> CandidateProfile:
    return CandidateProfile(
        experience=[
            ExperienceEntry(title="Lead Engineer", employer="A",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2021-01", end="2022-08")),
            ExperienceEntry(title="Senior Engineer", employer="B",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2020-06", end="2022-08")),
        ],
    )


async def test_explicit_profile_is_used_not_the_text(services):
    # The text alone carries no dates; findings prove the profile was used.
    node = make_cross_field_node(services)
    state = EvaluationState(
        resume_text="plain text with no dates at all",
        candidate_profile=_overlapping_profile(),
    )
    out = await node(state)
    a = out["cross_field"]
    assert any(f.id == "timeline_overlap" for f in a.findings)
    assert a.advisory is True


async def test_heuristic_fallback_flags_the_inconsistent_fixture(services, inconsistent_resume):
    node = make_cross_field_node(services)
    out = await node(EvaluationState(resume_text=inconsistent_resume))
    assert out["cross_field"].band is ConsistencyBand.MAJOR_ISSUES


async def test_no_text_produces_no_assessment(services):
    node = make_cross_field_node(services)
    assert await node(EvaluationState()) == {}
    assert await node(EvaluationState(resume_text="   ")) == {}


async def test_genuine_resume_is_not_major(services, genuine_resume):
    node = make_cross_field_node(services)
    out = await node(EvaluationState(resume_text=genuine_resume))
    assert out["cross_field"].band is not ConsistencyBand.MAJOR_ISSUES


def test_pipeline_wires_cross_field_after_ai_signals():
    names = [name for name, _ in _PIPELINE]
    assert names.index("cross_field") == names.index("ai_signals") + 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cross_field_node.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.graph.nodes.cross_field'`

- [ ] **Step 3: Implement node, state fields, wiring, pass-through**

Create `app/graph/nodes/cross_field.py`:

```python
"""cross_field — advisory cross-field forensics (S2.2, PI-2).

Purely deterministic date/structure checks over the extracted profile —
NO LLM by design (the convention demands fallbacks for LLM steps, not LLMs
everywhere; month arithmetic needs no model). When the caller supplied an
extracted CandidateProfile (POST /candidates), that profile is used; otherwise
the node derives one with the deterministic heuristic extractor, so
POST /evaluate gets the same forensics at heuristic-extraction quality.
Findings never touch claim verdicts or depth scoring (S2.4 owns fusion)."""

from __future__ import annotations

from app.candidates.extractor import heuristic_profile
from app.candidates.normalize import normalize_profile
from app.core.logging import get_logger
from app.fabrication.cross_field import assess_cross_field
from app.graph.state import EvaluationState
from app.services import Services


def make_cross_field_node(services: Services):
    log = get_logger("node.cross_field")

    async def cross_field(state: EvaluationState) -> dict:
        text = (state.resume_text or "").strip()
        if not text:
            return {}

        profile = state.candidate_profile
        source = "extracted"
        if profile is None:
            profile = normalize_profile(heuristic_profile(text))
            source = "heuristic"

        assessment = assess_cross_field(profile, services.settings)
        log.info(
            "cross_field_done",
            band=assessment.band.value,
            findings=len(assessment.findings),
            confidence=round(assessment.confidence, 3),
            profile_source=source,
        )
        return {"cross_field": assessment}

    return cross_field
```

In `app/graph/state.py`:

Add the imports:

```python
from app.candidates.schema import CandidateProfile
from app.schemas.fabrication import AIGenerationAssessment, CrossFieldAssessment
```

(The `AIGenerationAssessment` import already exists — extend that line.)

Add to the *inputs* block (after `portfolio_url`):

```python
    # S2.2: the extracted profile, when the caller already has one
    # (POST /candidates). None => cross_field derives a heuristic profile.
    candidate_profile: Optional[CandidateProfile] = None
```

Add after the ai_signals block:

```python
    # --- cross_field (S2.2) -----------------------------------------------------
    # Advisory cross-field forensics; None when resume text never arrived.
    cross_field: Optional[CrossFieldAssessment] = None
```

In `app/graph/nodes/__init__.py`: add the import and `__all__` entry:

```python
from app.graph.nodes.cross_field import make_cross_field_node
```

(and add `"make_cross_field_node",` to `__all__`.)

In `app/graph/build.py`:

- Import `make_cross_field_node` from `app.graph.nodes` and `CandidateProfile` from `app.candidates.schema`.
- Update the module docstring chain to `ingest → ai_signals → cross_field → claim_extraction → provenance → plausibility → probe_generation → scoring → report`.
- Insert into `_PIPELINE` directly after ai_signals:

```python
_PIPELINE = [
    ("ingest", make_ingest_node),
    ("ai_signals", make_ai_signals_node),
    ("cross_field", make_cross_field_node),
    ("claim_extraction", make_claim_extraction_node),
    ("provenance", make_provenance_node),
    ("plausibility", make_plausibility_node),
    ("probe_generation", make_probe_generation_node),
    ("scoring", make_scoring_node),
    ("report", make_report_node),
]
```

- Extend `EvaluationEngine.evaluate` with the new keyword and thread it into the initial state:

```python
    async def evaluate(
        self,
        *,
        resume_text: Optional[str] = None,
        resume_pdf_b64: Optional[str] = None,
        github_url: Optional[str] = None,
        portfolio_url: Optional[str] = None,
        domain: str = "genai",
        candidate_profile: Optional[CandidateProfile] = None,
    ) -> Report:
        initial = EvaluationState(
            domain=domain,
            raw_resume_text=resume_text,
            resume_pdf_b64=resume_pdf_b64,
            github_url=github_url,
            portfolio_url=portfolio_url,
            candidate_profile=candidate_profile,
        )
```

In `app/api/routes.py`, POST /candidates: pass the extracted profile through (the graph stays candidate-store-unaware — a profile is just a schema object):

```python
        report = await request.app.state.engine.evaluate(
            resume_text=text, domain=req.domain, candidate_profile=result.profile
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cross_field_node.py -q`
Expected: `5 passed`

- [ ] **Step 5: Run the full suite (node insertion must not break the graph)**

Run: `pytest -q`
Expected: all green (~258 tests).

- [ ] **Step 6: Commit**

```bash
git add app/graph/nodes/cross_field.py app/graph/state.py app/graph/nodes/__init__.py app/graph/build.py app/api/routes.py tests/test_cross_field_node.py
git commit -m "feat(graph): cross_field node after ai_signals; profile pass-through from POST /candidates"
```

---

### Task 6: Surface on Report + flywheel record

**Files:**
- Modify: `app/schemas/report.py` (new optional field), `app/graph/nodes/report.py` (pass-through, summary sentence for major only, flywheel record)
- Test: `tests/test_report_cross_field.py`

**Interfaces:**
- Consumes: `state.cross_field` (Task 5), `CrossFieldAssessment`/`ConsistencyBand`/`FindingSeverity` (Task 1), `services.flywheel.log(dict)`.
- Produces: `Report.cross_field: Optional[CrossFieldAssessment] = None`; summary suffix ONLY when band is `MAJOR_ISSUES` (minor findings stay off the summary — gaps are context, not alarms; the full assessment is always on the report body); one flywheel record `{"record_type": "cross_field", ...}` whenever an assessment exists. Tasks 7–8 assert on these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_report_cross_field.py`:

```python
"""Report node: cross_field pass-through, summary copy, flywheel record."""

from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import (
    ConsistencyBand,
    CrossFieldAssessment,
    CrossFieldFinding,
    FindingSeverity,
)


def _assessment(band: ConsistencyBand, severity=FindingSeverity.MAJOR) -> CrossFieldAssessment:
    return CrossFieldAssessment(
        score=0.6,
        confidence=0.9,
        band=band,
        findings=[CrossFieldFinding(id="timeline_overlap", detail="d",
                                    severity=severity, score=0.8)],
        reasoning="[deterministic] 1 finding(s) across 4 evaluated checks",
    )


async def test_report_carries_cross_field_and_major_summary_note(services):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", cross_field=_assessment(ConsistencyBand.MAJOR_ISSUES)
    )
    rep = (await node(state))["report"]
    assert rep.cross_field is not None
    assert rep.cross_field.band is ConsistencyBand.MAJOR_ISSUES
    assert "Cross-field consistency: major_issues" in rep.summary
    assert "never a rejection signal" in rep.summary
    assert rep.advisory is True and rep.human_review_required is True


async def test_minor_band_stays_out_of_summary(services):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x",
        cross_field=_assessment(ConsistencyBand.MINOR_ISSUES, FindingSeverity.MINOR),
    )
    rep = (await node(state))["report"]
    assert rep.cross_field is not None               # data still on the report...
    assert "Cross-field consistency" not in rep.summary  # ...but no reviewer noise


async def test_no_assessment_means_none_and_no_record(services, flywheel):
    node = make_report_node(services)
    rep = (await node(EvaluationState(resume_text="x")))["report"]
    assert rep.cross_field is None
    assert not [r for r in flywheel.records if r.get("record_type") == "cross_field"]


async def test_flywheel_gets_one_cross_field_record(services, flywheel):
    node = make_report_node(services)
    state = EvaluationState(
        resume_text="x", cross_field=_assessment(ConsistencyBand.MAJOR_ISSUES)
    )
    rep = (await node(state))["report"]
    rows = [r for r in flywheel.records if r.get("record_type") == "cross_field"]
    assert len(rows) == 1
    assert rows[0]["report_id"] == rep.id
    assert rows[0]["band"] == "major_issues"
    assert rows[0]["finding_ids"] == ["timeline_overlap"]
    assert rows[0]["outcome"] is None  # closed later by human feedback
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report_cross_field.py -q`
Expected: FAIL — `Report` has no field `cross_field` (ValidationError or AttributeError).

- [ ] **Step 3: Implement**

In `app/schemas/report.py`: extend the fabrication import and add the field on `Report` (after `ai_generation`):

```python
from app.schemas.fabrication import AIGenerationAssessment, CrossFieldAssessment
```

```python
    # S2.2: advisory cross-field forensics (timeline/coherence observations for
    # the reviewer, never a verdict; fusion into calibration is S2.4). None for
    # pre-S2.2 stored reports.
    cross_field: Optional[CrossFieldAssessment] = None
```

In `app/graph/nodes/report.py`: extend the fabrication import:

```python
from app.schemas.fabrication import AILikelihoodBand, ConsistencyBand, FindingSeverity
```

After the existing S2.1 `ai` summary suffix block, append:

```python
        xf = state.cross_field
        if xf is not None and xf.band is ConsistencyBand.MAJOR_ISSUES:
            majors = sum(1 for f in xf.findings if f.severity is FindingSeverity.MAJOR)
            summary += (
                f" Cross-field consistency: {xf.band.value} ({majors} major of "
                f"{len(xf.findings)} findings) — timeline observations for the "
                f"reviewer to probe in conversation; never a rejection signal."
            )
```

Add `cross_field=state.cross_field,` to the `Report(...)` constructor call (after `ai_generation=state.ai_generation,`).

After the S2.1 `ai_signals` flywheel block, append:

```python
        if state.cross_field is not None:
            services.flywheel.log(
                {
                    "record_type": "cross_field",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.cross_field.band.value,
                    "score": state.cross_field.score,
                    "confidence": state.cross_field.confidence,
                    "finding_ids": [f.id for f in state.cross_field.findings],
                    "outcome": None,  # closed later by human/hiring signal
                }
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_cross_field.py tests/test_report.py tests/test_report_ai.py -q`
Expected: all pass (4 new + existing report tests untouched).

- [ ] **Step 5: Commit**

```bash
git add app/schemas/report.py app/graph/nodes/report.py tests/test_report_cross_field.py
git commit -m "feat(report): surface advisory cross_field + flywheel record"
```

---

### Task 7: End-to-end integration tests

**Files:**
- Test: `tests/test_cross_field_integration.py`

**Interfaces:**
- Consumes: `EvaluationEngine` (`app/graph/build.py`), conftest fixtures `services`, `inconsistent_resume`, `genuine_resume`.
- Produces: regression guarantees the smoke script (Task 8) mirrors over HTTP.

- [ ] **Step 1: Write the tests**

Create `tests/test_cross_field_integration.py`:

```python
"""End-to-end (offline): the inconsistent fixture earns MAJOR_ISSUES with
explained findings via the heuristic-profile fallback; an explicitly passed
profile takes precedence; the genuine resume stays clean; and S2.2 stays
advisory — depth scoring and claim verdicts are untouched by the band."""

from app.candidates.schema import CandidateProfile, DateRange, EmploymentType, ExperienceEntry
from app.graph.build import EvaluationEngine
from app.schemas.fabrication import ConsistencyBand


async def test_inconsistent_resume_gets_major_issues(services, inconsistent_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=inconsistent_resume, domain="genai")

    assert report.cross_field is not None
    assert report.cross_field.band is ConsistencyBand.MAJOR_ISSUES
    assert len(report.cross_field.findings) >= 2
    assert all(f.detail for f in report.cross_field.findings)
    assert "Cross-field consistency: major_issues" in report.summary
    assert "never a rejection signal" in report.summary
    # Mandates survive: advisory, human decides.
    assert report.advisory is True
    assert report.human_review_required is True


async def test_explicit_profile_takes_precedence(services, genuine_resume):
    # The genuine TEXT is clean, but the caller-supplied profile overlaps:
    # findings prove POST /candidates' extraction wins over re-derivation.
    profile = CandidateProfile(
        experience=[
            ExperienceEntry(title="Lead Engineer", employer="A",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2021-01", end="2022-08")),
            ExperienceEntry(title="Senior Engineer", employer="B",
                            employment_type=EmploymentType.FULL_TIME,
                            dates=DateRange(start="2020-06", end="2022-08")),
        ],
    )
    engine = EvaluationEngine(services)
    report = await engine.evaluate(
        resume_text=genuine_resume, domain="genai", candidate_profile=profile
    )
    assert report.cross_field is not None
    assert any(f.id == "timeline_overlap" for f in report.cross_field.findings)


async def test_genuine_resume_is_clean_and_depth_unchanged(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, domain="genai")

    assert report.cross_field is not None
    assert report.cross_field.band is not ConsistencyBand.MAJOR_ISSUES
    # S2.2 must not perturb depth-eval: same expectations as test_integration.
    assert report.depth_band.value in {"solid", "deep"}
    incoherent = [v for v in report.verdicts if v.status.value == "incoherent"]
    assert not incoherent


async def test_report_json_round_trip_includes_cross_field(services, inconsistent_resume):
    from app.schemas.report import Report

    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=inconsistent_resume, domain="genai")
    again = Report.model_validate_json(report.model_dump_json())
    assert again.cross_field == report.cross_field
```

- [ ] **Step 2: Run the tests** (implementation landed in Tasks 5–6, so these should be green immediately; if any fails, fix the implementation, not the test)

Run: `pytest tests/test_cross_field_integration.py -q`
Expected: `4 passed`

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: all green (~266 tests, was 225).

- [ ] **Step 4: Commit**

```bash
git add tests/test_cross_field_integration.py
git commit -m "test: end-to-end cross-field forensics coverage"
```

---

### Task 8: Smoke script + ROADMAP close-out

**Files:**
- Create: `scripts/smoke_s22.py`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: the running app (`app.main:app` via uvicorn), fixtures `tests/fixtures/inconsistent_genai_resume.txt` and `tests/fixtures/genuine_genai_resume.txt`, `POST /candidates {resume_text, domain, evaluate: true}` (report carries the *extracted-profile* path) and `POST /evaluate {resume_text, domain}` (report carries the *heuristic-fallback* path).
- Produces: `python scripts/smoke_s22.py` exiting 0 with all checks OK, both key-less (heuristic extraction) and with a live OpenRouter key (LLM extraction).

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s22.py`:

```python
"""S2.2 smoke: cross-field forensics visible over the real HTTP surface.

Boots uvicorn on a scratch environment and exercises BOTH profile paths:
POST /candidates (extracted profile passed into the graph) and POST /evaluate
(heuristic-profile fallback inside the cross_field node). The inconsistent
fixture must surface explained findings on report.cross_field; the genuine
fixture must never reach major_issues; advisory mandates must hold. Works with
a live key (LLM extraction) and without one (heuristic floor). Run from the
repo root:
    python scripts/smoke_s22.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

INCONSISTENT_FIXTURE = Path("tests/fixtures/inconsistent_genai_resume.txt")
GENUINE_FIXTURE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8022
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s22.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            bad_text = INCONSISTENT_FIXTURE.read_text(encoding="utf-8")
            good_text = GENUINE_FIXTURE.read_text(encoding="utf-8")

            cand = c.post(
                "/candidates",
                json={"resume_text": bad_text, "domain": "genai", "evaluate": True},
            ).json()
            cand_rep = cand.get("report") or {}
            print(
                f"POST /candidates (inconsistent): candidate={cand.get('candidate_id', '?')} "
                f"extraction={cand.get('extraction_method', '?')} report={cand_rep.get('id', '?')}"
            )
            eval_rep = c.post(
                "/evaluate", json={"resume_text": bad_text, "domain": "genai"}
            ).json()
            print(f"POST /evaluate (inconsistent, heuristic fallback): report={eval_rep.get('id', '?')}")
            good_rep = c.post(
                "/evaluate", json={"resume_text": good_text, "domain": "genai"}
            ).json()
            print(f"POST /evaluate (genuine): report={good_rep.get('id', '?')}")

        cxf = cand_rep.get("cross_field") or {}
        exf = eval_rep.get("cross_field") or {}
        gxf = good_rep.get("cross_field") or {}
        checks = {
            "/candidates path: assessment present": bool(cxf),
            "/candidates path: band minor/major issues": cxf.get("band")
            in {"minor_issues", "major_issues"},
            "/candidates path: >=2 findings, all explained": len(cxf.get("findings", [])) >= 2
            and all(f.get("detail") for f in cxf.get("findings", [])),
            "/candidates path: timeline_overlap among findings": "timeline_overlap"
            in {f.get("id") for f in cxf.get("findings", [])},
            "/evaluate path (no stored profile): assessment present": bool(exf),
            "/evaluate path: major issues via heuristic fallback": exf.get("band")
            == "major_issues",
            "major band carries the advisory summary note": (
                "never a rejection signal" in eval_rep.get("summary", "")
                if exf.get("band") == "major_issues"
                else True
            ),
            "genuine fixture: never major_issues": gxf.get("band") != "major_issues",
            "mandates hold (advisory + human review)": eval_rep.get("advisory") is True
            and eval_rep.get("human_review_required") is True,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke key-less (heuristic extraction floor)**

PowerShell:

```powershell
$env:DEE_OPENROUTER_API_KEY = ""; python scripts/smoke_s22.py
```

Expected: all checks `OK`, exit 0. (Afterwards run `Remove-Item Env:DEE_OPENROUTER_API_KEY` so the live run isn't polluted.)

- [ ] **Step 3: Run the smoke live (with the real key from .env)**

```powershell
python scripts/smoke_s22.py
```

Expected: all checks `OK`, exit 0. The `/candidates` extraction method should print `llm`. If the LLM extraction labels the roles `full_time`, the overlap still fires (full_time is primary); band on the /candidates path may be `minor_issues` or `major_issues` — both pass.

- [ ] **Step 4: Full suite one last time**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: `[~] S2.2` → `[x] S2.2  Cross-field forensics — cross_field node (deterministic timeline/coherence checks over the extracted profile), advisory findings on Report`.
- Set S2.3 to `[~]` and **Current sprint** to `S2.3 — Resume-farm detection`; **Next action:** `Write the S2.3 plan (near-duplicate detection across candidates: minhash/embeddings).`
- Update **Last session** and append a session-log entry (today's date): branch `s22-cross-field`, files added, test count (225 → actual), smoke `scripts/smoke_s22.py` result key-less AND live.

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke_s22.py docs/ROADMAP.md
git commit -m "chore: S2.2 smoke script + roadmap close-out"
```

- [ ] **Step 7: Finish the branch**

Use superpowers:finishing-a-development-branch — verify `pytest -q` green, then merge `s22-cross-field` to `main` per the user's preference (previous sprints merged locally, no PR).

---

## Self-Review (performed at write time)

1. **Spec coverage:** Roadmap S2.2 scope = "timeline overlaps/gaps, education↔experience coherence, seniority-vs-claims" → Task 2 (overlaps + gaps), Task 3 (education↔employment overlap + seniority-vs-tenure). Sprint conventions (offline TDD, deterministic behavior with no key, advisory-only, config split, smoke, ROADMAP) → global constraints + Tasks 4/8. The "every LLM step degrades" convention is satisfied vacuously — S2.2 has no LLM step; the /evaluate path additionally gets a deterministic heuristic-profile fallback (Task 5). Fusion into calibration deliberately excluded (S2.4); resume-farm detection excluded (S2.3).
2. **Placeholder scan:** none — every code step carries full code; every run step has a command + expected outcome.
3. **Type consistency:** `CrossFieldFinding/CrossFieldAssessment/ConsistencyBand/FindingSeverity` defined in Task 1 and imported by those exact names in Tasks 2–7; `narrow_interval/wide_interval/month_precise_interval/overlap_months` defined in Task 2 with the signatures Tasks 3–4 call; `check_*` signatures in Tasks 2–3 match `assess_cross_field`'s calls in Task 4; `make_cross_field_node` exported in Task 5 and consumed by `build.py` there; `state.candidate_profile`/`state.cross_field`/`Report.cross_field` names match across Tasks 5–8. Fixture arithmetic verified by hand: exp overlap Jan 2021–Aug 2022 = 20 months (major); bachelor's 2018–2022 narrows to Dec 2018–Jan 2022, overlap with Jun 2020 start = 20 months (minor, < 24); wide career span Jun 2020–Aug 2022 = 27 months < 48 lead floor (major); no `Present` dates so results are independent of the run date.
