# S4.1 Feature Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned, in-code feature registry over candidate + depth +
fabrication + ledger data — the definition/compute-contract layer PI-4's later
sprints (materialization, ranking, training export) consume.

**Architecture:** A new pure package `app/features/` mirroring
`app/domains/`: `@register_feature` decorates pure extractor functions into a
module-global `FeatureRegistry`. `FeatureSpec` is serializable metadata;
`FeatureContext` is a per-candidate point-in-time snapshot; a `FeatureView`
(`core_v1`) pins feature versions; `compute_view` yields a `FeatureVector`. A
thin `build_context` assembles the snapshot from the existing stores. No
migration, no HTTP, no LLM this sprint.

**Tech Stack:** Python 3.12, pydantic v2, dataclasses, StrEnum. Tests: pytest
(fully offline). No new dependencies.

## Global Constraints

- **Advisory only, never auto-reject.** Features are ML inputs; nothing here
  changes a verdict, depth score, or gates a candidate.
- **Deterministic, LLM-free.** Every extractor is a pure function of
  `FeatureContext`; no I/O, no `datetime.now()`, no store access inside an
  extractor (only `build_context` touches stores).
- **TDD, fully offline.** Write the failing test first; `pytest -q` green before
  each commit. Use the in-memory store helpers from `tests/conftest.py`.
- **No migration, no new table** (values/persistence are S4.2); **no HTTP
  endpoint** (serving is S4.3); **no labels/outcomes** (S4.4).
- **Ledger/reputation features carry `requires_consent=True`** and source
  `LEDGER`/`REPUTATION`; enforcement is S4.2/S4.3, not this sprint.
- **Config comments must be ASCII** (`config.yaml` is read as cp1252 on Windows —
  no em-dashes/curly quotes).
- **No `Co-Authored-By` trailer in commits** (clean history — user preference).
- **Ordinal `categories` are ordered least→greatest with the insufficient/
  unknown sentinel at index 0**; the extractor returns the band string verbatim.

---

### Task 1: FeatureSpec contract + dtype/source enums

**Files:**
- Create: `app/features/__init__.py` (empty for now — filled in Task 3)
- Create: `app/features/schema.py`
- Test: `tests/test_feature_schema.py`

**Interfaces:**
- Produces: `FeatureDType(StrEnum)`, `FeatureSource(StrEnum)`, `FeatureValue`
  type alias (`float | int | bool | str | None`), and
  `FeatureSpec` (frozen dataclass) with `to_dict()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_schema.py
import pytest
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec


def _spec(**kw):
    base = dict(
        name="candidate.years_experience", version=1,
        dtype=FeatureDType.NUMERIC, source=FeatureSource.CANDIDATE,
        description="Years of experience.",
    )
    base.update(kw)
    return FeatureSpec(**base)


def test_valid_numeric_spec_roundtrips():
    s = _spec(valid_range=(0.0, 60.0))
    assert s.name == "candidate.years_experience"
    d = s.to_dict()
    assert d["dtype"] == "numeric" and d["valid_range"] == [0.0, 60.0]
    assert d["requires_consent"] is False


def test_bad_name_rejected():
    with pytest.raises(ValueError):
        _spec(name="BadName")           # no namespace, uppercase
    with pytest.raises(ValueError):
        _spec(name="candidate..x")


def test_version_and_description_bounds():
    with pytest.raises(ValueError):
        _spec(version=0)
    with pytest.raises(ValueError):
        _spec(description="   ")


def test_valid_range_only_numeric():
    with pytest.raises(ValueError):
        _spec(dtype=FeatureDType.BOOLEAN, valid_range=(0.0, 1.0))


def test_categorical_requires_categories_and_ordering():
    with pytest.raises(ValueError):
        _spec(dtype=FeatureDType.ORDINAL)                 # missing categories
    with pytest.raises(ValueError):
        _spec(dtype=FeatureDType.NUMERIC, categories=("a", "b"))  # forbidden
    ok = _spec(dtype=FeatureDType.ORDINAL, categories=("none", "bachelor"))
    assert ok.categories == ("none", "bachelor")


def test_consent_source_coherence():
    # ledger/reputation source MUST set requires_consent
    with pytest.raises(ValueError):
        _spec(source=FeatureSource.LEDGER)
    # requires_consent MUST come from a ledger/reputation source
    with pytest.raises(ValueError):
        _spec(requires_consent=True)
    ok = _spec(source=FeatureSource.REPUTATION, requires_consent=True)
    assert ok.requires_consent is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feature_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: app.features.schema`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/schema.py
"""Feature-registry contracts (PI-4 / S4.1).

Pure, serializable definitions of ML features over candidate + eval + ledger
data. No I/O, no LLM. A FeatureSpec is metadata; the extractor callable lives
beside it in the registry (registry.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional, Union

FeatureValue = Union[float, int, bool, str, None]


class FeatureDType(StrEnum):
    NUMERIC = "numeric"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"


class FeatureSource(StrEnum):
    CANDIDATE = "candidate"
    DEPTH = "depth"
    FABRICATION = "fabrication"
    LEDGER = "ledger"
    REPUTATION = "reputation"


_CONSENT_SOURCES = {FeatureSource.LEDGER, FeatureSource.REPUTATION}
_NUMERIC = {FeatureDType.NUMERIC, FeatureDType.INTEGER}
_CATEGORICAL = {FeatureDType.CATEGORICAL, FeatureDType.ORDINAL}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class FeatureSpec:
    """Serializable metadata for one feature definition (no callable)."""

    name: str
    version: int
    dtype: FeatureDType
    source: FeatureSource
    description: str
    nullable: bool = True
    requires_consent: bool = False
    valid_range: Optional[tuple[float, float]] = None
    categories: Optional[tuple[str, ...]] = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(
                f"feature name must be '<namespace>.<snake_case>': {self.name!r}"
            )
        if self.version < 1:
            raise ValueError(f"feature version must be >= 1: {self.version}")
        if not self.description.strip():
            raise ValueError(f"feature {self.name!r} needs a non-empty description")
        if self.valid_range is not None:
            if self.dtype not in _NUMERIC:
                raise ValueError(
                    f"valid_range only valid for numeric dtypes: {self.name!r}"
                )
            lo, hi = self.valid_range
            if hi < lo:
                raise ValueError(f"valid_range hi < lo: {self.name!r}")
        if self.dtype in _CATEGORICAL and not self.categories:
            raise ValueError(f"{self.dtype} feature needs categories: {self.name!r}")
        if self.dtype not in _CATEGORICAL and self.categories is not None:
            raise ValueError(
                f"categories only valid for categorical/ordinal: {self.name!r}"
            )
        if self.requires_consent and self.source not in _CONSENT_SOURCES:
            raise ValueError(
                f"requires_consent implies a ledger/reputation source: {self.name!r}"
            )
        if self.source in _CONSENT_SOURCES and not self.requires_consent:
            raise ValueError(
                f"ledger/reputation feature must set requires_consent: {self.name!r}"
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "dtype": self.dtype.value,
            "source": self.source.value,
            "description": self.description,
            "nullable": self.nullable,
            "requires_consent": self.requires_consent,
            "valid_range": list(self.valid_range) if self.valid_range else None,
            "categories": list(self.categories) if self.categories else None,
            "tags": list(self.tags),
        }
```

Also create an empty `app/features/__init__.py` (one line docstring is fine).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_feature_schema.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/__init__.py app/features/schema.py tests/test_feature_schema.py
git commit -m "feat(s41): FeatureSpec contract + dtype/source enums"
```

---

### Task 2: FeatureContext, FeatureView, FeatureVector

**Files:**
- Modify: `app/features/schema.py` (append)
- Test: `tests/test_feature_schema.py` (append)

**Interfaces:**
- Consumes: `FeatureValue` (Task 1); `CandidateProfile` (`app.candidates.schema`),
  `Report` (`app.schemas.report`), `InterviewRecord`/`CodingRoundResult`/
  `ReputationAssessment` (`app.ledger.schema`), `assess_reputation`
  (`app.ledger.reputation`).
- Produces: `FeatureContext` (dataclass, cached `reputation` property),
  `FeatureView` (frozen dataclass, `resolve(registry)`), `FeatureVector`
  (pydantic model).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_schema.py  (append)
from datetime import datetime, timezone
from app.features.schema import FeatureContext, FeatureVector, FeatureView


def test_context_reputation_is_cached_and_uses_as_of():
    ctx = FeatureContext(candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    rep_a = ctx.reputation
    rep_b = ctx.reputation
    assert rep_a is rep_b                      # memoized
    assert rep_a.band.value == "insufficient_data"   # no records -> prior


def test_feature_vector_shape():
    fv = FeatureVector(
        candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        view_name="core_v1", view_version=1,
        values={"candidate.num_skills": 3, "candidate.max_cgpa_10": None},
        missing=("candidate.max_cgpa_10",),
    )
    assert fv.values["candidate.num_skills"] == 3
    assert fv.missing == ("candidate.max_cgpa_10",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feature_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'FeatureContext'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/schema.py  (append)
from dataclasses import field
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.candidates.schema import CandidateProfile
from app.ledger.reputation import assess_reputation
from app.ledger.schema import (
    CodingRoundResult,
    InterviewRecord,
    ReputationAssessment,
)
from app.schemas.report import Report

if TYPE_CHECKING:  # avoid a schema<-registry import cycle
    from app.features.registry import FeatureRegistry, RegisteredFeature


@dataclass
class FeatureContext:
    """Read-only per-candidate snapshot (only data visible at ``as_of``).

    Read-only by convention: extractors must treat it as immutable and read
    nothing else — no store, no wall clock. Point-in-time slicing is S4.2's
    job; S4.1 assembles at ``as_of = now``.
    """

    candidate_id: str
    as_of: datetime
    profile: Optional[CandidateProfile] = None
    report: Optional[Report] = None
    interview_records: tuple[InterviewRecord, ...] = ()
    coding_rounds: tuple[CodingRoundResult, ...] = ()

    @cached_property
    def reputation(self) -> ReputationAssessment:
        """Advisory reputation over this snapshot, dated to ``as_of`` (neutral
        reliability in S4.1). Shared by all reputation.* features."""
        return assess_reputation(
            list(self.interview_records),
            list(self.coding_rounds),
            now=self.as_of,
        )


@dataclass(frozen=True)
class FeatureView:
    """A named, versioned bundle pinning exact ``(feature_name, version)`` pairs
    so a materialization/training run is reproducible."""

    name: str
    version: int
    members: tuple[tuple[str, int], ...]

    def resolve(self, registry: "FeatureRegistry") -> list["RegisteredFeature"]:
        return [registry.get(n, version=v) for n, v in self.members]


class FeatureVector(BaseModel):
    """Computed values for one context under one view (the row S4.2 persists)."""

    candidate_id: str
    as_of: datetime
    view_name: str
    view_version: int
    values: dict[str, FeatureValue] = Field(default_factory=dict)
    missing: tuple[str, ...] = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_feature_schema.py -q`
Expected: PASS (8 tests total in the file).

- [ ] **Step 5: Commit**

```bash
git add app/features/schema.py tests/test_feature_schema.py
git commit -m "feat(s41): FeatureContext + FeatureView + FeatureVector contracts"
```

---

### Task 3: FeatureRegistry + @register_feature + value validation

**Files:**
- Create: `app/features/registry.py`
- Modify: `app/features/__init__.py` (public API)
- Create: `app/features/definitions/__init__.py` (empty placeholder — filled Tasks 4-7)
- Test: `tests/test_feature_registry.py`

**Interfaces:**
- Consumes: everything from `schema.py`.
- Produces: `RegisteredFeature` (frozen dataclass `spec`, `fn`),
  `FeatureRegistry` (`register`, `get`, `latest_version`, `names`, `specs`,
  `compute_one`, `compute_view`, `manifest`, `manifest_json`),
  `register_feature(**kw)` decorator, `_register(spec, fn, registry=None)`,
  `latest_view(registry, *, name, version)`, module-global `_DEFAULT_REGISTRY`.
  `app.features.get_feature_registry()` and `default_view(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_registry.py
from datetime import datetime, timezone
import pytest
from app.features.schema import (
    FeatureContext, FeatureDType, FeatureSource, FeatureSpec, FeatureView,
)
from app.features.registry import FeatureRegistry, _register, latest_view


def _ctx():
    return FeatureContext(candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))


def _num_spec(name="candidate.x", version=1, **kw):
    return FeatureSpec(name=name, version=version, dtype=FeatureDType.NUMERIC,
                       source=FeatureSource.CANDIDATE, description="x", **kw)


def test_register_get_latest_and_collision():
    reg = FeatureRegistry()
    _register(_num_spec(version=1), lambda c: 1.0, registry=reg)
    _register(_num_spec(version=2), lambda c: 2.0, registry=reg)
    assert reg.latest_version("candidate.x") == 2
    assert reg.get("candidate.x").spec.version == 2       # latest
    assert reg.get("candidate.x", version=1).spec.version == 1
    with pytest.raises(ValueError):
        _register(_num_spec(version=2), lambda c: 9.0, registry=reg)  # dup key
    with pytest.raises(KeyError):
        reg.get("candidate.missing")


def test_compute_one_validates_output():
    reg = FeatureRegistry()
    _register(_num_spec(name="candidate.r", valid_range=(0.0, 1.0)),
              lambda c: 5.0, registry=reg)                # out of range
    with pytest.raises(ValueError):
        reg.compute_one("candidate.r", _ctx())

    _register(FeatureSpec(name="candidate.b", version=1, dtype=FeatureDType.BOOLEAN,
                          source=FeatureSource.CANDIDATE, description="b", nullable=False),
              lambda c: None, registry=reg)               # None but not nullable
    with pytest.raises(ValueError):
        reg.compute_one("candidate.b", _ctx())

    _register(FeatureSpec(name="candidate.o", version=1, dtype=FeatureDType.ORDINAL,
                          source=FeatureSource.CANDIDATE, description="o",
                          categories=("none", "high")),
              lambda c: "medium", registry=reg)           # not a category
    with pytest.raises(ValueError):
        reg.compute_one("candidate.o", _ctx())


def test_integer_coerces_integral_float():
    reg = FeatureRegistry()
    _register(FeatureSpec(name="candidate.n", version=1, dtype=FeatureDType.INTEGER,
                          source=FeatureSource.CANDIDATE, description="n"),
              lambda c: 3.0, registry=reg)
    out = reg.compute_one("candidate.n", _ctx())
    assert out == 3 and isinstance(out, int)


def test_compute_view_collects_missing_and_manifest_sorted():
    reg = FeatureRegistry()
    _register(_num_spec(name="candidate.a"), lambda c: 1.0, registry=reg)
    _register(_num_spec(name="candidate.z"), lambda c: None, registry=reg)  # nullable default
    view = latest_view(reg, name="core_v1", version=1)
    fv = reg.compute_view(view, _ctx())
    assert fv.values["candidate.a"] == 1.0
    assert fv.missing == ("candidate.z",)
    assert [s["name"] for s in reg.manifest()] == ["candidate.a", "candidate.z"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feature_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: app.features.registry`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/registry.py
"""The feature registry (PI-4 / S4.1).

Mirrors app/domains/base.py: a module-global registry + a decorator. Extractors
are pure ``FeatureContext -> FeatureValue``; ``compute_one`` validates every
output against its spec so an out-of-contract value is a loud bug, never a
silent clamp.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from app.features.schema import (
    FeatureContext,
    FeatureDType,
    FeatureSource,
    FeatureSpec,
    FeatureValue,
    FeatureVector,
    FeatureView,
)


@dataclass(frozen=True)
class RegisteredFeature:
    spec: FeatureSpec
    fn: Callable[[FeatureContext], FeatureValue]


def _check_range(spec: FeatureSpec, value: float) -> None:
    if spec.valid_range is not None:
        lo, hi = spec.valid_range
        if value < lo or value > hi:
            raise ValueError(
                f"feature {spec.name!r} value {value} outside {spec.valid_range}"
            )


def _validate_value(spec: FeatureSpec, value: FeatureValue) -> FeatureValue:
    if value is None:
        if not spec.nullable:
            raise ValueError(f"feature {spec.name!r} returned None but is not nullable")
        return None
    if spec.dtype is FeatureDType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError(f"feature {spec.name!r} expected bool, got {value!r}")
        return value
    if spec.dtype is FeatureDType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {spec.name!r} expected int, got {value!r}")
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError(f"feature {spec.name!r} expected integral, got {value!r}")
            value = int(value)
        _check_range(spec, value)
        return value
    if spec.dtype is FeatureDType.NUMERIC:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {spec.name!r} expected numeric, got {value!r}")
        value = float(value)
        _check_range(spec, value)
        return value
    # CATEGORICAL / ORDINAL
    if not isinstance(value, str):
        raise ValueError(f"feature {spec.name!r} expected str category, got {value!r}")
    if spec.categories and value not in spec.categories:
        raise ValueError(
            f"feature {spec.name!r} value {value!r} not in {spec.categories}"
        )
    return value


class FeatureRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int], RegisteredFeature] = {}

    def register(self, spec: FeatureSpec, fn: Callable[[FeatureContext], FeatureValue]) -> None:
        key = (spec.name, spec.version)
        if key in self._by_key:
            raise ValueError(f"feature already registered: {spec.name} v{spec.version}")
        self._by_key[key] = RegisteredFeature(spec, fn)

    def latest_version(self, name: str) -> int:
        versions = [v for (n, v) in self._by_key if n == name]
        if not versions:
            raise KeyError(f"unknown feature {name!r}. Registered: {self.names()}")
        return max(versions)

    def get(self, name: str, *, version: Optional[int] = None) -> RegisteredFeature:
        v = version if version is not None else self.latest_version(name)
        try:
            return self._by_key[(name, v)]
        except KeyError:
            raise KeyError(
                f"unknown feature {name!r} v{version}. Registered: {sorted(self._by_key)}"
            ) from None

    def names(self) -> list[str]:
        return sorted({n for (n, _) in self._by_key})

    def specs(self) -> list[FeatureSpec]:
        return [
            rf.spec
            for rf in sorted(self._by_key.values(), key=lambda r: (r.spec.name, r.spec.version))
        ]

    def compute_one(self, name: str, ctx: FeatureContext, *, version: Optional[int] = None) -> FeatureValue:
        rf = self.get(name, version=version)
        return _validate_value(rf.spec, rf.fn(ctx))

    def compute_view(self, view: FeatureView, ctx: FeatureContext) -> FeatureVector:
        values: dict[str, FeatureValue] = {}
        missing: list[str] = []
        for rf in view.resolve(self):
            value = _validate_value(rf.spec, rf.fn(ctx))
            values[rf.spec.name] = value
            if value is None:
                missing.append(rf.spec.name)
        return FeatureVector(
            candidate_id=ctx.candidate_id, as_of=ctx.as_of,
            view_name=view.name, view_version=view.version,
            values=values, missing=tuple(missing),
        )

    def manifest(self) -> list[dict]:
        return [s.to_dict() for s in self.specs()]

    def manifest_json(self) -> str:
        return json.dumps(self.manifest(), indent=2, sort_keys=True)


# --- module-global default registry (mirrors domains/base.py `_REGISTRY`) ------
_DEFAULT_REGISTRY = FeatureRegistry()


def register_feature(
    *,
    name: str,
    version: int,
    dtype: FeatureDType,
    source: FeatureSource,
    description: str,
    nullable: bool = True,
    requires_consent: bool = False,
    valid_range: Optional[tuple[float, float]] = None,
    categories: Optional[tuple[str, ...]] = None,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[[FeatureContext], FeatureValue]], Callable[[FeatureContext], FeatureValue]]:
    """Decorator: build a FeatureSpec from kwargs and register the wrapped
    extractor into the module-global registry, returning it unchanged."""
    spec = FeatureSpec(
        name=name, version=version, dtype=dtype, source=source,
        description=description, nullable=nullable, requires_consent=requires_consent,
        valid_range=valid_range, categories=categories, tags=tuple(tags),
    )

    def _decorator(fn: Callable[[FeatureContext], FeatureValue]):
        _DEFAULT_REGISTRY.register(spec, fn)
        return fn

    return _decorator


def _register(spec: FeatureSpec, fn: Callable[[FeatureContext], FeatureValue], *, registry: Optional[FeatureRegistry] = None) -> None:
    """Escape hatch for tests / programmatic registration."""
    (registry or _DEFAULT_REGISTRY).register(spec, fn)


def latest_view(registry: FeatureRegistry, *, name: str, version: int) -> FeatureView:
    """A view pinning every registered feature at its latest version."""
    members = tuple((n, registry.latest_version(n)) for n in registry.names())
    return FeatureView(name=name, version=version, members=members)
```

```python
# app/features/__init__.py  (replace)
"""Feature registry (PI-4 / S4.1).

Importing ``app.features.definitions`` fires every ``@register_feature`` into the
module-global default registry (the app/domains load pattern).
"""

from app.features.registry import (
    FeatureRegistry,
    RegisteredFeature,
    _DEFAULT_REGISTRY,
    _register,
    latest_view,
    register_feature,
)
from app.features.schema import (
    FeatureContext,
    FeatureDType,
    FeatureSource,
    FeatureSpec,
    FeatureValue,
    FeatureVector,
    FeatureView,
)


def get_feature_registry() -> FeatureRegistry:
    """The populated default registry (imports the seed catalog on first call)."""
    import app.features.definitions  # noqa: F401 — fires registration
    return _DEFAULT_REGISTRY


def default_view(registry: FeatureRegistry | None = None, *, settings=None) -> FeatureView:
    from app.core.config import get_settings
    settings = settings or get_settings()
    reg = registry or get_feature_registry()
    return latest_view(reg, name=settings.feat_default_view, version=1)


__all__ = [
    "FeatureRegistry", "RegisteredFeature", "FeatureContext", "FeatureDType",
    "FeatureSource", "FeatureSpec", "FeatureValue", "FeatureVector", "FeatureView",
    "register_feature", "get_feature_registry", "default_view", "latest_view",
]
```

Create `app/features/definitions/__init__.py` with just a docstring for now:

```python
# app/features/definitions/__init__.py
"""Seed feature catalog. Each module registers its features on import."""
```

Note: `default_view` reads `settings.feat_default_view`, added in Task 8. Task 3
tests do not call `default_view`, so this is fine until then.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_feature_registry.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/registry.py app/features/__init__.py app/features/definitions/__init__.py tests/test_feature_registry.py
git commit -m "feat(s41): FeatureRegistry + @register_feature + output validation"
```

---

### Task 4: Candidate feature definitions

**Files:**
- Create: `app/features/definitions/candidate.py`
- Modify: `app/features/definitions/__init__.py` (import candidate)
- Test: `tests/test_features_candidate.py`

**Interfaces:**
- Consumes: `register_feature`, `FeatureContext`, `FeatureDType`, `FeatureSource`;
  `CandidateProfile`/`LinkType` (`app.candidates.schema`).
- Produces: registers `candidate.*` features into `_DEFAULT_REGISTRY`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_candidate.py
from datetime import datetime, timezone
from app.candidates.schema import (
    CandidateProfile, ContactInfo, DateRange, EducationEntry, ExperienceEntry,
    LinkItem, LinkType, SkillItem,
)
from app.features.registry import FeatureRegistry, _register
import app.features.definitions.candidate as cand
from app.features.schema import FeatureContext


AS_OF = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ctx(profile):
    return FeatureContext(candidate_id="c1", as_of=AS_OF, profile=profile)


def test_years_experience_merges_overlaps():
    # 2020-01..2021-12 (24m) overlapping 2021-01..2022-12 (24m) -> union 36m = 3.0y
    p = CandidateProfile(experience=[
        ExperienceEntry(dates=DateRange(start="2020-01", end="2021-12")),
        ExperienceEntry(dates=DateRange(start="2021-01", end="2022-12")),
    ])
    assert cand.years_experience(_ctx(p)) == 3.0


def test_years_experience_is_current_uses_as_of():
    p = CandidateProfile(experience=[
        ExperienceEntry(dates=DateRange(start="2023-01", is_current=True)),
    ])
    # 2023-01 .. 2024-01 inclusive = 13 months
    assert cand.years_experience(_ctx(p)) == round(13 / 12, 2)


def test_years_experience_none_without_dates():
    assert cand.years_experience(_ctx(CandidateProfile())) is None


def test_highest_degree_level_ordinal():
    p = CandidateProfile(education=[
        EducationEntry(degree_level="bachelor"),
        EducationEntry(degree_level="master"),
    ])
    assert cand.highest_degree_level(_ctx(p)) == "master"
    assert cand.highest_degree_level(_ctx(CandidateProfile())) == "none"


def test_top_institution_tier_and_cgpa():
    p = CandidateProfile(education=[
        EducationEntry(institution_tier="tier_2", grade_cgpa_10=7.5),
        EducationEntry(institution_tier="tier_1", grade_cgpa_10=8.9),
    ])
    assert cand.top_institution_tier(_ctx(p)) == "tier_1"
    assert cand.max_cgpa_10(_ctx(p)) == 8.9
    assert cand.max_cgpa_10(_ctx(CandidateProfile())) is None


def test_has_github_and_counts():
    p = CandidateProfile(
        skills=[SkillItem(name="python", canonical="python"), SkillItem(name="foo")],
        links=[LinkItem(type=LinkType.GITHUB, url="https://github.com/x")],
    )
    assert cand.has_github(_ctx(p)) is True
    assert cand.num_skills(_ctx(p)) == 2
    assert cand.num_canonical_skills(_ctx(p)) == 1
    assert cand.has_github(_ctx(CandidateProfile())) is False


def test_location_and_notice():
    p = CandidateProfile(
        contact=ContactInfo(location_tier="metro"), notice_period_days=45,
    )
    assert cand.location_tier(_ctx(p)) == "metro"
    assert cand.notice_period_days(_ctx(p)) == 45


def test_all_candidate_features_registered_and_validated():
    # Every candidate.* feature computes + validates on a rich profile.
    reg = FeatureRegistry()
    from app.features.registry import _DEFAULT_REGISTRY
    for rf in _DEFAULT_REGISTRY._by_key.values():
        if rf.spec.source.value == "candidate":
            _register(rf.spec, rf.fn, registry=reg)
    p = CandidateProfile(
        experience=[ExperienceEntry(dates=DateRange(start="2020-01", end="2022-01"))],
        education=[EducationEntry(degree_level="master", institution_tier="tier_1", grade_cgpa_10=9.0)],
        skills=[SkillItem(name="python", canonical="python")],
    )
    for name in reg.names():
        reg.compute_one(name, _ctx(p))   # raises if any output violates its spec
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_candidate.py -q`
Expected: FAIL — `ModuleNotFoundError: app.features.definitions.candidate`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/definitions/candidate.py
"""Candidate-profile features (source CANDIDATE, first-party, no consent)."""

from __future__ import annotations

from app.candidates.schema import LinkType
from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource

_DEGREE_LEVELS = ("none", "diploma", "bachelor", "master", "doctorate")
_INST_TIERS = ("none", "tier_2", "tier_1")
_LOC_TIERS = ("unknown", "tier_2", "metro")


def _month_index(ym: str, *, end: bool) -> int | None:
    """'YYYY-MM' or 'YYYY' -> absolute month index. Year-only: Jan (start) / Dec (end)."""
    parts = ym.split("-")
    try:
        year = int(parts[0])
    except (ValueError, IndexError):
        return None
    if len(parts) >= 2 and parts[1].isdigit():
        month = int(parts[1])
    else:
        month = 12 if end else 1
    month = min(12, max(1, month))
    return year * 12 + (month - 1)


@register_feature(
    name="candidate.years_experience", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.CANDIDATE,
    description="Total non-overlapping months of professional experience, in years.",
    valid_range=(0.0, 60.0),
)
def years_experience(ctx: FeatureContext) -> float | None:
    p = ctx.profile
    if p is None:
        return None
    as_of_idx = ctx.as_of.year * 12 + (ctx.as_of.month - 1)
    intervals: list[tuple[int, int]] = []
    for exp in p.experience:
        d = exp.dates
        if not d.start:
            continue
        lo = _month_index(d.start, end=False)
        if lo is None:
            continue
        if d.is_current or not d.end:
            hi = as_of_idx
        else:
            hi = _month_index(d.end, end=True)
            if hi is None:
                hi = as_of_idx
        if hi < lo:
            continue
        intervals.append((lo, hi))
    if not intervals:
        return None
    intervals.sort()
    merged = [list(intervals[0])]
    for lo, hi in intervals[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    total_months = sum(hi - lo + 1 for lo, hi in merged)
    return min(60.0, round(total_months / 12.0, 2))


@register_feature(
    name="candidate.num_experiences", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of experience entries.",
)
def num_experiences(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.experience) if ctx.profile else None


@register_feature(
    name="candidate.num_projects", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of project entries.",
)
def num_projects(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.projects) if ctx.profile else None


@register_feature(
    name="candidate.num_certifications", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of certification entries.",
)
def num_certifications(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.certifications) if ctx.profile else None


@register_feature(
    name="candidate.num_skills", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of listed skills.",
)
def num_skills(ctx: FeatureContext) -> int | None:
    return len(ctx.profile.skills) if ctx.profile else None


@register_feature(
    name="candidate.num_canonical_skills", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Count of skills mapped to the S1.4 taxonomy.",
)
def num_canonical_skills(ctx: FeatureContext) -> int | None:
    if ctx.profile is None:
        return None
    return sum(1 for s in ctx.profile.skills if s.canonical)


@register_feature(
    name="candidate.highest_degree_level", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.CANDIDATE,
    description="Highest normalized degree level attained.",
    categories=_DEGREE_LEVELS,
)
def highest_degree_level(ctx: FeatureContext) -> str | None:
    if ctx.profile is None:
        return None
    best = 0
    for edu in ctx.profile.education:
        lvl = (edu.degree_level or "").lower()
        if lvl in _DEGREE_LEVELS:
            best = max(best, _DEGREE_LEVELS.index(lvl))
    return _DEGREE_LEVELS[best]


@register_feature(
    name="candidate.max_cgpa_10", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.CANDIDATE,
    description="Highest canonical CGPA on the 10-point scale.",
    valid_range=(0.0, 10.0),
)
def max_cgpa_10(ctx: FeatureContext) -> float | None:
    if ctx.profile is None:
        return None
    vals = [e.grade_cgpa_10 for e in ctx.profile.education if e.grade_cgpa_10 is not None]
    return max(vals) if vals else None


@register_feature(
    name="candidate.top_institution_tier", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.CANDIDATE,
    description="Best institution tier across education entries.",
    categories=_INST_TIERS,
)
def top_institution_tier(ctx: FeatureContext) -> str | None:
    if ctx.profile is None:
        return None
    best = 0
    for edu in ctx.profile.education:
        tier = (edu.institution_tier or "").lower()
        if tier in _INST_TIERS:
            best = max(best, _INST_TIERS.index(tier))
    return _INST_TIERS[best]


@register_feature(
    name="candidate.notice_period_days", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.CANDIDATE,
    description="Normalized notice-period days (0 = immediate joiner).",
    valid_range=(0.0, 365.0),
)
def notice_period_days(ctx: FeatureContext) -> int | None:
    if ctx.profile is None or ctx.profile.notice_period_days is None:
        return None
    return max(0, min(365, ctx.profile.notice_period_days))


@register_feature(
    name="candidate.location_tier", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.CANDIDATE,
    description="Candidate city tier (metro > tier_2 > unknown).",
    categories=_LOC_TIERS,
)
def location_tier(ctx: FeatureContext) -> str | None:
    if ctx.profile is None:
        return None
    tier = (ctx.profile.contact.location_tier or "").lower()
    return tier if tier in ("tier_2", "metro") else "unknown"


@register_feature(
    name="candidate.has_github", version=1,
    dtype=FeatureDType.BOOLEAN, source=FeatureSource.CANDIDATE,
    description="Whether the candidate shared a GitHub link.",
)
def has_github(ctx: FeatureContext) -> bool | None:
    if ctx.profile is None:
        return None
    return any(link.type == LinkType.GITHUB for link in ctx.profile.links)
```

Add the import to `app/features/definitions/__init__.py`:

```python
from app.features.definitions import candidate as _candidate  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_candidate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/features/definitions/candidate.py app/features/definitions/__init__.py tests/test_features_candidate.py
git commit -m "feat(s41): candidate.* feature definitions"
```

---

### Task 5: Depth feature definitions

**Files:**
- Create: `app/features/definitions/depth.py`
- Modify: `app/features/definitions/__init__.py` (import depth)
- Test: `tests/test_features_depth.py`

**Interfaces:**
- Consumes: `register_feature`, `FeatureContext`; `Report`, `DepthBand`,
  `CoherenceVerdict`, `VerdictStatus` (`app.schemas.report`).
- Produces: registers `depth.*` features.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_depth.py
from datetime import datetime, timezone
from app.features.schema import FeatureContext
import app.features.definitions.depth as depth
from app.schemas.report import CoherenceVerdict, DepthBand, Report, VerdictStatus

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ctx(report):
    return FeatureContext(candidate_id="c1", as_of=AS_OF, report=report)


def _report(**kw):
    return Report(candidate_id="c1", **kw)


def test_depth_scalars_and_band():
    r = _report(depth_score=0.72, overall_confidence=0.6, depth_band=DepthBand.SOLID)
    assert depth.depth_score(_ctx(r)) == 0.72
    assert depth.overall_confidence(_ctx(r)) == 0.6
    assert depth.depth_band(_ctx(r)) == "solid"


def test_depth_none_without_report():
    assert depth.depth_score(_ctx(None)) is None
    assert depth.depth_band(_ctx(None)) is None


def test_claim_counts_and_ratio():
    verdicts = [
        CoherenceVerdict(claim_id="a", claim_text="x", claim_type="t",
                         status=VerdictStatus.COHERENT),
        CoherenceVerdict(claim_id="b", claim_text="y", claim_type="t",
                         status=VerdictStatus.INCOHERENT),
    ]
    r = _report(verdicts=verdicts, flagged_claim_ids=["b"], deferred_claim_ids=[])
    ctx = _ctx(r)
    assert depth.verdict_count(ctx) == 2
    assert depth.flagged_claim_count(ctx) == 1
    assert depth.deferred_claim_count(ctx) == 0
    assert depth.coherent_claim_ratio(ctx) == 0.5


def test_coherent_ratio_none_without_verdicts():
    assert depth.coherent_claim_ratio(_ctx(_report())) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_depth.py -q`
Expected: FAIL — `ModuleNotFoundError: app.features.definitions.depth`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/definitions/depth.py
"""Depth-evaluation report features (source DEPTH, first-party, no consent)."""

from __future__ import annotations

from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource
from app.schemas.report import VerdictStatus

_DEPTH_BANDS = ("insufficient_signal", "superficial", "emerging", "solid", "deep")


@register_feature(
    name="depth.depth_score", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.DEPTH,
    description="Aggregate depth score from the latest report.",
    valid_range=(0.0, 1.0),
)
def depth_score(ctx: FeatureContext) -> float | None:
    return ctx.report.depth_score if ctx.report else None


@register_feature(
    name="depth.overall_confidence", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.DEPTH,
    description="Overall evaluation confidence from the latest report.",
    valid_range=(0.0, 1.0),
)
def overall_confidence(ctx: FeatureContext) -> float | None:
    return ctx.report.overall_confidence if ctx.report else None


@register_feature(
    name="depth.depth_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.DEPTH,
    description="Advisory depth band from the latest report.",
    categories=_DEPTH_BANDS,
)
def depth_band(ctx: FeatureContext) -> str | None:
    return ctx.report.depth_band.value if ctx.report else None


@register_feature(
    name="depth.verdict_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.DEPTH,
    description="Number of claim verdicts in the latest report.",
)
def verdict_count(ctx: FeatureContext) -> int | None:
    return len(ctx.report.verdicts) if ctx.report else None


@register_feature(
    name="depth.flagged_claim_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.DEPTH,
    description="Number of flagged (incoherent) claims.",
)
def flagged_claim_count(ctx: FeatureContext) -> int | None:
    return len(ctx.report.flagged_claim_ids) if ctx.report else None


@register_feature(
    name="depth.deferred_claim_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.DEPTH,
    description="Number of deferred (low-confidence) claims.",
)
def deferred_claim_count(ctx: FeatureContext) -> int | None:
    return len(ctx.report.deferred_claim_ids) if ctx.report else None


@register_feature(
    name="depth.coherent_claim_ratio", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.DEPTH,
    description="Fraction of verdicts that are coherent.",
    valid_range=(0.0, 1.0),
)
def coherent_claim_ratio(ctx: FeatureContext) -> float | None:
    if ctx.report is None or not ctx.report.verdicts:
        return None
    coherent = sum(1 for v in ctx.report.verdicts if v.status == VerdictStatus.COHERENT)
    return round(coherent / len(ctx.report.verdicts), 4)
```

Add to `app/features/definitions/__init__.py`:

```python
from app.features.definitions import depth as _depth  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_depth.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/features/definitions/depth.py app/features/definitions/__init__.py tests/test_features_depth.py
git commit -m "feat(s41): depth.* feature definitions"
```

---

### Task 6: Fabrication feature definitions

**Files:**
- Create: `app/features/definitions/fabrication.py`
- Modify: `app/features/definitions/__init__.py` (import fabrication)
- Test: `tests/test_features_fabrication.py`

**Interfaces:**
- Consumes: `register_feature`, `FeatureContext`; the fabrication assessments on
  `Report` (`app.schemas.report` / `app.schemas.fabrication`).
- Produces: registers `fabrication.*` features.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_fabrication.py
from datetime import datetime, timezone
from app.features.schema import FeatureContext
import app.features.definitions.fabrication as fab
from app.schemas.fabrication import (
    AIGenerationAssessment, AILikelihoodBand, ConsistencyBand, CrossFieldAssessment,
    CrossFieldFinding, DuplicationBand, FabricationRiskAssessment, FabricationRiskBand,
    FindingSeverity, ResumeFarmAssessment,
)
from app.schemas.report import Report

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ctx(report):
    return FeatureContext(candidate_id="c1", as_of=AS_OF, report=report)


def test_risk_score_and_band():
    r = Report(candidate_id="c1", fabrication_risk=FabricationRiskAssessment(
        score=0.42, band=FabricationRiskBand.MODERATE))
    assert fab.risk_score(_ctx(r)) == 0.42
    assert fab.risk_band(_ctx(r)) == "moderate"


def test_none_when_subsystem_absent():
    r = Report(candidate_id="c1")
    assert fab.risk_score(_ctx(r)) is None
    assert fab.ai_generation_band(_ctx(r)) is None
    assert fab.resume_farm_band(_ctx(r)) is None
    assert fab.cross_field_major_count(_ctx(r)) is None
    assert fab.risk_score(_ctx(None)) is None


def test_ai_farm_bands_and_major_count():
    r = Report(
        candidate_id="c1",
        ai_generation=AIGenerationAssessment(band=AILikelihoodBand.POSSIBLE),
        resume_farm=ResumeFarmAssessment(band=DuplicationBand.NEAR_DUPLICATE),
        cross_field=CrossFieldAssessment(band=ConsistencyBand.MAJOR_ISSUES, findings=[
            CrossFieldFinding(id="timeline_overlap", detail="x", severity=FindingSeverity.MAJOR, score=0.8),
            CrossFieldFinding(id="gap", detail="y", severity=FindingSeverity.MINOR, score=0.2),
        ]),
    )
    ctx = _ctx(r)
    assert fab.ai_generation_band(ctx) == "possible"
    assert fab.resume_farm_band(ctx) == "near_duplicate"
    assert fab.cross_field_major_count(ctx) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_fabrication.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/definitions/fabrication.py
"""Fabrication-defense features (source FABRICATION, first-party, no consent)."""

from __future__ import annotations

from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource
from app.schemas.fabrication import FindingSeverity

_RISK_BANDS = ("insufficient_data", "low", "moderate", "elevated")
_AI_BANDS = ("insufficient_text", "unlikely", "possible", "likely")
_FARM_BANDS = ("insufficient_data", "unique", "similar", "near_duplicate")


@register_feature(
    name="fabrication.risk_score", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.FABRICATION,
    description="Unified advisory fabrication-risk score (S2.4).",
    valid_range=(0.0, 1.0),
)
def risk_score(ctx: FeatureContext) -> float | None:
    r = ctx.report
    if r is None or r.fabrication_risk is None:
        return None
    return r.fabrication_risk.score


@register_feature(
    name="fabrication.risk_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.FABRICATION,
    description="Unified advisory fabrication-risk band (S2.4).",
    categories=_RISK_BANDS,
)
def risk_band(ctx: FeatureContext) -> str | None:
    r = ctx.report
    if r is None or r.fabrication_risk is None:
        return None
    return r.fabrication_risk.band.value


@register_feature(
    name="fabrication.ai_generation_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.FABRICATION,
    description="AI-generated-resume likelihood band (S2.1).",
    categories=_AI_BANDS,
)
def ai_generation_band(ctx: FeatureContext) -> str | None:
    r = ctx.report
    if r is None or r.ai_generation is None:
        return None
    return r.ai_generation.band.value


@register_feature(
    name="fabrication.cross_field_major_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.FABRICATION,
    description="Count of MAJOR cross-field forensic findings (S2.2).",
)
def cross_field_major_count(ctx: FeatureContext) -> int | None:
    r = ctx.report
    if r is None or r.cross_field is None:
        return None
    return sum(1 for f in r.cross_field.findings if f.severity == FindingSeverity.MAJOR)


@register_feature(
    name="fabrication.resume_farm_band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.FABRICATION,
    description="Resume-farm near-duplicate band (S2.3).",
    categories=_FARM_BANDS,
)
def resume_farm_band(ctx: FeatureContext) -> str | None:
    r = ctx.report
    if r is None or r.resume_farm is None:
        return None
    return r.resume_farm.band.value
```

Add to `app/features/definitions/__init__.py`:

```python
from app.features.definitions import fabrication as _fabrication  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_fabrication.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/features/definitions/fabrication.py app/features/definitions/__init__.py tests/test_features_fabrication.py
git commit -m "feat(s41): fabrication.* feature definitions"
```

---

### Task 7: Ledger + reputation feature definitions (consent-tagged)

**Files:**
- Create: `app/features/definitions/ledger.py`
- Modify: `app/features/definitions/__init__.py` (import ledger)
- Test: `tests/test_features_ledger.py`

**Interfaces:**
- Consumes: `register_feature`, `FeatureContext`; `InterviewRecord`,
  `CodingRoundResult` (`app.ledger.schema`); `ctx.reputation`.
- Produces: registers `ledger.*` (source LEDGER) and `reputation.*`
  (source REPUTATION) features, all `requires_consent=True`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_ledger.py
from datetime import datetime, timezone
from app.features.schema import FeatureContext
import app.features.definitions.ledger as led
from app.ledger.schema import (
    CodingPlatform, CodingRoundResult, InterviewOutcome, InterviewRecord, InterviewStage,
)

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rec(org):
    return InterviewRecord(
        org_id=org, candidate_id="c1", consent_id="g1",
        stage=InterviewStage.HM, outcome=InterviewOutcome.HIRED,
        interviewed_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )


def _coding(org, pct):
    return CodingRoundResult(
        org_id=org, candidate_id="c1", consent_id="g1",
        platform=CodingPlatform.HACKERRANK, score=90.0, max_score=100.0, percentile=pct,
        taken_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )


def _ctx(records=(), coding=()):
    return FeatureContext(candidate_id="c1", as_of=AS_OF,
                          interview_records=tuple(records), coding_rounds=tuple(coding))


def test_counts_and_distinct_orgs():
    ctx = _ctx([_rec("A"), _rec("B")], [_coding("A", 92.0)])
    assert led.interview_record_count(ctx) == 2
    assert led.coding_round_count(ctx) == 1
    assert led.distinct_orgs(ctx) == 2
    assert led.best_coding_percentile(ctx) == 92.0


def test_empty_ledger_defaults():
    ctx = _ctx()
    assert led.interview_record_count(ctx) == 0
    assert led.distinct_orgs(ctx) == 0
    assert led.best_coding_percentile(ctx) is None
    assert led.reputation_band(ctx) == "insufficient_data"
    assert 0.0 <= led.reputation_score(ctx) <= 1.0


def test_reputation_features_use_context_assessment():
    ctx = _ctx([_rec("A"), _rec("B")], [_coding("A", 92.0), _coding("B", 88.0)])
    assert led.reputation_band(ctx) in {"favorable", "strong", "mixed"}
    assert led.reputation_score(ctx) > 0.5


def test_all_ledger_features_require_consent():
    from app.features.registry import _DEFAULT_REGISTRY
    import app.features.definitions.ledger  # noqa: F401 ensure registered
    for (name, _), rf in _DEFAULT_REGISTRY._by_key.items():
        if rf.spec.source.value in ("ledger", "reputation"):
            assert rf.spec.requires_consent is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/definitions/ledger.py
"""Ledger + reputation features (consent-gated cross-company signals).

Source LEDGER/REPUTATION, requires_consent=True: S4.2/S4.3 must hold an active
ledger_read grant to materialize/serve these. Definition-time carries no consent
obligation.
"""

from __future__ import annotations

from app.features.registry import register_feature
from app.features.schema import FeatureContext, FeatureDType, FeatureSource

_REP_BANDS = ("insufficient_data", "guarded", "mixed", "favorable", "strong")


@register_feature(
    name="ledger.interview_record_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.LEDGER,
    description="Number of consented cross-company interview records.",
    nullable=False, requires_consent=True,
)
def interview_record_count(ctx: FeatureContext) -> int:
    return len(ctx.interview_records)


@register_feature(
    name="ledger.coding_round_count", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.LEDGER,
    description="Number of consented cross-company coding-round results.",
    nullable=False, requires_consent=True,
)
def coding_round_count(ctx: FeatureContext) -> int:
    return len(ctx.coding_rounds)


@register_feature(
    name="ledger.distinct_orgs", version=1,
    dtype=FeatureDType.INTEGER, source=FeatureSource.LEDGER,
    description="Distinct organizations across records and coding rounds.",
    nullable=False, requires_consent=True,
)
def distinct_orgs(ctx: FeatureContext) -> int:
    orgs = {r.org_id for r in ctx.interview_records}
    orgs |= {c.org_id for c in ctx.coding_rounds}
    return len(orgs)


@register_feature(
    name="ledger.best_coding_percentile", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.LEDGER,
    description="Highest coding-round percentile (None if none reported).",
    valid_range=(0.0, 100.0), requires_consent=True,
)
def best_coding_percentile(ctx: FeatureContext) -> float | None:
    vals = [c.percentile for c in ctx.coding_rounds if c.percentile is not None]
    return max(vals) if vals else None


@register_feature(
    name="reputation.score", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.REPUTATION,
    description="Advisory cross-company reputation score (S3.4).",
    valid_range=(0.0, 1.0), nullable=False, requires_consent=True,
)
def reputation_score(ctx: FeatureContext) -> float:
    return ctx.reputation.score


@register_feature(
    name="reputation.confidence", version=1,
    dtype=FeatureDType.NUMERIC, source=FeatureSource.REPUTATION,
    description="Confidence of the advisory reputation estimate (S3.4).",
    valid_range=(0.0, 1.0), nullable=False, requires_consent=True,
)
def reputation_confidence(ctx: FeatureContext) -> float:
    return ctx.reputation.confidence


@register_feature(
    name="reputation.band", version=1,
    dtype=FeatureDType.ORDINAL, source=FeatureSource.REPUTATION,
    description="Advisory cross-company reputation band (S3.4).",
    categories=_REP_BANDS, nullable=False, requires_consent=True,
)
def reputation_band(ctx: FeatureContext) -> str:
    return ctx.reputation.band.value
```

Add to `app/features/definitions/__init__.py`:

```python
from app.features.definitions import ledger as _ledger  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_ledger.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/features/definitions/ledger.py app/features/definitions/__init__.py tests/test_features_ledger.py
git commit -m "feat(s41): ledger.* + reputation.* feature definitions (consent-tagged)"
```

---

### Task 8: Catalog wiring (get_feature_registry, core_v1) + config knob

**Files:**
- Modify: `app/core/config.py` (add `feat_default_view`)
- Modify: `config.yaml` (add `feat_default_view`)
- Test: `tests/test_features_catalog.py`

**Interfaces:**
- Consumes: `get_feature_registry`, `default_view`, `compute_view` (Tasks 3, 4-7);
  `Settings.feat_default_view` (this task).
- Produces: a fully-loaded default registry; `core_v1` view; the config knob.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_catalog.py
from datetime import datetime, timezone
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.schema import FeatureContext


def test_default_view_covers_every_registered_feature():
    reg = get_feature_registry()
    view = default_view(reg, settings=Settings(_env_file=None, openrouter_api_key=""))
    assert view.name == "core_v1"
    assert {n for n, _ in view.members} == set(reg.names())
    assert len(reg.names()) >= 25          # seed catalog breadth


def test_consent_flag_matches_source():
    reg = get_feature_registry()
    for spec in reg.specs():
        expect = spec.source.value in ("ledger", "reputation")
        assert spec.requires_consent is expect


def test_manifest_json_roundtrips():
    import json
    reg = get_feature_registry()
    data = json.loads(reg.manifest_json())
    assert len(data) == len(reg.names())
    assert all("dtype" in row and "requires_consent" in row for row in data)


def test_compute_view_on_empty_context_is_well_formed():
    reg = get_feature_registry()
    view = default_view(reg, settings=Settings(_env_file=None, openrouter_api_key=""))
    ctx = FeatureContext(candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    fv = reg.compute_view(view, ctx)         # raises if any output violates its spec
    # ledger counts default to 0 (nullable=False); candidate/depth features missing
    assert fv.values["ledger.interview_record_count"] == 0
    assert fv.values["reputation.band"] == "insufficient_data"
    assert "candidate.years_experience" in fv.missing


def test_feat_default_view_setting_present():
    assert Settings(_env_file=None, openrouter_api_key="").feat_default_view == "core_v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_catalog.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'feat_default_view'`.

- [ ] **Step 3: Write minimal implementation**

In `app/core/config.py`, after the `rep_coding_weight` line (end of the reputation
block, ~line 222), add:

```python
    # --- ML feature store (PI-4, S4.1): feature registry -----------------------
    # Default FeatureView the materializer/smoke resolve (all seed features at
    # their latest version). Feature LOGIC is code-versioned, not config.
    feat_default_view: str = "core_v1"
```

In `config.yaml`, after the `rep_coding_weight` line (~line 149), add (ASCII only):

```yaml

# --- ML feature store (PI-4) - S4.1 feature registry --------------------------
feat_default_view: core_v1      # default FeatureView name (all seed features)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_catalog.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py config.yaml tests/test_features_catalog.py
git commit -m "feat(s41): catalog wiring (core_v1) + feat_default_view knob"
```

---

### Task 9: FeatureContext builder from stores

**Files:**
- Create: `app/features/context.py`
- Test: `tests/test_feature_context.py`

**Interfaces:**
- Consumes: `CandidateStore` (`latest_profile`, `get_candidate`, `ingest`),
  `ReportStore` (`for_candidate`, `save`), `LedgerStore`
  (`records_for_candidate`, `coding_rounds_for_candidate`); `FeatureContext`.
- Produces: `build_context(candidate_id, *, candidate_store, report_store,
  ledger_store, as_of=None) -> FeatureContext | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_context.py
from datetime import datetime, timezone
from app.candidates.extractor import extract_profile
from app.features.context import build_context
from app.schemas.report import DepthBand, Report
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store
from app.ledger.store import LedgerStore
from app.ledger.schema import ConsentPurpose, InterviewStage, InterviewOutcome

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark\nEmail: jane@example.com\n"


def _stores():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    rs = InMemoryReportStore()
    return cs, ls, rs


def test_build_context_unknown_candidate_returns_none():
    cs, ls, rs = _stores()
    assert build_context("nope", candidate_store=cs, report_store=rs, ledger_store=ls) is None


def test_build_context_assembles_profile_report_and_ledger():
    cs, ls, rs = _stores()
    result = extract_profile(RESUME)
    cid = cs.ingest(result, resume_text=RESUME).candidate_id
    # Pin created_at so the build_context `created_at <= as_of` cutoff includes it
    # (a default real-time created_at would sort after a fixed 2026-06-01 as_of).
    rs.save(Report(candidate_id=cid, depth_score=0.6, depth_band=DepthBand.SOLID,
                   created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=None, now=now)
    # create an org + submit a record
    org = ls.create_organization("Org A")
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=now)
    ls.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.HM,
        outcome=InterviewOutcome.HIRED, interviewed_at=now, now=now,
    )

    ctx = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                        as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert ctx is not None
    assert ctx.profile is not None and ctx.report is not None
    assert ctx.report.depth_score == 0.6
    assert len(ctx.interview_records) == 1


def test_build_context_respects_as_of_cutoff():
    cs, ls, rs = _stores()
    result = extract_profile(RESUME)
    cid = cs.ingest(result, resume_text=RESUME).candidate_id
    org = ls.create_organization("Org A")
    later = datetime(2026, 5, 1, tzinfo=timezone.utc)
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=later)
    ls.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.HM,
        outcome=InterviewOutcome.HIRED, interviewed_at=later, now=later,
    )
    ctx = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert ctx is not None and len(ctx.interview_records) == 0   # record is after as_of
```

Note (confirmed against `app/candidates/store.py`): `CandidateStore.ingest(result:
ExtractionResult, resume_text: str) -> IngestOutcome`, and `IngestOutcome` exposes
`.candidate_id`. Pass the whole `ExtractionResult` (not `result.profile`).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feature_context.py -q`
Expected: FAIL — `ModuleNotFoundError: app.features.context`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/context.py
"""Assemble a FeatureContext from the live stores (PI-4 / S4.1).

The only part of app/features that touches stores. Assembles the *current*
snapshot (``as_of = now``) with a coarse ``created_at <= as_of`` cutoff on
time-stamped rows. Full point-in-time correctness (versioned resumes/reports,
consent-validity-at-as_of) is S4.2's materialization job — this is the seam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.candidates.store import CandidateStore
from app.features.schema import FeatureContext
from app.ledger.store import LedgerStore
from app.services.report_store import ReportStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_context(
    candidate_id: str,
    *,
    candidate_store: CandidateStore,
    report_store: ReportStore,
    ledger_store: LedgerStore,
    as_of: Optional[datetime] = None,
) -> Optional[FeatureContext]:
    if candidate_store.get_candidate(candidate_id) is None:
        return None
    moment = as_of or _utcnow()

    profile = candidate_store.latest_profile(candidate_id)

    reports = [r for r in report_store.for_candidate(candidate_id) if r.created_at <= moment]
    report = max(reports, key=lambda r: r.created_at) if reports else None

    records = tuple(
        r for r in ledger_store.records_for_candidate(candidate_id)
        if r.interviewed_at <= moment
    )
    coding = tuple(
        c for c in ledger_store.coding_rounds_for_candidate(candidate_id)
        if c.taken_at <= moment
    )

    return FeatureContext(
        candidate_id=candidate_id, as_of=moment,
        profile=profile, report=report,
        interview_records=records, coding_rounds=coding,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_feature_context.py -q`
Expected: PASS (3 tests). Then run the whole suite: `pytest -q` — expect green.

- [ ] **Step 5: Commit**

```bash
git add app/features/context.py tests/test_feature_context.py
git commit -m "feat(s41): build_context snapshot assembler (as_of cutoff; slicing = S4.2)"
```

---

### Task 10: Smoke script + FEATURES.md + ROADMAP

**Files:**
- Create: `scripts/smoke_s41.py`
- Create: `FEATURES.md`
- Modify: `docs/ROADMAP.md` (status board `S4.1 [x]`, Current state, session log)

**Interfaces:**
- Consumes: the HTTP app (`app.main:app`) for population; the `build_*` store
  builders + `get_feature_registry`/`default_view`/`compute_view` for direct
  feature computation.

- [ ] **Step 1: Write the smoke script**

```python
# scripts/smoke_s41.py
"""S4.1 smoke: feature registry over real candidate + depth + ledger data.

Boots uvicorn on a migrated scratch DB, POSTs a fixture resume (real extraction
+ auto depth-eval + persisted report), submits consented interview + coding
rows, then opens the stores DIRECTLY and computes the core_v1 feature vector.
Also computes for a candidate with NO ledger data. LLM-free (heuristic
extraction, no API key). Run from the repo root:
    python scripts/smoke_s41.py
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

from app.core.config import Settings
from app.candidates.store import build_candidate_store
from app.features import default_view, get_feature_registry
from app.features.context import build_context
from app.ledger.store import build_ledger_store
from app.services.report_store import build_report_store

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8041
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
AT = "2026-07-24T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s41.db").as_posix()
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
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    admin_h = {"X-API-Key": ADMIN}
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

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            method = cand["extraction_method"]
            # a second candidate with NO ledger data — must be a DISTINCT identity
            # (a different email, else email-hash identity resolution merges it
            # into the first candidate).
            alt = ("Priya Nair\nBackend Engineer\n"
                   "Email: priya.nair.noledger@example.com\n"
                   "Skills: Python, PostgreSQL\n"
                   "Experience: Backend Engineer at Acme, 2021-2024\n")
            cand2 = c.post("/candidates", json={"resume_text": alt}, headers=admin_h).json()
            cid2 = cand2["candidate_id"]

            org = c.post("/ledger/orgs", json={"name": "Org A"}, headers=admin_h).json()
            oid, okey = org["org"]["id"], org["api_key"]
            oh = {"X-Org-Key": okey}
            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_write", "org_id": oid}, headers=admin_h)
            for _ in range(2):
                c.post("/ledger/records",
                       json={"candidate_id": cid, "stage": "hm",
                             "outcome": "hired", "interviewed_at": AT}, headers=oh)
            c.post("/ledger/coding-rounds",
                   json={"candidate_id": cid, "platform": "hackerrank",
                         "score": 90.0, "max_score": 100.0, "percentile": 92.0,
                         "taken_at": AT}, headers=oh)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    # --- direct feature computation against the same scratch DBs ---------------
    settings = Settings(
        _env_file=None, openrouter_api_key="",
        candidates_db_url=url, report_db_path=reports, vectorstore_backend="memory",
    )
    cs = build_candidate_store(settings)
    ls = build_ledger_store(settings)
    rs = build_report_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)

    ctx = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls)
    fv = reg.compute_view(view, ctx)
    ctx2 = build_context(cid2, candidate_store=cs, report_store=rs, ledger_store=ls)
    fv2 = reg.compute_view(view, ctx2)

    print(f"candidate [{method}]: {cid[:8]}  features={len(fv.values)}")
    print(f"  years_experience   = {fv.values.get('candidate.years_experience')}")
    print(f"  depth_score        = {fv.values.get('depth.depth_score')}")
    print(f"  fabrication.risk   = {fv.values.get('fabrication.risk_band')}")
    print(f"  interview_records  = {fv.values.get('ledger.interview_record_count')}")
    print(f"  reputation.band    = {fv.values.get('reputation.band')}")
    print(f"  reputation.score   = {fv.values.get('reputation.score')}")

    checks = {
        "registry has >= 25 features": len(reg.names()) >= 25,
        "view covers every feature": {n for n, _ in view.members} == set(reg.names()),
        "profile feature present": fv.values.get("candidate.num_skills") is not None,
        "depth feature present": fv.values.get("depth.depth_score") is not None,
        "consent-gated ledger count = 2": fv.values.get("ledger.interview_record_count") == 2,
        "best coding percentile = 92": fv.values.get("ledger.best_coding_percentile") == 92.0,
        "reputation computed (score in range)": 0.0 <= (fv.values.get("reputation.score") or -1) <= 1.0,
        "no-ledger candidate counts 0": fv2.values.get("ledger.interview_record_count") == 0,
        "no-ledger percentile missing": "ledger.best_coding_percentile" in fv2.missing,
        "no-ledger reputation insufficient": fv2.values.get("reputation.band") == "insufficient_data",
    }
    failed = [name for name, v in checks.items() if not v]
    for name, v in checks.items():
        print(f"  {'OK  ' if v else 'FAIL'} {name}")
    if failed:
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke (key-less)**

Run: `python scripts/smoke_s41.py`
Expected: all checks `OK`, `SMOKE OK`, exit 0. If a check fails, fix the
underlying code (not the assertion) and re-run.

- [ ] **Step 3: Write `FEATURES.md`**

Create `FEATURES.md` (peer of `LEDGER.md`/`FABRICATION.md`) documenting: the
registry model (`@register_feature`, `FeatureSpec`, `FeatureContext`,
`FeatureView`/`core_v1`, `FeatureVector`); the seed catalog table (name, dtype,
source, consent); the point-in-time convention + the S4.2 seam; the
`requires_consent` contract and that enforcement is S4.2/S4.3; how to add a
feature (drop a `@register_feature` in `app/features/definitions/`, bump
`version` on a logic change). Keep it to ~1 page, matching the tone of
`LEDGER.md`.

- [ ] **Step 4: Full suite green**

Run: `pytest -q`
Expected: all green (~468 + new tests). Fix any regressions before committing.

- [ ] **Step 5: Update ROADMAP + commit**

Update `docs/ROADMAP.md`: status board `S4.1 [x]`; "Current state" → next action
S4.2 (materialization); add a session-log entry summarizing S4.1 (registry
package, seed catalog count, tests delta, smoke result, `FEATURES.md`).

```bash
git add scripts/smoke_s41.py FEATURES.md docs/ROADMAP.md
git commit -m "feat(s41): direct-module smoke + FEATURES.md + ROADMAP (S4.1 complete)"
```

---

## Self-Review

**1. Spec coverage** (checked against `2026-07-26-s41-feature-registry-design.md`):
- Package layout `app/features/{schema,registry,context,definitions/}` → Tasks 1-9. ✓
- Contracts (`FeatureDType`, `FeatureSource`, `FeatureValue`, `FeatureSpec`,
  `FeatureContext`, `FeatureView`, `FeatureVector`) → Tasks 1-2. ✓
- Registry (`@register_feature`, register/collision/get/latest, `compute_one`
  validation, `compute_view`, `manifest`) → Task 3. ✓
- Seed catalog (candidate/depth/fabrication/ledger, ~28-30, consent-tagged) →
  Tasks 4-7. ✓ (candidate 12 + depth 7 + fabrication 5 + ledger/reputation 7 =
  31 features.)
- `core_v1` default view + `get_feature_registry` load pattern + config knob →
  Tasks 3, 8. ✓
- Point-in-time `as_of` convention + builder + deferred slicer → Task 9. ✓
- DPDP (no new table; `build_context` returns None after erasure; consent tag) →
  Tasks 7, 9 + FEATURES.md (Task 10). ✓
- Direct-module smoke + FEATURES.md + ROADMAP → Task 10. ✓
- Ordinal sentinel-at-0 ordering → encoded in each ordinal's `categories`
  (Tasks 4-7) + Global Constraints. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has real code. FEATURES.md
(Task 10 Step 3) is described by required sections, not code — acceptable for a
prose doc. Two verification notes (report `created_at` tz-awareness; `ingest`
return attribute) are flagged inline where a store signature must be confirmed.

**3. Type consistency:** `FeatureContext`, `FeatureSpec`, `FeatureView`,
`RegisteredFeature`, `register_feature`, `_register`, `latest_view`,
`get_feature_registry`, `default_view`, `compute_view`, `build_context` names +
signatures are identical across the tasks that define and consume them. Ordinal
category tuples (`_DEGREE_LEVELS`, `_DEPTH_BANDS`, `_RISK_BANDS`, `_AI_BANDS`,
`_FARM_BANDS`, `_REP_BANDS`) match the band `.value` strings they validate.

Store signatures confirmed against source: `CandidateStore.ingest(result:
ExtractionResult, resume_text: str) -> IngestOutcome` (`.candidate_id`);
`Report.created_at` is tz-aware (pydantic default `datetime.now(timezone.utc)`),
as are ledger `interviewed_at`/`taken_at` (coerced via `as_utc`), so every
`<= as_of` comparison in `build_context` is aware-vs-aware.
```
