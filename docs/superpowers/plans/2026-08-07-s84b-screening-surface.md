# S8.4 Phase B — Screening Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an organisation the screen the product is sold on — drop in resumes, watch them process, read a ranked and reasoned risk queue — plus the four measured defects the wiring session left open.

**Architecture:** A batch is a real stored object (`screening_batches` + `batch_items`); *batch* status is derived at read time while an *item* carries stored status plus the closed facts of its finished evaluation (`risk_score` column, `signals` JSON, scalars only). The queue read-model is built from `batch_items` alone, so no `Report` — a cross-corpus object — is ever on the org-plane read path. Processing is client-driven and bounded: `POST .../process` claims a few items with a conditional UPDATE and runs the same ingest core the single-upload route runs.

**Tech Stack:** Python 3.13 · FastAPI 0.138 · SQLAlchemy 2.x + Alembic on SQLite (Postgres-shaped) · Pydantic v2 · pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-s84b-screening-surface-design.md` (Phase B deltas + the FIELD tenancy table), which sits on top of `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md` §4.

**Baseline measured before starting:** `pytest -q` → **1434 passed**, exit 0.

## Global Constraints

- **TDD, fully offline.** `NullLLM` / fakes from `tests/conftest.py`. No network, no API key. `pytest -q` green before merge.
- **Advisory only.** Nothing here auto-rejects, auto-shortlists or hides a candidate. Every new response model carries `advisory: True` where it carries a score.
- **DPDP.** No new `ConsentPurpose`. `batch_items.raw_text` is cleared on success and deletable today. **`ItemSignals` holds scalars only — no names, no claim text, no model prose** (design §1.2); a field that could hold personal data must not be added to it.
- **Config:** tunables in `config.yaml` + `app/core/config.py`, secrets only in `.env` under `DEE_*`.
- **DB:** SQLAlchemy + Alembic on SQLite, written Postgres-shaped. New tables are created outright (no `batch_alter_table` needed); the org-name index is the one expression index.
- **404, never 403** for anything owned by another org — and byte-identical to a resource that does not exist.
- **Every new org route depends on `require_org`** or `tests/test_route_table_guard.py` fails the build.
- **Every new org handler reads through `services.screening`**, the sanctioned door. No batch store on `Services`.
- **The admin plane is not touched** except by the two additive changes in Task 11 (`POST /features/materialize`) and the 422→200 fix.
- Branch: `s84b-screening-surface`. Commit after every task.
- **No `Co-Authored-By` trailer in commit messages.**
- Pin `DEE_OPENROUTER_API_KEY=""` in the new smoke — Phase A found five smokes making live billed calls.

---

## File Structure

**Created:**
- `app/screening/schema.py` — pure Pydantic: statuses, `ItemSignals`, `QueueRow`, `BatchView`/`BatchDetail`/`BatchCounts`, `BatchSummary`, `ProcessResult`, the two page envelopes, and `compose_reason`. No I/O.
- `app/screening/pagination.py` — the opaque cursor codec + limit clamping. Pure.
- `app/screening/models.py` — `ScreeningBatchRow`, `BatchItemRow`.
- `app/screening/store.py` — `ScreeningStore`: every method takes `org_id` first.
- `app/screening/ingest.py` — `IngestDeps`, `IngestRefused`, `ingest_resume`: the one ingest core, shared by the route and the batch processor.
- `app/screening/service.py` — `ScreeningService`: composition over store + ingest + `OrgScopedReads`.
- `alembic/versions/0019_screening_batches.py` — two tables + the org-name expression index.
- `tests/test_screening_schema.py`, `test_screening_pagination.py`, `test_screening_store.py`, `test_screening_service.py`, `test_screening_batches_api.py`, `test_screening_tenancy.py`, `test_org_name_case_insensitive.py`, `test_openapi_contract.py`, `test_config_screening.py`, `test_features_materialize_api.py`.
- `scripts/smoke_s84b.py` — key-less HTTP smoke.
- `SCREENING.md` — root doc, peer of `TENANCY.md` / `AUTH.md`.

**Modified:**
- `app/core/config.py` — seven knobs.
- `config.yaml` — the same seven, documented.
- `app/api/routes.py` — seven org routes, `POST /features/materialize`, the two 422→200 sites, comp's shape, cursor on curation, explicit `operation_id`/`response_model` everywhere.
- `app/services/__init__.py` — wire `screening` into `Services`.
- `app/candidates/store.py` — `list_candidate_ids`.
- `app/auth/store.py` — `organization_name_exists` compares `lower(name)`.
- `app/ledger/models.py` — the `uq_organizations_name_ci` index.
- `app/matching/schema.py` — `MatchResult.reason`.
- `tests/conftest.py` — import `app.screening.models` so `create_all` builds the new tables.
- `tests/test_migrations.py` — new tables in the guard lists; expression-index exemption; the behavioural CI-name test.
- `tests/test_org_scope_guard.py` — `screening` joins the sanctioned doors; `ALLOWLISTED_LINES` empties out.
- `TENANCY.md` — §5 (guard reach after the ingest extraction), §8, §9.
- `docs/ROADMAP.md` — status board, current state, session log.

---

## Task 1: Config knobs

**Files:**
- Modify: `app/core/config.py` (after the interview block, ~line 206)
- Modify: `config.yaml`
- Test: `tests/test_config_screening.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.screening_max_batch_items: int`, `.screening_max_items_per_call: int`, `.screening_claim_timeout_seconds: int`, `.ret_batch_item_days: int`, `.page_default_limit: int`, `.page_max_limit: int`, `.materialize_max_candidates: int`.

**Context you need:** `Settings` is a `pydantic-settings` model read from `config.yaml` with `DEE_*` env overrides. Tests use a hermetic `Settings(_env_file=None, ...)` that bypasses `config.yaml`, so **the code default and the YAML value must agree** or the suite tests one thing and production runs another.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_screening.py`:

```python
"""S8.4 Phase B knobs. The values are bounds on cost and blast radius, so the
floors matter: a zero-item process call would spin, and an unbounded batch is a
denial-of-service against a synchronous pipeline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _s(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def test_screening_defaults():
    s = _s()
    assert s.screening_max_batch_items == 500
    assert s.screening_max_items_per_call == 5
    assert s.screening_claim_timeout_seconds == 900
    assert s.ret_batch_item_days == 90
    assert s.page_default_limit == 50
    assert s.page_max_limit == 200
    assert s.materialize_max_candidates == 1000


def test_page_default_never_exceeds_page_max():
    """A default above the cap would make the UNPARAMETERIZED call the one that
    gets refused -- the shape nobody tests."""
    s = _s()
    assert s.page_default_limit <= s.page_max_limit


@pytest.mark.parametrize(
    "kw",
    [
        {"screening_max_batch_items": 0},
        {"screening_max_items_per_call": 0},
        {"screening_claim_timeout_seconds": 0},
        {"ret_batch_item_days": 0},
        {"page_default_limit": 0},
        {"page_max_limit": 0},
        {"materialize_max_candidates": 0},
    ],
)
def test_floors_are_enforced(kw):
    with pytest.raises(ValidationError):
        _s(**kw)


def test_config_yaml_matches_the_code_defaults():
    """The hermetic test Settings bypasses config.yaml, so a drift between the
    two means the suite proves one number and the deploy runs another."""
    import yaml

    raw = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    s = _s()
    for key in (
        "screening_max_batch_items", "screening_max_items_per_call",
        "screening_claim_timeout_seconds", "ret_batch_item_days",
        "page_default_limit", "page_max_limit", "materialize_max_candidates",
    ):
        assert raw[key] == getattr(s, key), f"{key} drifted between config.yaml and Settings"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_config_screening.py -q`
Expected: FAIL — `AttributeError` / `KeyError: 'screening_max_batch_items'`.

- [ ] **Step 3: Add the fields**

In `app/core/config.py`, immediately after the `speech_max_retries` line (~206):

```python
    # --- Screening batches (PI-8, S8.4 Phase B) -------------------------------
    # Registration is a row insert, so the batch bound is a sanity limit rather
    # than a performance one. The per-call bound is the real cost control: each
    # item is a full nine-node graph run, and there is no worker -- the client
    # drives processing a few items at a time (spec §0.3).
    screening_max_batch_items: int = Field(default=500, ge=1)
    screening_max_items_per_call: int = Field(default=5, ge=1)
    # An item still 'processing' after this reads as pending again, so a batch
    # interrupted by a redeploy heals itself instead of wedging (spec §4.4).
    screening_claim_timeout_seconds: int = Field(default=900, ge=1)
    # Unprocessed item text. Declared here, swept by S8.3 -- the window is a
    # posture, and the honest statement is that nothing deletes on it yet.
    ret_batch_item_days: int = Field(default=90, ge=1)

    # --- Cursor pagination (PI-8, S8.4 Phase B) -------------------------------
    page_default_limit: int = Field(default=50, ge=1)
    page_max_limit: int = Field(default=200, ge=1)

    # --- Feature materialization (PI-8, S8.4 Phase B) -------------------------
    # Bound on the admin materialize route when it is called with no explicit
    # candidate list.
    materialize_max_candidates: int = Field(default=1000, ge=1)
```

- [ ] **Step 4: Add the same values to `config.yaml`**

Append at the end of the file:

```yaml
# --- Screening batches (PI-8, S8.4 Phase B) ----------------------------------
screening_max_batch_items: 500          # registration is cheap; a sanity bound
screening_max_items_per_call: 5         # each item is a full nine-node graph run
screening_claim_timeout_seconds: 900    # a 'processing' item older than this reads pending
ret_batch_item_days: 90                 # unprocessed item text; S8.3 sweep input
page_default_limit: 50
page_max_limit: 200
materialize_max_candidates: 1000        # bound on POST /features/materialize
```

- [ ] **Step 5: Run the test**

Run: `python -m pytest tests/test_config_screening.py -q`
Expected: PASS (11 tests).

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py config.yaml tests/test_config_screening.py
git commit -m "feat(s84b): screening batch + pagination config knobs"
```

---

## Task 2: `app/screening/schema.py` — the pure read-model types

**Files:**
- Create: `app/screening/schema.py`
- Test: `tests/test_screening_schema.py`

**Interfaces:**
- Consumes: `Settings` (not directly — pure module), `FabricationRiskBand` / `DuplicationBand` (`app/schemas/fabrication.py`), `DepthBand` (`app/schemas/report.py`), `MatchedOn` (`app/candidates/store.py`).
- Produces:
  - `ItemStatus` (StrEnum: `pending|processing|done|failed`), `BatchStatus` (StrEnum: `empty|pending|processing|complete|partial`)
  - `ItemSignals` (scalars only), `signals_from_report(report, outcome) -> ItemSignals`
  - `compose_reason(signals: ItemSignals | None, status: ItemStatus, error: str | None) -> str`
  - `QueueRow`, `QueuePage`, `BatchCounts`, `BatchView`, `BatchDetail`, `BatchPage`, `BatchSummary`, `ProcessResult`
  - `derive_status(counts: BatchCounts) -> BatchStatus`

**Context you need:** `ItemSignals` is the closed-facts blob stamped on an item when its evaluation finishes. **Scalars only** — design §1.2: `batch_items.candidate_id` is `SET NULL` on erasure, so any free text stored here would outlive its subject, which is the orphan S8.1's fold existed to make impossible. The one-line reason the UI wants is therefore *composed from the scalars at read time*, not copied from the report.

`signals_from_report` reads the report's `fabrication_risk.components[]` to find the loudest signal: the component with the greatest `weight`, ties broken by `risk` then by `id` so the choice is deterministic (a flaky "loudest" makes two identical reports render differently).

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_schema.py`:

```python
"""S8.4 Phase B: the queue read-model's pure types.

The DPDP assertion in this file is load-bearing rather than stylistic. An item
keeps its signals after its candidate is erased (batch_items.candidate_id is
SET NULL so the org's record of what it screened is not silently rewritten), so
anything free-form stored here outlives the person it describes.
"""

from __future__ import annotations

import pytest

from app.schemas.fabrication import (
    FabricationRiskAssessment, FabricationRiskBand, ResumeFarmAssessment,
    RiskComponent,
)
from app.schemas.report import DepthBand, Report
from app.screening.schema import (
    BatchCounts, BatchStatus, ItemSignals, ItemStatus, compose_reason,
    derive_status, signals_from_report,
)


def test_item_signals_holds_no_free_text():
    """Every field is a number, a bool, an enum member, or one of the three
    closed-vocabulary strings -- design §1.2.

    Written as an allowlist of FIELD NAMES rather than a check on types,
    because `str` is exactly what a prose field would also be: only a human
    decision can say that `loudest_signal` is a closed vocabulary and a
    hypothetical `reasoning` is not. Adding any string field therefore fails
    here until someone justifies it.
    """
    closed_vocabulary_strings = {"loudest_signal", "loudest_band", "matched_on"}
    for name, field in ItemSignals.model_fields.items():
        anno = str(field.annotation)
        if "str" in anno:
            assert name in closed_vocabulary_strings, (
                f"{name} is a string field on an item that OUTLIVES its "
                f"candidate's erasure (batch_items.candidate_id is SET NULL). "
                f"If it is a closed vocabulary, add it to this set and say so; "
                f"if it is prose, it does not belong in ItemSignals."
            )


def test_item_signals_string_fields_are_closed_vocabularies():
    """The three string-ish fields are enumerated values, not prose. Asserted by
    name so ADDING a prose field to this model fails here."""
    assert set(ItemSignals.model_fields) == {
        "risk_band", "risk_confidence", "depth_band", "depth_score",
        "loudest_signal", "loudest_band", "n_components",
        "farm_band", "farm_score", "farm_corpus_size",
        "matched_existing", "matched_on", "duplicate_resume", "flagged_claims",
    }


def _report_with(components, *, band=FabricationRiskBand.ELEVATED) -> Report:
    return Report(
        depth_score=0.4, depth_band=DepthBand.EMERGING, overall_confidence=0.5,
        fabrication_risk=FabricationRiskAssessment(
            score=0.7, confidence=0.6, band=band, components=components,
            reasoning="prose that must NOT be copied onto the item",
        ),
        resume_farm=ResumeFarmAssessment(score=0.9, confidence=0.8, corpus_size=12),
        flagged_claim_ids=["c1", "c2"],
    )


def test_signals_from_report_picks_the_heaviest_component_as_loudest():
    rep = _report_with([
        RiskComponent(id="ai_generation", band="low", risk=0.2, confidence=0.9, weight=0.9),
        RiskComponent(id="resume_farm", band="elevated", risk=0.9, confidence=0.8, weight=2.4),
        RiskComponent(id="cross_field", band="moderate", risk=0.5, confidence=0.5, weight=1.0),
    ])
    sig = signals_from_report(rep, matched_existing=True, matched_on="email_hash",
                              duplicate_resume=False)
    assert sig.loudest_signal == "resume_farm"
    assert sig.loudest_band == "elevated"
    assert sig.n_components == 3
    assert sig.flagged_claims == 2
    assert sig.farm_corpus_size == 12
    assert sig.matched_existing is True and sig.matched_on == "email_hash"


def test_signals_from_report_ties_break_deterministically():
    """Two identical reports must not render a different loudest signal."""
    comps = [
        RiskComponent(id="cross_field", band="low", risk=0.5, confidence=0.5, weight=1.0),
        RiskComponent(id="ai_generation", band="low", risk=0.5, confidence=0.5, weight=1.0),
    ]
    a = signals_from_report(_report_with(comps), matched_existing=False,
                            matched_on=None, duplicate_resume=False)
    b = signals_from_report(_report_with(list(reversed(comps))), matched_existing=False,
                            matched_on=None, duplicate_resume=False)
    assert a.loudest_signal == b.loudest_signal == "ai_generation"


def test_signals_from_a_report_with_no_fabrication_block_is_neutral():
    """Pre-S2.4 stored reports have none. Neutral, never a zero score -- an
    absent assessment is not a clean one."""
    sig = signals_from_report(Report(), matched_existing=False, matched_on=None,
                              duplicate_resume=False)
    assert sig.risk_band == FabricationRiskBand.INSUFFICIENT_DATA
    assert sig.loudest_signal is None


def test_compose_reason_reads_as_a_sentence_and_names_the_signal():
    sig = ItemSignals(
        risk_band=FabricationRiskBand.ELEVATED, risk_confidence=0.42,
        loudest_signal="resume_farm", loudest_band="elevated", n_components=3,
    )
    text = compose_reason(sig, ItemStatus.DONE, None)
    assert "elevated" in text and "resume farm" in text.lower() and "0.42" in text


def test_compose_reason_for_an_unprocessed_or_failed_item():
    assert compose_reason(None, ItemStatus.PENDING, None) == "not screened yet"
    assert "empty_resume" in compose_reason(None, ItemStatus.FAILED, "empty_resume")


def test_compose_reason_never_claims_confidence_it_does_not_have():
    sig = ItemSignals(risk_band=FabricationRiskBand.INSUFFICIENT_DATA, risk_confidence=0.0)
    assert "insufficient" in compose_reason(sig, ItemStatus.DONE, None).lower()


@pytest.mark.parametrize(
    "counts,expected",
    [
        (BatchCounts(), BatchStatus.EMPTY),
        (BatchCounts(pending=3), BatchStatus.PENDING),
        (BatchCounts(pending=1, processing=1), BatchStatus.PROCESSING),
        (BatchCounts(done=3), BatchStatus.COMPLETE),
        (BatchCounts(done=2, failed=1), BatchStatus.PARTIAL),
        (BatchCounts(failed=3), BatchStatus.PARTIAL),
        (BatchCounts(done=1, pending=1), BatchStatus.PENDING),
    ],
)
def test_derive_status(counts, expected):
    """Derived at read time, never stored (spec §4.4): a stored status goes
    stale the moment a process dies and nothing afterwards corrects it."""
    assert derive_status(counts) == expected
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_screening_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screening.schema'`.

- [ ] **Step 3: Write the module**

Create `app/screening/schema.py`:

```python
"""Screening batches: the pure types (S8.4 Phase B).

No I/O, no session, no clock beyond what a caller hands in. Everything here is
either a wire shape or a pure function over one.

The rule this module exists to enforce is DPDP, not tidiness: ``ItemSignals``
holds SCALARS ONLY. ``batch_items.candidate_id`` is ``ON DELETE SET NULL`` --
deliberately, so that a candidate erasing themselves does not silently rewrite
an organisation's record of how many resumes it screened -- which means
anything stored beside it OUTLIVES the person it describes. A band and a score
attached to a null candidate are not personal data. A copied reasoning string
that quotes claim text would be, and it would be exactly the orphan S8.1's fold
of the report store existed to make impossible.

So the one-line reason the queue shows is COMPOSED from the scalars at read
time (``compose_reason``), never copied. The full reasoning stays in the
``Report``, which CASCADEs from its candidate.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.store import MatchedOn
from app.schemas.fabrication import DuplicationBand, FabricationRiskBand
from app.schemas.report import DepthBand, Report


class ItemStatus(StrEnum):
    """Stored on the item. Contrast BatchStatus, which is derived."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class BatchStatus(StrEnum):
    """DERIVED at read time from the item counts (spec §4.4), never stored."""

    EMPTY = "empty"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    PARTIAL = "partial"  # nothing left to do, but something failed


class ItemSignals(BaseModel):
    """Closed facts about ONE finished evaluation. Scalars only -- see module docstring.

    Storing these is consistent with the derived-status rule rather than an
    exception to it (S7.3 drew the line): a fact that depends on the clock or on
    later rows must be derived, and a finished evaluation's score depends on
    neither. ``matched_existing`` is not even recomputable -- it is a fact about
    the moment of ingest.
    """

    risk_band: FabricationRiskBand = FabricationRiskBand.INSUFFICIENT_DATA
    risk_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    depth_band: DepthBand = DepthBand.INSUFFICIENT_SIGNAL
    depth_score: float = Field(default=0.0, ge=0.0, le=1.0)
    #: One of the three fixed component ids, never free text.
    loudest_signal: Optional[str] = None
    loudest_band: Optional[str] = None
    n_components: int = 0
    farm_band: DuplicationBand = DuplicationBand.INSUFFICIENT_DATA
    farm_score: float = Field(default=0.0, ge=0.0, le=1.0)
    #: A COUNT of fingerprinted resumes compared against -- never their ids.
    farm_corpus_size: int = 0
    matched_existing: bool = False
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool = False
    flagged_claims: int = 0


def signals_from_report(
    report: Report,
    *,
    matched_existing: bool,
    matched_on: Optional[MatchedOn],
    duplicate_resume: bool,
) -> ItemSignals:
    """Stamp the closed facts of a finished evaluation onto an item.

    Deliberately drops ``fabrication_risk.reasoning``, every ``verdict``, and
    ``resume_farm.matches[]``. The first is prose about a person; the last is
    the counterparty identity Phase A's projection exists to strip -- and not
    holding it is a stronger guarantee than redacting it.
    """
    fab = report.fabrication_risk
    farm = report.resume_farm

    loudest = None
    if fab is not None and fab.components:
        # Heaviest wins; ties broken by risk then id so two identical reports
        # never render a different "loudest".
        loudest = sorted(
            fab.components, key=lambda c: (-c.weight, -c.risk, c.id)
        )[0]

    return ItemSignals(
        risk_band=fab.band if fab is not None else FabricationRiskBand.INSUFFICIENT_DATA,
        risk_confidence=fab.confidence if fab is not None else 0.0,
        depth_band=report.depth_band,
        depth_score=report.depth_score,
        loudest_signal=loudest.id if loudest is not None else None,
        loudest_band=loudest.band if loudest is not None else None,
        n_components=len(fab.components) if fab is not None else 0,
        farm_band=farm.band if farm is not None else DuplicationBand.INSUFFICIENT_DATA,
        farm_score=farm.score if farm is not None else 0.0,
        farm_corpus_size=farm.corpus_size if farm is not None else 0,
        matched_existing=matched_existing,
        matched_on=matched_on,
        duplicate_resume=duplicate_resume,
        flagged_claims=len(report.flagged_claim_ids),
    )


_SIGNAL_LABELS = {
    "ai_generation": "AI-generation signals",
    "cross_field": "cross-field inconsistency",
    "resume_farm": "resume farm / near-duplicate",
}


def compose_reason(
    signals: Optional[ItemSignals], status: ItemStatus, error: Optional[str]
) -> str:
    """The queue's one-line reason, GENERATED from scalars (module docstring).

    Never asserts more than the numbers support: an ``insufficient_data`` band
    says so plainly rather than being rendered as a low risk, because
    "we could not say" and "we looked and it is fine" are different answers
    (UI.md §1).
    """
    if status is ItemStatus.PENDING:
        return "not screened yet"
    if status is ItemStatus.PROCESSING:
        return "screening in progress"
    if status is ItemStatus.FAILED:
        return f"could not be screened: {error or 'unknown_error'}"
    if signals is None:
        return "screened, but the stored signals could not be read"

    if signals.risk_band is FabricationRiskBand.INSUFFICIENT_DATA:
        return "insufficient signal to assess fabrication risk"

    label = _SIGNAL_LABELS.get(signals.loudest_signal or "", "no single dominant signal")
    tail = (
        f"{label} is the loudest of {signals.n_components}"
        if signals.loudest_signal
        else label
    )
    return (
        f"{signals.risk_band.value} fabrication risk — {tail}; "
        f"confidence {signals.risk_confidence:.2f}"
    )


class BatchCounts(BaseModel):
    """Item counts by status. The stale-``processing`` reinterpretation has
    already been applied by the store, so ``processing`` here means genuinely
    in flight."""

    pending: int = 0
    processing: int = 0
    done: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        return self.pending + self.processing + self.done + self.failed


def derive_status(counts: BatchCounts) -> BatchStatus:
    """Spec §4.4: a batch's status is a READ over its items, never a column."""
    if counts.total == 0:
        return BatchStatus.EMPTY
    if counts.pending:
        return BatchStatus.PENDING
    if counts.processing:
        return BatchStatus.PROCESSING
    return BatchStatus.PARTIAL if counts.failed else BatchStatus.COMPLETE


class BatchView(BaseModel):
    """A batch in a list."""

    id: str
    name: str = ""
    domain: str
    created_at: datetime
    created_by_org_user_id: Optional[str] = None
    counts: BatchCounts = Field(default_factory=BatchCounts)
    status: BatchStatus = BatchStatus.EMPTY


class BatchDetail(BatchView):
    """Identical today; a distinct type so the detail read can grow fields the
    list must not pay for."""


class QueueRow(BaseModel):
    """One resume in the fraud-screen queue.

    Every field comes from this item's own row (design §2.3). No Report is on
    this path, which is why there is nothing here to redact.
    """

    item_id: str
    status: ItemStatus
    created_at: datetime
    processed_at: Optional[datetime] = None
    candidate_id: Optional[str] = None
    resume_id: Optional[str] = None
    report_id: Optional[str] = None
    risk_score: Optional[float] = None
    signals: Optional[ItemSignals] = None
    reason: str = ""
    error: Optional[str] = None
    advisory: bool = True
    human_review_required: bool = True


class QueuePage(BaseModel):
    rows: list[QueueRow] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class BatchPage(BaseModel):
    batches: list[BatchView] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class SignalCount(BaseModel):
    signal: str
    count: int


class BatchSummary(BaseModel):
    """UI.md screen C -- the screenshot-able roll-up.

    Counts and enum members only: a summary that quoted its riskiest row would
    re-open every question the FIELD table answers (design §2.4).
    """

    batch_id: str
    name: str = ""
    domain: str
    status: BatchStatus
    counts: BatchCounts
    n_screened: int = 0
    by_risk_band: dict[str, int] = Field(default_factory=dict)
    top_signals: list[SignalCount] = Field(default_factory=list)
    advisory: bool = True
    human_review_required: bool = True


class ProcessResult(BaseModel):
    """What one bounded `process` call did."""

    batch_id: str
    processed: int = 0
    failed: int = 0
    remaining: int = 0
    status: BatchStatus = BatchStatus.EMPTY
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_screening_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite — nothing else may move**

Run: `python -m pytest -q`
Expected: 1434 + the new tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add app/screening/schema.py tests/test_screening_schema.py
git commit -m "feat(s84b): queue read-model types; signals are scalars only"
```

---

## Task 3: ORM rows + migration `0019` (the two tables)

**Files:**
- Create: `app/screening/models.py`
- Create: `alembic/versions/0019_screening_batches.py`
- Modify: `tests/conftest.py` (the `import app.*.models` block, ~line 26)
- Modify: `tests/test_migrations.py` (add `SCREENING_TABLES`)
- Test: `tests/test_screening_models.py`

**Interfaces:**
- Consumes: `ItemStatus` (Task 2).
- Produces: `ScreeningBatchRow` (`id, org_id, name, domain, created_by_org_user_id, created_at`, `items` relationship), `BatchItemRow` (`id, batch_id, status, raw_text, text_sha256, candidate_id, resume_id, report_id, risk_score, signals, error, created_at, claimed_at, processed_at`).

**Context you need:** the ondelete choices are the reviewable part and they are not uniform:
- `screening_batches.org_id` **CASCADE** — a batch is the org's own work product with no meaning once the org is gone. Contrast `resumes.org_id`, which is `SET NULL` because a resume is a *person's* data.
- `batch_items.batch_id` **CASCADE** — items are parts of the batch.
- `candidate_id` / `resume_id` / `report_id` **SET NULL** — a candidate erasing themselves must not silently delete the org's record of how many resumes it screened.

`app/core/db.py:32` sets `PRAGMA foreign_keys=ON` per connection, so these are enforced under SQLite and the tests below are real. `tests/conftest.py` builds test schemas with `create_all`, so the new module **must** be imported there or every test using the tables fails with "no such table".

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_models.py`:

```python
"""S8.4 Phase B: the batch tables, and the three ondelete decisions.

The SET NULL assertions are the point. A candidate erasing themselves must not
delete an organisation's record of what it screened -- and a CASCADE typo on
any of the three subject pointers would do exactly that, silently, until the
first erasure.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.screening.models import BatchItemRow, ScreeningBatchRow


def test_batch_org_id_cascades():
    """A batch is the ORG's work product -- unlike a resume, it has no meaning
    once the org is gone."""
    fk = next(iter(ScreeningBatchRow.__table__.c.org_id.foreign_keys))
    assert fk.column.table.name == "organizations"
    assert fk.ondelete == "CASCADE"
    assert ScreeningBatchRow.__table__.c.org_id.nullable is False


def test_batch_creator_is_set_null():
    """An org user leaving must not delete the batch they registered."""
    fk = next(iter(ScreeningBatchRow.__table__.c.created_by_org_user_id.foreign_keys))
    assert fk.column.table.name == "org_users"
    assert fk.ondelete == "SET NULL"
    assert ScreeningBatchRow.__table__.c.created_by_org_user_id.nullable is True


def test_the_three_subject_pointers_are_set_null_not_cascade():
    for col in ("candidate_id", "resume_id", "report_id"):
        c = BatchItemRow.__table__.c[col]
        fk = next(iter(c.foreign_keys))
        assert c.nullable is True, f"{col} must be nullable"
        assert fk.ondelete == "SET NULL", (
            f"batch_items.{col} must be SET NULL -- a candidate's erasure must "
            f"not rewrite the org's record of how many resumes it screened"
        )


def test_items_cascade_from_their_batch():
    fk = next(iter(BatchItemRow.__table__.c.batch_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_text_sha256_is_indexed_but_not_unique():
    """Phase A made a per-org resume row, so one sha can legitimately appear on
    several items -- and an org may hold two copies of one CV."""
    col = BatchItemRow.__table__.c.text_sha256
    assert col.index is True
    assert col.unique in (False, None)


def test_erasing_a_candidate_leaves_the_item_with_a_null_pointer(services):
    """The behaviour the ondelete assertions stand in for, end to end."""
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
    )

    org = services.ledger.create_organization("Acme Staffing")
    outcome = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value="Priya"),
                contact=ContactInfo(email=ExtractedStr(value="priya@example.in")),
            ),
            method="heuristic",
        ),
        "Priya Nair\nEmail: priya@example.in\nEXPERIENCE\n- Engineer, Acme\n",
        org_id=org.id,
    )

    sf = services.candidates._session_factory
    with sf() as s:
        batch = ScreeningBatchRow(org_id=org.id, name="Q3 intake", domain="genai")
        s.add(batch)
        s.flush()
        s.add(BatchItemRow(
            batch_id=batch.id, status="done", raw_text="", text_sha256="a" * 64,
            candidate_id=outcome.candidate_id, resume_id=outcome.resume_id,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()
        batch_id = batch.id

    assert services.candidates.delete_candidate(outcome.candidate_id) is True

    with sf() as s:
        item = s.execute(
            select(BatchItemRow).where(BatchItemRow.batch_id == batch_id)
        ).scalars().one()
        assert item.candidate_id is None and item.resume_id is None
        assert item.status == "done", "the org's record of the screening survives"


def test_deleting_an_org_takes_its_batches_with_it(services):
    org = services.ledger.create_organization("Acme Staffing")
    sf = services.candidates._session_factory
    with sf() as s:
        batch = ScreeningBatchRow(org_id=org.id, name="x", domain="genai")
        s.add(batch)
        s.commit()

    assert services.ledger.delete_organization(org.id) is True

    with sf() as s:
        assert s.execute(select(ScreeningBatchRow)).scalars().all() == []
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_screening_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screening.models'`.

- [ ] **Step 3: Write the models**

Create `app/screening/models.py`:

```python
"""ORM rows for screening batches (S8.4 Phase B). Postgres-shaped on SQLite.

Three ondelete decisions, and they are deliberately NOT uniform:

* ``screening_batches.org_id`` CASCADEs. A batch is the organisation's own work
  product and has no meaning once the org is gone -- the exact contrast with
  ``resumes.org_id``, which SET NULLs because a resume is a PERSON's data that
  merely happened to be uploaded by that org.
* ``batch_items.batch_id`` CASCADEs. Items are parts of the batch.
* ``candidate_id`` / ``resume_id`` / ``report_id`` SET NULL. A candidate
  erasing themselves must not silently rewrite an organisation's record of how
  many resumes it screened. The item reads "subject erased"; the count stands.

``signals`` is JSON for the same reason ``reports.body`` and
``extractions.profile`` are: schema evolution is Pydantic's job, not SQL's.
``risk_score`` is a real column beside it because it is the QUEUE'S SORT KEY --
ordering by a value inside a JSON blob is dialect-specific and unindexable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Index, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScreeningBatchRow(Base):
    __tablename__ = "screening_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(32))
    # NULL for a machine caller: X-Org-Key is an organisation credential with no
    # human behind it, and inventing one would be a false audit trail.
    created_by_org_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("org_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    items: Mapped[list["BatchItemRow"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # The list read filters on org_id and orders by created_at.
        Index("ix_screening_batches_org_created", "org_id", "created_at"),
    )


class BatchItemRow(Base):
    __tablename__ = "batch_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("screening_batches.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    #: CLEARED on success -- the text then lives in `resumes`, where candidate
    #: erasure already cascades. Kept on failure so the org can retry.
    raw_text: Mapped[str] = mapped_column(Text, default="")
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)

    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    resume_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )

    #: The queue's sort key. NULL until the item is evaluated.
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: ItemSignals. Scalars only -- see app/screening/schema.py.
    signals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    #: A reason CODE (`empty_resume`, `pdf_parse_failed`, ...), never prose and
    #: never model output.
    error: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    batch: Mapped[ScreeningBatchRow] = relationship(back_populates="items")

    __table_args__ = (
        # The claim query filters (batch_id, status); the queue orders by
        # risk_score. Both are hot on a 500-item batch.
        Index("ix_batch_items_batch_status", "batch_id", "status"),
        Index("ix_batch_items_batch_risk", "batch_id", "risk_score"),
    )
```

- [ ] **Step 4: Register the models with the test metadata**

In `tests/conftest.py`, in the `import app.*.models` block (after the `app.reports.models` line, ~line 26):

```python
import app.screening.models  # noqa: F401 — populate Base.metadata with screening tables
```

- [ ] **Step 5: Run the model test**

Run: `python -m pytest tests/test_screening_models.py -q`
Expected: PASS.

- [ ] **Step 6: Write the migration**

Create `alembic/versions/0019_screening_batches.py`:

```python
"""screening batches + items (S8.4 Phase B)

Revision ID: 0019_screening_batches
Revises: 0018_upload_ownership
Create Date: 2026-08-07

An organisation can now upload ONE resume and read its report (Phase A). This
adds the surface the product is actually sold on: drop in the resumes you have,
watch them process, read a ranked list of who needs a human.

Both tables are new, so there is no batch_alter_table here -- SQLite creates
them with their foreign keys in place.

The ondelete choices are not uniform and the asymmetry is deliberate:
screening_batches.org_id CASCADEs (a batch is the ORG's work product), while
the three subject pointers on batch_items SET NULL (a candidate's erasure must
not rewrite the org's record of what it screened).
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_screening_batches"
down_revision = "0018_upload_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screening_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("created_by_org_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_screening_batches_org_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_org_user_id"], ["org_users.id"],
            name="fk_screening_batches_created_by", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_screening_batches_org_id", "screening_batches", ["org_id"])
    op.create_index(
        "ix_screening_batches_org_created", "screening_batches", ["org_id", "created_at"]
    )

    op.create_table(
        "batch_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("resume_id", sa.String(length=36), nullable=True),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["screening_batches.id"],
            name="fk_batch_items_batch_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"],
            name="fk_batch_items_candidate_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"], ["resumes.id"],
            name="fk_batch_items_resume_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["reports.id"],
            name="fk_batch_items_report_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_batch_items_batch_id", "batch_items", ["batch_id"])
    op.create_index("ix_batch_items_text_sha256", "batch_items", ["text_sha256"])
    op.create_index("ix_batch_items_batch_status", "batch_items", ["batch_id", "status"])
    op.create_index("ix_batch_items_batch_risk", "batch_items", ["batch_id", "risk_score"])


def downgrade() -> None:
    op.drop_index("ix_batch_items_batch_risk", table_name="batch_items")
    op.drop_index("ix_batch_items_batch_status", table_name="batch_items")
    op.drop_index("ix_batch_items_text_sha256", table_name="batch_items")
    op.drop_index("ix_batch_items_batch_id", table_name="batch_items")
    op.drop_table("batch_items")

    op.drop_index("ix_screening_batches_org_created", table_name="screening_batches")
    op.drop_index("ix_screening_batches_org_id", table_name="screening_batches")
    op.drop_table("screening_batches")
```

> **`report_id` is `String(64)`, not 36** — `reports.id` is `String(64)` (`app/reports/models.py`), and a width mismatch is the kind of thing that works on SQLite and refuses on Postgres.

- [ ] **Step 7: Put the new tables under the migration guards**

In `tests/test_migrations.py`, after the `AUTH_TABLES` definition (~line 117):

```python
# S8.4 Phase B — batches CASCADE from the org; the three subject pointers on
# items SET NULL so an erasure cannot rewrite an org's screening record.
SCREENING_TABLES = ("screening_batches", "batch_items")
```

and add `+ SCREENING_TABLES` to the table lists in **both** `test_migrated_indexes_match_orm` and `test_migrated_fks_and_nullability_match_orm`.

- [ ] **Step 8: Run the migration guards and a full up/down/up**

Run: `python -m pytest tests/test_migrations.py -q`
Expected: PASS.

Run:
```bash
python -c "
from alembic import command; from alembic.config import Config
import tempfile, os
d = tempfile.mkdtemp(); url = f'sqlite:///{d}/m.db'
cfg = Config('alembic.ini'); cfg.set_main_option('sqlalchemy.url', url)
command.upgrade(cfg, 'head'); command.downgrade(cfg, 'base'); command.upgrade(cfg, 'head')
print('up -> base -> up OK')"
```
Expected: `up -> base -> up OK`.

- [ ] **Step 9: Full suite**

Run: `python -m pytest -q`
Expected: no failures.

- [ ] **Step 10: Commit**

```bash
git add app/screening/models.py alembic/versions/0019_screening_batches.py tests/conftest.py tests/test_migrations.py tests/test_screening_models.py
git commit -m "feat(s84b): screening_batches + batch_items, migration 0019"
```

---

## Task 4: Case-insensitive organisation names (Phase-A carry-over 1)

**Files:**
- Modify: `app/ledger/models.py:36-40` (`OrganizationRow.__table_args__`)
- Modify: `alembic/versions/0019_screening_batches.py` (append to `upgrade`/`downgrade`)
- Modify: `app/auth/store.py:408-422` (`organization_name_exists`)
- Modify: `tests/test_migrations.py` (expression-index exemption + two new tests)
- Test: `tests/test_org_name_case_insensitive.py`

**Interfaces:**
- Consumes: nothing.
- Produces: index `uq_organizations_name_ci` on `lower(name)`, UNIQUE. `AuthStore.organization_name_exists(name)` compares case-insensitively. No signature changes.

**Context you need — read this before writing code, it is the whole task.**

Phase A left names compared case-sensitively **on purpose**: a case-insensitive *check* without a matching case-insensitive *constraint* creates a **new** lockout — signup 409s on "acme", the insert at verify succeeds beside "Acme" anyway, and two orgs share a name the UI treats as unique. So the constraint comes first and the check merely agrees with it.

Both insert paths already map `IntegrityError` to their own refusal — `LedgerStore.create_organization` → `ValueError` (`app/ledger/store.py:233`), `AuthStore.create_org_with_owner` → `OrgNameTaken` (`app/auth/store.py:394`) — so **the database becomes the single enforcement point and neither door needs a new check.** That is the point of doing it at the constraint rather than in code.

**Measured, and it changes an existing guard.** SQLite *enforces* an expression index but does **not reflect** one:

```
SAWarning: Skipped unsupported reflection of expression-based index uq_orgs_name_ci
inspect(engine).get_indexes("orgs")  ->  []
INSERT 'acme' after 'Acme'           ->  IntegrityError    (enforced)
```

`test_migrated_indexes_match_orm` compares ORM indexes against reflected ones, so declaring this index in the ORM makes that guard fail **on a schema that is correct**. The guard therefore skips expression indexes explicitly, with the measurement written into it, and a behavioural test proves the constraint on the migrated engine instead — which is strictly stronger, since the metadata comparison never established that any index was *enforced*.

- [ ] **Step 1: Write the failing test**

Create `tests/test_org_name_case_insensitive.py`:

```python
"""S8.4 Phase B: 'Acme Staffing' and 'acme staffing' are one organisation.

Phase A deliberately did NOT fix this, and its reason is this task's design: a
case-insensitive CHECK without a case-insensitive CONSTRAINT creates a new
lockout -- signup refuses the name, the insert at verify succeeds anyway, and
two orgs end up sharing a name the UI treats as unique.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def test_the_store_sees_a_case_variant_as_taken(services):
    services.ledger.create_organization("Acme Staffing")
    assert services.auth._store.organization_name_exists("acme staffing") is True
    assert services.auth._store.organization_name_exists("ACME STAFFING") is True
    assert services.auth._store.organization_name_exists("Acme  Staffing") is False, (
        "only CASE is normalised -- collapsing whitespace too would silently "
        "merge two names a customer chose to make different"
    )


def test_ledger_refuses_a_case_variant(services):
    services.ledger.create_organization("Acme Staffing")
    with pytest.raises(ValueError):
        services.ledger.create_organization("acme staffing")


def test_auth_store_refuses_a_case_variant(services):
    from app.auth.store import OrgNameTaken

    services.ledger.create_organization("Acme Staffing")
    with pytest.raises(OrgNameTaken):
        services.auth._store.create_org_with_owner(
            name="ACME STAFFING", email_hash="h" * 64
        )


def test_signup_409s_on_a_case_variant_before_a_code_is_sent(services):
    services.ledger.create_organization("Acme Staffing")
    with _client(services) as c:
        r = c.post("/auth/org/signup",
                   json={"email": "ops@acme.in", "organization_name": "acme staffing"})
        assert r.status_code == 409
        assert r.json()["detail"] == "organization_name_taken"


def test_the_address_enumeration_property_is_untouched(services):
    """The protected fact is whether an ADDRESS has an account. A name is not an
    address, and nothing added here varies with one."""
    services.ledger.create_organization("Acme Staffing")
    with _client(services) as c:
        known = c.post("/auth/org/signup",
                       json={"email": "ops@acme.in", "organization_name": "Fresh Co"})
        unknown = c.post("/auth/org/signup",
                         json={"email": "nobody@nowhere.in", "organization_name": "Other Co"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_org_name_case_insensitive.py -q`
Expected: FAIL — the store finds no collision, the ledger creates the duplicate, signup answers 202.

- [ ] **Step 3: Declare the index on the ORM row**

In `app/ledger/models.py`, add `func` to the SQLAlchemy imports, then append **below the `OrganizationRow` class body** (the deferred form — it needs the mapped column to exist):

```python
# S8.4 Phase B: "Acme Staffing" and "acme staffing" are one customer.
#
# An EXPRESSION index rather than a lowercase companion column, because a
# companion column is a second source of truth maintained by application code at
# two insert sites -- the one-rule-two-doors shape this codebase keeps being bitten
# by. Here the database computes it, so BOTH existing insert paths inherit the
# constraint with no new check: LedgerStore.create_organization and
# AuthStore.create_org_with_owner already map IntegrityError to their own refusal.
#
# MEASURED: SQLite ENFORCES this and does not REFLECT it ("SAWarning: Skipped
# unsupported reflection of expression-based index"), so tests/test_migrations.py
# cannot compare it and proves it behaviourally instead.
Index("uq_organizations_name_ci", func.lower(OrganizationRow.name), unique=True)
```

- [ ] **Step 4: Add the index to migration `0019`**

Append inside `upgrade()`:

```python
    # --- Case-insensitive organisation names (S8.4 Phase B, carry-over 1) -----
    # Refuse loudly rather than mangle: a database already holding both "Acme"
    # and "acme" cannot take this index, and picking a winner on the customer's
    # behalf is not this migration's decision to make.
    conn = op.get_bind()
    dupes = conn.execute(sa.text(
        "SELECT lower(name) AS k FROM organizations "
        "GROUP BY lower(name) HAVING count(*) > 1"
    )).fetchall()
    if dupes:
        names = ", ".join(repr(row[0]) for row in dupes)
        raise RuntimeError(
            "0019 cannot add uq_organizations_name_ci: these organisation names "
            f"already collide case-insensitively and must be resolved first: {names}"
        )
    op.create_index(
        "uq_organizations_name_ci", "organizations",
        [sa.text("lower(name)")], unique=True,
    )
```

and at the **top** of `downgrade()`:

```python
    op.drop_index("uq_organizations_name_ci", table_name="organizations")
```

- [ ] **Step 5: Make the existence check agree with the constraint**

In `app/auth/store.py`, `organization_name_exists` — replace the `where` clause (and ensure `func` is imported):

```python
        with self._session_factory() as session:
            return session.execute(
                select(OrganizationRow.id)
                # lower(), matching uq_organizations_name_ci EXACTLY. A check
                # stricter or looser than its constraint is how the Phase A
                # lockout comes back: the check refuses, the insert succeeds
                # anyway, and two orgs share one name.
                .where(func.lower(OrganizationRow.name) == name.strip().lower())
                .limit(1)
            ).scalars().first() is not None
```

- [ ] **Step 6: Teach the index guard about expression indexes**

In `tests/test_migrations.py`, add above `test_migrated_indexes_match_orm`:

```python
def _is_expression_index(ix) -> bool:
    """True when the index is over an expression (lower(name)) rather than plain
    columns. `ix.columns` still lists the underlying column, so the test is on
    `ix.expressions`, which holds a non-Column element in that case."""
    from sqlalchemy import Column

    return any(not isinstance(e, Column) for e in ix.expressions)
```

and inside that test, filter the ORM side:

```python
        orm = {
            ix.name: (tuple(c.name for c in ix.columns), bool(ix.unique))
            for ix in Base.metadata.tables[table].indexes
            # MEASURED: SQLite does not reflect expression-based indexes at all
            # ("SAWarning: Skipped unsupported reflection of expression-based
            # index"), so comparing one fails on a schema that is correct.
            # uq_organizations_name_ci is proven BEHAVIOURALLY below instead --
            # the stronger check, since this comparison never established that
            # any index was enforced, only that it existed.
            if not _is_expression_index(ix)
        }
```

- [ ] **Step 7: Prove the constraint behaviourally, and prove the migration refuses collisions**

Add to `tests/test_migrations.py` (import `pytest` if the module does not already):

```python
def test_case_insensitive_org_name_is_enforced_on_the_migrated_schema(tmp_path):
    """What the index comparison cannot prove and what actually matters: the
    migrated database REFUSES the collision (S8.4 Phase B §1.7)."""
    import sqlalchemy as sa
    from sqlalchemy.exc import IntegrityError

    engine = _migrated_engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO organizations (id, name, status) "
            "VALUES ('o1','Acme Staffing','active')"))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO organizations (id, name, status) "
                "VALUES ('o2','acme staffing','active')"))


def test_0019_refuses_to_run_over_colliding_org_names(tmp_path):
    """A migration that silently picked a winner would be destroying a
    customer's data to make an index fit."""
    import sqlalchemy as sa

    url, cfg = _scratch_config(tmp_path, "collide.db")
    command.upgrade(cfg, "0018_upload_ownership")
    engine = make_engine(url)
    with engine.begin() as conn:
        for oid, name in (("o1", "Acme"), ("o2", "acme")):
            conn.execute(sa.text(
                "INSERT INTO organizations (id, name, status) "
                f"VALUES ('{oid}','{name}','active')"))

    with pytest.raises(Exception) as exc:
        command.upgrade(cfg, "head")
    assert "acme" in str(exc.value).lower()
```

- [ ] **Step 8: Run the affected files**

Run: `python -m pytest tests/test_org_name_case_insensitive.py tests/test_migrations.py tests/test_auth_org_name_taken.py tests/test_ledger_api.py -q`
Expected: PASS. If `test_auth_org_name_taken.py` fails, read it before touching it — Phase A pins the exact-match behaviour, and a failure there means the normalisation went further than case.

- [ ] **Step 9: Full suite**

Run: `python -m pytest -q`
Expected: no failures.

- [ ] **Step 10: Commit**

```bash
git add app/ledger/models.py app/auth/store.py alembic/versions/0019_screening_batches.py tests/test_migrations.py tests/test_org_name_case_insensitive.py
git commit -m "fix(s84b): organisation names unique case-insensitively, at the constraint"
```

---

## Task 5: `app/screening/pagination.py` — the opaque cursor

**Files:**
- Create: `app/screening/pagination.py`
- Test: `tests/test_screening_pagination.py`

**Interfaces:**
- Consumes: `Settings` (`page_default_limit`, `page_max_limit`).
- Produces: `InvalidCursor(ValueError)`, `encode_cursor(values: tuple) -> str`, `decode_cursor(cursor: str, *, arity: int) -> tuple`, `clamp_limit(limit: Optional[int], settings: Settings) -> int`.

**Context you need:** a cursor is the **sort-key tuple of the last row on the page** — a keyset position, not an offset — so rows inserted while a client pages can be neither skipped nor served twice.

**It carries no authority.** Ownership is enforced by each query's `org_id` filter; a cursor minted on one batch and replayed against another simply positions inside the second. Never add an ownership claim to it — that would make a client-supplied string load-bearing for tenancy, the opposite of Phase A's argument.

Design §1.4 is why this is not universal: `POST /jobs/{id}/match` and `POST /talent/search` re-rank on every request, so no stored key exists and a cursor would promise stability it cannot keep. They keep `limit`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_pagination.py`:

```python
"""S8.4 Phase B: the shared cursor codec.

A cursor is a keyset POSITION -- not an offset, and not a capability.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.screening.pagination import (
    InvalidCursor, clamp_limit, decode_cursor, encode_cursor,
)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def test_round_trips_a_tuple():
    assert decode_cursor(encode_cursor((0.42, "abc")), arity=2) == (0.42, "abc")


def test_round_trips_a_datetime_as_an_iso_string():
    dt = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    raw, ident = decode_cursor(encode_cursor((dt, "id-1")), arity=2)
    assert datetime.fromisoformat(raw) == dt
    assert ident == "id-1"


def test_the_cursor_is_opaque():
    """Not a promise about the encoding -- a promise that clients cannot build
    one by hand and then depend on the shape."""
    c = encode_cursor((1.0, "id-1"))
    assert "id-1" not in c and "1.0" not in c


@pytest.mark.parametrize("bad", ["", "!!!", "YWJj", "bm90LWpzb24"])
def test_a_malformed_cursor_raises_invalid_cursor(bad):
    """422 at the route, never a 500: the caller sent it, so the caller can fix
    it -- and an unhandled decode is a stack trace on the wire."""
    with pytest.raises(InvalidCursor):
        decode_cursor(bad, arity=2)


def test_wrong_arity_is_refused():
    """A cursor of the wrong width would compare a timestamp against an id."""
    with pytest.raises(InvalidCursor):
        decode_cursor(encode_cursor((1.0,)), arity=2)


def test_limit_defaults_and_clamps():
    s = _settings()
    assert clamp_limit(None, s) == s.page_default_limit
    assert clamp_limit(10, s) == 10
    assert clamp_limit(10_000, s) == s.page_max_limit


@pytest.mark.parametrize("bad", [0, -1])
def test_a_nonsense_limit_is_refused(bad):
    with pytest.raises(ValueError):
        clamp_limit(bad, _settings())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_screening_pagination.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screening.pagination'`.

- [ ] **Step 3: Write the module**

Create `app/screening/pagination.py`:

```python
"""One cursor codec, for every list that has a stored order (S8.4 §1.4).

A cursor is the SORT-KEY TUPLE of the last row on a page -- a keyset position,
not an offset -- so a row inserted while a client is paging can neither be
skipped nor served twice. It is base64 so callers cannot read it, hand-build
one, and then depend on a shape we mean to change.

WHAT A CURSOR IS NOT: a capability. Ownership is enforced by each query's own
``org_id`` filter, and a cursor minted on one batch and replayed against
another merely positions inside the second. Nothing here should ever grow an
ownership claim -- that would make a client-supplied string load-bearing for
tenancy, which is the opposite of Phase A's whole argument.

Deliberately NOT applied to ``POST /jobs/{id}/match`` or
``POST /talent/search``: both re-rank their pool on every request, so there is
no stored key to page on and a cursor would promise a stability it cannot keep.
They keep ``limit``, and their OpenAPI descriptions say so.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Optional

from app.core.config import Settings


class InvalidCursor(ValueError):
    """The caller sent a cursor this code cannot read. A 422, never a 500."""


def encode_cursor(values: tuple[Any, ...]) -> str:
    """Encode a sort-key tuple. ``datetime`` serialises ISO-8601 via ``str``."""
    raw = json.dumps(list(values), default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, *, arity: int) -> tuple[Any, ...]:
    """Decode, or raise :class:`InvalidCursor`."""
    if not cursor:
        raise InvalidCursor("empty cursor")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        values = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InvalidCursor("malformed cursor") from exc
    if not isinstance(values, list) or len(values) != arity:
        raise InvalidCursor("malformed cursor")
    return tuple(values)


def clamp_limit(limit: Optional[int], settings: Settings) -> int:
    """Default when absent, cap when excessive, refuse when nonsensical.

    Capping rather than refusing an over-large limit is deliberate: a client
    asking for too much should get a page, not an error it has no way to size
    correctly on its first call.
    """
    if limit is None:
        return settings.page_default_limit
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return min(limit, settings.page_max_limit)
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_screening_pagination.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/screening/pagination.py tests/test_screening_pagination.py
git commit -m "feat(s84b): opaque keyset cursor codec"
```

---

## Task 6: `app/screening/ingest.py` — one ingest core, shared by route and batch

**Files:**
- Create: `app/screening/ingest.py`
- Modify: `app/api/routes.py:312-408` (`_ingest_one` becomes an adapter)
- Modify: `tests/test_org_scope_guard.py` (`ALLOWLISTED_LINES` empties)
- Test: `tests/test_screening_ingest.py`

**Interfaces:**
- Consumes: `Services` attributes (`candidates`, `report_store`, `llm`, `settings`), `EvaluationEngine`.
- Produces:
  - `class IngestRefused(Exception)` with `.reason: str`
  - `@dataclass(frozen=True) IngestDeps(candidates, reports, llm, settings)` + `ingest_deps(services) -> IngestDeps`
  - `@dataclass(frozen=True) IngestResult(candidate_id, resume_id, resume_version, matched_existing, matched_on, duplicate_resume, extraction_method, report, resume_farm)`
  - `async def ingest_resume(deps, engine, *, text, domain, evaluate, org_id) -> IngestResult`

**Context you need — this is a refactor, and its acceptance test is that nothing changes.**

`_ingest_one` takes a FastAPI `Request` and raises `HTTPException`. A batch processor can use neither: it must turn a refusal into a row status, not a status code. So the pipeline moves into a module that raises a domain exception with a **reason code**, and the route becomes a thin adapter mapping it back to 422.

**Change no behaviour.** `tests/test_ingest.py`, `test_candidates_api.py`, `test_screening_api.py`, `test_resume_farm_api.py` and `smoke_s84a` must pass **unmodified**. If one needs editing, the refactor is wrong — re-read the original.

**A guard consequence to handle deliberately, not silently.** All five `ALLOWLISTED_LINES` entries in `tests/test_org_scope_guard.py` are lines *inside `_ingest_one`*. After the move they no longer exist in `routes.py`, so the allowlist becomes dead — and a dead content-keyed allowlist is a silent exemption waiting to match an unrelated future line. Empty it and assert it is empty, which leaves the guard with **no exemptions at all**. The reduction in what the guard *sees* is honest: those five lines were being waved through anyway, and the one genuinely cross-tenant read among them (`similar_resumes` — which must scan every customer's fingerprints or the farm check is worthless) is still bounded where it always was, at the org boundary by `redact_ingest_response_for_org`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_ingest.py`:

```python
"""S8.4 Phase B: the ingest core, extracted so batches and the single-upload
route run the SAME pipeline. Duplicating it would be the one-rule-two-doors
shape committed on purpose, in the sprint whose subject is that shape."""

from __future__ import annotations

import pytest

from app.graph.build import EvaluationEngine
from app.screening.ingest import IngestRefused, ingest_deps, ingest_resume


@pytest.mark.asyncio
async def test_ingest_resume_stamps_the_owner_and_returns_a_report(services, genuine_resume):
    org = services.ledger.create_organization("Acme Staffing")
    result = await ingest_resume(
        ingest_deps(services), EvaluationEngine(services),
        text=genuine_resume, domain="genai", evaluate=True, org_id=org.id,
    )
    assert result.candidate_id and result.resume_id
    assert result.report is not None
    assert services.report_store.get_for_org(org.id, result.report.id) is not None


@pytest.mark.asyncio
async def test_evaluate_false_skips_the_graph_but_still_ingests(services, genuine_resume):
    result = await ingest_resume(
        ingest_deps(services), EvaluationEngine(services),
        text=genuine_resume, domain="genai", evaluate=False, org_id=None,
    )
    assert result.report is None
    assert result.resume_farm is not None, "the farm check runs at ingest, not in the graph"


@pytest.mark.asyncio
async def test_empty_text_raises_a_reason_code_not_an_http_exception(services):
    """The batch processor writes this onto a row; a route maps it to 422.
    Neither can use an HTTPException."""
    with pytest.raises(IngestRefused) as exc:
        await ingest_resume(
            ingest_deps(services), EvaluationEngine(services),
            text="   ", domain="genai", evaluate=True, org_id=None,
        )
    assert exc.value.reason == "empty_resume"


@pytest.mark.asyncio
async def test_unknown_domain_is_refused_with_a_reason_code(services, genuine_resume):
    with pytest.raises(IngestRefused) as exc:
        await ingest_resume(
            ingest_deps(services), EvaluationEngine(services),
            text=genuine_resume, domain="no-such-domain", evaluate=True, org_id=None,
        )
    assert exc.value.reason == "unknown_domain"


@pytest.mark.asyncio
async def test_oversize_text_is_refused_with_a_reason_code(services):
    caps = services.settings
    with pytest.raises(IngestRefused) as exc:
        await ingest_resume(
            ingest_deps(services), EvaluationEngine(services),
            text="x" * (caps.max_resume_chars + 1), domain="genai",
            evaluate=True, org_id=None,
        )
    assert exc.value.reason == "resume_too_long"


@pytest.mark.asyncio
async def test_the_reason_codes_are_a_closed_vocabulary(services):
    """batch_items.error is String(64) holding these codes -- never prose and
    never model output. A code longer than the column is a write that fails at
    the worst possible moment."""
    from app.screening import ingest as mod

    for code in ("empty_resume", "unknown_domain", "resume_too_long"):
        assert len(code) <= 64
    assert IngestRefused("empty_resume").reason == "empty_resume"
    assert mod is not None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_screening_ingest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screening.ingest'`.

- [ ] **Step 3: Write the module**

Create `app/screening/ingest.py`. Copy the pipeline out of `_ingest_one` **verbatim** except for the refusals and the dependency access — and check every import against `app/api/routes.py`'s own import block before running, since these symbols must come from exactly the modules the route imports them from today:

```python
"""The ONE ingest core (S8.4 Phase B, design §1.3).

``POST /screening/candidates`` and ``POST /screening/batches/{id}/process`` run
the same pipeline: extract, resolve identity, store, fingerprint, farm-check,
evaluate. It lives here rather than in the route because the batch processor
cannot use a FastAPI ``Request`` and must turn a refusal into a row status
rather than a status code.

So refusals are ``IngestRefused(reason)`` carrying a reason CODE, and the two
callers map it their own way: the route to 422, the processor to
``status='failed', error=<reason>``.

Extracting this also emptied ``ALLOWLISTED_LINES`` in
``tests/test_org_scope_guard.py`` -- all five exemptions were lines of this
function. The one genuinely cross-tenant read among them, ``similar_resumes``
(which must scan every customer's fingerprints or the resume-farm check is
worthless), is still bounded exactly where it was: at the org-plane boundary by
``redact_ingest_response_for_org``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from app.candidates.store import CandidateStore, MatchedOn
from app.core.config import Settings
from app.reports.store import ReportStore, SubjectErasedError
from app.schemas.fabrication import ResumeFarmAssessment
from app.schemas.report import Report
from app.services.llm import LLMClient

if TYPE_CHECKING:
    from app.graph.build import EvaluationEngine
    from app.services import Services


class IngestRefused(Exception):
    """A refusal carrying a reason CODE, never prose.

    The code is written onto ``batch_items.error`` -- a ``String(64)`` holding
    closed vocabulary, never model output and never another row's content.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class IngestDeps:
    """Exactly what ingestion needs, so nothing here reaches a whole container."""

    candidates: CandidateStore
    reports: ReportStore
    llm: LLMClient
    settings: Settings


def ingest_deps(services: "Services") -> IngestDeps:
    return IngestDeps(
        candidates=services.candidates,
        reports=services.report_store,
        llm=services.llm,
        settings=services.settings,
    )


@dataclass(frozen=True)
class IngestResult:
    candidate_id: str
    resume_id: str
    resume_version: int
    matched_existing: bool
    matched_on: Optional[MatchedOn]
    duplicate_resume: bool
    extraction_method: str
    report: Optional[Report]
    resume_farm: ResumeFarmAssessment


async def ingest_resume(
    deps: IngestDeps,
    engine: "EvaluationEngine",
    *,
    text: str,
    domain: str,
    evaluate: bool,
    org_id: Optional[str],
) -> IngestResult:
    """Upload -> extract -> store -> (auto) depth-eval, for ONE resume.

    ``org_id`` is the owner stamped on the resume and on the report; ``None`` is
    the admin plane, which owns nothing by design.
    """
    # Function-local: these pull in the domain registry and the graph, and a
    # top-level import would cycle back through app.services.
    # Paths VERIFIED against app/api/routes.py:27-32 -- note `domains.base`
    # (not `app.domains`) and `fabrication.similarity` (not `resume_farm`).
    from app.candidates.extractor import extract_profile
    from app.domains.base import get_domain
    from app.fabrication.similarity import assess_resume_farm, fingerprint_text

    if len(text) > deps.settings.max_resume_chars:
        raise IngestRefused("resume_too_long")
    text = (text or "").strip()
    if not text:
        raise IngestRefused("empty_resume")
    try:
        get_domain(domain)
    except KeyError as exc:
        raise IngestRefused("unknown_domain") from exc

    result = await extract_profile(text, llm=deps.llm, settings=deps.settings)
    outcome = deps.candidates.ingest(result, text, org_id=org_id)

    # S2.3: fingerprint + farm check. Lives HERE, not in a graph node: the
    # comparison must exclude the uploader's own candidate (re-uploads and new
    # versions are legitimate), and the graph deliberately never learns the
    # candidate identity.
    farm = ResumeFarmAssessment()  # insufficient_data when the text is too short
    fp = fingerprint_text(text, deps.settings)
    if fp is not None:
        deps.candidates.save_fingerprint(
            fp, resume_id=outcome.resume_id, candidate_id=outcome.candidate_id
        )
        matches, corpus = deps.candidates.similar_resumes(
            fp,
            exclude_candidate_id=outcome.candidate_id,
            threshold=deps.settings.rf_similar_threshold,
            limit=deps.settings.rf_max_matches,
        )
        farm = assess_resume_farm(
            matches, shingle_count=fp.shingle_count, corpus_size=corpus,
            settings=deps.settings,
        )

    report: Optional[Report] = None
    if evaluate:
        report = await engine.evaluate(
            resume_text=text, domain=domain,
            candidate_profile=result.profile, resume_farm=farm,
        )
        report.candidate_id = outcome.candidate_id
        # DPDP: a derived report must not outlive the erasure of its subject.
        # Since S8.1 the foreign key REFUSES the orphan outright, and an erasure
        # landing after the save cascades the row away -- so both halves of this
        # race are the database's job, not a compensating delete we remember.
        try:
            deps.reports.save(report, org_id=org_id)
        except SubjectErasedError:
            report = None
        else:
            if deps.candidates.get_candidate(outcome.candidate_id) is None:
                report = None

    return IngestResult(
        candidate_id=outcome.candidate_id,
        resume_id=outcome.resume_id,
        resume_version=outcome.resume_version,
        matched_existing=outcome.matched_existing,
        matched_on=outcome.matched_on,
        duplicate_resume=outcome.duplicate_resume,
        extraction_method=result.method,
        report=report,
        resume_farm=farm,
    )
```

- [ ] **Step 4: Make `_ingest_one` an adapter**

Replace the body of `_ingest_one` in `app/api/routes.py`, adding
`from app.screening.ingest import IngestRefused, ingest_deps, ingest_resume`
beside the existing `app.screening.projection` import:

```python
async def _ingest_one(
    req: CandidateCreateRequest, request: Request, *, org_id: Optional[str] = None
) -> CandidateCreateResponse:
    """HTTP adapter over the ONE ingest core (app/screening/ingest.py).

    Shared by the admin route (no owner) and the org route (owner = caller).
    The pipeline itself moved out so the batch processor runs the same code:
    duplicating it would be the one-rule-two-doors shape in the sprint that
    exists to eliminate it.
    """
    services = _services(request)
    caps = services.settings

    if req.resume_text and len(req.resume_text) > caps.max_resume_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_text exceeds max_resume_chars={caps.max_resume_chars}",
        )
    if req.resume_pdf_b64 and len(req.resume_pdf_b64) > caps.max_pdf_b64_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_pdf_b64 exceeds max_pdf_b64_chars={caps.max_pdf_b64_chars}",
        )
    # Kept in the route so the 422 detail stays byte-identical to what clients
    # (and five smokes) already assert.
    try:
        get_domain(req.domain)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    text = req.resume_text
    if not text and req.resume_pdf_b64:
        try:
            text = pdf_b64_to_text(req.resume_pdf_b64)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"pdf_parse_failed: {exc}"
            ) from exc

    try:
        result = await ingest_resume(
            ingest_deps(services), request.app.state.engine,
            text=text or "", domain=req.domain, evaluate=req.evaluate, org_id=org_id,
        )
    except IngestRefused as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc

    return CandidateCreateResponse(
        candidate_id=result.candidate_id,
        resume_id=result.resume_id,
        resume_version=result.resume_version,
        matched_existing=result.matched_existing,
        matched_on=result.matched_on,
        duplicate_resume=result.duplicate_resume,
        extraction_method=result.extraction_method,
        report=result.report,
        resume_farm=result.resume_farm,
    )
```

> **The two detail strings that must not drift:** `max_resume_chars` and the domain `KeyError` message are asserted by existing tests and smokes, which is why both checks stay in the route rather than being read back off `IngestRefused`. If a test still fails on a detail string, fix the route — never the test.

- [ ] **Step 5: Empty the guard's allowlist**

In `tests/test_org_scope_guard.py`, replace the whole `ALLOWLISTED_LINES` dict:

```python
#: EMPTY, and that is the point (S8.4 Phase B, Task 6). Every entry here was a
#: line of `_ingest_one`, which moved to app/screening/ingest.py -- so the guard
#: now runs with NO exemptions at all. A content-keyed allowlist whose keys no
#: longer exist is not harmless: it is a silent exemption waiting to match an
#: unrelated future line that happens to contain the same text.
ALLOWLISTED_LINES: dict[str, str] = {}
```

and add:

```python
def test_the_guard_has_no_exemptions():
    """If a line ever needs allowlisting again, this test is where a reviewer is
    forced to look at the reason."""
    assert ALLOWLISTED_LINES == {}
```

- [ ] **Step 6: Run the ingest suite unmodified — the acceptance test**

Run:
```bash
python -m pytest tests/test_screening_ingest.py tests/test_ingest.py tests/test_candidates_api.py tests/test_screening_api.py tests/test_resume_farm_api.py tests/test_org_scope_guard.py tests/test_api.py -q
```
Expected: PASS, **with no edits to any pre-existing test file**.

- [ ] **Step 7: Full suite**

Run: `python -m pytest -q`
Expected: no failures.

- [ ] **Step 8: Smoke the path that exercises it end to end**

Run: `python scripts/smoke_s84a.py`
Expected: 23/23, exit 0.

- [ ] **Step 9: Commit**

```bash
git add app/screening/ingest.py app/api/routes.py tests/test_screening_ingest.py tests/test_org_scope_guard.py
git commit -m "refactor(s84b): one ingest core for the route and the batch processor"
```

---

## Task 7: `app/screening/store.py` — the org-scoped batch store

**Files:**
- Create: `app/screening/store.py`
- Test: `tests/test_screening_store.py`

**Interfaces:**
- Consumes: `ScreeningBatchRow` / `BatchItemRow` (Task 3), `ItemStatus` / `ItemSignals` / `BatchCounts` (Task 2), the cursor codec (Task 5).
- Produces `ScreeningStore` — **every method takes `org_id` first**:
  - `create_batch(org_id, *, name, domain, created_by_org_user_id, texts: list[str]) -> str`
  - `batch_row(org_id, batch_id) -> Optional[BatchRecord]`
  - `counts(org_id, batch_id, *, now) -> Optional[BatchCounts]`
  - `list_batches(org_id, *, cursor, limit) -> tuple[list[BatchRecord], Optional[str]]`
  - `claim(org_id, batch_id, *, limit, now, timeout_seconds) -> list[ClaimedItem]`
  - `complete(item_id, *, candidate_id, resume_id, report_id, risk_score, signals, at) -> None`
  - `fail(item_id, *, error, at) -> None`
  - `queue_page(org_id, batch_id, *, cursor, limit, now) -> Optional[tuple[list[ItemRecord], Optional[str]]]`
  - `all_items(org_id, batch_id, *, now) -> Optional[list[ItemRecord]]`
  - `delete_batch(org_id, batch_id) -> bool`
  - plus `build_screening_store(settings)`
- Dataclasses `BatchRecord` and `ItemRecord` (plain, not Pydantic — these are storage shapes; the service maps them to wire types).

**Context you need:**

1. **Ownership is a `WHERE` clause, never a Python check after the fact.** Every read joins or filters on `screening_batches.org_id == org_id`, and a batch belonging to another org returns `None` so the route answers 404 (never 403 — a 403 confirms it exists).

2. **The claim is a conditional UPDATE.** Two browser tabs can both `POST .../process`, and each item is a full nine-node graph run — on a live model that is money. The read that *chooses* an item may be stale; the write that *claims* it must not be. So the claim is `UPDATE ... WHERE id = :id AND <still claimable>` and counts only if `rowcount == 1`.

3. **"Still claimable" includes stale `processing`** (spec §4.4): `status='pending'` OR (`status='processing'` AND (`claimed_at IS NULL` OR `claimed_at < now - timeout`)). A NULL `claimed_at` on a processing row is a bug state, and treating it as stale is the self-healing choice.

4. **`raw_text` is cleared on success and kept on failure** — the org must be able to retry a failure, and success moves the text to `resumes`, where candidate erasure already cascades.

5. **Reading reinterprets a stale claim.** `counts` and `queue_page` map a stale `processing` row back to `pending`, so a batch interrupted by a redeploy *reads* as resumable rather than wedged. The stored value is never rewritten by a read.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_store.py`:

```python
"""S8.4 Phase B: the batch store.

Two properties here are worth more than the rest: an item cannot be claimed
twice (each claim is a paid graph run), and a batch that belongs to somebody
else is indistinguishable from one that does not exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.screening.schema import ItemSignals, ItemStatus
from app.screening.store import ScreeningStore

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(services) -> ScreeningStore:
    return ScreeningStore(services.candidates._session_factory)


def _org(services, name="Acme Staffing"):
    return services.ledger.create_organization(name).id


def test_register_creates_items_and_nothing_else(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="Q3", domain="genai",
                             created_by_org_user_id=None,
                             texts=["resume one", "resume two"])
    counts = store.counts(org, bid, now=NOW)
    assert counts.pending == 2 and counts.total == 2
    assert store.batch_row(org, bid).name == "Q3"


def test_another_orgs_batch_is_invisible_everywhere(store, services):
    a, b = _org(services, "A"), _org(services, "B")
    bid = store.create_batch(a, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["t"])
    assert store.batch_row(b, bid) is None
    assert store.counts(b, bid, now=NOW) is None
    assert store.queue_page(b, bid, cursor=None, limit=10, now=NOW) is None
    assert store.claim(b, bid, limit=5, now=NOW, timeout_seconds=900) == []
    assert store.delete_batch(b, bid) is False
    assert store.batch_row(a, bid) is not None, "and A still has it"


def test_claim_is_bounded_and_marks_items_processing(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None,
                             texts=[f"resume {i}" for i in range(5)])
    claimed = store.claim(org, bid, limit=2, now=NOW, timeout_seconds=900)
    assert len(claimed) == 2
    assert all(c.raw_text for c in claimed)
    counts = store.counts(org, bid, now=NOW)
    assert (counts.processing, counts.pending) == (2, 3)


def test_an_item_cannot_be_claimed_twice(store, services):
    """The whole reason the claim is a conditional UPDATE: each item is a full
    nine-node graph run, and on a live model a double claim is double money."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["only one"])
    first = store.claim(org, bid, limit=5, now=NOW, timeout_seconds=900)
    second = store.claim(org, bid, limit=5, now=NOW, timeout_seconds=900)
    assert len(first) == 1 and second == []


def test_a_stale_claim_is_reclaimed_and_reads_as_pending(store, services):
    """Spec §4.4: a batch interrupted by a redeploy heals itself instead of
    wedging with items nobody will ever claim."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)

    later = NOW + timedelta(seconds=901)
    assert store.counts(org, bid, now=later).pending == 1, (
        "a read reinterprets a stale claim; it never rewrites the row"
    )
    again = store.claim(org, bid, limit=1, now=later, timeout_seconds=900)
    assert len(again) == 1


def test_complete_clears_the_text_and_stamps_the_signals(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]
    store.complete(item.id, candidate_id=None, resume_id=None, report_id=None,
                   risk_score=0.8, signals=ItemSignals(risk_confidence=0.5), at=NOW)

    rows = store.all_items(org, bid, now=NOW)
    assert rows[0].status is ItemStatus.DONE
    assert rows[0].raw_text == "", (
        "the text now lives in `resumes`, where candidate erasure cascades"
    )
    assert rows[0].risk_score == 0.8
    assert rows[0].signals.risk_confidence == 0.5


def test_fail_keeps_the_text_so_the_org_can_retry(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]
    store.fail(item.id, error="empty_resume", at=NOW)

    rows = store.all_items(org, bid, now=NOW)
    assert rows[0].status is ItemStatus.FAILED
    assert rows[0].raw_text == "one", "failure is not a reason to destroy the input"
    assert rows[0].error == "empty_resume"


def test_unreadable_signals_degrade_to_none_rather_than_raising(store, services):
    """S7.3's finding: one unparseable stored blob must not brick every later
    read of the batch it belongs to."""
    from sqlalchemy import update
    from app.screening.models import BatchItemRow

    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]
    store.complete(item.id, candidate_id=None, resume_id=None, report_id=None,
                   risk_score=0.4, signals=ItemSignals(), at=NOW)
    with services.candidates._session_factory() as s:
        s.execute(update(BatchItemRow).where(BatchItemRow.id == item.id)
                  .values(signals={"risk_band": "not-a-band"}))
        s.commit()

    rows = store.all_items(org, bid, now=NOW)
    assert rows[0].signals is None
    assert rows[0].risk_score == 0.4, "the sort key is a real column and survives"


def test_the_queue_is_ranked_by_risk_with_unscored_items_last(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None,
                             texts=["a", "b", "c"])
    claimed = store.claim(org, bid, limit=2, now=NOW, timeout_seconds=900)
    store.complete(claimed[0].id, candidate_id=None, resume_id=None, report_id=None,
                   risk_score=0.3, signals=ItemSignals(), at=NOW)
    store.complete(claimed[1].id, candidate_id=None, resume_id=None, report_id=None,
                   risk_score=0.9, signals=ItemSignals(), at=NOW)

    rows, _ = store.queue_page(org, bid, cursor=None, limit=10, now=NOW)
    assert [r.risk_score for r in rows] == [0.9, 0.3, None]
    assert rows[-1].status is ItemStatus.PENDING, "unscreened rows are shown, last"


def test_paging_across_an_insert_neither_skips_nor_duplicates(store, services):
    """The reason the cursor is a keyset position rather than an offset."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["a", "b", "c"])
    items = store.claim(org, bid, limit=3, now=NOW, timeout_seconds=900)
    for item, score in zip(items, (0.9, 0.6, 0.3)):
        store.complete(item.id, candidate_id=None, resume_id=None, report_id=None,
                       risk_score=score, signals=ItemSignals(), at=NOW)

    first, cursor = store.queue_page(org, bid, cursor=None, limit=2, now=NOW)
    assert cursor is not None

    # A new item lands between the two page reads.
    store.add_items(org, bid, texts=["late arrival"])

    second, _ = store.queue_page(org, bid, cursor=cursor, limit=10, now=NOW)
    seen = [r.item_id for r in first] + [r.item_id for r in second]
    assert len(seen) == len(set(seen)), "no row served twice"
    assert {r.item_id for r in items} <= set(seen), "no scored row skipped"


def test_a_cursor_from_another_batch_cannot_reach_its_rows(store, services):
    """A cursor is a sort POSITION, not a capability -- the org_id/batch_id
    filter is what protects the boundary."""
    org = _org(services)
    mine = store.create_batch(org, name="mine", domain="genai",
                              created_by_org_user_id=None, texts=["a", "b"])
    other = store.create_batch(org, name="other", domain="genai",
                               created_by_org_user_id=None, texts=["c", "d"])
    _, cursor = store.queue_page(org, mine, cursor=None, limit=1, now=NOW)

    rows, _ = store.queue_page(org, other, cursor=cursor, limit=10, now=NOW)
    other_ids = {r.item_id for r in store.all_items(org, other, now=NOW)}
    assert {r.item_id for r in rows} <= other_ids


def test_delete_removes_items_and_their_text(store, services):
    from sqlalchemy import func, select
    from app.screening.models import BatchItemRow

    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["a", "b"])
    assert store.delete_batch(org, bid) is True
    assert store.batch_row(org, bid) is None
    with services.candidates._session_factory() as s:
        assert s.execute(select(func.count()).select_from(BatchItemRow)).scalar() == 0


def test_list_batches_is_newest_first_and_pages(store, services):
    org = _org(services)
    ids = [
        store.create_batch(org, name=f"b{i}", domain="genai",
                           created_by_org_user_id=None, texts=["t"])
        for i in range(3)
    ]
    page, cursor = store.list_batches(org, cursor=None, limit=2)
    assert len(page) == 2 and cursor is not None
    rest, _ = store.list_batches(org, cursor=cursor, limit=10)
    assert {b.id for b in page} | {b.id for b in rest} == set(ids)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_screening_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screening.store'`.

- [ ] **Step 3: Write the store**

Create `app/screening/store.py`:

```python
"""Screening batches: persistence, org-scoped by construction (S8.4 Phase B).

EVERY method takes ``org_id`` first and turns it into a WHERE clause. There is
no unscoped read on this object -- the same rule as ``OrgScopedReads``, one
table further along, and for the same reason: a rule enforced by remembering to
enforce it gets forgotten at the second door.

A batch that belongs to another organisation returns ``None``/``False``/``[]``
so the route can answer 404. Never an exception, never a 403: a 403 confirms
the batch exists, which is the fact being protected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import get_logger
from app.ledger.consent import as_utc
from app.screening.models import BatchItemRow, ScreeningBatchRow
from app.screening.pagination import decode_cursor, encode_cursor
from app.screening.schema import BatchCounts, ItemSignals, ItemStatus

log = get_logger("screening.store")

#: The queue's sort key for an item that has not been scored yet. Below every
#: real score (which is >= 0.0), so unscreened rows sort last under DESC.
_UNSCORED = -1.0


@dataclass(frozen=True)
class BatchRecord:
    id: str
    org_id: str
    name: str
    domain: str
    created_by_org_user_id: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class ItemRecord:
    item_id: str
    status: ItemStatus
    raw_text: str
    candidate_id: Optional[str]
    resume_id: Optional[str]
    report_id: Optional[str]
    risk_score: Optional[float]
    signals: Optional[ItemSignals]
    error: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]


@dataclass(frozen=True)
class ClaimedItem:
    id: str
    raw_text: str
    domain: str


def _signals_of(row: BatchItemRow) -> Optional[ItemSignals]:
    """Parse the stored blob, or degrade to None.

    S7.3's finding, applied here before it can happen: one unparseable write
    must not raise on EVERY later read of the batch it belongs to. The sort key
    lives in its own column, so a queue whose signals cannot be read still
    ranks correctly.
    """
    if row.signals is None:
        return None
    try:
        return ItemSignals.model_validate(row.signals)
    except ValidationError:
        log.warning("unreadable_item_signals", item_id=row.id)
        return None


class ScreeningStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    # ── writes ──────────────────────────────────────────────────────────────

    def create_batch(
        self,
        org_id: str,
        *,
        name: str,
        domain: str,
        created_by_org_user_id: Optional[str],
        texts: list[str],
    ) -> str:
        """Register a batch and its items. NO evaluation -- a row insert."""
        with self._session_factory() as s:
            batch = ScreeningBatchRow(
                org_id=org_id, name=name, domain=domain,
                created_by_org_user_id=created_by_org_user_id,
            )
            s.add(batch)
            s.flush()
            for text in texts:
                s.add(self._new_item(batch.id, text))
            s.commit()
            return batch.id

    def add_items(self, org_id: str, batch_id: str, *, texts: list[str]) -> bool:
        """Append items to an existing batch (used by tests and by a resumed
        upload). Scoped like every other method."""
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return False
            for text in texts:
                s.add(self._new_item(batch_id, text))
            s.commit()
            return True

    @staticmethod
    def _new_item(batch_id: str, text: str) -> BatchItemRow:
        return BatchItemRow(
            batch_id=batch_id,
            status=ItemStatus.PENDING.value,
            raw_text=text,
            text_sha256=sha256(text.encode("utf-8")).hexdigest(),
            created_at=datetime.now(timezone.utc),
        )

    def claim(
        self,
        org_id: str,
        batch_id: str,
        *,
        limit: int,
        now: datetime,
        timeout_seconds: int,
    ) -> list[ClaimedItem]:
        """Claim up to ``limit`` claimable items, one conditional UPDATE each.

        The read that CHOOSES an item can be stale -- two browser tabs both hit
        ``POST .../process``. The write that CLAIMS it cannot: it re-asserts
        claimability in its own WHERE clause and counts only if it changed a
        row. Each item is a full nine-node graph run, so a double claim is a
        double bill.
        """
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return []

            claimable = self._claimable(now, timeout_seconds)
            ids = s.execute(
                select(BatchItemRow.id)
                .where(BatchItemRow.batch_id == batch_id, claimable)
                .order_by(BatchItemRow.created_at, BatchItemRow.id)
                .limit(limit)
            ).scalars().all()

            claimed: list[str] = []
            for item_id in ids:
                res = s.execute(
                    update(BatchItemRow)
                    .where(BatchItemRow.id == item_id, claimable)
                    .values(status=ItemStatus.PROCESSING.value, claimed_at=now)
                )
                if res.rowcount == 1:
                    claimed.append(item_id)
            s.commit()

            if not claimed:
                return []
            rows = s.execute(
                select(BatchItemRow).where(BatchItemRow.id.in_(claimed))
            ).scalars().all()
            order = {item_id: i for i, item_id in enumerate(claimed)}
            rows.sort(key=lambda r: order[r.id])
            return [
                ClaimedItem(id=r.id, raw_text=r.raw_text, domain=batch.domain)
                for r in rows
            ]

    @staticmethod
    def _claimable(now: datetime, timeout_seconds: int):
        """pending, or a `processing` claim old enough to be presumed dead.

        A NULL ``claimed_at`` on a processing row is a bug state; treating it as
        stale is the self-healing reading (spec §4.4).
        """
        stale_before = now - timedelta(seconds=timeout_seconds)
        return or_(
            BatchItemRow.status == ItemStatus.PENDING.value,
            and_(
                BatchItemRow.status == ItemStatus.PROCESSING.value,
                or_(
                    BatchItemRow.claimed_at.is_(None),
                    BatchItemRow.claimed_at < stale_before,
                ),
            ),
        )

    def complete(
        self,
        item_id: str,
        *,
        candidate_id: Optional[str],
        resume_id: Optional[str],
        report_id: Optional[str],
        risk_score: Optional[float],
        signals: ItemSignals,
        at: datetime,
    ) -> None:
        """Success. CLEARS ``raw_text``: the text now lives in ``resumes``,
        where candidate erasure already cascades (spec §4.2)."""
        with self._session_factory() as s:
            s.execute(
                update(BatchItemRow)
                .where(BatchItemRow.id == item_id)
                .values(
                    status=ItemStatus.DONE.value,
                    raw_text="",
                    candidate_id=candidate_id,
                    resume_id=resume_id,
                    report_id=report_id,
                    risk_score=risk_score,
                    signals=signals.model_dump(mode="json"),
                    error=None,
                    processed_at=at,
                )
            )
            s.commit()

    def fail(self, item_id: str, *, error: str, at: datetime) -> None:
        """Failure KEEPS ``raw_text`` -- the org must be able to retry, and
        failure is not a reason to destroy the input."""
        with self._session_factory() as s:
            s.execute(
                update(BatchItemRow)
                .where(BatchItemRow.id == item_id)
                .values(
                    status=ItemStatus.FAILED.value,
                    error=error[:64],
                    processed_at=at,
                )
            )
            s.commit()

    def delete_batch(self, org_id: str, batch_id: str) -> bool:
        """Delete the batch, its items and their text. Items CASCADE."""
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return False
            s.delete(batch)
            s.commit()
            return True

    # ── reads ───────────────────────────────────────────────────────────────

    def batch_row(self, org_id: str, batch_id: str) -> Optional[BatchRecord]:
        with self._session_factory() as s:
            row = s.get(ScreeningBatchRow, batch_id)
            if row is None or row.org_id != org_id:
                return None
            return self._batch_record(row)

    def list_batches(
        self, org_id: str, *, cursor: Optional[str], limit: int
    ) -> tuple[list[BatchRecord], Optional[str]]:
        """Newest first, keyed on ``(created_at, id)``."""
        with self._session_factory() as s:
            q = select(ScreeningBatchRow).where(ScreeningBatchRow.org_id == org_id)
            if cursor is not None:
                last_created, last_id = decode_cursor(cursor, arity=2)
                cut = datetime.fromisoformat(last_created)
                q = q.where(
                    or_(
                        ScreeningBatchRow.created_at < cut,
                        and_(
                            ScreeningBatchRow.created_at == cut,
                            ScreeningBatchRow.id > last_id,
                        ),
                    )
                )
            rows = s.execute(
                q.order_by(ScreeningBatchRow.created_at.desc(), ScreeningBatchRow.id)
                .limit(limit + 1)
            ).scalars().all()

            more = len(rows) > limit
            rows = rows[:limit]
            next_cursor = (
                encode_cursor((as_utc(rows[-1].created_at), rows[-1].id))
                if more and rows else None
            )
            return [self._batch_record(r) for r in rows], next_cursor

    def counts(
        self, org_id: str, batch_id: str, *, now: datetime
    ) -> Optional[BatchCounts]:
        """Item counts, with a stale claim READ as pending.

        The read reinterprets; it never rewrites. A stored status corrected by
        a read would be a fact that depends on who looked at it last.
        """
        items = self.all_items(org_id, batch_id, now=now)
        if items is None:
            return None
        counts = BatchCounts()
        for item in items:
            setattr(counts, item.status.value, getattr(counts, item.status.value) + 1)
        return counts

    def all_items(
        self, org_id: str, batch_id: str, *, now: datetime
    ) -> Optional[list[ItemRecord]]:
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return None
            rows = s.execute(
                select(BatchItemRow)
                .where(BatchItemRow.batch_id == batch_id)
                .order_by(BatchItemRow.created_at, BatchItemRow.id)
            ).scalars().all()
            return [self._item_record(r, now=now) for r in rows]

    def queue_page(
        self,
        org_id: str,
        batch_id: str,
        *,
        cursor: Optional[str],
        limit: int,
        now: datetime,
    ) -> Optional[tuple[list[ItemRecord], Optional[str]]]:
        """Riskiest first; unscreened and failed rows last.

        ``COALESCE(risk_score, -1)`` rather than ``NULLS LAST``: SQLite sorts
        NULLs first under DESC and has no NULLS LAST, so the expression is the
        portable spelling of the same intent.
        """
        with self._session_factory() as s:
            batch = s.get(ScreeningBatchRow, batch_id)
            if batch is None or batch.org_id != org_id:
                return None

            sort_key = func.coalesce(BatchItemRow.risk_score, _UNSCORED)
            q = select(BatchItemRow).where(BatchItemRow.batch_id == batch_id)
            if cursor is not None:
                last_score, last_id = decode_cursor(cursor, arity=2)
                q = q.where(
                    or_(
                        sort_key < last_score,
                        and_(sort_key == last_score, BatchItemRow.id > last_id),
                    )
                )
            rows = s.execute(
                q.order_by(sort_key.desc(), BatchItemRow.id).limit(limit + 1)
            ).scalars().all()

            more = len(rows) > limit
            rows = rows[:limit]
            next_cursor = (
                encode_cursor(
                    (rows[-1].risk_score if rows[-1].risk_score is not None else _UNSCORED,
                     rows[-1].id)
                )
                if more and rows else None
            )
            return [self._item_record(r, now=now) for r in rows], next_cursor

    # ── mapping ─────────────────────────────────────────────────────────────

    @staticmethod
    def _batch_record(row: ScreeningBatchRow) -> BatchRecord:
        return BatchRecord(
            id=row.id, org_id=row.org_id, name=row.name or "", domain=row.domain,
            created_by_org_user_id=row.created_by_org_user_id,
            created_at=as_utc(row.created_at),
        )

    def _item_record(self, row: BatchItemRow, *, now: datetime) -> ItemRecord:
        status = ItemStatus(row.status)
        return ItemRecord(
            item_id=row.id,
            status=status,
            raw_text=row.raw_text or "",
            candidate_id=row.candidate_id,
            resume_id=row.resume_id,
            report_id=row.report_id,
            risk_score=row.risk_score,
            signals=_signals_of(row),
            error=row.error,
            created_at=as_utc(row.created_at),
            processed_at=as_utc(row.processed_at) if row.processed_at else None,
        )


def build_screening_store(settings: Optional[Settings] = None) -> ScreeningStore:
    """On the shared candidates DB URL -- one metadata root, one Alembic env.
    Schema is Alembic's job, NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return ScreeningStore(make_session_factory(engine))
```

> **The stale-claim reinterpretation is missing from `_item_record` on purpose in the code above — add it.** `_item_record` needs the `now` and the timeout to map a stale `processing` row to `PENDING`. Give `ScreeningStore.__init__` a `claim_timeout_seconds: int = 900` parameter, store it, and in `_item_record` write:
>
> ```python
>         status = ItemStatus(row.status)
>         if (
>             status is ItemStatus.PROCESSING
>             and (row.claimed_at is None
>                  or as_utc(row.claimed_at) < now - timedelta(seconds=self._claim_timeout))
>         ):
>             # Spec §4.4: a claim nobody is honouring reads as pending again, so
>             # a batch interrupted by a redeploy heals on the next process call.
>             status = ItemStatus.PENDING
> ```
>
> and pass `settings.screening_claim_timeout_seconds` from `build_screening_store`. The test `test_a_stale_claim_is_reclaimed_and_reads_as_pending` is what forces this; do not consider the task done until it passes.

- [ ] **Step 4: Run the store tests**

Run: `python -m pytest tests/test_screening_store.py -q`
Expected: PASS (14 tests).

- [ ] **Step 5: Mutation-test the claim predicate**

The claim is one of the two places a silent mutant is expensive (design §6). Apply each mutation by hand, confirm a test goes red, then revert:

| Mutation | Test that must fail |
|---|---|
| Drop `claimable` from the `update().where(...)` | `test_an_item_cannot_be_claimed_twice` |
| Change `res.rowcount == 1` to `res.rowcount >= 0` | `test_an_item_cannot_be_claimed_twice` |
| Drop the stale branch from `_claimable` | `test_a_stale_claim_is_reclaimed_and_reads_as_pending` |
| Drop `row.org_id != org_id` from `claim` | `test_another_orgs_batch_is_invisible_everywhere` |
| Drop `row.org_id != org_id` from `queue_page` | `test_another_orgs_batch_is_invisible_everywhere` |
| Drop `BatchItemRow.batch_id == batch_id` from `queue_page` | *(none today — write it)* |

If any mutant **survives**, write the test that kills it before continuing — a survivor here is either a cross-tenant read or a double-billed evaluation.

- [ ] **Step 6: Full suite**

Run: `python -m pytest -q`
Expected: no failures.

- [ ] **Step 7: Commit**

```bash
git add app/screening/store.py tests/test_screening_store.py
git commit -m "feat(s84b): org-scoped batch store with a conditional-UPDATE claim"
```

---

## Task 8: `app/screening/service.py` — `ScreeningService`, and wire it into `Services`

**Files:**
- Create: `app/screening/service.py`
- Modify: `app/services/__init__.py` (add `screening` to `Services` + `build_default_services`)
- Modify: `tests/conftest.py` (`make_services` gains a `screening=None` parameter)
- Test: `tests/test_screening_service.py`

**Interfaces:**
- Consumes: `ScreeningStore` (Task 7), `IngestDeps`/`ingest_resume`/`IngestRefused` (Task 6), the schema types (Task 2), `clamp_limit` (Task 5).
- Produces `ScreeningService`, every method `org_id` first:
  - `register(org_id, *, name, domain, texts, created_by_org_user_id) -> BatchDetail` (raises `ValueError` on an empty or over-large batch)
  - `get(org_id, batch_id) -> Optional[BatchDetail]`
  - `list(org_id, *, cursor, limit) -> BatchPage`
  - `async process(org_id, batch_id, *, engine) -> Optional[ProcessResult]`
  - `queue(org_id, batch_id, *, cursor, limit) -> Optional[QueuePage]`
  - `summary(org_id, batch_id) -> Optional[BatchSummary]`
  - `delete(org_id, batch_id) -> bool`
  - `build_screening_service(settings, *, deps: IngestDeps) -> ScreeningService`
- `Services.screening: ScreeningService`.

**Context you need:**

`process` is the only method that runs the pipeline. It claims up to `screening_max_items_per_call` items and, **for each one independently**, calls `ingest_resume` and writes the outcome. One item's failure must not abandon the rest of the claim — a batch of 500 with one corrupt PDF has to finish.

`IngestRefused` → `fail(reason)`. An **unexpected** exception also fails the item, with `error="internal_error"`, because the alternative is an item stuck in `processing` until the claim times out for a reason no one recorded. Log the real exception; never put it on the row (`batch_items.error` is a closed vocabulary, and an exception string can quote input).

`signals_from_report` needs a report. With `evaluate=True` there always is one unless the subject was erased mid-flight — that case yields `risk_score=None` and no signals, and the item is still `done` (the ingest succeeded; there is simply nothing to score).

`Services` gets `screening` and **not** the store: no handler should be able to reach an unscoped batch read, so `ScreeningStore` is built inside the service and is not an attribute of the container.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_service.py`:

```python
"""S8.4 Phase B: the screening service -- registration, bounded processing,
and the read-models."""

from __future__ import annotations

import pytest

from app.graph.build import EvaluationEngine
from app.screening.schema import BatchStatus, ItemStatus


def _org(services, name="Acme Staffing"):
    return services.ledger.create_organization(name).id


def test_registration_is_evaluation_free(services, genuine_resume):
    """The whole point of registering: 500 resumes cannot be evaluated inside
    one request, so upload only inserts rows."""
    org = _org(services)
    batch = services.screening.register(
        org, name="Q3", domain="genai", texts=[genuine_resume, genuine_resume],
        created_by_org_user_id=None,
    )
    assert batch.counts.pending == 2
    assert batch.status is BatchStatus.PENDING
    assert services.candidates.get_candidate("anything") is None
    assert services.report_store.for_candidate("anything") == []


def test_an_empty_batch_is_refused(services):
    org = _org(services)
    with pytest.raises(ValueError):
        services.screening.register(org, name="x", domain="genai", texts=[],
                                    created_by_org_user_id=None)


def test_an_oversize_batch_is_refused(services, genuine_resume):
    org = _org(services)
    cap = services.settings.screening_max_batch_items
    with pytest.raises(ValueError):
        services.screening.register(org, name="x", domain="genai",
                                    texts=["t"] * (cap + 1),
                                    created_by_org_user_id=None)


@pytest.mark.asyncio
async def test_process_is_bounded_and_resumable(services, genuine_resume):
    org = _org(services)
    batch = services.screening.register(
        org, name="Q3", domain="genai",
        texts=[f"{genuine_resume}\nRef {i}" for i in range(3)],
        created_by_org_user_id=None,
    )
    engine = EvaluationEngine(services)

    first = await services.screening.process(org, batch.id, engine=engine)
    assert first.processed <= services.settings.screening_max_items_per_call
    assert first.remaining == 3 - first.processed

    while (await services.screening.process(org, batch.id, engine=engine)).remaining:
        pass

    done = services.screening.get(org, batch.id)
    assert done.counts.done == 3
    assert done.status is BatchStatus.COMPLETE


@pytest.mark.asyncio
async def test_processing_a_finished_batch_is_a_no_op(services, genuine_resume):
    org = _org(services)
    batch = services.screening.register(org, name="x", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    await services.screening.process(org, batch.id, engine=engine)
    again = await services.screening.process(org, batch.id, engine=engine)
    assert (again.processed, again.failed, again.remaining) == (0, 0, 0)


@pytest.mark.asyncio
async def test_a_bad_item_fails_alone_and_the_batch_continues(services, genuine_resume):
    """A batch of 500 with one corrupt file has to finish."""
    org = _org(services)
    batch = services.screening.register(
        org, name="x", domain="genai", texts=["   ", genuine_resume],
        created_by_org_user_id=None,
    )
    engine = EvaluationEngine(services)
    while (await services.screening.process(org, batch.id, engine=engine)).remaining:
        pass

    detail = services.screening.get(org, batch.id)
    assert (detail.counts.done, detail.counts.failed) == (1, 1)
    assert detail.status is BatchStatus.PARTIAL

    rows = services.screening.queue(org, batch.id, cursor=None, limit=10).rows
    failed = [r for r in rows if r.status is ItemStatus.FAILED][0]
    assert failed.error == "empty_resume"
    assert "empty_resume" in failed.reason


@pytest.mark.asyncio
async def test_the_queue_row_carries_the_signals_and_a_composed_reason(
    services, genuine_resume
):
    org = _org(services)
    batch = services.screening.register(org, name="x", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    await services.screening.process(org, batch.id, engine=engine)

    row = services.screening.queue(org, batch.id, cursor=None, limit=10).rows[0]
    assert row.status is ItemStatus.DONE
    assert row.candidate_id and row.report_id
    assert row.signals is not None
    assert row.reason, "the one-line reason is composed, never stored"
    assert row.advisory is True and row.human_review_required is True


@pytest.mark.asyncio
async def test_a_queue_row_can_never_carry_resume_farm_match_identities(
    services, farm_resume_a, farm_resume_b
):
    """Design §1.1: no Report is on this path, so there is nothing to redact --
    asserted on a batch whose report genuinely HAS farm matches."""
    other = _org(services, "Other Agency")
    mine = _org(services, "Acme Staffing")
    engine = EvaluationEngine(services)

    # Seed another customer's near-duplicate so the farm check has something to
    # find, then screen ours.
    seeded = services.screening.register(other, name="theirs", domain="genai",
                                         texts=[farm_resume_a],
                                         created_by_org_user_id=None)
    await services.screening.process(other, seeded.id, engine=engine)

    ours = services.screening.register(mine, name="mine", domain="genai",
                                       texts=[farm_resume_b],
                                       created_by_org_user_id=None)
    await services.screening.process(mine, ours.id, engine=engine)

    row = services.screening.queue(mine, ours.id, cursor=None, limit=10).rows[0]
    dumped = row.model_dump_json()
    assert "matches" not in dumped
    assert row.signals.farm_corpus_size >= 0, "a COUNT survives; identities never existed here"


@pytest.mark.asyncio
async def test_summary_is_counts_only(services, genuine_resume):
    org = _org(services)
    batch = services.screening.register(org, name="Q3", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    engine = EvaluationEngine(services)
    await services.screening.process(org, batch.id, engine=engine)

    summary = services.screening.summary(org, batch.id)
    assert summary.n_screened == 1
    assert sum(summary.by_risk_band.values()) == 1
    dumped = summary.model_dump_json()
    for leaked in ("candidate_id", "resume_id", "report_id", "reasoning"):
        assert leaked not in dumped, f"a roll-up must not carry {leaked}"


def test_every_read_is_none_for_another_org(services, genuine_resume):
    a, b = _org(services, "A"), _org(services, "B")
    batch = services.screening.register(a, name="x", domain="genai",
                                        texts=[genuine_resume],
                                        created_by_org_user_id=None)
    assert services.screening.get(b, batch.id) is None
    assert services.screening.queue(b, batch.id, cursor=None, limit=10) is None
    assert services.screening.summary(b, batch.id) is None
    assert services.screening.delete(b, batch.id) is False
    assert services.screening.list(b, cursor=None, limit=10).batches == []
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_screening_service.py -q`
Expected: FAIL — `AttributeError: 'Services' object has no attribute 'screening'`.

- [ ] **Step 3: Write the service**

Create `app/screening/service.py`:

```python
"""Screening batches: the service (S8.4 Phase B).

Composition over the store and the ingest core. Owns no tables directly -- the
store does -- and holds no state, in the ``app/dashboard/`` style.

EVERY method takes ``org_id`` first, and the store it calls does too, so
tenancy is a property of the type signatures rather than of anybody's memory.
The store is deliberately NOT an attribute of ``Services``: if no handler can
reach an unscoped batch read, no handler can forget to scope one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.screening.ingest import IngestDeps, IngestRefused, ingest_resume
from app.screening.pagination import clamp_limit
from app.screening.schema import (
    BatchDetail, BatchPage, BatchSummary, BatchView, ProcessResult, QueuePage,
    QueueRow, SignalCount, compose_reason, derive_status, signals_from_report,
)
from app.screening.store import (
    BatchRecord, ItemRecord, ScreeningStore, build_screening_store,
)

if TYPE_CHECKING:
    from app.graph.build import EvaluationEngine

log = get_logger("screening.service")


class ScreeningService:
    def __init__(
        self, store: ScreeningStore, deps: IngestDeps, *, settings: Settings
    ) -> None:
        self._store = store
        self._deps = deps
        self._settings = settings

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # ── registration ────────────────────────────────────────────────────────

    def register(
        self,
        org_id: str,
        *,
        name: str,
        domain: str,
        texts: list[str],
        created_by_org_user_id: Optional[str],
    ) -> BatchDetail:
        """Register items. NO evaluation -- see spec §0.3: there is no worker
        anywhere in app/, and 500 nine-node graph runs cannot happen inside one
        request."""
        if not texts:
            raise ValueError("a batch needs at least one item")
        cap = self._settings.screening_max_batch_items
        if len(texts) > cap:
            raise ValueError(f"a batch holds at most {cap} items")

        batch_id = self._store.create_batch(
            org_id, name=name, domain=domain,
            created_by_org_user_id=created_by_org_user_id, texts=texts,
        )
        detail = self.get(org_id, batch_id)
        assert detail is not None  # just created, by this org
        return detail

    # ── reads ───────────────────────────────────────────────────────────────

    def get(self, org_id: str, batch_id: str) -> Optional[BatchDetail]:
        now = self._now()
        record = self._store.batch_row(org_id, batch_id)
        if record is None:
            return None
        counts = self._store.counts(org_id, batch_id, now=now)
        return BatchDetail(
            **self._batch_fields(record),
            counts=counts,
            status=derive_status(counts),
        )

    def list(
        self, org_id: str, *, cursor: Optional[str], limit: Optional[int]
    ) -> BatchPage:
        now = self._now()
        records, next_cursor = self._store.list_batches(
            org_id, cursor=cursor, limit=clamp_limit(limit, self._settings)
        )
        views = []
        for record in records:
            counts = self._store.counts(org_id, record.id, now=now)
            views.append(BatchView(
                **self._batch_fields(record),
                counts=counts, status=derive_status(counts),
            ))
        return BatchPage(batches=views, next_cursor=next_cursor)

    def queue(
        self, org_id: str, batch_id: str, *, cursor: Optional[str], limit: Optional[int]
    ) -> Optional[QueuePage]:
        page = self._store.queue_page(
            org_id, batch_id, cursor=cursor,
            limit=clamp_limit(limit, self._settings), now=self._now(),
        )
        if page is None:
            return None
        rows, next_cursor = page
        return QueuePage(rows=[self._row(i) for i in rows], next_cursor=next_cursor)

    def summary(self, org_id: str, batch_id: str) -> Optional[BatchSummary]:
        now = self._now()
        record = self._store.batch_row(org_id, batch_id)
        if record is None:
            return None
        items = self._store.all_items(org_id, batch_id, now=now) or []

        counts = self._store.counts(org_id, batch_id, now=now)
        by_band: dict[str, int] = {}
        signals: dict[str, int] = {}
        for item in items:
            if item.signals is None:
                continue
            band = item.signals.risk_band.value
            by_band[band] = by_band.get(band, 0) + 1
            if item.signals.loudest_signal:
                key = item.signals.loudest_signal
                signals[key] = signals.get(key, 0) + 1

        return BatchSummary(
            batch_id=record.id, name=record.name, domain=record.domain,
            status=derive_status(counts), counts=counts,
            n_screened=sum(by_band.values()),
            by_risk_band=by_band,
            top_signals=[
                SignalCount(signal=k, count=v)
                for k, v in sorted(signals.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        )

    def delete(self, org_id: str, batch_id: str) -> bool:
        return self._store.delete_batch(org_id, batch_id)

    # ── processing ──────────────────────────────────────────────────────────

    async def process(
        self, org_id: str, batch_id: str, *, engine: "EvaluationEngine"
    ) -> Optional[ProcessResult]:
        """Claim and run up to ``screening_max_items_per_call`` items.

        Each item is handled independently: one corrupt file must not abandon
        the other 499. An unexpected exception fails ITS item with a generic
        code rather than propagating, because the alternative is a row stuck in
        `processing` until the claim times out for a reason nobody recorded.
        """
        if self._store.batch_row(org_id, batch_id) is None:
            return None

        now = self._now()
        claimed = self._store.claim(
            org_id, batch_id,
            limit=self._settings.screening_max_items_per_call,
            now=now,
            timeout_seconds=self._settings.screening_claim_timeout_seconds,
        )

        processed = failed = 0
        for item in claimed:
            try:
                result = await ingest_resume(
                    self._deps, engine,
                    text=item.raw_text, domain=item.domain,
                    evaluate=True, org_id=org_id,
                )
            except IngestRefused as exc:
                self._store.fail(item.id, error=exc.reason, at=self._now())
                failed += 1
                continue
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see below
                # The exception's TEXT never goes on the row: batch_items.error
                # is a closed vocabulary, and an exception message can quote the
                # input that caused it.
                log.error("batch_item_failed", item_id=item.id, error=repr(exc))
                self._store.fail(item.id, error="internal_error", at=self._now())
                failed += 1
                continue

            report = result.report
            self._store.complete(
                item.id,
                candidate_id=result.candidate_id,
                resume_id=result.resume_id,
                report_id=report.id if report is not None else None,
                risk_score=(
                    report.fabrication_risk.score
                    if report is not None and report.fabrication_risk is not None
                    else None
                ),
                signals=signals_from_report(
                    report,
                    matched_existing=result.matched_existing,
                    matched_on=result.matched_on,
                    duplicate_resume=result.duplicate_resume,
                ) if report is not None else _no_report_signals(result),
                at=self._now(),
            )
            processed += 1

        counts = self._store.counts(org_id, batch_id, now=self._now())
        return ProcessResult(
            batch_id=batch_id, processed=processed, failed=failed,
            remaining=counts.pending + counts.processing,
            status=derive_status(counts),
        )

    # ── mapping ─────────────────────────────────────────────────────────────

    @staticmethod
    def _batch_fields(record: BatchRecord) -> dict:
        return {
            "id": record.id, "name": record.name, "domain": record.domain,
            "created_at": record.created_at,
            "created_by_org_user_id": record.created_by_org_user_id,
        }

    @staticmethod
    def _row(item: ItemRecord) -> QueueRow:
        return QueueRow(
            item_id=item.item_id, status=item.status,
            created_at=item.created_at, processed_at=item.processed_at,
            candidate_id=item.candidate_id, resume_id=item.resume_id,
            report_id=item.report_id, risk_score=item.risk_score,
            signals=item.signals, error=item.error,
            reason=compose_reason(item.signals, item.status, item.error),
        )


def _no_report_signals(result):
    """The subject was erased mid-evaluation, so there is nothing to score.

    The ingest itself succeeded, so the item is DONE with the ingest facts and
    no risk assessment -- which reads as "insufficient signal", the honest
    answer, rather than a zero.
    """
    from app.screening.schema import ItemSignals

    return ItemSignals(
        matched_existing=result.matched_existing,
        matched_on=result.matched_on,
        duplicate_resume=result.duplicate_resume,
    )


def build_screening_service(
    settings: Optional[Settings] = None, *, deps: IngestDeps
) -> ScreeningService:
    settings = settings or get_settings()
    return ScreeningService(build_screening_store(settings), deps, settings=settings)
```

- [ ] **Step 4: Wire it into `Services`**

In `app/services/__init__.py`:

1. Import beside the existing screening import:
   ```python
   from app.screening.ingest import ingest_deps
   from app.screening.service import ScreeningService, build_screening_service
   ```
2. Add the field to the `Services` dataclass, after `screening_scope`:
   ```python
       screening: ScreeningService
   ```
3. In `build_default_services`, after the `Services(...)` fields are ready, build it from the finished container. Because `ingest_deps` needs the container, construct `Services` first into a local and then attach — or simpler and preferred, build the deps inline from the same objects already in scope:
   ```python
       from app.screening.ingest import IngestDeps

       screening = build_screening_service(
           settings,
           deps=IngestDeps(
               candidates=candidates, reports=report_store, llm=llm, settings=settings
           ),
       )
   ```
   and pass `screening=screening` in the `Services(...)` call.

> **Note the store is NOT added to `Services`.** That is deliberate: no handler should be able to reach an unscoped batch read.

- [ ] **Step 5: Wire it into the test container**

In `tests/conftest.py`, `make_services`: add a `screening=None` keyword parameter, and before the `Services(...)` construction:

```python
    if screening is None:
        from app.screening.ingest import IngestDeps
        from app.screening.service import ScreeningService
        from app.screening.store import ScreeningStore

        screening = ScreeningService(
            ScreeningStore(
                candidates._session_factory,
                claim_timeout_seconds=settings.screening_claim_timeout_seconds,
            ),
            IngestDeps(candidates=candidates, reports=report_store,
                       llm=llm, settings=settings),
            settings=settings,
        )
```

then pass `screening=screening` in the `Services(...)` call. Check the local names in that function first — `report_store` and `llm` must already be bound at that point; if not, move the block below where they are.

- [ ] **Step 6: Run the service tests**

Run: `python -m pytest tests/test_screening_service.py -q`
Expected: PASS (10 tests).

- [ ] **Step 7: Full suite**

Run: `python -m pytest -q`
Expected: no failures.

- [ ] **Step 8: Commit**

```bash
git add app/screening/service.py app/services/__init__.py tests/conftest.py tests/test_screening_service.py
git commit -m "feat(s84b): ScreeningService — register, bounded process, queue, summary"
```

---

## Task 9: The seven org-plane routes

**Files:**
- Modify: `app/api/routes.py` (after the Phase A screening block, ~line 784)
- Modify: `tests/test_org_scope_guard.py` (`screening` joins the sanctioned doors)
- Test: `tests/test_screening_batches_api.py`, `tests/test_screening_tenancy.py`

**Interfaces:**
- Consumes: `ScreeningService` via `_services(request).screening`, `require_org`.
- Produces:

| Method | Path | Response model | Notes |
|---|---|---|---|
| POST | `/screening/batches` | `BatchDetail` | body `{name, domain, items:[{resume_text|resume_pdf_b64}]}`; PDFs decoded here |
| GET | `/screening/batches` | `BatchPage` | `cursor`, `limit` |
| GET | `/screening/batches/{batch_id}` | `BatchDetail` | 404 if not yours |
| POST | `/screening/batches/{batch_id}/process` | `ProcessResult` | bounded |
| GET | `/screening/batches/{batch_id}/queue` | `QueuePage` | `cursor`, `limit` |
| GET | `/screening/batches/{batch_id}/summary` | `BatchSummary` | |
| DELETE | `/screening/batches/{batch_id}` | `dict` | `{batch_id, deleted: true}` |

**Context you need:**

- **PDF decoding happens at registration**, not at processing: it is cheap, deterministic and LLM-free, so a corrupt file fails immediately rather than 400 items later. A decode failure refuses the **whole** registration with a 422 naming the item index — a half-registered batch would leave the org unable to tell which files made it in.
- **`created_by_org_user_id` comes from `request.state.principal.org_user_id`**, which is `None` for an `X-Org-Key` machine caller. Do not invent one; a machine credential has no human behind it, and a fabricated actor is a false audit trail.
- **`InvalidCursor` → 422**, never a 500.
- Every route is on `org_router` with `Depends(require_org)` or `tests/test_route_table_guard.py` fails the build.

- [ ] **Step 1: Write the failing tests — the tenancy file first**

Create `tests/test_screening_tenancy.py`:

```python
"""S8.4 Phase B: another organisation's batch does not exist.

Every route, not a sample: the Phase A leak got in through the ONE org-facing
surface nobody enumerated, so this file enumerates them.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def test_every_batch_route_is_404_for_another_org_and_matches_absence(
    services, genuine_resume
):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        bid = _register(c, key_a, [genuine_resume]).json()["id"]
        b = {"X-Org-Key": key_b}

        cases = [
            ("get", f"/screening/batches/{bid}", "/screening/batches/nope"),
            ("get", f"/screening/batches/{bid}/queue", "/screening/batches/nope/queue"),
            ("get", f"/screening/batches/{bid}/summary", "/screening/batches/nope/summary"),
            ("post", f"/screening/batches/{bid}/process", "/screening/batches/nope/process"),
            ("delete", f"/screening/batches/{bid}", "/screening/batches/nope"),
        ]
        for method, theirs, absent in cases:
            got = getattr(c, method)(theirs, headers=b)
            missing = getattr(c, method)(absent, headers=b)
            assert got.status_code == 404, f"{method} {theirs} -> {got.status_code}"
            assert got.json() == missing.json(), (
                f"{method} {theirs}: a different body from a genuinely absent "
                f"batch confirms this one exists"
            )


def test_listing_shows_only_my_own_batches(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        _register(c, key_a, [genuine_resume], name="A's batch")
        mine = c.get("/screening/batches", headers={"X-Org-Key": key_b}).json()
        assert mine["batches"] == []


def test_a_cursor_from_another_org_reaches_nothing(services, genuine_resume):
    """A cursor is a sort position, not a capability -- the org filter is what
    protects the boundary, so a stolen cursor buys nothing."""
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        # TWO batches, so a limit=1 page actually has a next_cursor to steal.
        _register(c, key_a, [genuine_resume], name="first")
        _register(c, key_a, [genuine_resume + "\nRef 2"], name="second")
        page = c.get("/screening/batches?limit=1", headers={"X-Org-Key": key_a}).json()
        stolen = page["next_cursor"]
        assert stolen, "two batches and limit=1 must produce a cursor"

        theirs = c.get(f"/screening/batches?cursor={stolen}",
                       headers={"X-Org-Key": key_b})
        assert theirs.status_code == 200
        assert theirs.json()["batches"] == []


def test_all_batch_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/batches").status_code == 401
        assert c.post("/screening/batches", json={}).status_code == 401
        assert c.get("/screening/batches/x/queue").status_code == 401
        assert c.post("/screening/batches/x/process").status_code == 401
        assert c.delete("/screening/batches/x").status_code == 401
```

- [ ] **Step 2: Write the behaviour tests**

Create `tests/test_screening_batches_api.py`:

```python
"""S8.4 Phase B: the screening surface over HTTP."""

from __future__ import annotations

import base64
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def test_register_then_process_then_read_the_queue(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        created = _register(c, key, [genuine_resume])
        assert created.status_code == 200, created.text
        bid = created.json()["id"]
        assert created.json()["counts"]["pending"] == 1
        assert created.json()["status"] == "pending"

        ran = c.post(f"/screening/batches/{bid}/process", headers={"X-Org-Key": key})
        assert ran.status_code == 200
        assert ran.json()["processed"] == 1 and ran.json()["remaining"] == 0

        queue = c.get(f"/screening/batches/{bid}/queue", headers={"X-Org-Key": key})
        row = queue.json()["rows"][0]
        assert row["status"] == "done" and row["reason"]
        assert row["advisory"] is True

        summary = c.get(f"/screening/batches/{bid}/summary", headers={"X-Org-Key": key})
        assert summary.status_code == 200 and summary.json()["n_screened"] == 1


def test_an_empty_batch_is_422(services):
    _, key = _key(services)
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key},
                   json={"name": "x", "domain": "genai", "items": []})
        assert r.status_code == 422


def test_an_oversize_batch_is_422(services):
    _, key = _key(services)
    cap = services.settings.screening_max_batch_items
    with _client(services) as c:
        r = _register(c, key, ["resume"] * (cap + 1))
        assert r.status_code == 422


def test_a_corrupt_pdf_refuses_the_whole_registration_and_names_the_item(services):
    """A half-registered batch would leave the org unable to say which files
    made it in."""
    _, key = _key(services)
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key}, json={
            "name": "x", "domain": "genai",
            "items": [
                {"resume_text": "a real resume"},
                {"resume_pdf_b64": base64.b64encode(b"not a pdf").decode()},
            ],
        })
        assert r.status_code == 422
        assert "1" in str(r.json()["detail"]), "the failing item's index is named"
        assert c.get("/screening/batches", headers={"X-Org-Key": key}).json()["batches"] == []


def test_a_malformed_cursor_is_422_not_500(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        for path in ("/screening/batches?cursor=!!!",
                     f"/screening/batches/{bid}/queue?cursor=!!!"):
            r = c.get(path, headers={"X-Org-Key": key})
            assert r.status_code == 422, f"{path} -> {r.status_code}"


def test_the_queue_pages_with_a_cursor(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        texts = [f"{genuine_resume}\nRef {i}" for i in range(3)]
        bid = _register(c, key, texts).json()["id"]
        while c.post(f"/screening/batches/{bid}/process",
                     headers={"X-Org-Key": key}).json()["remaining"]:
            pass

        first = c.get(f"/screening/batches/{bid}/queue?limit=2",
                      headers={"X-Org-Key": key}).json()
        assert len(first["rows"]) == 2 and first["next_cursor"]
        second = c.get(
            f"/screening/batches/{bid}/queue?cursor={first['next_cursor']}",
            headers={"X-Org-Key": key},
        ).json()
        ids = [r["item_id"] for r in first["rows"] + second["rows"]]
        assert len(ids) == len(set(ids)) == 3


def test_delete_removes_the_batch(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        gone = c.delete(f"/screening/batches/{bid}", headers={"X-Org-Key": key})
        assert gone.status_code == 200 and gone.json()["deleted"] is True
        assert c.get(f"/screening/batches/{bid}",
                     headers={"X-Org-Key": key}).status_code == 404


def test_a_machine_caller_records_no_human_creator(services, genuine_resume):
    """X-Org-Key is an ORGANISATION credential. Inventing an actor would be a
    false audit trail."""
    _, key = _key(services)
    with _client(services) as c:
        created = _register(c, key, [genuine_resume])
        assert created.json()["created_by_org_user_id"] is None
```

- [ ] **Step 3: Run both and watch them fail**

Run: `python -m pytest tests/test_screening_tenancy.py tests/test_screening_batches_api.py -q`
Expected: FAIL — 404s from the router (no such route).

- [ ] **Step 4: Add the routes**

In `app/api/routes.py`, after the Phase A screening block:

```python
# ── Screening batches (S8.4 Phase B) ─────────────────────────────────────────
# The wedge at volume: register what you have, process it in bounded calls,
# read a ranked queue. Registration is a row insert; PROCESSING is the slow
# part and the client drives it, because there is no worker anywhere in app/
# (spec §0.3) and 500 nine-node graph runs cannot happen inside one request.


class BatchItemInput(BaseModel):
    """Exactly one of resume_text / resume_pdf_b64 is required."""

    resume_text: str | None = None
    resume_pdf_b64: str | None = None

    @model_validator(mode="after")
    def _need_one_source(self) -> "BatchItemInput":
        if not (self.resume_text or self.resume_pdf_b64):
            raise ValueError("Provide resume_text or resume_pdf_b64.")
        return self


class BatchCreateRequest(BaseModel):
    name: str = ""
    domain: str = "genai"
    items: list[BatchItemInput] = Field(default_factory=list)


class BatchDeleteResponse(BaseModel):
    batch_id: str
    deleted: bool


def _batch_texts(req: BatchCreateRequest, caps) -> list[str]:
    """Decode every item to text AT REGISTRATION -- cheap, deterministic, no LLM.

    A corrupt file therefore fails immediately rather than 400 items later, and
    it fails the WHOLE registration: a half-registered batch would leave the org
    unable to tell which files made it in.
    """
    texts: list[str] = []
    for i, item in enumerate(req.items):
        if item.resume_text and len(item.resume_text) > caps.max_resume_chars:
            raise HTTPException(
                status_code=422,
                detail=f"item {i}: resume_text exceeds max_resume_chars={caps.max_resume_chars}",
            )
        if item.resume_pdf_b64 and len(item.resume_pdf_b64) > caps.max_pdf_b64_chars:
            raise HTTPException(
                status_code=422,
                detail=f"item {i}: resume_pdf_b64 exceeds max_pdf_b64_chars={caps.max_pdf_b64_chars}",
            )
        text = item.resume_text
        if not text and item.resume_pdf_b64:
            try:
                text = pdf_b64_to_text(item.resume_pdf_b64)
            except Exception as exc:
                raise HTTPException(
                    status_code=422, detail=f"item {i}: pdf_parse_failed: {exc}"
                ) from exc
        texts.append(text or "")
    return texts


def _org_user_id(request: Request) -> Optional[str]:
    """The human behind the call, or None for a machine credential."""
    principal = getattr(request.state, "principal", None)
    return getattr(principal, "org_user_id", None)


@org_router.post("/screening/batches", response_model=BatchDetail)
async def create_screening_batch(
    req: BatchCreateRequest, request: Request, org_id: str = Depends(require_org)
) -> BatchDetail:
    services = _services(request)
    texts = _batch_texts(req, services.settings)
    try:
        return services.screening.register(
            org_id, name=req.name, domain=req.domain, texts=texts,
            created_by_org_user_id=_org_user_id(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@org_router.get("/screening/batches", response_model=BatchPage)
async def list_screening_batches(
    request: Request,
    org_id: str = Depends(require_org),
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> BatchPage:
    try:
        return _services(request).screening.list(org_id, cursor=cursor, limit=limit)
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@org_router.get("/screening/batches/{batch_id}", response_model=BatchDetail)
async def get_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> BatchDetail:
    """404 -- never 403 -- for another org's batch."""
    found = _services(request).screening.get(org_id, batch_id)
    if found is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return found


@org_router.post("/screening/batches/{batch_id}/process", response_model=ProcessResult)
async def process_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> ProcessResult:
    """Bounded by `screening_max_items_per_call`. Call it until `remaining` is 0.

    An item whose claim goes stale becomes claimable again, so a batch
    interrupted by a redeploy heals on the next call rather than wedging.
    """
    result = await _services(request).screening.process(
        org_id, batch_id, engine=request.app.state.engine
    )
    if result is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return result


@org_router.get("/screening/batches/{batch_id}/queue", response_model=QueuePage)
async def screening_batch_queue(
    batch_id: str,
    request: Request,
    org_id: str = Depends(require_org),
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> QueuePage:
    """The fraud-screen read-model: riskiest first, unscreened rows last."""
    try:
        page = _services(request).screening.queue(
            org_id, batch_id, cursor=cursor, limit=limit
        )
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if page is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return page


@org_router.get("/screening/batches/{batch_id}/summary", response_model=BatchSummary)
async def screening_batch_summary(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> BatchSummary:
    found = _services(request).screening.summary(org_id, batch_id)
    if found is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return found


@org_router.delete("/screening/batches/{batch_id}", response_model=BatchDeleteResponse)
async def delete_screening_batch(
    batch_id: str, request: Request, org_id: str = Depends(require_org)
) -> BatchDeleteResponse:
    """A real delete path on a new table, shipped in the sprint that creates it
    -- `batch_items.raw_text` is personal data with no candidate to cascade
    from (spec §4.2)."""
    if not _services(request).screening.delete(org_id, batch_id):
        raise HTTPException(status_code=404, detail="batch not found")
    return BatchDeleteResponse(batch_id=batch_id, deleted=True)
```

Add the imports at the top of `routes.py`:

```python
from app.screening.pagination import InvalidCursor
from app.screening.schema import (
    BatchDetail, BatchPage, BatchSummary, ProcessResult, QueuePage,
)
```

- [ ] **Step 5: Add `screening` to the guard's sanctioned doors**

In `tests/test_org_scope_guard.py`, replace the single `SCOPED_ATTR` with a tuple and update `_sanctioned_re` to build an alternation over both names:

```python
#: The sanctioned doors. Both take org_id as the first argument of every method
#: and neither exposes an unscoped read: `screening_scope` (Phase A, reports and
#: candidates) and `screening` (Phase B, batches). The batch STORE is
#: deliberately not on `Services` at all, so there is nothing unscoped for a
#: handler to reach in the first place.
SCOPED_ATTRS = ("screening_scope", "screening")
```

Update every use of `SCOPED_ATTR` accordingly, and add:

```python
def test_the_batch_store_is_not_reachable_from_the_services_container():
    """Structural, not stylistic: a handler cannot forget to scope a read it
    has no way to perform."""
    from app.services import Services

    assert "screening_store" not in Services.__dataclass_fields__
    assert not hasattr(Services, "batches")
```

- [ ] **Step 6: Re-prove the guard is non-vacuous**

The guard must still fail when an org handler reaches an unscoped read. Temporarily add to `routes.py`:

```python
@org_router.get("/screening/_guard_probe")
async def _guard_probe(request: Request, org_id: str = Depends(require_org)):
    return _services(request).report_store.get("anything")
```

Run: `python -m pytest tests/test_org_scope_guard.py -q`
Expected: **FAIL**, naming `report_store.get`. Then delete the probe route and re-run — expected PASS. Record both outcomes in the commit message.

- [ ] **Step 7: Run the route tests and the route-table guard**

Run: `python -m pytest tests/test_screening_tenancy.py tests/test_screening_batches_api.py tests/test_route_table_guard.py tests/test_org_scope_guard.py tests/test_api_auth_gate.py -q`
Expected: PASS.

- [ ] **Step 8: Full suite**

Run: `python -m pytest -q`
Expected: no failures.

- [ ] **Step 9: Commit**

```bash
git add app/api/routes.py tests/test_screening_tenancy.py tests/test_screening_batches_api.py tests/test_org_scope_guard.py
git commit -m "feat(s84b): seven org-plane screening batch routes; guard proven non-vacuous"
```

---

## Task 10: Cursor pagination on `GET /curation/skills/unmapped`

**Files:**
- Modify: `app/curation/store.py:75-85` (`list_terms`)
- Modify: `app/curation/service.py:42-47` (`list_unmapped`)
- Modify: `app/api/routes.py:607-613`
- Test: `tests/test_curation_api.py` (add to the existing file)

**Interfaces:**
- Consumes: the cursor codec (Task 5).
- Produces: `CurationStore.list_terms(status, limit, *, cursor=None) -> tuple[list[UnmappedTerm], Optional[str]]`, `CurationService.list_unmapped(status, limit, *, cursor=None) -> UnmappedPage`, and a `UnmappedPage{terms, next_cursor}` model in `app/curation/schema.py`.

**Context you need — and one honest limitation to write down.**

The existing order is `occurrences DESC, last_seen DESC` (`app/curation/store.py:82-84`), which *is* a stored order, so a keyset cursor over `(occurrences, last_seen, norm_key)` works — `norm_key` is the stable unique identity and breaks ties.

**But the sort key is mutable**: a term seen again gains occurrences and moves. So paging here is stable against *inserts* and not against *re-observation*, and that goes in the docstring rather than being discovered. It is still strictly better than the `limit`-only status quo, and this queue is an internal operator tool (`UI.md` §4.F), not a customer surface.

**`limit` must keep working exactly as it does today** — this endpoint has callers.

> **The response shape changes** from a bare `list[UnmappedTerm]` to `UnmappedPage`. Check `scripts/smoke_s63.py` and `tests/test_curation_api.py` for callers that index the response directly, and update the smoke — it is ours. This is the only breaking shape change in Phase B beyond comp's (Task 12), and both are on endpoints the wired UI does not call (`frontend/api.js` wires auth, portal, devices, roles and comp only).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_curation_api.py`:

```python
def test_unmapped_terms_page_with_a_cursor(services, admin_headers):
    """S8.4 Phase B: the curation queue pages. `limit` keeps working -- this
    endpoint has callers."""
    from app.main import create_app
    from fastapi.testclient import TestClient

    for i in range(3):
        services.curation.record_unmapped(f"Term {i}", source_type="github")

    with TestClient(create_app(services), headers=admin_headers) as c:
        first = c.get("/curation/skills/unmapped?limit=2")
        assert first.status_code == 200
        body = first.json()
        assert len(body["terms"]) == 2 and body["next_cursor"]

        second = c.get(f"/curation/skills/unmapped?cursor={body['next_cursor']}")
        keys = [t["norm_key"] for t in body["terms"] + second.json()["terms"]]
        assert len(keys) == len(set(keys)) == 3


def test_a_malformed_curation_cursor_is_422(services, admin_headers):
    from app.main import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app(services), headers=admin_headers,
                    raise_server_exceptions=False) as c:
        assert c.get("/curation/skills/unmapped?cursor=!!!").status_code == 422
```

> `record_unmapped(name, *, source_type)` is the real seeding API (`app/curation/service.py:31`) — verified, not guessed. Three distinct names produce three terms at `occurrences=1`; if the store dedupes them differently than expected, read `CurationStore.record` before adjusting the test.

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_curation_api.py -q`
Expected: FAIL — the response is a list, so `body["terms"]` raises.

- [ ] **Step 3: Add the page model**

In `app/curation/schema.py`:

```python
class UnmappedPage(BaseModel):
    """S8.4 Phase B: a page of the review queue.

    NOTE the sort key (occurrences, last_seen) is MUTABLE -- a term seen again
    moves. Paging is therefore stable against inserts and not against
    re-observation. Acceptable here and stated rather than hidden: this is an
    internal operator queue (UI.md §4.F), not a customer surface.
    """

    terms: list[UnmappedTerm] = Field(default_factory=list)
    next_cursor: Optional[str] = None
```

- [ ] **Step 4: Page the store**

Replace `CurationStore.list_terms`:

```python
    def list_terms(
        self,
        status: Optional[CurationStatus] = None,
        limit: int = 200,
        *,
        cursor: Optional[str] = None,
    ) -> tuple[list[UnmappedTerm], Optional[str]]:
        """Keyset-paged over (occurrences, last_seen, norm_key) -- the existing
        order, plus norm_key to break ties into a total order."""
        from app.screening.pagination import decode_cursor, encode_cursor

        with self._session_factory() as session:
            q = select(UnmappedTermRow)
            if status is not None:
                q = q.where(UnmappedTermRow.status == status.value)
            if cursor is not None:
                occ, seen, key = decode_cursor(cursor, arity=3)
                cut = datetime.fromisoformat(seen)
                q = q.where(
                    or_(
                        UnmappedTermRow.occurrences < occ,
                        and_(
                            UnmappedTermRow.occurrences == occ,
                            or_(
                                UnmappedTermRow.last_seen < cut,
                                and_(
                                    UnmappedTermRow.last_seen == cut,
                                    UnmappedTermRow.norm_key > key,
                                ),
                            ),
                        ),
                    )
                )
            rows = session.execute(
                q.order_by(
                    UnmappedTermRow.occurrences.desc(),
                    UnmappedTermRow.last_seen.desc(),
                    UnmappedTermRow.norm_key,
                ).limit(limit + 1)
            ).scalars().all()

            more = len(rows) > limit
            rows = rows[:limit]
            next_cursor = (
                encode_cursor((rows[-1].occurrences, rows[-1].last_seen, rows[-1].norm_key))
                if more and rows else None
            )
            return [_to_term(r) for r in rows], next_cursor
```

Add `and_, or_` to that module's SQLAlchemy imports and `datetime` if absent.

- [ ] **Step 5: Thread it through the service and the route**

`CurationService.list_unmapped`:

```python
    def list_unmapped(
        self,
        status: Optional[CurationStatus] = None,
        limit: Optional[int] = None,
        *,
        cursor: Optional[str] = None,
    ) -> UnmappedPage:
        cap = self._settings.cur_queue_default_limit
        limit = cap if limit is None else max(1, min(limit, cap))
        terms, next_cursor = self._store.list_terms(status, limit, cursor=cursor)
        return UnmappedPage(terms=terms, next_cursor=next_cursor)
```

The route:

```python
@router.get("/curation/skills/unmapped", response_model=UnmappedPage)
async def list_unmapped_terms(
    request: Request,
    status: Optional[CurationStatus] = None,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> UnmappedPage:
    try:
        return _services(request).curation.list_unmapped(status, limit, cursor=cursor)
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

- [ ] **Step 6: Fix the smoke that reads this endpoint**

Run `grep -rn "curation/skills/unmapped" scripts/ tests/` and update every caller to read `["terms"]`. `scripts/smoke_s63.py` is ours; fix it rather than leaving it broken.

- [ ] **Step 7: Run the affected tests + the s63 smoke**

Run: `python -m pytest tests/test_curation_api.py tests/test_curation_service.py tests/test_curation_store.py -q`
Expected: PASS.

Run: `DEE_OPENROUTER_API_KEY="" python scripts/smoke_s63.py`
Expected: green, exit 0.

- [ ] **Step 8: Full suite + commit**

Run: `python -m pytest -q` → no failures.

```bash
git add app/curation/ app/api/routes.py tests/test_curation_api.py scripts/smoke_s63.py
git commit -m "feat(s84b): cursor-page the curation queue"
```

---

## Task 11: `POST /features/materialize`, and both 422 sites become 200

**Files:**
- Modify: `app/candidates/store.py` (add `list_candidate_ids`)
- Modify: `app/matching/schema.py:116-124` (`MatchResult.reason`)
- Modify: `app/api/routes.py:979-992` (match) and `:1081-1090` (board)
- Modify: `app/api/routes.py` (new admin route)
- Test: `tests/test_features_materialize_api.py`, plus edits to `tests/test_jobs_api.py` / `tests/test_dashboard_api.py` where they assert the 422

**Interfaces:**
- Consumes: `materialize_candidate` (`app/features/materialize.py`), `default_view` / `get_feature_registry` (`app/features`).
- Produces:
  - `CandidateStore.list_candidate_ids(limit: int) -> list[str]`
  - `MatchResult.reason: Optional[str]`
  - `POST /features/materialize` (admin) → `MaterializeResponse{view_name, view_version, as_of, materialized, skipped}`

**Context you need:** `app/features/materialize.py` is reachable only from Python — five smokes materialize by importing it in-process. For a self-registered org that makes the 422 below **permanent, not transient**, which is why this task pairs the route with the status change.

Materialization is **global across all candidates** and consent-masked per candidate (S4.2), so it is an **operator** action: on the org plane, one customer's call would compute vectors over every customer's people.

`"no materialized candidates to match"` appears at **two** call sites (`routes.py:991` and `:1089`) and an empty feature store is a *server-side* state — a 422 blames the client for it. Both become 200 with an empty ranking and a stated reason, mirroring `GET /candidates/{id}/card` (`UI.md` §6). **Change both, in the same commit**: one fixed and one left is this repo's signature bug.

- [ ] **Step 1: Write the failing test**

Create `tests/test_features_materialize_api.py`:

```python
"""S8.4 Phase B: materialization gets an HTTP route, and an empty feature store
stops being the client's fault.

Before this, `app/features/materialize.py` was reachable only from Python, so a
self-registered org's board 422'd PERMANENTLY -- there was no call it could make
to fix it.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _org_key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_an_empty_feature_store_gives_200_with_a_reason_not_422(services):
    """Both former 422 sites, in one test, because fixing one and leaving the
    other is this repo's signature defect."""
    _, key = _org_key(services)
    with _client(services) as c:
        job = c.post("/jobs", headers={"X-Org-Key": key}, json={
            "title": "Senior Engineer", "skills": ["python"],
        })
        assert job.status_code == 200, job.text
        req_id = job.json()["id"]

        match = c.post(f"/jobs/{req_id}/match", headers={"X-Org-Key": key}, json={})
        assert match.status_code == 200
        assert match.json()["pool_size"] == 0
        assert match.json()["ranked"] == []
        assert match.json()["reason"] == "no_materialized_candidates"

        board = c.get(f"/jobs/{req_id}/board", headers={"X-Org-Key": key})
        assert board.status_code == 200
        assert board.json()["match"]["reason"] == "no_materialized_candidates"


def test_materialize_route_fills_the_pool(services, genuine_resume):
    with _client(services) as c:
        up = c.post("/candidates", json={"resume_text": genuine_resume, "domain": "genai"})
        assert up.status_code == 200

        run = c.post("/features/materialize", json={})
        assert run.status_code == 200, run.text
        assert run.json()["materialized"] >= 1

    _, key = _org_key(services)
    with _client(services) as c:
        req_id = c.post("/jobs", headers={"X-Org-Key": key},
                        json={"title": "Senior Engineer", "skills": ["python"]}).json()["id"]
        match = c.post(f"/jobs/{req_id}/match", headers={"X-Org-Key": key}, json={})
        assert match.json()["pool_size"] >= 1
        assert match.json()["reason"] is None, "a successful match states no reason"


def test_materialize_accepts_an_explicit_candidate_list(services, genuine_resume):
    with _client(services) as c:
        cid = c.post("/candidates",
                     json={"resume_text": genuine_resume, "domain": "genai"}).json()["candidate_id"]
        run = c.post("/features/materialize", json={"candidate_ids": [cid]})
        assert run.json()["materialized"] == 1

        unknown = c.post("/features/materialize", json={"candidate_ids": ["nope"]})
        assert unknown.status_code == 200
        assert unknown.json()["materialized"] == 0 and unknown.json()["skipped"] == 1


def test_materialize_is_admin_only(services):
    _, key = _org_key(services)
    with _client(services) as c:
        assert c.post("/features/materialize", json={},
                      headers={"X-Org-Key": key, "X-API-Key": "wrong"}).status_code == 401
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_features_materialize_api.py -q`
Expected: FAIL — 422 from match/board, 404 from `/features/materialize`.

- [ ] **Step 3: Add `list_candidate_ids`**

In `app/candidates/store.py`:

```python
    def list_candidate_ids(self, limit: int) -> list[str]:
        """Oldest first, bounded. Used by the admin materialization route --
        the store has never needed a full enumeration before."""
        with self._session_factory() as session:
            return list(session.execute(
                select(CandidateRow.id)
                .order_by(CandidateRow.created_at, CandidateRow.id)
                .limit(limit)
            ).scalars().all())
```

- [ ] **Step 4: Add `MatchResult.reason`**

In `app/matching/schema.py`:

```python
    #: Why the ranking is empty, when it is. `no_materialized_candidates` means
    #: the feature store has not been materialized -- a SERVER-side state, which
    #: is why this is a 200 with a reason rather than a 422 blaming the caller
    #: (S8.4 Phase B §1.11). None on every successful match.
    reason: Optional[str] = None
```

- [ ] **Step 5: Change both 422 sites**

`match_job` — replace the `pool_size == 0` block:

```python
    if result.pool_size == 0:
        # 200, not 422: an empty feature store is a server-side state and the
        # caller cannot fix it. Mirrors GET /candidates/{id}/card's
        # 200-with-status pattern (UI.md §6).
        return result.model_copy(update={"reason": "no_materialized_candidates"})
    return result
```

`job_board` — replace its `pool_size == 0` block:

```python
    if board.match.pool_size == 0:
        board = board.model_copy(update={
            "match": board.match.model_copy(
                update={"reason": "no_materialized_candidates"}
            )
        })
    return board
```

- [ ] **Step 6: Add the admin route**

```python
class MaterializeRequest(BaseModel):
    candidate_ids: Optional[list[str]] = None
    as_of: Optional[datetime] = None
    view_name: Optional[str] = None


class MaterializeResponse(BaseModel):
    view_name: str
    view_version: int
    as_of: Optional[datetime] = None
    materialized: int = 0
    skipped: int = 0


@router.post("/features/materialize", response_model=MaterializeResponse)
async def materialize_features(
    body: MaterializeRequest, request: Request
) -> MaterializeResponse:
    """Compute + persist feature vectors. ADMIN plane, deliberately.

    Materialization spans ALL candidates and is consent-masked per candidate
    (S4.2), so on the org plane one customer's call would compute vectors over
    every customer's people. It is an operator action.

    Until this route existed, `app/features/materialize.py` was reachable only
    from Python -- which made `GET /jobs/{id}/board`'s empty-pool state
    permanent for a self-registered org rather than transient.
    """
    services = _services(request)
    registry = get_feature_registry()
    view = default_view(registry, settings=services.settings)
    view_name = body.view_name or services.settings.feat_default_view

    ids = body.candidate_ids
    if ids is None:
        ids = services.candidates.list_candidate_ids(
            services.settings.materialize_max_candidates
        )

    materialized = skipped = 0
    for candidate_id in ids:
        mv = materialize_candidate(
            candidate_id, view=view, registry=registry, as_of=body.as_of,
            candidate_store=services.candidates,
            report_store=services.report_store,
            ledger_store=services.ledger,
        )
        if mv is None:
            # No context for this candidate (unknown id, or nothing to compute).
            skipped += 1
            continue
        services.features.upsert_vector(mv)
        materialized += 1

    return MaterializeResponse(
        view_name=view_name, view_version=view.version, as_of=body.as_of,
        materialized=materialized, skipped=skipped,
    )
```

Add `from app.features.materialize import materialize_candidate` to the imports.

- [ ] **Step 7: Update the tests that pinned the old 422**

Run `grep -rn "no materialized candidates" tests/ scripts/` and change every assertion from `422` to `200` **with the reason**. `scripts/smoke_s53.py` asserts the 422 explicitly in its own docstring and body — update both, and note in the smoke why.

- [ ] **Step 8: Run the affected tests + the smokes that touch matching**

Run: `python -m pytest tests/test_features_materialize_api.py tests/test_jobs_api.py tests/test_dashboard_api.py tests/test_matching_match.py -q`
Expected: PASS.

Run: `DEE_OPENROUTER_API_KEY="" python scripts/smoke_s53.py` and `DEE_OPENROUTER_API_KEY="" python scripts/smoke_s51.py`
Expected: green, exit 0.

- [ ] **Step 9: Full suite + commit**

Run: `python -m pytest -q` → no failures.

```bash
git add app/candidates/store.py app/matching/schema.py app/api/routes.py tests/ scripts/smoke_s53.py
git commit -m "feat(s84b): admin materialize route; an empty pool is 200 with a reason, not 422"
```

---

## Task 12: Comp returns one shape

**Files:**
- Modify: `app/api/routes.py:1041-1054` (`comp_estimate`)
- Test: `tests/test_comp_api.py` (edit the existing assertions)

**Interfaces:**
- Consumes: `CompService.estimate`, `CompBenchmark` (`app/comp/schema.py:75-83`).
- Produces: `POST /comp/estimate` → `CompBenchmark` with `requisition_band`, `position` and `delta_pct` all `None`.

**Context you need:** `GET /jobs/{id}/comp` returns a `CompBenchmark` **wrapping** the estimate; `POST /comp/estimate` returns the bare `CompBandEstimate`. During the wiring session, assuming one shape rendered a comp band made entirely of dashes. The UI already unwraps `CompBenchmark` centrally, so this makes that unwrap correct for both paths (parent spec §4.7).

The three positioning fields are `None` and that is the honest answer — there was no requisition to position against, and a zero would read as "exactly at market".

- [ ] **Step 1: Write the failing test**

Add to `tests/test_comp_api.py`:

```python
def test_comp_estimate_returns_a_benchmark_with_null_positioning(services):
    """S8.4 Phase B §1.12: one shape from both comp endpoints.

    The three positioning fields are NULL rather than zero -- there was no
    requisition to position against, and 0.0 would read as 'exactly at market'.
    """
    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.conftest import ADMIN_HEADERS

    org = services.ledger.create_organization("Agency A")
    key = services.ledger.issue_api_key(org.id)

    with TestClient(create_app(services), headers=ADMIN_HEADERS) as c:
        r = c.post("/comp/estimate", headers={"X-Org-Key": key}, json={
            "skills": ["python"], "title": "Senior Engineer", "years_experience": 6,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert "estimate" in body, "the same wrapper GET /jobs/{id}/comp returns"
        assert body["requisition_band"] is None
        assert body["position"] is None
        assert body["delta_pct"] is None
        assert body["advisory"] is True
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_comp_api.py -q`
Expected: FAIL — the response is a bare `CompBandEstimate`, so `"estimate" not in body`.

- [ ] **Step 3: Change the route**

```python
@org_router.post("/comp/estimate", response_model=CompBenchmark)
async def comp_estimate(
    body: CompEstimateRequest, request: Request, org_id: str = Depends(require_org)
) -> CompBenchmark:
    """One shape from both comp endpoints (S8.4 Phase B §1.12).

    `GET /jobs/{id}/comp` has always returned a CompBenchmark WRAPPING the
    estimate; this returned the bare estimate, and during the UI wiring session
    assuming one shape rendered a band made entirely of dashes. The three
    positioning fields are None because there is no requisition to position
    against -- honest, where a 0.0 would read as 'exactly at market'.
    """
    services = _services(request)
    try:
        signal = bands.role_signal_from_input(
            skills=body.skills, title=body.title, years=body.years_experience,
            location_tiers=body.location_tiers, remote=body.remote,
            role_family=body.role_family, seniority=body.seniority,
            settings=services.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CompBenchmark(
        estimate=services.comp.estimate(signal, org_id=org_id),
        requisition_band=None, position=None, delta_pct=None,
        reasoning="ad-hoc estimate: no requisition to position against",
    )
```

- [ ] **Step 4: Update the existing callers**

Run `grep -rn "comp/estimate" tests/ scripts/ frontend/` and update every response read. Note `frontend/api.js` already unwraps `CompBenchmark` centrally, so the UI side should need **no** change — verify by reading the unwrap, and if it does need one, make it and say so in the commit message.

- [ ] **Step 5: Run the comp tests + smoke**

Run: `python -m pytest tests/test_comp_api.py tests/test_comp_service.py tests/test_comp_estimate.py -q`
Expected: PASS.

Run: `DEE_OPENROUTER_API_KEY="" python scripts/smoke_s52.py`
Expected: green, exit 0.

- [ ] **Step 6: Full suite + commit**

Run: `python -m pytest -q` → no failures.

```bash
git add app/api/routes.py tests/test_comp_api.py scripts/smoke_s52.py
git commit -m "fix(s84b): POST /comp/estimate returns CompBenchmark, one shape for both paths"
```

---

## Task 13: OpenAPI a typed client can actually be generated from

**Files:**
- Modify: `app/main.py` (one `operation_id` pass in `create_app`)
- Modify: `app/api/routes.py` (type the 38 `dict` responses)
- Create: `tests/test_openapi_contract.py`

**Interfaces:**
- Consumes: the live FastAPI app.
- Produces: a unique explicit `operation_id` on every route (`= route.name`), a typed `response_model` on every route, and the contract test that keeps both true for routes nobody has written yet.

**Context you need — measured, and bigger than the spec first said.**

```
82 operations
 0 duplicate operationIds        (unique, but auto-derived and unusable:
                                  list_candidate_reports_candidates__candidate_id__reports_get)
 0 missing success schemas
38 UNTYPED success schemas       {"type":"object","additionalProperties":true}
```

**The first count of this was wrong, and the way it was wrong matters more than the number.** It looked only at `200`/`201` and reported "5 missing" — those five were the OTP routes, which answer **202**. The check was measuring its own assumption about status codes rather than the API. Re-run across every `2xx`: nothing is missing, 38 are untyped. Believe the second measurement because it is the one that enumerated what it found instead of what it expected.

Most of the 38 are cheap. Roughly:
- **Already have a model, annotated `-> dict` anyway** — `GET /verification/candidates/{id}/assurance` (`IdentityAssurance`), `GET /verification/candidates/{id}/claims`, `GET /interview/candidates/{id}/assessments`, `GET /portal/verifications`, `GET /portal/interviews`, `POST /portal/interviews*`, `POST /portal/documents`.
- **One-field acknowledgements** — `{deleted: true}`, `{revoked: true}`, `{ok: true}` shapes across the deletes, revokes and rotations. Give them a small shared set of models; do **not** invent one model per route.
- **The eight `/auth/*` routes** — two shapes: `CodeRequestAccepted{accepted: true}` for the five 202s, and the existing verify response for the three that establish a session.
- `GET /`, `GET /healthz`, `GET /auth/me`, `POST /auth/logout`.

**Set `operation_id` in a loop, not 82 times by hand.** A per-route literal is 82 chances to typo and no protection for route 83. One pass over the route table gives every current and future route the property, and the test then has something real to assert.

- [ ] **Step 1: Write the failing test**

Create `tests/test_openapi_contract.py`:

```python
"""S8.4 Phase B: the OpenAPI document is the client contract, so it is tested.

The wiring session had to DISCOVER the 401/403/404/409 forks by measurement
because the schema did not describe them. This file is the standing answer:
every property a generated client depends on is asserted over the LIVE schema,
so a route added next sprint inherits the requirement instead of quietly
opting out.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import create_app
from tests.test_route_table_guard import _walk


@pytest.fixture(scope="module")
def app(services_module_scope=None):
    from tests.conftest import ADMIN_KEY  # noqa: F401 - documents the auth context
    return create_app()


def _api_routes(app):
    return [r for r, _ in _walk(app.routes) if isinstance(r, APIRoute)]


def test_every_route_has_an_explicit_operation_id(app):
    """Auto-derived ids are unique but unusable -- a generated client method
    called list_candidate_reports_candidates__candidate_id__reports_get is not
    a client anyone will keep."""
    for route in _api_routes(app):
        assert route.operation_id, f"{route.path} has no explicit operation_id"
        assert route.operation_id == route.name, (
            f"{route.path}: operation_id should be the handler name"
        )


def test_operation_ids_are_unique(app):
    """Two handlers sharing a name would silently collapse into one client
    method. This is the assertion the loop in create_app cannot make itself."""
    ids = [r.operation_id for r in _api_routes(app)]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate operation_ids: {sorted(dupes)}"


def test_every_route_declares_a_response_model(app):
    for route in _api_routes(app):
        assert route.response_model is not None, f"{route.path} declares no response_model"


def test_no_success_response_is_an_untyped_object(app):
    """`-> dict` generates Record<string, any> and puts the caller back to
    guessing. MEASURED at 38 of 82 before this sprint."""
    spec = app.openapi()
    untyped = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            for code, resp in op.get("responses", {}).items():
                if not code.startswith("2"):
                    continue
                schema = resp.get("content", {}).get("application/json", {}).get("schema", {})
                if schema.get("type") == "object" and schema.get("additionalProperties") is True:
                    untyped.append(f"{method.upper()} {path}")
    assert not untyped, f"untyped success schemas: {untyped}"


def test_the_schema_covers_every_route(app):
    """Non-vacuity, in the S8.2 tradition: a walk that sees nothing passes
    everything. 82 routes existed when this was written."""
    spec = app.openapi()
    operations = sum(len(m) for m in spec["paths"].values())
    assert operations >= 80, f"only {operations} operations inspected"
```

> The `app` fixture above must build an app the same way the other API tests do. Copy the construction from `tests/test_route_table_guard.py` — if that file builds `create_app()` with no services, do the same; if it uses the `services` fixture, use it and drop the module scope.

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_openapi_contract.py -q`
Expected: FAIL on `operation_id` (auto-derived, not equal to `route.name`) and on the 38 untyped responses.

- [ ] **Step 3: Set `operation_id` once, in `create_app`**

In `app/main.py`, after the `include_router` calls:

```python
    # OpenAPI: give every route the handler's own name as its operation_id.
    #
    # In a loop rather than 82 literals: a per-route operation_id= argument is
    # 82 chances to typo and no protection at all for route 83. FastAPI's
    # default is unique but unusable -- it derives
    # `list_candidate_reports_candidates__candidate_id__reports_get` from the
    # path -- and S8.4 exists partly so a typed client can be generated from
    # this document. tests/test_openapi_contract.py asserts uniqueness, which is
    # the one thing this loop cannot check for itself.
    for route in _iter_api_routes(app.routes):
        route.operation_id = route.name
```

and add the walker beside it (FastAPI 0.138 does not flatten `include_router`, so a naive loop sees **one** route — S8.2's trap, re-encountered while measuring this task):

```python
def _iter_api_routes(routes):
    """Every real APIRoute, recursing through the _IncludedRouter wrappers
    FastAPI 0.138 stores instead of flattening include_router. A naive
    `for route in app.routes` sees ONE route here."""
    from fastapi.routing import APIRoute

    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(original.routes)
        elif isinstance(route, APIRoute):
            yield route
```

- [ ] **Step 4: Type the 38 responses**

Add the small shared models to `app/api/routes.py` near the top of the schema block:

```python
class Acknowledged(BaseModel):
    """A one-field acknowledgement. Shared deliberately: 38 responses were
    untyped `dict`, and one model per route would trade an untyped client for
    an unreadable one."""

    ok: bool = True


class DeletedResponse(BaseModel):
    deleted: bool = True
    id: Optional[str] = None


class RevokedResponse(BaseModel):
    revoked: bool
    id: Optional[str] = None


class CodeRequestAccepted(BaseModel):
    """The 202 from every signup/login. Identical for known and unknown
    addresses, on purpose -- see AUTH.md's anti-enumeration rule."""

    accepted: bool = True
```

Then work through the list below, changing each handler's `-> dict` annotation and `response_model`. **Run the full suite after every five or six routes** — each change is small, but a wrong model silently reshapes a response some test asserts on.

The 38, grouped:

```
Already have a model — annotate it:
  GET  /verification/candidates/{candidate_id}/assurance   -> IdentityAssurance
  GET  /verification/candidates/{candidate_id}/claims      -> list[ClaimEvidence]
  GET  /interview/candidates/{candidate_id}/assessments    -> (the existing summary model)
  GET  /portal/verifications                               -> list[Verification]
  POST /portal/verifications                               -> Verification
  POST /portal/verifications/{verification_id}/confirm     -> Verification
  POST /portal/documents                                   -> (the document-ingest model)
  GET  /portal/interviews                                  -> list[InterviewSummary]
  POST /portal/interviews                                  -> InterviewSession
  GET  /portal/interviews/{session_id}                     -> InterviewSession
  POST /portal/interviews/{session_id}/answers             -> InterviewTurn
  POST /portal/interviews/{session_id}/finish              -> InterviewAssessment
  POST /candidates/{candidate_id}/verifications/manual-review -> Verification
  POST /report/{report_id}/outcome                         -> OutcomeRecord
  GET  /report/{report_id}/outcomes                        -> list[OutcomeRecord]
  POST /admin/users                                        -> (the admin-user model)
  GET  /auth/me                                            -> Principal (or its view model)

Acknowledgements — use the shared models above:
  DELETE /candidates/{candidate_id}                        -> DeletedResponse
  DELETE /candidates/{candidate_id}/resumes/{resume_id}    -> DeletedResponse
  DELETE /ledger/orgs/{org_id}                             -> DeletedResponse
  DELETE /admin/users/{admin_user_id}                      -> DeletedResponse
  DELETE /portal/me                                        -> (keep its erasure counts; give it a model)
  POST /ledger/consent/{consent_id}/revoke                 -> RevokedResponse
  POST /portal/consents/{consent_id}/revoke                -> RevokedResponse
  POST /auth/sessions/{session_id}/revoke                  -> RevokedResponse
  POST /auth/logout                                        -> Acknowledged
  POST /candidates/{candidate_id}/auth-key                 -> (key-issue model; returned once)
  POST /ledger/orgs/{org_id}/api-key                       -> (same shape as above)

Auth 202s — CodeRequestAccepted:
  POST /auth/org/signup · /auth/org/login
  POST /auth/candidate/signup · /auth/candidate/login
  POST /auth/admin/login

Auth verifies — the existing session-establishing shape, given a model:
  POST /auth/org/verify · /auth/candidate/verify · /auth/admin/verify

Public:
  GET /            -> a small ServiceInfo model
  GET /healthz     -> a small Health model
```

> **Do not change any response body.** These are annotations over shapes that already exist — if a test starts failing on a *value*, the model is wrong, not the test. The one place to be careful is `DELETE /portal/me`, which returns erasure counts (`reports_deleted` and friends): model the real fields rather than collapsing it to `{deleted: true}`.

- [ ] **Step 5: Say in the schema which lists are paged and which are not**

Design §1.4 decided that `POST /jobs/{req_id}/match` and `POST /talent/search`
keep `limit` and get **no** cursor, because they re-rank on every request and a
cursor would promise a stability they cannot keep. A client author cannot see
that decision unless the document states it, so add it to both route
decorators:

```python
@org_router.post(
    "/jobs/{req_id}/match",
    response_model=MatchResult,
    description=(
        "Top-N advisory ranking. NOT paginated: the pool is re-ranked on every "
        "request, so there is no stable key to page on and a cursor would "
        "promise an ordering this endpoint cannot keep. Use `limit`."
    ),
)
```

and the equivalent on `POST /talent/search`. Add the mirror sentence to the
three cursor-paged routes (`GET /screening/batches`,
`GET /screening/batches/{batch_id}/queue`, `GET /curation/skills/unmapped`):
"Cursor-paginated; pass `next_cursor` back as `cursor`."

- [ ] **Step 6: Run the contract test**

Run: `python -m pytest tests/test_openapi_contract.py -q`
Expected: PASS.

- [ ] **Step 7: Full suite**

Run: `python -m pytest -q`
Expected: no failures. Expect a handful of tests to need *no* change; if many fail, a model is reshaping a body.

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/api/routes.py tests/test_openapi_contract.py
git commit -m "feat(s84b): typed OpenAPI — explicit operation ids, 38 dict responses modelled"
```

---

## Task 14: `scripts/smoke_s84b.py` — the sprint over real HTTP

**Files:**
- Create: `scripts/smoke_s84b.py`

**Context you need:** the smokes boot uvicorn against a migrated scratch database and drive real HTTP. Copy the harness from `scripts/smoke_s84a.py` — the process launch, `_wait_healthy`, the check counter and the exit code.

**Pin `DEE_OPENROUTER_API_KEY=""`.** Phase A found **five** smokes making live billed calls because they never pinned it and this repo's `.env` holds a real key; `smoke_s23` ran past a ten-minute timeout before the pin and finished in seconds after. A smoke claiming to prove the key-less path must actually run key-less.

**What it must prove**, in order:

1. Two organisations exist, each with its own `X-Org-Key`.
2. **Registration is evaluation-free** — register a 3-item batch, and `GET /candidates` shows nothing new (the batch created rows, not candidates).
3. **Bounded processing** — `POST .../process` returns `processed <= screening_max_items_per_call`, and repeated calls drive `remaining` to 0.
4. **Derived progress** — `GET /screening/batches/{id}` counts move `pending → done` across those calls, and `status` ends `complete`.
5. **A failed item does not stop the batch** — include one empty item; it ends `failed` with `error: "empty_resume"` while the others finish, and the batch reads `partial`.
6. **The queue is ranked**, riskiest first, with unscreened rows last, and every row carries a non-empty `reason`.
7. **The farm signal is present and identity-free** — seed org B's near-duplicate first, then screen org A's; A's queue row shows a farm band/score and the serialized row contains **no** `matches` key at all.
8. **The summary** returns counts only — assert the body contains no `candidate_id`, `resume_id`, `report_id` or `reasoning`.
9. **Cursor paging** — `?limit=2` then follow `next_cursor`; the union is every row exactly once.
10. **Cross-org 404 on all five batch routes**, byte-identical to a batch id that never existed.
11. **A cursor minted by org A returns nothing when replayed by org B.**
12. **`DELETE /screening/batches/{id}`** → 200, then `GET` → 404.
13. **The materialization route un-breaks the board** — `GET /jobs/{id}/board` first returns 200 with `reason: "no_materialized_candidates"`, then `POST /features/materialize`, then the board's `pool_size` is non-zero.
14. **`POST /comp/estimate` returns a `CompBenchmark`** with three null positioning fields.
15. **A taken organisation name in a different case** is refused `409 organization_name_taken` at signup.

- [ ] **Step 1: Write the smoke**

Create `scripts/smoke_s84b.py`. Copy the harness from `smoke_s84a.py` — read that file first and match its process launch, `_wait_healthy`, check counter and exit code. The skeleton, with the parts that differ:

```python
"""S8.4 Phase B smoke: the screening surface over real HTTP, key-less.

Boots uvicorn on a migrated scratch DB and drives the whole sprint: register a
batch without evaluating anything, process it in bounded calls, watch derived
progress, read the ranked queue and the roll-up, page with a cursor, prove
cross-org 404s on every route, delete, and confirm the materialization route
un-breaks the board.

Run from the repo root:  python scripts/smoke_s84b.py
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

PORT = 8085
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

RESUME = (
    "Priya Nair\nEmail: priya.nair@example.in\n"
    "EXPERIENCE\n- Senior Engineer, Acme (2019 - Present)\n"
    "SKILLS\nPython, Django\n"
)

_failures = 0


def check(label, ok, detail=""):
    global _failures
    print(f"{'OK  ' if ok else 'FAIL'} {label}{'' if ok else f'  <- {detail}'}")
    if not ok:
        _failures += 1


def _wait_healthy(c):
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    workdir = Path(tempfile.mkdtemp())
    db_url = f"sqlite:///{workdir / 'smoke.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": db_url,
        "DEE_FLYWHEEL_PATH": (workdir / "flywheel.jsonl").as_posix(),
        # MUST be memory: a persistent Chroma client hangs on this machine, and
        # a smoke that hangs is a smoke nobody runs.
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
        # Phase A found FIVE smokes making live billed calls because they never
        # pinned this and .env holds a real key. A smoke that claims to prove
        # the key-less path must actually run key-less.
        "DEE_OPENROUTER_API_KEY": "",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, timeout=120.0) as c:
            if not _wait_healthy(c):
                print("server never became healthy")
                return 1
            run_checks(c)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    print(f"\n{'ALL OK' if _failures == 0 else f'{_failures} FAILED'}")
    return 0 if _failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

`run_checks(c)` implements the fifteen checks below in order. Each is one `check(...)` call, and the labels become the smoke's output — write them as claims ("a failed item does not stop the batch"), not as route names.

- [ ] **Step 2: Run it**

Run: `DEE_OPENROUTER_API_KEY="" python scripts/smoke_s84b.py`
Expected: every check OK, exit 0. Fix the **code** if a check fails — the smoke is the specification here.

- [ ] **Step 3: Confirm it is genuinely key-less**

Run: `grep -n "DEE_OPENROUTER_API_KEY" scripts/smoke_s84b.py`
Expected: the pin is present in the subprocess environment, not merely in the docstring.

- [ ] **Step 4: Run every regression smoke**

```bash
for s in s12 s13 s23 s41 s51 s52 s53 s63 s64 s73 s81 s82 s84a; do
  echo "== $s"; DEE_OPENROUTER_API_KEY="" python scripts/smoke_$s.py >/dev/null 2>&1 && echo OK || echo FAIL
done
```
Expected: all OK. `smoke_s53` and `smoke_s63` were edited in Tasks 10–11; `smoke_s52` in Task 12.

- [ ] **Step 5: Commit**

```bash
git add scripts/smoke_s84b.py
git commit -m "test(s84b): end-to-end HTTP smoke for the screening surface"
```

---

## Task 15: Documentation

**Files:**
- Create: `SCREENING.md`
- Modify: `TENANCY.md` (§5, §8, §9)
- Modify: `UI.md` (§4.A, §4.C — the 🔜 markers become ✅)
- Modify: `docs/ROADMAP.md`

**Context you need:** a root doc per subsystem is the convention (`AUTH.md`, `PORTAL.md`, `VERIFICATION.md`, `INTERVIEWS.md`, `TENANCY.md`). Phase A's rule applies: **a rule nobody can look up is a rule the next sprint reinvents differently.**

- [ ] **Step 1: Write `SCREENING.md`**

Sections, each stating the decision *and* its rejected alternative:
1. What a batch is, and why registration and processing are separate calls (no worker exists in `app/`).
2. The seven routes, with their 404/422 forks.
3. **Why item status is stored and batch status is derived** — and the stale-claim reinterpretation that makes a redeploy self-healing.
4. **Why the queue reads `batch_items` and never a `Report`** — design §1.1, and that this is what makes the leak structurally impossible rather than correctly handled.
5. **Why `ItemSignals` holds no free text** — §1.2, the DPDP argument, and the fact that the one-line reason is composed at read time.
6. The cursor: keyset, opaque, **carries no authority**; and why `match`/`talent search` do not get one.
7. DPDP: `raw_text` cleared on success, kept on failure, `ret_batch_item_days` declared but **not yet swept** (S8.3).
8. What is deliberately not here: a worker, rate limiting, a cross-batch queue.

- [ ] **Step 2: Update `TENANCY.md`**

- **§5 (the guard)** — the sanctioned door set is now `screening_scope` **and** `screening`; the batch store is deliberately absent from `Services`; and **state the reach change honestly**: the ingest core moved to `app/screening/ingest.py`, so the guard no longer sees those lines *and no longer needs to* — the allowlist is empty, which it never was before.
- **§8** — batches are scoped; `/evaluate`, `/talent/search` and the two marketplace routes remain the open tenancy decision, unchanged.
- **§9** — add the Phase B test files and `smoke_s84b`.

- [ ] **Step 3: Update `UI.md`**

Screens A and C are no longer 🔜. Give each its real endpoints, and add the two fields a designer needs and would otherwise invent: a queue row's `reason` is **generated**, and `status` on an unprocessed row is a normal state, not an error.

- [ ] **Step 4: Update `docs/ROADMAP.md`**

Status board, "Current state" (what shipped, what was found, what was deferred, with reasons), and the session log. Follow the existing entries' density — findings and their evidence, not a summary.

- [ ] **Step 5: Commit**

```bash
git add SCREENING.md TENANCY.md UI.md docs/ROADMAP.md
git commit -m "docs(s84b): SCREENING.md; tenancy, UI and roadmap updated"
```

---

## Definition of done

1. An organisation registers a batch, processes it in bounded calls, and reads a ranked queue and a summary — **without an operator touching anything**.
2. Every one of the seven batch routes answers **404** for another org's batch, byte-identical to absence.
3. A queue row is structurally incapable of carrying another customer's identity — proven on a batch whose report genuinely has farm matches.
4. The scope guard covers the new handlers, runs with **no exemptions**, and is re-proven non-vacuous against a planted unscoped read.
5. Processing is bounded, resumable, idempotent when finished, and self-healing after a stale claim; one bad item fails alone.
6. `raw_text` is empty after success, present after failure, and gone after `DELETE`.
7. Organisation names are unique case-insensitively **at the constraint**, and the migration refuses to run over existing collisions.
8. Both former 422 sites return 200 with `reason`; materialization has an admin route.
9. Comp returns one shape from both endpoints.
10. Every route has an explicit unique `operation_id` and a typed `response_model`; **no success schema is a bare object**.
11. `pytest -q` green; `smoke_s84b` green; all existing smokes green.

---

## Self-review notes (for the executor)

Three things in this plan are known-uncertain and should be treated as *measure first, then write*:

- **Task 4's ORM index placement.** SQLAlchemy accepts a functional index in `__table_args__` only if the column object is in scope; the deferred form below the class is given because it always works. If `test_migrated_indexes_match_orm` behaves unexpectedly, re-run the measurement in the task's context block before changing the guard further.
- **Task 8's container wiring.** `build_default_services` builds objects in a dependency order that matters (`interview` after `verification`, `auth` last). `screening` needs `candidates`, `report_store`, `llm` and `settings` only, so it can go late — but read the function before inserting, and put it where those four are already bound.
- **Task 13's 38 routes.** The grouping is from a real enumeration, but each `-> dict` handler's actual return shape must be read before a model is written for it. A model that drops a field is a silent API break that no test may cover.
