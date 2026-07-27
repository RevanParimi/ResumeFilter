# S4.3 Talent Search / Ranking API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, advisory talent-search endpoint that filters and ranks the materialized candidate pool (`ml_feature_vectors`) by a caller-supplied composite score, with per-feature explainability — never an auto-reject gate.

**Architecture:** Two pure modules (contracts + engine) mirroring `app/fabrication/risk.py` and `app/ledger/reputation.py` — no I/O, no clock, no store. One admin-plane HTTP endpoint (`POST /talent/search`, `X-API-Key`) that loads point-in-time vectors via the existing `FeatureStore.vectors_for_view(...)`, resolves feature specs from the registry, then runs filter → score → sort → limit. Consent is not re-applied: S4.2 already masked consent-tagged features at materialization, so a withheld feature is already null in the row.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, SQLAlchemy (read-only here), pytest. Fully offline tests (NullLLM / in-memory stores per `tests/conftest.py`).

## Global Constraints

- TDD, fully offline tests (NullLLM / in-memory stores); `pytest -q` green before merge.
- Advisory only — the endpoint narrows/orders; it never auto-rejects. `SearchResult.advisory` is always `True`.
- Consent-withheld or absent data must **never lower** a candidate's rank (drop-term + renormalize; report `coverage`).
- No new table, no migration, no LLM, no new candidate-linked data ⇒ no new DPDP erasure path.
- Reproducible normalization: ranged features use `FeatureSpec.valid_range`/category index (pool-independent); only range-less numerics fall back to pool min-max.
- Config: the one new tunable (`search_default_limit`) goes in `config.yaml` + `Settings`; config.yaml comments must stay ASCII (cp1252 read on Windows).
- No Claude co-author trailer in commits (repo convention).
- Branch: `s43-talent-search` (already created; spec committed as `24844eb`).

---

### Task 1: Ranking contracts

**Files:**
- Create: `app/features/ranking_schema.py`
- Test: `tests/test_ranking_schema.py`

**Interfaces:**
- Consumes: `FeatureValue` from `app.features.schema`.
- Produces: `FilterOp`, `SortDirection` (StrEnums); `FeatureFilter{feature:str, op:FilterOp, value:FilterValue|None}`; `RankingTerm{feature:str, weight:float>0, direction:SortDirection}`; `RankingSpec{terms:tuple[RankingTerm,...]}` (non-empty); `Contribution{feature:str, raw:FeatureValue, normalized:float, weight:float, weighted:float}`; `RankedCandidate{candidate_id:str, score:float, coverage:float, contributions:tuple[Contribution,...], missing:tuple[str,...]}`; `SearchResult{advisory:bool=True, as_of:datetime|None, view_name:str, view_version:int, pool_size:int, filtered_size:int, ranked:tuple[RankedCandidate,...]}`. `FilterValue = Union[float,int,bool,str,list]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking_schema.py
import pytest
from pydantic import ValidationError

from app.features.ranking_schema import (
    FeatureFilter, FilterOp, RankingSpec, RankingTerm, SearchResult, SortDirection,
)


def test_comparison_filter_requires_a_value():
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE)


def test_exists_filter_forbids_a_value():
    ok = FeatureFilter(feature="candidate.has_github", op=FilterOp.EXISTS)
    assert ok.value is None
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.has_github", op=FilterOp.EXISTS, value=True)


def test_in_filter_requires_a_list_and_scalar_ops_reject_lists():
    ok = FeatureFilter(feature="candidate.location_tier", op=FilterOp.IN, value=["metro", "tier_2"])
    assert ok.value == ["metro", "tier_2"]
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.location_tier", op=FilterOp.IN, value="metro")
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE, value=[5])


def test_ranking_term_weight_must_be_positive_and_spec_non_empty():
    with pytest.raises(ValidationError):
        RankingTerm(feature="candidate.years_experience", weight=0.0)
    with pytest.raises(ValidationError):
        RankingSpec(terms=())
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=1.0),))
    assert spec.terms[0].direction is SortDirection.HIGHER_BETTER


def test_search_result_is_advisory_by_default():
    r = SearchResult(view_name="core_v1", view_version=1, pool_size=0, filtered_size=0)
    assert r.advisory is True and r.ranked == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ranking_schema.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.features.ranking_schema'`.

- [ ] **Step 3: Write the contracts**

```python
# app/features/ranking_schema.py
"""Talent-search / ranking contracts (PI-4 / S4.3).

Pure, serializable request/result models + enums for the advisory ranking
engine. No I/O, no callables. The engine lives in ranking.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator

from app.features.schema import FeatureValue

FilterValue = Union[float, int, bool, str, list]


class FilterOp(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in_"
    NOT_IN = "not_in"
    EXISTS = "exists"
    MISSING = "missing"


class SortDirection(StrEnum):
    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"


_NO_VALUE_OPS = {FilterOp.EXISTS, FilterOp.MISSING}
_LIST_OPS = {FilterOp.IN, FilterOp.NOT_IN}


class FeatureFilter(BaseModel):
    feature: str
    op: FilterOp
    value: Optional[FilterValue] = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> "FeatureFilter":
        if self.op in _NO_VALUE_OPS:
            if self.value is not None:
                raise ValueError(f"{self.op.value} takes no value")
            return self
        if self.value is None:
            raise ValueError(f"{self.op.value} requires a value")
        if self.op in _LIST_OPS and not isinstance(self.value, list):
            raise ValueError(f"{self.op.value} requires a list value")
        if self.op not in _LIST_OPS and isinstance(self.value, list):
            raise ValueError(f"{self.op.value} does not take a list value")
        return self


class RankingTerm(BaseModel):
    feature: str
    weight: float = Field(gt=0.0)
    direction: SortDirection = SortDirection.HIGHER_BETTER


class RankingSpec(BaseModel):
    terms: tuple[RankingTerm, ...]

    @model_validator(mode="after")
    def _non_empty(self) -> "RankingSpec":
        if not self.terms:
            raise ValueError("ranking needs at least one term")
        return self


class Contribution(BaseModel):
    feature: str
    raw: FeatureValue
    normalized: float
    weight: float
    weighted: float


class RankedCandidate(BaseModel):
    candidate_id: str
    score: float
    coverage: float
    contributions: tuple[Contribution, ...] = ()
    missing: tuple[str, ...] = ()


class SearchResult(BaseModel):
    advisory: bool = True
    as_of: Optional[datetime] = None
    view_name: str
    view_version: int
    pool_size: int
    filtered_size: int
    ranked: tuple[RankedCandidate, ...] = ()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ranking_schema.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/ranking_schema.py tests/test_ranking_schema.py
git commit -m "feat(s43): ranking contracts (filters, ranking spec, search result)"
```

---

### Task 2: Pure normalization (`normalize_value`)

**Files:**
- Create: `app/features/ranking.py`
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: `FeatureSpec`, `FeatureDType`, `FeatureValue` from `app.features.schema`; `SortDirection` from `app.features.ranking_schema`.
- Produces: `normalize_value(spec: FeatureSpec, value: FeatureValue, *, direction: SortDirection = SortDirection.HIGHER_BETTER, pool: Optional[list] = None) -> Optional[float]` — maps a value to `[0,1]` (None passes through as None); ranged numerics use `valid_range`, range-less numerics use pool min-max, ordinals use category index, booleans 0/1; a non-ordinal categorical raises `ValueError`; `lower_better` returns `1 - norm`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking.py
import pytest

from app.features.ranking import normalize_value
from app.features.ranking_schema import SortDirection
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec

YEARS = FeatureSpec(name="candidate.years_experience", version=1, dtype=FeatureDType.NUMERIC,
                    source=FeatureSource.CANDIDATE, description="x", valid_range=(0.0, 60.0))
DEGREE = FeatureSpec(name="candidate.highest_degree_level", version=1, dtype=FeatureDType.ORDINAL,
                     source=FeatureSource.CANDIDATE, description="x",
                     categories=("none", "diploma", "bachelor", "master", "doctorate"))
GITHUB = FeatureSpec(name="candidate.has_github", version=1, dtype=FeatureDType.BOOLEAN,
                     source=FeatureSource.CANDIDATE, description="x")
COUNT = FeatureSpec(name="candidate.num_experiences", version=1, dtype=FeatureDType.INTEGER,
                    source=FeatureSource.CANDIDATE, description="x")  # no valid_range
CATEG = FeatureSpec(name="candidate.some_cat", version=1, dtype=FeatureDType.CATEGORICAL,
                    source=FeatureSource.CANDIDATE, description="x", categories=("a", "b"))


def test_numeric_uses_valid_range_and_clamps():
    assert normalize_value(YEARS, 30.0) == pytest.approx(0.5)
    assert normalize_value(YEARS, 999.0) == 1.0  # clamp above hi


def test_ordinal_uses_category_index():
    assert normalize_value(DEGREE, "master") == pytest.approx(3 / 4)
    assert normalize_value(DEGREE, "none") == 0.0


def test_boolean_and_none():
    assert normalize_value(GITHUB, True) == 1.0
    assert normalize_value(GITHUB, False) == 0.0
    assert normalize_value(GITHUB, None) is None


def test_lower_better_inverts():
    assert normalize_value(YEARS, 30.0, direction=SortDirection.LOWER_BETTER) == pytest.approx(0.5)
    assert normalize_value(YEARS, 0.0, direction=SortDirection.LOWER_BETTER) == 1.0


def test_range_less_numeric_falls_back_to_pool_min_max():
    # pool 2..10 -> value 6 normalizes to 0.5
    assert normalize_value(COUNT, 6, pool=[2, 4, 10]) == pytest.approx(0.5)
    # degenerate pool (all equal / singleton) -> neutral 0.5
    assert normalize_value(COUNT, 5, pool=[5]) == 0.5
    assert normalize_value(COUNT, 5, pool=None) == 0.5


def test_non_ordinal_categorical_is_not_rankable():
    with pytest.raises(ValueError):
        normalize_value(CATEG, "a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ranking.py -q`
Expected: FAIL with `ImportError: cannot import name 'normalize_value'`.

- [ ] **Step 3: Implement `normalize_value`**

```python
# app/features/ranking.py
"""Pure, deterministic talent-ranking engine (PI-4 / S4.3).

No I/O, no store, no wall clock (the app/fabrication/risk.py pattern). Operates
over already-materialized FeatureVector values + the FeatureSpecs the caller
resolves from the registry. Advisory: filters narrow, scoring orders; a
missing/consent-withheld value is dropped and never penalizes a candidate.
"""

from __future__ import annotations

from typing import Optional

from app.features.ranking_schema import SortDirection
from app.features.schema import FeatureDType, FeatureSpec, FeatureValue

_NUMERIC = {FeatureDType.NUMERIC, FeatureDType.INTEGER}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _minmax(x: float, lo: float, hi: float) -> float:
    return 0.5 if hi == lo else _clamp01((x - lo) / (hi - lo))


def normalize_value(
    spec: FeatureSpec,
    value: FeatureValue,
    *,
    direction: SortDirection = SortDirection.HIGHER_BETTER,
    pool: Optional[list] = None,
) -> Optional[float]:
    """Map ``value`` to [0,1]; None -> None (the missing-term signal)."""
    if value is None:
        return None

    if spec.dtype is FeatureDType.BOOLEAN:
        norm = 1.0 if value else 0.0
    elif spec.dtype is FeatureDType.ORDINAL:
        cats = spec.categories or ()
        if value not in cats:
            raise ValueError(f"{value!r} not a category of {spec.name!r}")
        norm = 0.0 if len(cats) <= 1 else cats.index(value) / (len(cats) - 1)
    elif spec.dtype in _NUMERIC:
        x = float(value)
        if spec.valid_range is not None:
            lo, hi = spec.valid_range
            norm = _minmax(x, lo, hi)
        else:
            vals = [float(v) for v in (pool or []) if v is not None]
            norm = 0.5 if len(vals) < 2 else _minmax(x, min(vals), max(vals))
    else:  # CATEGORICAL (non-ordinal)
        raise ValueError(f"categorical feature {spec.name!r} is not rankable")

    return 1.0 - norm if direction is SortDirection.LOWER_BETTER else norm
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ranking.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/ranking.py tests/test_ranking.py
git commit -m "feat(s43): pool-independent feature normalization"
```

---

### Task 3: Pure filtering (`apply_filters`)

**Files:**
- Modify: `app/features/ranking.py` (add `apply_filters`)
- Test: `tests/test_ranking_filters.py`

**Interfaces:**
- Consumes: `FeatureFilter`, `FilterOp` from `app.features.ranking_schema`; `FeatureVector` from `app.features.schema`; `normalize_value`'s module.
- Produces: `apply_filters(vectors: list[FeatureVector], filters: list[FeatureFilter], specs_by_name: dict[str, FeatureSpec]) -> list[FeatureVector]` — returns the subset matching every filter. Null value fails all comparison ops; only `missing` matches null, only `exists` matches a present value. Ordinal ordered comparisons (`gt`/`gte`/`lt`/`lte`) use the category index. Unknown feature → `KeyError`; an ordered op on a non-orderable dtype (boolean / non-ordinal categorical) → `ValueError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking_filters.py
from datetime import datetime, timezone

import pytest

from app.features.ranking import apply_filters
from app.features.ranking_schema import FeatureFilter, FilterOp
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec, FeatureVector

_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
DEGREE = FeatureSpec(name="candidate.highest_degree_level", version=1, dtype=FeatureDType.ORDINAL,
                     source=FeatureSource.CANDIDATE, description="x",
                     categories=("none", "diploma", "bachelor", "master", "doctorate"))
YEARS = FeatureSpec(name="candidate.years_experience", version=1, dtype=FeatureDType.NUMERIC,
                    source=FeatureSource.CANDIDATE, description="x", valid_range=(0.0, 60.0))
LOC = FeatureSpec(name="candidate.location_tier", version=1, dtype=FeatureDType.ORDINAL,
                  source=FeatureSource.CANDIDATE, description="x",
                  categories=("unknown", "tier_2", "metro"))
GITHUB = FeatureSpec(name="candidate.has_github", version=1, dtype=FeatureDType.BOOLEAN,
                     source=FeatureSource.CANDIDATE, description="x")
SPECS = {s.name: s for s in (DEGREE, YEARS, LOC, GITHUB)}


def _vec(cid, values):
    return FeatureVector(candidate_id=cid, as_of=_AS_OF, view_name="core_v1",
                         view_version=1, values=values)


def test_numeric_gte_filters():
    vs = [_vec("a", {"candidate.years_experience": 3.0}),
          _vec("b", {"candidate.years_experience": 8.0})]
    out = apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE, value=5)], SPECS)
    assert [v.candidate_id for v in out] == ["b"]


def test_ordinal_gte_uses_category_index():
    vs = [_vec("a", {"candidate.highest_degree_level": "bachelor"}),
          _vec("b", {"candidate.highest_degree_level": "master"}),
          _vec("c", {"candidate.highest_degree_level": "diploma"})]
    out = apply_filters(vs, [FeatureFilter(feature="candidate.highest_degree_level", op=FilterOp.GTE, value="bachelor")], SPECS)
    assert sorted(v.candidate_id for v in out) == ["a", "b"]


def test_in_and_eq_on_categorical():
    vs = [_vec("a", {"candidate.location_tier": "metro"}),
          _vec("b", {"candidate.location_tier": "tier_2"}),
          _vec("c", {"candidate.location_tier": "unknown"})]
    out = apply_filters(vs, [FeatureFilter(feature="candidate.location_tier", op=FilterOp.IN, value=["metro", "tier_2"])], SPECS)
    assert sorted(v.candidate_id for v in out) == ["a", "b"]


def test_missing_and_exists_and_null_fails_comparison():
    vs = [_vec("a", {"candidate.years_experience": 8.0}),
          _vec("b", {"candidate.years_experience": None})]
    assert [v.candidate_id for v in apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.EXISTS)], SPECS)] == ["a"]
    assert [v.candidate_id for v in apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.MISSING)], SPECS)] == ["b"]
    # a comparison against a null value never matches
    assert [v.candidate_id for v in apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE, value=1)], SPECS)] == ["a"]


def test_unknown_feature_raises_keyerror():
    with pytest.raises(KeyError):
        apply_filters([_vec("a", {})], [FeatureFilter(feature="nope.bad", op=FilterOp.EXISTS)], SPECS)


def test_ordered_op_on_boolean_raises_valueerror():
    vs = [_vec("a", {"candidate.has_github": True})]
    with pytest.raises(ValueError):
        apply_filters(vs, [FeatureFilter(feature="candidate.has_github", op=FilterOp.GT, value=True)], SPECS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ranking_filters.py -q`
Expected: FAIL with `ImportError: cannot import name 'apply_filters'`.

- [ ] **Step 3: Implement `apply_filters`**

Append to `app/features/ranking.py`:

```python
from app.features.ranking_schema import FeatureFilter, FilterOp  # add to existing imports
from app.features.schema import FeatureVector  # add to existing imports

_ORDER_OPS = {FilterOp.GT, FilterOp.GTE, FilterOp.LT, FilterOp.LTE}
_ORDERABLE = {FeatureDType.NUMERIC, FeatureDType.INTEGER, FeatureDType.ORDINAL}


def _order_key(spec: FeatureSpec, value):
    """Comparable key for ordered ops: category index for ordinal, else the value."""
    if spec.dtype is FeatureDType.ORDINAL:
        cats = spec.categories or ()
        if value not in cats:
            raise ValueError(f"{value!r} not a category of {spec.name!r}")
        return cats.index(value)
    return value


def _match(spec: FeatureSpec, value, op: FilterOp, target) -> bool:
    if op is FilterOp.EXISTS:
        return value is not None
    if op is FilterOp.MISSING:
        return value is None
    if value is None:
        return False
    if op is FilterOp.EQ:
        return value == target
    if op is FilterOp.NE:
        return value != target
    if op is FilterOp.IN:
        return value in target
    if op is FilterOp.NOT_IN:
        return value not in target
    # ordered ops
    if spec.dtype not in _ORDERABLE:
        raise ValueError(f"{op.value} is not valid on dtype {spec.dtype.value} ({spec.name!r})")
    lhs, rhs = _order_key(spec, value), _order_key(spec, target)
    if op is FilterOp.GT:
        return lhs > rhs
    if op is FilterOp.GTE:
        return lhs >= rhs
    if op is FilterOp.LT:
        return lhs < rhs
    return lhs <= rhs  # FilterOp.LTE


def apply_filters(
    vectors: list[FeatureVector],
    filters: list[FeatureFilter],
    specs_by_name: dict[str, FeatureSpec],
) -> list[FeatureVector]:
    out = list(vectors)
    for f in filters:
        spec = specs_by_name.get(f.feature)
        if spec is None:
            raise KeyError(f"unknown feature in filter: {f.feature}")
        out = [v for v in out if _match(spec, v.values.get(f.feature), f.op, f.value)]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ranking_filters.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/ranking.py tests/test_ranking_filters.py
git commit -m "feat(s43): dtype-aware feature filters"
```

---

### Task 4: Pure scoring (`score`)

**Files:**
- Modify: `app/features/ranking.py` (add `score`)
- Test: `tests/test_ranking_score.py`

**Interfaces:**
- Consumes: `RankingSpec`, `RankedCandidate`, `Contribution` from `app.features.ranking_schema`; `normalize_value`, `FeatureVector`.
- Produces: `score(vectors: list[FeatureVector], spec: RankingSpec, specs_by_name: dict[str, FeatureSpec]) -> list[RankedCandidate]` — weighted mean of present terms, renormalized by present weight; `coverage = present_weight / total_weight`; `missing` lists dropped terms; builds per-feature pools internally for the range-less fallback; sorts `score` desc then `candidate_id` asc. Unknown feature → `KeyError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking_score.py
from datetime import datetime, timezone

import pytest

from app.features.ranking import score
from app.features.ranking_schema import RankingSpec, RankingTerm
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec, FeatureVector

_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
YEARS = FeatureSpec(name="candidate.years_experience", version=1, dtype=FeatureDType.NUMERIC,
                    source=FeatureSource.CANDIDATE, description="x", valid_range=(0.0, 60.0))
REP = FeatureSpec(name="reputation.score", version=1, dtype=FeatureDType.NUMERIC,
                  source=FeatureSource.REPUTATION, description="x",
                  valid_range=(0.0, 1.0), nullable=False, requires_consent=True)
SPECS = {YEARS.name: YEARS, REP.name: REP}


def _vec(cid, values):
    return FeatureVector(candidate_id=cid, as_of=_AS_OF, view_name="core_v1",
                         view_version=1, values=values)


def test_weighted_mean_and_sort_desc():
    vs = [_vec("a", {"candidate.years_experience": 6.0}),   # 0.1
          _vec("b", {"candidate.years_experience": 30.0})]  # 0.5
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=1.0),))
    ranked = score(vs, spec, SPECS)
    assert [r.candidate_id for r in ranked] == ["b", "a"]
    assert ranked[0].score == pytest.approx(0.5) and ranked[0].coverage == 1.0
    assert ranked[0].contributions[0].normalized == pytest.approx(0.5)


def test_missing_term_renormalizes_and_reports_coverage():
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=0.6),
                              RankingTerm(feature="reputation.score", weight=0.4)))
    v = _vec("a", {"candidate.years_experience": 30.0, "reputation.score": None})
    r = score([v], spec, SPECS)[0]
    assert r.missing == ("reputation.score",)
    assert r.coverage == pytest.approx(0.6)          # 0.6 of 1.0 total weight had data
    assert r.score == pytest.approx(0.5)             # only the present term counts


def test_consent_withheld_is_never_penalized_below_a_present_low_value():
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=0.5),
                              RankingTerm(feature="reputation.score", weight=0.5)))
    withheld = _vec("withheld", {"candidate.years_experience": 30.0, "reputation.score": None})
    low = _vec("low", {"candidate.years_experience": 30.0, "reputation.score": 0.1})
    ranked = {r.candidate_id: r for r in score([withheld, low], spec, SPECS)}
    assert ranked["withheld"].score >= ranked["low"].score
    assert ranked["withheld"].score == pytest.approx(0.5)  # scored on the present term alone


def test_tie_break_is_candidate_id_asc():
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=1.0),))
    vs = [_vec("z", {"candidate.years_experience": 30.0}),
          _vec("a", {"candidate.years_experience": 30.0})]
    assert [r.candidate_id for r in score(vs, spec, SPECS)] == ["a", "z"]


def test_all_terms_missing_scores_zero_coverage_zero():
    spec = RankingSpec(terms=(RankingTerm(feature="reputation.score", weight=1.0),))
    r = score([_vec("a", {"reputation.score": None})], spec, SPECS)[0]
    assert r.score == 0.0 and r.coverage == 0.0 and r.missing == ("reputation.score",)


def test_unknown_ranking_feature_raises_keyerror():
    spec = RankingSpec(terms=(RankingTerm(feature="nope.bad", weight=1.0),))
    with pytest.raises(KeyError):
        score([_vec("a", {})], spec, SPECS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ranking_score.py -q`
Expected: FAIL with `ImportError: cannot import name 'score'`.

- [ ] **Step 3: Implement `score`**

Append to `app/features/ranking.py` (extend the `ranking_schema` import line to include `Contribution, RankedCandidate, RankingSpec`):

```python
from app.features.ranking_schema import (  # extend existing import
    Contribution, FeatureFilter, FilterOp, RankedCandidate, RankingSpec,
)


def score(
    vectors: list[FeatureVector],
    spec: RankingSpec,
    specs_by_name: dict[str, FeatureSpec],
) -> list[RankedCandidate]:
    # Per-feature pools (present values) feed the range-less-numeric fallback.
    pools = {
        term.feature: [
            v.values.get(term.feature) for v in vectors
            if v.values.get(term.feature) is not None
        ]
        for term in spec.terms
    }
    total_weight = sum(t.weight for t in spec.terms)

    results: list[RankedCandidate] = []
    for v in vectors:
        contributions: list[Contribution] = []
        missing: list[str] = []
        present_weight = 0.0
        acc = 0.0
        for term in spec.terms:
            fspec = specs_by_name.get(term.feature)
            if fspec is None:
                raise KeyError(f"unknown feature in ranking: {term.feature}")
            raw = v.values.get(term.feature)
            norm = normalize_value(fspec, raw, direction=term.direction, pool=pools[term.feature])
            if norm is None:
                missing.append(term.feature)
                continue
            weighted = norm * term.weight
            acc += weighted
            present_weight += term.weight
            contributions.append(Contribution(
                feature=term.feature, raw=raw, normalized=norm,
                weight=term.weight, weighted=weighted,
            ))
        composite = acc / present_weight if present_weight > 0 else 0.0
        coverage = present_weight / total_weight if total_weight > 0 else 0.0
        results.append(RankedCandidate(
            candidate_id=v.candidate_id, score=composite, coverage=coverage,
            contributions=tuple(contributions), missing=tuple(missing),
        ))
    results.sort(key=lambda r: (-r.score, r.candidate_id))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ranking_score.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/ranking.py tests/test_ranking_score.py
git commit -m "feat(s43): composite scoring (drop-term renormalize + coverage)"
```

---

### Task 5: `FeatureStore.latest_as_of` + `search_default_limit` config

**Files:**
- Modify: `app/features/store.py` (add `latest_as_of`)
- Modify: `app/core/config.py:227` (add `search_default_limit` after `feat_default_view`)
- Modify: `config.yaml:152` (add the `search_default_limit` line, ASCII comment)
- Test: `tests/test_feature_store.py` (append), `tests/test_ranking_config.py` (new)

**Interfaces:**
- Consumes: existing `FeatureVectorRow`, `as_utc`.
- Produces: `FeatureStore.latest_as_of(view_name: str, view_version: int) -> Optional[datetime]` (newest `as_of` present for the view/version as aware UTC, else `None`); `Settings.search_default_limit: int` (default 50, ge=1).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ranking_config.py
from app.core.config import Settings


def test_search_default_limit_default_and_bound():
    assert Settings(_env_file=None, openrouter_api_key="").search_default_limit == 50
```

Append to `tests/test_feature_store.py` (it already imports `datetime`/`timezone`,
`FeatureStore`, `LedgerStore`, `InMemoryReportStore`, `make_candidate_store`, and
defines `_settings()` + `_make_mv(cs, ls, rs)`):

```python
def test_latest_as_of_returns_newest_cut_or_none():
    from datetime import timedelta
    from app.features.materialize import MaterializedVector
    from app.features.schema import FeatureVector

    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, _ = _make_mv(cs, ls, rs)  # persists a candidate row (FK satisfied)
    assert fs.latest_as_of(view.name, view.version) is None

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = t1 + timedelta(days=30)
    for t in (t1, t2):
        fs.upsert_vector(MaterializedVector(
            vector=FeatureVector(candidate_id=cid, as_of=t, view_name=view.name,
                                 view_version=view.version, values={}, missing=()),
            consent_state={"allowed": True}, materialized_at=t))
    assert fs.latest_as_of(view.name, view.version) == t2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ranking_config.py tests/test_feature_store.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'search_default_limit'` and `AttributeError: 'FeatureStore' object has no attribute 'latest_as_of'`.

- [ ] **Step 3: Implement the config knob**

In `app/core/config.py`, immediately after the `feat_default_view` line (227):

```python
    # --- ML feature store (PI-4, S4.3): talent search / ranking ---------------
    # Default page size for POST /talent/search when the caller omits `limit`.
    search_default_limit: int = Field(default=50, ge=1)
```

In `config.yaml`, after the `feat_default_view` line (152), ASCII comment only:

```yaml
search_default_limit: 50        # default page size for POST /talent/search
```

- [ ] **Step 4: Implement `latest_as_of`**

Add to `FeatureStore` in `app/features/store.py`:

```python
    def latest_as_of(self, view_name: str, view_version: int) -> Optional[datetime]:
        """Newest materialized `as_of` for a view (aware UTC), or None if none."""
        with self._session_factory() as session:
            row = session.execute(
                select(FeatureVectorRow.as_of)
                .where(
                    FeatureVectorRow.view_name == view_name,
                    FeatureVectorRow.view_version == view_version,
                )
                .order_by(FeatureVectorRow.as_of.desc())
                .limit(1)
            ).scalar_one_or_none()
            return as_utc(row) if row is not None else None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ranking_config.py tests/test_feature_store.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/features/store.py app/core/config.py config.yaml tests/test_ranking_config.py tests/test_feature_store.py
git commit -m "feat(s43): FeatureStore.latest_as_of + search_default_limit knob"
```

---

### Task 6: Wire `Services.features`

**Files:**
- Modify: `app/services/__init__.py` (add `features` field + build it)
- Modify: `tests/conftest.py` (`make_services` builds a `FeatureStore` on the shared session factory)
- Test: `tests/test_services_features.py`

**Interfaces:**
- Consumes: `FeatureStore`, `build_feature_store` from `app.features.store`.
- Produces: `Services.features: FeatureStore`; `make_services(..., features=None)` defaulting to `FeatureStore(candidates._session_factory)` (shares the in-memory candidate DB so FK-linked vector rows insert).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services_features.py
from app.features.store import FeatureStore
from tests.conftest import make_services


def test_services_bundle_has_feature_store_sharing_candidate_db(settings):
    services = make_services(settings)
    assert isinstance(services.features, FeatureStore)
    # Shares the candidate DB session factory so FK-linked vectors persist.
    assert services.features._session_factory is services.candidates._session_factory
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services_features.py -q`
Expected: FAIL — `AttributeError: 'Services' object has no attribute 'features'`.

- [ ] **Step 3: Add the field + production wiring**

In `app/services/__init__.py`: add the import, the dataclass field, and the builder line.

```python
from app.features.store import FeatureStore, build_feature_store  # new import
```

```python
@dataclass
class Services:
    settings: Settings
    llm: LLMClient
    vectorstore: VectorStore
    github: GitHubService
    flywheel: Flywheel
    report_store: ReportStore
    candidates: CandidateStore
    ledger: LedgerStore
    features: FeatureStore  # new
```

```python
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=GitHubClient(settings),
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=build_candidate_store(settings),
        ledger=build_ledger_store(settings),
        features=build_feature_store(settings),  # new
    )
```

- [ ] **Step 4: Wire the test factory**

In `tests/conftest.py`, import `FeatureStore` and extend `make_services`:

```python
from app.features.store import FeatureStore  # new import near the other store imports
```

Add a `features` parameter and default, and pass it to the `Services(...)` constructor:

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
) -> Services:
    candidates = candidates or make_candidate_store()
    ledger = ledger or LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    features = features or FeatureStore(candidates._session_factory)
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
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services_features.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite (no regression from the new required field)**

Run: `pytest -q`
Expected: PASS — every `make_services`/`build_default_services` call now supplies `features`. If any direct `Services(...)` construction elsewhere fails for the missing field, add `features=...` there.

- [ ] **Step 7: Commit**

```bash
git add app/services/__init__.py tests/conftest.py tests/test_services_features.py
git commit -m "feat(s43): inject Services.features (FeatureStore) sharing candidate DB"
```

---

### Task 7: `POST /talent/search` endpoint

**Files:**
- Modify: `app/api/routes.py` (request model + handler + imports)
- Modify: `app/main.py:100-127` (add the route to the `root()` endpoint list)
- Test: `tests/test_talent_search_api.py`

**Interfaces:**
- Consumes: `Services.features` (`vectors_for_view`, `latest_as_of`); `get_feature_registry`, `default_view` from `app.features`; `apply_filters`, `score` from `app.features.ranking`; `FeatureFilter`, `RankingSpec`, `SearchResult` from `app.features.ranking_schema`; `require_api_key` (already on `router`).
- Produces: `POST /talent/search` → `SearchResult`. 200 always advisory; 400 on unknown feature / dtype-invalid op; 401 without the admin key; 422 on empty `ranking`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_talent_search_api.py
"""S4.3 talent-search HTTP surface — offline TestClient over injected stores."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidates.extractor import extract_profile
from app.features.materialize import MaterializedVector
from app.features.schema import FeatureVector
from app.main import create_app
from tests.conftest import make_services

_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _seed(services, tag, values):
    # Distinct email per tag => distinct candidates (no phone: identical phones
    # would merge via identity resolution). Feature values are set explicitly
    # below, so extraction quality is irrelevant — ingest only creates the FK row.
    text = (f"{tag} Kumar\nEmail: {tag}@example.com\n"
            "EXPERIENCE\n- Engineer, Acme (2020 - Present)\nSKILLS\nPython\n")
    result = await extract_profile(text, llm=services.llm, settings=services.settings)
    cid = services.candidates.ingest(result, text).candidate_id
    services.features.upsert_vector(MaterializedVector(
        vector=FeatureVector(candidate_id=cid, as_of=_AS_OF, view_name="core_v1",
                             view_version=1, values=values,
                             missing=tuple(k for k, v in values.items() if v is None)),
        consent_state={"allowed": True}, materialized_at=_AS_OF))
    return cid


@pytest.fixture
def api(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


def _search(client, **body):
    return client.post("/talent/search", json=body)


def test_ranks_desc_and_is_advisory(api):
    client, services = api
    ids = {}
    for tag, yrs in (("aaa", 2.0), ("bbb", 8.0), ("ccc", 5.0)):
        ids[tag] = asyncio.run(_seed(services, tag, {"candidate.years_experience": yrs}))
    resp = _search(client, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["advisory"] is True and body["pool_size"] == 3 and body["filtered_size"] == 3
    order = [r["candidate_id"] for r in body["ranked"]]
    assert order == [ids["bbb"], ids["ccc"], ids["aaa"]]
    assert body["ranked"][0]["contributions"][0]["feature"] == "candidate.years_experience"


def test_filter_narrows_pool(api):
    client, services = api
    for tag, yrs in (("aaa", 2.0), ("bbb", 8.0), ("ccc", 5.0)):
        asyncio.run(_seed(services, tag, {"candidate.years_experience": yrs}))
    resp = _search(
        client,
        filters=[{"feature": "candidate.years_experience", "op": "gte", "value": 5}],
        ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]},
    )
    body = resp.json()
    assert body["pool_size"] == 3 and body["filtered_size"] == 2


def test_limit_is_honored(api):
    client, services = api
    for tag, yrs in (("aaa", 2.0), ("bbb", 8.0)):
        asyncio.run(_seed(services, tag, {"candidate.years_experience": yrs}))
    resp = _search(client, limit=1, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    assert len(resp.json()["ranked"]) == 1


def test_unknown_feature_is_400(api):
    client, _ = api
    resp = _search(client, ranking={"terms": [{"feature": "nope.bad", "weight": 1.0}]})
    assert resp.status_code == 400


def test_empty_ranking_is_422(api):
    client, _ = api
    assert _search(client, ranking={"terms": []}).status_code == 422


def test_empty_pool_when_nothing_materialized_is_200_advisory(api):
    client, _ = api
    resp = _search(client, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    body = resp.json()
    assert resp.status_code == 200 and body["advisory"] is True
    assert body["pool_size"] == 0 and body["ranked"] == []


def test_requires_admin_key(settings, flywheel):
    locked = settings.model_copy(update={"api_auth_key": SecretStr("s3cret")})
    services = make_services(locked, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        body = {"ranking": {"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]}}
        assert client.post("/talent/search", json=body).status_code == 401
        assert client.post("/talent/search", json=body, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_as_of_selects_the_cut(api):
    client, services = api
    # one candidate materialized only at _AS_OF; a query at a different cut sees an empty pool
    asyncio.run(_seed(services, "aaa", {"candidate.years_experience": 8.0}))
    other = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    resp = _search(client, as_of=other, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    assert resp.json()["pool_size"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_talent_search_api.py -q`
Expected: FAIL — 404 on `POST /talent/search` (route not defined).

- [ ] **Step 3: Add imports to `app/api/routes.py`**

Near the existing feature/ledger imports:

```python
from app.features import default_view, get_feature_registry
from app.features.ranking import apply_filters, score
from app.features.ranking_schema import FeatureFilter, RankingSpec, SearchResult
```

- [ ] **Step 4: Add the request model + handler**

Place after the ledger endpoints, before `get_report` (still on the admin `router`):

```python
class TalentSearchRequest(BaseModel):
    """Advisory talent search over materialized feature vectors (admin plane).

    `ranking` is required and non-empty. `view_name`/`view_version` default to the
    materialized default view; `as_of` defaults to its newest cut. Only the
    features referenced in `filters`/`ranking` are validated against the registry.
    """

    ranking: RankingSpec
    filters: list[FeatureFilter] = Field(default_factory=list)
    view_name: Optional[str] = None
    view_version: Optional[int] = None
    as_of: Optional[datetime] = None
    limit: Optional[int] = Field(default=None, ge=1)


@router.post("/talent/search", response_model=SearchResult)
async def talent_search(req: TalentSearchRequest, request: Request) -> SearchResult:
    """Filter + rank the materialized pool by a composite score. Advisory: it
    narrows and orders, never auto-rejects. Consent was masked at materialization
    (S4.2), so a withheld feature is already null and simply drops out of scoring."""
    services = _services(request)
    registry = get_feature_registry()

    # Resolve specs per referenced feature; an unknown name is a 400.
    referenced = {t.feature for t in req.ranking.terms} | {f.feature for f in req.filters}
    specs_by_name = {}
    for name in referenced:
        try:
            specs_by_name[name] = registry.get(name).spec
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    view_name = req.view_name or services.settings.feat_default_view
    view_version = (
        req.view_version
        if req.view_version is not None
        else default_view(registry, settings=services.settings).version
    )
    as_of = req.as_of or services.features.latest_as_of(view_name, view_version)

    pool = (
        services.features.vectors_for_view(view_name, view_version, as_of=as_of)
        if as_of is not None
        else []
    )
    vectors = [mv.vector for mv in pool]

    try:
        filtered = apply_filters(vectors, req.filters, specs_by_name)
        ranked = score(filtered, req.ranking, specs_by_name)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    limit = req.limit or services.settings.search_default_limit
    return SearchResult(
        advisory=True,
        as_of=as_of,
        view_name=view_name,
        view_version=view_version,
        pool_size=len(vectors),
        filtered_size=len(filtered),
        ranked=tuple(ranked[:limit]),
    )
```

- [ ] **Step 5: List the route in `root()`**

In `app/main.py`, add `"POST /talent/search",` to the `endpoints` list (after the ledger entries).

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_talent_search_api.py -q`
Expected: PASS (8 tests).

- [ ] **Step 7: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_talent_search_api.py
git commit -m "feat(s43): POST /talent/search admin endpoint over ml_feature_vectors"
```

---

### Task 8: Docs + smoke

**Files:**
- Modify: `FEATURES.md` (add an S4.3 section)
- Create: `scripts/smoke_s43.py`
- (No test file — this task is docs + an end-to-end smoke run.)

**Interfaces:**
- Consumes: everything above, over HTTP + direct stores (the `scripts/smoke_s42.py` pattern).
- Produces: `scripts/smoke_s43.py` returning exit 0 with `SMOKE OK`.

- [ ] **Step 1: Write the smoke script**

```python
# scripts/smoke_s43.py
"""S4.3 smoke: boot uvicorn on a migrated scratch DB, POST three fixture resumes
(one consent-withheld), materialize + persist their core_v1 vectors directly, then
exercise POST /talent/search over HTTP: a ranking with visible contributions, a
filter that narrows the pool, and proof the consent-withheld candidate is ranked
(reduced coverage) not penalized to the bottom. LLM-free. Run from the repo root:
python scripts/smoke_s43.py
"""

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.candidates.store import build_candidate_store
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.store import build_feature_store
from app.ledger.store import build_ledger_store
from app.services.report_store import build_report_store

PORT = 8043
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

# Three resumes with distinct emails (no identity merge) and different experience.
RESUMES = {
    "sr": ("Sr Dev\nEmail: sr@example.com\nEXPERIENCE\n- Engineer, Acme (2013 - Present)\nSKILLS\nPython\n"),
    "mid": ("Mid Dev\nEmail: mid@example.com\nEXPERIENCE\n- Engineer, Acme (2019 - Present)\nSKILLS\nPython\n"),
    "jr": ("Jr Dev\nEmail: jr@example.com\nEXPERIENCE\n- Engineer, Acme (2023 - Present)\nSKILLS\nPython\n"),
}


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s43.db").as_posix()
    reports = (scratch / "reports.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": reports,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    admin_h = {"X-API-Key": ADMIN}
    ids = {}
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1
            for tag, text in RESUMES.items():
                ids[tag] = c.post("/candidates", json={"resume_text": text},
                                  headers=admin_h).json()["candidate_id"]
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    settings = Settings(_env_file=None, openrouter_api_key="", candidates_db_url=url,
                        report_db_path=reports, vectorstore_backend="memory")
    cs, ls, rs = build_candidate_store(settings), build_ledger_store(settings), build_report_store(settings)
    fs = build_feature_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)
    now = datetime.now(timezone.utc)

    # No consent granted for anyone -> reputation.* / ledger.* materialize masked.
    for cid in ids.values():
        mv = materialize_candidate(cid, view=view, registry=reg, as_of=now,
                                   candidate_store=cs, report_store=rs, ledger_store=ls)
        fs.upsert_vector(mv)

    # Re-boot uvicorn against the now-populated DB and search over HTTP.
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy (2nd boot)")
                return 1

            ranking = {"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]}
            ranked = c.post("/talent/search", json={"ranking": ranking}, headers=admin_h).json()
            order = [r["candidate_id"] for r in ranked["ranked"]]

            filt = c.post("/talent/search", json={
                "filters": [{"feature": "candidate.years_experience", "op": "gte", "value": 6}],
                "ranking": ranking,
            }, headers=admin_h).json()

            # A ranking that WOULD reward reputation: consent-withheld candidates
            # must still be ranked (reputation dropped), not pushed to the bottom.
            rep_ranking = {"terms": [
                {"feature": "candidate.years_experience", "weight": 0.5},
                {"feature": "reputation.score", "weight": 0.5},
            ]}
            rep = c.post("/talent/search", json={"ranking": rep_ranking}, headers=admin_h).json()
            rep_by_id = {r["candidate_id"]: r for r in rep["ranked"]}
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    checks = {
        "advisory always true": ranked["advisory"] is True,
        "pool has all three": ranked["pool_size"] == 3,
        "ranked senior -> mid -> junior": order == [ids["sr"], ids["mid"], ids["jr"]],
        "top has a contribution": bool(ranked["ranked"][0]["contributions"]),
        "filter narrows to the two most experienced": filt["filtered_size"] == 2,
        "consent-withheld still ranked (reputation dropped)":
            len(rep["ranked"]) == 3,
        "withheld reputation reduces coverage, not membership":
            all(r["coverage"] < 1.0 and "reputation.score" in r["missing"]
                for r in rep["ranked"]),
        "withheld senior still ranks first on present terms":
            rep["ranked"][0]["candidate_id"] == ids["sr"],
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke script**

Run: `python scripts/smoke_s43.py`
Expected: every check `OK`, final line `SMOKE OK`, exit 0. (Runs key-less on the heuristic extractor; a live OpenRouter key is not required.)

> If `candidate.years_experience` comes back null on the heuristic path for these short fixtures (breaking the ordering checks), enrich the fixture resumes with clearer `EXPERIENCE` date ranges until `years_experience` is populated — the ranking logic is already unit-tested; the smoke only needs a populated, ordered pool.

- [ ] **Step 3: Write the FEATURES.md S4.3 section**

Append an `## S4.3 — Talent search / ranking` section to `FEATURES.md` covering: the two pure modules (`ranking_schema.py` contracts, `ranking.py` engine); the admin-plane `POST /talent/search` endpoint and its request/response; **the consent story** (no re-application at query time — vectors were masked at S4.2 materialization on the network opt-in basis, admin plane keeps this consistent, no new disclosure surface); normalization (`valid_range`/category-index, pool min-max fallback for range-less counts); drop-term + renormalize + `coverage` so withheld/absent data never penalizes; point-in-time (`as_of` selects the cut); DPDP (no new table/erasure path); and the `search_default_limit` knob. Mirror the depth/length of the existing S4.2 section.

- [ ] **Step 4: Commit**

```bash
git add FEATURES.md scripts/smoke_s43.py
git commit -m "docs(s43): FEATURES.md S4.3 section + smoke_s43 (search/rank over HTTP)"
```

---

## Final verification (after all tasks)

- [ ] Run the full suite: `pytest -q` — expect green (~529 → ~560 tests).
- [ ] Run the smoke: `python scripts/smoke_s43.py` — expect `SMOKE OK`, exit 0.
- [ ] Whole-branch review (superpowers:requesting-code-review) before merge.
- [ ] Update `docs/ROADMAP.md` (status board S4.3 → `[x]`, "Current state", session log) and merge per the sprint workflow. Next: S4.4 (training-set export).

## Self-review notes (plan author)

- **Spec coverage:** contracts (T1) · normalization D2 (T2) · filters (T3) · scoring D3 + coverage (T4) · `latest_as_of` + config (T5) · `Services.features` wiring (T6) · admin endpoint D1 + consent/point-in-time/DPDP behavior (T7) · docs + smoke incl. consent-withheld-not-penalized (T8). All spec §4–§8 items map to a task.
- **Type consistency:** `normalize_value(spec, value, *, direction, pool)`, `apply_filters(vectors, filters, specs_by_name)`, `score(vectors, spec, specs_by_name)`, `FeatureStore.latest_as_of(view_name, view_version)`, `Services.features`, `TalentSearchRequest`/`SearchResult` are used with identical signatures across T2–T7.
- **Consent invariant** is enforced structurally (S4.2 masks; S4.3 only reads) and asserted behaviorally in T4 (`test_consent_withheld_is_never_penalized...`) and T8 smoke — not left as prose.
