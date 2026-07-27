# S5.1 — Job Requisition + Role-Conditioned Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an org describe a role as a *job requisition* and get an advisory, explainable role-conditioned shortlist over the already-materialized candidate pool, reusing the S4.3 ranking engine plus one job-relative skill-coverage dimension.

**Architecture:** New `app/matching/` package layered like `app/ledger/`: pure contracts (`schema.py`) + pure engine (`match.py`, no I/O/clock) + ORM (`models.py`) + `JobStore` (`store.py`). The engine compiles a requisition into an S4.3 `RankingSpec` of soft terms, computes a synthetic `match.skill_coverage`/`match.location_fit` per candidate, injects them into a copy of each `FeatureVector`, and calls the existing `ranking.score()`. Org plane (`X-Org-Key`); every returned candidate is audited as a `match.surface` disclosure in the existing `audit_log`.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLAlchemy + Alembic on SQLite (Postgres-shaped), FastAPI, pytest (fully offline).

## Global Constraints

- **TDD, fully offline** (NullLLM/fakes); `pytest -q` green before every commit. **No LLM in S5.1.**
- **Advisory only** — matching narrows/orders, never auto-rejects; a missing/consent-withheld value **drops its term, never the candidate**.
- **DPDP:** `job_requisitions` is org-owned (CASCADE on `org_id`), **not candidate-linked** — it survives candidate erasure. `match.surface` audit rows are candidate-linked and CASCADE. **No new `ConsentPurpose`.**
- **Consent already masked at S4.2 materialization** — matching adds no new consent gate.
- **Config:** tunables in `config.yaml` (ASCII-only comments — cp1252 read on Windows) + `Settings`; `DEE_*` overridable.
- **DB:** SQLAlchemy + Alembic; schema is Alembic's job, never `create_all` in builders. Drift/index/FK/nullability guards must pass.
- **Point-in-time:** one `as_of` drives both the vector cut and the profile read; no later data leaks into an earlier match.
- Feature names match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; synthetic specs use the `match.` namespace, `source=CANDIDATE`, `requires_consent=False`.
- Commit style: `feat(s51): …` / `test(s51): …` / `docs(s51): …`. **No Co-Authored-By trailer.**

**Naming note:** the contract for skill explanation is `SkillMatchDetail` (NOT `SkillMatch`) — `app/candidates/normalize/skills.py` already exports a `SkillMatch` NamedTuple; the different name avoids a collision.

---

### Task 1: Config knobs (`match_*`)

**Files:**
- Modify: `app/core/config.py` (after the `search_default_limit` block, ~line 231)
- Modify: `config.yaml` (after `search_default_limit`, ~line 155)
- Test: `tests/test_config_match.py`

**Interfaces:**
- Produces: `Settings.match_default_limit:int`, `match_skill_weight:float`, `match_years_weight:float`, `match_degree_weight:float`, `match_notice_weight:float`, `match_location_weight:float`, `match_nice_to_have_fraction:float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_match.py
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def test_match_knob_defaults():
    s = _settings()
    assert s.match_default_limit == 25
    assert s.match_skill_weight == 3.0
    assert s.match_years_weight == 1.0
    assert s.match_degree_weight == 1.0
    assert s.match_notice_weight == 1.0
    assert s.match_location_weight == 1.0
    assert s.match_nice_to_have_fraction == 0.3


def test_match_nice_fraction_bounded():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openrouter_api_key="", match_nice_to_have_fraction=1.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_match.py -v`
Expected: FAIL (`AttributeError`/no such field `match_default_limit`).

- [ ] **Step 3: Add the knobs to `Settings`**

In `app/core/config.py`, immediately after the `search_default_limit` field:

```python
    # --- Demand side (PI-5, S5.1): job requisition + role-conditioned matching -
    # Advisory role-match ranking over the S4.2 pool. Weights are the default
    # RankingTerm weights; a requisition may override any of them. skill coverage
    # is the dominant term. match never auto-rejects.
    match_default_limit: int = Field(default=25, ge=1)
    match_skill_weight: float = Field(default=3.0, gt=0.0)
    match_years_weight: float = Field(default=1.0, gt=0.0)
    match_degree_weight: float = Field(default=1.0, gt=0.0)
    match_notice_weight: float = Field(default=1.0, gt=0.0)
    match_location_weight: float = Field(default=1.0, gt=0.0)
    match_nice_to_have_fraction: float = Field(default=0.3, ge=0.0, le=1.0)
```

In `config.yaml`, after the `search_default_limit` line:

```yaml

# --- Demand side (PI-5) - S5.1 job requisition + role-conditioned matching -----
match_default_limit: 25          # default shortlist size for POST /jobs/{id}/match
match_skill_weight: 3.0          # dominant term: job-relative skill coverage
match_years_weight: 1.0          # candidate.years_experience (higher better)
match_degree_weight: 1.0         # candidate.highest_degree_level (higher better)
match_notice_weight: 1.0         # candidate.notice_period_days (lower better)
match_location_weight: 1.0       # match.location_fit (candidate city tier in target)
match_nice_to_have_fraction: 0.3 # nice-to-have share of skill coverage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_match.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config.yaml tests/test_config_match.py
git commit -m "feat(s51): match_* config knobs (weights + shortlist limit)"
```

---

### Task 2: Contracts — `app/matching/schema.py`

**Files:**
- Create: `app/matching/__init__.py` (empty)
- Create: `app/matching/schema.py`
- Test: `tests/test_matching_schema.py`

**Interfaces:**
- Consumes: `Contribution` from `app.features.ranking_schema`.
- Produces: `RequisitionStatus`, `CompBand`, `MatchWeights`, `JobRequisitionInput`, `JobRequisition`, `SkillMatchDetail`, `MatchedCandidate`, `MatchResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matching_schema.py
import pytest
from pydantic import ValidationError

from app.matching.schema import (
    CompBand, JobRequisitionInput, MatchWeights, RequisitionStatus,
)


def test_requisition_requires_at_least_one_skill():
    with pytest.raises(ValidationError):
        JobRequisitionInput(title="Backend Engineer")


def test_requisition_ok_with_must_have():
    r = JobRequisitionInput(title="BE", must_have_skills=("python", "django"))
    assert r.status is RequisitionStatus.OPEN
    assert r.remote is False


def test_bad_degree_level_rejected():
    with pytest.raises(ValidationError):
        JobRequisitionInput(title="BE", must_have_skills=("python",), min_degree_level="phd")


def test_bad_location_tier_rejected():
    with pytest.raises(ValidationError):
        JobRequisitionInput(title="BE", must_have_skills=("python",), location_tiers=("village",))


def test_compband_bounds():
    with pytest.raises(ValidationError):
        CompBand(ctc_min=30.0, ctc_max=10.0)
    assert CompBand(ctc_min=10.0, ctc_max=30.0).currency == "INR"


def test_weights_must_be_positive():
    with pytest.raises(ValidationError):
        MatchWeights(skill_coverage=0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matching_schema.py -v`
Expected: FAIL (`ModuleNotFoundError: app.matching.schema`).

- [ ] **Step 3: Write the contracts**

```python
# app/matching/schema.py
"""Demand-side matching contracts (PI-5 / S5.1).

Pure, serializable request/result models + enums. No I/O, no callables. The
engine lives in match.py. A JobRequisition is org-owned; matching is advisory —
it narrows and orders, never auto-rejects.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.features.ranking_schema import Contribution

_LOC_TIERS = ("metro", "tier_2")
_DEGREE_LEVELS = ("none", "diploma", "bachelor", "master", "doctorate")


class RequisitionStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class CompBand(BaseModel):
    """Advisory compensation band. Stored on the requisition; NOT a matching
    term in S5.1 (comp intelligence is S5.2)."""

    currency: str = "INR"
    ctc_min: Optional[float] = Field(default=None, ge=0.0)
    ctc_max: Optional[float] = Field(default=None, ge=0.0)
    variable_max: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _bounds(self) -> "CompBand":
        if (
            self.ctc_min is not None
            and self.ctc_max is not None
            and self.ctc_max < self.ctc_min
        ):
            raise ValueError("ctc_max must be >= ctc_min")
        return self


class MatchWeights(BaseModel):
    """Optional per-term weight overrides; each falls back to its match_* default."""

    skill_coverage: Optional[float] = Field(default=None, gt=0.0)
    years: Optional[float] = Field(default=None, gt=0.0)
    degree: Optional[float] = Field(default=None, gt=0.0)
    notice: Optional[float] = Field(default=None, gt=0.0)
    location: Optional[float] = Field(default=None, gt=0.0)


class JobRequisitionInput(BaseModel):
    """Writable requisition fields (API create/replace payload). Skills are
    free-text here; the store normalizes them to canonical taxonomy keys."""

    title: str
    status: RequisitionStatus = RequisitionStatus.OPEN
    must_have_skills: tuple[str, ...] = ()
    nice_to_have_skills: tuple[str, ...] = ()
    min_years_experience: Optional[float] = Field(default=None, ge=0.0)
    min_degree_level: Optional[str] = None
    max_notice_days: Optional[int] = Field(default=None, ge=0)
    location_tiers: Optional[tuple[str, ...]] = None
    remote: bool = False
    min_skill_coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    comp_band: Optional[CompBand] = None
    weights: Optional[MatchWeights] = None

    @model_validator(mode="after")
    def _validate(self) -> "JobRequisitionInput":
        if not self.must_have_skills and not self.nice_to_have_skills:
            raise ValueError("requisition needs at least one must-have or nice-to-have skill")
        if self.min_degree_level is not None and self.min_degree_level not in _DEGREE_LEVELS:
            raise ValueError(f"min_degree_level must be one of {_DEGREE_LEVELS}")
        if self.location_tiers is not None:
            for t in self.location_tiers:
                if t not in _LOC_TIERS:
                    raise ValueError(f"location tier must be in {_LOC_TIERS}: {t!r}")
        return self


class JobRequisition(JobRequisitionInput):
    """A stored requisition (skills are canonical). Server-owned id/org/timestamps."""

    id: str
    org_id: str
    created_at: datetime
    updated_at: datetime


class SkillMatchDetail(BaseModel):
    """Per-candidate skill explanation for one requisition."""

    matched: tuple[str, ...] = ()
    missing_must_have: tuple[str, ...] = ()
    matched_nice_to_have: tuple[str, ...] = ()
    coverage: float  # [0,1], the value fed to the match.skill_coverage term


class MatchedCandidate(BaseModel):
    candidate_id: str
    score: float          # composite [0,1]
    coverage: float       # share of ranking weight that had data (S4.3 semantics)
    skill: SkillMatchDetail
    contributions: tuple[Contribution, ...] = ()
    missing: tuple[str, ...] = ()  # ranking terms with no value for this candidate


class MatchResult(BaseModel):
    advisory: bool = True
    requisition_id: str
    as_of: Optional[datetime] = None
    view_name: str
    view_version: int
    pool_size: int
    filtered_size: int
    ranked: tuple[MatchedCandidate, ...] = ()
```

Also create `app/matching/__init__.py` as an empty file.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matching_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/matching/__init__.py app/matching/schema.py tests/test_matching_schema.py
git commit -m "feat(s51): job requisition + match-result contracts"
```

---

### Task 3: Pure engine A — skill coverage + location fit + synthetic specs

**Files:**
- Create: `app/matching/match.py`
- Test: `tests/test_matching_engine.py`

**Interfaces:**
- Consumes: `Settings` (`match_nice_to_have_fraction`), `JobRequisitionInput` fields, `CandidateProfile`, `FeatureSpec`/`FeatureDType`/`FeatureSource`.
- Produces: constants `SKILL_COVERAGE="match.skill_coverage"`, `LOCATION_FIT="match.location_fit"`; `_SYNTHETIC_SPECS: dict[str, FeatureSpec]`; `canonical_skills(profile)->set[str]`; `skill_coverage(req, have, settings)->SkillMatchDetail`; `location_fit(req, tier)->float|None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matching_engine.py
from app.candidates.schema import CandidateProfile, ContactInfo, SkillItem
from app.core.config import Settings
from app.matching import match as M
from app.matching.schema import JobRequisitionInput


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _profile(skills=(), tier=None) -> CandidateProfile:
    return CandidateProfile(
        skills=[SkillItem(name=s, canonical=s) for s in skills],
        contact=ContactInfo(location_tier=tier),
    )


def test_synthetic_specs_are_valid_and_ranged():
    for name in (M.SKILL_COVERAGE, M.LOCATION_FIT):
        spec = M._SYNTHETIC_SPECS[name]
        assert spec.valid_range == (0.0, 1.0)
        assert spec.requires_consent is False


def test_canonical_skills_drops_uncanonical():
    p = _profile(skills=("python",))
    p.skills.append(SkillItem(name="mysterylang"))  # canonical=None
    assert M.canonical_skills(p) == {"python"}


def test_full_must_have_coverage():
    req = JobRequisitionInput(title="BE", must_have_skills=("python", "django"))
    sd = M.skill_coverage(req, {"python", "django"}, _settings())
    assert sd.coverage == 1.0
    assert sd.missing_must_have == ()


def test_partial_must_have_coverage():
    req = JobRequisitionInput(title="BE", must_have_skills=("python", "django", "aws"))
    sd = M.skill_coverage(req, {"python"}, _settings())
    assert sd.coverage == 1 / 3
    assert set(sd.missing_must_have) == {"django", "aws"}


def test_nice_to_have_blend():
    # both sets present: must_frac=1.0, nice_frac=0.5, f=0.3 -> 1.0*0.7 + 0.5*0.3
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), nice_to_have_skills=("aws", "gcp"),
    )
    sd = M.skill_coverage(req, {"python", "aws"}, _settings())
    assert abs(sd.coverage - (1.0 * 0.7 + 0.5 * 0.3)) < 1e-9
    assert sd.matched_nice_to_have == ("aws",)


def test_pure_nice_to_have_uses_nice_frac():
    req = JobRequisitionInput(title="BE", nice_to_have_skills=("aws", "gcp"))
    sd = M.skill_coverage(req, {"aws"}, _settings())
    assert sd.coverage == 0.5


def test_location_fit_variants():
    base = dict(title="BE", must_have_skills=("python",))
    metro = JobRequisitionInput(**base, location_tiers=("metro",))
    assert M.location_fit(metro, "metro") == 1.0
    assert M.location_fit(metro, "tier_2") == 0.0
    assert M.location_fit(metro, None) is None            # unknown -> drops
    remote = JobRequisitionInput(**base, location_tiers=("metro",), remote=True)
    assert M.location_fit(remote, "metro") is None        # remote -> no term
    no_tiers = JobRequisitionInput(**base)
    assert M.location_fit(no_tiers, "metro") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matching_engine.py -v`
Expected: FAIL (`ModuleNotFoundError: app.matching.match`).

- [ ] **Step 3: Write the coverage/fit engine**

```python
# app/matching/match.py
"""Pure role-conditioned matching engine (PI-5 / S5.1).

No I/O, no store, no wall clock (the app/features/ranking.py pattern). Compiles a
JobRequisition into an S4.3 RankingSpec + filters, computes two job-relative
synthetic values (skill coverage, location fit) per candidate, injects them into
a copy of each FeatureVector, and reuses ranking.score(). Advisory: a missing
value drops its term, never the candidate.
"""

from __future__ import annotations

from typing import Optional

from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec
from app.matching.schema import JobRequisitionInput, SkillMatchDetail

SKILL_COVERAGE = "match.skill_coverage"
LOCATION_FIT = "match.location_fit"

_SYNTHETIC_SPECS: dict[str, FeatureSpec] = {
    SKILL_COVERAGE: FeatureSpec(
        name=SKILL_COVERAGE, version=1, dtype=FeatureDType.NUMERIC,
        source=FeatureSource.CANDIDATE,
        description="Job-relative fraction of the requisition's skills the candidate has.",
        valid_range=(0.0, 1.0),
    ),
    LOCATION_FIT: FeatureSpec(
        name=LOCATION_FIT, version=1, dtype=FeatureDType.NUMERIC,
        source=FeatureSource.CANDIDATE,
        description="1.0 if the candidate's city tier is one of the requisition's target tiers.",
        valid_range=(0.0, 1.0),
    ),
}


def canonical_skills(profile: CandidateProfile) -> set[str]:
    """The candidate's canonical (S1.4 taxonomy) skill ids; uncanonical skills drop."""
    return {s.canonical for s in profile.skills if s.canonical}


def skill_coverage(
    req: JobRequisitionInput, have: set[str], settings: Settings
) -> SkillMatchDetail:
    must = list(req.must_have_skills)
    nice = list(req.nice_to_have_skills)
    matched_must = [s for s in must if s in have]
    matched_nice = [s for s in nice if s in have]
    missing_must = [s for s in must if s not in have]
    must_frac = (len(matched_must) / len(must)) if must else None
    nice_frac = (len(matched_nice) / len(nice)) if nice else None
    f = settings.match_nice_to_have_fraction
    if must_frac is not None and nice_frac is not None:
        cov = must_frac * (1.0 - f) + nice_frac * f
    elif must_frac is not None:
        cov = must_frac
    else:
        cov = nice_frac if nice_frac is not None else 0.0
    return SkillMatchDetail(
        matched=tuple(matched_must + matched_nice),
        missing_must_have=tuple(missing_must),
        matched_nice_to_have=tuple(matched_nice),
        coverage=cov,
    )


def location_fit(req: JobRequisitionInput, location_tier: Optional[str]) -> Optional[float]:
    """None (term drops, no penalty) when remote / no target tiers / unknown tier;
    else 1.0 in-tier, 0.0 out-of-tier."""
    if req.remote or not req.location_tiers:
        return None
    if not location_tier:
        return None
    return 1.0 if location_tier in req.location_tiers else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matching_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/matching/match.py tests/test_matching_engine.py
git commit -m "feat(s51): pure skill-coverage + location-fit + synthetic feature specs"
```

---

### Task 4: Pure engine B — `compile_ranking` + `compile_filters`

**Files:**
- Modify: `app/matching/match.py`
- Test: `tests/test_matching_compile.py`

**Interfaces:**
- Consumes: `RankingSpec`, `RankingTerm`, `SortDirection`, `FeatureFilter`, `FilterOp` from `app.features.ranking_schema`; `Settings` match weights.
- Produces: `compile_ranking(req, settings)->RankingSpec`; `compile_filters(req)->list[FeatureFilter]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matching_compile.py
from app.core.config import Settings
from app.features.ranking_schema import FilterOp, SortDirection
from app.matching import match as M
from app.matching.schema import JobRequisitionInput, MatchWeights


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def test_ranking_has_skill_term_always():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",))
    terms = {t.feature: t for t in M.compile_ranking(req, _settings()).terms}
    assert M.SKILL_COVERAGE in terms
    assert terms[M.SKILL_COVERAGE].weight == 3.0  # match_skill_weight default
    # no other criteria set -> only the skill term
    assert set(terms) == {M.SKILL_COVERAGE}


def test_ranking_includes_set_scalar_terms_with_correct_direction():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",),
        min_years_experience=3.0, min_degree_level="bachelor",
        max_notice_days=30, location_tiers=("metro",),
    )
    terms = {t.feature: t for t in M.compile_ranking(req, _settings()).terms}
    assert terms["candidate.years_experience"].direction is SortDirection.HIGHER_BETTER
    assert terms["candidate.highest_degree_level"].direction is SortDirection.HIGHER_BETTER
    assert terms["candidate.notice_period_days"].direction is SortDirection.LOWER_BETTER
    assert M.LOCATION_FIT in terms


def test_remote_drops_location_term():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), location_tiers=("metro",), remote=True,
    )
    terms = {t.feature for t in M.compile_ranking(req, _settings()).terms}
    assert M.LOCATION_FIT not in terms


def test_weight_overrides_beat_defaults():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), min_years_experience=1.0,
        weights=MatchWeights(skill_coverage=5.0, years=2.0),
    )
    terms = {t.feature: t for t in M.compile_ranking(req, _settings()).terms}
    assert terms[M.SKILL_COVERAGE].weight == 5.0
    assert terms["candidate.years_experience"].weight == 2.0


def test_min_skill_coverage_becomes_one_filter():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",), min_skill_coverage=0.5)
    filters = M.compile_filters(req)
    assert len(filters) == 1
    assert filters[0].feature == M.SKILL_COVERAGE
    assert filters[0].op is FilterOp.GTE
    assert filters[0].value == 0.5


def test_no_filter_when_no_floor():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",))
    assert M.compile_filters(req) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matching_compile.py -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'compile_ranking'`).

- [ ] **Step 3: Add compile functions to `app/matching/match.py`**

Add these imports at the top of `match.py` (extend the existing import block):

```python
from app.features.ranking_schema import (
    FeatureFilter, FilterOp, RankingSpec, RankingTerm, SortDirection,
)
```

Append to `match.py`:

```python
def _weight(override: Optional[float], default: float) -> float:
    return override if override is not None else default


def compile_ranking(req: JobRequisitionInput, settings: Settings) -> RankingSpec:
    """Requisition -> RankingSpec of SOFT terms. skill_coverage is always present;
    each scalar term appears only when its requisition field is set. The threshold
    VALUE is not a cutoff here — it selects the dimension; scoring is monotonic."""
    w = req.weights
    terms: list[RankingTerm] = [
        RankingTerm(
            feature=SKILL_COVERAGE,
            weight=_weight(w.skill_coverage if w else None, settings.match_skill_weight),
            direction=SortDirection.HIGHER_BETTER,
        )
    ]
    if req.min_years_experience is not None:
        terms.append(RankingTerm(
            feature="candidate.years_experience",
            weight=_weight(w.years if w else None, settings.match_years_weight),
            direction=SortDirection.HIGHER_BETTER,
        ))
    if req.min_degree_level is not None:
        terms.append(RankingTerm(
            feature="candidate.highest_degree_level",
            weight=_weight(w.degree if w else None, settings.match_degree_weight),
            direction=SortDirection.HIGHER_BETTER,
        ))
    if req.max_notice_days is not None:
        terms.append(RankingTerm(
            feature="candidate.notice_period_days",
            weight=_weight(w.notice if w else None, settings.match_notice_weight),
            direction=SortDirection.LOWER_BETTER,
        ))
    if req.location_tiers and not req.remote:
        terms.append(RankingTerm(
            feature=LOCATION_FIT,
            weight=_weight(w.location if w else None, settings.match_location_weight),
            direction=SortDirection.HIGHER_BETTER,
        ))
    return RankingSpec(terms=tuple(terms))


def compile_filters(req: JobRequisitionInput) -> list[FeatureFilter]:
    """The only opt-in hard gate: a min_skill_coverage floor on the synthetic term."""
    if req.min_skill_coverage is not None:
        return [FeatureFilter(
            feature=SKILL_COVERAGE, op=FilterOp.GTE, value=req.min_skill_coverage,
        )]
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matching_compile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/matching/match.py tests/test_matching_compile.py
git commit -m "feat(s51): compile requisition to RankingSpec + opt-in coverage filter"
```

---

### Task 5: Pure engine C — `match` (inject + reuse `score`)

**Files:**
- Modify: `app/matching/match.py`
- Test: `tests/test_matching_match.py`

**Interfaces:**
- Consumes: `apply_filters`, `score` from `app.features.ranking`; `FeatureVector` from `app.features.schema`.
- Produces: `match(req, vectors, profiles_by_candidate, specs_by_name, settings)->list[MatchedCandidate]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matching_match.py
from datetime import datetime, timezone

from app.candidates.schema import CandidateProfile, ContactInfo, SkillItem
from app.core.config import Settings
from app.features.schema import FeatureVector
from app.matching import match as M
from app.matching.schema import JobRequisitionInput


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _vec(cid: str, values: dict) -> FeatureVector:
    return FeatureVector(
        candidate_id=cid, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        view_name="core_v1", view_version=1, values=values,
    )


def _profile(skills=(), tier=None) -> CandidateProfile:
    return CandidateProfile(
        skills=[SkillItem(name=s, canonical=s) for s in skills],
        contact=ContactInfo(location_tier=tier),
    )


def test_full_skill_candidate_outranks_partial():
    req = JobRequisitionInput(title="BE", must_have_skills=("python", "django"))
    vectors = [_vec("a", {}), _vec("b", {})]
    profiles = {"a": _profile(("python", "django")), "b": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, {}, _settings())
    assert [m.candidate_id for m in ranked] == ["a", "b"]
    assert ranked[0].skill.coverage == 1.0
    assert ranked[1].skill.coverage == 0.5


def test_missing_scalar_feature_drops_term_not_candidate():
    # requisition ranks on skills + years; candidate b has no years feature at all.
    from app.features import get_feature_registry
    reg = get_feature_registry()
    specs = {"candidate.years_experience": reg.get("candidate.years_experience").spec}
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), min_years_experience=2.0,
    )
    vectors = [_vec("a", {"candidate.years_experience": 8.0}), _vec("b", {})]
    profiles = {"a": _profile(("python",)), "b": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, specs, _settings())
    ids = {m.candidate_id for m in ranked}
    assert ids == {"a", "b"}  # b NOT dropped
    b = next(m for m in ranked if m.candidate_id == "b")
    assert "candidate.years_experience" in b.missing
    assert b.coverage < 1.0  # its years term had no data


def test_min_skill_coverage_gate_drops_below_floor():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python", "django"), min_skill_coverage=0.75,
    )
    vectors = [_vec("a", {}), _vec("b", {})]
    profiles = {"a": _profile(("python", "django")), "b": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, {}, _settings())
    assert [m.candidate_id for m in ranked] == ["a"]  # b (0.5) gated out


def test_deterministic_tie_break_by_candidate_id():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",))
    vectors = [_vec("z", {}), _vec("a", {})]
    profiles = {"z": _profile(("python",)), "a": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, {}, _settings())
    assert [m.candidate_id for m in ranked] == ["a", "z"]  # equal score -> id asc
```

Note: `get_feature_registry()` (from `app.features`) returns the populated default registry (it imports the seed catalog on first call), so `candidate.years_experience` resolves.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matching_match.py -v`
Expected: FAIL (`AttributeError: ... 'match'`). If the registry import name is wrong, fix it to `from app.features import get_feature_registry` first, then re-run.

- [ ] **Step 3: Add `match` to `app/matching/match.py`**

Extend the imports:

```python
from app.features.ranking import apply_filters, score
from app.features.schema import FeatureVector
from app.matching.schema import MatchedCandidate
```

Append:

```python
def match(
    req: JobRequisitionInput,
    vectors: list[FeatureVector],
    profiles_by_candidate: dict[str, CandidateProfile],
    specs_by_name: dict[str, FeatureSpec],
    settings: Settings,
) -> list[MatchedCandidate]:
    """Compute job-relative synthetic values, inject them into a copy of each
    vector, apply the opt-in filter, and rank with the S4.3 engine."""
    specs = {**specs_by_name, **_SYNTHETIC_SPECS}
    skill_by_cand: dict[str, SkillMatchDetail] = {}
    augmented: list[FeatureVector] = []
    for v in vectors:
        profile = profiles_by_candidate.get(v.candidate_id)
        if profile is not None:
            detail = skill_coverage(req, canonical_skills(profile), settings)
            cov_value: Optional[float] = detail.coverage
            loc = location_fit(req, profile.contact.location_tier)
        else:
            # No point-in-time profile: skill/location unknown -> terms drop (no penalty).
            detail = SkillMatchDetail(
                coverage=0.0, missing_must_have=tuple(req.must_have_skills)
            )
            cov_value = None
            loc = None
        skill_by_cand[v.candidate_id] = detail
        augmented.append(v.model_copy(update={"values": {
            **v.values, SKILL_COVERAGE: cov_value, LOCATION_FIT: loc,
        }}))
    filtered = apply_filters(augmented, compile_filters(req), specs)
    ranked = score(filtered, compile_ranking(req, settings), specs)
    return [
        MatchedCandidate(
            candidate_id=rc.candidate_id,
            score=rc.score,
            coverage=rc.coverage,
            skill=skill_by_cand[rc.candidate_id],
            contributions=rc.contributions,
            missing=rc.missing,
        )
        for rc in ranked
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matching_match.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/matching/match.py tests/test_matching_match.py
git commit -m "feat(s51): match orchestration (inject synthetic values, reuse ranking.score)"
```

---

### Task 6: ORM model + migration `0008` + drift guard

**Files:**
- Create: `app/matching/models.py`
- Create: `alembic/versions/0008_job_requisitions.py`
- Modify: `tests/test_migrations.py`
- Modify: `tests/conftest.py` (import `app.matching.models` for `Base.metadata`)
- Test: `tests/test_migrations.py` (extended)

**Interfaces:**
- Produces: `JobRequisitionRow` (table `job_requisitions`).

- [ ] **Step 1: Write the failing test**

In `tests/test_migrations.py`, add a matching-tables tuple and extend the three checks:

```python
# add near FEATURE_TABLES
MATCHING_TABLES = ("job_requisitions",)  # S5.1
```

Add an import at the top (with the other `# noqa: F401` model imports):

```python
import app.matching.models  # noqa: F401 — populate Base.metadata
```

Extend `test_upgrade_head_creates_candidate_tables` with:

```python
    assert "job_requisitions" in names  # S5.1 migration 0008
```

Change the two loops in `test_migrated_indexes_match_orm` and
`test_migrated_fks_and_nullability_match_orm` from
`LEDGER_TABLES + FEATURE_TABLES` to `LEDGER_TABLES + FEATURE_TABLES + MATCHING_TABLES`.

Also add the model import to `tests/conftest.py` beside the existing ones:

```python
import app.matching.models  # noqa: F401 — populate Base.metadata with matching tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migrations.py -v`
Expected: FAIL (`ModuleNotFoundError: app.matching.models`, or drift: `add_table job_requisitions` once the model exists but migration doesn't).

- [ ] **Step 3: Write the ORM model**

```python
# app/matching/models.py
"""ORM row for job requisitions (S5.1). Postgres-shaped on SQLite.

Org-owned demand-side object: CASCADEs on its organization, and is NOT
candidate-linked, so DPDP candidate erasure never touches it. Match disclosure
is audited in the shared audit_log (candidate-linked, CASCADE) — not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRequisitionRow(Base):
    """One role an organization is hiring for."""

    __tablename__ = "job_requisitions"
    __table_args__ = (
        Index("ix_job_requisitions_org_id", "org_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=False
    )
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    must_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_to_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    min_years_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_degree_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    max_notice_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location_tiers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    min_skill_coverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    comp_band: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
```

Note: `Index(...)` in `__table_args__` declares the org_id index (mirrors the migration); keep `index=False` on the column so it is not declared twice.

- [ ] **Step 4: Write the migration**

```python
# alembic/versions/0008_job_requisitions.py
"""job requisitions: org-owned demand-side matching table (S5.1)

Revision ID: 0008_job_requisitions
Revises: 0007_ml_feature_vectors
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0008_job_requisitions"
down_revision = "0007_ml_feature_vectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_requisitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id", sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("must_have_skills", sa.JSON(), nullable=False),
        sa.Column("nice_to_have_skills", sa.JSON(), nullable=False),
        sa.Column("min_years_experience", sa.Float(), nullable=True),
        sa.Column("min_degree_level", sa.String(length=16), nullable=True),
        sa.Column("max_notice_days", sa.Integer(), nullable=True),
        sa.Column("location_tiers", sa.JSON(), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=False),
        sa.Column("min_skill_coverage", sa.Float(), nullable=True),
        sa.Column("comp_band", sa.JSON(), nullable=True),
        sa.Column("weights", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_requisitions_org_id", "job_requisitions", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_job_requisitions_org_id", table_name="job_requisitions")
    op.drop_table("job_requisitions")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_migrations.py -v`
Expected: PASS (table present, drift empty, index + FK-ondelete + nullability match).

- [ ] **Step 6: Commit**

```bash
git add app/matching/models.py alembic/versions/0008_job_requisitions.py tests/test_migrations.py tests/conftest.py
git commit -m "feat(s51): job_requisitions table + migration 0008 (org-owned, CASCADE)"
```

---

### Task 7: `JobStore` CRUD + `Services.jobs` wiring

**Files:**
- Create: `app/matching/store.py`
- Modify: `app/services/__init__.py`
- Modify: `tests/conftest.py` (`make_services` builds `jobs`)
- Test: `tests/test_job_store.py`

**Interfaces:**
- Consumes: `normalize_skill` from `app.candidates.normalize.skills`, `norm_key` from `app.candidates.normalize.text`, `AuditLogRow`/`OrganizationRow` from `app.ledger.models`, `CandidateStore`, `FeatureStore`.
- Produces: `JobStore(session_factory, *, candidate_store, feature_store, settings)` with `create_requisition`, `get_requisition`, `list_requisitions`, `update_requisition`; `build_job_store(settings)`; `Services.jobs`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_job_store.py
import pytest

from app.matching.store import JobStore
from app.matching.schema import JobRequisitionInput, RequisitionStatus
from tests.conftest import make_candidate_store
from app.ledger.store import LedgerStore
from app.features.store import FeatureStore
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _wire():
    cands = make_candidate_store()
    sf = cands._session_factory
    settings = _settings()
    ledger = LedgerStore(sf, settings=settings)
    features = FeatureStore(sf)
    jobs = JobStore(sf, candidate_store=cands, feature_store=features, settings=settings)
    return cands, ledger, jobs


def test_create_normalizes_skills_to_canonical():
    _, ledger, jobs = _wire()
    org = ledger.create_organization("Acme")
    req = jobs.create_requisition(org.id, JobRequisitionInput(
        title="BE", must_have_skills=("React.js", "Postgres"),
    ))
    assert set(req.must_have_skills) == {"react", "postgresql"}
    assert req.org_id == org.id
    assert req.status is RequisitionStatus.OPEN


def test_get_and_list_are_org_scoped():
    _, ledger, jobs = _wire()
    a = ledger.create_organization("A")
    b = ledger.create_organization("B")
    req = jobs.create_requisition(a.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    assert jobs.get_requisition(a.id, req.id).id == req.id
    assert jobs.get_requisition(b.id, req.id) is None          # cross-org invisible
    assert [r.id for r in jobs.list_requisitions(a.id)] == [req.id]
    assert jobs.list_requisitions(b.id) == []


def test_update_status_and_replace_spec():
    _, ledger, jobs = _wire()
    org = ledger.create_organization("A")
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    closed = jobs.update_requisition(org.id, req.id, status=RequisitionStatus.CLOSED)
    assert closed.status is RequisitionStatus.CLOSED
    replaced = jobs.update_requisition(
        org.id, req.id,
        spec=JobRequisitionInput(title="BE2", must_have_skills=("Django",)),
    )
    assert replaced.title == "BE2"
    assert set(replaced.must_have_skills) == {"django"}
    assert jobs.update_requisition("nope", req.id, status=RequisitionStatus.OPEN) is None


def test_create_is_audited_and_survives_candidate_erasure():
    cands, ledger, jobs = _wire()
    org = ledger.create_organization("A")
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    # requisition create audited (org-only, candidate_id None) — not swept by candidate erasure
    from app.candidates.schema import ExtractionResult
    saved = cands.ingest(
        ExtractionResult(profile=_minimal_profile(), method="heuristic"), resume_text="x"
    )
    cands.delete_candidate(saved.candidate_id)
    assert jobs.get_requisition(org.id, req.id) is not None  # survives


def _minimal_profile():
    from app.candidates.schema import CandidateProfile, ContactInfo, ExtractedStr
    return CandidateProfile(
        full_name=ExtractedStr(value="P"),
        contact=ContactInfo(email=ExtractedStr(value="p@x.io")),
    )
```

Note: `CandidateStore.ingest(result: ExtractionResult, resume_text: str) -> IngestOutcome` (with `.candidate_id`), so ingestion wraps the profile in an `ExtractionResult(method="heuristic")`. The assertion that matters is that the requisition survives candidate erasure.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_job_store.py -v`
Expected: FAIL (`ModuleNotFoundError: app.matching.store`).

- [ ] **Step 3: Write `JobStore` (CRUD only; `run_match` is Task 8)**

```python
# app/matching/store.py
"""Job requisition store + role-conditioned match orchestrator (S5.1).

Shares the candidates/ledger session factory (organizations, candidates,
ml_feature_vectors, audit_log are one DB). CRUD is org-scoped: an org only sees
its own requisitions. run_match (Task 8) does the I/O the pure engine cannot and
audits every surfaced candidate as a match.surface disclosure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.candidates.normalize.skills import normalize_skill
from app.candidates.normalize.text import norm_key
from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.features.store import FeatureStore, build_feature_store
from app.ledger.consent import as_utc
from app.ledger.models import AuditLogRow, OrganizationRow
from app.matching.models import JobRequisitionRow
from app.matching.schema import (
    CompBand, JobRequisition, JobRequisitionInput, MatchWeights, RequisitionStatus,
)


def _canonicalize(skills: tuple[str, ...]) -> list[str]:
    """Map free-text skills to canonical taxonomy ids (unknown -> norm_key, so the
    ask is recorded verbatim-normalized even if no candidate can match it).
    De-duplicates, preserving first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for s in skills:
        m = normalize_skill(s)
        key = m.canonical if m else norm_key(s)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _to_contract(row: JobRequisitionRow) -> JobRequisition:
    return JobRequisition(
        id=row.id,
        org_id=row.org_id,
        title=row.title,
        status=RequisitionStatus(row.status),
        must_have_skills=tuple(row.must_have_skills or ()),
        nice_to_have_skills=tuple(row.nice_to_have_skills or ()),
        min_years_experience=row.min_years_experience,
        min_degree_level=row.min_degree_level,
        max_notice_days=row.max_notice_days,
        location_tiers=tuple(row.location_tiers) if row.location_tiers else None,
        remote=row.remote,
        min_skill_coverage=row.min_skill_coverage,
        comp_band=CompBand.model_validate(row.comp_band) if row.comp_band else None,
        weights=MatchWeights.model_validate(row.weights) if row.weights else None,
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
    )


def _apply_spec(row: JobRequisitionRow, spec: JobRequisitionInput) -> None:
    row.title = spec.title
    row.status = spec.status.value
    row.must_have_skills = _canonicalize(spec.must_have_skills)
    row.nice_to_have_skills = _canonicalize(spec.nice_to_have_skills)
    row.min_years_experience = spec.min_years_experience
    row.min_degree_level = spec.min_degree_level
    row.max_notice_days = spec.max_notice_days
    row.location_tiers = list(spec.location_tiers) if spec.location_tiers else None
    row.remote = spec.remote
    row.min_skill_coverage = spec.min_skill_coverage
    row.comp_band = spec.comp_band.model_dump() if spec.comp_band else None
    row.weights = spec.weights.model_dump(exclude_none=True) if spec.weights else None


class JobStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        candidate_store: Optional[CandidateStore] = None,
        feature_store: Optional[FeatureStore] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._candidates = candidate_store
        self._features = feature_store
        self._settings = settings or get_settings()

    def create_requisition(
        self, org_id: str, spec: JobRequisitionInput
    ) -> JobRequisition:
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            row = JobRequisitionRow(org_id=org_id)
            _apply_spec(row, spec)
            session.add(row)
            session.flush()
            session.add(AuditLogRow(
                actor_type="org", actor_id=org_id, action="requisition.create",
                entity_type="requisition", entity_id=row.id, candidate_id=None,
                details={"title": spec.title},
            ))
            session.commit()
            return _to_contract(row)

    def get_requisition(self, org_id: str, req_id: str) -> Optional[JobRequisition]:
        with self._session_factory() as session:
            row = session.get(JobRequisitionRow, req_id)
            if row is None or row.org_id != org_id:
                return None
            return _to_contract(row)

    def list_requisitions(self, org_id: str) -> list[JobRequisition]:
        with self._session_factory() as session:
            rows = session.execute(
                select(JobRequisitionRow)
                .where(JobRequisitionRow.org_id == org_id)
                .order_by(JobRequisitionRow.created_at, JobRequisitionRow.id)
            ).scalars().all()
            return [_to_contract(r) for r in rows]

    def update_requisition(
        self,
        org_id: str,
        req_id: str,
        *,
        status: Optional[RequisitionStatus] = None,
        spec: Optional[JobRequisitionInput] = None,
    ) -> Optional[JobRequisition]:
        with self._session_factory() as session:
            row = session.get(JobRequisitionRow, req_id)
            if row is None or row.org_id != org_id:
                return None
            if spec is not None:
                _apply_spec(row, spec)
            if status is not None:
                row.status = status.value
            session.add(AuditLogRow(
                actor_type="org", actor_id=org_id, action="requisition.update",
                entity_type="requisition", entity_id=row.id, candidate_id=None,
                details={"status": row.status},
            ))
            session.commit()
            return _to_contract(row)


def build_job_store(settings: Optional[Settings] = None) -> JobStore:
    """Store on the shared candidates DB URL. Schema is Alembic's job."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    session_factory = make_session_factory(engine)
    return JobStore(
        session_factory,
        candidate_store=build_candidate_store(settings),
        feature_store=build_feature_store(settings),
        settings=settings,
    )
```

- [ ] **Step 4: Wire `Services.jobs`**

In `app/services/__init__.py`, extend the `TYPE_CHECKING` block and dataclass:

```python
if TYPE_CHECKING:  # avoid a features.store -> features.context -> services cycle
    from app.features.store import FeatureStore
    from app.matching.store import JobStore
```

Add the field to `Services` (after `features`):

```python
    jobs: JobStore
```

In `build_default_services`, add the function-local import and the field:

```python
    from app.features.store import build_feature_store
    from app.matching.store import build_job_store
```

```python
        features=build_feature_store(settings),
        jobs=build_job_store(settings),
    )
```

In `tests/conftest.py`, extend `make_services`:

```python
def make_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    github: FakeGitHub | None = None,
    flywheel: InMemoryFlywheel | None = None,
    candidates: CandidateStore | None = None,
    ledger: LedgerStore | None = None,
    features: FeatureStore | None = None,
    jobs=None,
) -> Services:
    candidates = candidates or make_candidate_store()
    ledger = ledger or LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    features = features or FeatureStore(candidates._session_factory)
    if jobs is None:
        from app.matching.store import JobStore
        jobs = JobStore(
            candidates._session_factory,
            candidate_store=candidates, feature_store=features, settings=settings,
        )
    return Services(
        settings=settings,
        llm=llm or NullLLM(settings),
        vectorstore=InMemoryVectorStore(),
        github=github or FakeGitHub(),
        flywheel=flywheel or InMemoryFlywheel(),
        report_store=InMemoryReportStore(),
        candidates=candidates,
        ledger=ledger,
        features=features,
        jobs=jobs,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_job_store.py -v`
Expected: PASS. Then `pytest -q` to confirm `Services`/conftest changes didn't break the suite.

- [ ] **Step 6: Commit**

```bash
git add app/matching/store.py app/services/__init__.py tests/conftest.py tests/test_job_store.py
git commit -m "feat(s51): JobStore CRUD (canonical skills, org-scoped, audited) + Services.jobs"
```

---

### Task 8: `JobStore.run_match` — orchestrate + disclosure audit + DPDP

**Files:**
- Modify: `app/matching/store.py`
- Test: `tests/test_job_store_match.py`

**Interfaces:**
- Consumes: `get_feature_registry`, `default_view` from `app.features`; `app.matching.match.match`; `FeatureStore.vectors_for_view`/`latest_as_of`; `CandidateStore.profile_as_of`.
- Produces: `JobStore.run_match(org_id, req_id, *, as_of=None, limit=None) -> Optional[MatchResult]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_job_store_match.py
from datetime import datetime, timezone

from app.core.config import Settings
from app.features.materialize import materialize_candidate
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.matching.store import JobStore
from app.matching.schema import JobRequisitionInput
from tests.conftest import make_candidate_store, set_extraction_created_at

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _profile(name, email, skills, tier=None):
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, SkillItem,
    )
    return CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(email=ExtractedStr(value=email), location_tier=tier),
        skills=[SkillItem(name=s, canonical=s) for s in skills],
    )


def _wire():
    cands = make_candidate_store()
    sf = cands._session_factory
    s = _settings()
    ledger = LedgerStore(sf, settings=s)
    features = FeatureStore(sf)
    jobs = JobStore(sf, candidate_store=cands, feature_store=features, settings=s)
    return cands, ledger, features, jobs, s


def _seed_candidate(cands, features, ledger, name, email, skills, tier=None):
    from app.candidates.schema import ExtractionResult
    from app.features import default_view, get_feature_registry
    from app.services.report_store import InMemoryReportStore
    saved = cands.ingest(
        ExtractionResult(profile=_profile(name, email, skills, tier), method="heuristic"),
        resume_text=email,
    )
    cid = saved.candidate_id
    set_extraction_created_at(cands, cid, AS_OF.replace(tzinfo=None))
    registry = get_feature_registry()
    mv = materialize_candidate(
        cid, view=default_view(registry), registry=registry, as_of=AS_OF,
        candidate_store=cands, report_store=InMemoryReportStore(), ledger_store=ledger,
    )
    features.upsert_vector(mv)
    return cid


def test_run_match_ranks_by_skill_coverage_and_audits_disclosure():
    cands, ledger, features, jobs, s = _wire()
    org = ledger.create_organization("Acme")
    strong = _seed_candidate(cands, features, ledger, "Strong", "strong@x.io", ("python", "django"))
    weak = _seed_candidate(cands, features, ledger, "Weak", "weak@x.io", ("python",))
    req = jobs.create_requisition(org.id, JobRequisitionInput(
        title="BE", must_have_skills=("python", "django"),
    ))
    result = jobs.run_match(org.id, req.id, as_of=AS_OF)
    assert result.advisory is True
    assert [m.candidate_id for m in result.ranked] == [strong, weak]
    assert result.pool_size == 2
    # each returned candidate is audited as a disclosure
    strong_audit = [a for a in ledger.audit_for_candidate(strong) if a.action == "match.surface"]
    assert len(strong_audit) == 1
    assert strong_audit[0].actor_id == org.id


def test_run_match_cross_org_returns_none():
    cands, ledger, features, jobs, s = _wire()
    a = ledger.create_organization("A")
    b = ledger.create_organization("B")
    req = jobs.create_requisition(a.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    assert jobs.run_match(b.id, req.id, as_of=AS_OF) is None


def test_run_match_empty_pool_reports_zero():
    cands, ledger, features, jobs, s = _wire()
    org = ledger.create_organization("A")
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    result = jobs.run_match(org.id, req.id, as_of=AS_OF)  # nothing materialized
    assert result.pool_size == 0
    assert result.ranked == ()


def test_dpdp_erasure_sweeps_match_surface_audit():
    cands, ledger, features, jobs, s = _wire()
    org = ledger.create_organization("A")
    cid = _seed_candidate(cands, features, ledger, "C", "c@x.io", ("python",))
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    jobs.run_match(org.id, req.id, as_of=AS_OF)
    assert [a for a in ledger.audit_for_candidate(cid) if a.action == "match.surface"]
    cands.delete_candidate(cid)
    assert ledger.audit_for_candidate(cid) == []  # candidate-linked rows CASCADE
```

Note: `materialize_candidate(cid, *, view, registry, as_of, candidate_store, report_store, ledger_store) -> Optional[MaterializedVector]` is the confirmed signature. The seeded candidates have no consent grants, so consent-tagged (`ledger.*`/`reputation.*`) features materialize as masked null while first-party `candidate.*` features populate — exactly what matching reads. A fresh `InMemoryReportStore` gives null depth features (fine for these tests).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_job_store_match.py -v`
Expected: FAIL (`AttributeError: 'JobStore' object has no attribute 'run_match'`).

- [ ] **Step 3: Add `run_match` to `JobStore`**

Extend imports in `app/matching/store.py`:

```python
from app.features import default_view, get_feature_registry
from app.matching.match import match as run_match_engine
from app.matching.schema import MatchResult, MatchedCandidate
```

Add the method to `JobStore`:

```python
    def run_match(
        self,
        org_id: str,
        req_id: str,
        *,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Optional[MatchResult]:
        """Role-conditioned match over the materialized pool. Returns None if the
        requisition is not owned by org_id. Reads vectors + point-in-time profiles
        at one as_of, ranks with the pure engine, and audits each RETURNED
        candidate as a match.surface disclosure (candidate-linked, CASCADE)."""
        req = self.get_requisition(org_id, req_id)
        if req is None:
            return None

        registry = get_feature_registry()
        view_name = self._settings.feat_default_view
        view_version = default_view(registry, settings=self._settings).version
        limit = limit or self._settings.match_default_limit

        cut = as_of or self._features.latest_as_of(view_name, view_version)
        pool = (
            self._features.vectors_for_view(view_name, view_version, as_of=cut)
            if cut is not None else []
        )
        vectors = [mv.vector for mv in pool]

        # Scalar feature specs the compiled ranking references (synthetic specs are
        # merged inside the engine); resolved from the registry.
        ranking = run_match_ranking(req, self._settings)  # local import below
        scalar = {t.feature for t in ranking.terms if not t.feature.startswith("match.")}
        specs_by_name = {n: registry.get(n).spec for n in scalar}

        profiles = {}
        if cut is not None and self._candidates is not None:
            for v in vectors:
                p = self._candidates.profile_as_of(v.candidate_id, cut)
                if p is not None:
                    profiles[v.candidate_id] = p

        ranked = run_match_engine(req, vectors, profiles, specs_by_name, self._settings)
        ranked = ranked[:limit]

        # Disclosure audit: one match.surface row per RETURNED candidate.
        with self._session_factory() as session:
            for rank, mc in enumerate(ranked, start=1):
                session.add(AuditLogRow(
                    actor_type="org", actor_id=org_id, action="match.surface",
                    entity_type="requisition", entity_id=req_id,
                    candidate_id=mc.candidate_id,
                    details={"rank": rank, "score": mc.score},
                ))
            session.commit()

        return MatchResult(
            advisory=True, requisition_id=req_id, as_of=cut,
            view_name=view_name, view_version=view_version,
            pool_size=len(vectors), filtered_size=len(ranked),
            ranked=tuple(ranked),
        )
```

Add `run_match_ranking` = the engine's `compile_ranking` (import it to avoid recomputing inside the store):

```python
from app.matching.match import compile_ranking as run_match_ranking
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_job_store_match.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/matching/store.py tests/test_job_store_match.py
git commit -m "feat(s51): JobStore.run_match (pool+profile read, disclosure audit, DPDP CASCADE)"
```

---

### Task 9: HTTP endpoints — org plane

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_jobs_api.py`

**Interfaces:**
- Consumes: `require_org`, `_services`, `org_router`; `JobRequisitionInput`, `JobRequisition`, `MatchResult`, `RequisitionStatus` from `app.matching.schema`.
- Produces: `POST/GET/PATCH /jobs`, `GET /jobs/{req_id}`, `POST /jobs/{req_id}/match`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jobs_api.py
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.features.materialize import materialize_candidate
from app.main import create_app
from app.matching.schema import RequisitionStatus
from tests.conftest import make_services, set_extraction_created_at

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _profile(name, email, skills):
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, SkillItem,
    )
    return CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(email=ExtractedStr(value=email)),
        skills=[SkillItem(name=s, canonical=s) for s in skills],
    )


def _client(services):
    app = create_app(services=services)
    return TestClient(app)


def _org_key(services, name="Acme"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_create_requires_org_key(services):
    c = _client(services)
    assert c.post("/jobs", json={"title": "BE", "must_have_skills": ["python"]}).status_code == 401


def test_crud_and_match_flow(services, settings):
    _, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    c = _client(services)

    # create
    r = c.post("/jobs", headers=hdr,
               json={"title": "BE", "must_have_skills": ["React.js", "Postgres"]})
    assert r.status_code == 200
    req = r.json()
    assert set(req["must_have_skills"]) == {"react", "postgresql"}

    # get / list
    assert c.get(f"/jobs/{req['id']}", headers=hdr).status_code == 200
    assert len(c.get("/jobs", headers=hdr).json()) == 1
    assert c.get("/jobs/does-not-exist", headers=hdr).status_code == 404

    # patch (close)
    p = c.patch(f"/jobs/{req['id']}", headers=hdr, json={"status": "closed"})
    assert p.json()["status"] == RequisitionStatus.CLOSED.value

    # match with empty pool -> 422
    m0 = c.post(f"/jobs/{req['id']}/match", headers=hdr, json={"as_of": AS_OF.isoformat()})
    assert m0.status_code == 422


def test_cross_org_match_404(services):
    _, key_a = _org_key(services, "A")
    org_b = services.ledger.create_organization("B")
    key_b = services.ledger.issue_api_key(org_b.id)
    c = _client(services)
    req = c.post("/jobs", headers={"X-Org-Key": key_a},
                 json={"title": "BE", "must_have_skills": ["python"]}).json()
    r = c.post(f"/jobs/{req['id']}/match", headers={"X-Org-Key": key_b},
               json={"as_of": AS_OF.isoformat()})
    assert r.status_code == 404


def test_match_ranks_materialized_pool(services, settings):
    org_id, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    c = _client(services)
    from app.candidates.schema import ExtractionResult
    from app.features import default_view, get_feature_registry
    registry = get_feature_registry()
    for name, email, skills in [
        ("Strong", "s@x.io", ["python", "django"]),
        ("Weak", "w@x.io", ["python"]),
    ]:
        saved = services.candidates.ingest(
            ExtractionResult(profile=_profile(name, email, skills), method="heuristic"),
            resume_text=email,
        )
        set_extraction_created_at(services.candidates, saved.candidate_id, AS_OF.replace(tzinfo=None))
        mv = materialize_candidate(
            saved.candidate_id, view=default_view(registry), registry=registry, as_of=AS_OF,
            candidate_store=services.candidates, report_store=services.report_store,
            ledger_store=services.ledger,
        )
        services.features.upsert_vector(mv)
    req = c.post("/jobs", headers=hdr,
                 json={"title": "BE", "must_have_skills": ["python", "django"]}).json()
    m = c.post(f"/jobs/{req['id']}/match", headers=hdr, json={"as_of": AS_OF.isoformat()})
    assert m.status_code == 200
    body = m.json()
    assert body["advisory"] is True
    assert body["ranked"][0]["skill"]["coverage"] == 1.0
    assert body["pool_size"] == 2
```

Note: `create_app(services: Optional[Services] = None) -> FastAPI` is the confirmed test entrypoint (`app/main.py`; used across the API tests). The `materialize_candidate`/`ingest` calls above use the confirmed real signatures.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jobs_api.py -v`
Expected: FAIL (404s / no `/jobs` route).

- [ ] **Step 3: Add the endpoints to `app/api/routes.py`**

Extend the matching imports near the top:

```python
from app.matching.schema import (
    JobRequisition, JobRequisitionInput, MatchResult, RequisitionStatus,
)
```

Add near the other `org_router` endpoints (after the reputation endpoint):

```python
# ── Demand side: job requisitions + role-conditioned matching (S5.1) ─────────
# Org plane (X-Org-Key). Requisitions are org-owned; match is advisory and
# audits every surfaced candidate as a disclosure. Consent was masked at S4.2.


class JobUpdateRequest(BaseModel):
    status: Optional[RequisitionStatus] = None
    spec: Optional[JobRequisitionInput] = None


class JobMatchRequest(BaseModel):
    as_of: Optional[datetime] = None
    limit: Optional[int] = Field(default=None, ge=1)


@org_router.post("/jobs", response_model=JobRequisition)
async def create_job(
    req: JobRequisitionInput, request: Request, org_id: str = Depends(require_org)
) -> JobRequisition:
    return _services(request).jobs.create_requisition(org_id, req)


@org_router.get("/jobs", response_model=list[JobRequisition])
async def list_jobs(request: Request, org_id: str = Depends(require_org)) -> list[JobRequisition]:
    return _services(request).jobs.list_requisitions(org_id)


@org_router.get("/jobs/{req_id}", response_model=JobRequisition)
async def get_job(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> JobRequisition:
    r = _services(request).jobs.get_requisition(org_id, req_id)
    if r is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    return r


@org_router.patch("/jobs/{req_id}", response_model=JobRequisition)
async def update_job(
    req_id: str, body: JobUpdateRequest, request: Request, org_id: str = Depends(require_org)
) -> JobRequisition:
    r = _services(request).jobs.update_requisition(
        org_id, req_id, status=body.status, spec=body.spec
    )
    if r is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    return r


@org_router.post("/jobs/{req_id}/match", response_model=MatchResult)
async def match_job(
    req_id: str, body: JobMatchRequest, request: Request, org_id: str = Depends(require_org)
) -> MatchResult:
    jobs = _services(request).jobs
    try:
        result = jobs.run_match(org_id, req_id, as_of=body.as_of, limit=body.limit)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    if result.pool_size == 0:
        raise HTTPException(status_code=422, detail="no materialized candidates to match")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jobs_api.py -v`
Expected: PASS. Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_jobs_api.py
git commit -m "feat(s51): org-plane /jobs CRUD + /jobs/{id}/match endpoints"
```

---

### Task 10: Docs (`MATCHING.md`) + smoke (`scripts/smoke_s51.py`)

**Files:**
- Create: `MATCHING.md` (repo root, peer of `LEDGER.md`/`FEATURES.md`)
- Create: `scripts/smoke_s51.py`
- Modify: `docs/ROADMAP.md` (status board + Current state + session log)

**Interfaces:**
- Consumes: the running app (uvicorn) + HTTP; no new code interfaces.

- [ ] **Step 1: Write `MATCHING.md`**

Sections (mirror `FEATURES.md`'s density): purpose (demand side, S5.1); the requisition schema (fields + comp-band-is-metadata); compile rules (soft terms table + the always-on skill term + the min_* fields select-not-cutoff nuance + the one opt-in `min_skill_coverage` filter); the two synthetic features; consent/point-in-time/DPDP posture (org-owned table survives candidate erasure, `match.surface` audit CASCADEs, no new consent purpose); config knobs; and the S5.2/S5.3 seams. Keep it factual and concise.

- [ ] **Step 2: Write the smoke script**

Model it on `scripts/smoke_s43.py` (uvicorn subprocess + `httpx`/`requests` HTTP). Sequence, asserting each step and exiting non-zero on any failure:

1. Start uvicorn on a random port; wait for `/healthz`.
2. Admin-create an org, issue its `X-Org-Key`.
3. Ingest ≥3 candidates via `POST /candidates` spanning skills / experience / notice (e.g. a strong full-stack senior, a mid python-only, a junior). Capture their candidate ids from the responses.
4. Directly materialize + persist each candidate's vector at `T = now` (import `materialize_candidate` + `FeatureStore`, as `smoke_s42`/`smoke_s43` do) — capture `T` AFTER ingestion so the cut post-dates the extraction `created_at`.
5. `POST /jobs` (must-have `["python","django"]`, `min_years_experience`, `max_notice_days`).
6. `POST /jobs/{id}/match` with `{ "as_of": T }`: assert `advisory` true, the strong candidate ranks first with `skill.coverage == 1.0` and a visible notice contribution, the weak-skill candidate still appears (advisory), and `pool_size == 3`.
7. Re-`POST` with a requisition carrying `min_skill_coverage: 0.75` (create a second requisition): assert the weak candidate is gated out.
8. DPDP: `DELETE /candidates/{id}` for a ranked candidate, re-match, assert they drop from `ranked`; assert their `match.surface` audit rows are swept (query `audit_for_candidate` via the store, or a fresh match shows them absent).
9. Print `SMOKE OK` and exit 0.

Run: `python scripts/smoke_s51.py`
Expected: all checks OK, exit 0. (Runs key-less — S5.1 has no LLM; the `POST /candidates` extraction uses the heuristic floor without an API key.)

- [ ] **Step 3: Full suite green**

Run: `pytest -q`
Expected: PASS (target ~625 tests, up from 584).

- [ ] **Step 4: Update ROADMAP**

In `docs/ROADMAP.md`: flip the PI-5 board line for S5.1 to `[x]`, rewrite "Current state"/"Next action" to reflect S5.1 merged-ready and S5.2 (comp intelligence) next, and add a session-log entry summarizing what shipped (contracts, pure engine, table+migration 0008, JobStore + run_match, endpoints, MATCHING.md, smoke, test delta).

- [ ] **Step 5: Commit**

```bash
git add MATCHING.md scripts/smoke_s51.py docs/ROADMAP.md
git commit -m "docs(s51): MATCHING.md + smoke_s51 + ROADMAP (S5.1 complete)"
```

---

## Self-Review

**1. Spec coverage** (each S5.1 spec section → task):
- §4.1 contracts → Task 2. §4.2 pure engine (synthetic specs, skill/location, compile, match) → Tasks 3–5. §4.3 ORM + migration + drift → Task 6. §4.4 JobStore CRUD + run_match → Tasks 7–8. §4.5 HTTP org plane → Task 9. §5 consent/point-in-time/DPDP → enforced in Tasks 6 (org-owned survives erasure), 8 (one as_of; match.surface CASCADE). §6 config → Task 1. §7 tests → every task's tests + Task 10 smoke. §8 deliverables incl. MATCHING.md → Task 10. §9 seams → MATCHING.md (Task 10). **No gaps.**

**2. Placeholder scan:** every code step has real code; test steps have real assertions. The three "Note:" callouts (confirm `CandidateStore.ingest` return attr, `materialize_candidate` signature, `create_app`/registry accessor names) are **verification instructions against real existing code**, not deferred work — the implementer confirms the exact local name and proceeds. No "TBD"/"handle edge cases"/"similar to Task N".

**3. Type consistency:** `SkillMatchDetail` (not `SkillMatch`) used consistently. `JobRequisitionInput` (writable) vs `JobRequisition` (stored, adds id/org/timestamps) consistent across store/endpoints. `run_match` returns `Optional[MatchResult]`; endpoint maps `None→404`, `pool_size==0→422`. `compile_ranking`/`compile_filters`/`match`/`skill_coverage`/`location_fit` names match between engine tasks and the store's use (`run_match_engine`=`match`, `run_match_ranking`=`compile_ranking`). Synthetic feature names `match.skill_coverage`/`match.location_fit` consistent (constants `SKILL_COVERAGE`/`LOCATION_FIT`). `Services.jobs` added to dataclass, builder, and conftest together.

**Verified local interfaces** (confirmed against the code while writing this plan, so the test code above is exact): `CandidateStore.ingest(result: ExtractionResult, resume_text) -> IngestOutcome` (`.candidate_id`); `materialize_candidate(cid, *, view, registry, as_of, candidate_store, report_store, ledger_store)`; `get_feature_registry()` + `default_view(registry=None, *, settings=None)` from `app.features`; `create_app(services=None) -> FastAPI`; `FeatureStore.vectors_for_view/latest_as_of`, `CandidateStore.profile_as_of`, `LedgerStore.audit_for_candidate`, `AuditLogRow`/`OrganizationRow` fields — all as used above. The one item genuinely left to the implementer: adjust any incidental fixture detail (e.g. a resume-text value) that a local run reveals.
