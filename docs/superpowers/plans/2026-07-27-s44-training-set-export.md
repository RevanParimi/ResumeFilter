# S4.4 — Training-set Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Join each stored `ml_feature_vectors` row to a leakage-free ground-truth label derived only from ledger outcomes strictly after the vector's `as_of`, and export the result as a wide labeled CSV/parquet training set.

**Architecture:** A pure label module (`app/features/training.py`) computes a `TrainingLabel` from a candidate's ledger records filtered to `> as_of` (the risk.py/reputation.py purity pattern); a thin orchestrator reads the ledger only for consented vectors and audits each join; `export.py` grows label columns on top of the existing S4.2 wide pivot. No new table, no migration, no HTTP, no LLM, no config knob — read-side only, mirroring S4.3.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLAlchemy, pytest (fully offline), stdlib `csv`, optional `pyarrow`.

## Global Constraints

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` green before merge. (Baseline this sprint: **564** tests.)
- Advisory only — labels are training data, never a gate/auto-reject. `TrainingLabel` carries no verdict.
- No-leakage is the headline invariant: features from data `≤ as_of`; label from ledger events **strictly `> as_of`** (`interviewed_at`, `taken_at`). A record at exactly `as_of` fed the features and can never be a label.
- Consent: reuse the S4.2 decision stored in `MaterializedVector.consent_state` (`{"allowed": bool, ...}`); a withheld vector's label is withheld and its ledger is not read. Every join is audited `training.label`.
- `withdrawn` interview outcomes are excluded entirely (non-signal — mirrors S3.4 reputation).
- Hire-positive terminal set = `{hired, offer}`. Terminal-best ordering `hired>offer>advanced>rejected>no_show`.
- DPDP: no new candidate-linked table ⇒ no new erasure path. New `training.label` audit rows are candidate-linked and CASCADE on erasure like every other.
- All timestamps normalized through `app.ledger.consent.as_utc` before comparison (SQLite drops tzinfo; ledger converters return aware-UTC).
- Commit conventions: `feat(s44): …` / `test(s44): …` / `docs(s44): …`. **Do not** add a Claude co-author trailer.

## File Structure

- **Create** `app/features/training_schema.py` — `TrainingLabel`, `TrainingExample` (pydantic contracts).
- **Create** `app/features/training.py` — `_TERMINAL_ORDER`, `_HIRED_POSITIVE`, pure `build_label`, `build_training_example`, orchestrator `build_training_set`.
- **Modify** `app/ledger/store.py` — add `LedgerStore.audit_training_label`.
- **Modify** `app/features/export.py` — extract public `feature_columns` / `vector_cells`; add `_LABEL_COLUMNS`, `export_training_csv`, `export_training_parquet`.
- **Modify** `FEATURES.md` — add the S4.4 section.
- **Create** `scripts/smoke_s44.py` — end-to-end smoke.
- **Create** tests: `tests/test_features_training_schema.py`, `tests/test_features_build_label.py`, `tests/test_ledger_store_audit_training_label.py`, `tests/test_features_build_training_set.py`, `tests/test_features_training_export.py`.

---

### Task 1: Contracts — `TrainingLabel` / `TrainingExample`

**Files:**
- Create: `app/features/training_schema.py`
- Test: `tests/test_features_training_schema.py`

**Interfaces:**
- Consumes: `app.features.schema.FeatureVector`.
- Produces:
  - `TrainingLabel(hired: Optional[bool]=None, outcome: Optional[str]=None, coding_best_percentile: Optional[float]=None, event_at: Optional[datetime]=None, lag_days: Optional[float]=None, observed: bool=False, withheld: bool=False)`
  - `TrainingExample(vector: FeatureVector, label: TrainingLabel)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_training_schema.py
from datetime import datetime, timezone

from app.features.schema import FeatureVector
from app.features.training_schema import TrainingExample, TrainingLabel

T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_label_defaults_are_unobserved_and_not_withheld():
    lab = TrainingLabel()
    assert lab.hired is None and lab.outcome is None
    assert lab.coding_best_percentile is None and lab.event_at is None and lab.lag_days is None
    assert lab.observed is False and lab.withheld is False


def test_example_wraps_a_vector_and_label():
    fv = FeatureVector(candidate_id="c1", as_of=T, view_name="core_v1", view_version=1,
                       values={"candidate.num_skills": 3}, missing=())
    lab = TrainingLabel(hired=True, outcome="hired", event_at=T, lag_days=30.0, observed=True)
    ex = TrainingExample(vector=fv, label=lab)
    assert ex.vector.candidate_id == "c1"
    assert ex.label.hired is True and ex.label.outcome == "hired"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_training_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: app.features.training_schema`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/training_schema.py
"""S4.4 training-set contracts — leakage-free label + labeled example.

A TrainingLabel is derived ONLY from ledger outcomes strictly after the feature
vector's `as_of`. `observed=False` (right-censored) means no post-cut outcome
exists yet — NOT a negative. `withheld=True` means consent was not active at
`as_of` (the S4.2 decision), so no label was read and every value field is None.
Advisory: this is training data, never a gate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.features.schema import FeatureVector


class TrainingLabel(BaseModel):
    hired: Optional[bool] = None
    outcome: Optional[str] = None
    coding_best_percentile: Optional[float] = None
    event_at: Optional[datetime] = None
    lag_days: Optional[float] = None
    observed: bool = False
    withheld: bool = False


class TrainingExample(BaseModel):
    """One training row: an S4.2 feature vector joined to its post-cut label."""

    vector: FeatureVector
    label: TrainingLabel
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_training_schema.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/training_schema.py tests/test_features_training_schema.py
git commit -m "feat(s44): TrainingLabel + TrainingExample contracts"
```

---

### Task 2: Pure `build_label`

**Files:**
- Create: `app/features/training.py`
- Test: `tests/test_features_build_label.py`

**Interfaces:**
- Consumes: `TrainingLabel` (Task 1); `app.ledger.schema.{InterviewRecord, InterviewOutcome, InterviewStage, CodingRoundResult, CodingPlatform}`; `app.ledger.consent.as_utc`.
- Produces: `build_label(*, as_of: datetime, interview_records: Iterable[InterviewRecord], coding_rounds: Iterable[CodingRoundResult], consent_allowed: bool) -> TrainingLabel`. Module constants `_TERMINAL_ORDER: dict[InterviewOutcome,int]`, `_HIRED_POSITIVE: set[InterviewOutcome]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_build_label.py
from datetime import datetime, timedelta, timezone

from app.ledger.schema import (
    CodingPlatform, CodingRoundResult, InterviewOutcome, InterviewRecord, InterviewStage,
)
from app.features.training import build_label

T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _ir(outcome, when, rid="r"):
    return InterviewRecord(id=rid, org_id="o1", candidate_id="c1", consent_id="g1",
                           stage=InterviewStage.HM, outcome=outcome, interviewed_at=when,
                           created_at=when)


def _cr(pct, when, rid="cr"):
    return CodingRoundResult(id=rid, org_id="o1", candidate_id="c1", consent_id="g1",
                             platform=CodingPlatform.HACKERRANK, score=80.0, percentile=pct,
                             taken_at=when, created_at=when)


def test_record_at_exactly_as_of_does_not_leak_into_label():
    # A record AT the cut fed features; strictly-after is required to label.
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.HIRED, T)],
                      coding_rounds=[], consent_allowed=True)
    assert lab.observed is False and lab.hired is None and lab.outcome is None


def test_post_cut_hired_labels_positive_with_lag():
    when = T + timedelta(days=30)
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.HIRED, when)],
                      coding_rounds=[], consent_allowed=True)
    assert lab.observed is True and lab.hired is True and lab.outcome == "hired"
    assert lab.event_at == when and abs(lab.lag_days - 30.0) < 1e-6


def test_terminal_best_wins_and_withdrawn_excluded():
    recs = [
        _ir(InterviewOutcome.REJECTED, T + timedelta(days=5), "a"),
        _ir(InterviewOutcome.OFFER, T + timedelta(days=10), "b"),
        _ir(InterviewOutcome.WITHDRAWN, T + timedelta(days=20), "c"),
    ]
    lab = build_label(as_of=T, interview_records=recs, coding_rounds=[], consent_allowed=True)
    assert lab.outcome == "offer" and lab.hired is True
    assert lab.event_at == T + timedelta(days=10)  # earliest carrier of the winner


def test_event_at_is_earliest_carrier_of_winning_outcome():
    recs = [
        _ir(InterviewOutcome.HIRED, T + timedelta(days=40), "late"),
        _ir(InterviewOutcome.HIRED, T + timedelta(days=15), "early"),
    ]
    lab = build_label(as_of=T, interview_records=recs, coding_rounds=[], consent_allowed=True)
    assert lab.event_at == T + timedelta(days=15)


def test_advanced_and_rejected_are_not_hire_positive():
    for oc in (InterviewOutcome.ADVANCED, InterviewOutcome.REJECTED, InterviewOutcome.NO_SHOW):
        lab = build_label(as_of=T, interview_records=[_ir(oc, T + timedelta(days=3))],
                          coding_rounds=[], consent_allowed=True)
        assert lab.observed is True and lab.hired is False and lab.outcome == oc.value


def test_all_withdrawn_is_unobserved():
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.WITHDRAWN, T + timedelta(days=3))],
                      coding_rounds=[], consent_allowed=True)
    assert lab.observed is False and lab.hired is None


def test_censored_when_no_post_cut_record_but_coding_still_set():
    # pre-cut hired must NOT label; post-cut coding percentile is independent.
    lab = build_label(as_of=T,
                      interview_records=[_ir(InterviewOutcome.HIRED, T - timedelta(days=10))],
                      coding_rounds=[_cr(88.0, T + timedelta(days=5))], consent_allowed=True)
    assert lab.observed is False and lab.hired is None and lab.outcome is None
    assert lab.coding_best_percentile == 88.0


def test_coding_best_is_max_post_cut_percentile_ignoring_pre_and_nulls():
    rounds = [
        _cr(99.0, T - timedelta(days=1), "pre"),        # pre-cut -> ignored
        _cr(70.0, T + timedelta(days=1), "p70"),
        _cr(None, T + timedelta(days=2), "pnull"),      # no percentile -> ignored
        _cr(85.0, T + timedelta(days=3), "p85"),
    ]
    lab = build_label(as_of=T, interview_records=[], coding_rounds=rounds, consent_allowed=True)
    assert lab.coding_best_percentile == 85.0 and lab.observed is False


def test_consent_withheld_yields_fully_null_label_even_with_records():
    lab = build_label(as_of=T, interview_records=[_ir(InterviewOutcome.HIRED, T + timedelta(days=3))],
                      coding_rounds=[_cr(90.0, T + timedelta(days=3))], consent_allowed=False)
    assert lab.withheld is True and lab.observed is False
    assert lab.hired is None and lab.outcome is None and lab.coding_best_percentile is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_build_label.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_label'`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/features/training.py
"""S4.4 — join feature vectors to leakage-free labels from ledger outcomes.

`build_label` is pure (no store, no clock — the risk.py/reputation.py pattern):
it filters a candidate's ledger to events STRICTLY after the vector's `as_of`
(`interviewed_at`/`taken_at` > as_of) and reduces them to a `TrainingLabel`.
`build_training_set` is the thin orchestrator that reads the ledger only for
consented vectors and audits each join. No leakage: a record at exactly `as_of`
fed the features and never becomes a label.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from app.features.materialize import MaterializedVector
from app.features.training_schema import TrainingExample, TrainingLabel
from app.ledger.consent import as_utc
from app.ledger.schema import CodingRoundResult, InterviewOutcome, InterviewRecord

# Terminal-best ranking; WITHDRAWN is excluded entirely (non-signal, per S3.4).
_TERMINAL_ORDER: dict[InterviewOutcome, int] = {
    InterviewOutcome.HIRED: 5,
    InterviewOutcome.OFFER: 4,
    InterviewOutcome.ADVANCED: 3,
    InterviewOutcome.REJECTED: 2,
    InterviewOutcome.NO_SHOW: 1,
}
_HIRED_POSITIVE: set[InterviewOutcome] = {InterviewOutcome.HIRED, InterviewOutcome.OFFER}


def _withheld_label() -> TrainingLabel:
    return TrainingLabel(observed=False, withheld=True)


def build_label(
    *,
    as_of: datetime,
    interview_records: Iterable[InterviewRecord],
    coding_rounds: Iterable[CodingRoundResult],
    consent_allowed: bool,
) -> TrainingLabel:
    if not consent_allowed:
        return _withheld_label()

    cut = as_utc(as_of)

    # Best post-cut coding percentile (independent of interview observability).
    coding_pcts = [
        c.percentile
        for c in coding_rounds
        if as_utc(c.taken_at) > cut and c.percentile is not None
    ]
    coding_best = max(coding_pcts) if coding_pcts else None

    # Post-cut, non-withdrawn interview records (strict > cut = no leakage).
    post = [
        r
        for r in interview_records
        if as_utc(r.interviewed_at) > cut and r.outcome != InterviewOutcome.WITHDRAWN
    ]
    if not post:
        return TrainingLabel(
            observed=False, withheld=False, coding_best_percentile=coding_best
        )

    best_outcome = max(post, key=lambda r: _TERMINAL_ORDER[r.outcome]).outcome
    carriers = [r for r in post if r.outcome == best_outcome]
    event_at = min(as_utc(r.interviewed_at) for r in carriers)
    lag_days = (event_at - cut).total_seconds() / 86400.0

    return TrainingLabel(
        hired=best_outcome in _HIRED_POSITIVE,
        outcome=best_outcome.value,
        coding_best_percentile=coding_best,
        event_at=event_at,
        lag_days=lag_days,
        observed=True,
        withheld=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_build_label.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/training.py tests/test_features_build_label.py
git commit -m "feat(s44): pure build_label (leakage-free, terminal-best, censoring-aware)"
```

---

### Task 3: `LedgerStore.audit_training_label`

**Files:**
- Modify: `app/ledger/store.py` (add method next to `materialization_consent`, ~line 866)
- Test: `tests/test_ledger_store_audit_training_label.py`

**Interfaces:**
- Consumes: existing `self._audit`, `consent_logic.as_utc`, `self._session_factory`.
- Produces: `LedgerStore.audit_training_label(self, candidate_id: str, *, allowed: bool, as_of: datetime) -> None`. Writes one `audit_log` row, `action="training.label"`, `actor_type="system"`, `actor_id="platform"`, `entity_type="candidate"`, `details={"allowed": bool, "as_of": iso}`. Never raises for a withheld candidate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ledger_store_audit_training_label.py
from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store

RESUME = "Jane Rao\nML Engineer\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _setup():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    return ls, cid


def test_audit_training_label_allowed_writes_row():
    ls, cid = _setup()
    ls.audit_training_label(cid, allowed=True, as_of=T)
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "training.label"]
    assert len(audits) == 1
    assert audits[-1].details.get("allowed") is True
    assert audits[-1].details.get("as_of", "").startswith("2026-06-01")
    assert audits[-1].actor_type == "system" and audits[-1].candidate_id == cid


def test_audit_training_label_withheld_writes_row_and_does_not_raise():
    ls, cid = _setup()
    ls.audit_training_label(cid, allowed=False, as_of=T)
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "training.label"]
    assert len(audits) == 1 and audits[-1].details.get("allowed") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_store_audit_training_label.py -v`
Expected: FAIL with `AttributeError: 'LedgerStore' object has no attribute 'audit_training_label'`.

- [ ] **Step 3: Write minimal implementation**

Insert after `materialization_consent` (before `def build_ledger_store`), inside class `LedgerStore`:

```python
    def audit_training_label(
        self, candidate_id: str, *, allowed: bool, as_of: datetime
    ) -> None:
        """S4.4 training-set export: audit that the platform used (allowed) or
        withheld (not allowed) this candidate's consent-gated outcomes as a
        training label. Audit-only — it records the S4.2 materialization decision
        reused at export time (single source of truth), does not recompute
        consent, and never raises. The candidate-linked row CASCADEs on erasure."""
        with self._session_factory() as session:
            self._audit(
                session,
                actor_type="system",
                actor_id="platform",
                action="training.label",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": allowed,
                    "as_of": consent_logic.as_utc(as_of).isoformat(),
                },
            )
            session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger_store_audit_training_label.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_audit_training_label.py
git commit -m "feat(s44): LedgerStore.audit_training_label (audits the reused S4.2 decision)"
```

---

### Task 4: Orchestrator — `build_training_example` + `build_training_set`

**Files:**
- Modify: `app/features/training.py` (append the two functions)
- Test: `tests/test_features_build_training_set.py`

**Interfaces:**
- Consumes: `MaterializedVector` (`app.features.materialize`), `build_label` (Task 2), `LedgerStore.{records_for_candidate, coding_rounds_for_candidate, audit_training_label}`.
- Produces:
  - `build_training_example(mv: MaterializedVector, *, interview_records, coding_rounds) -> TrainingExample`
  - `build_training_set(mvs: Iterable[MaterializedVector], *, ledger_store, audit: bool = True) -> list[TrainingExample]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_build_training_set.py
from datetime import datetime, timedelta, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.training import build_training_set
from app.ledger.schema import ConsentPurpose, InterviewOutcome, InterviewStage
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

T = datetime(2026, 6, 1, tzinfo=timezone.utc)
G = datetime(2026, 1, 1, tzinfo=timezone.utc)
PRE = T - timedelta(days=30)
POST = T + timedelta(days=30)


def _ingest(cs, name, email):
    resume = f"{name}\nML Engineer\nEmail: {email}\n"
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(resume), method="heuristic"),
                    resume_text=resume).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    return cid


def _mv(cid, cs, ls, rs, reg, view):
    return materialize_candidate(cid, view=view, registry=reg, as_of=T,
                                 candidate_store=cs, report_store=rs, ledger_store=ls)


def _setup():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    reg = get_feature_registry()
    view = default_view(reg)
    org = ls.create_organization("Org A")
    a = _ingest(cs, "A Dev", "a@example.com")
    b = _ingest(cs, "B Dev", "b@example.com")
    c = _ingest(cs, "C Dev", "c@example.com")
    for cid in (a, b, c):
        ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=G)
    # A and B are read-consented (materialization allowed); C is not.
    for cid in (a, b):
        ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id, now=G)
    # A: a post-cut HIRED record -> positive label.
    ls.submit_interview_record(org_id=org.id, candidate_id=a, stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)
    # B: only a PRE-cut HIRED record -> censored (must NOT leak as a label).
    ls.submit_interview_record(org_id=org.id, candidate_id=b, stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=PRE)
    # C: a post-cut HIRED record exists, but C is not read-consented -> withheld.
    ls.submit_interview_record(org_id=org.id, candidate_id=c, stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)
    mvs = [_mv(a, cs, ls, rs, reg, view), _mv(b, cs, ls, rs, reg, view), _mv(c, cs, ls, rs, reg, view)]
    return ls, mvs, (a, b, c)


def test_build_training_set_labels_the_mix_correctly():
    ls, mvs, (a, b, c) = _setup()
    examples = build_training_set(mvs, ledger_store=ls)
    by_id = {ex.vector.candidate_id: ex.label for ex in examples}
    # A: consented + post-cut hired.
    assert by_id[a].observed is True and by_id[a].hired is True and by_id[a].withheld is False
    # B: consented but only a pre-cut hired -> censored, not a false positive.
    assert by_id[b].observed is False and by_id[b].hired is None and by_id[b].withheld is False
    # C: withheld -> null label despite an existing post-cut hired record.
    assert by_id[c].withheld is True and by_id[c].hired is None and by_id[c].observed is False


def test_build_training_set_audits_every_join():
    ls, mvs, (a, b, c) = _setup()
    build_training_set(mvs, ledger_store=ls)
    for cid, expected in ((a, True), (b, True), (c, False)):
        joins = [x for x in ls.audit_for_candidate(cid) if x.action == "training.label"]
        assert joins and joins[-1].details.get("allowed") is expected


def test_audit_false_flag_skips_audit_rows():
    ls, mvs, _ = _setup()
    build_training_set(mvs, ledger_store=ls, audit=False)
    assert all(
        not [x for x in ls.audit_for_candidate(ex.vector.candidate_id) if x.action == "training.label"]
        for ex in build_training_set(mvs, ledger_store=ls, audit=False)
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_build_training_set.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_training_set'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/features/training.py`:

```python
def build_training_example(
    mv: MaterializedVector,
    *,
    interview_records: Iterable[InterviewRecord],
    coding_rounds: Iterable[CodingRoundResult],
) -> TrainingExample:
    """Combine one materialized vector with the candidate's ledger rows. Consent is
    read from the vector's stored S4.2 decision; a withheld vector short-circuits
    to a withheld label inside build_label regardless of the passed records."""
    allowed = bool(mv.consent_state.get("allowed"))
    label = build_label(
        as_of=mv.vector.as_of,
        interview_records=interview_records,
        coding_rounds=coding_rounds,
        consent_allowed=allowed,
    )
    return TrainingExample(vector=mv.vector, label=label)


def build_training_set(
    mvs: Iterable[MaterializedVector],
    *,
    ledger_store,
    audit: bool = True,
) -> list[TrainingExample]:
    """Join each materialized vector to its leakage-free label. Reads the ledger
    ONLY for a consented vector (a withheld candidate's outcomes are never
    fetched); audits every join as `training.label` (allowed/withheld) unless
    `audit=False`."""
    out: list[TrainingExample] = []
    for mv in mvs:
        cid = mv.vector.candidate_id
        allowed = bool(mv.consent_state.get("allowed"))
        if allowed:
            irs = ledger_store.records_for_candidate(cid)
            crs = ledger_store.coding_rounds_for_candidate(cid)
        else:
            irs, crs = [], []
        if audit:
            ledger_store.audit_training_label(cid, allowed=allowed, as_of=mv.vector.as_of)
        out.append(build_training_example(mv, interview_records=irs, coding_rounds=crs))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_build_training_set.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/training.py tests/test_features_build_training_set.py
git commit -m "feat(s44): build_training_set orchestrator (consent-reuse, audited, no read when withheld)"
```

---

### Task 5: `export.py` refactor — public pivot helpers (behavior-preserving)

**Files:**
- Modify: `app/features/export.py`
- Test: `tests/test_features_export.py` (existing — must stay green; add one helper test)

**Interfaces:**
- Produces: `feature_columns(view: FeatureView) -> list[str]` and `vector_cells(vector: FeatureVector, view: FeatureView, null_token) -> list`. Existing `export_view_csv` / `export_view_parquet` re-expressed on top of them, unchanged behavior.

- [ ] **Step 1: Write the failing test (new helper test appended to the existing file)**

```python
# append to tests/test_features_export.py
from app.features.export import feature_columns, vector_cells


def test_feature_columns_and_vector_cells_helpers():
    reg, view, mv, cid = _mv()
    cols = feature_columns(view)
    assert cols == [name for name, _ in view.members]
    cells = vector_cells(mv.vector, view, "")
    # fixed (4) + one cell per feature column
    assert len(cells) == 4 + len(cols)
    assert cells[0] == cid  # candidate_id first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_export.py::test_feature_columns_and_vector_cells_helpers -v`
Expected: FAIL with `ImportError: cannot import name 'feature_columns'`.

- [ ] **Step 3: Refactor implementation (behavior-preserving)**

In `app/features/export.py`: add `FeatureVector` to the schema import, and replace the `_columns` / `_row_cells` block with public helpers; retarget the existing exporters onto them.

```python
from app.features.schema import FeatureDType, FeatureVector, FeatureView  # add FeatureVector

_FIXED = ("candidate_id", "as_of", "view_name", "view_version")


def feature_columns(view: FeatureView) -> list[str]:
    return [name for name, _ in view.members]


def _columns(view: FeatureView) -> list[str]:
    return list(_FIXED) + feature_columns(view)


def vector_cells(vector: FeatureVector, view: FeatureView, null_token) -> list:
    fixed = {
        "candidate_id": vector.candidate_id,
        "as_of": as_utc(vector.as_of).isoformat(),
        "view_name": vector.view_name,
        "view_version": vector.view_version,
    }
    cells = []
    for col in _columns(view):
        if col in fixed:
            cells.append(fixed[col])
        else:
            val = vector.values.get(col)
            cells.append(null_token if val is None else val)
    return cells
```

Then update the two existing exporters to call `vector_cells(mv.vector, view, null_token)` in place of the old `_row_cells(mv, view, null_token)` (in `export_view_csv`'s loop and in `export_view_parquet`'s `for mv in rows` / `zip(columns, vector_cells(mv.vector, view, None))`). Delete the old `_row_cells`.

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_features_export.py -v`
Expected: PASS (existing 3 + new 1 = 4).

- [ ] **Step 5: Commit**

```bash
git add app/features/export.py tests/test_features_export.py
git commit -m "refactor(s44): extract public feature_columns/vector_cells pivot helpers"
```

---

### Task 6: Training export — `export_training_csv` / `export_training_parquet`

**Files:**
- Modify: `app/features/export.py`
- Test: `tests/test_features_training_export.py`

**Interfaces:**
- Consumes: `feature_columns`, `vector_cells`, `_columns`, `_pa_type`, `ParquetUnavailable` (Task 5 + existing); `TrainingExample` (Task 1).
- Produces: `_LABEL_COLUMNS: tuple[str, ...]`; `export_training_csv(examples, *, view, path, null_token="") -> None`; `export_training_parquet(examples, *, view, registry, path) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features_training_export.py
import csv
import importlib.util
from datetime import datetime, timezone

import pytest

from app.features.schema import FeatureVector
from app.features.materialize import MaterializedVector
from app.features.training_schema import TrainingExample, TrainingLabel
from app.features.export import (
    ParquetUnavailable, export_training_csv, export_training_parquet, feature_columns,
)
from app.features import default_view, get_feature_registry

T = datetime(2026, 6, 1, tzinfo=timezone.utc)
LABELS = ["label_hired", "label_outcome", "label_coding_best_percentile",
          "label_event_at", "label_lag_days", "label_observed", "label_withheld"]


def _example(cid, values, label):
    fv = FeatureVector(candidate_id=cid, as_of=T, view_name="core_v1", view_version=1,
                       values=values, missing=())
    return TrainingExample(vector=fv, label=label)


def _fixture():
    reg = get_feature_registry()
    view = default_view(reg)
    cols = feature_columns(view)
    labeled = _example("a", {c: None for c in cols},
                       TrainingLabel(hired=True, outcome="hired", coding_best_percentile=88.0,
                                     event_at=T, lag_days=30.0, observed=True))
    withheld = _example("c", {c: None for c in cols}, TrainingLabel(withheld=True))
    return reg, view, [labeled, withheld]


def test_training_csv_header_appends_label_columns(tmp_path):
    reg, view, examples = _fixture()
    path = tmp_path / "train.csv"
    export_training_csv(examples, view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header[:4] == ["candidate_id", "as_of", "view_name", "view_version"]
    assert header[4:4 + len(feature_columns(view))] == feature_columns(view)
    assert header[-7:] == LABELS


def test_training_csv_rows_render_label_values_and_nulls(tmp_path):
    reg, view, examples = _fixture()
    path = tmp_path / "train.csv"
    export_training_csv(examples, view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    a = next(r for r in rows if r["candidate_id"] == "a")
    assert a["label_hired"] == "True" and a["label_outcome"] == "hired"
    assert a["label_coding_best_percentile"] == "88.0" and a["label_observed"] == "True"
    c = next(r for r in rows if r["candidate_id"] == "c")
    assert c["label_withheld"] == "True" and c["label_hired"] == "" and c["label_outcome"] == ""


def test_training_parquet_guarded(tmp_path):
    reg, view, examples = _fixture()
    path = tmp_path / "train.parquet"
    if importlib.util.find_spec("pyarrow") is None:
        with pytest.raises(ParquetUnavailable):
            export_training_parquet(examples, view=view, registry=reg, path=str(path))
    else:
        export_training_parquet(examples, view=view, registry=reg, path=str(path))
        assert path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features_training_export.py -v`
Expected: FAIL with `ImportError: cannot import name 'export_training_csv'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/features/export.py` (add `TrainingExample` import at top: `from app.features.training_schema import TrainingExample`):

```python
_LABEL_COLUMNS = (
    "label_hired", "label_outcome", "label_coding_best_percentile",
    "label_event_at", "label_lag_days", "label_observed", "label_withheld",
)


def _label_cells(label: TrainingLabel, null_token) -> list:
    def cell(v):
        return null_token if v is None else v

    ev = null_token if label.event_at is None else as_utc(label.event_at).isoformat()
    return [
        cell(label.hired),
        cell(label.outcome),
        cell(label.coding_best_percentile),
        ev,
        cell(label.lag_days),
        label.observed,
        label.withheld,
    ]


def export_training_csv(
    examples: Iterable[TrainingExample], *, view: FeatureView, path: str, null_token: str = ""
) -> None:
    columns = _columns(view) + list(_LABEL_COLUMNS)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for ex in examples:
            writer.writerow(
                vector_cells(ex.vector, view, null_token) + _label_cells(ex.label, null_token)
            )


def export_training_parquet(
    examples: Iterable[TrainingExample], *, view: FeatureView, registry: FeatureRegistry, path: str
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # optional dependency
        raise ParquetUnavailable(
            "parquet export needs pyarrow; install it (optional extra) or use export_training_csv"
        ) from exc

    examples = list(examples)
    feat_cols = _columns(view)
    specs = {rf.spec.name: rf.spec for rf in view.resolve(registry)}

    fdata: dict[str, list] = {c: [] for c in feat_cols}
    ldata: dict[str, list] = {c: [] for c in _LABEL_COLUMNS}
    for ex in examples:
        for col, cell in zip(feat_cols, vector_cells(ex.vector, view, None)):
            fdata[col].append(cell)
        for col, cell in zip(_LABEL_COLUMNS, _label_cells(ex.label, None)):
            ldata[col].append(cell)

    arrays = {}
    for col in feat_cols:
        if col == "view_version":
            arrays[col] = pa.array(fdata[col], type=pa.int64())
        elif col in ("candidate_id", "as_of", "view_name"):
            arrays[col] = pa.array(fdata[col], type=pa.string())
        else:
            arrays[col] = pa.array(fdata[col], type=_pa_type(pa, specs[col].dtype))

    _label_arrow = {
        "label_hired": pa.bool_(), "label_outcome": pa.string(),
        "label_coding_best_percentile": pa.float64(), "label_event_at": pa.string(),
        "label_lag_days": pa.float64(), "label_observed": pa.bool_(), "label_withheld": pa.bool_(),
    }
    for col in _LABEL_COLUMNS:
        arrays[col] = pa.array(ldata[col], type=_label_arrow[col])

    ordered = feat_cols + list(_LABEL_COLUMNS)
    pq.write_table(pa.table({c: arrays[c] for c in ordered}), path)
```

Also add `FeatureRegistry` to the top import if not present: `from app.features.registry import FeatureRegistry` (the existing parquet exporter already takes `registry: FeatureRegistry` — reuse that import).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features_training_export.py -v`
Expected: PASS (3 tests; parquet guarded either raises or writes depending on pyarrow presence).

- [ ] **Step 5: Commit**

```bash
git add app/features/export.py tests/test_features_training_export.py
git commit -m "feat(s44): export_training_csv/parquet (wide feature pivot + label columns)"
```

---

### Task 7: Docs — FEATURES.md S4.4 section

**Files:**
- Modify: `FEATURES.md` (append after the S4.3 section)

- [ ] **Step 1: Append the S4.4 section**

Add this section at the end of `FEATURES.md`:

```markdown
## S4.4 — Training-set export (features ⋈ outcomes)

S4.4 adds the **label-join / training-set export** layer: each stored
`ml_feature_vectors` row (features at `as_of=T`) joined to a **ground-truth label
derived only from ledger outcomes strictly after T** — the point-in-time-correct,
leakage-free training set. Read-side only: **no new table, no migration, no HTTP,
no LLM, no config knob** (mirrors S4.3).

### No-leakage seam

Features come from data timestamped `≤ T`; the label from `interview_records`
with `interviewed_at > T` and `coding_round_results` with `taken_at > T`. The
**strict `>`** is the guarantee — a record at exactly `T` fed the features and can
never be a label (asserted directly in tests + smoke).

### Label (`training_schema.py` + `training.py`)

`build_label` is pure (no store/clock — the `risk.py`/`reputation.py` pattern).
Per vector it emits a `TrainingLabel`:

- `outcome` — **terminal-best** post-cut interview outcome, ranked
  `hired>offer>advanced>rejected>no_show`; **`withdrawn` excluded** (non-signal,
  per S3.4). `hired` = terminal ∈ `{hired, offer}`.
- `event_at` / `lag_days` — earliest `interviewed_at` carrying that outcome, and
  its distance from `as_of` in days (lets a modeler window/censor).
- `coding_best_percentile` — max post-cut coding percentile (independent of the
  interview label).
- `observed` — a post-cut non-withdrawn interview record exists. When False the
  example is **right-censored** (`hired`/`outcome` null) — *not* a negative.
- `withheld` — consent was not active at `as_of`; the label is unread and null.

### Consent (reuse S4.2 decision + audit)

The label is derived from the same consent-gated cross-company records S4.2 masks,
so it **inherits the S4.2 decision** stored in `MaterializedVector.consent_state`.
`build_training_set` reads the ledger only for a consented vector (a withheld
candidate's outcomes are never fetched) and audits every join via
`LedgerStore.audit_training_label` → `training.label` (allowed/withheld), keeping
platform use of gated data observable without a new gate. A withheld vector's
`ledger.*` features are already null *and* its label is withheld — consistent.

### Export (`export.py`)

`export_training_csv` / `export_training_parquet` = the S4.2 wide feature pivot
(shared `feature_columns` / `vector_cells` helpers) **plus** appended
`label_hired, label_outcome, label_coding_best_percentile, label_event_at,
label_lag_days, label_observed, label_withheld`. Values are already
masked/withheld, so a file can never leak. Parquet stays guarded
(`ParquetUnavailable` without pyarrow).

### DPDP

No new candidate-linked table ⇒ no new erasure path; labels recompute from ledger
rows that already CASCADE on erasure, and the `training.label` audit rows are
candidate-linked and CASCADE too.

### Testing (S4.4)

Pure `build_label` (no-leakage boundary, terminal-best + withdrawn-excluded,
event_at/lag, hire-positive set, censoring, coding-best, consent-withheld),
`audit_training_label`, `build_training_set` over a mix (labeled / censored /
withheld) proving no ledger read when withheld + every join audited, and labeled
export shape (CSV header + values, guarded parquet). Smoke `scripts/smoke_s44.py`:
A consented+labeled (post-cut hired, point-in-time features), B consented+censored
(pre-cut hired does NOT leak), C withheld (features + label null, `training.label`
withheld audit).
```

- [ ] **Step 2: Commit**

```bash
git add FEATURES.md
git commit -m "docs(s44): FEATURES.md training-set export section"
```

---

### Task 8: Smoke — `scripts/smoke_s44.py`

**Files:**
- Create: `scripts/smoke_s44.py`

**Interfaces:**
- Consumes: `build_candidate_store`, `build_ledger_store`, `build_feature_store`, `build_report_store`, `default_view`, `get_feature_registry`, `materialize_candidate`, `build_training_set`, `export_training_csv`, `export_training_parquet`, `ParquetUnavailable`.

- [ ] **Step 1: Write the smoke script**

```python
# scripts/smoke_s44.py
"""S4.4 smoke: boot uvicorn on a migrated scratch DB, POST three fixture resumes,
then directly build the ledger (consent + interview/coding records with controlled
timestamps), materialize core_v1 vectors at a fixed cut T, join labels via
build_training_set, and export a labeled training CSV. Proves: A (consented) gets
a post-cut HIRED label while its features stay point-in-time; B (consented) with
only a PRE-cut hired is right-censored (no leakage); C (unconsented) is withheld in
both features and label, with a `training.label` withheld audit. LLM-free.
Run from the repo root: python scripts/smoke_s44.py
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.candidates.store import build_candidate_store
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.export import ParquetUnavailable, export_training_csv, export_training_parquet
from app.features.materialize import materialize_candidate
from app.features.store import build_feature_store
from app.features.training import build_training_set
from app.ledger.schema import ConsentPurpose, InterviewOutcome, InterviewStage
from app.ledger.store import build_ledger_store
from app.services.report_store import build_report_store

PORT = 8044
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

RESUMES = {
    "a": "A Dev\nEmail: a44@example.com\nEXPERIENCE\n- Engineer, Acme (2015 - Present)\nSKILLS\nPython\n",
    "b": "B Dev\nEmail: b44@example.com\nEXPERIENCE\n- Engineer, Acme (2016 - Present)\nSKILLS\nPython\n",
    "c": "C Dev\nEmail: c44@example.com\nEXPERIENCE\n- Engineer, Acme (2017 - Present)\nSKILLS\nPython\n",
}


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s44.db").as_posix()
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
    admin_h = {"X-API-Key": ADMIN}
    ids = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not _wait_healthy(c):
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

    # Cut T is in the recent past so ingest-stamped extractions (created_at ~ now)
    # predate it; consent granted before T; pre/post records straddle it.
    now = datetime.now(timezone.utc)
    T = now - timedelta(days=1)
    G = T - timedelta(days=60)
    PRE = T - timedelta(days=30)
    POST = T + timedelta(days=30)

    org = ls.create_organization("Smoke Org")
    for tag in ("a", "b", "c"):
        ls.grant_consent(candidate_id=ids[tag], purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=G)
    for tag in ("a", "b"):  # read consent -> materialization allowed; C withheld
        ls.grant_consent(candidate_id=ids[tag], purpose=ConsentPurpose.LEDGER_READ, org_id=org.id, now=G)

    # A: post-cut HIRED -> positive label; B: pre-cut HIRED -> censored (no leak);
    # C: post-cut HIRED but unconsented -> withheld.
    ls.submit_interview_record(org_id=org.id, candidate_id=ids["a"], stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)
    ls.submit_interview_record(org_id=org.id, candidate_id=ids["b"], stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=PRE)
    ls.submit_interview_record(org_id=org.id, candidate_id=ids["c"], stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)

    mvs = []
    for tag in ("a", "b", "c"):
        mv = materialize_candidate(ids[tag], view=view, registry=reg, as_of=T,
                                   candidate_store=cs, report_store=rs, ledger_store=ls)
        fs.upsert_vector(mv)
        mvs.append(mv)

    examples = build_training_set(mvs, ledger_store=ls)
    label = {ex.vector.candidate_id: ex.label for ex in examples}

    csv_path = scratch / "train_core_v1.csv"
    export_training_csv(examples, view=view, path=str(csv_path))
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")

    pq_ok = True
    pq_path = scratch / "train_core_v1.parquet"
    if importlib.util.find_spec("pyarrow") is None:
        try:
            export_training_parquet(examples, view=view, registry=reg, path=str(pq_path))
            pq_ok = False  # should have raised
        except ParquetUnavailable:
            pq_ok = True
    else:
        export_training_parquet(examples, view=view, registry=reg, path=str(pq_path))
        pq_ok = pq_path.exists()

    a, b, c = label[ids["a"]], label[ids["b"]], label[ids["c"]]
    a_audit = [x for x in ls.audit_for_candidate(ids["a"]) if x.action == "training.label"]
    c_audit = [x for x in ls.audit_for_candidate(ids["c"]) if x.action == "training.label"]

    checks = {
        "A labeled positive (post-cut hired)": a.observed and a.hired is True and a.outcome == "hired",
        "A label lag is positive (~30d)": a.lag_days is not None and a.lag_days > 0,
        "A features point-in-time (pre-cut interview count = 0)":
            mvs[0].vector.values.get("ledger.interview_record_count") in (0, None),
        "B censored: pre-cut hired does NOT leak": (b.observed is False) and (b.hired is None),
        "C withheld in label": c.withheld is True and c.hired is None and c.observed is False,
        "C features consent-masked (ledger count null)":
            mvs[2].vector.values.get("ledger.interview_record_count") is None,
        "labeled CSV header ends with label columns":
            header[-7:] == ["label_hired", "label_outcome", "label_coding_best_percentile",
                            "label_event_at", "label_lag_days", "label_observed", "label_withheld"],
        "A join audited allowed": bool(a_audit) and a_audit[-1].details.get("allowed") is True,
        "C join audited withheld": bool(c_audit) and c_audit[-1].details.get("allowed") is False,
        "parquet guarded/written": pq_ok,
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

- [ ] **Step 2: Run the smoke (key-less; deterministic floor)**

Run: `python scripts/smoke_s44.py`
Expected: every line `OK`, final `SMOKE OK`, exit 0. (Note: `ledger.interview_record_count` for A is checked `in (0, None)` — A's only record is post-cut, so at `T` the feature sees zero pre-cut records; the exact null-vs-0 depends on the S4.1 extractor's empty-vs-absent convention. If the smoke reports A's count as a non-zero number, a submitted record leaked into features — investigate before proceeding.)

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_s44.py
git commit -m "test(s44): end-to-end smoke (leakage-free labels, censoring, consent withhold)"
```

---

### Task 9: Close-out — full suite green + ROADMAP update

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Run the full offline suite**

Run: `pytest -q`
Expected: all green (~595 tests; baseline 564 + ~31 new). Fix any regression before continuing.

- [ ] **Step 2: Update ROADMAP**

In `docs/ROADMAP.md`: flip S4.4 to `[x]` on the status board; update the "▶ Current state" (PI-4 COMPLETE, next action = PI-5 shaping per the vision gap analysis); add a session-log entry summarizing S4.4 (deliverables, test count, smoke result). Follow the existing session-log entry style.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(s44): ROADMAP — S4.4 complete, PI-4 done"
```

- [ ] **Step 4: (Execution-time) whole-branch review + merge**

Per the sprint workflow: run a whole-branch self-review (superpowers:requesting-code-review), address any Critical/Important findings, then `superpowers:finishing-a-development-branch` to merge `s44-training-set-export` to `main` (fast-forward), confirm `pytest -q` green on main, delete the branch.

---

## Self-Review

**1. Spec coverage** (against `2026-07-27-s44-training-set-export-design.md`):
- §4.1 contracts → Task 1. §4.2 pure `build_label` → Task 2. §4.4 `audit_training_label` → Task 3. §4.3 orchestrator → Task 4. §4.5 export refactor → Task 5; training export → Task 6. §5 consent/point-in-time/DPDP → exercised across Tasks 2/4/8. §6 config (none) → nothing to do (asserted by omission). §7 testing → Tasks 2/3/4/5/6 unit + Task 8 smoke. §8 deliverables → all mapped. §9 PI-4 close-out → Task 9. No gaps.

**2. Placeholder scan:** every step has real test + implementation code; no TBD/TODO/"handle edge cases"/"similar to Task N". Clean.

**3. Type consistency:** `build_label(*, as_of, interview_records, coding_rounds, consent_allowed)` identical in Task 2 def and Task 4 call. `build_training_set(mvs, *, ledger_store, audit=True)` identical in Task 4 def and Task 8 use. `audit_training_label(candidate_id, *, allowed, as_of)` identical in Task 3 def, Task 4 call, Task 8 use. `_LABEL_COLUMNS` order identical in Task 6 impl, Task 6 test, Task 7 docs, Task 8 smoke. `TrainingLabel` field names identical across Tasks 1/2/6. `feature_columns`/`vector_cells` signatures identical in Task 5 def and Tasks 6/8 use. Consistent.
