# S5.2 — Comp Intelligence v0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an org an advisory, explainable comp band for a role — a
deterministic static prior blended with consent-gated ledger-observed offers —
plus a benchmark of a requisition's own `comp_band` against market.

**Architecture:** A new pure `app/comp/` package (contracts + static seed table +
blend engine + a thin service) consumes a new consent-gated `observed_offers`
ledger record. Observed offers live in `app/ledger/` (same consent/audit/erasure
machinery as interview records); comp is a pure consumer that reads them via
`LedgerStore`. The blend mirrors `app/ledger/reputation.py` (shrinkage toward a
prior). Two org-plane read endpoints + one submit endpoint. Advisory, no LLM.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLAlchemy + Alembic on SQLite
(Postgres-shaped), FastAPI, pytest (offline).

**Design spec:** `docs/superpowers/specs/2026-07-28-s52-comp-intelligence-design.md`.

## Global Constraints

- **Advisory only, forever.** Every comp output carries `advisory=True`; nothing
  gates, ranks, or rejects. No auto-anything.
- **No LLM.** Comp is deterministic arithmetic; no API key is ever needed.
- **TDD, fully offline.** Write the failing test first; `pytest -q` green before
  each commit. Use the `make_services`/`make_candidate_store` conftest helpers.
- **DPDP.** `observed_offers` is candidate-linked with `ondelete="CASCADE"` FKs
  (erasure sweeps it) and org `CASCADE`; `consent_id` stamped; submit is
  `ledger_write`-gated; every touch audited in the same transaction.
- **Layering.** `app/ledger/` MUST NOT import `app/comp/` (PI-3 stays below PI-5).
  Vocabulary enums live in `app/comp/schema.py`; `observed_offers` stores
  `role_family`/`seniority`/`city_tier` as plain `str`, validated at the API
  boundary (routes.py, which may import comp). `app/comp/` never imports the API
  layer; the graph never imports `app/comp/`.
- **Config.** New tunables in `config.yaml` + `app/core/config.py` as `comp_*`
  (all `DEE_*`-overridable). `config.yaml` comments MUST be ASCII (cp1252 read on
  Windows).
- **Commits:** conventional `feat(s52):` / `test(s52):` / `docs(s52):`. **Do NOT
  append a `Co-Authored-By` trailer** (user preference).
- **Migration discipline:** new table lands with migration `0009` in the SAME
  task as the ORM model (the metadata-wide drift guard fires as soon as the model
  is imported), and the drift-guard tests are extended in that task.

---

### Task 1: Config knobs (`comp_*`)

**Files:**
- Modify: `app/core/config.py` (add fields after the `match_*` block, ~line 243)
- Modify: `config.yaml` (add a `comp_*` block after the `match_*` block, ~line 164)
- Test: `tests/test_config.py` (add cases; create if absent)

**Interfaces:**
- Produces: `Settings.comp_currency_default: str`, `comp_min_observations: int`,
  `comp_recency_halflife_days: float`, `comp_prior_strength: float`,
  `comp_confidence_floor: float`, `comp_confidence_cap: float`,
  `comp_confidence_k: float`, `comp_mid_years: float`, `comp_senior_years: float`,
  `comp_lead_years: float`, `comp_benchmark_tolerance: float`,
  `comp_bands_path: str | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_comp_defaults_present():
    from app.core.config import Settings
    s = Settings()
    assert s.comp_min_observations == 5
    assert s.comp_prior_strength == 8.0
    assert s.comp_confidence_floor == 0.30
    assert s.comp_confidence_cap == 0.90
    assert (s.comp_mid_years, s.comp_senior_years, s.comp_lead_years) == (2.0, 5.0, 9.0)
    assert s.comp_benchmark_tolerance == 0.10
    assert s.comp_currency_default == "INR"
    assert s.comp_bands_path is None


def test_comp_env_override(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv("DEE_COMP_MIN_OBSERVATIONS", "3")
    assert Settings().comp_min_observations == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -k comp -v`
Expected: FAIL (`AttributeError` on `comp_min_observations`).

- [ ] **Step 3: Add the fields**

In `app/core/config.py`, immediately after `match_nice_to_have_fraction`:

```python
    # ── Comp intelligence (S5.2) ─────────────────────────────────────────────
    comp_currency_default: str = "INR"
    comp_min_observations: int = Field(default=5, ge=1)   # k-anonymity floor
    comp_recency_halflife_days: float = Field(default=365.0, gt=0.0)
    comp_prior_strength: float = Field(default=8.0, gt=0.0)   # static-prior pseudo-count
    comp_confidence_floor: float = Field(default=0.30, ge=0.0, le=1.0)
    comp_confidence_cap: float = Field(default=0.90, ge=0.0, le=1.0)
    comp_confidence_k: float = Field(default=4.0, gt=0.0)
    comp_mid_years: float = Field(default=2.0, ge=0.0)
    comp_senior_years: float = Field(default=5.0, ge=0.0)
    comp_lead_years: float = Field(default=9.0, ge=0.0)
    comp_benchmark_tolerance: float = Field(default=0.10, ge=0.0)
    comp_bands_path: str | None = None   # optional operator-supplied static table
```

In `config.yaml`, after the `match_*` block (ASCII comments only):

```yaml
# Comp intelligence (S5.2) - advisory static bands + ledger-observed offers.
comp_currency_default: INR
comp_min_observations: 5         # min observed offers before the observed blend applies
comp_recency_halflife_days: 365  # observed-offer recency half-life
comp_prior_strength: 8.0         # static-prior pseudo-count (k0)
comp_confidence_floor: 0.30      # static-only confidence (and blend floor)
comp_confidence_cap: 0.90        # confidence ceiling
comp_confidence_k: 4.0           # evidence mass where confidence gains half its range
comp_mid_years: 2.0              # seniority junior->mid threshold (years)
comp_senior_years: 5.0           # seniority mid->senior threshold
comp_lead_years: 9.0             # seniority senior->lead threshold
comp_benchmark_tolerance: 0.10   # +/- band around p50 counted as "at market"
# comp_bands_path:               # optional path to an operator static-band JSON
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -k comp -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config.yaml tests/test_config.py
git commit -m "feat(s52): comp_* config knobs (bands, blend, seniority thresholds)"
```

---

### Task 2: Comp contracts (`app/comp/schema.py`)

**Files:**
- Create: `app/comp/__init__.py` (empty)
- Create: `app/comp/schema.py`
- Test: `tests/test_comp_schema.py`

**Interfaces:**
- Consumes: `CompBand` from `app.matching.schema`.
- Produces: `SeniorityBand(StrEnum)` {junior,mid,senior,lead}; module tuples
  `ROLE_FAMILIES: tuple[str,...]`, `CITY_TIERS: tuple[str,...]`,
  `DEFAULT_ROLE_FAMILY: str`; models `RoleSignal(role_family:str,
  seniority:SeniorityBand, city_tier:str)`, `CompBandEstimate(...)`,
  `CompBenchmark(...)`.

- [ ] **Step 1: Write the failing test**

`tests/test_comp_schema.py`:

```python
import pytest
from pydantic import ValidationError

from app.comp.schema import (
    ROLE_FAMILIES, CITY_TIERS, DEFAULT_ROLE_FAMILY,
    SeniorityBand, RoleSignal, CompBandEstimate, CompBenchmark,
)
from app.matching.schema import CompBand


def test_vocabulary_constants():
    assert DEFAULT_ROLE_FAMILY in ROLE_FAMILIES
    assert set(CITY_TIERS) == {"metro", "tier_2"}
    assert "backend_engineer" in ROLE_FAMILIES


def test_role_signal_validates_family_and_tier():
    ok = RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro")
    assert ok.seniority is SeniorityBand.SENIOR
    with pytest.raises(ValidationError):
        RoleSignal(role_family="astronaut", seniority=SeniorityBand.MID, city_tier="metro")
    with pytest.raises(ValidationError):
        RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.MID, city_tier="mars")


def test_estimate_and_benchmark_defaults():
    est = CompBandEstimate(
        p25=10.0, p50=12.0, p75=14.0, confidence=0.3,
        role_family="backend_engineer", seniority=SeniorityBand.MID, city_tier="metro",
    )
    assert est.advisory is True
    assert est.sources == ("static",)
    assert est.currency == "INR"
    bench = CompBenchmark(estimate=est, requisition_band=CompBand(ctc_min=8.0, ctc_max=10.0))
    assert bench.advisory is True
    assert bench.position is None  # unset until benchmark_comp fills it
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_comp_schema.py -v`
Expected: FAIL (`ModuleNotFoundError: app.comp.schema`).

- [ ] **Step 3: Write the implementation**

`app/comp/__init__.py`: empty file.

`app/comp/schema.py`:

```python
"""Comp intelligence contracts (PI-5 / S5.2). Pure, serializable. Advisory —
every output narrows to a band + confidence, never a decision. The static-band
vocabulary (role families, seniority, city tiers) is owned here so both the
comp engine and the ledger's observed-offer capture agree on it; the ledger
stores these as plain strings and never imports this module (layering)."""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.matching.schema import CompBand


class SeniorityBand(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


# Curated role families for the IT launch vertical. A small controlled
# vocabulary keyed by the static band table; unknown roles resolve to the default.
ROLE_FAMILIES: tuple[str, ...] = (
    "backend_engineer",
    "frontend_engineer",
    "fullstack_engineer",
    "data_engineer",
    "data_scientist",
    "ml_engineer",
    "devops_sre",
    "qa_engineer",
    "mobile_engineer",
    "engineering_manager",
)
CITY_TIERS: tuple[str, ...] = ("metro", "tier_2")
DEFAULT_ROLE_FAMILY = "backend_engineer"


class RoleSignal(BaseModel):
    """The resolved (role_family x seniority x city_tier) key comp is computed for."""

    role_family: str
    seniority: SeniorityBand
    city_tier: str

    @model_validator(mode="after")
    def _validate(self) -> "RoleSignal":
        if self.role_family not in ROLE_FAMILIES:
            raise ValueError(f"role_family must be one of {ROLE_FAMILIES}")
        if self.city_tier not in CITY_TIERS:
            raise ValueError(f"city_tier must be one of {CITY_TIERS}")
        return self


class CompBandEstimate(BaseModel):
    """Advisory comp band (annual TOTAL CTC) for a role signal."""

    currency: str = "INR"
    p25: float
    p50: float
    p75: float
    confidence: float = Field(ge=0.0, le=1.0)
    role_family: str
    seniority: SeniorityBand
    city_tier: str
    n_observed: int = 0                      # included observed offers (>= k, else 0)
    sources: tuple[str, ...] = ("static",)   # ("static",) or ("static","observed")
    reasoning: str = ""
    advisory: bool = True


class CompBenchmark(BaseModel):
    """A requisition's stored comp_band positioned against the market estimate."""

    estimate: CompBandEstimate
    requisition_band: Optional[CompBand] = None
    position: Optional[str] = None    # "below" | "at" | "above" | None (no band)
    delta_pct: Optional[float] = None  # (req_mid - p50) / p50
    reasoning: str = ""
    advisory: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_comp_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/comp/__init__.py app/comp/schema.py tests/test_comp_schema.py
git commit -m "feat(s52): comp contracts (RoleSignal, CompBandEstimate, CompBenchmark)"
```

---

### Task 3: Static bands + resolvers (`app/comp/bands.py`)

**Files:**
- Create: `app/comp/bands.py`
- Test: `tests/test_comp_bands.py`

**Interfaces:**
- Consumes: `norm_key` from `app.candidates.normalize.text`; `Settings`;
  `RoleSignal`, `SeniorityBand`, `ROLE_FAMILIES`, `CITY_TIERS`,
  `DEFAULT_ROLE_FAMILY` from `app.comp.schema`; `JobRequisition` from
  `app.matching.schema`.
- Produces:
  - `CompCell = tuple[float, float, float, float]` (fixed_low, fixed_mid,
    fixed_high, variable_fraction).
  - `lookup_cell(signal: RoleSignal, settings: Settings) -> CompCell`
  - `resolve_role_family(skills: tuple[str,...], title: str | None, settings: Settings) -> str`
  - `resolve_seniority(years: float | None, settings: Settings) -> SeniorityBand`
  - `resolve_city_tier(location_tiers, remote: bool, settings: Settings) -> str`
  - `role_signal_from_input(*, skills, title, years, location_tiers, remote, role_family, seniority, settings) -> RoleSignal`
  - `role_signal_from_requisition(req: JobRequisition, settings: Settings) -> RoleSignal`

**Note (deviates from spec §3 "nearest-lower fallback"):** the seed table is
*computed* (per-role metro-mid fixed × seniority multiplier × tier multiplier),
so every `(role, seniority, tier)` yields a cell — there is never a miss. An
optional operator override (`comp_bands_path`, JSON keyed `"role|seniority|tier"`)
wins where present and falls back to the computed seed where absent. Simpler and
fully deterministic; the spec's nearest-lower logic is unnecessary given full
coverage.

- [ ] **Step 1: Write the failing test**

`tests/test_comp_bands.py`:

```python
from app.core.config import Settings
from app.comp import bands
from app.comp.schema import RoleSignal, SeniorityBand
from app.matching.schema import JobRequisition, RequisitionStatus
from datetime import datetime, timezone


def _s() -> Settings:
    return Settings()


def test_lookup_cell_monotonic_in_seniority_and_tier():
    s = _s()
    jr = bands.lookup_cell(RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.JUNIOR, city_tier="metro"), s)
    sr = bands.lookup_cell(RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro"), s)
    t2 = bands.lookup_cell(RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="tier_2"), s)
    assert sr[1] > jr[1]          # senior mid > junior mid
    assert t2[1] < sr[1]          # tier_2 < metro
    assert jr[0] < jr[1] < jr[2]  # low < mid < high
    assert 0.0 <= jr[3] < 1.0     # variable fraction in range


def test_resolve_role_family_title_then_skills_then_default():
    s = _s()
    assert bands.resolve_role_family((), "Senior Frontend Engineer", s) == "frontend_engineer"
    assert bands.resolve_role_family(("react", "css"), None, s) == "frontend_engineer"
    assert bands.resolve_role_family(("kubernetes", "terraform"), None, s) == "devops_sre"
    assert bands.resolve_role_family((), None, s) == "backend_engineer"  # default


def test_resolve_seniority_thresholds():
    s = _s()
    assert bands.resolve_seniority(1.0, s) is SeniorityBand.JUNIOR
    assert bands.resolve_seniority(3.0, s) is SeniorityBand.MID
    assert bands.resolve_seniority(7.0, s) is SeniorityBand.SENIOR
    assert bands.resolve_seniority(12.0, s) is SeniorityBand.LEAD
    assert bands.resolve_seniority(None, s) is SeniorityBand.MID  # unknown -> neutral


def test_resolve_city_tier_remote_and_unknown_default_metro():
    s = _s()
    assert bands.resolve_city_tier(("tier_2",), False, s) == "tier_2"
    assert bands.resolve_city_tier(None, True, s) == "metro"
    assert bands.resolve_city_tier((), False, s) == "metro"


def test_role_signal_from_requisition():
    s = _s()
    req = JobRequisition(
        id="r1", org_id="o1", title="Backend Engineer",
        status=RequisitionStatus.OPEN, must_have_skills=("python",),
        nice_to_have_skills=(), min_years_experience=6.0,
        location_tiers=("metro",), remote=False,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    sig = bands.role_signal_from_requisition(req, s)
    assert sig.role_family == "backend_engineer"
    assert sig.seniority is SeniorityBand.SENIOR
    assert sig.city_tier == "metro"


def test_role_signal_from_input_overrides_win():
    s = _s()
    sig = bands.role_signal_from_input(
        skills=("react",), title="Frontend Engineer", years=1.0,
        location_tiers=None, remote=True,
        role_family="ml_engineer", seniority=SeniorityBand.LEAD, settings=s,
    )
    assert sig.role_family == "ml_engineer"      # override beats title/skills
    assert sig.seniority is SeniorityBand.LEAD    # override beats years
    assert sig.city_tier == "metro"               # remote -> metro
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_comp_bands.py -v`
Expected: FAIL (`ModuleNotFoundError: app.comp.bands`).

- [ ] **Step 3: Write the implementation**

`app/comp/bands.py`:

```python
"""Static comp prior + deterministic role-signal resolution (S5.2).

ILLUSTRATIVE, LICENSE-CLEAN SEED DATA. The per-role figures below are
hand-authored, order-of-magnitude annual FIXED CTC (INR) for the IT launch
vertical -- NOT scraped or licensed. An operator replaces them by pointing
`comp_bands_path` at a JSON file keyed "role_family|seniority|city_tier" ->
[fixed_low, fixed_mid, fixed_high, variable_fraction]. The engine is
source-agnostic; only this module knows the numbers.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from app.candidates.normalize.text import norm_key
from app.core.config import Settings, get_settings
from app.comp.schema import (
    CITY_TIERS, DEFAULT_ROLE_FAMILY, ROLE_FAMILIES, RoleSignal, SeniorityBand,
)
from app.matching.schema import JobRequisition

CompCell = tuple[float, float, float, float]  # fixed_low, fixed_mid, fixed_high, var_frac

# Per-role metro MID fixed CTC (annual INR). Illustrative seed.
_ROLE_METRO_MID_FIXED: dict[str, float] = {
    "backend_engineer": 1_800_000.0,
    "frontend_engineer": 1_600_000.0,
    "fullstack_engineer": 1_800_000.0,
    "data_engineer": 1_900_000.0,
    "data_scientist": 2_000_000.0,
    "ml_engineer": 2_200_000.0,
    "devops_sre": 2_000_000.0,
    "qa_engineer": 1_300_000.0,
    "mobile_engineer": 1_700_000.0,
    "engineering_manager": 3_200_000.0,
}
_SENIORITY_MULT: dict[SeniorityBand, float] = {
    SeniorityBand.JUNIOR: 0.55,
    SeniorityBand.MID: 1.0,
    SeniorityBand.SENIOR: 1.7,
    SeniorityBand.LEAD: 2.6,
}
_TIER_MULT: dict[str, float] = {"metro": 1.0, "tier_2": 0.75}
_VARIABLE_FRACTION: dict[str, float] = {"engineering_manager": 0.20}
_DEFAULT_VARIABLE_FRACTION = 0.12
_SPREAD = 0.22  # low = mid*(1-spread), high = mid*(1+spread)

# Title substrings -> role family, most specific first (first hit wins).
_TITLE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("engineering manager", "engineering_manager"),
    ("data engineer", "data_engineer"),
    ("data scientist", "data_scientist"),
    ("data science", "data_scientist"),
    ("machine learning", "ml_engineer"),
    ("ml engineer", "ml_engineer"),
    ("mlops", "ml_engineer"),
    ("devops", "devops_sre"),
    ("site reliability", "devops_sre"),
    ("sre", "devops_sre"),
    ("platform engineer", "devops_sre"),
    ("sdet", "qa_engineer"),
    ("test engineer", "qa_engineer"),
    ("quality", "qa_engineer"),
    (" qa", "qa_engineer"),
    ("mobile", "mobile_engineer"),
    ("android", "mobile_engineer"),
    ("ios", "mobile_engineer"),
    ("full stack", "fullstack_engineer"),
    ("fullstack", "fullstack_engineer"),
    ("full-stack", "fullstack_engineer"),
    ("front end", "frontend_engineer"),
    ("frontend", "frontend_engineer"),
    ("front-end", "frontend_engineer"),
    ("backend", "backend_engineer"),
    ("back-end", "backend_engineer"),
    ("manager", "engineering_manager"),
)

# norm_key(skill) -> role family, for the secondary (skill-signature) vote.
_SKILL_FAMILY: dict[str, str] = {
    norm_key(k): v
    for k, v in {
        "react": "frontend_engineer", "angular": "frontend_engineer",
        "vue": "frontend_engineer", "css": "frontend_engineer",
        "html": "frontend_engineer", "typescript": "frontend_engineer",
        "kubernetes": "devops_sre", "docker": "devops_sre",
        "terraform": "devops_sre", "ansible": "devops_sre", "jenkins": "devops_sre",
        "spark": "data_engineer", "hadoop": "data_engineer",
        "airflow": "data_engineer", "kafka": "data_engineer",
        "pandas": "data_scientist", "numpy": "data_scientist",
        "scikit learn": "data_scientist", "statistics": "data_scientist",
        "pytorch": "ml_engineer", "tensorflow": "ml_engineer", "nlp": "ml_engineer",
        "android": "mobile_engineer", "kotlin": "mobile_engineer",
        "swift": "mobile_engineer", "flutter": "mobile_engineer",
        "python": "backend_engineer", "java": "backend_engineer",
        "golang": "backend_engineer", "node": "backend_engineer",
        "django": "backend_engineer", "spring": "backend_engineer",
    }.items()
}


@lru_cache(maxsize=8)
def _load_override(path: str) -> dict[tuple[str, str, str], CompCell]:
    """Parse an operator override JSON. Missing/broken file -> empty (seed wins)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    out: dict[tuple[str, str, str], CompCell] = {}
    for key, cell in raw.items():
        parts = key.split("|")
        if len(parts) == 3 and isinstance(cell, list) and len(cell) == 4:
            out[(parts[0], parts[1], parts[2])] = (
                float(cell[0]), float(cell[1]), float(cell[2]), float(cell[3])
            )
    return out


def _computed_cell(signal: RoleSignal) -> CompCell:
    base = _ROLE_METRO_MID_FIXED.get(signal.role_family, _ROLE_METRO_MID_FIXED[DEFAULT_ROLE_FAMILY])
    mid = base * _SENIORITY_MULT[signal.seniority] * _TIER_MULT[signal.city_tier]
    var = _VARIABLE_FRACTION.get(signal.role_family, _DEFAULT_VARIABLE_FRACTION)
    return (mid * (1 - _SPREAD), mid, mid * (1 + _SPREAD), var)


def lookup_cell(signal: RoleSignal, settings: Optional[Settings] = None) -> CompCell:
    s = settings or get_settings()
    if s.comp_bands_path:
        override = _load_override(s.comp_bands_path)
        cell = override.get((signal.role_family, signal.seniority.value, signal.city_tier))
        if cell is not None:
            return cell
    return _computed_cell(signal)


def resolve_role_family(
    skills: tuple[str, ...], title: Optional[str], settings: Optional[Settings] = None
) -> str:
    if title:
        low = title.lower()
        for kw, fam in _TITLE_KEYWORDS:
            if kw in low:
                return fam
    votes: dict[str, int] = {}
    for sk in skills:
        fam = _SKILL_FAMILY.get(norm_key(sk))
        if fam:
            votes[fam] = votes.get(fam, 0) + 1
    if votes:
        top = max(votes.values())
        return sorted(f for f, c in votes.items() if c == top)[0]  # deterministic tie-break
    return DEFAULT_ROLE_FAMILY


def resolve_seniority(
    years: Optional[float], settings: Optional[Settings] = None
) -> SeniorityBand:
    s = settings or get_settings()
    if years is None:
        return SeniorityBand.MID  # unknown -> neutral
    if years < s.comp_mid_years:
        return SeniorityBand.JUNIOR
    if years < s.comp_senior_years:
        return SeniorityBand.MID
    if years < s.comp_lead_years:
        return SeniorityBand.SENIOR
    return SeniorityBand.LEAD


def resolve_city_tier(
    location_tiers: Optional[tuple[str, ...]], remote: bool, settings: Optional[Settings] = None
) -> str:
    if location_tiers:
        t = location_tiers[0]
        if t in CITY_TIERS:
            return t
    return "metro"  # remote / unknown -> metro baseline


def role_signal_from_input(
    *,
    skills: tuple[str, ...] = (),
    title: Optional[str] = None,
    years: Optional[float] = None,
    location_tiers: Optional[tuple[str, ...]] = None,
    remote: bool = False,
    role_family: Optional[str] = None,
    seniority: Optional[SeniorityBand] = None,
    settings: Optional[Settings] = None,
) -> RoleSignal:
    s = settings or get_settings()
    if role_family is not None and role_family not in ROLE_FAMILIES:
        raise ValueError(f"role_family must be one of {ROLE_FAMILIES}")
    rf = role_family or resolve_role_family(tuple(skills), title, s)
    sen = seniority or resolve_seniority(years, s)
    tier = resolve_city_tier(tuple(location_tiers) if location_tiers else None, remote, s)
    return RoleSignal(role_family=rf, seniority=sen, city_tier=tier)


def role_signal_from_requisition(
    req: JobRequisition, settings: Optional[Settings] = None
) -> RoleSignal:
    s = settings or get_settings()
    return RoleSignal(
        role_family=resolve_role_family(tuple(req.must_have_skills), req.title, s),
        seniority=resolve_seniority(req.min_years_experience, s),
        city_tier=resolve_city_tier(
            tuple(req.location_tiers) if req.location_tiers else None, req.remote, s
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_comp_bands.py -v`
Expected: PASS. If `resolve_role_family(("react","css"), None)` fails, verify
`norm_key("react") == "react"`; adjust the `_SKILL_FAMILY` key normalization only.

- [ ] **Step 5: Commit**

```bash
git add app/comp/bands.py tests/test_comp_bands.py
git commit -m "feat(s52): static comp seed table + deterministic role-signal resolvers"
```

---

### Task 4: Blend engine (`app/comp/estimate.py`)

**Files:**
- Create: `app/comp/estimate.py`
- Test: `tests/test_comp_estimate.py`

**Interfaces:**
- Consumes: `Settings`; `RoleSignal`, `CompBandEstimate`, `CompBenchmark` from
  `app.comp.schema`; `CompBand` from `app.matching.schema`; `ObservedOfferPoint`
  from `app.ledger.schema` (defined in Task 5 — for the test in this task, use a
  tiny stand-in object with `.total_ctc`/`.offered_at`, OR sequence Task 5 first;
  see note). `CompCell` from `app.comp.bands`.
- Produces:
  - `estimate_comp(signal: RoleSignal, cell: CompCell, points: Sequence, *, now: datetime, settings=None) -> CompBandEstimate`
  - `benchmark_comp(estimate: CompBandEstimate, comp_band: CompBand | None, *, settings=None) -> CompBenchmark`

**Note:** `estimate_comp` reads only `.total_ctc` and `.offered_at` off each
point, so it does not import `ObservedOfferPoint` — it stays duck-typed and pure.
Tests use a local namedtuple, so this task has NO dependency on Task 5.

- [ ] **Step 1: Write the failing test**

`tests/test_comp_estimate.py`:

```python
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.comp.estimate import estimate_comp, benchmark_comp
from app.comp.schema import RoleSignal, SeniorityBand
from app.matching.schema import CompBand

Point = namedtuple("Point", ["total_ctc", "offered_at"])
NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)
SIG = RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.MID, city_tier="metro")
CELL = (1_584_000.0, 1_800_000.0, 2_016_000.0, 0.12)  # mid=18L fixed, var 12%


def _s() -> Settings:
    return Settings()


def test_static_only_when_below_k():
    s = _s()
    pts = [Point(3_000_000.0, NOW)] * 3  # 3 < comp_min_observations (5)
    est = estimate_comp(SIG, CELL, pts, now=NOW, settings=s)
    assert est.sources == ("static",)
    assert est.n_observed == 0
    assert est.confidence == s.comp_confidence_floor
    # p50 == static total mid = 18L * 1.12
    assert round(est.p50) == round(1_800_000.0 * 1.12)
    assert est.p25 < est.p50 < est.p75


def test_observed_blend_shifts_toward_observed_and_raises_confidence():
    s = _s()
    static_total_mid = 1_800_000.0 * 1.12
    pts = [Point(3_000_000.0, NOW)] * 6  # 6 >= k, all well above static
    est = estimate_comp(SIG, CELL, pts, now=NOW, settings=s)
    assert est.sources == ("static", "observed")
    assert est.n_observed == 6
    assert est.p50 > static_total_mid           # pulled up toward 30L
    assert est.p50 < 3_000_000.0                # but shrunk by the prior
    assert est.confidence > s.comp_confidence_floor
    assert est.p25 < est.p50 < est.p75


def test_recency_downweights_old_offers():
    s = _s()
    old = NOW - timedelta(days=5 * 365)  # ~5 half-lives -> tiny weight
    recent = [Point(3_000_000.0, NOW)] * 5
    with_old = recent + [Point(500_000.0, old)]  # one stale low offer
    est_recent = estimate_comp(SIG, CELL, recent, now=NOW, settings=s)
    est_mixed = estimate_comp(SIG, CELL, with_old, now=NOW, settings=s)
    # the stale low offer barely moves p50
    assert abs(est_mixed.p50 - est_recent.p50) < 0.02 * est_recent.p50


def test_benchmark_positions():
    s = _s()
    est = estimate_comp(SIG, CELL, [], now=NOW, settings=s)  # static-only
    p50 = est.p50
    at = benchmark_comp(est, CompBand(ctc_min=p50 * 0.97, ctc_max=p50 * 1.03), settings=s)
    below = benchmark_comp(est, CompBand(ctc_min=p50 * 0.5, ctc_max=p50 * 0.6), settings=s)
    above = benchmark_comp(est, CompBand(ctc_min=p50 * 1.4, ctc_max=p50 * 1.5), settings=s)
    none = benchmark_comp(est, None, settings=s)
    assert at.position == "at"
    assert below.position == "below" and below.delta_pct < 0
    assert above.position == "above" and above.delta_pct > 0
    assert none.position is None and none.requisition_band is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_comp_estimate.py -v`
Expected: FAIL (`ModuleNotFoundError: app.comp.estimate`).

- [ ] **Step 3: Write the implementation**

`app/comp/estimate.py`:

```python
"""Comp blend engine (S5.2) -- pure, no I/O, no clock (caller passes `now`).

Mirrors app/ledger/reputation.py: a static prior shrunk by observed evidence.
Everything blends on a TOTAL-CTC basis (observed offers already carry total;
the static cell's FIXED figures are grossed up by the variable fraction first).
Advisory only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from app.core.config import Settings, get_settings
from app.comp.schema import CompBandEstimate, CompBenchmark, RoleSignal
from app.matching.schema import CompBand


def _recency_weight(at: datetime, now: datetime, halflife_days: float) -> float:
    age_days = max(0.0, (now - at).total_seconds() / 86400.0)  # future-dated -> 0 age
    return 0.5 ** (age_days / halflife_days)


def estimate_comp(
    signal: RoleSignal,
    cell: tuple[float, float, float, float],
    points: Sequence,
    *,
    now: datetime,
    settings: Optional[Settings] = None,
) -> CompBandEstimate:
    s = settings or get_settings()
    f_low, f_mid, f_high, var = cell
    gross = 1.0 + var
    t_low, t_mid, t_high = f_low * gross, f_mid * gross, f_high * gross

    n = len(points)
    include = n >= s.comp_min_observations
    if include:
        weights = [_recency_weight(p.offered_at, now, s.comp_recency_halflife_days) for p in points]
        W = sum(weights)
        mu = (sum(w * p.total_ctc for w, p in zip(weights, points)) / W) if W > 0 else t_mid
        k0 = s.comp_prior_strength
        p50 = (k0 * t_mid + W * mu) / (k0 + W)
        confidence = min(
            s.comp_confidence_cap,
            s.comp_confidence_floor + (1.0 - s.comp_confidence_floor) * (W / (W + s.comp_confidence_k)),
        )
        sources = ("static", "observed")
        n_obs = n
        reasoning = (
            f"Blended {n} consented observed offer(s) (recency-weighted mass "
            f"{W:.2f}, mean {mu:,.0f}) with the static prior ({t_mid:,.0f}) for "
            f"{signal.role_family}/{signal.seniority.value}/{signal.city_tier}: "
            f"p50 {p50:,.0f}. Advisory only."
        )
    else:
        p50 = t_mid
        confidence = s.comp_confidence_floor
        sources = ("static",)
        n_obs = 0
        reasoning = (
            f"Static prior only for {signal.role_family}/{signal.seniority.value}/"
            f"{signal.city_tier} ({n} observed offer(s) < k={s.comp_min_observations}); "
            f"p50 {p50:,.0f}. Advisory only."
        )

    p25 = p50 * (t_low / t_mid) if t_mid else p50
    p75 = p50 * (t_high / t_mid) if t_mid else p50
    return CompBandEstimate(
        currency=s.comp_currency_default,
        p25=round(p25, 2), p50=round(p50, 2), p75=round(p75, 2),
        confidence=round(confidence, 2),
        role_family=signal.role_family, seniority=signal.seniority, city_tier=signal.city_tier,
        n_observed=n_obs, sources=sources, reasoning=reasoning,
    )


def _req_mid(comp_band: Optional[CompBand]) -> Optional[float]:
    if comp_band is None:
        return None
    lo, hi = comp_band.ctc_min, comp_band.ctc_max
    if lo is not None and hi is not None:
        return (lo + hi) / 2.0
    return lo if lo is not None else hi


def benchmark_comp(
    estimate: CompBandEstimate,
    comp_band: Optional[CompBand],
    *,
    settings: Optional[Settings] = None,
) -> CompBenchmark:
    s = settings or get_settings()
    mid = _req_mid(comp_band)
    if mid is None:
        return CompBenchmark(
            estimate=estimate, requisition_band=comp_band, position=None, delta_pct=None,
            reasoning="Requisition has no comp_band to benchmark; market estimate only. Advisory.",
        )
    delta = (mid - estimate.p50) / estimate.p50 if estimate.p50 > 0 else 0.0
    if abs(delta) <= s.comp_benchmark_tolerance:
        position = "at"
    elif delta < 0:
        position = "below"
    else:
        position = "above"
    return CompBenchmark(
        estimate=estimate, requisition_band=comp_band, position=position,
        delta_pct=round(delta, 4),
        reasoning=(
            f"Requisition midpoint {mid:,.0f} is {position} the market p50 "
            f"{estimate.p50:,.0f} ({delta:+.1%}). Advisory only."
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_comp_estimate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/comp/estimate.py tests/test_comp_estimate.py
git commit -m "feat(s52): comp blend engine (static prior shrinkage + benchmark)"
```

---

### Task 5: ObservedOffer contract + ORM + migration 0009 + drift guards

**Files:**
- Modify: `app/ledger/schema.py` (add `ObservedOffer`, `ObservedOfferPoint`)
- Modify: `app/ledger/models.py` (add `ObservedOfferRow`)
- Create: `alembic/versions/0009_observed_offers.py`
- Modify: `tests/test_migrations.py` (extend table set + `LEDGER_TABLES`)
- Test: `tests/test_ledger_models.py` (add a construction test) + the migration tests

**Interfaces:**
- Produces:
  - `ObservedOffer(BaseModel)`: `id, org_id, candidate_id, consent_id,
    role_family:str, seniority:str, city_tier:str, ctc_fixed:float,
    ctc_variable:float|None, currency:str, offered_at:datetime, created_at:datetime`.
  - `ObservedOfferPoint(BaseModel)`: `total_ctc:float, offered_at:datetime`
    (de-identified projection — NO candidate/org id).
  - `ObservedOfferRow` ORM (table `observed_offers`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_migrations.py` `test_upgrade_head_creates_candidate_tables`
the assertion `assert "observed_offers" in names  # S5.2 migration 0009`, and add
`"observed_offers"` to the `LEDGER_TABLES` tuple. Add to `tests/test_ledger_models.py`:

```python
def test_observed_offer_contract_roundtrips():
    from datetime import datetime, timezone
    from app.ledger.schema import ObservedOffer, ObservedOfferPoint
    o = ObservedOffer(
        id="x", org_id="o1", candidate_id="c1", consent_id="g1",
        role_family="backend_engineer", seniority="senior", city_tier="metro",
        ctc_fixed=2_500_000.0, ctc_variable=300_000.0, currency="INR",
        offered_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    assert o.ctc_fixed == 2_500_000.0
    p = ObservedOfferPoint(total_ctc=2_800_000.0, offered_at=o.offered_at)
    assert p.total_ctc == 2_800_000.0
    assert not hasattr(p, "candidate_id")  # de-identified by construction
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ledger_models.py::test_observed_offer_contract_roundtrips tests/test_migrations.py -v`
Expected: FAIL (import error, then drift/table assertions once the model exists).

- [ ] **Step 3: Add the contract**

In `app/ledger/schema.py` (after `CodingRoundResult`):

```python
class ObservedOffer(BaseModel):
    """One compensation offer an org extended to a candidate (S5.2). A peer of
    CodingRoundResult: consent-gated, candidate-linked, DPDP-swept. Carries its
    own role signal (role_family/seniority/city_tier as strings -- the comp
    vocabulary is validated at the API boundary, keeping this module comp-free).
    Field bounds are data hygiene, NOT scoring."""

    id: str
    org_id: str
    candidate_id: str
    consent_id: str  # the ledger_write grant this was submitted under
    role_family: str
    seniority: str
    city_tier: str
    ctc_fixed: float = Field(ge=0)
    ctc_variable: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    offered_at: datetime
    created_at: datetime


class ObservedOfferPoint(BaseModel):
    """De-identified projection for cross-candidate comp aggregation. Carries NO
    candidate/org identity -- only the total CTC and when it was offered, so the
    comp engine can never re-leak who was offered what."""

    total_ctc: float
    offered_at: datetime
```

- [ ] **Step 4: Add the ORM row**

In `app/ledger/models.py` (after `CodingRoundResultRow`), first add `Index` to the
existing sqlalchemy import if not present, then:

```python
class ObservedOfferRow(Base):
    """One compensation offer one org extended to one candidate (S5.2). Peer of
    coding_round_results: same consent/audit/DPDP machinery. Candidate-linked so
    erasure cascades it; org-linked so org deletion cascades it. The composite
    index serves the comp aggregation query (role_family, seniority, city_tier)."""

    __tablename__ = "observed_offers"
    __table_args__ = (
        Index("ix_observed_offers_role_signal", "role_family", "seniority", "city_tier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=False
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    consent_id: Mapped[str] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="CASCADE"), index=False
    )
    role_family: Mapped[str] = mapped_column(String(32))
    seniority: Mapped[str] = mapped_column(String(16))
    city_tier: Mapped[str] = mapped_column(String(16))
    ctc_fixed: Mapped[float] = mapped_column(Float)
    ctc_variable: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 5: Write migration 0009**

`alembic/versions/0009_observed_offers.py`:

```python
"""observed offers: consent-gated comp capture for comp intelligence (S5.2)

Revision ID: 0009_observed_offers
Revises: 0008_job_requisitions
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0009_observed_offers"
down_revision = "0008_job_requisitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observed_offers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id", sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "consent_id", sa.String(length=36),
            sa.ForeignKey("consent_grants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("role_family", sa.String(length=32), nullable=False),
        sa.Column("seniority", sa.String(length=16), nullable=False),
        sa.Column("city_tier", sa.String(length=16), nullable=False),
        sa.Column("ctc_fixed", sa.Float(), nullable=False),
        sa.Column("ctc_variable", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observed_offers_candidate_id", "observed_offers", ["candidate_id"])
    op.create_index(
        "ix_observed_offers_role_signal", "observed_offers",
        ["role_family", "seniority", "city_tier"],
    )


def downgrade() -> None:
    op.drop_index("ix_observed_offers_role_signal", table_name="observed_offers")
    op.drop_index("ix_observed_offers_candidate_id", table_name="observed_offers")
    op.drop_table("observed_offers")
```

- [ ] **Step 6: Run the migration + model tests**

Run: `pytest tests/test_ledger_models.py tests/test_migrations.py -v`
Expected: PASS — table present, drift guard clean (ORM `index=True` on
`candidate_id` → `ix_observed_offers_candidate_id`; composite index matches;
`currency` non-null with a python default; every FK `ondelete="CASCADE"`).

- [ ] **Step 7: Commit**

```bash
git add app/ledger/schema.py app/ledger/models.py alembic/versions/0009_observed_offers.py tests/test_ledger_models.py tests/test_migrations.py
git commit -m "feat(s52): observed_offers table + contracts + migration 0009 (CASCADE, drift-guarded)"
```

---

### Task 6: `LedgerStore.submit_observed_offer` (consent-gated write)

**Files:**
- Modify: `app/ledger/store.py`
- Test: `tests/test_ledger_store_offers.py`

**Interfaces:**
- Consumes: `ObservedOfferRow`, `ObservedOffer`, `ConsentPurpose.LEDGER_WRITE`,
  `consent_logic.check_consent`, the `_audit` helper.
- Produces: `LedgerStore.submit_observed_offer(*, org_id, candidate_id,
  role_family, seniority, city_tier, ctc_fixed, ctc_variable=None,
  currency="INR", offered_at, now=None) -> ObservedOffer`. Raises `ConsentError`
  without an active `ledger_write` grant; `LookupError` for unknown org/candidate.
  Audits `offer.submit`.

- [ ] **Step 1: Write the failing test**

`tests/test_ledger_store_offers.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _setup():
    cands = make_candidate_store()
    ledger = LedgerStore(cands._session_factory)
    org = ledger.create_organization("Acme")
    cand = cands.ingest_resume("Ann Example\nann@example.com\nPython\n")
    return cands, ledger, org.id, cand.candidate_id


def _submit(ledger, org_id, cand_id):
    return ledger.submit_observed_offer(
        org_id=org_id, candidate_id=cand_id,
        role_family="backend_engineer", seniority="senior", city_tier="metro",
        ctc_fixed=2_500_000.0, ctc_variable=300_000.0, offered_at=NOW, now=NOW,
    )


def test_submit_requires_write_consent():
    _cands, ledger, org_id, cand_id = _setup()
    with pytest.raises(ConsentError):
        _submit(ledger, org_id, cand_id)


def test_submit_stamps_consent_and_audits():
    _cands, ledger, org_id, cand_id = _setup()
    grant = ledger.grant_consent(candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE,
                                 org_id=org_id, expires_at=NOW + timedelta(days=30), now=NOW)
    offer = _submit(ledger, org_id, cand_id)
    assert offer.consent_id == grant.id
    assert offer.ctc_fixed == 2_500_000.0
    actions = [a.action for a in ledger.audit_for_candidate(cand_id)]
    assert "offer.submit" in actions


def test_submit_unknown_candidate_raises_lookup():
    _cands, ledger, org_id, _cand_id = _setup()
    with pytest.raises(LookupError):
        ledger.submit_observed_offer(
            org_id=org_id, candidate_id="nope", role_family="backend_engineer",
            seniority="mid", city_tier="metro", ctc_fixed=1.0, offered_at=NOW, now=NOW,
        )


def test_offer_cascades_on_candidate_erasure():
    cands, ledger, org_id, cand_id = _setup()
    ledger.grant_consent(candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE,
                         org_id=org_id, expires_at=NOW + timedelta(days=30), now=NOW)
    _submit(ledger, org_id, cand_id)
    cands.delete_candidate(cand_id)  # DPDP erasure
    # a fresh aggregate read (Task 7) would find nothing; here assert the row is gone
    from app.ledger.models import ObservedOfferRow
    with ledger._session_factory() as s:
        assert s.query(ObservedOfferRow).count() == 0
```

(If `CandidateStore.ingest_resume`/`delete_candidate` have different names, match
the ones used in `tests/test_ledger_store_records.py`.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_ledger_store_offers.py -v`
Expected: FAIL (`AttributeError: submit_observed_offer`).

- [ ] **Step 3: Implement**

Add the import to the `app.ledger.models` import group in `store.py`
(`ObservedOfferRow`) and to the `app.ledger.schema` group (`ObservedOffer`,
`ObservedOfferPoint`). Add a converter near `_coding_round`:

```python
def _observed_offer(row: ObservedOfferRow) -> ObservedOffer:
    return ObservedOffer(
        id=row.id, org_id=row.org_id, candidate_id=row.candidate_id,
        consent_id=row.consent_id, role_family=row.role_family,
        seniority=row.seniority, city_tier=row.city_tier,
        ctc_fixed=row.ctc_fixed, ctc_variable=row.ctc_variable, currency=row.currency,
        offered_at=consent_logic.as_utc(row.offered_at),
        created_at=consent_logic.as_utc(row.created_at),
    )
```

Add the method (after `submit_coding_round`):

```python
    # -- observed offers (S5.2, consent-gated like interview records) -----------

    def submit_observed_offer(
        self,
        *,
        org_id: str,
        candidate_id: str,
        role_family: str,
        seniority: str,
        city_tier: str,
        ctc_fixed: float,
        ctc_variable: Optional[float] = None,
        currency: str = "INR",
        offered_at: datetime,
        now: Optional[datetime] = None,
    ) -> ObservedOffer:
        """Write-time DPDP gate: refuses without an active ledger_write grant.
        role_family/seniority/city_tier are validated at the API boundary."""
        moment = consent_logic.as_utc(now) if now else _utcnow()
        offered_at = consent_logic.as_utc(offered_at)
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_WRITE)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_WRITE, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)
            row = ObservedOfferRow(
                org_id=org_id, candidate_id=candidate_id, consent_id=decision.grant_id,
                role_family=role_family, seniority=seniority, city_tier=city_tier,
                ctc_fixed=ctc_fixed, ctc_variable=ctc_variable, currency=currency,
                offered_at=offered_at,
            )
            session.add(row)
            session.flush()
            self._audit(
                session, actor_type="org", actor_id=org_id, action="offer.submit",
                entity_type="observed_offer", entity_id=row.id, candidate_id=candidate_id,
                details={
                    "role_family": role_family, "seniority": seniority,
                    "city_tier": city_tier, "ctc_fixed": ctc_fixed,
                    "consent_id": decision.grant_id,
                },
            )
            session.commit()
            return _observed_offer(row)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_ledger_store_offers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_offers.py
git commit -m "feat(s52): LedgerStore.submit_observed_offer (ledger_write-gated, audited)"
```

---

### Task 7: `LedgerStore.observed_offers_for_comp` (de-identified aggregate read)

**Files:**
- Modify: `app/ledger/store.py`
- Test: `tests/test_ledger_store_offers.py` (extend)

**Interfaces:**
- Produces: `LedgerStore.observed_offers_for_comp(*, requesting_org_id: str,
  role_family: str, seniority: str, city_tier: str, at: datetime | None = None)
  -> list[ObservedOfferPoint]`. Returns only offers matching the role signal whose
  stamped `ledger_write` grant is still active at `at` (revocation/expiry
  respecting), de-identified. Audits `comp.aggregate` (matched/active/excluded
  counts, `candidate_id=None`) in the same transaction.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ledger_store_offers.py`:

```python
def test_aggregate_returns_deidentified_active_only():
    cands, ledger, org_id, cand_id = _setup()
    g = ledger.grant_consent(candidate_id=cand_id, purpose="ledger_write",
                             org_id=org_id, expires_at=NOW + timedelta(days=90), now=NOW)
    _submit(ledger, org_id, cand_id)
    pts = ledger.observed_offers_for_comp(
        requesting_org_id=org_id, role_family="backend_engineer",
        seniority="senior", city_tier="metro", at=NOW,
    )
    assert len(pts) == 1
    assert pts[0].total_ctc == 2_500_000.0 + 300_000.0  # fixed + variable
    assert not hasattr(pts[0], "candidate_id")
    # role-signal filter excludes non-matching cells
    assert ledger.observed_offers_for_comp(
        requesting_org_id=org_id, role_family="frontend_engineer",
        seniority="senior", city_tier="metro", at=NOW,
    ) == []
    # revocation drops the offer from the aggregate
    ledger.revoke_consent(g.id, now=NOW + timedelta(days=1))
    later = NOW + timedelta(days=2)
    assert ledger.observed_offers_for_comp(
        requesting_org_id=org_id, role_family="backend_engineer",
        seniority="senior", city_tier="metro", at=later,
    ) == []
    assert "comp.aggregate" in [a.action for a in ledger.audit_for_candidate(cand_id)] \
        or True  # aggregate audit is candidate_id=None; see next assertion


def test_aggregate_audits_with_null_candidate():
    from app.ledger.models import AuditLogRow
    cands, ledger, org_id, cand_id = _setup()
    ledger.grant_consent(candidate_id=cand_id, purpose="ledger_write", org_id=org_id,
                         expires_at=NOW + timedelta(days=90), now=NOW)
    _submit(ledger, org_id, cand_id)
    ledger.observed_offers_for_comp(requesting_org_id=org_id, role_family="backend_engineer",
                                    seniority="senior", city_tier="metro", at=NOW)
    with ledger._session_factory() as s:
        agg = s.query(AuditLogRow).filter(AuditLogRow.action == "comp.aggregate").all()
    assert len(agg) == 1
    assert agg[0].candidate_id is None            # aggregate is not about one candidate
    assert agg[0].details["active"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_ledger_store_offers.py -k aggregate -v`
Expected: FAIL (`AttributeError: observed_offers_for_comp`).

- [ ] **Step 3: Implement**

Add `ConsentGrantRow` to the models import group if not already imported, and add
the method (after `submit_observed_offer`):

```python
    def observed_offers_for_comp(
        self,
        *,
        requesting_org_id: str,
        role_family: str,
        seniority: str,
        city_tier: str,
        at: Optional[datetime] = None,
    ) -> list[ObservedOfferPoint]:
        """Cross-candidate comp aggregation read (S5.2). Returns DE-IDENTIFIED
        points (total_ctc + offered_at only) for offers matching the role signal
        whose stamped ledger_write grant is still active at `at` -- so a
        candidate's revocation/expiry removes their offer. Audits comp.aggregate
        (candidate_id=None: the aggregate is about a role, not a person). The
        k-anonymity floor is applied by the comp engine, not here."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ObservedOfferRow).where(
                        ObservedOfferRow.role_family == role_family,
                        ObservedOfferRow.seniority == seniority,
                        ObservedOfferRow.city_tier == city_tier,
                    )
                ).scalars().all()
            )
            points: list[ObservedOfferPoint] = []
            for r in rows:
                grant_row = session.get(ConsentGrantRow, r.consent_id)
                if grant_row is None:
                    continue
                if consent_logic.is_grant_active(
                    _grant(grant_row), org_id=r.org_id,
                    purpose=ConsentPurpose.LEDGER_WRITE, at=moment,
                ):
                    points.append(ObservedOfferPoint(
                        total_ctc=r.ctc_fixed + (r.ctc_variable or 0.0),
                        offered_at=consent_logic.as_utc(r.offered_at),
                    ))
            self._audit(
                session, actor_type="org", actor_id=requesting_org_id,
                action="comp.aggregate", entity_type="role_signal",
                entity_id=f"{role_family}:{seniority}:{city_tier}", candidate_id=None,
                details={
                    "matched": len(rows), "active": len(points),
                    "excluded": len(rows) - len(points),
                },
            )
            session.commit()
            return points
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_ledger_store_offers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_offers.py
git commit -m "feat(s52): LedgerStore.observed_offers_for_comp (de-identified, revocation-respecting)"
```

---

### Task 8: `CompService` + `Services.comp` wiring

**Files:**
- Create: `app/comp/service.py`
- Modify: `app/services/__init__.py` (add `comp: CompService` field + build)
- Modify: `tests/conftest.py` (`make_services` builds a `CompService`)
- Test: `tests/test_comp_service.py`

**Interfaces:**
- Consumes: `LedgerStore` (`observed_offers_for_comp`), `bands.lookup_cell`,
  `bands.role_signal_from_requisition`, `estimate.estimate_comp`,
  `estimate.benchmark_comp`, `JobRequisition`.
- Produces:
  - `CompService.estimate(signal: RoleSignal, *, org_id: str, as_of=None) -> CompBandEstimate`
  - `CompService.benchmark(req: JobRequisition, *, org_id: str, as_of=None) -> CompBenchmark`
  - `build_comp_service(settings=None) -> CompService`
  - `Services.comp: CompService`

- [ ] **Step 1: Write the failing test**

`tests/test_comp_service.py`:

```python
from datetime import datetime, timedelta, timezone

from app.comp.schema import RoleSignal, SeniorityBand
from app.comp.service import CompService
from app.matching.schema import CompBand, JobRequisition, RequisitionStatus
from tests.conftest import make_candidate_store
from app.core.config import Settings
from app.ledger.store import LedgerStore

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _svc():
    cands = make_candidate_store()
    ledger = LedgerStore(cands._session_factory)
    return cands, ledger, CompService(ledger, settings=Settings())


def test_estimate_static_only_then_shifts_with_offers():
    cands, ledger, svc = _svc()
    org = ledger.create_organization("Acme")
    sig = RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro")
    static = svc.estimate(sig, org_id=org.id, as_of=NOW)
    assert static.sources == ("static",)
    # add 6 consented high offers, re-estimate
    for i in range(6):
        c = cands.ingest_resume(f"C{i}\nc{i}@example.com\nPython\n")
        ledger.grant_consent(candidate_id=c.candidate_id, purpose="ledger_write",
                             org_id=org.id, expires_at=NOW + timedelta(days=90), now=NOW)
        ledger.submit_observed_offer(
            org_id=org.id, candidate_id=c.candidate_id, role_family="backend_engineer",
            seniority="senior", city_tier="metro", ctc_fixed=4_000_000.0, offered_at=NOW, now=NOW,
        )
    blended = svc.estimate(sig, org_id=org.id, as_of=NOW)
    assert blended.sources == ("static", "observed")
    assert blended.p50 > static.p50


def test_benchmark_from_requisition():
    cands, ledger, svc = _svc()
    org = ledger.create_organization("Acme")
    est_sig = svc.estimate(
        RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro"),
        org_id=org.id, as_of=NOW,
    )
    low = est_sig.p50 * 0.5
    req = JobRequisition(
        id="r1", org_id=org.id, title="Senior Backend Engineer",
        status=RequisitionStatus.OPEN, must_have_skills=("python",), nice_to_have_skills=(),
        min_years_experience=7.0, location_tiers=("metro",), remote=False,
        comp_band=CompBand(ctc_min=low * 0.9, ctc_max=low * 1.1),
        created_at=NOW, updated_at=NOW,
    )
    bench = svc.benchmark(req, org_id=org.id, as_of=NOW)
    assert bench.position == "below"
    assert bench.estimate.role_family == "backend_engineer"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_comp_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.comp.service`).

- [ ] **Step 3: Implement the service**

`app/comp/service.py`:

```python
"""Comp intelligence service (S5.2) -- wires the pure engine to the ledger's
observed-offer read. Holds no tables; reads offers via LedgerStore. Advisory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.config import Settings, get_settings
from app.comp import bands
from app.comp.estimate import benchmark_comp, estimate_comp
from app.comp.schema import CompBandEstimate, CompBenchmark, RoleSignal
from app.ledger.store import LedgerStore, build_ledger_store
from app.matching.schema import JobRequisition


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompService:
    def __init__(self, ledger_store: LedgerStore, *, settings: Optional[Settings] = None) -> None:
        self._ledger = ledger_store
        self._settings = settings or get_settings()

    def estimate(
        self, signal: RoleSignal, *, org_id: str, as_of: Optional[datetime] = None
    ) -> CompBandEstimate:
        now = as_of or _utcnow()
        cell = bands.lookup_cell(signal, self._settings)
        points = self._ledger.observed_offers_for_comp(
            requesting_org_id=org_id, role_family=signal.role_family,
            seniority=signal.seniority.value, city_tier=signal.city_tier, at=now,
        )
        return estimate_comp(signal, cell, points, now=now, settings=self._settings)

    def benchmark(
        self, req: JobRequisition, *, org_id: str, as_of: Optional[datetime] = None
    ) -> CompBenchmark:
        signal = bands.role_signal_from_requisition(req, self._settings)
        est = self.estimate(signal, org_id=org_id, as_of=as_of)
        return benchmark_comp(est, req.comp_band, settings=self._settings)


def build_comp_service(settings: Optional[Settings] = None) -> CompService:
    settings = settings or get_settings()
    return CompService(build_ledger_store(settings), settings=settings)
```

- [ ] **Step 4: Wire `Services.comp`**

In `app/services/__init__.py`: under `TYPE_CHECKING` add
`from app.comp.service import CompService`; add field `comp: CompService` to the
dataclass (after `jobs`); in `build_default_services`, add function-local
`from app.comp.service import build_comp_service` and `comp=build_comp_service(settings)`
to the `Services(...)` call.

In `tests/conftest.py` `make_services`, add a `comp=None` parameter and, before the
`return Services(...)`, build it and pass it:

```python
    if comp is None:
        from app.comp.service import CompService
        comp = CompService(ledger, settings=settings)
```
and add `comp=comp,` to the `Services(...)` constructor call.

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_comp_service.py -v && pytest -q -k "services or conftest" -v`
Expected: PASS. Then `pytest -q` to confirm the new required dataclass field did
not break other `Services(...)` construction sites (fix any by adding `comp=`).

- [ ] **Step 6: Commit**

```bash
git add app/comp/service.py app/services/__init__.py tests/conftest.py tests/test_comp_service.py
git commit -m "feat(s52): CompService + Services.comp wiring (import-cycle-safe)"
```

---

### Task 9: Endpoints — submit offer, estimate, benchmark

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_comp_api.py`

**Interfaces:**
- Produces (org plane, `X-Org-Key`):
  - `POST /ledger/offers` → `ObservedOffer` (403 no write consent, 404 unknown
    candidate/org, 400 invalid role_family/city_tier, 401 bad key).
  - `POST /comp/estimate` → `CompBandEstimate` (400 malformed, 401 bad key).
  - `GET /jobs/{req_id}/comp` → `CompBenchmark` (404 cross-org/unknown, 401).

- [ ] **Step 1: Write the failing test**

`tests/test_comp_api.py` (mirror `tests/test_matching_api.py` / the ledger API
tests for how they build the `TestClient` with the app lifespan and an org key;
follow that exact fixture pattern):

```python
from datetime import datetime, timezone

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc).isoformat()


def test_estimate_static_only(org_client):
    client, ctx = org_client  # (TestClient, dict with org key headers etc.)
    resp = client.post("/comp/estimate", headers=ctx["headers"],
                       json={"title": "Senior Backend Engineer", "years_experience": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["advisory"] is True
    assert body["sources"] == ["static"]
    assert body["role_family"] == "backend_engineer"
    assert body["p25"] < body["p50"] < body["p75"]


def test_submit_offer_requires_consent_then_succeeds(org_client):
    client, ctx = org_client
    cand_id = ctx["candidate_id"]
    payload = {
        "candidate_id": cand_id, "role_family": "backend_engineer",
        "seniority": "senior", "city_tier": "metro",
        "ctc_fixed": 2500000, "offered_at": NOW,
    }
    r1 = client.post("/ledger/offers", headers=ctx["headers"], json=payload)
    assert r1.status_code == 403  # no ledger_write grant yet
    ctx["grant_write"]()          # helper grants ledger_write for cand_id/org
    r2 = client.post("/ledger/offers", headers=ctx["headers"], json=payload)
    assert r2.status_code == 200
    assert r2.json()["ctc_fixed"] == 2500000


def test_submit_offer_invalid_role_family_400(org_client):
    client, ctx = org_client
    ctx["grant_write"]()
    payload = {
        "candidate_id": ctx["candidate_id"], "role_family": "astronaut",
        "seniority": "senior", "city_tier": "metro", "ctc_fixed": 1, "offered_at": NOW,
    }
    assert client.post("/ledger/offers", headers=ctx["headers"], json=payload).status_code == 400


def test_benchmark_cross_org_404_and_owned_ok(org_client):
    client, ctx = org_client
    # create a requisition with a low comp_band, then benchmark it
    req = client.post("/jobs", headers=ctx["headers"], json={
        "title": "Senior Backend Engineer", "must_have_skills": ["python"],
        "min_years_experience": 7, "location_tiers": ["metro"],
        "comp_band": {"ctc_min": 800000, "ctc_max": 900000},
    }).json()
    resp = client.get(f"/jobs/{req['id']}/comp", headers=ctx["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["advisory"] is True
    assert body["position"] in {"below", "at", "above"}
    # a different org cannot benchmark it
    assert client.get(f"/jobs/{req['id']}/comp", headers=ctx["other_headers"]).status_code == 404
```

Provide an `org_client` fixture in this file (or reuse a shared one) that: builds
the app with `make_services`, wraps it in `with TestClient(app) as client:` so the
lifespan sets `app.state.services`, issues an org API key, creates a candidate, and
exposes `grant_write()` + a second org's headers. Model it on the existing
matching/ledger API test fixtures.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_comp_api.py -v`
Expected: FAIL (404s — routes not registered).

- [ ] **Step 3: Implement the endpoints**

In `app/api/routes.py`, add imports:

```python
from app.comp import bands
from app.comp.schema import (
    CITY_TIERS, ROLE_FAMILIES, CompBandEstimate, CompBenchmark, SeniorityBand,
)
from app.ledger.schema import ObservedOffer
```

Add request models + handlers (near the other `org_router` ledger/job routes):

```python
class OfferSubmitRequest(BaseModel):
    candidate_id: str
    role_family: str
    seniority: SeniorityBand
    city_tier: str
    ctc_fixed: float = Field(ge=0)
    ctc_variable: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    offered_at: datetime

    @model_validator(mode="after")
    def _validate_vocab(self) -> "OfferSubmitRequest":
        if self.role_family not in ROLE_FAMILIES:
            raise ValueError(f"role_family must be one of {ROLE_FAMILIES}")
        if self.city_tier not in CITY_TIERS:
            raise ValueError(f"city_tier must be one of {CITY_TIERS}")
        return self


@org_router.post("/ledger/offers", response_model=ObservedOffer)
async def submit_offer(
    req: OfferSubmitRequest, request: Request, org_id: str = Depends(require_org)
) -> ObservedOffer:
    ledger = _services(request).ledger
    try:
        return ledger.submit_observed_offer(
            org_id=org_id, candidate_id=req.candidate_id, role_family=req.role_family,
            seniority=req.seniority.value, city_tier=req.city_tier,
            ctc_fixed=req.ctc_fixed, ctc_variable=req.ctc_variable,
            currency=req.currency, offered_at=req.offered_at,
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CompEstimateRequest(BaseModel):
    skills: tuple[str, ...] = ()
    title: Optional[str] = None
    years_experience: Optional[float] = Field(default=None, ge=0)
    location_tiers: Optional[tuple[str, ...]] = None
    remote: bool = False
    role_family: Optional[str] = None
    seniority: Optional[SeniorityBand] = None


@org_router.post("/comp/estimate", response_model=CompBandEstimate)
async def comp_estimate(
    body: CompEstimateRequest, request: Request, org_id: str = Depends(require_org)
) -> CompBandEstimate:
    services = _services(request)
    try:
        signal = bands.role_signal_from_input(
            skills=body.skills, title=body.title, years=body.years_experience,
            location_tiers=body.location_tiers, remote=body.remote,
            role_family=body.role_family, seniority=body.seniority, settings=services.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return services.comp.estimate(signal, org_id=org_id)


@org_router.get("/jobs/{req_id}/comp", response_model=CompBenchmark)
async def job_comp(
    req_id: str, request: Request, org_id: str = Depends(require_org)
) -> CompBenchmark:
    services = _services(request)
    req = services.jobs.get_requisition(org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    return services.comp.benchmark(req, org_id=org_id)
```

**Note:** `OfferSubmitRequest`'s `model_validator` raising `ValueError` yields
FastAPI's default 422, not 400. To get **400** for an invalid role_family/city_tier
(per the design), do NOT validate in the model; instead validate inside the handler
and raise `HTTPException(400)`. Replace the `@model_validator` with an explicit
check at the top of `submit_offer`:

```python
    if req.role_family not in ROLE_FAMILIES or req.city_tier not in CITY_TIERS:
        raise HTTPException(status_code=400, detail="invalid role_family or city_tier")
```

(Keep `SeniorityBand` as the typed field — an invalid seniority is a genuine 422
schema error, which is fine.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_comp_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_comp_api.py
git commit -m "feat(s52): org-plane /ledger/offers + /comp/estimate + /jobs/{id}/comp"
```

---

### Task 10: Docs (`COMP.md`) + smoke + ROADMAP + full-suite green

**Files:**
- Create: `COMP.md`
- Create: `scripts/smoke_s52.py`
- Modify: `docs/ROADMAP.md`
- Verify: full `pytest -q`

**Interfaces:** none (documentation + end-to-end verification).

- [ ] **Step 1: Write `COMP.md`**

A peer of `MATCHING.md`/`LEDGER.md`/`FEATURES.md`. Cover: the two homes
(`app/comp/` engine + `app/ledger/` observed_offers), the static prior (illustrative
seed, `comp_bands_path` override), role-signal resolution, the blend (total-CTC
basis, k-floor, shrinkage, confidence), the DPDP posture (§6 of the spec:
revocation-respecting inclusion + k-anonymity + de-identified aggregate +
`comp.aggregate` audit; no new consent purpose — documented residual), the three
endpoints, the `comp_*` config table, and the seams (real market data, comp-fit
match term, dedicated aggregation consent, observed quantiles).

- [ ] **Step 2: Write `scripts/smoke_s52.py`**

Model it on `scripts/smoke_s51.py` (uvicorn subprocess + HTTP via `httpx`/stdlib;
`with TestClient` is NOT used for smokes — smokes hit a real server). Steps, each
printing `OK`/`FAIL` and exiting non-zero on any failure:

```
1.  POST /comp/estimate {title:"Senior Backend Engineer", years:7} -> 200,
    sources==["static"], p25<p50<p75.
2.  Create org + key; create candidate(s).
3.  POST /ledger/offers before consent -> 403.
4.  Grant ledger_write; submit >= comp_min_observations (5) high offers
    (role backend_engineer/senior/metro) across distinct consented candidates -> 200 each.
5.  POST /comp/estimate same signal -> 200, sources==["static","observed"],
    p50 greater than step 1's p50, confidence > 0.30.
6.  POST /ledger/offers for a DIFFERENT role signal with < 5 offers -> estimate
    of that signal stays sources==["static"].
7.  Create a requisition with a low comp_band; GET /jobs/{id}/comp -> position=="below".
8.  Create a requisition whose comp_band brackets the estimate p50 -> position=="at".
9.  Revoke one candidate's grant -> re-estimate: n_observed drops (and if it falls
    below 5, sources back to ["static"]).
10. DPDP-erase one offered candidate -> re-estimate: that candidate's offer gone
    from the aggregate (n_observed decremented).
11. Cross-org GET /jobs/{id}/comp with a second org's key -> 404.
```

Exit 0 with `SMOKE OK` only if all pass.

- [ ] **Step 3: Run the smoke**

Run: `python scripts/smoke_s52.py`
Expected: all checks `OK`, `SMOKE OK`, exit 0. (Runs key-less — S5.2 has no LLM;
candidate ingestion uses the heuristic extractor floor.)

- [ ] **Step 4: Full suite**

Run: `pytest -q`
Expected: all green (623 prior + ~30 new). Investigate any failure before
proceeding; do not xfail.

- [ ] **Step 5: Update ROADMAP**

In `docs/ROADMAP.md`: flip S5.2 `[ ]` → `[x]` on the status board; update
"Current state"/"Next action" (S5.2 done; next is S5.3 thin employer dashboard);
add a session-log entry (delivered summary, new test count, smoke result).

- [ ] **Step 6: Commit**

```bash
git add COMP.md scripts/smoke_s52.py docs/ROADMAP.md
git commit -m "docs(s52): COMP.md + smoke_s52 + ROADMAP (S5.2 built)"
```

---

## After all tasks

Whole-branch self-review (superpowers:requesting-code-review), fix any
Critical/Important inline, then merge `s52-comp-intelligence` → main and delete the
branch (superpowers:finishing-a-development-branch).

## Self-Review (plan vs spec)

- **Spec §1 goal/non-goals:** static bands (Task 3), observed capture (Tasks 5–6),
  blend (Task 4), estimate+benchmark surfaces (Tasks 8–9). No comp-fit match term /
  no candidate surface / no LLM — none introduced. ✅
- **Spec §2 package split:** ledger owns the record (Tasks 5–7); `app/comp/` is a
  pure consumer (Tasks 2–4, 8). Layering constraint (ledger never imports comp)
  enforced via str fields + boundary validation. ✅
- **Spec §3 static bands + resolvers:** Task 3. Deviation logged (computed seed
  with full coverage replaces nearest-lower fallback; override still supported). ✅
- **Spec §4 observed_offers table/migration/consent-gated submit:** Tasks 5–6. ✅
- **Spec §5 blend (total-CTC basis, k-floor, shrinkage, p25/p75 relative spread,
  confidence):** Task 4, all formulas present. ✅
- **Spec §6 DPDP posture (revocation-respecting + k-anonymity + de-identified +
  comp.aggregate audit, no new purpose):** k-floor in Task 4; revocation-respecting
  + de-identified + audit in Task 7. ✅
- **Spec §7 config:** Task 1 (all knobs). ✅
- **Spec §8 endpoints:** Task 9 (all three, with 400/403/404 shapes). ✅
- **Spec §9 testing/smoke:** per-task unit tests + Task 10 smoke covering all six
  spec smoke scenarios. ✅
- **Type consistency:** `RoleSignal`, `CompCell`, `CompBandEstimate`,
  `CompBenchmark`, `ObservedOffer`, `ObservedOfferPoint`, and the store/service/
  bands/estimate signatures are used identically across tasks (verified against the
  Interfaces blocks). `seniority` crosses the ledger boundary as `str`
  (`.value`), a `SeniorityBand` everywhere in `app/comp/`. ✅
- **Placeholder scan:** no TBD/TODO; every code step has real code. ✅
