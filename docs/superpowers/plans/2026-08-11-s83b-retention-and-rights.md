# S8.3 Phase B — Retention & Rights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the retention promise the portal already prints mechanically true, and
ship the DPDP correction / grievance mechanism, so the service can be operated for
paying data principals.

**Architecture:** Two new packages. `app/retention/` derives its sweep targets from
the *same* `RETENTION_KNOBS` table the portal reads, so the promise and the deletion
cannot drift; `run_sweep` is pure orchestration invoked by an admin route and a
`python -m` CLI (there is still no scheduler anywhere in `app/`). `app/rights/`
follows the `app/ratelimit/` split (schema · models · store · service) and backs a
reviewed request queue: a data principal *asks*, an operator *decides*, and only
`full_name` is ever auto-applied.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 + Alembic on SQLite (Postgres-shaped) ·
Pydantic v2 · pytest (fully offline).

**Spec:** `docs/superpowers/specs/2026-08-10-s83-operating-safely-design.md` §7–§13.
Phase A (`s83a-limits-and-metrics`) is merged at `a57a05d`.

**Branch:** `s83b-retention-and-rights`, cut from `main`.

## Global Constraints

- **Baseline measured on `main` 2026-08-11: `pytest -q` = 1689 passed.** Every task
  ends green; the count only goes up.
- **TDD, one commit per task.** Write the failing test, *run it and see it fail for
  the stated reason*, implement, see it pass, commit. A test that has never been red
  has proven nothing.
- **Fully offline.** `NullLLM` / fake services from `tests/conftest.py`; a fake clock
  (`now=` argument) for every window. No network, no sleeping.
- **No `Optional` defaults on injected gates.** `RightsService` takes `limiter` as a
  REQUIRED constructor argument. Phase A's lesson: under an `Optional` default the
  four tests that construct the service directly keep passing while silently running
  **unlimited**, which is the entire failure mode.
- **Advisory only.** Nothing here auto-rejects a person; a correction is *reviewed*.
- **DPDP:** first-party data only; every new table has a consent/erasure story stated
  in its model docstring.
- **Config:** every new tunable goes in `config.yaml` *and* `app/core/config.py` with
  a comment saying what depends on it. Secrets stay in `.env` (`DEE_*`).
- **A knob whose rule has no call site is refused** (spec 0.5). Same for a metric:
  `tests/test_metrics.py::test_every_declared_metric_has_a_call_site` fails the build
  if `_HELP` declares a name nothing increments. `retention_deleted` is added to
  `_HELP` in the **same commit** as the code that increments it (Task 4).
- **Migrations are additive and reversible**; `alembic upgrade head` then `downgrade`
  must both run. Follow `alembic/versions/0021_rate_limit_counters.py` for style.
- **OneDrive trap (S8.4 Phase B):** after rewriting anything under `alembic/`, let the
  file settle before running pytest in a subprocess, or the local `alembic/` directory
  shadows the installed package (`ImportError: cannot import name 'command'`).

---

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `app/retention/__init__.py` | package marker |
| `app/retention/plan.py` | `SweepMode`, `SweepTarget`, `TARGETS` — the target table, derived from `RETENTION_KNOBS`. No I/O. |
| `app/retention/schema.py` | `ClassSweepResult`, `SweepReport` — the response contracts. No I/O. |
| `app/retention/sweep.py` | `run_sweep(...)` + the `python -m app.retention.sweep` CLI |
| `app/rights/__init__.py` | package marker |
| `app/rights/schema.py` | `RequestKind`, `RequestStatus`, `CorrectionField`, `ResolvedBy`, `RequestView`, `GrievanceContact`, `RequestRefused`, `build_grievance_contact` |
| `app/rights/models.py` | `DataPrincipalRequestRow` → migration `0022` |
| `app/rights/store.py` | `RightsStore` — the only thing that touches the table |
| `app/rights/service.py` | `RightsService` — submit (rate-limited), list, resolve, apply |
| `alembic/versions/0022_data_principal_requests.py` | the migration |
| `tests/test_retention_plan.py` … `tests/test_rights_admin_api.py` | see each task |
| `scripts/smoke_s83b.py` | the sprint's smoke |

**Modified**

| Path | Change |
|---|---|
| `app/core/config.py` | 7 new knobs (Tasks 1, 5, 11, 14) |
| `config.yaml` | the same 7, with the reasoning |
| `app/portal/retention.py` | `RETENTION_KNOBS` 8 → 11 classes; `sweep_active` stops being a literal |
| `app/portal/schema.py` | `MyData.requests`, `MyData.grievance` |
| `app/portal/service.py` | reads the request queue into `MyData` |
| `app/metrics/registry.py` | `Metrics.add()`; `retention_deleted` in `_HELP` |
| `app/services/__init__.py` | `rights` on the container |
| `app/api/routes.py` | 7 routes; `PUBLIC_PATHS` gains `/grievance` |
| `app/core/boot.py` | refusal #7 (empty grievance officer email in prod) |
| `app/candidates/store.py` | `apply_correction` |
| `app/ratelimit/service.py` | the `request_submit` rule |
| `tests/conftest.py` | `make_services` builds `rights` |
| `tests/test_metrics.py` | the call-site scanner must also see `add(` |
| `OPERATING.md`, `SCREENING.md`, `UI.md`, `docs/ROADMAP.md` | Task 15 |

---

## The eleven data classes (measured 2026-08-11, off the ORM)

`RETENTION_KNOBS` is the single source: it is what the candidate is **told** in
`/portal/me`, and from this sprint on it is also what the sweeper **does**. A
sweeper carrying its own list of targets is a portal that keeps promising a window
nothing enforces.

| data_class | knob | table | timestamp column | mode |
|---|---|---|---|---|
| `resumes` | `ret_resume_days` (1095) | `resumes` | `created_at` | delete |
| `profile_sources` | `ret_profile_source_days` (1095) | `profile_sources` | `created_at` | delete |
| `verifications` | `ret_verification_days` (1095) | `verifications` | `created_at` | delete |
| `interviews` | `ret_interview_session_days` (1095) | `interview_sessions` | `created_at` | delete |
| `interview_records` | `ret_interview_record_days` (1825) | `interview_records` | `created_at` | delete |
| `coding_rounds` | `ret_coding_round_days` (1825) | `coding_round_results` | `created_at` | delete |
| `observed_offers` | `ret_observed_offer_days` (1825) | `observed_offers` | `created_at` | delete |
| `audit_log` | `ret_audit_log_days` (2555) | `audit_log` | `created_at` | delete |
| `batch_item_text` | `ret_batch_item_days` (90) | `batch_items` | `created_at` | **clear** `raw_text` |
| `rate_limit_counters` | `ret_rate_limit_days` (7, NEW) | `rate_limit_counters` | `expires_at` | delete |
| `login_state` | `ret_login_state_days` (7, NEW) | `login_challenges` **and** `auth_sessions` | `expires_at` | delete |

**Eleven classes, twelve targets.** `login_state` is one data class over two tables —
an abandoned challenge is never consumed and a session that expires without a logout
is never revoked, and they are the same fact to the person they describe. The drift
guard therefore compares the *set of data classes*, not the length of the list.

**Three consequences worth stating before anyone writes code:**

1. **Adding three classes to `RETENTION_KNOBS` widens what the portal discloses**, from
   8 windows to 11. That is the correct direction: `batch_item_text` is a copy of the
   person's own resume text, `rate_limit_counters` holds a salted hash of their email
   beside one of their IP, and `login_state` is their abandoned login attempts. A
   window we enforce and do not disclose is the mirror image of the bug this sprint
   is fixing. `tests/test_portal_retention.py` compares against `set(RETENTION_KNOBS)`
   and needs **no edit**.
2. **Clear-mode needs a non-empty predicate.** `batch_items.raw_text` is `""` on
   success, so a sweep keyed on age alone would report "cleared 400 rows" every single
   day forever. The target carries `WHERE raw_text != ''`, and a test pins that a
   second sweep over the same data reports **0**.
3. **Bulk DELETE relies on the database's own CASCADE, and that is sound here.**
   A bulk `DELETE` bypasses SQLAlchemy's ORM-level `cascade="all, delete-orphan"` — but
   every relationship in play also declares `passive_deletes=True` against a real
   `ondelete="CASCADE"` FK, and `app/core/db.py` sets `PRAGMA foreign_keys=ON` on every
   SQLite connection. Task 2 proves it rather than assuming it: sweeping an old
   `resumes` row must take its `extractions` row with it.

---

## Task 1: The sweep target table, derived from RETENTION_KNOBS

**Files:**
- Create: `app/retention/__init__.py`, `app/retention/plan.py`
- Modify: `app/portal/retention.py` (RETENTION_KNOBS 8 → 11), `app/core/config.py`, `config.yaml`
- Test: `tests/test_retention_plan.py`

**Interfaces:**
- Consumes: `app.portal.retention.RETENTION_KNOBS`, `app.core.config.Settings`
- Produces: `SweepMode` (StrEnum: `DELETE`, `CLEAR`), `SweepTarget` (frozen dataclass:
  `data_class: str`, `knob: str`, `model: type`, `timestamp_column: str`,
  `mode: SweepMode`, `clear_column: Optional[str] = None`), `TARGETS: tuple[SweepTarget, ...]`,
  `data_classes() -> set[str]`, `ttl_days(target, settings) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retention_plan.py
"""The sweeper and the portal must name the same classes -- §7.1."""
from app.core.config import Settings
from app.portal.retention import RETENTION_KNOBS
from app.retention.plan import TARGETS, SweepMode, data_classes, ttl_days


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def test_every_declared_window_has_a_sweep_target_and_vice_versa():
    """Set equality in BOTH directions. One direction leaves a promise nothing
    enforces; the other leaves a deletion nobody was told about."""
    assert data_classes() == set(RETENTION_KNOBS)


def test_every_target_names_a_real_settings_knob():
    s = _settings()
    for t in TARGETS:
        assert hasattr(s, t.knob), f"{t.data_class} names a knob that does not exist"
        assert ttl_days(t, s) >= 1


def test_every_target_names_a_real_column_on_its_model():
    for t in TARGETS:
        assert hasattr(t.model, t.timestamp_column), t.data_class
        if t.mode is SweepMode.CLEAR:
            assert t.clear_column and hasattr(t.model, t.clear_column), t.data_class
        else:
            assert t.clear_column is None, t.data_class


def test_login_state_is_one_class_over_two_tables():
    """The reason the guard compares a SET and not a length."""
    tables = sorted(
        t.model.__tablename__ for t in TARGETS if t.data_class == "login_state"
    )
    assert tables == ["auth_sessions", "login_challenges"]


def test_batch_item_text_clears_and_never_deletes():
    """The org's record of what it screened outlives the text it screened --
    the same reasoning as batch_items.candidate_id being SET NULL."""
    t = next(t for t in TARGETS if t.data_class == "batch_item_text")
    assert t.mode is SweepMode.CLEAR
    assert t.clear_column == "raw_text"
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_retention_plan.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retention'`.

- [ ] **Step 3: Add the two new knobs**

In `app/core/config.py`, beside the other `ret_*` fields (after `ret_batch_item_days`):

```python
    # S8.3 Phase B. Both are SHORT windows on pseudonymous operational rows.
    # A rate-limit counter holds a salted hash of an email beside one of an IP:
    # that is personal data, not bookkeeping, and it has no value once its
    # window has closed. `login_state` is abandoned login challenges and
    # sessions that expired without a logout -- neither is ever consumed, so
    # without a sweep they live forever.
    ret_rate_limit_days: int = Field(default=7, ge=1)
    ret_login_state_days: int = Field(default=7, ge=1)
```

In `config.yaml`, append a new block after the rate-limiting block:

```yaml
# --- Retention sweep (PI-8, S8.3 Phase B) -------------------------------------
# The eight windows above stopped being posture-only in this sprint. The sweep's
# targets are DERIVED from app/portal/retention.py's RETENTION_KNOBS -- the same
# table the candidate portal prints -- so a promise and its enforcement cannot
# drift apart silently.
ret_rate_limit_days: 7                  # hashed email + hashed IP; short on purpose
ret_login_state_days: 7                 # expired challenges + expired sessions
```

- [ ] **Step 4: Grow `RETENTION_KNOBS` to eleven**

In `app/portal/retention.py`, replace the module docstring's second sentence and the
table:

```python
"""Pure retention-posture helpers (S6.4, mechanised in S8.3 Phase B). No I/O.

RETENTION_KNOBS is the SINGLE source of the retention promise: the portal prints
it, and since S8.3 Phase B `app/retention/plan.py` derives the sweeper's targets
from it. A sweeper carrying its own list would let the two drift, and the drift
is silent in the worst direction -- the portal would keep promising a window
that nothing enforces.
"""

# data_class -> Settings attribute holding its TTL in days.
RETENTION_KNOBS: dict[str, str] = {
    "resumes": "ret_resume_days",
    "profile_sources": "ret_profile_source_days",
    "verifications": "ret_verification_days",
    "interviews": "ret_interview_session_days",
    "interview_records": "ret_interview_record_days",
    "coding_rounds": "ret_coding_round_days",
    "observed_offers": "ret_observed_offer_days",
    "audit_log": "ret_audit_log_days",
    # S8.3 Phase B. Disclosed because they are enforced: a window we sweep and
    # do not print is the mirror image of the bug this sprint fixes.
    "batch_item_text": "ret_batch_item_days",
    "rate_limit_counters": "ret_rate_limit_days",
    "login_state": "ret_login_state_days",
}
```

- [ ] **Step 5: Write `app/retention/plan.py`**

```python
"""Sweep targets, derived from the portal's own retention table (S8.3 Phase B).

There is no second list of what to delete. `TARGETS` names a model and a column
per data class in RETENTION_KNOBS, and tests/test_retention_plan.py asserts set
equality in both directions -- the metadata-drift-guard family that already
caught a real migration-vs-ORM drift in S7.1.

ELEVEN CLASSES, TWELVE TARGETS: `login_state` covers two tables, because an
abandoned login challenge and a session that expired without a logout are the
same fact to the person they describe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from app.auth.models import AuthSessionRow, LoginChallengeRow
from app.candidates.models import ResumeRow
from app.core.config import Settings
from app.interview.models import InterviewSessionRow
from app.ledger.models import (
    AuditLogRow, CodingRoundResultRow, InterviewRecordRow, ObservedOfferRow,
)
from app.profile_sources.models import ProfileSourceRow
from app.ratelimit.models import RateLimitCounterRow
from app.screening.models import BatchItemRow
from app.verification.models import VerificationRow


class SweepMode(StrEnum):
    """DELETE removes the row. CLEAR blanks one column and KEEPS it."""

    DELETE = "delete"
    CLEAR = "clear"


@dataclass(frozen=True)
class SweepTarget:
    data_class: str
    knob: str
    model: type
    timestamp_column: str
    mode: SweepMode
    #: CLEAR only. The column blanked, and the column whose non-emptiness is the
    #: eligibility predicate -- without it a preview reports the same already
    #: cleared rows every day forever.
    clear_column: Optional[str] = None


TARGETS: tuple[SweepTarget, ...] = (
    SweepTarget("resumes", "ret_resume_days", ResumeRow, "created_at", SweepMode.DELETE),
    SweepTarget("profile_sources", "ret_profile_source_days", ProfileSourceRow,
                "created_at", SweepMode.DELETE),
    SweepTarget("verifications", "ret_verification_days", VerificationRow,
                "created_at", SweepMode.DELETE),
    SweepTarget("interviews", "ret_interview_session_days", InterviewSessionRow,
                "created_at", SweepMode.DELETE),
    SweepTarget("interview_records", "ret_interview_record_days", InterviewRecordRow,
                "created_at", SweepMode.DELETE),
    SweepTarget("coding_rounds", "ret_coding_round_days", CodingRoundResultRow,
                "created_at", SweepMode.DELETE),
    SweepTarget("observed_offers", "ret_observed_offer_days", ObservedOfferRow,
                "created_at", SweepMode.DELETE),
    SweepTarget("audit_log", "ret_audit_log_days", AuditLogRow,
                "created_at", SweepMode.DELETE),
    # The row SURVIVES: an organisation's record of what it screened must
    # outlive the text it screened, exactly as batch_items.candidate_id is SET
    # NULL rather than cascading. This is also where Phase A and Phase B meet --
    # after ret_batch_item_days a failed item is no longer retryable, because
    # its input is gone (SCREENING.md §7, OPERATING.md §6).
    SweepTarget("batch_item_text", "ret_batch_item_days", BatchItemRow,
                "created_at", SweepMode.CLEAR, clear_column="raw_text"),
    # Keyed on expires_at, not created_at: the row's own declared end of life is
    # the honest start of its retention window.
    SweepTarget("rate_limit_counters", "ret_rate_limit_days", RateLimitCounterRow,
                "expires_at", SweepMode.DELETE),
    SweepTarget("login_state", "ret_login_state_days", LoginChallengeRow,
                "expires_at", SweepMode.DELETE),
    SweepTarget("login_state", "ret_login_state_days", AuthSessionRow,
                "expires_at", SweepMode.DELETE),
)


def data_classes() -> set[str]:
    return {t.data_class for t in TARGETS}


def ttl_days(target: SweepTarget, settings: Settings) -> int:
    return int(getattr(settings, target.knob))
```

Verify the ORM class names before running — if any import name differs (e.g. the
ledger rows), read the module and use the real name rather than renaming the model.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_retention_plan.py tests/test_portal_retention.py tests/test_config.py -q`
Expected: PASS. `test_portal_retention.py` must pass **unedited** — it compares against
`set(RETENTION_KNOBS)`, which is the point of that assertion.

- [ ] **Step 7: Full suite, then commit**

Run: `python -m pytest -q` → 1689 + new, all passing.

```bash
git add app/retention app/portal/retention.py app/core/config.py config.yaml tests/test_retention_plan.py
git commit -m "feat(s83b): sweep targets derived from the portal's own retention table"
```

---

## Task 2: `run_sweep` — delete mode, dry-run parity, and a real cascade

**Files:**
- Create: `app/retention/schema.py`, `app/retention/sweep.py`
- Test: `tests/test_retention_sweep.py`

**Interfaces:**
- Consumes: `TARGETS`, `SweepMode`, `ttl_days` from Task 1
- Produces:
  - `ClassSweepResult(BaseModel)`: `data_class: str`, `affected: int`, `truncated: bool`
  - `SweepReport(BaseModel)`: `by_class: list[ClassSweepResult]`, `dry_run: bool`,
    `truncated: bool`, `at: datetime`
  - `run_sweep(session_factory, settings, *, now: datetime, dry_run: bool, metrics=None) -> SweepReport`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retention_sweep.py
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.retention.sweep import run_sweep

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _settings(**over):
    return Settings(_env_file=None, openrouter_api_key="", **over)


def _seed_resume(session_factory, *, age_days: int) -> tuple[str, str]:
    """One candidate + one resume + one extraction, aged by `age_days`."""
    when = NOW - timedelta(days=age_days)
    with session_factory() as s:
        cand = CandidateRow(full_name="Asha R")
        s.add(cand)
        s.flush()
        resume = ResumeRow(
            candidate_id=cand.id, version=1, raw_text="x", text_sha256="a" * 64,
            created_at=when,
        )
        s.add(resume)
        s.flush()
        s.add(ExtractionRow(
            resume_id=resume.id, candidate_id=cand.id, method="heuristic",
            profile={}, warnings=[], created_at=when,
        ))
        s.commit()
        return resume.id, cand.id


def test_dry_run_counts_and_deletes_nothing(session_factory):
    _seed_resume(session_factory, age_days=2000)   # older than ret_resume_days (1095)
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    resumes = next(c for c in report.by_class if c.data_class == "resumes")
    assert resumes.affected == 1
    assert report.dry_run is True
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 1


def test_a_real_run_deletes_exactly_what_the_dry_run_counted(session_factory):
    """DRY-RUN PARITY. A preview that disagrees with the action is worse than
    no preview: it is the reason an operator trusts the destructive call."""
    _seed_resume(session_factory, age_days=2000)
    preview = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    real = run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    assert [(c.data_class, c.affected) for c in preview.by_class] == \
           [(c.data_class, c.affected) for c in real.by_class]
    with session_factory() as s:
        assert s.execute(select(ResumeRow)).scalars().all() == []


def test_rows_inside_the_window_survive(session_factory):
    _seed_resume(session_factory, age_days=10)
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 1


def test_the_delete_cascades_at_the_DATABASE(session_factory):
    """MEASURED, not assumed. A bulk DELETE bypasses SQLAlchemy's ORM-level
    cascade -- what carries it is the FK's ON DELETE CASCADE plus
    PRAGMA foreign_keys=ON from app/core/db.py. If either were absent this
    sweep would leave an orphaned extraction holding the very text the resume
    row was deleted to remove."""
    _seed_resume(session_factory, age_days=2000)
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert s.execute(select(ExtractionRow)).scalars().all() == []


def test_the_cap_bounds_one_invocation_and_the_report_says_so(session_factory):
    for _ in range(4):
        _seed_resume(session_factory, age_days=2000)
    settings = _settings(sweep_max_rows_per_class=2)
    report = run_sweep(session_factory, settings, now=NOW, dry_run=False)
    resumes = next(c for c in report.by_class if c.data_class == "resumes")
    assert resumes.affected == 2
    assert resumes.truncated is True
    assert report.truncated is True          # any class truncated
    with session_factory() as s:
        assert len(s.execute(select(ResumeRow)).scalars().all()) == 2


def test_a_clean_database_reports_zero_everywhere_and_is_not_truncated(session_factory):
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    assert all(c.affected == 0 for c in report.by_class)
    assert report.truncated is False
    assert {c.data_class for c in report.by_class} == {
        "resumes", "profile_sources", "verifications", "interviews",
        "interview_records", "coding_rounds", "observed_offers", "audit_log",
        "batch_item_text", "rate_limit_counters", "login_state",
    }
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_retention_sweep.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retention.sweep'`.

- [ ] **Step 3: Add `sweep_max_rows_per_class`**

`app/core/config.py`, beside the Task 1 knobs:

```python
    # Bounds ONE invocation per class so the sweep cannot hold locks for
    # minutes on a large table. The report carries truncated=true rather than
    # pretending it finished; the operator (or the cron) simply runs it again.
    sweep_max_rows_per_class: int = Field(default=10_000, ge=1)
```

`config.yaml`, in the Phase B block:

```yaml
sweep_max_rows_per_class: 10000         # one invocation's bound; report says truncated
```

- [ ] **Step 4: Write `app/retention/schema.py`**

```python
"""Retention sweep contracts (S8.3 Phase B). Pure Pydantic -- no I/O."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ClassSweepResult(BaseModel):
    """What one data class contributed. `affected` is rows DELETED for a delete
    target and rows CLEARED for a clear target -- one number, because the
    operator's question is "how much moved", and the mode is a property of the
    class, printed in OPERATING.md rather than repeated per run."""

    data_class: str
    affected: int
    truncated: bool = False


class SweepReport(BaseModel):
    by_class: list[ClassSweepResult] = Field(default_factory=list)
    dry_run: bool
    #: True when ANY class hit its cap. Surfaced at the top level so a cron's
    #: log line does not have to walk the list to learn there is more to do.
    truncated: bool = False
    at: datetime
```

- [ ] **Step 5: Write `app/retention/sweep.py`**

```python
"""The retention sweep (S8.3 Phase B).

Pure orchestration over app/retention/plan.py: no HTTP vocabulary, no route, no
scheduler. There is still no worker anywhere in `app/` (measured again this
sprint), so this is an INVOCABLE thing -- an admin route and a `python -m`
entry point -- and never a daemon.

DRY-RUN PARITY IS THE DESIGN. `affected` is computed by the same COUNT in both
modes, and only the write is skipped. A preview that disagrees with the action
is worse than no preview, because the whole reason an operator trusts the
destructive call is that they read the safe one first.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.logging import get_logger
from app.retention.plan import TARGETS, SweepMode, SweepTarget, ttl_days
from app.retention.schema import ClassSweepResult, SweepReport

log = get_logger(__name__)


def _predicate(target: SweepTarget, cutoff: datetime):
    """Rows eligible for this target.

    The CLEAR arm carries a non-empty test as well as the age test, and that is
    not an optimisation: batch_items.raw_text is already "" on every successful
    item, so age alone would report the same rows as "cleared" every day
    forever -- a preview that lies in the direction of looking busy.
    """
    column = getattr(target.model, target.timestamp_column)
    condition = column.is_not(None) & (column < cutoff)
    if target.mode is SweepMode.CLEAR:
        cleared = getattr(target.model, target.clear_column)
        condition = condition & (cleared != "")
    return condition


def run_sweep(
    session_factory: sessionmaker,
    settings: Settings,
    *,
    now: datetime,
    dry_run: bool,
    metrics=None,
) -> SweepReport:
    cap = settings.sweep_max_rows_per_class
    totals: dict[str, int] = {}
    truncated_classes: set[str] = set()

    for target in TARGETS:
        cutoff = now - timedelta(days=ttl_days(target, settings))
        condition = _predicate(target, cutoff)
        with session_factory() as session:
            matched = session.scalar(
                select(func.count()).select_from(target.model).where(condition)
            ) or 0
            affected = min(matched, cap)
            if matched > cap:
                truncated_classes.add(target.data_class)
            if not dry_run and affected:
                # A subquery on the primary key, not an IN of 10k bound
                # parameters: dialect variable limits are not a thing to be
                # one deploy away from discovering.
                chosen = (
                    select(target.model.id)
                    .where(condition)
                    .order_by(getattr(target.model, target.timestamp_column))
                    .limit(cap)
                    .scalar_subquery()
                )
                if target.mode is SweepMode.DELETE:
                    statement = delete(target.model).where(
                        target.model.id.in_(chosen)
                    )
                else:
                    statement = (
                        update(target.model)
                        .where(target.model.id.in_(chosen))
                        .values(**{target.clear_column: ""})
                    )
                session.execute(
                    statement.execution_options(synchronize_session=False)
                )
                session.commit()
            totals[target.data_class] = totals.get(target.data_class, 0) + affected

    by_class = [
        ClassSweepResult(
            data_class=name,
            affected=count,
            truncated=name in truncated_classes,
        )
        for name, count in sorted(totals.items())
    ]
    report = SweepReport(
        by_class=by_class,
        dry_run=dry_run,
        truncated=bool(truncated_classes),
        at=now,
    )
    log.info(
        "retention_sweep",
        dry_run=dry_run,
        truncated=report.truncated,
        affected=sum(totals.values()),
    )
    return report
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_retention_sweep.py -q`
Expected: PASS, all seven.

If `test_the_delete_cascades_at_the_DATABASE` fails, do **not** reach for an ORM
loop — first check that the fixture engine went through `make_engine` (which is what
installs `PRAGMA foreign_keys=ON`). A raw `create_engine` in a test would produce
exactly this failure and would be the test's bug, not the sweeper's.

- [ ] **Step 7: Full suite, then commit**

```bash
git add app/retention/schema.py app/retention/sweep.py app/core/config.py config.yaml tests/test_retention_sweep.py
git commit -m "feat(s83b): run_sweep -- bounded, dry-run-faithful, cascading at the DB"
```

---

## Task 3: Clear mode, proven on the second run

**Files:**
- Test: `tests/test_retention_sweep.py` (append)

**Interfaces:**
- Consumes: `run_sweep` (Task 2). No production change is expected — this task exists
  to prove the CLEAR arm behaves, and to *find out* if it does not.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retention_sweep.py (append)
from app.screening.models import BatchItemRow, ScreeningBatchRow
from app.ledger.models import OrganizationRow


def _seed_batch_item(session_factory, *, age_days: int, text: str) -> str:
    when = NOW - timedelta(days=age_days)
    with session_factory() as s:
        org = OrganizationRow(name=f"Agency {age_days}-{text[:3]}-{id(text)}")
        s.add(org)
        s.flush()
        batch = ScreeningBatchRow(org_id=org.id, created_at=when)
        s.add(batch)
        s.flush()
        item = BatchItemRow(
            batch_id=batch.id, status="failed", raw_text=text,
            text_sha256="b" * 64, created_at=when,
        )
        s.add(item)
        s.commit()
        return item.id


def test_clear_mode_blanks_the_text_and_KEEPS_the_row(session_factory):
    item_id = _seed_batch_item(session_factory, age_days=200, text="a resume")
    report = run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    cleared = next(c for c in report.by_class if c.data_class == "batch_item_text")
    assert cleared.affected == 1
    with session_factory() as s:
        row = s.get(BatchItemRow, item_id)
        assert row is not None, "the org's record of what it screened must survive"
        assert row.raw_text == ""
        assert row.status == "failed"       # the outcome is not rewritten


def test_a_second_sweep_reports_zero_rather_than_the_same_rows_again(session_factory):
    """The non-empty predicate, stated as behaviour. Without it a preview
    reports 'about to clear 1' every day forever on a row that is already
    blank -- and an operator who sees a number that never falls stops reading
    the number."""
    _seed_batch_item(session_factory, age_days=200, text="a resume")
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    second = run_sweep(session_factory, _settings(), now=NOW, dry_run=True)
    cleared = next(c for c in second.by_class if c.data_class == "batch_item_text")
    assert cleared.affected == 0


def test_a_recent_failed_item_keeps_its_text_so_retry_still_works(session_factory):
    """Phase A and Phase B meet here: retention BOUNDS the retry window, and
    inside the window the retry input must still be there."""
    item_id = _seed_batch_item(session_factory, age_days=5, text="a resume")
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False)
    with session_factory() as s:
        assert s.get(BatchItemRow, item_id).raw_text == "a resume"
```

- [ ] **Step 2: Run and record what happens**

Run: `python -m pytest tests/test_retention_sweep.py -q`

Expected: PASS if Task 2's CLEAR arm is right. **If any fails, that is a real defect
found by this task** — fix `app/retention/sweep.py`, not the test, and say so in the
commit message. Check the seeding first: `ScreeningBatchRow` / `BatchItemRow` column
names must match `app/screening/models.py` (read it), and `OrganizationRow.name` is
case-insensitively unique (`uq_organizations_name_ci`), so each seeded org needs a
distinct name.

- [ ] **Step 3: Commit**

```bash
git add tests/test_retention_sweep.py
git commit -m "test(s83b): clear mode keeps the row, and the second run reports zero"
```

---

## Task 4: `retention_deleted`, declared and incremented in ONE commit

**Files:**
- Modify: `app/metrics/registry.py`, `app/retention/sweep.py`, `tests/test_metrics.py`
- Test: `tests/test_retention_sweep.py` (append), `tests/test_metrics.py` (modify)

**Interfaces:**
- Produces: `Metrics.add(name: str, amount: int, **labels: str) -> None`;
  `increment` becomes `add(name, 1, **labels)`.

**Why this task is not folded into Task 2:** it is a rule with teeth.
`test_every_declared_metric_has_a_call_site` scans `app/` for `increment("<name>")`.
A counter incremented N-at-a-time wants `add(...)`, which that regex does **not**
match — so wiring the metric without widening the scanner would make the guard pass
by not looking. The scanner and the call site change together, here.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retention_sweep.py (append)
from app.metrics.registry import build_metrics


def test_a_real_sweep_counts_what_it_removed_per_data_class(session_factory):
    _seed_resume(session_factory, age_days=2000)
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False, metrics=metrics)
    snapshot = metrics.snapshot()
    key = ("retention_deleted", (("data_class", "resumes"),))
    assert snapshot.get(key) == 1


def test_a_dry_run_counts_NOTHING(session_factory):
    """A preview that moves the counter would make the runbook's 'how much have
    we deleted' unanswerable -- it would be counting intentions."""
    _seed_resume(session_factory, age_days=2000)
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=True, metrics=metrics)
    assert metrics.snapshot() == {}


def test_the_counter_carries_the_ROW_COUNT_not_one_per_class(session_factory):
    for _ in range(3):
        _seed_resume(session_factory, age_days=2000)
    metrics = build_metrics()
    run_sweep(session_factory, _settings(), now=NOW, dry_run=False, metrics=metrics)
    assert metrics.snapshot()[("retention_deleted", (("data_class", "resumes"),))] == 3
```

```python
# tests/test_metrics.py -- append beside the existing registry tests
def test_add_accumulates_and_increment_is_add_of_one():
    m = build_metrics()
    m.add("retention_deleted", 5, data_class="resumes")
    m.increment("retention_deleted", data_class="resumes")
    assert m.snapshot()[("retention_deleted", (("data_class", "resumes"),))] == 6


def test_the_call_site_scanner_sees_add_as_well_as_increment():
    """The scanner is the guard on _HELP. A counter that moves N at a time is
    written `add(...)`, so a scanner that only knows `increment(` would call a
    declared-inert `retention_deleted` clean -- passing by not looking, which
    is the exact failure this guard exists to prevent."""
    assert "retention_deleted" in _incremented_names()
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_retention_sweep.py tests/test_metrics.py -q`
Expected: FAIL — `AttributeError: 'Metrics' object has no attribute 'add'`, and the
scanner test failing on `retention_deleted`.

- [ ] **Step 3: Add `Metrics.add`**

In `app/metrics/registry.py`, replace `increment` with:

```python
    def add(self, name: str, amount: int, **labels: str) -> None:
        """Move a counter by `amount`. Counters only ever go up, so a negative
        amount is a caller bug and is refused rather than quietly reversing a
        series a scraper has already read as monotonic."""
        if amount < 0:
            raise ValueError("a counter cannot decrease")
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self._lock:
            self._counters[key] += amount

    def increment(self, name: str, **labels: str) -> None:
        self.add(name, 1, **labels)
```

And declare the metric in `_HELP` (same commit as its call site, per the comment
already in that file):

```python
    "retention_deleted": (
        "Rows deleted or cleared by the retention sweep, by data class."
    ),
```

- [ ] **Step 4: Widen the scanner in `tests/test_metrics.py`**

Find `_incremented_names()` and make its regex match both call spellings — read the
existing implementation and extend the pattern to `(?:increment|add)\(\s*"([a-z_]+)"`.
Leave `test_the_call_site_scanner_can_actually_find_something` unchanged; it still
proves the scanner finds something.

- [ ] **Step 5: Count in `run_sweep`**

In `app/retention/sweep.py`, inside the `if not dry_run and affected:` block, after
`session.commit()`:

```python
                if metrics is not None:
                    # AFTER the commit, and only on a real run: a preview that
                    # moved this counter would be counting intentions.
                    metrics.add(
                        "retention_deleted", affected, data_class=target.data_class
                    )
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_retention_sweep.py tests/test_metrics.py -q`
Expected: PASS.

- [ ] **Step 7: Full suite, then commit**

```bash
git add app/metrics/registry.py app/retention/sweep.py tests/test_metrics.py tests/test_retention_sweep.py
git commit -m "feat(s83b): retention_deleted -- declared, incremented and scanned in one commit"
```

---

## Task 5: `sweep_active` stops being a literal

**Files:**
- Modify: `app/portal/retention.py`, `app/core/config.py`, `config.yaml`,
  `tests/test_portal_retention.py`, `tests/test_portal_schema.py`,
  `tests/test_portal_service.py`, `tests/test_portal_api.py`,
  `tests/test_interview_org_api.py`

**Interfaces:**
- Consumes: `Settings.retention_sweep_enabled` (new)
- Produces: `build_retention_policy` returns `sweep_active=settings.retention_sweep_enabled`

**This is the point of Phase B.** Right now the portal tells every data principal
that no mechanical purge runs. That sentence has to become true in the other
direction — and *derived*, because a second hardcoded literal is a promise that goes
stale the day the operator flips the config.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portal_retention.py (append)
def test_sweep_active_is_DERIVED_from_the_config_not_a_literal():
    """A second hardcoded literal is a promise that goes stale the day an
    operator flips the knob -- and it goes stale in the direction of telling a
    data principal that nothing is deleted while the cron deletes."""
    on = build_retention_policy({}, _settings())
    off = build_retention_policy(
        {}, Settings(_env_file=None, openrouter_api_key="",
                     retention_sweep_enabled=False)
    )
    assert on.sweep_active is True          # config.yaml ships it enabled
    assert off.sweep_active is False
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_portal_retention.py -q`
Expected: FAIL — `assert False is True`, because line 50 returns the literal.

- [ ] **Step 3: Add the knob**

`app/core/config.py`, with the other Phase B knobs:

```python
    # Flipped to True in S8.3 Phase B, because the job it was waiting for now
    # exists. This is what /portal/me reports as `sweep_active`, so it must
    # never be read from a literal: the portal would keep saying "no mechanical
    # purge runs" while the cron ran one.
    retention_sweep_enabled: bool = True
```

`config.yaml`, in the Phase B block:

```yaml
retention_sweep_enabled: true           # the job now exists; /portal/me reports this
```

- [ ] **Step 4: Derive it**

`app/portal/retention.py`, last line of `build_retention_policy`:

```python
    return RetentionPolicy(
        windows=windows, sweep_active=settings.retention_sweep_enabled
    )
```

And in `app/portal/schema.py`, correct the now-false comment on the field:

```python
class RetentionPolicy(BaseModel):
    windows: list[RetentionWindow] = Field(default_factory=list)
    #: Does a mechanical purge actually run? DERIVED from
    #: settings.retention_sweep_enabled since S8.3 Phase B -- the default below
    #: is the safe answer for a policy built without settings, never the answer
    #: the portal gives.
    sweep_active: bool = False
```

- [ ] **Step 5: Update the five call sites that asserted `False`**

These are not breakage; they are the assertion changing meaning. Update each to
`is True` and leave a short comment saying the sweep exists now:

- `tests/test_portal_retention.py:29`
- `tests/test_portal_schema.py:14` — this one builds a bare `RetentionPolicy()` with
  no settings, so it keeps `is False` (the model default). **Read it before editing**:
  if it constructs the model directly, leave it alone and note why in the commit.
- `tests/test_portal_service.py:38`
- `tests/test_portal_api.py:45`
- `tests/test_interview_org_api.py:139`

- [ ] **Step 6: Run the suite**

Run: `python -m pytest -q`
Expected: PASS. Any *other* test asserting `sweep_active` false is a site this step
missed — fix it the same way.

- [ ] **Step 7: Commit**

```bash
git add app/portal/retention.py app/portal/schema.py app/core/config.py config.yaml tests/
git commit -m "feat(s83b): sweep_active is derived, so the portal stops promising the opposite"
```

---

## Task 6: `POST /admin/retention/sweep`

**Files:**
- Modify: `app/api/routes.py`, `app/services/__init__.py`
- Test: `tests/test_retention_api.py`

**Interfaces:**
- Consumes: `run_sweep`, `SweepReport`
- Produces: route `POST /admin/retention/sweep`, body `SweepRequest{dry_run: bool = True}`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retention_api.py
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_the_sweep_requires_the_admin_credential(client):
    assert client.post("/admin/retention/sweep", json={}).status_code == 401


def test_an_empty_body_is_a_DRY_RUN(client, admin_headers):
    """The most destructive operation in the repo must not delete because
    somebody posted an empty body. A cron passes {"dry_run": false} on purpose,
    which is one word of evidence that somebody meant it."""
    r = client.post("/admin/retention/sweep", json={}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


def test_the_report_names_every_data_class(client, admin_headers):
    body = client.post("/admin/retention/sweep", json={}, headers=admin_headers).json()
    assert {c["data_class"] for c in body["by_class"]} == {
        "resumes", "profile_sources", "verifications", "interviews",
        "interview_records", "coding_rounds", "observed_offers", "audit_log",
        "batch_item_text", "rate_limit_counters", "login_state",
    }
    assert body["truncated"] is False
    assert "at" in body


def test_a_real_run_is_refused_409_when_the_sweep_is_disabled(services, admin_headers):
    services.settings.retention_sweep_enabled = False
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.post("/admin/retention/sweep", json={"dry_run": False},
                   headers=admin_headers)
        assert r.status_code == 409
        assert r.json()["detail"] == "retention_sweep_disabled"


def test_a_DRY_RUN_still_works_when_the_sweep_is_disabled(services, admin_headers):
    """A count is safe, and it is the operator's only way to see what WOULD go
    before they turn the knob on."""
    services.settings.retention_sweep_enabled = False
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.post("/admin/retention/sweep", json={}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["dry_run"] is True
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_retention_api.py -q`
Expected: FAIL — 404 on every call (the route does not exist).

- [ ] **Step 3: Add the route**

In `app/api/routes.py`, beside the other admin routes (near `GET /metrics`):

```python
class SweepRequest(BaseModel):
    """`dry_run` DEFAULTS TO TRUE. This is the most destructive call in the
    repo, and defaulting it the other way would make an empty body -- the
    easiest thing to send by accident -- delete production data."""

    dry_run: bool = True


@router.post("/admin/retention/sweep", response_model=SweepReport)
async def retention_sweep(req: SweepRequest, request: Request) -> SweepReport:
    services = _services(request)
    if not req.dry_run and not services.settings.retention_sweep_enabled:
        # 409, not 403: the configuration is the thing in the wrong state, and
        # the operator's fix is a knob rather than a credential. The dry run is
        # still allowed above, because a count is safe.
        raise HTTPException(status_code=409, detail="retention_sweep_disabled")
    return run_sweep(
        services.candidates._session_factory,
        services.settings,
        now=datetime.now(timezone.utc),
        dry_run=req.dry_run,
        metrics=services.metrics,
    )
```

Import `run_sweep` and `SweepReport` at the top of the module beside the other app
imports. Use whichever session factory the container already exposes for the main
database — check how `build_rate_limiter` is handed one in
`app/screening/service.py:322` and follow the same source rather than opening a
second engine.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_retention_api.py tests/test_route_table_guard.py tests/test_openapi_contract.py -q`
Expected: PASS. The route-table and OpenAPI guards must cover the new route **with no
edit** — it is on `router`, so `require_api_key` is inherited, and it declares a
`response_model`. If either guard fails, the route is in the wrong place; move it
rather than exempting it.

- [ ] **Step 5: Full suite, then commit**

```bash
git add app/api/routes.py tests/test_retention_api.py
git commit -m "feat(s83b): POST /admin/retention/sweep, dry by default, 409 when disabled"
```

---

## Task 7: `python -m app.retention.sweep`

**Files:**
- Modify: `app/retention/sweep.py`
- Test: `tests/test_retention_api.py` (append)

**Interfaces:**
- Produces: `main(argv: Optional[list[str]] = None) -> int` in `app/retention/sweep.py`,
  plus an `if __name__ == "__main__":` guard.

There is no scheduler in `app/`, so the CLI is how a Railway cron or an operator shell
invokes this. It shares `run_sweep` with the route — one door, two callers.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_retention_api.py (append)
import json

from app.retention.sweep import main


def test_the_cli_defaults_to_a_dry_run_and_prints_the_report(capsys, monkeypatch,
                                                             tmp_path):
    monkeypatch.setenv("DEE_CANDIDATES_DB_URL", f"sqlite:///{tmp_path}/cli.db")
    monkeypatch.setenv("DEE_API_AUTH_KEY", "k" * 32)
    assert main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["dry_run"] is True


def test_the_cli_needs_an_explicit_flag_to_delete(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DEE_CANDIDATES_DB_URL", f"sqlite:///{tmp_path}/cli2.db")
    monkeypatch.setenv("DEE_API_AUTH_KEY", "k" * 32)
    assert main(["--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False


def test_the_cli_refuses_to_apply_when_the_sweep_is_disabled(capsys, monkeypatch,
                                                             tmp_path):
    """The same refusal as the route's 409, at the second door -- a rule
    enforced at one entry point and not the other is this repo's signature
    defect."""
    monkeypatch.setenv("DEE_CANDIDATES_DB_URL", f"sqlite:///{tmp_path}/cli3.db")
    monkeypatch.setenv("DEE_API_AUTH_KEY", "k" * 32)
    monkeypatch.setenv("DEE_RETENTION_SWEEP_ENABLED", "false")
    assert main(["--apply"]) == 2
    assert "retention_sweep_disabled" in capsys.readouterr().err
```

Before writing these, confirm the env-var prefix and how `get_settings()` is cached —
if `get_settings` is `lru_cache`d, the test must clear it (`get_settings.cache_clear()`)
after `monkeypatch.setenv`. Read `app/core/config.py` and do whatever the existing
config tests do.

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_retention_api.py -q`
Expected: FAIL — `ImportError: cannot import name 'main'`.

- [ ] **Step 3: Write the CLI**

Append to `app/retention/sweep.py`:

```python
def main(argv: Optional[list[str]] = None) -> int:
    """`python -m app.retention.sweep [--apply]`.

    A CLI and a route, because there is no scheduler: this is the entry point a
    Railway cron or an operator shell uses. Both go through `run_sweep`, so the
    disabled-config refusal cannot be enforced at one door and forgotten at the
    other.
    """
    import argparse
    import json
    import sys
    from datetime import timezone

    from app.core.config import get_settings
    from app.core.db import make_engine, make_session_factory

    parser = argparse.ArgumentParser(prog="app.retention.sweep")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete. Without it this is a dry run, deliberately.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.apply and not settings.retention_sweep_enabled:
        print("retention_sweep_disabled", file=sys.stderr)
        return 2

    factory = make_session_factory(make_engine(settings.candidates_db_url))
    report = run_sweep(
        factory,
        settings,
        now=datetime.now(timezone.utc),
        dry_run=not args.apply,
    )
    print(json.dumps(report.model_dump(mode="json")))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
```

Add `from datetime import datetime, timedelta, timezone` to the module's imports and
drop the function-local `timezone` import if it is then redundant.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_retention_api.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, then commit**

```bash
git add app/retention/sweep.py tests/test_retention_api.py
git commit -m "feat(s83b): python -m app.retention.sweep, sharing the route's one door"
```

---

## Task 8: `data_principal_requests` — schema, model, migration 0022

**Files:**
- Create: `app/rights/__init__.py`, `app/rights/schema.py`, `app/rights/models.py`,
  `alembic/versions/0022_data_principal_requests.py`
- Test: `tests/test_rights_schema.py`

**Interfaces:**
- Produces:
  - `RequestKind` (StrEnum): `CORRECTION`, `GRIEVANCE`
  - `RequestStatus` (StrEnum): `OPEN`, `RESOLVED`, `REJECTED`
  - `CorrectionField` (StrEnum): `FULL_NAME`, `EMAIL`, `PHONE`, `OTHER`
  - `ResolvedBy` (StrEnum): `OPERATOR_KEY`, `ADMIN_USER`
  - `RequestRefused(Exception)`, `RequestAlreadyResolved(RequestRefused)`
  - `RequestView(BaseModel)`: `id`, `kind`, `status`, `applied`, `field`,
    `current_value`, `requested_value`, `note`, `created_at`, `resolved_at`,
    `resolution`, `resolved_by`
  - `AUTO_APPLIABLE_FIELDS: frozenset[CorrectionField]` — `{FULL_NAME}` and nothing else
  - `DataPrincipalRequestRow` (ORM)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rights_schema.py
from app.rights.schema import (
    AUTO_APPLIABLE_FIELDS, CorrectionField, RequestKind, RequestStatus, ResolvedBy,
)


def test_only_full_name_is_auto_appliable():
    """email and phone are hashed into the dedup keys _resolve_candidate matches
    on, and email_hash is additionally the portal login credential. Changing
    either is an IDENTITY operation that can collide two candidate rows or move
    an account's login address -- not a data correction."""
    assert AUTO_APPLIABLE_FIELDS == frozenset({CorrectionField.FULL_NAME})


def test_the_four_correction_fields_are_named():
    assert {f.value for f in CorrectionField} == {
        "full_name", "email", "phone", "other"
    }


def test_status_and_applied_are_two_facts_so_status_has_only_three_members():
    """A four-member enum folding 'applied' in would leave 'is an applied
    correction also resolved?' answerable two ways, and the subject's own view
    of their request is the last place to be vague about whether anything
    changed."""
    assert {s.value for s in RequestStatus} == {"open", "resolved", "rejected"}


def test_resolution_authorship_distinguishes_a_machine_key_from_a_person():
    """The S8.5 `recorded_by` argument, one table over: a null admin_user_id
    would conflate 'an operator using the shared key decided this' with 'the
    admin who decided it has since been deleted'."""
    assert {r.value for r in ResolvedBy} == {"operator_key", "admin_user"}


def test_both_kinds_exist():
    assert {k.value for k in RequestKind} == {"correction", "grievance"}
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_rights_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rights'`.

- [ ] **Step 3: Write `app/rights/schema.py`**

```python
"""DPDP rights contracts (S8.3 Phase B). Pure Pydantic + StrEnum -- no I/O.

A correction is a REVIEWED REQUEST, never a self-service edit (spec 0.3). On a
fraud-screening platform, giving the subject a write path onto the data the risk
score is computed from is giving them an edit box over the evidence. DPDP
permits the fiduciary to verify before correcting; what must exist is the
MECHANISM -- request, review, decide, record, disclose -- and it exists here for
all four fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel


class RequestKind(StrEnum):
    CORRECTION = "correction"
    GRIEVANCE = "grievance"


class RequestStatus(StrEnum):
    """What the OPERATOR decided. Whether stored data changed is `applied`, a
    separate column: false for every grievance, false for a resolved `email`
    correction handled out of band, true only when a value was written."""

    OPEN = "open"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class CorrectionField(StrEnum):
    FULL_NAME = "full_name"
    EMAIL = "email"
    PHONE = "phone"
    OTHER = "other"


class ResolvedBy(StrEnum):
    OPERATOR_KEY = "operator_key"
    ADMIN_USER = "admin_user"


#: The ONLY field a resolution may write automatically. `full_name` is a plain
#: column with no identity semantics; `email`/`phone` are hashed into the dedup
#: keys and the portal login credential, and `other` is free text nobody can map
#: to a column. The refusal names its own reason so nobody has to remember it.
AUTO_APPLIABLE_FIELDS: frozenset[CorrectionField] = frozenset({CorrectionField.FULL_NAME})


class RequestRefused(Exception):
    """The request or the resolution is not permissible. Carries the reason,
    because a refusal a subject cannot act on is not a mechanism."""


class RequestAlreadyResolved(RequestRefused):
    """A second decision on a request that already has one.

    Its own type, not a message: the HTTP layer answers 409 here and 422 for
    every other refusal, and choosing between them by matching on message text
    is a translation that breaks the first time somebody rewords a sentence.
    """


class RequestView(BaseModel):
    """One request as its subject sees it -- and as the operator lists it.
    ONE shape for both planes: the operator's view of a person's complaint
    should not be able to drift from what that person is shown.

    `resolved_by` names the KIND of decider, never the person: 'a platform
    operator decided this' is what the subject is owed, and an admin's identity
    is not theirs to have.
    """

    id: str
    kind: RequestKind
    status: RequestStatus
    applied: bool = False
    field: Optional[CorrectionField] = None
    #: What the row said WHEN THE REQUEST WAS FILED. The operator reviews the
    #: pair the subject actually saw, not whatever the row says by the time
    #: somebody gets to it.
    current_value: str = ""
    requested_value: str = ""
    note: str = ""
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution: str = ""
    resolved_by: Optional[ResolvedBy] = None


class GrievanceContact(BaseModel):
    """The published grievance mechanism. DPDP requires it to be PUBLISHED, so
    GET /grievance is in PUBLIC_PATHS: a contact reachable only after login is
    not reachable by someone whose complaint is that they cannot log in."""

    name: str = ""
    email: str = ""
    phone: str = ""
    response_days: int = 30
```

Stop at the types. `build_grievance_contact()` reads four settings that do not exist
until Task 14 and is written there, beside its knobs — a helper shipped ahead of the
config it reads is an `AttributeError` waiting for its first caller.

- [ ] **Step 4: Write `app/rights/models.py`**

```python
"""ORM row for the DPDP request queue (S8.3 Phase B). Postgres-shaped on SQLite.

`candidate_id` CASCADES, and the contrast with S8.5's `outcomes.org_id` (SET
NULL) is the reasoning: an outcome is a label the PLATFORM learns from and
outlives the org that recorded it, while a correction request is wholly the
subject's own. Erasure is the stronger right, and a request about a person who
no longer exists is personal data with no subject.

`status` and `applied` are TWO FACTS. `status` is what the operator decided;
`applied` is whether that decision changed stored data. Collapsing them into one
four-member enum would leave "is an applied correction also resolved?"
answerable two ways.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataPrincipalRequestRow(Base):
    __tablename__ = "data_principal_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    #: Did the resolution WRITE anything? Never true for a grievance.
    applied: Mapped[bool] = mapped_column(Boolean, default=False)

    field: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    current_value: Mapped[str] = mapped_column(Text, default="")
    requested_value: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution: Mapped[str] = mapped_column(Text, default="")
    #: WHO decided, in two columns for the S8.5 reason: a null FK alone would
    #: conflate "an operator used the shared machine key" with "the admin who
    #: decided this has since been deleted". NO server default -- a writer that
    #: forgets to say must fail loudly, which is exactly what caught the third
    #: writer to `outcomes` in S8.5.
    resolved_by: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    resolved_by_admin_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 5: Write the migration**

`alembic/versions/0022_data_principal_requests.py`, `down_revision = "0021_rate_limit_counters"`.
Mirror `0021`'s docstring style: say *why* `candidate_id` cascades and why `status`
and `applied` are separate columns. Create the table with the six indexed columns
above (`candidate_id`, `kind`, `status`, `created_at`), and drop them in `downgrade`.

- [ ] **Step 6: Register the model so `Base.metadata` sees it**

Check how other model modules get imported for `Base.metadata.create_all` (grep for
where `app.ratelimit.models` is imported — likely `app/core/migrate.py`, `alembic/env.py`
or a package `__init__`). Add `app.rights.models` the same way. `tests/test_migrations.py`
compares the migrated schema to the ORM metadata and will fail loudly if you skip this.

- [ ] **Step 7: Run**

Run: `python -m pytest tests/test_rights_schema.py tests/test_migrations.py -q`
Expected: PASS. (OneDrive trap: if pytest reports
`ImportError: cannot import name 'command' from 'alembic'`, wait for the new file to
sync and re-run — it is the write, not the content.)

- [ ] **Step 8: Full suite, then commit**

```bash
git add app/rights alembic/versions/0022_data_principal_requests.py tests/test_rights_schema.py
git commit -m "feat(s83b): the data-principal request queue's table, types and migration"
```

---

## Task 9: `RightsStore`

**Files:**
- Create: `app/rights/store.py`
- Test: `tests/test_rights_store.py`

**Interfaces:**
- Produces `RightsStore(session_factory)` with:
  - `create(candidate_id, *, kind, field, current_value, requested_value, note) -> RequestView`
  - `for_candidate(candidate_id) -> list[RequestView]` (newest first)
  - `get(request_id) -> Optional[tuple[RequestView, str]]` — the view and its `candidate_id`
  - `list_by_status(status: Optional[RequestStatus], limit: int) -> list[RequestView]`
  - `resolve(request_id, *, status, resolution, applied, resolved_by, resolved_by_admin_user_id, now) -> bool`
  - `build_rights_store(settings=None, session_factory=None) -> RightsStore`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rights_store.py
from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.rights.schema import CorrectionField, RequestKind, RequestStatus, ResolvedBy
from app.rights.store import RightsStore

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


@pytest.fixture
def store():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return RightsStore(make_session_factory(engine))


def _candidate(store) -> str:
    with store._session_factory() as s:
        row = CandidateRow(full_name="Asha R")
        s.add(row)
        s.commit()
        return row.id


def test_a_new_request_is_open_and_unapplied(store):
    cid = _candidate(store)
    view = store.create(
        cid, kind=RequestKind.CORRECTION, field=CorrectionField.FULL_NAME,
        current_value="Asha R", requested_value="Asha Rao", note="",
    )
    assert view.status is RequestStatus.OPEN
    assert view.applied is False
    assert view.requested_value == "Asha Rao"


def test_a_candidate_sees_only_their_own(store):
    a, b = _candidate(store), _candidate(store)
    store.create(a, kind=RequestKind.GRIEVANCE, field=None, current_value="",
                 requested_value="", note="nobody answered")
    assert [v.note for v in store.for_candidate(a)] == ["nobody answered"]
    assert store.for_candidate(b) == []


def test_resolve_records_the_decision_the_authorship_and_the_time(store):
    cid = _candidate(store)
    view = store.create(cid, kind=RequestKind.CORRECTION,
                        field=CorrectionField.FULL_NAME, current_value="Asha R",
                        requested_value="Asha Rao", note="")
    assert store.resolve(
        view.id, status=RequestStatus.RESOLVED, resolution="name updated",
        applied=True, resolved_by=ResolvedBy.OPERATOR_KEY,
        resolved_by_admin_user_id=None, now=NOW,
    ) is True
    again = store.for_candidate(cid)[0]
    assert again.status is RequestStatus.RESOLVED
    assert again.applied is True
    assert again.resolution == "name updated"
    assert again.resolved_at == NOW


def test_resolving_an_already_resolved_request_is_refused_at_the_STORE(store):
    """The conditional UPDATE is the guard, not a read-then-write: two
    operators clicking Resolve on the same request must not both apply it, and
    an applied correction applied twice is a second write onto a person's row
    on the strength of one decision."""
    cid = _candidate(store)
    view = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                        current_value="", requested_value="", note="x")
    kwargs = dict(status=RequestStatus.RESOLVED, resolution="done", applied=False,
                  resolved_by=ResolvedBy.OPERATOR_KEY,
                  resolved_by_admin_user_id=None, now=NOW)
    assert store.resolve(view.id, **kwargs) is True
    assert store.resolve(view.id, **kwargs) is False


def test_resolving_an_unknown_id_is_False_not_an_exception(store):
    assert store.resolve(
        "nope", status=RequestStatus.RESOLVED, resolution="", applied=False,
        resolved_by=ResolvedBy.OPERATOR_KEY, resolved_by_admin_user_id=None, now=NOW,
    ) is False


def test_list_by_status_filters_and_None_means_all(store):
    cid = _candidate(store)
    open_one = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                            current_value="", requested_value="", note="a")
    closed = store.create(cid, kind=RequestKind.GRIEVANCE, field=None,
                          current_value="", requested_value="", note="b")
    store.resolve(closed.id, status=RequestStatus.REJECTED, resolution="no",
                  applied=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                  resolved_by_admin_user_id=None, now=NOW)
    assert [v.id for v in store.list_by_status(RequestStatus.OPEN, limit=50)] == [open_one.id]
    assert len(store.list_by_status(None, limit=50)) == 2


def test_erasing_the_candidate_takes_their_requests_with_them(store):
    """CASCADE, and the opposite call from S8.5's outcomes.org_id -- a
    correction request is wholly the subject's own."""
    cid = _candidate(store)
    store.create(cid, kind=RequestKind.GRIEVANCE, field=None, current_value="",
                 requested_value="", note="x")
    with store._session_factory() as s:
        s.delete(s.get(CandidateRow, cid))
        s.commit()
    assert store.for_candidate(cid) == []
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_rights_store.py -q`
Expected: FAIL — no module `app.rights.store`.

- [ ] **Step 3: Implement the store**

Follow `app/screening/store.py`'s shape: a `sessionmaker` in, detached Pydantic views
out, never an ORM row across the boundary. `resolve` must be a **conditional UPDATE**
whose `rowcount` is the decision:

```python
        result = session.execute(
            update(DataPrincipalRequestRow)
            .where(
                DataPrincipalRequestRow.id == request_id,
                # The guard: only an OPEN request may be resolved. Two
                # operators clicking at once must produce one decision, and a
                # read-then-write cannot promise that.
                DataPrincipalRequestRow.status == RequestStatus.OPEN.value,
            )
            .values(
                status=status.value,
                resolution=resolution,
                applied=applied,
                resolved_at=now,
                resolved_by=resolved_by.value,
                resolved_by_admin_user_id=resolved_by_admin_user_id,
            )
            .execution_options(synchronize_session=False)
        )
        session.commit()
        return result.rowcount == 1
```

`build_rights_store(settings=None, session_factory=None)` mirrors
`build_rate_limit_store` — take the session factory when the container has one and
only build an engine when it does not.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_rights_store.py -q`
Expected: PASS, all seven.

- [ ] **Step 5: Full suite, then commit**

```bash
git add app/rights/store.py tests/test_rights_store.py
git commit -m "feat(s83b): RightsStore -- one conditional UPDATE decides a resolution"
```

---

## Task 10: `RightsService` and `CandidateStore.apply_correction`

**Files:**
- Create: `app/rights/service.py`
- Modify: `app/candidates/store.py`
- Test: `tests/test_rights_service.py`

**Interfaces:**
- Consumes: `RightsStore`, `RateLimiter` + `RateLimited` (Phase A), `CandidateStore`,
  `LedgerStore`
- Produces: `RightsService(store, candidates, ledger, *, limiter, settings)` with
  - `submit(candidate_id, *, kind, field, requested_value, note, now) -> RequestView`
  - `for_candidate(candidate_id) -> list[RequestView]`
  - `list_by_status(status, limit) -> list[RequestView]`
  - `resolve(request_id, *, status, resolution, apply, resolved_by, admin_user_id, now) -> RequestView`
  - `build_rights_service(settings, *, store, candidates, ledger, limiter) -> RightsService`
- Produces: `CandidateStore.apply_correction(candidate_id, *, full_name) -> bool`

**The load-bearing rule of this phase (§8.2): a correction NEVER rewrites an
extraction.** An `extractions` row is a record of what a document said. The subject of
a correction request is exactly the person with an incentive to edit a claim that got
flagged. `apply_correction` touches `candidates.full_name` and nothing else.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rights_service.py
from datetime import datetime, timezone

import pytest

from app.ratelimit.service import RateLimited
from app.rights.schema import (
    CorrectionField, RequestKind, RequestRefused, RequestStatus, ResolvedBy,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def test_a_correction_requires_a_requested_value(rights, candidate_id):
    with pytest.raises(RequestRefused):
        rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                      field=CorrectionField.FULL_NAME, requested_value="  ",
                      note="", now=NOW)


def test_a_correction_requires_a_field(rights, candidate_id):
    with pytest.raises(RequestRefused):
        rights.submit(candidate_id, kind=RequestKind.CORRECTION, field=None,
                      requested_value="Asha Rao", note="", now=NOW)


def test_the_field_other_requires_a_note(rights, candidate_id):
    with pytest.raises(RequestRefused):
        rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                      field=CorrectionField.OTHER, requested_value="x", note="",
                      now=NOW)


def test_a_grievance_requires_a_note_and_carries_no_field(rights, candidate_id):
    with pytest.raises(RequestRefused):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="", note="", now=NOW)
    view = rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                         requested_value="", note="nobody replied", now=NOW)
    assert view.field is None


def test_the_note_is_bounded_by_max_request_note_chars(rights, candidate_id, settings):
    """The S8.5 argument one table over: free text typed by a person about
    their own record, into an unbounded Text column, is unbounded input."""
    with pytest.raises(RequestRefused):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="",
                      note="x" * (settings.max_request_note_chars + 1), now=NOW)


def test_the_requested_value_is_bounded_too(rights, candidate_id, settings):
    with pytest.raises(RequestRefused):
        rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                      field=CorrectionField.FULL_NAME,
                      requested_value="x" * (settings.max_request_note_chars + 1),
                      note="", now=NOW)


def test_the_submission_captures_the_CURRENT_value_at_request_time(rights,
                                                                  candidate_id,
                                                                  candidates):
    """What the operator reviews is the pair the subject saw, not whatever the
    row says by the time somebody gets to it."""
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.FULL_NAME,
                         requested_value="Asha Rao", note="", now=NOW)
    assert view.current_value == "Asha R"
    # And it stays what it was, even after the row moves underneath it.
    candidates.apply_correction(candidate_id, full_name="Someone Else")
    assert rights.for_candidate(candidate_id)[0].current_value == "Asha R"


def test_resolving_a_full_name_correction_with_apply_writes_the_candidate_row(
    rights, candidate_id, candidates
):
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.FULL_NAME,
                         requested_value="Asha Rao", note="", now=NOW)
    out = rights.resolve(view.id, status=RequestStatus.RESOLVED,
                         resolution="verified against the payslip", apply=True,
                         resolved_by=ResolvedBy.OPERATOR_KEY, admin_user_id=None,
                         now=NOW)
    assert out.applied is True
    assert candidates.get_candidate(candidate_id).full_name == "Asha Rao"


def test_an_email_correction_is_REFUSED_for_auto_apply_naming_its_reason(
    rights, candidate_id
):
    """Not 'not implemented': email_hash is the dedup key AND the portal login
    credential, so changing it is an identity operation that can collide two
    candidate rows or move an account's login address."""
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.EMAIL,
                         requested_value="new@example.com", note="", now=NOW)
    with pytest.raises(RequestRefused) as exc:
        rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="ok",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)
    assert "email" in str(exc.value)
    assert "login" in str(exc.value).lower()


def test_an_email_correction_can_still_be_RESOLVED_without_apply(rights, candidate_id):
    """The mechanism is complete for all four fields. Auto-apply is a
    convenience for the one field where it is safe."""
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.EMAIL,
                         requested_value="new@example.com", note="", now=NOW)
    out = rights.resolve(view.id, status=RequestStatus.RESOLVED,
                         resolution="changed by hand after an ID check",
                         apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                         admin_user_id=None, now=NOW)
    assert out.status is RequestStatus.RESOLVED
    assert out.applied is False


def test_applying_a_grievance_is_refused(rights, candidate_id):
    view = rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                         requested_value="", note="nobody replied", now=NOW)
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="sorry",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_applying_a_REJECTED_request_is_refused(rights, candidate_id):
    """A rejection that writes the value is a contradiction the subject would
    read as an approval."""
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.FULL_NAME,
                         requested_value="Asha Rao", note="", now=NOW)
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, status=RequestStatus.REJECTED, resolution="no",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_a_rejection_records_the_reason_and_leaves_the_row_alone(rights, candidate_id,
                                                                 candidates):
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.FULL_NAME,
                         requested_value="Someone Else", note="", now=NOW)
    out = rights.resolve(view.id, status=RequestStatus.REJECTED,
                         resolution="the name does not match the submitted ID",
                         apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                         admin_user_id=None, now=NOW)
    assert out.status is RequestStatus.REJECTED
    assert out.applied is False
    assert candidates.get_candidate(candidate_id).full_name == "Asha R"


def test_resolving_twice_is_refused(rights, candidate_id):
    view = rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                         requested_value="", note="x", now=NOW)
    kwargs = dict(status=RequestStatus.RESOLVED, resolution="done", apply=False,
                  resolved_by=ResolvedBy.OPERATOR_KEY, admin_user_id=None, now=NOW)
    rights.resolve(view.id, **kwargs)
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, **kwargs)


def test_an_APPLIED_correction_NEVER_touches_an_extraction(rights, candidate_id,
                                                           candidates, extraction_id):
    """THE LOAD-BEARING RULE. An extractions row records what a DOCUMENT said.
    The subject of a correction is exactly the person with an incentive to edit
    a claim that got flagged, so the evidence is immutable and only the
    candidate's own identity column moves."""
    before = candidates.latest_profile(candidate_id)
    view = rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                         field=CorrectionField.FULL_NAME,
                         requested_value="Asha Rao", note="", now=NOW)
    rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="ok",
                   apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                   admin_user_id=None, now=NOW)
    assert candidates.latest_profile(candidate_id) == before


def test_submitting_is_rate_limited_per_candidate(rights, candidate_id, settings):
    """A stuck client looping on a new authenticated write is the surface the
    Phase A limiter exists for -- and this rule covers BOTH request kinds,
    because a rule applied at one door and not its twin is this repo's
    signature defect."""
    limit = settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="", note=f"n{i}", now=NOW)
    with pytest.raises(RateLimited):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="", note="over", now=NOW)


def test_a_CORRECTION_spends_the_same_budget_as_a_grievance(rights, candidate_id,
                                                            settings):
    limit = settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        rights.submit(candidate_id, kind=RequestKind.CORRECTION,
                      field=CorrectionField.FULL_NAME, requested_value=f"N {i}",
                      note="", now=NOW)
    with pytest.raises(RateLimited):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="", note="over", now=NOW)


def test_the_limit_is_charged_BEFORE_the_row_is_written(rights, candidate_id, settings):
    """A bound that runs after the work it bounds is the S8.4 Phase B finding
    (4) shape. Here it would leave the refused request stored."""
    limit = settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="", note=f"n{i}", now=NOW)
    with pytest.raises(RateLimited):
        rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                      requested_value="", note="over", now=NOW)
    assert len(rights.for_candidate(candidate_id)) == limit
```

Write the fixtures at the top of the file: build a real `CandidateStore`,
`LedgerStore`, `RightsStore` and a **real** `RateLimiter` (via `build_rate_limiter`)
over one in-memory engine, plus a `candidate_id` seeded with `full_name="Asha R"` and
an `extraction_id` seeded through `candidates.ingest`. Do **not** invent a permissive
stand-in limiter — Phase A's lesson is that a fake which cannot enforce the invariant
hides it.

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_rights_service.py -q`
Expected: FAIL — no module `app.rights.service`, and no
`rate_limit_request_per_hour_per_candidate` on `Settings`.

- [ ] **Step 3: Add the rule, the knob and the limiter wiring**

`app/core/config.py`:

```python
    # S8.3 Phase B. NOTE THE NAME: the spec's §10 sketch called this
    # rate_limit_grievance_per_hour_per_candidate, and it is deliberately
    # broader here. The candidate plane gained TWO new authenticated writes,
    # not one, and limiting the grievance while leaving the correction
    # unlimited is precisely the "a rule applied at one entry point and not the
    # other" defect this repo has shipped in S7.1, S7.2, S7.3 and S8.4 Phase B.
    # One rule, one shared budget, named for what it covers.
    rate_limit_request_per_hour_per_candidate: int = Field(default=10, ge=1)

    # The same bound and the same reason as max_outcome_notes_chars (S8.5):
    # free text about a named person, typed into an unbounded Text column.
    max_request_note_chars: int = Field(default=2_000, ge=1)
```

`config.yaml`, in a new Phase B block:

```yaml
# --- DPDP rights (PI-8, S8.3 Phase B) -----------------------------------------
# A correction is a REVIEWED REQUEST, never a self-service edit: on a fraud
# screen, a subject write path onto the scored data is an edit box over the
# evidence. Only full_name is ever auto-applied.
max_request_note_chars: 2000            # same bound, same reason, as outcome notes
# Covers BOTH /portal/corrections and /portal/grievances on one budget. The spec
# sketched this as ...grievance..., and limiting one of two sibling writes is
# this repo's signature defect -- so it is named for what it covers.
rate_limit_request_per_hour_per_candidate: 10
```

`app/ratelimit/service.py`, in `rules_for`'s table:

```python
            "request_submit": [
                RateRule("request_submit",
                         s.rate_limit_request_per_hour_per_candidate,
                         _HOUR, LimitScope.CANDIDATE),
            ],
```

- [ ] **Step 4: Add `CandidateStore.apply_correction`**

In `app/candidates/store.py`, beside the other write methods:

```python
    def apply_correction(self, candidate_id: str, *, full_name: str) -> bool:
        """Write a REVIEWED correction onto the candidate's own identity row.

        `full_name` and nothing else, ever. An `extractions` row is a record of
        what a DOCUMENT said, and rewriting it destroys the evidence the fraud
        screen is computed from -- on this product that is not hypothetical,
        because the subject of a correction request is exactly the person with
        an incentive to edit a claim that got flagged (spec §8.2).

        email/phone are refused one layer up, in RightsService: both are hashed
        into the dedup keys `_resolve_candidate` matches on, and `email_hash` is
        additionally the portal login credential.
        """
        with self._session_factory() as session:
            row = session.get(CandidateRow, candidate_id)
            if row is None:
                return False
            row.full_name = full_name
            session.commit()
            return True
```

- [ ] **Step 5: Write `app/rights/service.py`**

The gate order inside `submit` is load-bearing and must read:

1. `self._limiter.enforce(self._limiter.rules_for("request_submit"), {LimitScope.CANDIDATE: candidate_id}, now=now)`
2. validate (kind/field/note/value bounds) — raising `RequestRefused`
3. read the current value off `CandidateStore`
4. `store.create(...)`
5. audit through `LedgerStore._audit`-equivalent public path

`resolve` refuses, in this order, before touching the store: `apply` with
`kind == GRIEVANCE`; `apply` with `status == REJECTED`; `apply` with a field outside
`AUTO_APPLIABLE_FIELDS` (message must name the field *and* why); then
`store.resolve(...)` returning False ⇒ `RequestAlreadyResolved` (the 409 case; an id
that never existed is distinguished by the preceding `store.get` returning None).
Apply the
candidate write **after** a successful `store.resolve`, and if `apply_correction`
returns False (the candidate was erased mid-decision — the S8.5 shape) raise
`RequestRefused` naming that, rather than reporting an applied correction that wrote
nothing.

Every submit and every resolve is audited with `entity_type="data_principal_request"`
and the candidate id, so it surfaces in the subject's own `/portal/access-log`. Use
whatever public audit method `LedgerStore` exposes (read it — `_audit` is a private
static helper; there is a public writer beside it).

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_rights_service.py tests/test_config_ratelimit.py -q`
Expected: PASS.

- [ ] **Step 7: Full suite, then commit**

```bash
git add app/rights/service.py app/candidates/store.py app/ratelimit/service.py app/core/config.py config.yaml tests/test_rights_service.py
git commit -m "feat(s83b): RightsService -- reviewed corrections, one shared candidate budget"
```

---

## Task 11: The candidate plane

**Files:**
- Modify: `app/api/routes.py`, `app/services/__init__.py`, `tests/conftest.py`
- Test: `tests/test_rights_api.py`

**Interfaces:**
- Consumes: `RightsService`
- Produces: `POST /portal/corrections`, `POST /portal/grievances`, `GET /portal/requests`;
  `Services.rights: RightsService`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rights_api.py
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_every_request_route_needs_a_candidate_credential(client):
    assert client.post("/portal/corrections", json={}).status_code == 401
    assert client.post("/portal/grievances", json={}).status_code == 401
    assert client.get("/portal/requests").status_code == 401


def test_a_correction_round_trips(client, candidate_headers):
    r = client.post("/portal/corrections", headers=candidate_headers,
                    json={"field": "full_name", "requested_value": "Asha Rao"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open" and body["applied"] is False

    listed = client.get("/portal/requests", headers=candidate_headers).json()
    assert [x["id"] for x in listed] == [body["id"]]


def test_a_grievance_round_trips(client, candidate_headers):
    r = client.post("/portal/grievances", headers=candidate_headers,
                    json={"note": "nobody answered my correction"})
    assert r.status_code == 200
    assert r.json()["kind"] == "grievance"


def test_a_refused_submission_is_422_and_says_why(client, candidate_headers):
    r = client.post("/portal/corrections", headers=candidate_headers,
                    json={"field": "full_name", "requested_value": "   "})
    assert r.status_code == 422
    assert r.json()["detail"]


def test_the_submission_appears_in_the_candidates_own_access_log(client,
                                                                 candidate_headers):
    """S3.1's rule -- surveillance is itself observable -- applied to the
    handling of the subject's own complaint, which is the case where it matters
    most."""
    client.post("/portal/grievances", headers=candidate_headers,
                json={"note": "nobody answered"})
    log = client.get("/portal/access-log", headers=candidate_headers).json()
    assert any(e["entity_type"] == "data_principal_request" for e in log)


def test_a_candidate_never_sees_another_candidates_requests(client,
                                                            candidate_headers,
                                                            other_candidate_headers):
    client.post("/portal/grievances", headers=candidate_headers,
                json={"note": "mine"})
    assert client.get("/portal/requests", headers=other_candidate_headers).json() == []


def test_the_route_returns_429_when_the_budget_is_spent(client, candidate_headers,
                                                        services):
    limit = services.settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        assert client.post("/portal/grievances", headers=candidate_headers,
                           json={"note": f"n{i}"}).status_code == 200
    over = client.post("/portal/grievances", headers=candidate_headers,
                       json={"note": "over"})
    assert over.status_code == 429
    assert over.headers["Retry-After"]
    assert over.json()["detail"] == "rate_limited"
```

Reuse the existing candidate-credential fixture pattern — grep `tests/test_portal_api.py`
for how it mints `X-Candidate-Key` and copy it rather than inventing a second way.

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_rights_api.py -q`
Expected: FAIL — 404 on every route.

- [ ] **Step 3: Put `rights` on the container**

`app/services/__init__.py`: add `rights: RightsService` to the `Services` dataclass and
build it in `build_default_services` **after** `candidates`/`ledger`, passing
`metrics=metrics` to its limiter. Phase A's headline finding was a builder that
skipped `metrics=` for one service, so the new limiter must be built the same way the
others are — `tests/test_ratelimit_wiring.py` builds the production container and
asserts every limiter shares the container's metrics *and* settings, so add `rights`
to whatever list that test parametrizes over.

`tests/conftest.py::make_services` gets the same wiring, using the container's own
limiter — not a permissive stand-in.

- [ ] **Step 4: Add the three routes**

In `app/api/routes.py`, with the other `candidate_router` portal routes. Map
`RequestRefused` → 422 with the message as `detail`, and `RateLimited` → 429 exactly
the way the auth routes already do (find that handler and reuse it; do not write a
second translation).

```python
class CorrectionSubmitRequest(BaseModel):
    field: CorrectionField
    requested_value: str = ""
    note: str = ""


class GrievanceSubmitRequest(BaseModel):
    note: str = ""
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_rights_api.py tests/test_route_table_guard.py tests/test_openapi_contract.py tests/test_ratelimit_wiring.py -q`
Expected: PASS.

- [ ] **Step 6: Full suite, then commit**

```bash
git add app/api/routes.py app/services/__init__.py tests/conftest.py tests/test_rights_api.py tests/test_ratelimit_wiring.py
git commit -m "feat(s83b): the candidate plane files corrections and grievances"
```

---

## Task 12: `MyData.requests`

**Files:**
- Modify: `app/portal/schema.py`, `app/portal/service.py`
- Test: `tests/test_portal_service.py` (append), `tests/test_rights_api.py` (append)

**Interfaces:**
- Consumes: `RightsService.for_candidate`
- Produces: `MyData.requests: list[RequestView]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_portal_service.py (append)
def test_my_data_carries_the_subjects_own_requests(services, candidate_id):
    """The DPDP access view is 'everything the platform holds about you that
    the portal surfaces'. A complaint you filed is squarely that."""
    services.rights.submit(
        candidate_id, kind=RequestKind.GRIEVANCE, field=None,
        requested_value="", note="nobody answered", now=NOW,
    )
    md = services.portal.my_data(candidate_id)
    assert [r.note for r in md.requests] == ["nobody answered"]


def test_my_data_has_no_requests_when_none_were_filed(services, candidate_id):
    assert services.portal.my_data(candidate_id).requests == []
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_portal_service.py -q`
Expected: FAIL — `AttributeError: 'MyData' object has no attribute 'requests'`.

- [ ] **Step 3: Implement**

`app/portal/schema.py`: import `RequestView` and add to `MyData`:

```python
    # S8.3 Phase B. The subject's own correction and grievance requests, in the
    # one view they check hardest -- a mechanism they cannot see the state of is
    # not a mechanism.
    requests: list[RequestView] = Field(default_factory=list)
```

`app/portal/service.py`: accept `rights=None` in `__init__` and `build_portal_service`
(Optional for the same reason `verification`/`interview`/`auth` are — the portal must
stay constructible without it), and in `my_data`:

```python
        requests = (
            self._rights.for_candidate(candidate_id)
            if self._rights is not None
            else []
        )
```

Wire `rights=rights` in `build_default_services` and in `make_services`.

- [ ] **Step 4: Run, then commit**

Run: `python -m pytest tests/test_portal_service.py tests/test_portal_api.py tests/test_rights_api.py -q` → PASS, then the full suite.

```bash
git add app/portal/schema.py app/portal/service.py app/services/__init__.py tests/conftest.py tests/test_portal_service.py
git commit -m "feat(s83b): MyData carries the subject's own requests"
```

---

## Task 13: The admin plane

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_rights_admin_api.py`

**Interfaces:**
- Produces: `GET /admin/requests?status=open&limit=50`,
  `POST /admin/requests/{request_id}/resolve` with
  `ResolveRequest{status: RequestStatus, resolution: str, apply: bool = False}`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rights_admin_api.py
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rights.schema import ResolvedBy


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_both_admin_routes_need_the_admin_credential(client):
    assert client.get("/admin/requests").status_code == 401
    assert client.post("/admin/requests/x/resolve", json={}).status_code == 401


def test_the_operator_lists_open_requests(client, admin_headers, candidate_headers):
    client.post("/portal/corrections", headers=candidate_headers,
                json={"field": "full_name", "requested_value": "Asha Rao"})
    listed = client.get("/admin/requests?status=open", headers=admin_headers).json()
    assert len(listed) == 1 and listed[0]["field"] == "full_name"


def test_resolving_with_apply_updates_the_candidate_and_the_portal_shows_it(
    client, admin_headers, candidate_headers, services
):
    submitted = client.post("/portal/corrections", headers=candidate_headers,
                            json={"field": "full_name",
                                  "requested_value": "Asha Rao"}).json()
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    headers=admin_headers,
                    json={"status": "resolved", "resolution": "checked the ID",
                          "apply": True})
    assert r.status_code == 200 and r.json()["applied"] is True
    me = client.get("/portal/me", headers=candidate_headers).json()
    assert me["requests"][0]["status"] == "resolved"
    assert me["requests"][0]["applied"] is True
    # The identity row is what moved -- `profile` is the EXTRACTION's view and
    # is deliberately untouched (§8.2), so assert the column directly.
    assert services.candidates.get_candidate(
        me["candidate_id"]
    ).full_name == "Asha Rao"


def test_applying_an_email_correction_is_422_and_names_the_reason(
    client, admin_headers, candidate_headers
):
    submitted = client.post("/portal/corrections", headers=candidate_headers,
                            json={"field": "email",
                                  "requested_value": "new@example.com"}).json()
    r = client.post(f"/admin/requests/{submitted['id']}/resolve",
                    headers=admin_headers,
                    json={"status": "resolved", "resolution": "ok", "apply": True})
    assert r.status_code == 422
    assert "login" in r.json()["detail"].lower()


def test_an_unknown_request_id_is_404(client, admin_headers):
    r = client.post("/admin/requests/nope/resolve", headers=admin_headers,
                    json={"status": "resolved", "resolution": "x", "apply": False})
    assert r.status_code == 404


def test_resolving_twice_is_409(client, admin_headers, candidate_headers):
    submitted = client.post("/portal/grievances", headers=candidate_headers,
                            json={"note": "nobody answered"}).json()
    body = {"status": "resolved", "resolution": "called them", "apply": False}
    assert client.post(f"/admin/requests/{submitted['id']}/resolve",
                       headers=admin_headers, json=body).status_code == 200
    assert client.post(f"/admin/requests/{submitted['id']}/resolve",
                       headers=admin_headers, json=body).status_code == 409


def test_a_machine_key_resolution_is_recorded_as_a_KEY_not_as_a_person(
    client, admin_headers, candidate_headers, services
):
    """S8.5's `recorded_by` argument at a second table: the shared admin key
    has no human behind it, and a null admin_user_id alone would be
    indistinguishable from an admin who was later deleted."""
    submitted = client.post("/portal/grievances", headers=candidate_headers,
                            json={"note": "x"}).json()
    client.post(f"/admin/requests/{submitted['id']}/resolve", headers=admin_headers,
                json={"status": "resolved", "resolution": "done", "apply": False})
    row = services.rights.list_by_status(None, limit=10)[0]
    assert row.resolved_by is ResolvedBy.OPERATOR_KEY
    # And the subject is told the KIND of decider, never a person's identity.
    shown = client.get("/portal/requests", headers=candidate_headers).json()[0]
    assert shown["resolved_by"] == "operator_key"


def test_the_resolution_appears_in_the_subjects_access_log(client, admin_headers,
                                                           candidate_headers):
    submitted = client.post("/portal/grievances", headers=candidate_headers,
                            json={"note": "x"}).json()
    client.post(f"/admin/requests/{submitted['id']}/resolve", headers=admin_headers,
                json={"status": "resolved", "resolution": "done", "apply": False})
    log = client.get("/portal/access-log", headers=candidate_headers).json()
    actions = [e["action"] for e in log
               if e["entity_type"] == "data_principal_request"]
    assert len(actions) == 2       # the submission AND the decision
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_rights_admin_api.py -q`
Expected: FAIL — 404 on both routes.

- [ ] **Step 3: Add the routes**

On `router` (admin plane), so `require_api_key` is inherited. Read the principal for
authorship the way the route knows how:

```python
@router.post("/admin/requests/{request_id}/resolve", response_model=RequestView)
async def resolve_request(
    request_id: str, req: ResolveRequest, request: Request
) -> RequestView:
    services = _services(request)
    principal = request.state.principal
    admin_user_id = principal.admin_user_id
    resolved_by = (
        ResolvedBy.ADMIN_USER if admin_user_id else ResolvedBy.OPERATOR_KEY
    )
    ...
```

Three outcomes, three statuses, and the handler picks by **type** — never by matching
on message text, which breaks the first time somebody rewords a sentence:

- `RequestAlreadyResolved` → **409**. A second decision on a decided request.
- `RequestRefused` → **422**. A refused decision: apply on a grievance, apply on a
  rejection, apply on `email`/`phone`/`other`.
- the service returning nothing for an unknown id → **404**.

Order the `except` clauses subclass-first, or the 409 is unreachable — `RequestAlreadyResolved`
IS a `RequestRefused`, so a broad clause above it swallows every one.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_rights_admin_api.py tests/test_route_table_guard.py tests/test_openapi_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite, then commit**

```bash
git add app/api/routes.py app/rights/service.py tests/test_rights_admin_api.py
git commit -m "feat(s83b): the operator reviews, decides and is recorded deciding"
```

---

## Task 14: The published grievance officer, and boot refusal #7

**Files:**
- Modify: `app/core/config.py`, `config.yaml`, `app/core/boot.py`, `app/api/routes.py`,
  `app/rights/schema.py` (`build_grievance_contact`), `app/portal/schema.py`,
  `app/portal/service.py`
- Test: `tests/test_grievance_contact.py`, `tests/test_boot_config.py` (append)

**Interfaces:**
- Produces: `GET /grievance` (PUBLIC), `MyData.grievance: GrievanceContact`,
  refusal #7 in `verify_launch_config`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grievance_contact.py
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_the_grievance_contact_is_readable_WITHOUT_a_session(client):
    """DPDP requires the mechanism to be PUBLISHED. A contact reachable only
    after login is not reachable by the person whose complaint is that they
    cannot log in."""
    r = client.get("/grievance")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"name", "email", "phone", "response_days"}


def test_the_contact_is_echoed_in_the_portal_in_context(client, candidate_headers):
    me = client.get("/portal/me", headers=candidate_headers).json()
    assert me["grievance"]["response_days"] >= 1


def test_grievance_is_in_the_named_public_set(client):
    """Widening PUBLIC_PATHS is the reviewable act. This asserts the route is
    public BY BEING IN THE LIST, not by happening to answer 200."""
    from app.api.routes import PUBLIC_PATHS
    assert "/grievance" in PUBLIC_PATHS
```

```python
# tests/test_boot_config.py (append)
def test_prod_refuses_to_boot_without_a_published_grievance_contact():
    """The SEVENTH refusal. Shipping to production with no published grievance
    contact is exactly the RFP blocker GTM §8.1 names, and a boot failure is the
    only form of 'remember this' that works."""
    settings = _prod_settings(grievance_officer_email="")
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(settings)
    assert "grievance" in str(exc.value).lower()


def test_a_published_contact_boots():
    verify_launch_config(_prod_settings(grievance_officer_email="dpo@example.com"))


def test_the_grievance_refusal_does_NOT_fire_outside_prod():
    """It must sit AFTER boot.py's `if settings.env != "prod": return`, or
    every local run breaks -- the same placement Phase A's rate-limit refusal
    needed."""
    verify_launch_config(_local_settings(grievance_officer_email=""))
```

Read `tests/test_boot_config.py` first and reuse its existing helpers for building a
prod-shaped and a local-shaped `Settings` — do not add a second way to construct one.

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_grievance_contact.py tests/test_boot_config.py -q`
Expected: FAIL — 404 on `/grievance`, and no refusal raised.

- [ ] **Step 3: Add the four knobs**

`app/core/config.py`:

```python
    # S8.3 Phase B. PROD REFUSES TO BOOT with an empty officer email
    # (app/core/boot.py -- the seventh refusal): a published grievance
    # mechanism is a statutory requirement and an RFP blocker, and a boot
    # failure is the only form of "remember this" that works.
    grievance_officer_name: str = ""
    grievance_officer_email: str = ""
    grievance_officer_phone: str = ""
    grievance_response_days: int = Field(default=30, ge=1)
```

`config.yaml`, in the DPDP block:

```yaml
grievance_officer_name: ""              # prod REFUSES to boot with an empty email
grievance_officer_email: ""
grievance_officer_phone: ""
grievance_response_days: 30
```

- [ ] **Step 4: Refusal #7**

`app/core/boot.py`, **after** the `if settings.env != "prod": return` guard, beside the
rate-limit refusal:

```python
    if not settings.grievance_officer_email.strip():
        raise LaunchConfigError(
            "DEE_ENV=prod with an empty grievance_officer_email. DPDP requires "
            "the grievance mechanism to be PUBLISHED, GET /grievance would "
            "return an empty contact, and every enterprise RFP asks for the "
            "officer by name. Set grievance_officer_email (and the name and "
            "phone beside it)."
        )
```

Update the module docstring's count: it currently says S8.3 adds "a sixth"; it now
adds a sixth and a seventh.

- [ ] **Step 5: `build_grievance_contact`, the route, and the portal echo**

Add `build_grievance_contact(settings) -> GrievanceContact` to `app/rights/schema.py`
(the four knobs now exist). Then:

```python
@public_router.get("/grievance", response_model=GrievanceContact)
async def grievance(request: Request) -> GrievanceContact:
    """PUBLIC by design -- see GrievanceContact's docstring. This is the route
    that made PUBLIC_PATHS wider, which is the reviewable act that widening
    that set is meant to be."""
    return build_grievance_contact(_services(request).settings)
```

Add `"/grievance"` to `PUBLIC_PATHS`. Add `grievance: GrievanceContact` to `MyData`
(with a default) and fill it in `PortalService.my_data` from `self._settings`.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_grievance_contact.py tests/test_boot_config.py tests/test_route_table_guard.py tests/test_api_auth_gate.py -q`
Expected: PASS. The auth-gate test enumerates what may be reached unauthenticated —
if it fails, it is telling you the widening is real, so update it deliberately.

- [ ] **Step 7: Full suite, then commit**

```bash
git add app/core/config.py app/core/boot.py app/api/routes.py app/rights/schema.py app/portal/ config.yaml tests/
git commit -m "feat(s83b): the grievance officer is published, and prod refuses to ship without one"
```

---

## Task 15: Documentation

**Files:**
- Modify: `OPERATING.md`, `SCREENING.md`, `UI.md`

**No code.** Run `pytest -q` first and record the number; it must be unchanged at the
end.

- [ ] **Step 1: `OPERATING.md` §9 — the sweep runbook**

Append three sections after §8:

- **§9 The retention sweep.** The eleven-class table (copy the one at the top of this
  plan), the two modes and why `batch_item_text` clears rather than deletes, the cap
  and what `truncated: true` means, and the dry-run discipline: `POST
  /admin/retention/sweep` with an empty body previews, `{"dry_run": false}` deletes,
  `python -m app.retention.sweep [--apply]` is the cron's door, and both doors refuse
  a real run when `retention_sweep_enabled` is false. State plainly that **there is no
  scheduler in the application** — if nobody invokes it, nothing is deleted.
- **§10 The request queue's lifecycle.** open → resolved | rejected, `applied` as a
  separate fact, the four fields and why only `full_name` auto-applies, and that an
  extraction is never rewritten.
- **§11 The grievance officer.** The published contact, the public route, the boot
  refusal, and `grievance_response_days` as the promise being made.

Also correct §6 ("Retry"): retention now **bounds** the retry window — after
`ret_batch_item_days` a failed item's text is gone and the retry reports it `skipped`.

- [ ] **Step 2: `SCREENING.md` §7**

It currently states the text is kept for S8.3's in-place retry and "held under
`ret_batch_item_days`". Make the coupling explicit **in both directions**: retaining
the text is justified by the retry, and the retry is bounded by the sweep that now
exists. One sentence; do not restate the whole design.

- [ ] **Step 3: `UI.md` §4.D**

Correction, grievance and a live sweep are new portal surfaces. Say what exists at the
API and that no screen calls them yet — an unwired route described as a screen is the
overclaim shape three reviews in a row have caught.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest -q` — the same count as before Step 1.

```bash
git add OPERATING.md SCREENING.md UI.md
git commit -m "docs(s83b): the sweep runbook, the request lifecycle, the published officer"
```

---

## Task 16: `smoke_s83b.py`, mutation probes, and the regression sweep

**Files:**
- Create: `scripts/smoke_s83b.py`
- Test: the smoke itself, plus every prior smoke re-run

**Interfaces:** Consumes the running app over HTTP. Follow `scripts/smoke_s83a.py`
exactly: same `check()` helper, same uvicorn launch, same teardown, and
`DEE_OPENROUTER_API_KEY` **pinned empty** so the run cannot make a billed call — that
trap has now bitten three sprints running.

- [ ] **Step 1: Write the smoke**

Checks, each a named `check()`:

1. `GET /grievance` answers 200 **with no credential at all** (a fresh client, no
   cookie jar, no key).
2. A candidate signs up through a **real session** (cookie + CSRF), files a
   correction, and it appears in `GET /portal/requests`.
3. The same correction appears in `GET /portal/access-log` — the subject can see that
   their own complaint was handled.
4. The operator lists it at `GET /admin/requests?status=open` and resolves it with
   `apply: true`; `GET /portal/me` then shows the corrected `full_name`.
5. An `email` correction is refused for auto-apply with **422** and the body names the
   reason.
6. Resolving the same request twice answers **409**.
7. Rows seeded with old timestamps (write them directly into the smoke's own SQLite
   file before starting the server) are counted by a dry run…
8. …and then deleted by a real run, **with the counts matching**. This is the
   dry-run-parity check and it is the cheapest guard against a sweeper whose preview
   and whose action disagree.
9. A second real run over the same data reports **0** — the clear-mode predicate,
   end to end.
10. `sweep_active` reads **true** in `GET /portal/me`.
11. `GET /metrics` (admin) carries `veritas_retention_deleted_total` with a
    `data_class` label after check 8.
12. The candidate-plane request budget: submit past
    `rate_limit_request_per_hour_per_candidate` and assert **429** with `Retry-After`.

**Say only what you assert.** Phase A's review found two docstrings claiming checks the
code never made; if a check compares status and body, do not write "byte-identical",
and do not put failure-phrased detail in a string `check()` also prints on success.

- [ ] **Step 2: Run it**

Run: `python scripts/smoke_s83b.py`
Expected: every check OK, exit 0. Fix the code, not the check, when one fails.

- [ ] **Step 3: Plant the mutation probes**

Each must die naming a test. Plant, run the named test, confirm RED, revert:

| # | Mutation | Must be caught by |
|---|---|---|
| 1 | `_predicate` drops the `!= ""` arm for CLEAR | `test_a_second_sweep_reports_zero_rather_than_the_same_rows_again` |
| 2 | `run_sweep` counts on a dry run too (move the `metrics.add` out of the `if`) | `test_a_dry_run_counts_NOTHING` |
| 3 | `run_sweep` ignores `dry_run` and always writes | `test_dry_run_counts_and_deletes_nothing` |
| 4 | the cap is applied to the COUNT but not to the DELETE subquery | `test_the_cap_bounds_one_invocation_and_the_report_says_so` |
| 5 | `AUTO_APPLIABLE_FIELDS` gains `EMAIL` | `test_an_email_correction_is_REFUSED_for_auto_apply_naming_its_reason` |
| 6 | `RightsService.submit` enforces the limit **after** the store write | `test_the_limit_is_charged_BEFORE_the_row_is_written` |
| 7 | `store.resolve` drops the `status == OPEN` clause | `test_resolving_an_already_resolved_request_is_refused_at_the_STORE` |
| 8 | `build_retention_policy` returns the literal `False` again | `test_sweep_active_is_DERIVED_from_the_config_not_a_literal` |
| 9 | `apply_correction` also writes the latest extraction's `profile["full_name"]` | `test_an_APPLIED_correction_NEVER_touches_an_extraction` |
| 10 | the boot refusal is moved **above** the `env != "prod"` return | `test_the_grievance_refusal_does_NOT_fire_outside_prod` |

**A probe that does not express the behaviour it names proves nothing** — Phase A's
probe 4 survived its first version for exactly that reason. If a probe survives, first
ask whether the mutation is really the behaviour you meant; only then write the missing
test.

**OneDrive:** probes that touch `alembic/` need the file settled before the run.

- [ ] **Step 4: Re-run every prior smoke**

`smoke_s63`, `s64`, `s73`, `s81`, `s82`, `s83a`, `s84a`, `s84b`, `s85_outcome`, and the
new `s83b` — all with `DEE_OPENROUTER_API_KEY` pinned. `smoke_s83a` matters most: this
branch changed `Metrics.increment` into a wrapper over `add`, and `s83a` reads the
deny counter out of `/metrics`.

- [ ] **Step 5: Full suite, then commit**

Run: `python -m pytest -q`

```bash
git add scripts/smoke_s83b.py
git commit -m "test(s83b): the smoke, and ten probes that all die"
```

---

## Closeout (not a task — do it before asking for review)

1. Update `docs/ROADMAP.md`: status board, "Current state" with a new session bullet,
   and the ➤ NEXT STEP. Record, at minimum: the eleven-class table and that the portal
   now discloses three more windows than it did; the clear-mode predicate and why a
   preview without it lies; that the bulk delete's cascade is carried by the DB and is
   **measured**, not assumed; the `Metrics.add` / scanner coupling; the deliberate
   rename of the spec's grievance-only rate rule to `request_submit` covering both
   candidate writes, with the reason; and any probe that survived its first version.
2. Note the two items Phase A carried forward and did **not** fix, so they stay
   visible: the six "byte-identical" 404-vs-absence claims in `SCREENING.md` and
   `TENANCY.md`, and `GET /`'s stale hand-maintained `endpoints` list.
3. Request a whole-branch review (`superpowers:requesting-code-review`) before merging.
   Name the hot spots: `run_sweep`'s predicate and cap arithmetic, the resolve state
   machine's refusal ordering, and the authorship columns.
