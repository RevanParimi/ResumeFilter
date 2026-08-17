# S9.1 Signal Quality Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether veritas's advisory numbers predict what a human concluded — and refuse to report a number when the sample cannot support one.

**Architecture:** A new pure package `src/app/signal_quality/`. One predictor source (the persisted `Report` body, which is the point-in-time artifact the human actually saw) joined to two label sources behind a seam that carries label *semantics*, so a fraud signal can never be scored against a hiring label. Metrics are pure stdlib Python. Three refusals — insufficient samples, degenerate class, label-kind mismatch — return a type that structurally cannot carry a metric.

**Tech Stack:** Python 3.11+, pydantic v2, SQLAlchemy 2.0, FastAPI, pytest. **No new dependency.**

**Spec:** `docs/superpowers/specs/2026-08-17-s91-signal-quality-harness-design.md`

## Global Constraints

- **No new dependency.** `requirements.txt` is unchanged. No numpy, scipy, or scikit-learn — every metric is written out in stdlib Python.
- **No new table, no migration.** This sprint reads existing rows only.
- **TDD, every test seen red first.** `pytest -q` green before merge. Baseline is **1854 passing** on `main` at `9ac59b9`.
- **Fully offline.** No LLM, no network, no API key. Nothing here has an LLM step, so the deterministic-fallback rule is satisfied vacuously — say so rather than inventing a fallback.
- **Advisory only.** This sprint measures; it never retunes a threshold, weight, or band boundary.
- **`build_label` is not edited.** `src/app/features/training.py` stays byte-identical; the ledger source wraps it.
- **No boot refusal is added.** The existing eight stand. This is analysis tooling.
- **Package is `app`,** at `src/app/` (S8.7). Imports read `from app.signal_quality...`.
- **Naming:** the package is `signal_quality`, never `calibration` (taken: `app/core/calibration.py`, the scoring gate) and never `metrics` (taken: `app/metrics/`, the Prometheus surface).
- **Commits:** no `Co-Authored-By` trailer.

---

### Task 1: Result and refusal types

**Files:**
- Create: `src/app/signal_quality/__init__.py` (empty)
- Create: `src/app/signal_quality/schema.py`
- Test: `tests/test_signal_quality_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LabelKind`, `MetricKind`, `RefusalReason`, `CalibrationBin`, `BandLift`, `SignalMeasured`, `SignalRefused`, `SignalResult`, `Population`, `SignalQualityReport`.

The load-bearing decision: `SignalMeasured` and `SignalRefused` are **separate models**, not one model with optional fields. A refusal that still carries an `auc` attribute set to `None` is a refusal a caller can misread as "AUC is null"; separate types make that unrepresentable. The `sufficient` literal is the discriminator.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_schema.py
import pytest
from pydantic import ValidationError

from app.signal_quality.schema import (
    LabelKind,
    MetricKind,
    RefusalReason,
    SignalMeasured,
    SignalRefused,
)


def test_a_refusal_cannot_carry_a_metric():
    """The whole point of two types instead of one optional-field type."""
    refused = SignalRefused(
        signal="fabrication_risk.score",
        reason=RefusalReason.INSUFFICIENT_SAMPLES,
        n=3,
        detail="3 usable labels, need 30",
    )
    assert refused.sufficient is False
    assert not hasattr(refused, "auc")
    with pytest.raises(ValidationError):
        SignalRefused(
            signal="x", reason=RefusalReason.DEGENERATE_CLASS, n=0,
            detail="", auc=0.9,
        )


def test_measured_carries_n_and_positives():
    m = SignalMeasured(signal="fabrication_risk.score", n=40, positives=12, auc=0.71)
    assert m.sufficient is True
    assert (m.n, m.positives) == (40, 12)
    assert m.brier is None


def test_results_are_frozen():
    m = SignalMeasured(signal="s", n=1, positives=1)
    with pytest.raises(ValidationError):
        m.auc = 0.5


def test_label_kinds_are_distinct():
    assert LabelKind.FRAUD != LabelKind.HIRE
    assert set(MetricKind) == {MetricKind.AUC, MetricKind.BRIER, MetricKind.LIFT}
    assert RefusalReason.LABEL_KIND_MISMATCH.value == "label_kind_mismatch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signal_quality'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/signal_quality/schema.py
"""Result types for the signal quality harness (S9.1).

A REFUSAL AND A MEASUREMENT ARE DIFFERENT TYPES, deliberately. One model with
optional metric fields would let a refusal travel as ``{"auc": null}``, which a
caller reads as "AUC could not be computed" when the truth is "we refused to
compute anything and here is why". Two types make the wrong reading
unrepresentable rather than merely discouraged -- the same move S7.1 made for
"no column can hold a document".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class LabelKind(StrEnum):
    """What a label is ABOUT. See schema 4.1: OutcomeLabel is a fraud
    vocabulary and InterviewOutcome is a hiring one, and scoring a signal
    against the wrong one produces a plausible-looking number for a question
    nobody asked."""

    FRAUD = "fraud"
    HIRE = "hire"


class MetricKind(StrEnum):
    AUC = "auc"
    BRIER = "brier"
    LIFT = "lift"


class RefusalReason(StrEnum):
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    DEGENERATE_CLASS = "degenerate_class"
    LABEL_KIND_MISMATCH = "label_kind_mismatch"


class CalibrationBin(BaseModel):
    """One bin of the reliability curve. ``n`` is NOT optional: a bin's
    predicted-vs-observed gap is uninterpretable without it, and a chart that
    hides it is how a 2-sample bin gets read as a finding."""

    model_config = ConfigDict(frozen=True)

    lower: float
    upper: float
    n: int
    mean_predicted: Optional[float] = None
    observed_rate: Optional[float] = None


class BandLift(BaseModel):
    model_config = ConfigDict(frozen=True)

    band: str
    n: int
    positive_rate: float
    lift: Optional[float] = None  # None when the base rate is 0


class SignalMeasured(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: str
    sufficient: Literal[True] = True
    n: int
    positives: int
    auc: Optional[float] = None
    brier: Optional[float] = None
    curve: tuple[CalibrationBin, ...] = ()
    lift: tuple[BandLift, ...] = ()


class SignalRefused(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: str
    sufficient: Literal[False] = False
    reason: RefusalReason
    n: int
    detail: str


SignalResult = Union[SignalMeasured, SignalRefused]


class Population(BaseModel):
    """The run's own population. A metric without this is not interpretable,
    so it is never optional and never omitted from a response."""

    model_config = ConfigDict(frozen=True)

    label_source: str
    label_kind: LabelKind
    include_operator_labels: bool
    reports_considered: int
    labels_usable: int
    earliest_report: Optional[datetime] = None
    latest_report: Optional[datetime] = None


class SignalQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime = Field(default_factory=datetime.now)
    population: Population
    signals: tuple[SignalResult, ...] = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_schema.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/ tests/test_signal_quality_schema.py
git commit -m "feat(s91): result types -- a refusal and a measurement are different types

One model with optional metric fields would let a refusal travel as
{\"auc\": null}, which reads as 'could not compute' rather than 'we refused
to, and here is why'. Two types make the wrong reading unrepresentable."
```

---

### Task 2: AUC — rank-based, with an explicit tie policy

**Files:**
- Create: `src/app/signal_quality/metrics.py`
- Test: `tests/test_signal_quality_metrics.py`

**Interfaces:**
- Consumes: nothing (`metrics.py` imports nothing from `app/` — that is what makes every number here assertable against a hand-computed fixture).
- Produces: `DegenerateClass(Exception)`, `average_ranks(values) -> list[float]`, `auc(scores, labels) -> float`.

Ties are the reason this is written out rather than imported. Resume scores tie constantly — banded signals tie by design — and a tie policy chosen silently by a library is a number that looks computed but is arbitrary.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_metrics.py
import pytest

from app.signal_quality.metrics import DegenerateClass, auc, average_ranks


def test_average_ranks_are_1_based_and_average_ties():
    assert average_ranks([0.1, 0.2, 0.3]) == [1.0, 2.0, 3.0]
    # Two values tied for ranks 1 and 2 -> both get 1.5.
    assert average_ranks([0.5, 0.5]) == [1.5, 1.5]
    # Three-way tie across ranks 2,3,4 -> all get 3.0.
    assert average_ranks([0.1, 0.7, 0.7, 0.7]) == [1.0, 3.0, 3.0, 3.0]


def test_auc_perfect_separation_is_one():
    """Hand-computable: ranks 1,2,3,4; positives hold 3+4=7.
    (7 - 2*3/2) / (2*2) = 4/4 = 1.0"""
    assert auc([0.1, 0.2, 0.3, 0.4], [False, False, True, True]) == 1.0


def test_auc_perfect_inversion_is_zero():
    assert auc([0.1, 0.2, 0.3, 0.4], [True, True, False, False]) == 0.0


def test_auc_all_tied_is_one_half():
    """THE TIE POLICY, PINNED. Every score identical means the signal
    separates nothing, and averaged ranks are what make that come out at
    exactly 0.5. A sort-based implementation returns 0.0 or 1.0 here
    depending on sort stability -- silently, and only on real data."""
    assert auc([0.5, 0.5, 0.5, 0.5], [True, False, True, False]) == 0.5
    assert auc([0.5, 0.5], [True, False]) == 0.5


def test_auc_partial_tie_hand_computed():
    """scores 0.2, 0.4, 0.4, 0.9  labels F, T, F, T
    ranks: 1, 2.5, 2.5, 4  -> positives hold 2.5 + 4 = 6.5
    (6.5 - 2*3/2) / (2*2) = 3.5/4 = 0.875"""
    assert auc([0.2, 0.4, 0.4, 0.9], [False, True, False, True]) == 0.875


def test_auc_refuses_a_degenerate_class():
    """AUC is UNDEFINED with one class present. Libraries variously return
    0.5, nan, or raise -- and 0.5 reads as 'no signal' when the truth is
    'no measurement'."""
    with pytest.raises(DegenerateClass):
        auc([0.1, 0.2, 0.3], [True, True, True])
    with pytest.raises(DegenerateClass):
        auc([0.1, 0.2, 0.3], [False, False, False])


def test_auc_refuses_mismatched_lengths():
    with pytest.raises(ValueError):
        auc([0.1, 0.2], [True])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_metrics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signal_quality.metrics'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/signal_quality/metrics.py
"""Pure metric functions (S9.1).

THIS MODULE IMPORTS NOTHING FROM ``app/``. That is deliberate: the numbers here
are the sprint's entire deliverable, so every one of them is asserted against a
fixture computed by hand, and a unit test of this module is a unit test in the
strict sense.

No numpy, no scipy, no scikit-learn -- and not merely to avoid a dependency.
AUC's TIE POLICY is the reason. Resume signals tie constantly (every ``*_band``
ties by construction), and a library that picks a tie rule silently produces a
number that looks computed and is arbitrary. Averaged ranks are written out
below so the rule is readable and testable.
"""

from __future__ import annotations

from typing import Sequence


class DegenerateClass(ValueError):
    """Raised when one class is absent, which makes AUC undefined.

    Deliberately an exception and not a sentinel return: 0.5 is a real AUC
    value meaning "separates nothing", and returning it here would conflate a
    measured null result with an impossible measurement.
    """


def average_ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks, ties sharing their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def auc(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Area under the ROC curve, via the Mann-Whitney U identity.

    AUC = (sum of positive ranks - n_pos*(n_pos+1)/2) / (n_pos * n_neg)
    """
    if len(scores) != len(labels):
        raise ValueError(f"length mismatch: {len(scores)} scores, {len(labels)} labels")
    n_pos = sum(1 for x in labels if x)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise DegenerateClass(
            f"AUC undefined: {n_pos} positive and {n_neg} negative labels"
        )
    ranks = average_ranks(scores)
    rank_sum = sum(r for r, lab in zip(ranks, labels) if lab)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_metrics.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/metrics.py tests/test_signal_quality_metrics.py
git commit -m "feat(s91): AUC by Mann-Whitney, with the tie policy written out and pinned

Ties are why this is not imported. Every *_band signal ties by construction,
and a library picking a tie rule silently yields a number that looks computed
and is arbitrary. test_auc_all_tied_is_one_half is the pin: a sort-based
implementation returns 0.0 or 1.0 there depending on sort stability."
```

---

### Task 3: Brier score and the calibration curve

**Files:**
- Modify: `src/app/signal_quality/metrics.py`
- Test: `tests/test_signal_quality_metrics.py`

**Interfaces:**
- Consumes: `DegenerateClass` from Task 2.
- Produces: `brier(scores, labels) -> float`, `calibration_curve(scores, labels, *, bins=10) -> list[tuple[float, float, int, Optional[float], Optional[float]]]` returning `(lower, upper, n, mean_predicted, observed_rate)` per bin.

The curve returns plain tuples, not `CalibrationBin` — `metrics.py` imports nothing from `app/`, including our own schema. The service does the mapping.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_quality_metrics.py
from app.signal_quality.metrics import brier, calibration_curve


def test_brier_is_mean_squared_error():
    assert brier([0.0, 1.0], [False, True]) == 0.0
    assert brier([1.0, 0.0], [False, True]) == 1.0
    assert brier([0.5, 0.5], [False, True]) == 0.25
    # (0.2-0)^2 + (0.6-1)^2 = 0.04 + 0.16 = 0.20, over 2 -> 0.10
    assert brier([0.2, 0.6], [False, True]) == pytest.approx(0.10)


def test_brier_refuses_mismatched_lengths():
    with pytest.raises(ValueError):
        brier([0.1], [True, False])


def test_calibration_curve_bins_are_half_open_and_carry_n():
    # 4 bins of width 0.25. Scores 0.1 | 0.3 | 0.6, 0.7 | (none)
    curve = calibration_curve(
        [0.1, 0.3, 0.6, 0.7], [False, True, True, True], bins=4
    )
    assert len(curve) == 4
    assert [b[2] for b in curve] == [1, 1, 2, 0]
    assert curve[0][:2] == (0.0, 0.25)
    # bin 2 holds 0.6 and 0.7 -> mean predicted 0.65, both positive -> 1.0
    assert curve[2][3] == pytest.approx(0.65)
    assert curve[2][4] == pytest.approx(1.0)


def test_an_empty_bin_reports_none_not_zero():
    """An empty bin is NOT a bin whose observed rate is 0. Reporting 0.0
    would draw a point on a reliability chart where no data exists."""
    curve = calibration_curve([0.1], [True], bins=4)
    assert curve[3][2] == 0
    assert curve[3][3] is None
    assert curve[3][4] is None


def test_score_of_exactly_one_lands_in_the_last_bin():
    """Half-open bins would drop 1.0 entirely, and a silently discarded
    sample is worse than a wrong one."""
    curve = calibration_curve([1.0], [True], bins=4)
    assert [b[2] for b in curve] == [0, 0, 0, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_metrics.py -q`
Expected: FAIL — `ImportError: cannot import name 'brier'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/app/signal_quality/metrics.py
from typing import Optional


def brier(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Mean squared error against the 0/1 label. Lower is better.

    Only meaningful for a score already constrained to [0,1] -- which every
    signal routed here is, by its own ``Field(ge=0.0, le=1.0)``. An unbounded
    count has no Brier score, and ``signals.py`` is what stops one being asked
    for.
    """
    if len(scores) != len(labels):
        raise ValueError(f"length mismatch: {len(scores)} scores, {len(labels)} labels")
    if not scores:
        raise ValueError("brier requires at least one observation")
    return sum((s - (1.0 if lab else 0.0)) ** 2 for s, lab in zip(scores, labels)) / len(scores)


def calibration_curve(
    scores: Sequence[float], labels: Sequence[bool], *, bins: int = 10
) -> list[tuple[float, float, int, Optional[float], Optional[float]]]:
    """Reliability curve over fixed-width bins.

    Returns ``(lower, upper, n, mean_predicted, observed_rate)`` per bin --
    plain tuples, because this module imports nothing from ``app/``, including
    our own schema. The service maps these onto ``CalibrationBin``.

    AN EMPTY BIN REPORTS ``None``, NOT ``0.0``. Zero is a real observed rate
    meaning "none of these were positive"; an empty bin means "nothing was
    predicted here". Collapsing them draws a point on a chart where no data
    exists. No smoothing and no interpolation for the same reason.
    """
    if len(scores) != len(labels):
        raise ValueError(f"length mismatch: {len(scores)} scores, {len(labels)} labels")
    if bins < 1:
        raise ValueError("bins must be >= 1")

    width = 1.0 / bins
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for s, lab in zip(scores, labels):
        idx = int(s / width)
        # A score of exactly 1.0 computes to idx == bins. Half-open bins would
        # drop it, and a silently discarded sample is worse than a wrong one.
        idx = min(max(idx, 0), bins - 1)
        buckets[idx].append((s, lab))

    out: list[tuple[float, float, int, Optional[float], Optional[float]]] = []
    for i, bucket in enumerate(buckets):
        lower, upper = i * width, (i + 1) * width
        if not bucket:
            out.append((lower, upper, 0, None, None))
            continue
        mean_pred = sum(s for s, _ in bucket) / len(bucket)
        observed = sum(1 for _, lab in bucket if lab) / len(bucket)
        out.append((lower, upper, len(bucket), mean_pred, observed))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_metrics.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/metrics.py tests/test_signal_quality_metrics.py
git commit -m "feat(s91): Brier and the reliability curve, with empty bins reporting None

An empty bin is not a bin whose observed rate is zero. Zero means 'none of
these were positive'; empty means 'nothing was predicted here'. Collapsing
them draws a point on a chart where no data exists, so no smoothing and no
interpolation."
```

---

### Task 4: Lift by band

**Files:**
- Modify: `src/app/signal_quality/metrics.py`
- Test: `tests/test_signal_quality_metrics.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `lift_by_band(bands, labels) -> list[tuple[str, int, float, Optional[float]]]` returning `(band, n, positive_rate, lift)`, ordered by band name.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_quality_metrics.py
from app.signal_quality.metrics import lift_by_band


def test_lift_is_band_rate_over_base_rate():
    """4 samples, 2 positive -> base rate 0.5.
    'high': 2 samples both positive -> rate 1.0, lift 2.0
    'low':  2 samples none positive -> rate 0.0, lift 0.0"""
    rows = lift_by_band(
        ["high", "high", "low", "low"], [True, True, False, False]
    )
    assert rows == [("high", 2, 1.0, 2.0), ("low", 2, 0.0, 0.0)]


def test_bands_are_ordered_by_name_for_stable_output():
    rows = lift_by_band(["z", "a"], [True, False])
    assert [r[0] for r in rows] == ["a", "z"]


def test_lift_is_none_when_the_base_rate_is_zero():
    """Division by zero has no useful answer here, and 0.0 would read as
    'this band underperforms' when nothing was positive anywhere."""
    rows = lift_by_band(["a", "b"], [False, False])
    assert [r[3] for r in rows] == [None, None]
    assert [r[2] for r in rows] == [0.0, 0.0]


def test_lift_refuses_mismatched_lengths():
    with pytest.raises(ValueError):
        lift_by_band(["a"], [True, False])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_metrics.py -q`
Expected: FAIL — `ImportError: cannot import name 'lift_by_band'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/app/signal_quality/metrics.py


def lift_by_band(
    bands: Sequence[str], labels: Sequence[bool]
) -> list[tuple[str, int, float, Optional[float]]]:
    """Positive rate per band against the overall base rate.

    Returns ``(band, n, positive_rate, lift)`` ordered by band NAME, not by
    rate: a stable order is what makes two runs diffable, and the natural
    ordinal order of a band enum is not knowable here (this module imports
    nothing from ``app/``).

    ``lift`` is ``None`` when the base rate is 0 -- returning 0.0 would read as
    "this band underperforms" when the truth is that nothing was positive
    anywhere.
    """
    if len(bands) != len(labels):
        raise ValueError(f"length mismatch: {len(bands)} bands, {len(labels)} labels")
    if not bands:
        raise ValueError("lift_by_band requires at least one observation")

    base = sum(1 for x in labels if x) / len(labels)
    grouped: dict[str, list[bool]] = {}
    for band, lab in zip(bands, labels):
        grouped.setdefault(band, []).append(lab)

    out: list[tuple[str, int, float, Optional[float]]] = []
    for band in sorted(grouped):
        members = grouped[band]
        rate = sum(1 for x in members if x) / len(members)
        out.append((band, len(members), rate, (rate / base) if base > 0 else None))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_metrics.py -q`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/metrics.py tests/test_signal_quality_metrics.py
git commit -m "feat(s91): lift by band, ordered by name and None on a zero base rate"
```

---

### Task 5: The cross-report outcome reader

**Files:**
- Modify: `src/app/reports/store.py` (the `ReportStore` Protocol and `SqlReportStore`)
- Test: `tests/test_report_store_outcome_scan.py`

**Interfaces:**
- Consumes: `Report`, `OutcomeRecord` (existing).
- Produces: `ReportStore.report_level_outcomes() -> list[tuple[Report, OutcomeRecord]]`.

Today's readers are `outcomes(report_id)` and `outcomes_for_org(org_id, report_id)` — both report-scoped. The harness needs a cross-report scan. There is exactly one implementation and the tests exercise it against real SQLite, so there is no in-memory fake to drift.

Note this reader returns **only `claim_id IS NULL`** rows. A per-claim outcome judges a claim; every signal measured in this sprint is report-level. Filtering here rather than in the label source keeps the rule in one place.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_store_outcome_scan.py
from datetime import datetime, timedelta, timezone

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import Report


def _report(store, candidate_id, *, created_at):
    rep = Report(candidate_id=candidate_id, created_at=created_at)
    store.save(rep)
    return rep


def test_scan_returns_every_report_level_outcome_joined_to_its_report(
    report_store, candidate_id
):
    now = datetime.now(timezone.utc)
    rep = _report(report_store, candidate_id, created_at=now)
    report_store.add_outcome(
        OutcomeRecord(
            report_id=rep.id,
            outcome=OutcomeLabel.VERIFIED_FABRICATED,
            recorded_by=OutcomeSource.ORG,
            recorded_at=now + timedelta(days=1),
        )
    )
    rows = report_store.report_level_outcomes()
    assert len(rows) == 1
    got_report, got_outcome = rows[0]
    assert got_report.id == rep.id
    assert got_outcome.outcome is OutcomeLabel.VERIFIED_FABRICATED
    assert got_outcome.recorded_by is OutcomeSource.ORG


def test_scan_excludes_per_claim_outcomes(report_store, candidate_id):
    """A per-claim outcome judges ONE CLAIM. Every signal this harness
    measures is report-level, so scoring a whole-report number against a
    single claim's verdict is a category error one column over."""
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    rep.verdicts.append(_a_verdict("claim-1"))
    report_store.save(rep)
    report_store.add_outcome(
        OutcomeRecord(
            report_id=rep.id,
            claim_id="claim-1",
            outcome=OutcomeLabel.VERIFIED_FABRICATED,
            recorded_by=OutcomeSource.ORG,
            recorded_at=now + timedelta(days=1),
        )
    )
    assert report_store.report_level_outcomes() == []


def test_scan_is_cross_report_and_cross_org(report_store, candidate_id):
    now = datetime.now(timezone.utc)
    for i in range(3):
        rep = _report(report_store, candidate_id, created_at=now + timedelta(hours=i))
        report_store.add_outcome(
            OutcomeRecord(
                report_id=rep.id,
                outcome=OutcomeLabel.VERIFIED_GENUINE,
                recorded_by=OutcomeSource.OPERATOR,
                recorded_at=now + timedelta(days=1),
            )
        )
    assert len(report_store.report_level_outcomes()) == 3


def test_scan_is_empty_when_nothing_was_judged(report_store, candidate_id):
    _report(report_store, candidate_id, created_at=datetime.now(timezone.utc))
    assert report_store.report_level_outcomes() == []
```

Add a `_a_verdict` helper mirroring whatever `tests/` already uses to build a `CoherenceVerdict`; reuse the existing helper if one exists rather than writing a second.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report_store_outcome_scan.py -q`
Expected: FAIL — `AttributeError: 'SqlReportStore' object has no attribute 'report_level_outcomes'`

- [ ] **Step 3: Write minimal implementation**

Add to the `ReportStore` Protocol:

```python
    def report_level_outcomes(self) -> list[tuple[Report, "OutcomeRecord"]]: ...
```

And to `SqlReportStore`:

```python
    def report_level_outcomes(self) -> list[tuple[Report, OutcomeRecord]]:
        """Every report-level outcome joined to the report it judges.

        ADMIN PLANE ONLY -- cross-tenant by construction. There is deliberately
        no org-scoped variant: a per-org view of "how well does the screen
        work" is a different question with its own sample-size problem, and the
        org-plane readers above (``outcomes_for_org``) stay report-scoped.

        ``claim_id IS NULL`` only. A per-claim outcome judges one claim, and
        every signal S9.1 measures is report-level. The filter lives here so
        the rule has one home rather than one per label source.

        Ordered by ``(report_id, recorded_at, id)`` so a caller reducing many
        outcomes to one label gets a deterministic 'earliest' -- including when
        two rows share a timestamp, which a same-second double submit produces.
        """
        with self._session_factory() as session:
            rows = session.execute(
                select(ReportRow, OutcomeRow)
                .join(OutcomeRow, OutcomeRow.report_id == ReportRow.id)
                .where(OutcomeRow.claim_id.is_(None))
                .order_by(OutcomeRow.report_id, OutcomeRow.recorded_at, OutcomeRow.id)
            ).all()
            return [(_to_report(rep_row), _to_outcome(out_row)) for rep_row, out_row in rows]
```

Reuse the existing row→model helpers in this file (the ones `get()` and `outcomes()` already call) rather than writing new ones — find their real names and use those; `_to_report` / `_to_outcome` above are placeholders for whatever they are actually called.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report_store_outcome_scan.py -q`
Expected: PASS (4 tests)

Then run the full store suite to confirm nothing regressed:
Run: `python -m pytest tests/ -q -k "report_store or outcome"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/reports/store.py tests/test_report_store_outcome_scan.py
git commit -m "feat(s91): a cross-report outcome reader, report-level rows only

Both existing readers are report-scoped; the harness needs a scan. claim_id
IS NULL is filtered HERE rather than in each label source, so the rule that a
per-claim judgment is about a different object has one home.

Ordered by (report_id, recorded_at, id): the id tiebreak is what makes
'earliest outcome wins' deterministic when two rows share a timestamp, which
a same-second double submit produces."
```

---

### Task 6: The label seam and `OutcomesLabelSource`

**Files:**
- Create: `src/app/signal_quality/labels.py`
- Test: `tests/test_signal_quality_labels.py`

**Interfaces:**
- Consumes: `LabelKind` (Task 1), `report_level_outcomes()` (Task 5).
- Produces: `LabeledReport` dataclass (`report: Report`, `positive: bool`, `labeled_at: datetime`), `LabelSource` Protocol (`name: str`, `kind: LabelKind`, `labeled() -> list[LabeledReport]`), `OutcomesLabelSource`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_labels.py
from datetime import datetime, timedelta, timezone

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import Report
from app.signal_quality.labels import OutcomesLabelSource
from app.signal_quality.schema import LabelKind


def _judged(report_store, candidate_id, label, *, source=OutcomeSource.ORG, lag_days=1):
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    report_store.save(rep)
    report_store.add_outcome(
        OutcomeRecord(
            report_id=rep.id, outcome=label, recorded_by=source,
            recorded_at=now + timedelta(days=lag_days),
        )
    )
    return rep


def test_source_declares_the_fraud_kind(report_store):
    src = OutcomesLabelSource(report_store)
    assert src.kind is LabelKind.FRAUD
    assert src.name == "outcomes"


def test_fabricated_is_positive_and_genuine_is_negative(report_store, candidate_id):
    _judged(report_store, candidate_id, OutcomeLabel.VERIFIED_FABRICATED)
    _judged(report_store, candidate_id, OutcomeLabel.VERIFIED_GENUINE)
    labeled = OutcomesLabelSource(report_store).labeled()
    assert sorted(x.positive for x in labeled) == [False, True]


def test_clarified_and_inconclusive_are_excluded_not_coerced(report_store, candidate_id):
    """Forcing these to 0 or 1 manufactures a judgment a human declined to
    give, and it would inflate n while doing it."""
    _judged(report_store, candidate_id, OutcomeLabel.CANDIDATE_CLARIFIED)
    _judged(report_store, candidate_id, OutcomeLabel.INCONCLUSIVE)
    assert OutcomesLabelSource(report_store).labeled() == []


def test_operator_labels_are_excluded_by_default(report_store, candidate_id):
    """OutcomeRow.recorded_by exists for this sprint. Its docstring: 'PI-9
    must never train on our operator's self-labels believing a customer
    produced them; that is circular.'"""
    _judged(
        report_store, candidate_id, OutcomeLabel.VERIFIED_FABRICATED,
        source=OutcomeSource.OPERATOR,
    )
    assert OutcomesLabelSource(report_store).labeled() == []
    included = OutcomesLabelSource(report_store, include_operator_labels=True).labeled()
    assert len(included) == 1


def test_an_outcome_recorded_before_its_report_is_not_a_label(report_store, candidate_id):
    """Leakage. A judgment predating the prediction cannot have been informed
    by it, and a row that fed the prediction must never become its label."""
    _judged(report_store, candidate_id, OutcomeLabel.VERIFIED_FABRICATED, lag_days=-1)
    assert OutcomesLabelSource(report_store).labeled() == []


def test_an_outcome_exactly_on_as_of_is_excluded(report_store, candidate_id):
    """STRICTLY after, matching build_label's rule exactly."""
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    report_store.save(rep)
    report_store.add_outcome(
        OutcomeRecord(
            report_id=rep.id, outcome=OutcomeLabel.VERIFIED_FABRICATED,
            recorded_by=OutcomeSource.ORG, recorded_at=now,
        )
    )
    assert OutcomesLabelSource(report_store).labeled() == []


def test_one_label_per_report_and_it_is_the_earliest(report_store, candidate_id):
    """A report can carry contradictory outcomes from different orgs. The
    earliest qualifying one wins: it is the judgment closest to the
    prediction, and it is the only rule under which recording a NEW outcome
    tomorrow does not silently change a measurement taken today."""
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    report_store.save(rep)
    for lag, label in (
        (5, OutcomeLabel.VERIFIED_GENUINE),
        (1, OutcomeLabel.VERIFIED_FABRICATED),
    ):
        report_store.add_outcome(
            OutcomeRecord(
                report_id=rep.id, outcome=label, recorded_by=OutcomeSource.ORG,
                recorded_at=now + timedelta(days=lag),
            )
        )
    labeled = OutcomesLabelSource(report_store).labeled()
    assert len(labeled) == 1
    assert labeled[0].positive is True  # the day-1 FABRICATED, not the day-5 GENUINE


def test_an_excluded_label_does_not_block_a_later_qualifying_one(report_store, candidate_id):
    """INCONCLUSIVE first, then a real judgment. 'Earliest' means earliest
    QUALIFYING -- an excluded row must not consume the report's one slot."""
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    report_store.save(rep)
    for lag, label in (
        (1, OutcomeLabel.INCONCLUSIVE),
        (2, OutcomeLabel.VERIFIED_FABRICATED),
    ):
        report_store.add_outcome(
            OutcomeRecord(
                report_id=rep.id, outcome=label, recorded_by=OutcomeSource.ORG,
                recorded_at=now + timedelta(days=lag),
            )
        )
    labeled = OutcomesLabelSource(report_store).labeled()
    assert len(labeled) == 1 and labeled[0].positive is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_labels.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signal_quality.labels'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/signal_quality/labels.py
"""The label seam (S9.1, spec 4).

TWO GROUND TRUTHS EXIST AND THEY ARE NOT INTERCHANGEABLE. ``OutcomeLabel`` is a
FRAUD vocabulary (verified_genuine / verified_fabricated / ...) and
``InterviewOutcome`` is a HIRING one (hired / offer / rejected / ...). Scoring
``depth_score`` against ``VERIFIED_FABRICATED`` is not a weak measurement -- it
is a category error that still produces a plausible-looking AUC. So a source
DECLARES the kind it emits, a signal declares the kind it can be scored by, and
``service.py`` refuses the mismatch rather than computing it.

``outcomes`` is the DEFAULT because it is what the fraud-screen wedge actually
collects. The ledger needs N organisations before it holds anything, and the
GTM keeps it off the pitch -- so a ledger-only harness would still be empty
after the launch PI-9 was gated on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from app.ledger.consent import as_utc
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.report import Report
from app.signal_quality.schema import LabelKind

#: CANDIDATE_CLARIFIED and INCONCLUSIVE appear in NEITHER set, deliberately.
#: Forcing them to 0 or 1 manufactures a judgment a human declined to give, and
#: it would inflate `n` while doing it. See spec 11.2 -- CANDIDATE_CLARIFIED may
#: be the wedge's most interesting label and it deserves its own analysis, not a
#: coin flip.
_POSITIVE: frozenset[OutcomeLabel] = frozenset({OutcomeLabel.VERIFIED_FABRICATED})
_NEGATIVE: frozenset[OutcomeLabel] = frozenset({OutcomeLabel.VERIFIED_GENUINE})


@dataclass(frozen=True)
class LabeledReport:
    """One report and the single human judgment that scores it."""

    report: Report
    positive: bool
    labeled_at: datetime


class LabelSource(Protocol):
    name: str
    kind: LabelKind

    def labeled(self) -> list[LabeledReport]: ...


def _binary(label: OutcomeLabel) -> Optional[bool]:
    if label in _POSITIVE:
        return True
    if label in _NEGATIVE:
        return False
    return None


class OutcomesLabelSource:
    """Human fraud judgments from the ``outcomes`` table.

    Reads through ``report_level_outcomes()``, which already excludes per-claim
    rows and orders deterministically.
    """

    name = "outcomes"
    kind = LabelKind.FRAUD

    def __init__(self, report_store, *, include_operator_labels: bool = False) -> None:
        self._store = report_store
        self.include_operator_labels = include_operator_labels

    def labeled(self) -> list[LabeledReport]:
        chosen: dict[str, LabeledReport] = {}
        for report, rec in self._store.report_level_outcomes():
            if (
                not self.include_operator_labels
                and rec.recorded_by is OutcomeSource.OPERATOR
            ):
                continue

            # LEAKAGE, the same rule build_label uses: strictly after. A
            # judgment at or before the report's creation cannot have been
            # informed by it.
            recorded_at, as_of = as_utc(rec.recorded_at), as_utc(report.created_at)
            if recorded_at <= as_of:
                continue

            positive = _binary(rec.outcome)
            if positive is None:
                continue

            # Earliest QUALIFYING wins. The scan is already ordered by
            # (report_id, recorded_at, id), so the first survivor per report is
            # the earliest -- and an excluded row above never consumed the slot.
            if report.id not in chosen:
                chosen[report.id] = LabeledReport(
                    report=report, positive=positive, labeled_at=recorded_at
                )
        return list(chosen.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_labels.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/labels.py tests/test_signal_quality_labels.py
git commit -m "feat(s91): the label seam, and outcomes as the default fraud ground truth

A source declares the KIND it emits, because OutcomeLabel is a fraud
vocabulary and InterviewOutcome is a hiring one. Leakage uses build_label's
own rule -- strictly after -- and one report yields one label: the earliest
QUALIFYING one, so recording a new outcome tomorrow cannot silently change a
measurement taken today."
```

---

### Task 7: `LedgerLabelSource`

**Files:**
- Modify: `src/app/signal_quality/labels.py`
- Test: `tests/test_signal_quality_labels.py`

**Interfaces:**
- Consumes: `build_label` from `app.features.training` (**unedited**), `LabeledReport`, `LabelKind`.
- Produces: `LedgerLabelSource(report_store, ledger_store)` with `kind = LabelKind.HIRE`, `name = "ledger"`.

`build_label` is pure and correct — this wraps it, passing `as_of=report.created_at` and the candidate's ledger rows, and maps `TrainingLabel.hired` to `positive`. An unobserved or withheld label yields nothing.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_signal_quality_labels.py
from app.signal_quality.labels import LedgerLabelSource


def test_ledger_source_declares_the_hire_kind(report_store, ledger_store):
    src = LedgerLabelSource(report_store, ledger_store)
    assert src.kind is LabelKind.HIRE
    assert src.name == "ledger"


def test_ledger_source_is_empty_with_no_ledger_rows(report_store, ledger_store, candidate_id):
    """The honest day-one state, and the reason depth.* refuses."""
    rep = Report(candidate_id=candidate_id, created_at=datetime.now(timezone.utc))
    report_store.save(rep)
    assert LedgerLabelSource(report_store, ledger_store).labeled() == []


def test_ledger_source_yields_a_positive_for_a_hire_after_the_report(
    report_store, ledger_store, candidate_id, an_interview_record
):
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    report_store.save(rep)
    an_interview_record(candidate_id, outcome="hired", interviewed_at=now + timedelta(days=7))
    labeled = LedgerLabelSource(report_store, ledger_store).labeled()
    assert len(labeled) == 1 and labeled[0].positive is True


def test_ledger_source_respects_build_labels_leakage_rule(
    report_store, ledger_store, candidate_id, an_interview_record
):
    """A record at or before as_of fed the features and must never be the
    label. Asserted through this source rather than trusting build_label,
    because the wiring is what is new here."""
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)
    report_store.save(rep)
    an_interview_record(candidate_id, outcome="hired", interviewed_at=now)
    assert LedgerLabelSource(report_store, ledger_store).labeled() == []
```

`an_interview_record` is a fixture to add to `tests/conftest.py` if no equivalent exists — check first; the S4.4 tests already build interview records and that helper should be reused rather than duplicated.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_labels.py -q`
Expected: FAIL — `ImportError: cannot import name 'LedgerLabelSource'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/app/signal_quality/labels.py
from app.features.training import build_label


class LedgerLabelSource:
    """Hiring outcomes from the PI-3 ledger, via S4.4's ``build_label``.

    ``build_label`` IS NOT EDITED BY THIS SPRINT. It is pure, consent-gated,
    audited and leakage-free, and it already answers exactly the question this
    source needs; wrapping it keeps one implementation of the strict-after rule
    rather than a second that agrees today.

    Expected to return NOTHING until real organisations submit interview
    records. That is the honest day-one state and the reason every ``depth.*``
    signal refuses -- see spec 4.1.
    """

    name = "ledger"
    kind = LabelKind.HIRE

    def __init__(self, report_store, ledger_store) -> None:
        self._reports = report_store
        self._ledger = ledger_store

    def labeled(self) -> list[LabeledReport]:
        out: list[LabeledReport] = []
        for report in self._reports.all_reports_with_candidates():
            cid = report.candidate_id
            if cid is None:
                continue
            label = build_label(
                as_of=report.created_at,
                interview_records=self._ledger.records_for_candidate(cid),
                coding_rounds=self._ledger.coding_rounds_for_candidate(cid),
                consent_allowed=True,
            )
            if not label.observed or label.withheld or label.event_at is None:
                continue
            out.append(
                LabeledReport(
                    report=report, positive=bool(label.hired), labeled_at=label.event_at
                )
            )
        return out
```

This needs one more store reader — `all_reports_with_candidates()`, returning every report whose `candidate_id` is not null. Add it to the `ReportStore` Protocol and `SqlReportStore` in the same commit, with a test in `tests/test_report_store_outcome_scan.py`:

```python
def test_all_reports_with_candidates_skips_ad_hoc_reports(report_store, candidate_id):
    """POST /evaluate reports have candidate_id=None and no owner to join a
    ledger row to."""
    report_store.save(Report(candidate_id=candidate_id, created_at=datetime.now(timezone.utc)))
    report_store.save(Report(candidate_id=None, created_at=datetime.now(timezone.utc)))
    got = report_store.all_reports_with_candidates()
    assert len(got) == 1 and got[0].candidate_id == candidate_id
```

```python
    def all_reports_with_candidates(self) -> list[Report]:
        """Every stored report attached to a candidate, oldest first.

        Ad-hoc ``POST /evaluate`` reports carry ``candidate_id=None`` and are
        excluded: there is no subject to join a ledger row to. Admin plane
        only, cross-tenant by construction.
        """
        with self._session_factory() as session:
            rows = session.execute(
                select(ReportRow)
                .where(ReportRow.candidate_id.is_not(None))
                .order_by(ReportRow.created_at, ReportRow.id)
            ).scalars().all()
            return [_to_report(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_labels.py tests/test_report_store_outcome_scan.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/labels.py src/app/reports/store.py tests/
git commit -m "feat(s91): the ledger label source, wrapping build_label unedited

build_label is pure, consent-gated and leakage-free and already answers this
question. Wrapping it keeps ONE implementation of the strict-after rule rather
than a second that agrees today. Expected to return nothing until real orgs
submit interview records -- the honest day-one state, and why depth.* refuses."
```

---

### Task 8: The signal registry

**Files:**
- Create: `src/app/signal_quality/signals.py`
- Test: `tests/test_signal_quality_signals.py`

**Interfaces:**
- Consumes: `LabelKind`, `MetricKind` (Task 1), `Report` and the S2.x assessment models.
- Produces: `SignalSpec` dataclass (`name`, `kind`, `metrics: frozenset[MetricKind]`, `extract: Callable[[Report], float | None]`, `band: bool`), and `SIGNALS: tuple[SignalSpec, ...]` — the twelve of spec §4.1.

A signal declares which metrics are meaningful for it. Bands get lift; `[0,1]` scores get AUC and Brier; unbounded counts get AUC and lift but never Brier.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_signals.py
from app.schemas.fabrication import (
    AIGenerationAssessment,
    FabricationRiskAssessment,
    FabricationRiskBand,
)
from app.schemas.report import DepthBand, Report
from app.signal_quality.schema import LabelKind, MetricKind
from app.signal_quality.signals import SIGNALS, by_name


def test_all_twelve_signals_are_registered():
    assert len(SIGNALS) == 12
    names = {s.name for s in SIGNALS}
    assert "fabrication_risk.score" in names
    assert "ai_generation.likelihood" in names
    assert "cross_field.major_findings" in names
    assert "depth_score" in names


def test_fraud_and_hire_signals_are_split_nine_and_three():
    fraud = [s for s in SIGNALS if s.kind is LabelKind.FRAUD]
    hire = [s for s in SIGNALS if s.kind is LabelKind.HIRE]
    assert (len(fraud), len(hire)) == (9, 3)


def test_a_band_gets_lift_and_never_brier():
    """Brier is undefined on anything not constrained to [0,1], and an
    ordinal encoded as a float would produce one anyway."""
    for spec in SIGNALS:
        if spec.band:
            assert spec.metrics == frozenset({MetricKind.LIFT})


def test_an_unbounded_count_gets_auc_and_lift_but_never_brier():
    spec = by_name("cross_field.major_findings")
    assert MetricKind.BRIER not in spec.metrics
    assert {MetricKind.AUC, MetricKind.LIFT} <= spec.metrics


def test_extract_reads_the_score_off_the_report_body():
    rep = Report(
        depth_score=0.42,
        fabrication_risk=FabricationRiskAssessment(score=0.77, band=FabricationRiskBand.ELEVATED),
        ai_generation=AIGenerationAssessment(likelihood=0.31),
    )
    assert by_name("depth_score").extract(rep) == 0.42
    assert by_name("fabrication_risk.score").extract(rep) == 0.77
    assert by_name("ai_generation.likelihood").extract(rep) == 0.31
    assert by_name("fabrication_risk.band").extract(rep) == "elevated"


def test_extract_returns_none_when_the_assessment_is_absent():
    """Pre-S2.4 stored reports and ad-hoc runs carry None. Those rows drop out
    of THAT signal's sample and must not become a 0.0, which would read as a
    confident 'no risk'."""
    rep = Report(depth_score=0.5)
    assert rep.fabrication_risk is None
    assert by_name("fabrication_risk.score").extract(rep) is None
    assert by_name("fabrication_risk.band").extract(rep) is None
    assert by_name("depth_score").extract(rep) == 0.5


def test_depth_band_extracts_the_enum_value():
    rep = Report(depth_band=DepthBand.INSUFFICIENT_SIGNAL)
    assert by_name("depth_band").extract(rep) == "insufficient_signal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_signals.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signal_quality.signals'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/signal_quality/signals.py
"""The twelve measured signals (S9.1, spec 4.1).

A SIGNAL DECLARES ITS OWN METRIC SET. The alternative -- computing four numbers
for everything and letting a reader work out which are nonsense -- puts a Brier
score on an unbounded count and an AUC on an ordinal that was cast to a float to
make it fit. Both look like measurements.

  - a [0,1] score        -> AUC + Brier
  - a *_band ordinal     -> lift only
  - an unbounded count   -> AUC + lift, never Brier

AN ABSENT ASSESSMENT EXTRACTS AS None, NEVER 0.0. Pre-S2.x stored reports and
ad-hoc POST /evaluate runs carry None for these, and 0.0 on a risk score reads
as a confident "no risk" rather than "never assessed". A None drops that report
from THAT signal's sample and is counted in nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from app.schemas.report import Report
from app.signal_quality.schema import LabelKind, MetricKind

_SCORE = frozenset({MetricKind.AUC, MetricKind.BRIER})
_BAND = frozenset({MetricKind.LIFT})
_COUNT = frozenset({MetricKind.AUC, MetricKind.LIFT})


@dataclass(frozen=True)
class SignalSpec:
    name: str
    kind: LabelKind
    metrics: frozenset[MetricKind]
    extract: Callable[[Report], Optional[Union[float, str]]]
    #: True when `extract` yields a category rather than a number. Drives which
    #: metric family the service routes it to, and is asserted against
    #: `metrics` by a guard test.
    band: bool = False


def _opt(assessment, attr: str):
    return None if assessment is None else getattr(assessment, attr)


def _band_value(assessment, attr: str = "band"):
    got = _opt(assessment, attr)
    return None if got is None else str(got.value)


SIGNALS: tuple[SignalSpec, ...] = (
    # --- FRAUD: scored by `outcomes`, measurable today -----------------------
    SignalSpec("fabrication_risk.score", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.fabrication_risk, "score")),
    SignalSpec("fabrication_risk.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.fabrication_risk), band=True),
    SignalSpec("ai_generation.likelihood", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.ai_generation, "likelihood")),
    SignalSpec("ai_generation.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.ai_generation), band=True),
    SignalSpec("cross_field.score", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.cross_field, "score")),
    SignalSpec("cross_field.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.cross_field), band=True),
    SignalSpec("cross_field.major_findings", LabelKind.FRAUD, _COUNT,
               lambda r: None if r.cross_field is None else float(
                   sum(1 for f in r.cross_field.findings if f.severity.value == "major")
               )),
    SignalSpec("resume_farm.score", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.resume_farm, "score")),
    SignalSpec("resume_farm.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.resume_farm), band=True),
    # --- HIRE: scored by the ledger, refuses until real orgs exist -----------
    SignalSpec("depth_score", LabelKind.HIRE, _SCORE, lambda r: r.depth_score),
    SignalSpec("depth_band", LabelKind.HIRE, _BAND,
               lambda r: str(r.depth_band.value), band=True),
    SignalSpec("overall_confidence", LabelKind.HIRE, _SCORE,
               lambda r: r.overall_confidence),
)


def by_name(name: str) -> SignalSpec:
    for spec in SIGNALS:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown signal {name!r}")
```

Note `cross_field.major_findings` uses `f.severity.value == "major"`; import `FindingSeverity` and compare to the enum member instead if the surrounding code does that — match the file's neighbours.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_signals.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/signals.py tests/test_signal_quality_signals.py
git commit -m "feat(s91): the twelve signals, each declaring its own metric set

Computing four numbers for everything puts a Brier score on an unbounded count
and an AUC on an ordinal cast to a float to make it fit -- both of which look
like measurements. A band gets lift, a [0,1] score gets AUC and Brier, a count
gets AUC and lift.

An absent assessment extracts as None, never 0.0: pre-S2.x reports carry None,
and 0.0 on a risk score reads as a confident 'no risk'."
```

---

### Task 9: The service, and the three refusals

**Files:**
- Create: `src/app/signal_quality/service.py`
- Test: `tests/test_signal_quality_service.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `measure(label_source, *, min_samples, bins=10) -> SignalQualityReport`.

This is where the sprint's claim lives: a harness that **cannot** emit a number on an insufficient sample.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_service.py
from datetime import datetime, timedelta, timezone

from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.schemas.fabrication import FabricationRiskAssessment, FabricationRiskBand
from app.schemas.report import Report
from app.signal_quality.labels import OutcomesLabelSource
from app.signal_quality.schema import (
    LabelKind, RefusalReason, SignalMeasured, SignalRefused,
)
from app.signal_quality.service import measure


def _seed(report_store, candidate_id, score, band, positive, *, i=0):
    now = datetime.now(timezone.utc) + timedelta(seconds=i)
    rep = Report(
        candidate_id=candidate_id,
        created_at=now,
        fabrication_risk=FabricationRiskAssessment(score=score, band=band),
    )
    report_store.save(rep)
    report_store.add_outcome(
        OutcomeRecord(
            report_id=rep.id,
            outcome=OutcomeLabel.VERIFIED_FABRICATED if positive else OutcomeLabel.VERIFIED_GENUINE,
            recorded_by=OutcomeSource.ORG,
            recorded_at=now + timedelta(days=1),
        )
    )


def _of(report, name):
    return next(s for s in report.signals if s.signal == name)


def test_below_the_threshold_every_signal_refuses(report_store, candidate_id):
    for i in range(4):
        _seed(report_store, candidate_id, 0.5, FabricationRiskBand.ELEVATED, i % 2 == 0, i=i)
    got = measure(OutcomesLabelSource(report_store), min_samples=30)
    assert all(isinstance(s, SignalRefused) for s in got.signals)
    assert _of(got, "fabrication_risk.score").reason is RefusalReason.INSUFFICIENT_SAMPLES
    assert _of(got, "fabrication_risk.score").n == 4


def test_a_refusal_carries_no_metric_fields_at_all(report_store, candidate_id):
    _seed(report_store, candidate_id, 0.5, FabricationRiskBand.ELEVATED, True)
    got = measure(OutcomesLabelSource(report_store), min_samples=30)
    dumped = _of(got, "fabrication_risk.score").model_dump()
    assert "auc" not in dumped and "brier" not in dumped and "curve" not in dumped


def test_the_threshold_releases_at_exactly_n(report_store, candidate_id):
    """n-1 refuses, n answers. A threshold nobody has seen release is a
    threshold nobody knows the direction of."""
    for i in range(5):
        _seed(report_store, candidate_id, 0.9 if i % 2 == 0 else 0.1,
              FabricationRiskBand.ELEVATED, i % 2 == 0, i=i)
    assert isinstance(_of(measure(OutcomesLabelSource(report_store), min_samples=6),
                          "fabrication_risk.score"), SignalRefused)
    assert isinstance(_of(measure(OutcomesLabelSource(report_store), min_samples=5),
                          "fabrication_risk.score"), SignalMeasured)


def test_a_degenerate_class_refuses_rather_than_reporting_one_half(
    report_store, candidate_id
):
    """0.5 is a real AUC meaning 'separates nothing'. Emitting it for an
    impossible measurement is the failure this refusal exists for."""
    for i in range(10):
        _seed(report_store, candidate_id, 0.5, FabricationRiskBand.ELEVATED, True, i=i)
    got = _of(measure(OutcomesLabelSource(report_store), min_samples=5),
              "fabrication_risk.score")
    assert isinstance(got, SignalRefused)
    assert got.reason is RefusalReason.DEGENERATE_CLASS


def test_hire_signals_refuse_against_a_fraud_source(report_store, candidate_id):
    """The load-bearing refusal: depth_score cannot be scored by a fraud
    label, and the harness says so instead of producing a plausible number."""
    for i in range(10):
        _seed(report_store, candidate_id, 0.9 if i % 2 else 0.1,
              FabricationRiskBand.ELEVATED, i % 2 == 0, i=i)
    got = measure(OutcomesLabelSource(report_store), min_samples=5)
    depth = _of(got, "depth_score")
    assert isinstance(depth, SignalRefused)
    assert depth.reason is RefusalReason.LABEL_KIND_MISMATCH
    assert isinstance(_of(got, "fabrication_risk.score"), SignalMeasured)


def test_a_perfect_signal_measures_at_auc_one(report_store, candidate_id):
    for i in range(10):
        positive = i % 2 == 0
        _seed(report_store, candidate_id, 0.9 if positive else 0.1,
              FabricationRiskBand.ELEVATED, positive, i=i)
    got = _of(measure(OutcomesLabelSource(report_store), min_samples=5),
              "fabrication_risk.score")
    assert isinstance(got, SignalMeasured)
    assert got.auc == 1.0
    assert got.n == 10 and got.positives == 5


def test_the_population_is_always_reported(report_store, candidate_id):
    _seed(report_store, candidate_id, 0.5, FabricationRiskBand.ELEVATED, True)
    pop = measure(OutcomesLabelSource(report_store), min_samples=30).population
    assert pop.label_source == "outcomes"
    assert pop.label_kind is LabelKind.FRAUD
    assert pop.include_operator_labels is False
    assert pop.labels_usable == 1
    assert pop.earliest_report is not None and pop.latest_report is not None


def test_reports_missing_an_assessment_leave_that_signals_sample(
    report_store, candidate_id
):
    """A None must not become a 0.0 and must not inflate n."""
    now = datetime.now(timezone.utc)
    rep = Report(candidate_id=candidate_id, created_at=now)  # no fabrication_risk
    report_store.save(rep)
    report_store.add_outcome(
        OutcomeRecord(
            report_id=rep.id, outcome=OutcomeLabel.VERIFIED_FABRICATED,
            recorded_by=OutcomeSource.ORG, recorded_at=now + timedelta(days=1),
        )
    )
    for i in range(6):
        _seed(report_store, candidate_id, 0.9 if i % 2 else 0.1,
              FabricationRiskBand.ELEVATED, i % 2 == 0, i=i + 1)
    got = measure(OutcomesLabelSource(report_store), min_samples=5)
    assert _of(got, "fabrication_risk.score").n == 6      # not 7
    assert got.population.labels_usable == 7              # the population is honest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signal_quality.service'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/signal_quality/service.py
"""Orchestration and the three refusals (S9.1, spec 5).

THE REFUSALS ARE THE SPRINT'S CENTRAL CLAIM. PI-9 was gated on real
organisations submitting outcomes, on the grounds that "a harness measuring
test fixtures would have been actively misleading". That is an argument against
a harness which emits a number no matter what it is fed -- so this one cannot.
Below the sample floor, on a one-class sample, or on a signal the label source
cannot score, the result is a ``SignalRefused`` carrying no metric fields at
all.

No boot refusal is added. The eight that exist guard configurations producing a
service that LOOKS healthy while being unsafe or unusable; this is advisory
analysis tooling, and refusing to start over a report nobody has asked for yet
would be a ninth that earns nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.signal_quality.labels import LabelSource, LabeledReport
from app.signal_quality.metrics import (
    DegenerateClass, auc, brier, calibration_curve, lift_by_band,
)
from app.signal_quality.schema import (
    BandLift, CalibrationBin, LabelKind, MetricKind, Population, RefusalReason,
    SignalMeasured, SignalQualityReport, SignalRefused, SignalResult,
)
from app.signal_quality.signals import SIGNALS, SignalSpec


def _measure_one(
    spec: SignalSpec, labeled: list[LabeledReport], *, min_samples: int,
    source_kind: LabelKind, bins: int,
) -> SignalResult:
    if spec.kind is not source_kind:
        # Refusal 3, and the load-bearing one. A fraud label cannot score a
        # hiring signal; the pairing would still produce a plausible number.
        return SignalRefused(
            signal=spec.name, reason=RefusalReason.LABEL_KIND_MISMATCH, n=0,
            detail=(
                f"{spec.name} is scored by {spec.kind.value} labels; this run "
                f"used a {source_kind.value} source"
            ),
        )

    pairs = []
    for lr in labeled:
        value = spec.extract(lr.report)
        if value is None:
            continue  # never assessed -- not a zero, and not counted
        pairs.append((value, lr.positive))

    n = len(pairs)
    if n < min_samples:
        return SignalRefused(
            signal=spec.name, reason=RefusalReason.INSUFFICIENT_SAMPLES, n=n,
            detail=f"{n} usable labels, need {min_samples}",
        )

    labels = [p for _, p in pairs]
    positives = sum(1 for p in labels if p)
    if positives == 0 or positives == n:
        return SignalRefused(
            signal=spec.name, reason=RefusalReason.DEGENERATE_CLASS, n=n,
            detail=(
                f"all {n} labels are {'positive' if positives else 'negative'}; "
                "AUC is undefined and a lift baseline is meaningless"
            ),
        )

    if spec.band:
        rows = lift_by_band([str(v) for v, _ in pairs], labels)
        return SignalMeasured(
            signal=spec.name, n=n, positives=positives,
            lift=tuple(
                BandLift(band=b, n=cnt, positive_rate=rate, lift=lift)
                for b, cnt, rate, lift in rows
            ),
        )

    values = [float(v) for v, _ in pairs]
    try:
        area = auc(values, labels)
    except DegenerateClass:  # pragma: no cover - the check above already caught it
        area = None

    measured = {"signal": spec.name, "n": n, "positives": positives, "auc": area}
    if MetricKind.BRIER in spec.metrics:
        measured["brier"] = brier(values, labels)
        measured["curve"] = tuple(
            CalibrationBin(
                lower=lo, upper=hi, n=cnt, mean_predicted=mp, observed_rate=obs
            )
            for lo, hi, cnt, mp, obs in calibration_curve(values, labels, bins=bins)
        )
    if MetricKind.LIFT in spec.metrics:
        measured["lift"] = tuple(
            BandLift(band=b, n=cnt, positive_rate=rate, lift=lift)
            for b, cnt, rate, lift in lift_by_band([str(v) for v in values], labels)
        )
    return SignalMeasured(**measured)


def measure(
    label_source: LabelSource, *, min_samples: int, bins: int = 10
) -> SignalQualityReport:
    """Measure every registered signal against one label source."""
    labeled = label_source.labeled()
    created = [lr.report.created_at for lr in labeled]

    return SignalQualityReport(
        generated_at=datetime.now(timezone.utc),
        population=Population(
            label_source=label_source.name,
            label_kind=label_source.kind,
            include_operator_labels=bool(
                getattr(label_source, "include_operator_labels", False)
            ),
            reports_considered=len(labeled),
            labels_usable=len(labeled),
            earliest_report=min(created) if created else None,
            latest_report=max(created) if created else None,
        ),
        signals=tuple(
            _measure_one(
                spec, labeled, min_samples=min_samples,
                source_kind=label_source.kind, bins=bins,
            )
            for spec in SIGNALS
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_service.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/service.py tests/test_signal_quality_service.py
git commit -m "feat(s91): the service, and the three refusals that answer PI-9's gate

PI-9 was gated on the grounds that 'a harness measuring test fixtures would
have been actively misleading'. That argues against a harness which emits a
number no matter what it is fed, so this one cannot: below the sample floor,
on a one-class sample, or on a signal the source cannot score, the result
carries no metric fields at all."
```

---

### Task 10: The config knob and the admin route

**Files:**
- Modify: `config.yaml`, `src/app/core/config.py`, `src/app/api/routes.py`
- Test: `tests/test_signal_quality_route.py`

**Interfaces:**
- Consumes: `measure` (Task 9), `OutcomesLabelSource`, `LedgerLabelSource`.
- Produces: `GET /admin/signal-quality?source=outcomes|ledger&include_operator_labels=false`, handler `signal_quality_report`, `response_model=SignalQualityReport`.

The route goes on `router` (which carries `Depends(require_api_key)`), so it inherits the admin gate and the route-table guard passes without an edit. `operation_id` is assigned from the handler name by the loop in `create_app`, so the handler name must be unique and readable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_route.py
def test_route_is_admin_gated(client_without_key):
    assert client_without_key.get("/admin/signal-quality").status_code in (401, 403)


def test_route_returns_refusals_on_an_empty_database(client):
    body = client.get("/admin/signal-quality").json()
    assert body["population"]["label_source"] == "outcomes"
    assert body["population"]["labels_usable"] == 0
    assert all(s["sufficient"] is False for s in body["signals"])
    assert len(body["signals"]) == 12


def test_the_ledger_source_is_selectable(client):
    body = client.get("/admin/signal-quality?source=ledger").json()
    assert body["population"]["label_source"] == "ledger"
    assert body["population"]["label_kind"] == "hire"
    fraud = next(s for s in body["signals"] if s["signal"] == "fabrication_risk.score")
    assert fraud["reason"] == "label_kind_mismatch"


def test_an_unknown_source_is_refused_with_422(client):
    assert client.get("/admin/signal-quality?source=nonsense").status_code == 422


def test_operator_labels_are_opt_in_over_the_wire(client):
    body = client.get("/admin/signal-quality?include_operator_labels=true").json()
    assert body["population"]["include_operator_labels"] is True
```

Use whatever the existing admin-route tests use for `client` / `client_without_key`; do not invent new fixtures.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_route.py -q`
Expected: FAIL — 404 on the route

- [ ] **Step 3: Write minimal implementation**

In `config.yaml`, beside the other PI-8/PI-9 blocks:

```yaml
# --- Signal quality harness (PI-9, S9.1) --------------------------------------
# Does any advisory number predict what a human concluded? The harness REFUSES
# to answer below this many usable labels rather than reporting a number
# computed from a handful of rows -- which is the objection that gated PI-9 in
# the first place. Advisory analysis only: nothing here changes a score, a band
# or a threshold.
min_signal_quality_samples: 30          # usable labels per signal, or it refuses
signal_quality_curve_bins: 10           # reliability-curve bins; empty bins report null
```

In `src/app/core/config.py`, beside the neighbouring fields:

```python
    # --- Signal quality harness (PI-9, S9.1) ------------------------------------
    # The sample floor below which the harness refuses rather than reports. 30 is
    # a convention, not a derivation -- it is the point where a proportion's
    # confidence interval stops spanning most of [0,1] -- and it is a knob
    # precisely because the right value is an empirical question this repo has no
    # data to answer yet.
    min_signal_quality_samples: int = Field(default=30, ge=1)
    signal_quality_curve_bins: int = Field(default=10, ge=1)
```

In `src/app/api/routes.py`, near the other admin routes:

```python
@router.get("/admin/signal-quality", response_model=SignalQualityReport)
async def signal_quality_report(
    request: Request,
    source: Literal["outcomes", "ledger"] = "outcomes",
    include_operator_labels: bool = False,
) -> SignalQualityReport:
    """Do the advisory numbers predict what a human concluded? Admin plane.

    ADMIN ONLY, AND THERE IS NO ORG-PLANE VARIANT. This report is cross-tenant
    by construction: an organisation must not be able to learn how well the
    fraud screen performs against other organisations' candidates. The honest
    per-org version ("how is it doing on MY pipeline") is a different question
    with its own sample-size problem, and inventing it here would ship a number
    computed from a handful of rows.

    Expect refusals. Below the sample floor, on a one-class sample, or for a
    signal this source cannot score, each signal says so and carries no
    numbers -- see app/signal_quality/service.py.
    """
    services = _services(request)
    if source == "ledger":
        label_source = LedgerLabelSource(services.report_store, services.ledger)
    else:
        label_source = OutcomesLabelSource(
            services.report_store, include_operator_labels=include_operator_labels
        )
    return measure(
        label_source,
        min_samples=services.settings.min_signal_quality_samples,
        bins=services.settings.signal_quality_curve_bins,
    )
```

Add the imports at the top of `routes.py` beside the existing `app.*` imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_route.py tests/test_route_table_guard.py tests/test_openapi_contract.py -q`
Expected: PASS. The route-table guard and the OpenAPI contract must both stay green — the guard's `>= 60` route-count assertion grows by one, and `operation_id` comes from the handler name automatically.

- [ ] **Step 5: Commit**

```bash
git add config.yaml src/app/core/config.py src/app/api/routes.py tests/test_signal_quality_route.py
git commit -m "feat(s91): GET /admin/signal-quality, admin plane and no org variant

Cross-tenant by construction: an org must not learn how well the screen
performs on other orgs' candidates. The per-org version is a different
question with its own sample-size problem, and inventing it here would ship a
number computed from a handful of rows.

min_signal_quality_samples defaults to 30 -- a convention, not a derivation,
and a knob because the right value is an empirical question we cannot yet
answer."
```

---

### Task 11: The CLI entry point

**Files:**
- Create: `src/app/signal_quality/report.py`
- Test: `tests/test_signal_quality_cli.py`

**Interfaces:**
- Consumes: `measure`, both label sources, `revision_state`.
- Produces: `main(argv=None) -> int`. Exit 0 with JSON on stdout; **exit 3** with a sentence on stderr against an unmigrated database.

S8.6 found the retention CLI exiting 1 with a forty-line traceback on an unmigrated database — the most likely thing a cron meets first. Same treatment here from the start.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_quality_cli.py
import json

from app.signal_quality.report import main


def test_cli_prints_the_report_as_the_last_line_of_stdout(capsys, migrated_settings):
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["population"]["label_source"] == "outcomes"
    assert len(payload["signals"]) == 12


def test_cli_refuses_an_unmigrated_database_with_exit_3(capsys, unmigrated_settings):
    """A cron is the caller nobody is watching when it goes wrong. S8.6 found
    the retention sweep answering this case with a forty-line traceback and
    exit 1; an operator reading a log at 3am gets a sentence."""
    assert main([]) == 3
    err = capsys.readouterr().err
    assert "not migrated" in err
    assert "Traceback" not in err


def test_cli_accepts_the_ledger_source(capsys, migrated_settings):
    assert main(["--source", "ledger"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["population"]["label_kind"] == "hire"
```

`migrated_settings` / `unmigrated_settings` mirror whatever `tests/test_retention_cli.py` (or its equivalent) already uses for the same two states — find it and reuse it rather than building a second.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_quality_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.signal_quality.report'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/app/signal_quality/report.py
"""``python -m app.signal_quality.report`` (S9.1).

A CLI as well as a route, for the same reason the retention sweep has both:
there is no scheduler anywhere in ``app/``, so this is an INVOCABLE thing and
never a daemon.

OUTPUT CONTRACT: the report is the LAST line of stdout, and it is JSON. This
process shares stdout with the structured log, so the stream is a sequence of
JSON documents rather than one. A test pins it, because an output contract
nobody asserts is a comment.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    from app.core.config import get_settings
    from app.core.db import make_engine, make_session_factory
    from app.core.migrate import revision_state
    from app.ledger.store import LedgerStore
    from app.reports.store import SqlReportStore
    from app.signal_quality.labels import LedgerLabelSource, OutcomesLabelSource
    from app.signal_quality.service import measure

    parser = argparse.ArgumentParser(prog="app.signal_quality.report")
    parser.add_argument(
        "--source", choices=("outcomes", "ledger"), default="outcomes",
        help="which ground truth to measure against (default: outcomes)",
    )
    parser.add_argument(
        "--include-operator-labels", action="store_true",
        help="include our OWN operators' judgments. Off by default: training on "
             "them believing a customer produced them is circular.",
    )
    args = parser.parse_args(argv)
    settings = get_settings()

    # S8.6, FOUND BY RUNNING IT: the retention CLI met an unmigrated database
    # with a forty-line SQLAlchemy traceback and exit 1. This process reads
    # only, but it is reachable the same way -- an operator shell, or a cron
    # container that starts before the web service has migrated anything.
    current, head = revision_state(settings)
    if current != head:
        print(
            "signal_quality_refused: the database is not migrated (schema is at "
            f"{current or 'no revision at all'}, head is {head}). Nothing was "
            "read. The web service applies migrations on boot; run it, or "
            "`alembic upgrade head`, first.",
            file=sys.stderr,
        )
        return 3

    factory = make_session_factory(make_engine(settings.candidates_db_url))
    reports = SqlReportStore(factory)
    if args.source == "ledger":
        source = LedgerLabelSource(reports, LedgerStore(factory))
    else:
        source = OutcomesLabelSource(
            reports, include_operator_labels=args.include_operator_labels
        )

    report = measure(
        source,
        min_samples=settings.min_signal_quality_samples,
        bins=settings.signal_quality_curve_bins,
    )
    print(json.dumps(report.model_dump(mode="json")))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

Check `LedgerStore`'s real constructor signature before wiring it — match how `app/services/__init__.py` builds it rather than assuming it takes a session factory.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_quality_cli.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/app/signal_quality/report.py tests/test_signal_quality_cli.py
git commit -m "feat(s91): the CLI, exiting 3 on an unmigrated database

S8.6 found the retention sweep meeting that case with a forty-line traceback
and exit 1 -- the most likely thing a cron encounters first. An operator
reading a log at 3am gets a sentence instead, from the start this time."
```

---

### Task 12: The mutation pass

**Files:**
- Create: `tests/test_signal_quality_mutants.py` (or extend the repo's existing mutation harness — check how S8.3's 12/12 mutants were run and follow it)

**Interfaces:**
- Consumes: everything.
- Produces: a mutation report. The numbers are this sprint's entire deliverable, so a suite that survives mutating them is not testing them.

Each mutant is a deliberate one-line break; the pass requires that at least one existing test fails for each.

- [ ] **Step 1: Write the mutant list**

Mutants that MUST be killed:

1. `auc`: drop the tie-averaging (rank ties by position) → `test_auc_all_tied_is_one_half`
2. `auc`: `>=` instead of `>` in the rank loop's tie scan → `test_auc_partial_tie_hand_computed`
3. `auc`: `n_pos * (n_pos - 1) / 2` instead of `+ 1` → the perfect-separation tests
4. `auc`: return 0.5 instead of raising on a degenerate class → `test_auc_refuses_a_degenerate_class`
5. `brier`: absolute error instead of squared → `test_brier_is_mean_squared_error`
6. `calibration_curve`: empty bin reports 0.0 instead of None → `test_an_empty_bin_reports_none_not_zero`
7. `calibration_curve`: drop the `min(idx, bins-1)` clamp → `test_score_of_exactly_one_lands_in_the_last_bin`
8. `lift_by_band`: return 0.0 instead of None on a zero base rate → `test_lift_is_none_when_the_base_rate_is_zero`
9. `labels`: `<` instead of `<=` in the leakage check → `test_an_outcome_exactly_on_as_of_is_excluded`
10. `labels`: include operator labels by default → `test_operator_labels_are_excluded_by_default`
11. `labels`: last qualifying outcome wins instead of earliest → `test_one_label_per_report_and_it_is_the_earliest`
12. `labels`: treat `CANDIDATE_CLARIFIED` as positive → `test_clarified_and_inconclusive_are_excluded_not_coerced`
13. `service`: `<=` instead of `<` on the sample floor → `test_the_threshold_releases_at_exactly_n`
14. `service`: skip the label-kind check → `test_hire_signals_refuse_against_a_fraud_source`
15. `service`: extract `None` as 0.0 → `test_reports_missing_an_assessment_leave_that_signals_sample`

- [ ] **Step 2: Apply each mutant and confirm a test fails**

For each: apply the one-line change, run the named test, confirm FAIL, revert.

Run per mutant: `python -m pytest tests/test_signal_quality_*.py -q`
Expected: at least one FAIL per mutant, 0 survivors.

- [ ] **Step 3: Record the result**

Record `15/15 mutants dead` (or fix the gap and re-run). A surviving mutant means a test is missing, not that the mutant is acceptable.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test(s91): 15/15 mutants dead over the metrics and the refusals

The numbers are this sprint's whole deliverable, so a suite that survives
mutating them is not testing them. Every tie rule, every boundary and every
refusal direction has a mutant that kills it."
```

---

### Task 13: The smoke, the docs, and the roadmap

**Files:**
- Create: `scripts/smoke_s91.py` (match the naming and structure of `scripts/smoke_s86.py`)
- Create: `SIGNALS.md` (root, beside `SCREENING.md` / `OPERATING.md`)
- Modify: `docs/ROADMAP.md`, `OPERATING.md`, `DEPLOY.md`

**Interfaces:**
- Consumes: the whole sprint.
- Produces: a green smoke run and the sprint's written record.

- [ ] **Step 1: Write the smoke script**

Follow the existing smoke pattern exactly — uvicorn started with a positive startup marker (never a `code != 0` check, which S8.6 showed can pass because the harness killed a hung process). Checks:

1. server boots, `/healthz` is healthy
2. `GET /admin/signal-quality` without a key → 401/403
3. with a key on an empty DB → 200, all twelve signals refuse, `reason=insufficient_samples`
4. seed 30+ reports with outcomes over HTTP, mixed labels
5. re-read → `fabrication_risk.score` is now measured, with an `auc` and an `n`
6. every `depth.*` signal still refuses with `label_kind_mismatch`
7. `?source=ledger` → the fraud signals refuse with `label_kind_mismatch`
8. `?include_operator_labels=true` is reflected in `population`
9. seed a one-class set and confirm `degenerate_class`
10. `python -m app.signal_quality.report` exits 0 and prints JSON as the last stdout line
11. the same CLI against a fresh unmigrated SQLite file exits **3** with no traceback

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_s91.py`
Expected: all checks pass. Record the count (e.g. `smoke_s91 11/11`).

- [ ] **Step 3: Run the full suite and the UI checks**

Run: `python -m pytest -q`
Expected: 1854 + the new tests, all passing, no regressions.

Run the three UI verification layers, which must be unchanged (this sprint touches no frontend):
`node scripts/check_ui_bindings.js` → 402/402
`python scripts/check_ui_screening_contract.py` → 31/31
`python scripts/check_ui_screening_browser.py` → 19/19

- [ ] **Step 4: Write `SIGNALS.md`**

A root doc in the house style covering: what the harness measures and what it refuses; the two label vocabularies and why they cannot be crossed; the twelve signals and their metric sets; how to read a refusal; why `depth.*` reports nothing today and what would change that; the `min_signal_quality_samples` knob and that 30 is a convention rather than a derivation.

Add the CLI to `OPERATING.md` beside the retention sweep, and add the route to `DEPLOY.md`'s surface list if it enumerates routes.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

Add a PI-9 block to the status board with S9.1 marked done, update "Current state" and the session log with the measured numbers (suite count, smoke count, mutants), and record the two spec corrections found while planning: the signal table was under-counted at eight (`ai_generation.likelihood` and `cross_field.score` are `[0,1]` scores, not band-only), and per-claim outcomes must be excluded because every measured signal is report-level.

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke_s91.py SIGNALS.md OPERATING.md DEPLOY.md docs/ROADMAP.md
git commit -m "docs(s91): SIGNALS.md, the smoke, and the roadmap

Records the two spec corrections the planning pass found: the signal table was
under-counted at eight, because ai_generation.likelihood and cross_field.score
are [0,1] scores rather than band-only; and per-claim outcomes are excluded,
because every signal measured here is report-level and scoring one against a
single claim's verdict is the category error one column over."
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 the gate answered by refusal | 9 |
| §2.1 Report body as predictor source | 8 |
| §2.2 outcomes as default ground truth | 6 |
| §3.1 naming | 1 |
| §3.2 four modules | 1, 2, 6, 9 |
| §3.3 no new dependency, pure metrics | 2, 3, 4 |
| §4 the label seam + semantics | 6, 7 |
| §4.1 the twelve signals + metric sets | 8 |
| §4.2 label mapping, exclusions, report-level, earliest-wins | 5, 6 |
| §4.3 operator labels excluded by default | 6, 10, 11 |
| §5 the three refusals | 9 |
| §6 leakage | 6, 7 |
| §7.1 admin route | 10 |
| §7.2 CLI + unmigrated DB | 11 |
| §8 the store reader, no migration | 5, 7 |
| §9 testing incl. mutation + smoke | 2–12, 13 |
| §10 non-goals | respected throughout (no `build_label` edit, no signal retuning, no UI, no org-plane view) |

No gaps.

**Placeholder scan:** two deliberate "match the existing pattern" notes remain — the row→model helper names in Task 5, and the fixtures in Tasks 7/10/11. Both are instructions to reuse what exists rather than invent a second, which is the correct instruction; each names the file to look in.

**Type consistency:** `LabelKind`, `MetricKind`, `RefusalReason`, `SignalMeasured`, `SignalRefused`, `CalibrationBin`, `BandLift`, `Population`, `SignalQualityReport` are defined in Task 1 and used unchanged in 6–11. `LabeledReport(report, positive, labeled_at)` is defined in Task 6 and consumed identically in 7 and 9. `metrics.py` returns plain tuples throughout (Tasks 2–4) and only `service.py` maps them onto schema models (Task 9) — consistent with §3.2's "imports nothing from `app/`".
