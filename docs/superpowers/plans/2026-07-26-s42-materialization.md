# S4.2 Feature Materialization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn S4.1's registered feature definitions into persisted, point-in-time-correct feature vectors in a new `ml_feature_vectors` table + a wide CSV/parquet export, with `ledger_read` enforced on consent-tagged features at materialization time.

**Architecture:** Upgrade `build_context` into a true point-in-time slicer (profile-as-of via versioned extractions; consent evaluated at `as_of`). A pure `materialize.py` computes a view over the sliced context, then masks `requires_consent` features to null unless the candidate has an active `ledger_read` grant at `as_of` (decision audited in-txn by a new `LedgerStore.materialization_consent`). A compact `ml_feature_vectors` row (JSON `feature_values`) is written by a new `FeatureStore`; `export.py` pivots stored vectors to wide CSV (stdlib) and optional parquet (guarded `pyarrow`).

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0 + Alembic on SQLite (Postgres-shaped), Pydantic v2, stdlib `csv`, optional `pyarrow`. No LLM. Fully offline tests (`pytest -q`).

**Spec:** `docs/superpowers/specs/2026-07-26-s42-materialization-design.md`.

## Global Constraints

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` green before merge. No network, no API key.
- S4.2 is **LLM-free** — the "every LLM step degrades to a deterministic fallback" rule is trivially met.
- **Advisory only** — a feature value is never an auto-reject gate.
- **DPDP:** the new table is candidate-linked with an `ondelete="CASCADE"` FK to `candidates.id`, so existing `CandidateStore.delete_candidate` erasure sweeps it — **no new erasure code**. Consent-tagged feature inclusion is gated + audited per candidate.
- **Consent basis (D1):** consent-tagged features (`spec.requires_consent`, i.e. sources `ledger`/`reputation`) materialize only under an **active `ledger_read` grant in effect at `as_of`, org-agnostic** (any org, or org=NULL). Withheld ⇒ those cells null + recorded reason; first-party features (`candidate`/`depth`/`fabrication`) always materialize. Fail-closed.
- **Storage (D2):** one compact row per `(candidate_id, as_of, view_name, view_version)`; values in a JSON column; re-materializing the same cut is an idempotent upsert. Wide shape is an export-time pivot.
- **Parquet (D3):** CSV always via stdlib; parquet only when `pyarrow` importable, else raise `ParquetUnavailable`. **Do not add pyarrow to `requirements.txt`.**
- **Point-in-time / no leakage:** `as_of` threads through profile, report, ledger, consent validity, reputation decay. A vector at `as_of=T` reflects only data timestamped `<= T`, even when newer rows exist now.
- DB via SQLAlchemy + Alembic on SQLite, Postgres-shaped (UUID PKs, FKs, JSON columns). Tunables in `config.yaml` (`DEE_*` env override); no new numeric knob (reuse `feat_default_view`).
- Config.yaml comments must stay ASCII (Windows cp1252 read).
- Commits: **no `Co-Authored-By` trailer** (clean history).

## File structure

- `app/candidates/store.py` (modify) — `+ profile_as_of(candidate_id, as_of)`.
- `app/features/context.py` (modify) — `build_context` uses `profile_as_of` (point-in-time profile).
- `app/ledger/consent.py` (modify) — `+ has_any_active(grants, *, purpose, at)` (org-agnostic).
- `app/ledger/store.py` (modify) — `+ materialization_consent(candidate_id, *, at=None)` (+ `feature.materialize` audit).
- `app/features/models.py` (create) — `FeatureVectorRow` ORM (`ml_feature_vectors`).
- `alembic/versions/0007_ml_feature_vectors.py` (create) — the migration.
- `alembic/env.py` (modify) — import `app.features.models` so metadata is complete.
- `app/features/materialize.py` (create) — `MaterializedVector`, `materialize_candidate`, `materialize_all`.
- `app/features/store.py` (create) — `FeatureStore` + `build_feature_store`.
- `app/features/export.py` (create) — `export_view_csv`, `export_view_parquet`, `ParquetUnavailable`.
- `tests/conftest.py` (modify) — import `app.features.models`; `+ set_extraction_created_at` helper.
- `tests/test_migrations.py` (modify) — import features model; assert new table; extend index/FK/nullability guards.
- New tests: `test_candidate_store_asof.py`, `test_feature_context.py` (modify), `test_consent_has_any_active.py`, `test_ledger_store_materialize_consent.py`, `test_features_materialize.py`, `test_feature_store.py`, `test_features_export.py`.
- `FEATURES.md` (modify) — S4.2 section.
- `scripts/smoke_s42.py` (create) — uvicorn populate → materialize/persist/export smoke.

Branch `s42-materialization` already exists (spec committed there).

---

### Task 1: `CandidateStore.profile_as_of` + test helper

**Files:**
- Modify: `app/candidates/store.py`
- Modify: `tests/conftest.py` (add `set_extraction_created_at`)
- Test: `tests/test_candidate_store_asof.py`

**Interfaces:**
- Produces: `CandidateStore.profile_as_of(candidate_id: str, as_of: datetime) -> Optional[CandidateProfile]` — the newest extraction whose `created_at <= as_of` (joined to resume version; tie-break newest version then newest created_at); `None` if none existed by `as_of`.
- Produces (test util): `tests.conftest.set_extraction_created_at(store: CandidateStore, candidate_id: str, when: datetime) -> None` — overwrites every extraction row's `created_at` for that candidate (lets tests control the point-in-time axis).

- [ ] **Step 1: Write the failing test** — `tests/test_candidate_store_asof.py`

```python
from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark\nEmail: jane@example.com\n"


def _ingest(cs):
    return cs.ingest(
        ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
        resume_text=RESUME,
    ).candidate_id


def test_profile_as_of_none_before_first_extraction():
    cs = make_candidate_store()
    cid = _ingest(cs)
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert cs.profile_as_of(cid, datetime(2026, 1, 1, tzinfo=timezone.utc)) is None


def test_profile_as_of_returns_profile_after_extraction():
    cs = make_candidate_store()
    cid = _ingest(cs)
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))
    prof = cs.profile_as_of(cid, datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert prof is not None
    assert prof.full_name  # heuristic pulled a name


def test_profile_as_of_unknown_candidate_is_none():
    cs = make_candidate_store()
    assert cs.profile_as_of("nope", datetime(2026, 6, 1, tzinfo=timezone.utc)) is None
```

- [ ] **Step 2: Add the conftest helper.** In `tests/conftest.py`, add near the top imports:

```python
from sqlalchemy import select as _select
from app.candidates.models import ExtractionRow as _ExtractionRow
```

and after `make_candidate_store`:

```python
def set_extraction_created_at(store, candidate_id, when):
    """Test util: pin every extraction row's created_at so point-in-time tests
    can control the profile axis (ingest itself stamps wall-clock now)."""
    with store._session_factory() as s:
        rows = s.execute(
            _select(_ExtractionRow).where(_ExtractionRow.candidate_id == candidate_id)
        ).scalars().all()
        for r in rows:
            r.created_at = when
        s.commit()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_candidate_store_asof.py -q`
Expected: FAIL (`AttributeError: 'CandidateStore' object has no attribute 'profile_as_of'`).

- [ ] **Step 4: Implement `profile_as_of`.** In `app/candidates/store.py`, add a module-level helper near the top (after imports) and the method just below `latest_profile`. If `timezone` is not already imported, extend the datetime import.

```python
def _as_utc(dt):
    from datetime import timezone
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
```

```python
    def profile_as_of(self, candidate_id: str, as_of: datetime) -> Optional[CandidateProfile]:
        """Point-in-time profile: newest extraction with created_at <= as_of
        (tie-break: newest resume version, then newest created_at). None if the
        candidate had no extraction by as_of. Filtering happens in Python after
        as_utc coercion because SQLite returns naive datetimes (see consent.py)."""
        moment = _as_utc(as_of)
        with self._session_factory() as session:
            rows = session.execute(
                select(ExtractionRow, ResumeRow.version)
                .join(ResumeRow, ExtractionRow.resume_id == ResumeRow.id)
                .where(ExtractionRow.candidate_id == candidate_id)
            ).all()
        eligible = [
            (version, _as_utc(ext.created_at), ext)
            for ext, version in rows
            if _as_utc(ext.created_at) <= moment
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda t: (t[0], t[1]))  # ascending; last = newest
        return CandidateProfile.model_validate(eligible[-1][2].profile)
```

Confirm `ExtractionRow`, `ResumeRow`, `select`, `CandidateProfile`, `Optional`, `datetime` are already imported in `store.py` (they are — `latest_profile` uses them). Add any missing import.

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_candidate_store_asof.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/candidates/store.py tests/conftest.py tests/test_candidate_store_asof.py
git commit -m "feat(s42): CandidateStore.profile_as_of (point-in-time profile) + test helper"
```

---

### Task 2: `build_context` uses the point-in-time profile

**Files:**
- Modify: `app/features/context.py`
- Modify: `tests/test_feature_context.py`

**Interfaces:**
- Consumes: `CandidateStore.profile_as_of` (Task 1), `set_extraction_created_at` (Task 1).
- Produces: `build_context(...)` unchanged signature, but `profile` is now the profile **as of `as_of`** rather than the wall-clock latest.

- [ ] **Step 1: Write the failing test.** Add to `tests/test_feature_context.py` (and update its import line to include the helper):

Change the import:
```python
from tests.conftest import make_candidate_store, set_extraction_created_at
```

Add:
```python
def test_build_context_profile_is_point_in_time():
    cs, ls, rs = _stores()
    result = ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic")
    cid = cs.ingest(result, resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))

    early = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                          as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert early is not None and early.profile is None      # before the extraction existed

    late = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls,
                         as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert late.profile is not None
```

Also fix the existing `test_build_context_assembles_profile_report_and_ledger`: its extraction is stamped wall-clock-now but it asserts `ctx.profile is not None` at `as_of=2026-06-01`. Pin the extraction so it precedes the cutoff — add this line right after the `cid = ...ingest(...)` line in that test:
```python
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
```

- [ ] **Step 2: Run the tests to verify the new one fails**

Run: `pytest tests/test_feature_context.py -q`
Expected: `test_build_context_profile_is_point_in_time` FAILS (`late.profile`/`early.profile` — currently `build_context` uses `latest_profile`, so `early.profile` is NOT None → assertion fails).

- [ ] **Step 3: Implement.** In `app/features/context.py`, replace the profile line inside `build_context`:

```python
    profile = candidate_store.latest_profile(candidate_id)
```
with
```python
    profile = candidate_store.profile_as_of(candidate_id, moment)
```

Update the module docstring's "coarse cutoff / latest_profile" note to say the profile is now point-in-time (`profile_as_of`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_feature_context.py -q`
Expected: PASS (all, including the updated assemble test and the new PIT test).

- [ ] **Step 5: Commit**

```bash
git add app/features/context.py tests/test_feature_context.py
git commit -m "feat(s42): build_context assembles point-in-time profile via profile_as_of"
```

---

### Task 3: `consent.has_any_active` (org-agnostic active-grant check)

**Files:**
- Modify: `app/ledger/consent.py`
- Test: `tests/test_consent_has_any_active.py`

**Interfaces:**
- Consumes: `as_utc`, `_selection_key`, `ConsentDecision`, `ConsentGrant`, `ConsentPurpose` (all in `consent.py`/`schema.py`).
- Produces: `has_any_active(grants: Sequence[ConsentGrant], *, purpose: ConsentPurpose, at: datetime) -> ConsentDecision` — allowed iff any grant matches `purpose` and is in its active window at `at`, **ignoring org scope**; the authorizing grant is chosen with the existing `_selection_key`.

- [ ] **Step 1: Write the failing test** — `tests/test_consent_has_any_active.py`

```python
from datetime import datetime, timezone

from app.ledger.consent import has_any_active
from app.ledger.schema import ConsentGrant, ConsentPurpose


def _grant(**kw):
    base = dict(
        id="g1", candidate_id="c1", org_id=None, purpose=ConsentPurpose.LEDGER_READ,
        granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc), revoked_at=None,
    )
    base.update(kw)
    return ConsentGrant(**base)


AT = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_active_grant_allows():
    d = has_any_active([_grant()], purpose=ConsentPurpose.LEDGER_READ, at=AT)
    assert d.allowed and d.grant_id == "g1"


def test_org_specific_grant_still_counts():
    d = has_any_active([_grant(org_id="orgX")], purpose=ConsentPurpose.LEDGER_READ, at=AT)
    assert d.allowed  # org-agnostic: any org's grant is enough for platform materialization


def test_expired_grant_denied():
    d = has_any_active([_grant()], purpose=ConsentPurpose.LEDGER_READ,
                       at=datetime(2028, 1, 1, tzinfo=timezone.utc))
    assert not d.allowed and d.grant_id is None


def test_revoked_before_at_denied():
    g = _grant(revoked_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert not has_any_active([g], purpose=ConsentPurpose.LEDGER_READ, at=AT).allowed


def test_point_in_time_before_revocation_allows():
    g = _grant(revoked_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    at = datetime(2026, 3, 1, tzinfo=timezone.utc)  # asked before the revocation instant
    assert has_any_active([g], purpose=ConsentPurpose.LEDGER_READ, at=at).allowed


def test_wrong_purpose_excluded():
    g = _grant(purpose=ConsentPurpose.LEDGER_WRITE)
    assert not has_any_active([g], purpose=ConsentPurpose.LEDGER_READ, at=AT).allowed
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_consent_has_any_active.py -q`
Expected: FAIL (`ImportError: cannot import name 'has_any_active'`).

- [ ] **Step 3: Implement.** Append to `app/ledger/consent.py`:

```python
def has_any_active(
    grants: Sequence[ConsentGrant], *, purpose: ConsentPurpose, at: datetime
) -> ConsentDecision:
    """Org-agnostic active-grant check for platform-internal materialization.

    Unlike ``check_consent`` this ignores grant.org_id: the candidate opting any
    reader in (org-specific or wildcard) is a sufficient basis for the platform's
    own feature materialization. Same active-window rules and deterministic
    ``_selection_key`` tie-break."""
    moment = as_utc(at)
    active = [
        g for g in grants
        if g.purpose == purpose
        and as_utc(g.granted_at) <= moment
        and as_utc(g.expires_at) > moment
        and (g.revoked_at is None or as_utc(g.revoked_at) > moment)
    ]
    if not active:
        return ConsentDecision(
            allowed=False,
            reason=f"no active consent for purpose '{purpose.value}'",
        )
    best = min(active, key=_selection_key)
    return ConsentDecision(
        allowed=True,
        reason=f"active grant {best.id} covers purpose '{purpose.value}' (any org)",
        grant_id=best.id,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_consent_has_any_active.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ledger/consent.py tests/test_consent_has_any_active.py
git commit -m "feat(s42): consent.has_any_active (org-agnostic ledger_read check for materialization)"
```

---

### Task 4: `LedgerStore.materialization_consent` (audited gate)

**Files:**
- Modify: `app/ledger/store.py`
- Test: `tests/test_ledger_store_materialize_consent.py`

**Interfaces:**
- Consumes: `has_any_active` (Task 3), `_grants_for`, `_audit`, `consent_logic.as_utc`, `ConsentPurpose`.
- Produces: `LedgerStore.materialization_consent(candidate_id: str, *, at: Optional[datetime] = None) -> ConsentDecision` — decides platform materialization consent (any active `ledger_read` grant at `at`), **audits `feature.materialize`** (actor `system`/`"platform"`, allowed & withheld both) in-txn; raises `LookupError` for an unknown candidate. **Does not raise on withheld** (returns the decision).

- [ ] **Step 1: Write the failing test** — `tests/test_ledger_store_materialize_consent.py`

```python
from datetime import datetime, timezone

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store

RESUME = "Jane Rao\nML Engineer\nSkills: Python\nEmail: jane@example.com\n"
AT = datetime(2026, 6, 1, tzinfo=timezone.utc)
G = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _setup():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    return cs, ls, cid


def test_allowed_with_active_read_grant():
    cs, ls, cid = _setup()
    org = ls.create_organization("Org A")
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id, now=G)
    d = ls.materialization_consent(cid, at=AT)
    assert d.allowed and d.grant_id
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "feature.materialize"]
    assert audits and audits[-1].details.get("allowed") is True


def test_withheld_without_grant_does_not_raise():
    cs, ls, cid = _setup()
    d = ls.materialization_consent(cid, at=AT)
    assert not d.allowed
    audits = [a for a in ls.audit_for_candidate(cid) if a.action == "feature.materialize"]
    assert audits and audits[-1].details.get("allowed") is False


def test_unknown_candidate_raises():
    cs, ls, cid = _setup()
    with pytest.raises(LookupError):
        ls.materialization_consent("nope", at=AT)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_ledger_store_materialize_consent.py -q`
Expected: FAIL (`AttributeError: ... 'materialization_consent'`).

- [ ] **Step 3: Implement.** In `app/ledger/store.py`, add the method to `LedgerStore` (place it just after `reputation_for_org`):

```python
    def materialization_consent(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> ConsentDecision:
        """Platform-internal materialization gate (S4.2): may the platform include
        this candidate's consent-tagged (ledger/reputation) features in the ML
        feature table at `at`? Basis = any active ledger_read grant (org-agnostic).
        Audits `feature.materialize` (allowed AND withheld) in the same
        transaction. Returns the decision — withheld does NOT raise (the caller
        still writes a valid row with those features nulled)."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_READ)
            decision = consent_logic.has_any_active(
                grants, purpose=ConsentPurpose.LEDGER_READ, at=moment
            )
            details = {"allowed": decision.allowed, "purpose": "ledger_read"}
            if decision.allowed:
                details["consent_id"] = decision.grant_id
            self._audit(
                session,
                actor_type="system",
                actor_id="platform",
                action="feature.materialize",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details=details,
            )
            session.commit()
            return decision
```

`ConsentDecision` is already imported in `store.py`; confirm the import list includes it (it does).

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_ledger_store_materialize_consent.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_materialize_consent.py
git commit -m "feat(s42): LedgerStore.materialization_consent (audited org-agnostic ledger_read gate)"
```

---

### Task 5: `ml_feature_vectors` ORM + migration 0007 + drift guard

**Files:**
- Create: `app/features/models.py`
- Create: `alembic/versions/0007_ml_feature_vectors.py`
- Modify: `alembic/env.py`
- Modify: `tests/conftest.py` (import the model)
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Produces: `app.features.models.FeatureVectorRow` — table `ml_feature_vectors` with columns `id, candidate_id (CASCADE FK→candidates.id, indexed), as_of, view_name, view_version, feature_values (JSON), missing (JSON), consent_state (JSON), materialized_at, created_at`; unique `(candidate_id, as_of, view_name, view_version)`; index `(view_name, view_version)`.

> **Column name note:** the JSON payload column is `feature_values`, **not** `values` — `values` is a reserved word in SQLite/Postgres. `missing`/`consent_state` are safe.

- [ ] **Step 1: Write the failing test.** Edit `tests/test_migrations.py`:

Add the import near the other model imports:
```python
import app.features.models  # noqa: F401 — populate Base.metadata
```

Add the new table to the existence assertion in `test_upgrade_head_creates_candidate_tables` (after the ledger block):
```python
    assert "ml_feature_vectors" in names
```

Add a `FEATURE_TABLES` constant next to `LEDGER_TABLES`:
```python
FEATURE_TABLES = ("ml_feature_vectors",)
```

In `test_migrated_indexes_match_orm` and `test_migrated_fks_and_nullability_match_orm`, change the loop header from `for table in LEDGER_TABLES:` to:
```python
    for table in LEDGER_TABLES + FEATURE_TABLES:
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_migrations.py -q`
Expected: FAIL — `ModuleNotFoundError: app.features.models` (model not created yet) or, once the module exists but the migration doesn't, `add_table` drift + missing-table assertion.

- [ ] **Step 3: Create the ORM model** — `app/features/models.py`

```python
"""ORM row for materialized ML feature vectors (PI-4 / S4.2). Postgres-shaped.

One compact row per (candidate_id, as_of, view_name, view_version): the values a
FeatureView produced over a point-in-time context, plus which came back null and
the consent decision that governed the consent-tagged ones. Candidate-linked with
an ondelete=CASCADE FK so DPDP erasure (CandidateStore.delete_candidate) sweeps
materialized rows with the candidate — no separate erasure path.

The JSON payload column is `feature_values` (not `values`, a reserved word)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeatureVectorRow(Base):
    __tablename__ = "ml_feature_vectors"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "as_of", "view_name", "view_version",
            name="uq_ml_feature_vectors_cut",
        ),
        Index("ix_ml_feature_vectors_view", "view_name", "view_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    view_name: Mapped[str] = mapped_column(String(64))
    view_version: Mapped[int] = mapped_column(Integer)
    feature_values: Mapped[dict] = mapped_column(JSON, default=dict)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    consent_state: Mapped[dict] = mapped_column(JSON, default=dict)
    materialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Create the migration** — `alembic/versions/0007_ml_feature_vectors.py`

```python
"""ml feature vectors: materialized feature-store table (S4.2)

Revision ID: 0007_ml_feature_vectors
Revises: 0006_org_reliability_weight
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

revision = "0007_ml_feature_vectors"
down_revision = "0006_org_reliability_weight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_feature_vectors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_name", sa.String(length=64), nullable=False),
        sa.Column("view_version", sa.Integer(), nullable=False),
        sa.Column("feature_values", sa.JSON(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("consent_state", sa.JSON(), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "candidate_id", "as_of", "view_name", "view_version",
            name="uq_ml_feature_vectors_cut",
        ),
    )
    op.create_index(
        "ix_ml_feature_vectors_candidate_id", "ml_feature_vectors", ["candidate_id"]
    )
    op.create_index(
        "ix_ml_feature_vectors_view", "ml_feature_vectors", ["view_name", "view_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_ml_feature_vectors_view", table_name="ml_feature_vectors")
    op.drop_index("ix_ml_feature_vectors_candidate_id", table_name="ml_feature_vectors")
    op.drop_table("ml_feature_vectors")
```

- [ ] **Step 5: Wire imports.** In `alembic/env.py`, add below `import app.candidates.models`:
```python
import app.ledger.models  # noqa: F401 — register ledger tables on Base.metadata
import app.features.models  # noqa: F401 — register feature tables on Base.metadata
```
(If `app.ledger.models` is already imported there, only add the features line.)

In `tests/conftest.py`, add below `import app.ledger.models`:
```python
import app.features.models  # noqa: F401 — populate Base.metadata with feature tables
```

- [ ] **Step 6: Run the migration + drift guard**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS — new table created; `compare_metadata` finds no structural drift; the index guard finds `ix_ml_feature_vectors_candidate_id` and `ix_ml_feature_vectors_view`; the FK/nullability guard confirms `candidate_id` CASCADE + all columns NOT NULL.

- [ ] **Step 7: Run the whole suite** (the new conftest import must not break anything)

Run: `pytest -q`
Expected: PASS (all prior tests + Tasks 1-4).

- [ ] **Step 8: Commit**

```bash
git add app/features/models.py alembic/versions/0007_ml_feature_vectors.py alembic/env.py tests/conftest.py tests/test_migrations.py
git commit -m "feat(s42): ml_feature_vectors table + migration 0007 + drift guard"
```

---

### Task 6: Materializer — `MaterializedVector` + `materialize_candidate`/`materialize_all`

**Files:**
- Create: `app/features/materialize.py`
- Test: `tests/test_features_materialize.py`

**Interfaces:**
- Consumes: `build_context` (Task 2), `LedgerStore.materialization_consent` (Task 4), `FeatureRegistry.compute_view`, `FeatureView.resolve`, `FeatureVector` (S4.1).
- Produces:
  - `MaterializedVector` — frozen dataclass `(vector: FeatureVector, consent_state: dict, materialized_at: datetime)`.
  - `materialize_candidate(candidate_id, *, view, registry, as_of=None, candidate_store, report_store, ledger_store) -> Optional[MaterializedVector]`.
  - `materialize_all(candidate_ids, *, view, registry, as_of=None, candidate_store, report_store, ledger_store) -> list[MaterializedVector]`.

- [ ] **Step 1: Write the failing test** — `tests/test_features_materialize.py`

```python
from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import MaterializedVector, materialize_candidate
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark, SQL\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _setup():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    rs = InMemoryReportStore()
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    return cs, ls, rs, cid


def _view_reg():
    reg = get_feature_registry()
    return reg, default_view(reg, settings=_settings())


def test_absent_candidate_returns_none():
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    assert materialize_candidate("nope", view=view, registry=reg, as_of=T,
                                 candidate_store=cs, report_store=rs, ledger_store=ls) is None


def test_masks_consent_features_when_withheld():
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    assert isinstance(mv, MaterializedVector)
    assert mv.consent_state["allowed"] is False
    assert mv.vector.values["ledger.interview_record_count"] is None
    assert mv.vector.values["reputation.band"] is None
    assert "ledger.interview_record_count" in mv.vector.missing
    assert mv.vector.values["candidate.num_skills"] is not None  # first-party intact


def test_keeps_consent_features_when_granted():
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    org = ls.create_organization("Org A")
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id,
                     now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    assert mv.consent_state["allowed"] is True and mv.consent_state["consent_id"]
    assert mv.vector.values["ledger.interview_record_count"] == 0   # present, not masked
    assert mv.vector.values["reputation.band"] == "insufficient_data"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_features_materialize.py -q`
Expected: FAIL (`ModuleNotFoundError: app.features.materialize`).

- [ ] **Step 3: Implement** — `app/features/materialize.py`

```python
"""Materialize a FeatureView over a point-in-time context (PI-4 / S4.2).

Pure orchestration: slice the context (build_context), compute the view, then
apply the per-candidate consent decision — consent-tagged features (ledger.* /
reputation.*, i.e. spec.requires_consent) are nulled unless an active ledger_read
grant governs the candidate at as_of. First-party features always survive. The
consent decision itself is audited in LedgerStore.materialization_consent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from app.features.context import build_context
from app.features.registry import FeatureRegistry
from app.features.schema import FeatureVector, FeatureView


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MaterializedVector:
    vector: FeatureVector
    consent_state: dict
    materialized_at: datetime


def materialize_candidate(
    candidate_id: str,
    *,
    view: FeatureView,
    registry: FeatureRegistry,
    as_of: Optional[datetime] = None,
    candidate_store,
    report_store,
    ledger_store,
) -> Optional[MaterializedVector]:
    ctx = build_context(
        candidate_id,
        candidate_store=candidate_store,
        report_store=report_store,
        ledger_store=ledger_store,
        as_of=as_of,
    )
    if ctx is None:
        return None

    vector = registry.compute_view(view, ctx)
    decision = ledger_store.materialization_consent(candidate_id, at=ctx.as_of)

    if decision.allowed:
        consent_state = {"allowed": True, "consent_id": decision.grant_id}
    else:
        consent_state = {"allowed": False, "reason": decision.reason}
        consent_names = [
            rf.spec.name for rf in view.resolve(registry) if rf.spec.requires_consent
        ]
        if consent_names:
            values = dict(vector.values)
            missing = list(vector.missing)
            for name in consent_names:
                values[name] = None
                if name not in missing:
                    missing.append(name)
            vector = vector.model_copy(update={"values": values, "missing": tuple(missing)})

    return MaterializedVector(vector=vector, consent_state=consent_state, materialized_at=_utcnow())


def materialize_all(
    candidate_ids: Iterable[str],
    *,
    view: FeatureView,
    registry: FeatureRegistry,
    as_of: Optional[datetime] = None,
    candidate_store,
    report_store,
    ledger_store,
) -> list[MaterializedVector]:
    out: list[MaterializedVector] = []
    for cid in candidate_ids:
        mv = materialize_candidate(
            cid, view=view, registry=registry, as_of=as_of,
            candidate_store=candidate_store, report_store=report_store, ledger_store=ledger_store,
        )
        if mv is not None:
            out.append(mv)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_features_materialize.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/materialize.py tests/test_features_materialize.py
git commit -m "feat(s42): materializer — view over point-in-time context + consent masking"
```

---

### Task 7: `FeatureStore` — persist / read `ml_feature_vectors`

**Files:**
- Create: `app/features/store.py`
- Test: `tests/test_feature_store.py`

**Interfaces:**
- Consumes: `FeatureVectorRow` (Task 5), `MaterializedVector` (Task 6), `FeatureVector`, `app.ledger.consent.as_utc`, `app.core.db.make_engine/make_session_factory`, `app.core.config.get_settings`.
- Produces:
  - `FeatureStore(session_factory)` with `upsert_vector(mv) -> str`, `get_vector(candidate_id, *, view_name, view_version, as_of) -> Optional[MaterializedVector]`, `vectors_for_view(view_name, view_version, *, as_of=None) -> list[MaterializedVector]`.
  - `build_feature_store(settings=None) -> FeatureStore` (on `candidates_db_url`).

> **as_of key handling:** store + query `as_of` as **naive-UTC** (`as_utc(dt).replace(tzinfo=None)`) so the unique-cut equality lookup round-trips exactly on SQLite (which drops tzinfo). Reconstruct aware-UTC via `as_utc` when building the `FeatureVector`.

- [ ] **Step 1: Write the failing test** — `tests/test_feature_store.py`

```python
from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nML Engineer\nSkills: Python, SQL\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _make_mv(cs, ls, rs):
    reg = get_feature_registry()
    view = default_view(reg, settings=_settings())
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    return cid, view, mv


def test_upsert_and_get_roundtrip():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    got = fs.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T)
    assert got is not None
    assert got.vector.values == mv.vector.values
    assert got.consent_state["allowed"] is False


def test_upsert_is_idempotent_on_same_cut():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    fs.upsert_vector(mv)
    assert len(fs.vectors_for_view(view.name, view.version)) == 1


def test_delete_candidate_cascades_vectors():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    cs.delete_candidate(cid)
    assert fs.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_feature_store.py -q`
Expected: FAIL (`ModuleNotFoundError: app.features.store`).

- [ ] **Step 3: Implement** — `app/features/store.py`

```python
"""Persist / read materialized feature vectors (PI-4 / S4.2).

Shares candidates_db_url (one metadata root, one Alembic env). Schema is
Alembic's job. The unique cut (candidate_id, as_of, view_name, view_version) makes
re-materialization an idempotent upsert. as_of is stored + queried as naive-UTC so
the equality lookup round-trips on SQLite (which drops tzinfo)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.features.materialize import MaterializedVector
from app.features.models import FeatureVectorRow
from app.features.schema import FeatureVector
from app.ledger.consent import as_utc


def _key_dt(dt: datetime) -> datetime:
    return as_utc(dt).replace(tzinfo=None)


def _to_mv(row: FeatureVectorRow) -> MaterializedVector:
    return MaterializedVector(
        vector=FeatureVector(
            candidate_id=row.candidate_id,
            as_of=as_utc(row.as_of),
            view_name=row.view_name,
            view_version=row.view_version,
            values=dict(row.feature_values or {}),
            missing=tuple(row.missing or ()),
        ),
        consent_state=dict(row.consent_state or {}),
        materialized_at=as_utc(row.materialized_at),
    )


class FeatureStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def upsert_vector(self, mv: MaterializedVector) -> str:
        v = mv.vector
        with self._session_factory() as session:
            row = session.execute(
                select(FeatureVectorRow).where(
                    FeatureVectorRow.candidate_id == v.candidate_id,
                    FeatureVectorRow.as_of == _key_dt(v.as_of),
                    FeatureVectorRow.view_name == v.view_name,
                    FeatureVectorRow.view_version == v.view_version,
                )
            ).scalar_one_or_none()
            if row is None:
                row = FeatureVectorRow(
                    candidate_id=v.candidate_id,
                    as_of=_key_dt(v.as_of),
                    view_name=v.view_name,
                    view_version=v.view_version,
                )
                session.add(row)
            row.feature_values = dict(v.values)
            row.missing = list(v.missing)
            row.consent_state = dict(mv.consent_state)
            row.materialized_at = _key_dt(mv.materialized_at)
            session.flush()
            rid = row.id
            session.commit()
            return rid

    def get_vector(
        self, candidate_id: str, *, view_name: str, view_version: int, as_of: datetime
    ) -> Optional[MaterializedVector]:
        with self._session_factory() as session:
            row = session.execute(
                select(FeatureVectorRow).where(
                    FeatureVectorRow.candidate_id == candidate_id,
                    FeatureVectorRow.as_of == _key_dt(as_of),
                    FeatureVectorRow.view_name == view_name,
                    FeatureVectorRow.view_version == view_version,
                )
            ).scalar_one_or_none()
            return _to_mv(row) if row else None

    def vectors_for_view(
        self, view_name: str, view_version: int, *, as_of: Optional[datetime] = None
    ) -> list[MaterializedVector]:
        with self._session_factory() as session:
            q = select(FeatureVectorRow).where(
                FeatureVectorRow.view_name == view_name,
                FeatureVectorRow.view_version == view_version,
            )
            if as_of is not None:
                q = q.where(FeatureVectorRow.as_of == _key_dt(as_of))
            q = q.order_by(FeatureVectorRow.candidate_id)
            return [_to_mv(r) for r in session.execute(q).scalars().all()]


def build_feature_store(settings: Optional[Settings] = None) -> FeatureStore:
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return FeatureStore(make_session_factory(engine))
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_feature_store.py -q`
Expected: PASS (3 tests, including cascade-on-erase).

- [ ] **Step 5: Commit**

```bash
git add app/features/store.py tests/test_feature_store.py
git commit -m "feat(s42): FeatureStore — idempotent upsert + read of ml_feature_vectors"
```

---

### Task 8: Export — wide CSV (stdlib) + guarded parquet

**Files:**
- Create: `app/features/export.py`
- Test: `tests/test_features_export.py`

**Interfaces:**
- Consumes: `MaterializedVector` (Task 6), `FeatureView`, `FeatureRegistry`, `app.ledger.consent.as_utc`.
- Produces:
  - `ParquetUnavailable(RuntimeError)`.
  - `export_view_csv(rows, *, view, path, null_token="") -> None` — wide pivot, header `candidate_id, as_of, view_name, view_version, <features in view.members order>`.
  - `export_view_parquet(rows, *, view, registry, path) -> None` — same columns typed per `spec.dtype`; raises `ParquetUnavailable` if pyarrow is not importable.

- [ ] **Step 1: Write the failing test** — `tests/test_features_export.py`

```python
import csv
import importlib.util
from datetime import datetime, timezone

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.export import ParquetUnavailable, export_view_csv, export_view_parquet
from app.features.materialize import materialize_candidate
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nML Engineer\nSkills: Python, SQL\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _mv():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    reg = get_feature_registry()
    view = default_view(reg, settings=_settings())
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    return reg, view, mv, cid


def test_csv_header_is_wide_and_in_view_order(tmp_path):
    reg, view, mv, cid = _mv()
    path = tmp_path / "features.csv"
    export_view_csv([mv], view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    assert header[:4] == ["candidate_id", "as_of", "view_name", "view_version"]
    assert header[4:] == [name for name, _ in view.members]
    assert len(rows) == 2  # header + one data row


def test_csv_masks_consent_cell_and_keeps_first_party(tmp_path):
    reg, view, mv, cid = _mv()
    path = tmp_path / "features.csv"
    export_view_csv([mv], view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        header, row = list(csv.reader(f))
    col = {name: row[i] for i, name in enumerate(header)}
    assert col["candidate_id"] == cid
    assert col["ledger.interview_record_count"] == ""      # consent-withheld → empty
    assert col["candidate.num_skills"] != ""               # first-party present


def test_parquet_guarded(tmp_path):
    reg, view, mv, cid = _mv()
    path = tmp_path / "features.parquet"
    if importlib.util.find_spec("pyarrow") is None:
        with pytest.raises(ParquetUnavailable):
            export_view_parquet([mv], view=view, registry=reg, path=str(path))
    else:
        export_view_parquet([mv], view=view, registry=reg, path=str(path))
        assert path.exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_features_export.py -q`
Expected: FAIL (`ModuleNotFoundError: app.features.export`).

- [ ] **Step 3: Implement** — `app/features/export.py`

```python
"""Export materialized feature vectors to wide CSV / parquet (PI-4 / S4.2).

The 'wide' deliverable is a pivot: fixed columns then one column per feature in
view.members order. Values are already consent-masked at materialization, so an
exported file can never leak a consent-withheld value. CSV uses the stdlib;
parquet requires pyarrow (optional) and raises ParquetUnavailable if absent."""

from __future__ import annotations

import csv
from typing import Iterable

from app.features.materialize import MaterializedVector
from app.features.registry import FeatureRegistry
from app.features.schema import FeatureDType, FeatureView
from app.ledger.consent import as_utc

_FIXED = ("candidate_id", "as_of", "view_name", "view_version")


class ParquetUnavailable(RuntimeError):
    """pyarrow is not installed; parquet export is unavailable."""


def _columns(view: FeatureView) -> list[str]:
    return list(_FIXED) + [name for name, _ in view.members]


def _row_cells(mv: MaterializedVector, view: FeatureView, null_token):
    v = mv.vector
    fixed = {
        "candidate_id": v.candidate_id,
        "as_of": as_utc(v.as_of).isoformat(),
        "view_name": v.view_name,
        "view_version": v.view_version,
    }
    cells = []
    for col in _columns(view):
        if col in fixed:
            cells.append(fixed[col])
        else:
            val = v.values.get(col)
            cells.append(null_token if val is None else val)
    return cells


def export_view_csv(rows: Iterable[MaterializedVector], *, view: FeatureView, path: str, null_token: str = "") -> None:
    columns = _columns(view)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for mv in rows:
            writer.writerow(_row_cells(mv, view, null_token))


def _pa_type(pa, dtype: FeatureDType):
    if dtype is FeatureDType.NUMERIC:
        return pa.float64()
    if dtype is FeatureDType.INTEGER:
        return pa.int64()
    if dtype is FeatureDType.BOOLEAN:
        return pa.bool_()
    return pa.string()  # categorical / ordinal


def export_view_parquet(rows: Iterable[MaterializedVector], *, view: FeatureView, registry: FeatureRegistry, path: str) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # optional dependency
        raise ParquetUnavailable(
            "parquet export needs pyarrow; install it (optional extra) or use export_view_csv"
        ) from exc

    rows = list(rows)
    columns = _columns(view)
    specs = {rf.spec.name: rf.spec for rf in view.resolve(registry)}
    data: dict[str, list] = {c: [] for c in columns}
    for mv in rows:
        for col, cell in zip(columns, _row_cells(mv, view, None)):
            data[col].append(cell)

    arrays = {}
    for col in columns:
        if col == "view_version":
            arrays[col] = pa.array(data[col], type=pa.int64())
        elif col in ("candidate_id", "as_of", "view_name"):
            arrays[col] = pa.array(data[col], type=pa.string())
        else:
            arrays[col] = pa.array(data[col], type=_pa_type(pa, specs[col].dtype))
    pq.write_table(pa.table(arrays), path)
```

- [ ] **Step 4: Run to verify it passes** (pyarrow absent ⇒ the parquet test asserts `ParquetUnavailable`)

Run: `pytest tests/test_features_export.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/features/export.py tests/test_features_export.py
git commit -m "feat(s42): wide CSV export (stdlib) + guarded parquet export"
```

---

### Task 9: FEATURES.md S4.2 section + `scripts/smoke_s42.py` + full suite

**Files:**
- Modify: `FEATURES.md`
- Create: `scripts/smoke_s42.py`

**Interfaces:**
- Consumes: everything above; the HTTP surface (`POST /candidates`, `/ledger/orgs`, `/ledger/candidates/{id}/consent`, `/ledger/records`, `/ledger/coding-rounds`) as used by `scripts/smoke_s41.py`.

- [ ] **Step 1: FEATURES.md.** Append an `## S4.2 — Materialization` section documenting: the point-in-time slicer (`profile_as_of` + `as_of` on every axis), the consent gate (`has_any_active` / `materialization_consent`, per-candidate, audited `feature.materialize`, withheld→null), the `ml_feature_vectors` table (compact row-per-vector, JSON `feature_values`, idempotent cut, CASCADE erasure), and the wide CSV/optional-parquet export. Note the S4.3 seam (per-feature indexing/projection) and that consent-tagged values are masked **before** persistence.

- [ ] **Step 2: Write the smoke** — `scripts/smoke_s42.py`. Mirror `scripts/smoke_s41.py`'s harness (scratch DB migrated to head, uvicorn boot on a distinct port, `httpx` health-wait, admin `X-API-Key`). Use **PORT = 8042**. The S4.2-specific body:

```python
"""S4.2 smoke: materialize + persist + export feature vectors, consent-gated and
point-in-time. Boots uvicorn on a migrated scratch DB, POSTs two fixture resumes
(A consented for ledger_read with FUTURE-dated ledger rows; B no consent, no
rows), then opens the stores directly to materialize, persist, and export.
LLM-free. Run from the repo root: python scripts/smoke_s42.py
"""

import os, subprocess, sys, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.candidates.store import build_candidate_store
from app.features import default_view, get_feature_registry
from app.features.export import ParquetUnavailable, export_view_csv, export_view_parquet
from app.features.materialize import materialize_candidate
from app.features.store import build_feature_store
from app.ledger.store import build_ledger_store
from app.services.report_store import build_report_store

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8042
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
FUTURE = "2027-01-01T10:00:00+00:00"   # ledger rows dated AFTER the `now` cut


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s42.db").as_posix()
    reports = (scratch / "reports.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

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
            cidA = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()["candidate_id"]
            altB = ("Priya Nair\nBackend Engineer\nEmail: priya.noledger@example.com\n"
                    "Skills: Python, PostgreSQL\nExperience: Backend Engineer at Acme, 2021-2024\n")
            cidB = c.post("/candidates", json={"resume_text": altB}, headers=admin_h).json()["candidate_id"]

            org = c.post("/ledger/orgs", json={"name": "Org A"}, headers=admin_h).json()
            oid, okey = org["org"]["id"], org["api_key"]
            oh = {"X-Org-Key": okey}
            # A: write + read consent; two hired records + one coding round, FUTURE-dated
            for purpose in ("ledger_write", "ledger_read"):
                c.post(f"/ledger/candidates/{cidA}/consent",
                       json={"purpose": purpose, "org_id": oid}, headers=admin_h)
            for _ in range(2):
                c.post("/ledger/records",
                       json={"candidate_id": cidA, "stage": "hm", "outcome": "hired",
                             "interviewed_at": FUTURE}, headers=oh)
            c.post("/ledger/coding-rounds",
                   json={"candidate_id": cidA, "platform": "hackerrank", "score": 90.0,
                         "max_score": 100.0, "percentile": 92.0, "taken_at": FUTURE}, headers=oh)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    settings = Settings(_env_file=None, openrouter_api_key="",
                        candidates_db_url=url, report_db_path=reports, vectorstore_backend="memory")
    cs, ls, rs = build_candidate_store(settings), build_ledger_store(settings), build_report_store(settings)
    fs = build_feature_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=400)                    # after the FUTURE-dated rows

    mvA_now = materialize_candidate(cidA, view=view, registry=reg, as_of=now,
                                    candidate_store=cs, report_store=rs, ledger_store=ls)
    mvA_later = materialize_candidate(cidA, view=view, registry=reg, as_of=later,
                                      candidate_store=cs, report_store=rs, ledger_store=ls)
    mvB = materialize_candidate(cidB, view=view, registry=reg, as_of=now,
                                candidate_store=cs, report_store=rs, ledger_store=ls)

    fs.upsert_vector(mvA_now)
    fs.upsert_vector(mvB)

    csv_path = scratch / "features.csv"
    export_view_csv(fs.vectors_for_view(view.name, view.version, as_of=now), view=view, path=str(csv_path))
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")

    parquet_ok = None
    try:
        export_view_parquet([mvA_now], view=view, registry=reg, path=str(scratch / "features.parquet"))
        parquet_ok = True
    except ParquetUnavailable:
        parquet_ok = "skipped (pyarrow absent)"

    cs.delete_candidate(cidA)
    erased = fs.get_vector(cidA, view_name=view.name, view_version=view.version, as_of=now)

    checks = {
        "A consent allowed at now": mvA_now.consent_state["allowed"] is True,
        "A ledger count 0 at now (point-in-time; rows are future)":
            mvA_now.vector.values.get("ledger.interview_record_count") == 0,
        "A ledger count 2 later (future rows now visible)":
            mvA_later.vector.values.get("ledger.interview_record_count") == 2,
        "A best percentile 92 later":
            mvA_later.vector.values.get("ledger.best_coding_percentile") == 92.0,
        "B consent withheld": mvB.consent_state["allowed"] is False,
        "B consent feature masked to null":
            mvB.vector.values.get("ledger.interview_record_count") is None,
        "B first-party present": mvB.vector.values.get("candidate.num_skills") is not None,
        "persisted two vectors at now":
            len(fs.vectors_for_view(view.name, view.version, as_of=now)) == 2,
        "csv header wide + view order":
            header[:4] == ["candidate_id", "as_of", "view_name", "view_version"]
            and header[4:] == [n for n, _ in view.members],
        "parquet guarded": parquet_ok is True or isinstance(parquet_ok, str),
        "DPDP erase cascades vector": erased is None,
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    print(f"  parquet: {parquet_ok}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the smoke**

Run: `python scripts/smoke_s42.py`
Expected: every check `OK`, `SMOKE OK`, exit 0. `parquet: skipped (pyarrow absent)` is acceptable (D3).

- [ ] **Step 4: Run the whole suite**

Run: `pytest -q`
Expected: all green (~537 tests: 507 + Tasks 1-8's ~30 new).

- [ ] **Step 5: Commit**

```bash
git add FEATURES.md scripts/smoke_s42.py
git commit -m "docs(s42): FEATURES.md S4.2 section + smoke_s42 (materialize/persist/export)"
```

---

## Self-review

**Spec coverage** (each spec §3 unit → task):
- §3.1 point-in-time slicer (`profile_as_of`, `build_context`) → Tasks 1, 2. ✓
- §3.2 consent gate (`has_any_active`, `materialization_consent`) → Tasks 3, 4. ✓
- §3.3 materializer (`MaterializedVector`, `materialize_candidate/_all`) → Task 6. ✓
- §3.4 storage (`FeatureVectorRow`, migration, `FeatureStore`) → Tasks 5, 7. ✓
- §3.5 export (CSV + guarded parquet, `ParquetUnavailable`) → Task 8. ✓
- §3.6 config/docs/smoke → Task 9 (config: reuse `feat_default_view`, no change needed — verified present). ✓
- §4 point-in-time proof → Task 9 smoke step (future-dated rows invisible at `now`) + Task 2 unit test. ✓
- §5 testing → each task's tests; drift guard extended in Task 5. ✓
- DPDP cascade → Task 5 (FK) + Task 7 cascade test + Task 9 smoke erase. ✓

**Placeholder scan:** no TBD/TODO; every code step has real code; the smoke mirrors an existing, named script with its S4.2 body fully written. ✓

**Type consistency:** `MaterializedVector(vector, consent_state, materialized_at)` defined in Task 6, consumed identically in Tasks 7-9. `FeatureVector.values`/`.missing`/`.view_name`/`.view_version`/`.as_of`/`.candidate_id` match S4.1 `schema.py`. `has_any_active(grants, *, purpose, at)` and `materialization_consent(candidate_id, *, at)` signatures match between definition and callers. Column `feature_values` used consistently in model, migration, store, and (via `values` mapping) export. View accessed as `view.members`/`view.name`/`view.version`/`view.resolve(registry)` per S4.1. ✓

## Execution Handoff

Plan complete. Recommended: **subagent-driven** (fresh subagent per task + two-stage review), matching how S4.1/S3.4 shipped.
