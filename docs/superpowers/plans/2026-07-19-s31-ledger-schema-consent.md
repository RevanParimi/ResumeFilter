# S3.1 — Ledger Schema + DPDP Consent Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the cross-company evaluation ledger's data layer — `organizations`, `consent_grants`, `interview_records`, `evaluation_events`, `audit_log` — with a DPDP consent model (purpose-scoped, org-scoped, always-expiring, revocable, audited) enforced at write time in a new `LedgerStore`. No HTTP APIs (S3.2), no LLM anywhere.

**Architecture:** New peer subsystem `app/ledger/` beside `app/candidates/`: Pydantic contracts (`schema.py`), a pure clock-free consent decision module (`consent.py`), Postgres-shaped ORM rows on the shared `Base` (`models.py`), Alembic migration `0003_evaluation_ledger`, and a `LedgerStore` (`store.py`) that writes an audit row in the same transaction as every mutation and refuses interview-record submission without an active `ledger_write` consent. The ledger lives in the same DB as candidates (`candidates_db_url`, one metadata root, one Alembic env — per `app/core/db.py`'s design), so the existing DPDP candidate-erasure path sweeps ledger rows via `ondelete=CASCADE` FKs.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.x + Alembic on SQLite (PG-shaped), pytest (fully offline — no LLM in this sprint).

**Branch:** `s31-ledger-consent` (create from `main` before Task 1: `git checkout -b s31-ledger-consent`)

**Test count:** 350 green today → ~395 expected.

## Global Constraints

- DPDP by construction — every candidate-linked row (`consent_grants`, `interview_records`, `evaluation_events`, candidate-linked `audit_log` rows) carries an `ondelete="CASCADE"` FK to `candidates.id`; `CandidateStore.delete_candidate` erasure must provably sweep the ledger (tested, not assumed).
- Consent is purpose-scoped (one purpose per grant), org-scoped (`org_id` NULL = any member org), **always expiring** (`expires_at` NOT NULL; missing expiry gets `ledger_consent_default_ttl_days`), revocable (UPDATE `revoked_at`, never DELETE — audit needs the row), and audited (grant/revoke/submit each write an `audit_log` row in the same transaction).
- Write-time enforcement only in S3.1: `submit_interview_record` requires an active `ledger_write` grant and raises `ConsentError` otherwise. Query-time enforcement of `ledger_read` is S3.2 (API layer); the read helpers here are store primitives.
- Taxonomies (stage `screen/tech/coding/hm`, outcome, purpose) are **code constants** (StrEnums), not config. The only tunable is `ledger_consent_default_ttl_days` in `config.yaml`/`Settings` (no `DEE_` prefix in YAML).
- Deterministic, fully offline — no LLM anywhere in S3.1; smoke is key-less by design.
- Advisory principle unchanged: ledger records are shared facts for humans; nothing here changes verdicts, depth, or auto-rejects anything.
- SQLite returns **naive** datetimes from `DateTime(timezone=True)` columns; every consent-time comparison must coerce to aware UTC first (naive ⇒ assume UTC, matching how rows are written).
- Schema is Alembic's job (`alembic upgrade head`), never `create_all` in builders (tests may `create_all` on in-memory engines, matching existing test style).
- Commit messages: plain conventional commits, **no Co-Authored-By trailer**.
- `pytest -q` must be green at every commit.

## File Structure

- Create: `app/ledger/__init__.py` — empty package marker.
- Create: `app/ledger/schema.py` — StrEnum taxonomies + Pydantic contracts. One responsibility: the ledger's data contracts.
- Create: `app/ledger/consent.py` — pure consent decision logic (no I/O, no clock; caller passes `at`).
- Create: `app/ledger/models.py` — `*Row` ORM classes on the shared `Base`.
- Create: `alembic/versions/0003_evaluation_ledger.py` — the five tables + indexes.
- Create: `app/ledger/store.py` — `LedgerStore`, `ConsentError`, `build_ledger_store`.
- Modify: `app/core/config.py` + `config.yaml` — `ledger_consent_default_ttl_days`.
- Modify: `tests/test_migrations.py` — import ledger models; expect the new tables.
- Create: `scripts/smoke_s31.py` — scratch-DB migrate + full consent lifecycle + DPDP cascade proof.
- Create: `LEDGER.md` — subsystem doc (sibling to `CANDIDATES.md` / `FABRICATION.md`).
- Tests: `tests/test_ledger_schema.py`, `tests/test_ledger_consent.py`, `tests/test_ledger_models.py`, `tests/test_ledger_store.py`, `tests/test_ledger_store_records.py`.

---

### Task 1: Ledger contracts — taxonomies + Pydantic models

**Files:**
- Create: `app/ledger/__init__.py`
- Create: `app/ledger/schema.py`
- Test: `tests/test_ledger_schema.py`

**Interfaces:**
- Consumes: nothing (new package).
- Produces (imported by every later task from `app.ledger.schema`):
  `InterviewStage` (StrEnum: `screen/tech/coding/hm`), `InterviewOutcome` (StrEnum: `advanced/rejected/offer/hired/withdrawn/no_show`), `ConsentPurpose` (StrEnum: `ledger_write/ledger_read`), `Organization {id, name, status="active", created_at}`, `ConsentGrant {id, candidate_id, org_id: Optional[str]=None, purpose: ConsentPurpose, granted_at, expires_at, revoked_at: Optional[datetime]=None}`, `ConsentDecision {allowed: bool, reason: str, grant_id: Optional[str]=None}`, `InterviewRecord {id, org_id, candidate_id, consent_id, stage: InterviewStage, outcome: InterviewOutcome, interviewed_at, summary: Optional[str]=None, created_at}`, `EvaluationEvent {id, record_id, candidate_id, event_type, payload: dict={}, created_at}`, `AuditEntry {id, actor_type, actor_id: Optional[str]=None, action, entity_type, entity_id, candidate_id: Optional[str]=None, details: dict={}, created_at}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger_schema.py`:

```python
"""S3.1 contracts: ledger taxonomies + Pydantic models."""

from datetime import datetime, timedelta, timezone

from app.ledger.schema import (
    AuditEntry,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def test_stage_taxonomy():
    assert [s.value for s in InterviewStage] == ["screen", "tech", "coding", "hm"]


def test_outcome_taxonomy():
    assert [o.value for o in InterviewOutcome] == [
        "advanced", "rejected", "offer", "hired", "withdrawn", "no_show",
    ]


def test_consent_purposes():
    assert ConsentPurpose.LEDGER_WRITE == "ledger_write"
    assert ConsentPurpose.LEDGER_READ == "ledger_read"


def test_grant_defaults_and_scope():
    g = ConsentGrant(
        id="g1", candidate_id="c1", purpose="ledger_write",
        granted_at=NOW, expires_at=NOW + timedelta(days=365),
    )
    assert g.org_id is None          # None = any member org
    assert g.revoked_at is None
    assert g.purpose is ConsentPurpose.LEDGER_WRITE  # str coerces to enum


def test_decision_shape():
    d = ConsentDecision(allowed=False, reason="no active consent")
    assert d.grant_id is None
    ok = ConsentDecision(allowed=True, reason="active grant", grant_id="g1")
    assert ok.allowed and ok.grant_id == "g1"


def test_record_coerces_taxonomies():
    r = InterviewRecord(
        id="r1", org_id="o1", candidate_id="c1", consent_id="g1",
        stage="tech", outcome="advanced", interviewed_at=NOW, created_at=NOW,
    )
    assert r.stage is InterviewStage.TECH
    assert r.outcome is InterviewOutcome.ADVANCED
    assert r.summary is None


def test_event_and_audit_defaults():
    e = EvaluationEvent(id="e1", record_id="r1", candidate_id="c1",
                        event_type="score", created_at=NOW)
    assert e.payload == {}
    a = AuditEntry(id="a1", actor_type="org", action="record.submit",
                   entity_type="interview_record", entity_id="r1", created_at=NOW)
    assert a.actor_id is None and a.candidate_id is None and a.details == {}


def test_record_round_trips_json():
    r = InterviewRecord(
        id="r1", org_id="o1", candidate_id="c1", consent_id="g1",
        stage="coding", outcome="offer", interviewed_at=NOW,
        summary="strong systems round", created_at=NOW,
    )
    assert InterviewRecord.model_validate_json(r.model_dump_json()) == r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ledger'`

- [ ] **Step 3: Implement**

Create `app/ledger/__init__.py` (empty file).

Create `app/ledger/schema.py`:

```python
"""S3.1 ledger contracts — cross-company evaluation ledger data shapes.

Taxonomies (stage/outcome/purpose) are code constants, not config: changing
them is a reviewed schema decision, never a deploy-time tunable. DPDP
framing: a consent grant is purpose-scoped (exactly one purpose per grant),
org-scoped (a specific member org, or None = any member org), always
expiring, and revocable at any time. Revocation keeps the row so the audit
trail survives; DPDP *erasure* deletes it (cascades from the candidate).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class InterviewStage(StrEnum):
    SCREEN = "screen"
    TECH = "tech"
    CODING = "coding"
    HM = "hm"


class InterviewOutcome(StrEnum):
    ADVANCED = "advanced"
    REJECTED = "rejected"
    OFFER = "offer"
    HIRED = "hired"
    WITHDRAWN = "withdrawn"
    NO_SHOW = "no_show"


class ConsentPurpose(StrEnum):
    """What a grant authorizes. ledger_write = an org may submit interview
    records about the candidate; ledger_read = an org may query the
    candidate's ledger history (enforced at query time in S3.2)."""

    LEDGER_WRITE = "ledger_write"
    LEDGER_READ = "ledger_read"


class Organization(BaseModel):
    id: str
    name: str
    status: str = "active"  # active | suspended
    created_at: datetime


class ConsentGrant(BaseModel):
    id: str
    candidate_id: str
    org_id: Optional[str] = None  # None = any member organization
    purpose: ConsentPurpose
    granted_at: datetime
    expires_at: datetime  # always expires; DPDP forbids perpetual consent
    revoked_at: Optional[datetime] = None


class ConsentDecision(BaseModel):
    allowed: bool
    reason: str
    grant_id: Optional[str] = None  # the grant that authorized, when allowed


class InterviewRecord(BaseModel):
    id: str
    org_id: str
    candidate_id: str
    consent_id: str  # the grant this record was submitted under
    stage: InterviewStage
    outcome: InterviewOutcome
    interviewed_at: datetime
    summary: Optional[str] = None
    created_at: datetime


class EvaluationEvent(BaseModel):
    id: str
    record_id: str
    candidate_id: str
    event_type: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class AuditEntry(BaseModel):
    id: str
    actor_type: str  # "org" | "candidate" | "system"
    actor_id: Optional[str] = None
    action: str  # e.g. "consent.grant", "consent.revoke", "record.submit"
    entity_type: str
    entity_id: str
    candidate_id: Optional[str] = None
    details: dict = Field(default_factory=dict)
    created_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger_schema.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite, then commit**

Run: `pytest -q` — expected: 358 passed.

```bash
git add app/ledger/__init__.py app/ledger/schema.py tests/test_ledger_schema.py
git commit -m "feat(ledger): S3.1 contracts - taxonomies, consent grant/decision, record/event/audit shapes"
```

---

### Task 2: Pure consent decision logic

**Files:**
- Create: `app/ledger/consent.py`
- Test: `tests/test_ledger_consent.py`

**Interfaces:**
- Consumes: `ConsentDecision`, `ConsentGrant`, `ConsentPurpose` from `app.ledger.schema` (Task 1).
- Produces: `as_utc(dt: datetime) -> datetime` (naive ⇒ assume UTC), `is_grant_active(grant: ConsentGrant, *, org_id: str, purpose: ConsentPurpose, at: datetime) -> bool`, `check_consent(grants: Sequence[ConsentGrant], *, org_id: str, purpose: ConsentPurpose, at: datetime) -> ConsentDecision`. Task 5/6's store calls these via `from app.ledger import consent`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger_consent.py`:

```python
"""S3.1 pure consent logic: purpose/org scope, expiry, revocation, tz coercion."""

from datetime import datetime, timedelta, timezone

from app.ledger.consent import as_utc, check_consent, is_grant_active
from app.ledger.schema import ConsentGrant, ConsentPurpose

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def grant(**over) -> ConsentGrant:
    base = dict(
        id="g1", candidate_id="c1", org_id=None, purpose="ledger_write",
        granted_at=NOW - timedelta(days=1), expires_at=NOW + timedelta(days=364),
        revoked_at=None,
    )
    base.update(over)
    return ConsentGrant(**base)


def test_active_grant_allows():
    assert is_grant_active(grant(), org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_purpose_must_match():
    assert not is_grant_active(grant(), org_id="o1", purpose=ConsentPurpose.LEDGER_READ, at=NOW)


def test_org_scoped_grant_only_covers_that_org():
    g = grant(org_id="o1")
    assert is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)
    assert not is_grant_active(g, org_id="o2", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_null_org_covers_any_org():
    assert is_grant_active(grant(org_id=None), org_id="o2",
                           purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_not_yet_granted_is_inactive():
    g = grant(granted_at=NOW + timedelta(hours=1))
    assert not is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_expiry_boundary_is_inactive():
    g = grant(expires_at=NOW)  # expires_at <= at -> inactive
    assert not is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_revoked_before_at_is_inactive():
    g = grant(revoked_at=NOW - timedelta(hours=1))
    assert not is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_point_in_time_before_revocation_is_active():
    """Historical queries (PI-4 point-in-time correctness) see pre-revocation truth."""
    g = grant(revoked_at=NOW + timedelta(hours=1))
    assert is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)


def test_naive_datetimes_are_treated_as_utc():
    """SQLite returns naive datetimes; they must compare as UTC, not crash."""
    g = grant(granted_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
              expires_at=(NOW + timedelta(days=1)).replace(tzinfo=None))
    assert is_grant_active(g, org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE,
                           at=NOW.replace(tzinfo=None))
    assert as_utc(NOW.replace(tzinfo=None)) == NOW


def test_check_consent_picks_first_active_grant():
    inactive = grant(id="g0", revoked_at=NOW - timedelta(days=1))
    active = grant(id="g2")
    d = check_consent([inactive, active], org_id="o1",
                      purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)
    assert d.allowed and d.grant_id == "g2"


def test_check_consent_denies_with_reason():
    d = check_consent([], org_id="o1", purpose=ConsentPurpose.LEDGER_WRITE, at=NOW)
    assert not d.allowed and d.grant_id is None
    assert "ledger_write" in d.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_consent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ledger.consent'`

- [ ] **Step 3: Implement**

Create `app/ledger/consent.py`:

```python
"""Pure consent decision logic (S3.1). No I/O, no clock — caller passes ``at``.

SQLite returns naive datetimes even from ``DateTime(timezone=True)`` columns,
so every comparison coerces to aware UTC first (naive ⇒ assume UTC, matching
how the store writes rows). A grant is active at time ``at`` iff: purpose
matches, the asking org is in scope (grant.org_id is None or equals it),
``granted_at <= at < expires_at``, and it was not revoked at or before
``at`` — so historical (point-in-time) checks still see pre-revocation truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from app.ledger.schema import ConsentDecision, ConsentGrant, ConsentPurpose


def as_utc(dt: datetime) -> datetime:
    """Aware-UTC view of any datetime; naive values are assumed UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_grant_active(
    grant: ConsentGrant, *, org_id: str, purpose: ConsentPurpose, at: datetime
) -> bool:
    if grant.purpose != purpose:
        return False
    if grant.org_id is not None and grant.org_id != org_id:
        return False
    moment = as_utc(at)
    if as_utc(grant.granted_at) > moment:
        return False
    if as_utc(grant.expires_at) <= moment:
        return False
    if grant.revoked_at is not None and as_utc(grant.revoked_at) <= moment:
        return False
    return True


def check_consent(
    grants: Sequence[ConsentGrant], *, org_id: str, purpose: ConsentPurpose, at: datetime
) -> ConsentDecision:
    for grant in grants:
        if is_grant_active(grant, org_id=org_id, purpose=purpose, at=at):
            return ConsentDecision(
                allowed=True,
                reason=f"active grant {grant.id} covers purpose '{purpose.value}'",
                grant_id=grant.id,
            )
    return ConsentDecision(
        allowed=False,
        reason=f"no active consent for purpose '{purpose.value}'",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger_consent.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full suite, then commit**

Run: `pytest -q` — expected: 369 passed.

```bash
git add app/ledger/consent.py tests/test_ledger_consent.py
git commit -m "feat(ledger): pure consent decision logic - scope, expiry, revocation, utc coercion"
```

---

### Task 3: ORM models on the shared Base

**Files:**
- Create: `app/ledger/models.py`
- Test: `tests/test_ledger_models.py`

**Interfaces:**
- Consumes: `Base`, `make_engine`, `make_session_factory` from `app.core.db`; the `candidates` table (FK target) from `app.candidates.models`.
- Produces (used by Tasks 4–6): `OrganizationRow` (table `organizations`), `ConsentGrantRow` (`consent_grants`), `InterviewRecordRow` (`interview_records`), `EvaluationEventRow` (`evaluation_events`), `AuditLogRow` (`audit_log`), plus module helpers `_uuid()` and `_utcnow()` (same pattern as `app/candidates/models.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger_models.py`:

```python
"""S3.1 ORM rows: defaults, constraints, FK enforcement on SQLite."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import app.candidates.models  # noqa: F401 — candidates table is an FK target
from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.models import (
    AuditLogRow,
    ConsentGrantRow,
    EvaluationEventRow,
    InterviewRecordRow,
    OrganizationRow,
    _utcnow,
)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_tablenames():
    assert OrganizationRow.__tablename__ == "organizations"
    assert ConsentGrantRow.__tablename__ == "consent_grants"
    assert InterviewRecordRow.__tablename__ == "interview_records"
    assert EvaluationEventRow.__tablename__ == "evaluation_events"
    assert AuditLogRow.__tablename__ == "audit_log"


def test_org_defaults_and_unique_name(session_factory):
    with session_factory() as s:
        org = OrganizationRow(name="Acme Talent")
        s.add(org)
        s.commit()
        assert len(org.id) == 36 and org.status == "active"
        assert org.created_at is not None
        s.add(OrganizationRow(name="Acme Talent"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_grant_requires_existing_candidate(session_factory):
    with session_factory() as s:
        s.add(ConsentGrantRow(candidate_id="nope", purpose="ledger_write",
                              expires_at=_utcnow()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_grant_org_id_nullable_and_revoked_default(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        g = ConsentGrantRow(candidate_id=cand.id, purpose="ledger_write",
                            expires_at=_utcnow())
        s.add(g)
        s.commit()
        assert g.org_id is None and g.revoked_at is None
        assert g.granted_at is not None


def test_candidate_delete_cascades_ledger_rows(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        org = OrganizationRow(name="Beta Corp")
        s.add_all([cand, org])
        s.flush()
        g = ConsentGrantRow(candidate_id=cand.id, org_id=org.id,
                            purpose="ledger_write", expires_at=_utcnow())
        s.add(g)
        s.flush()
        rec = InterviewRecordRow(org_id=org.id, candidate_id=cand.id,
                                 consent_id=g.id, stage="tech",
                                 outcome="advanced", interviewed_at=_utcnow())
        s.add(rec)
        s.flush()
        s.add(EvaluationEventRow(record_id=rec.id, candidate_id=cand.id,
                                 event_type="score", payload={"value": 4}))
        s.add(AuditLogRow(actor_type="org", actor_id=org.id,
                          action="record.submit", entity_type="interview_record",
                          entity_id=rec.id, candidate_id=cand.id))
        s.commit()

        s.delete(cand)
        s.commit()
        for row_cls in (ConsentGrantRow, InterviewRecordRow, EvaluationEventRow):
            assert s.execute(select(row_cls)).scalars().all() == []
        assert s.execute(select(AuditLogRow)).scalars().all() == []
        # the org itself survives erasure
        assert s.execute(select(OrganizationRow)).scalars().all() != []


def test_audit_row_defaults(session_factory):
    with session_factory() as s:
        a = AuditLogRow(actor_type="system", action="org.create",
                        entity_type="organization", entity_id="o1")
        s.add(a)
        s.commit()
        assert a.actor_id is None and a.candidate_id is None
        assert a.details == {} and a.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ledger.models'`

- [ ] **Step 3: Implement**

Create `app/ledger/models.py`:

```python
"""ORM rows for the evaluation ledger (S3.1). Postgres-shaped on SQLite.

``audit_log`` and ``evaluation_events`` are append-only by convention (the
store never updates or deletes them); consent revocation is an UPDATE of
``revoked_at`` so the fact of having consented survives for audit. DPDP
erasure is the one exception that trumps append-only: every candidate-linked
row carries an ``ondelete="CASCADE"`` FK to ``candidates.id`` and vanishes
with the candidate. Organizations are not candidate-linked and survive.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationRow(Base):
    """One member company of the ledger network."""

    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("name", name="uq_organizations_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ConsentGrantRow(Base):
    """One purpose-scoped, expiring, revocable consent from a candidate.

    ``org_id`` NULL = any member organization. Revocation sets ``revoked_at``;
    the row is deleted only by DPDP erasure (candidate cascade)."""

    __tablename__ = "consent_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InterviewRecordRow(Base):
    """One interview outcome one org submitted about one candidate."""

    __tablename__ = "interview_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    consent_id: Mapped[str] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(16))  # screen | tech | coding | hm
    outcome: Mapped[str] = mapped_column(String(16))
    interviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvaluationEventRow(Base):
    """Append-only detail attached to an interview record (scores, notes)."""

    __tablename__ = "evaluation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("interview_records.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLogRow(Base):
    """Append-only audit of every ledger mutation.

    ``candidate_id`` is a nullable CASCADE FK so DPDP erasure also sweeps the
    candidate-linked audit rows; org-only actions (org.create) keep None and
    survive."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_type: Mapped[str] = mapped_column(String(16))  # org | candidate | system
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True, nullable=True
    )
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger_models.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite, then commit**

Run: `pytest -q` — expected: 375 passed.

```bash
git add app/ledger/models.py tests/test_ledger_models.py
git commit -m "feat(ledger): ORM rows - orgs, consent grants, records, events, audit (CASCADE DPDP)"
```

---

### Task 4: Alembic migration 0003 + drift guard

**Files:**
- Create: `alembic/versions/0003_evaluation_ledger.py`
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Consumes: revision `0002_resume_fingerprints` (down_revision); `app.ledger.models` table definitions (Task 3) — the migration must mirror them exactly or the drift guard fails.
- Produces: tables `organizations`, `consent_grants`, `interview_records`, `evaluation_events`, `audit_log` on `alembic upgrade head` — the store (Tasks 5–6) and smoke (Task 7) run against migrated schema.

- [ ] **Step 1: Extend the drift-guard test (failing first)**

In `tests/test_migrations.py`, add the ledger models import next to the candidates one and extend the expected table set:

```python
import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
```

and change `test_upgrade_head_creates_candidate_tables` to:

```python
def test_upgrade_head_creates_candidate_tables(tmp_path):
    engine = _migrated_engine(tmp_path)
    names = set(inspect(engine).get_table_names())
    assert {"candidates", "resumes", "extractions", "resume_fingerprints"} <= names
    assert {
        "organizations",
        "consent_grants",
        "interview_records",
        "evaluation_events",
        "audit_log",
    } <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migrations.py -q`
Expected: FAIL — both tests (missing tables; drift between metadata and migrated schema).

- [ ] **Step 3: Write the migration**

Create `alembic/versions/0003_evaluation_ledger.py`:

```python
"""evaluation ledger: orgs, consent grants, interview records, events, audit (S3.1)

Revision ID: 0003_evaluation_ledger
Revises: 0002_resume_fingerprints
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0003_evaluation_ledger"
down_revision = "0002_resume_fingerprints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_organizations_name"),
    )

    op.create_table(
        "consent_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_consent_grants_candidate_id", "consent_grants", ["candidate_id"])
    op.create_index("ix_consent_grants_org_id", "consent_grants", ["org_id"])
    op.create_index("ix_consent_grants_purpose", "consent_grants", ["purpose"])

    op.create_table(
        "interview_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consent_id",
            sa.String(36),
            sa.ForeignKey("consent_grants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("interviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interview_records_org_id", "interview_records", ["org_id"])
    op.create_index(
        "ix_interview_records_candidate_id", "interview_records", ["candidate_id"]
    )
    op.create_index("ix_interview_records_consent_id", "interview_records", ["consent_id"])

    op.create_table(
        "evaluation_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "record_id",
            sa.String(36),
            sa.ForeignKey("interview_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_events_record_id", "evaluation_events", ["record_id"])
    op.create_index(
        "ix_evaluation_events_candidate_id", "evaluation_events", ["candidate_id"]
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_candidate_id", "audit_log", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("evaluation_events")
    op.drop_table("interview_records")
    op.drop_table("consent_grants")
    op.drop_table("organizations")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS (2 tests) — including the drift guard: migrated schema == `Base.metadata`.

- [ ] **Step 5: Run the full suite, then commit**

Run: `pytest -q` — expected: 375 passed.

```bash
git add alembic/versions/0003_evaluation_ledger.py tests/test_migrations.py
git commit -m "feat(ledger): migration 0003_evaluation_ledger + drift guard covers ledger tables"
```

---

### Task 5: LedgerStore — organizations + consent lifecycle + audit (+ config knob)

**Files:**
- Create: `app/ledger/store.py`
- Modify: `app/core/config.py` (add `ledger_consent_default_ttl_days`)
- Modify: `config.yaml` (add the ledger section)
- Test: `tests/test_ledger_store.py`

**Interfaces:**
- Consumes: Tasks 1–3 (`app.ledger.schema`, `app.ledger.consent`, `app.ledger.models`), `CandidateRow` from `app.candidates.models`, `Settings`/`get_settings` from `app.core.config`, `make_engine`/`make_session_factory` from `app.core.db`.
- Produces (Task 6 extends this same class; Task 7 smoke uses it):
  - `class ConsentError(RuntimeError)`
  - `class LedgerStore` with `__init__(self, session_factory: sessionmaker, *, default_consent_ttl_days: int = 365)` and methods
    `create_organization(name: str) -> Organization` (raises `ValueError` on duplicate name),
    `get_organization(org_id: str) -> Optional[Organization]`,
    `list_organizations() -> list[Organization]`,
    `delete_organization(org_id: str) -> bool`,
    `grant_consent(*, candidate_id: str, purpose: ConsentPurpose | str, org_id: Optional[str] = None, expires_at: Optional[datetime] = None, now: Optional[datetime] = None) -> ConsentGrant` (raises `LookupError` on unknown candidate/org),
    `revoke_consent(consent_id: str, *, now: Optional[datetime] = None) -> bool` (True only when newly revoked),
    `consent_status(candidate_id: str, *, org_id: str, purpose: ConsentPurpose | str, at: Optional[datetime] = None) -> ConsentDecision`,
    `audit_for_candidate(candidate_id: str) -> list[AuditEntry]`.
  - `build_ledger_store(settings: Optional[Settings] = None) -> LedgerStore` on `settings.candidates_db_url` (shared DB; schema is Alembic's job, no create_all).

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger_store.py`:

```python
"""S3.1 LedgerStore: orgs, consent grant/revoke/status, audit-in-transaction."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365)


@pytest.fixture()
def candidate_id(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


def test_create_and_get_organization(store):
    org = store.create_organization("Acme Talent")
    assert org.status == "active"
    assert store.get_organization(org.id) == org
    assert [o.id for o in store.list_organizations()] == [org.id]


def test_duplicate_org_name_rejected(store):
    store.create_organization("Acme Talent")
    with pytest.raises(ValueError):
        store.create_organization("Acme Talent")


def test_delete_organization(store):
    org = store.create_organization("Gone Inc")
    assert store.delete_organization(org.id) is True
    assert store.get_organization(org.id) is None
    assert store.delete_organization(org.id) is False


def test_grant_defaults_ttl(store, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id,
                            purpose=ConsentPurpose.LEDGER_WRITE, now=NOW)
    assert g.org_id is None and g.revoked_at is None
    assert g.expires_at - g.granted_at == timedelta(days=365)


def test_grant_unknown_candidate_or_org(store, candidate_id):
    with pytest.raises(LookupError):
        store.grant_consent(candidate_id="nope", purpose="ledger_write")
    with pytest.raises(LookupError):
        store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id="nope")


def test_consent_status_and_revocation(store, candidate_id):
    org = store.create_organization("Acme Talent")
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    d = store.consent_status(candidate_id, org_id=org.id,
                             purpose="ledger_write", at=NOW)
    assert d.allowed and d.grant_id == g.id
    # other org is out of scope; other purpose is out of scope
    assert not store.consent_status(candidate_id, org_id="other",
                                    purpose="ledger_write", at=NOW).allowed
    assert not store.consent_status(candidate_id, org_id=org.id,
                                    purpose="ledger_read", at=NOW).allowed

    assert store.revoke_consent(g.id, now=NOW) is True
    assert store.revoke_consent(g.id, now=NOW) is False  # already revoked
    assert store.revoke_consent("nope") is False
    after = store.consent_status(candidate_id, org_id=org.id,
                                 purpose="ledger_write",
                                 at=NOW + timedelta(hours=1))
    assert not after.allowed


def test_expired_grant_is_inactive(store, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        expires_at=NOW + timedelta(days=1), now=NOW)
    assert not store.consent_status(candidate_id, org_id="any",
                                    purpose="ledger_write",
                                    at=NOW + timedelta(days=2)).allowed


def test_mutations_are_audited(store, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            now=NOW)
    store.revoke_consent(g.id, now=NOW)
    actions = [a.action for a in store.audit_for_candidate(candidate_id)]
    assert actions == ["consent.grant", "consent.revoke"]
    entries = store.audit_for_candidate(candidate_id)
    assert all(a.actor_type == "candidate" and a.actor_id == candidate_id
               for a in entries)
    assert entries[0].entity_id == g.id
    assert entries[0].details["purpose"] == "ledger_write"


def test_settings_knob_exists():
    from app.core.config import Settings

    assert Settings(_env_file=None).ledger_consent_default_ttl_days == 365


def test_build_ledger_store(tmp_path):
    from app.core.config import Settings
    from app.ledger.store import build_ledger_store

    url = "sqlite:///" + (tmp_path / "ledger.db").as_posix()
    store = build_ledger_store(Settings(_env_file=None, candidates_db_url=url))
    assert isinstance(store, LedgerStore)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ledger.store'`

- [ ] **Step 3: Implement the store (orgs + consent + audit)**

Create `app/ledger/store.py`:

```python
"""Ledger store — organizations, consent lifecycle, audit trail (S3.1).

Every mutation writes its audit row inside the same transaction: an action
that committed is an action that was audited, atomically. Consent decisions
delegate to the pure ``app.ledger.consent`` module; the store only loads the
candidate's grant rows and converts them to contracts.

Actor model (S3.1, pre-auth): consent mutations are attributed to the
candidate (the DPDP data principal), record submissions to the org, and
org management to "system". Org-scoped API keys arrive in S3.2.

DPDP: erasure is NOT this store's job — every candidate-linked ledger row
cascades away when ``CandidateStore.delete_candidate`` deletes the candidate
(proven in tests). ``delete_organization`` is the org-side delete path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger import consent as consent_logic
from app.ledger.models import (
    AuditLogRow,
    ConsentGrantRow,
    EvaluationEventRow,
    InterviewRecordRow,
    OrganizationRow,
)
from app.ledger.schema import (
    AuditEntry,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
)


class ConsentError(RuntimeError):
    """A write needed consent that is not currently active."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _org(row: OrganizationRow) -> Organization:
    return Organization(id=row.id, name=row.name, status=row.status,
                        created_at=row.created_at)


def _grant(row: ConsentGrantRow) -> ConsentGrant:
    return ConsentGrant(
        id=row.id,
        candidate_id=row.candidate_id,
        org_id=row.org_id,
        purpose=ConsentPurpose(row.purpose),
        granted_at=row.granted_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def _audit_entry(row: AuditLogRow) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        candidate_id=row.candidate_id,
        details=dict(row.details or {}),
        created_at=row.created_at,
    )


class LedgerStore:
    def __init__(
        self, session_factory: sessionmaker, *, default_consent_ttl_days: int = 365
    ) -> None:
        self._session_factory = session_factory
        self._default_consent_ttl_days = default_consent_ttl_days

    # -- audit ----------------------------------------------------------------

    @staticmethod
    def _audit(
        session: Session,
        *,
        actor_type: str,
        actor_id: Optional[str],
        action: str,
        entity_type: str,
        entity_id: str,
        candidate_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        session.add(
            AuditLogRow(
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                candidate_id=candidate_id,
                details=details or {},
            )
        )

    def audit_for_candidate(self, candidate_id: str) -> list[AuditEntry]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(AuditLogRow)
                    .where(AuditLogRow.candidate_id == candidate_id)
                    .order_by(AuditLogRow.created_at, AuditLogRow.id)
                )
                .scalars()
                .all()
            )
            return [_audit_entry(r) for r in rows]

    # -- organizations --------------------------------------------------------

    def create_organization(self, name: str) -> Organization:
        with self._session_factory() as session:
            dup = session.execute(
                select(OrganizationRow.id).where(OrganizationRow.name == name)
            ).first()
            if dup:
                raise ValueError(f"organization name already exists: {name!r}")
            row = OrganizationRow(name=name)
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.create",
                entity_type="organization",
                entity_id=row.id,
                details={"name": name},
            )
            session.commit()
            return _org(row)

    def get_organization(self, org_id: str) -> Optional[Organization]:
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            return _org(row) if row else None

    def list_organizations(self) -> list[Organization]:
        with self._session_factory() as session:
            rows = (
                session.execute(select(OrganizationRow).order_by(OrganizationRow.created_at))
                .scalars()
                .all()
            )
            return [_org(r) for r in rows]

    def delete_organization(self, org_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            if row is None:
                return False
            session.delete(row)
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.delete",
                entity_type="organization",
                entity_id=org_id,
            )
            session.commit()
            return True

    # -- consent lifecycle ----------------------------------------------------

    def grant_consent(
        self,
        *,
        candidate_id: str,
        purpose: ConsentPurpose | str,
        org_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> ConsentGrant:
        purpose = ConsentPurpose(purpose)
        moment = now or _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            if org_id is not None and session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            expires = expires_at or moment + timedelta(days=self._default_consent_ttl_days)
            row = ConsentGrantRow(
                candidate_id=candidate_id,
                org_id=org_id,
                purpose=purpose.value,
                granted_at=moment,
                expires_at=expires,
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="candidate",
                actor_id=candidate_id,
                action="consent.grant",
                entity_type="consent_grant",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "purpose": purpose.value,
                    "org_id": org_id,
                    "expires_at": expires.isoformat(),
                },
            )
            session.commit()
            return _grant(row)

    def revoke_consent(self, consent_id: str, *, now: Optional[datetime] = None) -> bool:
        """True only when this call newly revoked the grant."""
        moment = now or _utcnow()
        with self._session_factory() as session:
            row = session.get(ConsentGrantRow, consent_id)
            if row is None or row.revoked_at is not None:
                return False
            row.revoked_at = moment
            self._audit(
                session,
                actor_type="candidate",
                actor_id=row.candidate_id,
                action="consent.revoke",
                entity_type="consent_grant",
                entity_id=row.id,
                candidate_id=row.candidate_id,
            )
            session.commit()
            return True

    def _grants_for(
        self, session: Session, candidate_id: str, purpose: ConsentPurpose
    ) -> list[ConsentGrant]:
        rows = (
            session.execute(
                select(ConsentGrantRow).where(
                    ConsentGrantRow.candidate_id == candidate_id,
                    ConsentGrantRow.purpose == purpose.value,
                )
            )
            .scalars()
            .all()
        )
        return [_grant(r) for r in rows]

    def consent_status(
        self,
        candidate_id: str,
        *,
        org_id: str,
        purpose: ConsentPurpose | str,
        at: Optional[datetime] = None,
    ) -> ConsentDecision:
        purpose = ConsentPurpose(purpose)
        moment = at or _utcnow()
        with self._session_factory() as session:
            grants = self._grants_for(session, candidate_id, purpose)
        return consent_logic.check_consent(
            grants, org_id=org_id, purpose=purpose, at=moment
        )


def build_ledger_store(settings: Optional[Settings] = None) -> LedgerStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job (`alembic upgrade head`), NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return LedgerStore(
        make_session_factory(engine),
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
    )
```

(The `EvaluationEventRow` / `InterviewRecordRow` / `EvaluationEvent` / `InterviewRecord` / `InterviewStage` / `InterviewOutcome` / `ConsentError` imports and class are used by Task 6, which extends this file — keeping them now avoids an import churn commit.)

Add to `app/core/config.py`, after the `fr_*` block (before "API hardening"):

```python
    # --- Evaluation ledger (PI-3, S3.1): schema + DPDP consent model -----------
    # The ledger shares candidates_db_url (one metadata root, one Alembic env).
    # Grants created without an explicit expiry get this TTL — DPDP forbids
    # perpetual consent by construction. Purposes/stages are code constants.
    ledger_consent_default_ttl_days: int = 365
```

Add to `config.yaml`, after the S2.4 `fr_*` block (before "API hardening"):

```yaml
# --- Evaluation ledger (PI-3) — S3.1 schema + DPDP consent ---------------------
# Consent grants are purpose-scoped, org-scoped, revocable, and ALWAYS expire:
# grants created without an explicit expiry get this TTL (days). No perpetual
# consent. Purpose/stage/outcome taxonomies are code constants, not config.
ledger_consent_default_ttl_days: 365
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger_store.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full suite, then commit**

Run: `pytest -q` — expected: 386 passed.

```bash
git add app/ledger/store.py app/core/config.py config.yaml tests/test_ledger_store.py
git commit -m "feat(ledger): LedgerStore - orgs + consent grant/revoke/status, audited in-transaction"
```

---

### Task 6: LedgerStore — consent-gated interview records + evaluation events + DPDP cascade proof

**Files:**
- Modify: `app/ledger/store.py` (extend `LedgerStore`)
- Test: `tests/test_ledger_store_records.py`

**Interfaces:**
- Consumes: Task 5's `LedgerStore` + `ConsentError`; `CandidateStore` from `app.candidates.store` (for the erasure-path proof).
- Produces (Task 7 smoke and S3.2 APIs use these):
  `submit_interview_record(*, org_id: str, candidate_id: str, stage: InterviewStage | str, outcome: InterviewOutcome | str, interviewed_at: datetime, summary: Optional[str] = None, now: Optional[datetime] = None) -> InterviewRecord` (raises `LookupError` on unknown org/candidate, `ConsentError` without an active `ledger_write` grant),
  `append_event(record_id: str, *, event_type: str, payload: Optional[dict] = None) -> EvaluationEvent` (raises `LookupError` on unknown record),
  `records_for_candidate(candidate_id: str) -> list[InterviewRecord]`,
  `events_for_record(record_id: str) -> list[EvaluationEvent]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger_store_records.py`:

```python
"""S3.1 LedgerStore records/events: consent-gated writes + DPDP cascade proof."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365)


@pytest.fixture()
def candidate_id(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


@pytest.fixture()
def org(store):
    return store.create_organization("Acme Talent")


def test_submit_without_consent_is_refused(store, org, candidate_id):
    with pytest.raises(ConsentError):
        store.submit_interview_record(
            org_id=org.id, candidate_id=candidate_id, stage="tech",
            outcome="advanced", interviewed_at=NOW, now=NOW,
        )
    assert store.records_for_candidate(candidate_id) == []


def test_submit_with_consent_links_grant(store, org, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    rec = store.submit_interview_record(
        org_id=org.id, candidate_id=candidate_id, stage="tech",
        outcome="advanced", interviewed_at=NOW, summary="solid round", now=NOW,
    )
    assert rec.consent_id == g.id
    assert rec.stage == "tech" and rec.outcome == "advanced"
    assert [r.id for r in store.records_for_candidate(candidate_id)] == [rec.id]


def test_submit_unknown_org_or_candidate(store, org, candidate_id):
    with pytest.raises(LookupError):
        store.submit_interview_record(org_id="nope", candidate_id=candidate_id,
                                      stage="tech", outcome="advanced",
                                      interviewed_at=NOW)
    with pytest.raises(LookupError):
        store.submit_interview_record(org_id=org.id, candidate_id="nope",
                                      stage="tech", outcome="advanced",
                                      interviewed_at=NOW)


def test_revocation_blocks_future_submissions(store, org, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                  stage="screen", outcome="advanced",
                                  interviewed_at=NOW, now=NOW)
    store.revoke_consent(g.id, now=NOW + timedelta(hours=1))
    with pytest.raises(ConsentError):
        store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                      stage="tech", outcome="advanced",
                                      interviewed_at=NOW,
                                      now=NOW + timedelta(hours=2))
    # the pre-revocation record legitimately remains (revocation ≠ erasure)
    assert len(store.records_for_candidate(candidate_id)) == 1


def test_events_append_and_read(store, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    rec = store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                        stage="coding", outcome="advanced",
                                        interviewed_at=NOW, now=NOW)
    e1 = store.append_event(rec.id, event_type="score",
                            payload={"scale": 5, "value": 4})
    e2 = store.append_event(rec.id, event_type="note")
    assert e1.candidate_id == candidate_id and e1.payload == {"scale": 5, "value": 4}
    assert e2.payload == {}
    assert [e.id for e in store.events_for_record(rec.id)] == [e1.id, e2.id]
    with pytest.raises(LookupError):
        store.append_event("nope", event_type="score")


def test_record_and_event_writes_are_audited(store, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    rec = store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                        stage="hm", outcome="offer",
                                        interviewed_at=NOW, now=NOW)
    store.append_event(rec.id, event_type="note")
    entries = store.audit_for_candidate(candidate_id)
    actions = [a.action for a in entries]
    assert actions == ["consent.grant", "record.submit", "event.append"]
    submit = entries[1]
    assert submit.actor_type == "org" and submit.actor_id == org.id
    assert submit.details["stage"] == "hm" and submit.details["outcome"] == "offer"


def test_dpdp_erasure_sweeps_ledger(store, session_factory, org, candidate_id):
    """The REAL erasure path: CandidateStore.delete_candidate cascades ledger rows."""
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    rec = store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                        stage="tech", outcome="hired",
                                        interviewed_at=NOW, now=NOW)
    store.append_event(rec.id, event_type="score", payload={"value": 5})
    assert CandidateStore(session_factory).delete_candidate(candidate_id) is True

    assert store.records_for_candidate(candidate_id) == []
    assert store.events_for_record(rec.id) == []
    assert store.audit_for_candidate(candidate_id) == []
    assert not store.consent_status(candidate_id, org_id=org.id,
                                    purpose="ledger_write", at=NOW).allowed
    # the org itself survives erasure
    assert store.get_organization(org.id) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_store_records.py -q`
Expected: FAIL — `AttributeError: 'LedgerStore' object has no attribute 'submit_interview_record'`

- [ ] **Step 3: Implement — extend `LedgerStore` in `app/ledger/store.py`**

Add converters at module level (next to `_grant`):

```python
def _record(row: InterviewRecordRow) -> InterviewRecord:
    return InterviewRecord(
        id=row.id,
        org_id=row.org_id,
        candidate_id=row.candidate_id,
        consent_id=row.consent_id,
        stage=InterviewStage(row.stage),
        outcome=InterviewOutcome(row.outcome),
        interviewed_at=row.interviewed_at,
        summary=row.summary,
        created_at=row.created_at,
    )


def _event(row: EvaluationEventRow) -> EvaluationEvent:
    return EvaluationEvent(
        id=row.id,
        record_id=row.record_id,
        candidate_id=row.candidate_id,
        event_type=row.event_type,
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )
```

Add methods to `LedgerStore` (new section after the consent lifecycle):

```python
    # -- interview records + events (consent-gated writes) --------------------

    def submit_interview_record(
        self,
        *,
        org_id: str,
        candidate_id: str,
        stage: InterviewStage | str,
        outcome: InterviewOutcome | str,
        interviewed_at: datetime,
        summary: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> InterviewRecord:
        """Write-time DPDP gate: refuses without an active ledger_write grant."""
        stage = InterviewStage(stage)
        outcome = InterviewOutcome(outcome)
        moment = now or _utcnow()
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
            row = InterviewRecordRow(
                org_id=org_id,
                candidate_id=candidate_id,
                consent_id=decision.grant_id,
                stage=stage.value,
                outcome=outcome.value,
                interviewed_at=interviewed_at,
                summary=summary,
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="record.submit",
                entity_type="interview_record",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "stage": stage.value,
                    "outcome": outcome.value,
                    "consent_id": decision.grant_id,
                },
            )
            session.commit()
            return _record(row)

    def append_event(
        self,
        record_id: str,
        *,
        event_type: str,
        payload: Optional[dict] = None,
    ) -> EvaluationEvent:
        with self._session_factory() as session:
            record = session.get(InterviewRecordRow, record_id)
            if record is None:
                raise LookupError(f"unknown interview record: {record_id}")
            row = EvaluationEventRow(
                record_id=record.id,
                candidate_id=record.candidate_id,
                event_type=event_type,
                payload=payload or {},
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="org",
                actor_id=record.org_id,
                action="event.append",
                entity_type="evaluation_event",
                entity_id=row.id,
                candidate_id=record.candidate_id,
                details={"record_id": record.id, "event_type": event_type},
            )
            session.commit()
            return _event(row)

    def records_for_candidate(self, candidate_id: str) -> list[InterviewRecord]:
        """Raw store read — query-time ledger_read enforcement is S3.2 (API)."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(InterviewRecordRow)
                    .where(InterviewRecordRow.candidate_id == candidate_id)
                    .order_by(InterviewRecordRow.created_at, InterviewRecordRow.id)
                )
                .scalars()
                .all()
            )
            return [_record(r) for r in rows]

    def events_for_record(self, record_id: str) -> list[EvaluationEvent]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(EvaluationEventRow)
                    .where(EvaluationEventRow.record_id == record_id)
                    .order_by(EvaluationEventRow.created_at, EvaluationEventRow.id)
                )
                .scalars()
                .all()
            )
            return [_event(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ledger_store_records.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite, then commit**

Run: `pytest -q` — expected: 393 passed.

```bash
git add app/ledger/store.py tests/test_ledger_store_records.py
git commit -m "feat(ledger): consent-gated interview records + events, DPDP erasure cascade proven"
```

---

### Task 7: Smoke script + LEDGER.md + roadmap

**Files:**
- Create: `scripts/smoke_s31.py`
- Create: `LEDGER.md`
- Modify: `docs/ROADMAP.md` (status board `[x]` S3.1, "Current state", session log)

**Interfaces:**
- Consumes: everything from Tasks 1–6; `extract_profile` from `app.candidates.extractor`, `CandidateStore` from `app.candidates.store`, `build_llm` from `app.services.llm` (smoke pattern copied from `scripts/smoke_s12.py` — S3.1 has no HTTP surface, so the smoke drives the stores directly against a migrated scratch DB, exactly as S1.2 did pre-API).
- Produces: `python scripts/smoke_s31.py` exits 0 with all checks OK, key-less (S3.1 is LLM-free; the extraction step degrades to heuristic without a key, which is fine — the ledger path is identical either way).

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s31.py`:

```python
"""S3.1 smoke: migrate a scratch DB with Alembic, then run the real ledger flow —
ingest a candidate → org → consent-refused submit → grant → submit → event →
audit trail → revoke blocks → DPDP erasure sweeps the ledger, org survives.

S3.1 is LLM-free; with no API key the candidate-extraction step uses the
heuristic floor, which changes nothing downstream. Run from the repo root:
    python scripts/smoke_s31.py
"""

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger.store import ConsentError, LedgerStore
from app.services.llm import build_llm

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
LEDGER_TABLES = {
    "organizations", "consent_grants", "interview_records",
    "evaluation_events", "audit_log",
}


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "smoke_s31.db"
    url = "sqlite:///" + db_path.as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    settings = get_settings()
    engine = make_engine(url)
    session_factory = make_session_factory(engine)
    candidates = CandidateStore(session_factory)
    ledger = LedgerStore(
        session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
    )
    now = datetime.now(timezone.utc)

    tables_ok = LEDGER_TABLES <= set(inspect(engine).get_table_names())

    text = FIXTURE.read_text(encoding="utf-8")
    result = asyncio.run(extract_profile(text, llm=build_llm(settings), settings=settings))
    ingest = candidates.ingest(result, text)
    print(f"candidate [{result.method}]: {ingest.candidate_id[:8]}")

    org = ledger.create_organization("Acme Talent Pvt Ltd")
    print(f"org: {org.id[:8]} {org.name!r}")

    refused = False
    try:
        ledger.submit_interview_record(
            org_id=org.id, candidate_id=ingest.candidate_id, stage="tech",
            outcome="advanced", interviewed_at=now,
        )
    except ConsentError as exc:
        refused = True
        print(f"submit without consent refused: {exc}")

    grant = ledger.grant_consent(
        candidate_id=ingest.candidate_id, purpose="ledger_write", org_id=org.id
    )
    ttl_days = (grant.expires_at - grant.granted_at).days
    print(f"consent granted: {grant.id[:8]} expires in {ttl_days}d")

    record = ledger.submit_interview_record(
        org_id=org.id, candidate_id=ingest.candidate_id, stage="tech",
        outcome="advanced", interviewed_at=now, summary="solid systems round",
    )
    event = ledger.append_event(record.id, event_type="score",
                                payload={"scale": 5, "value": 4})
    print(f"record: {record.id[:8]} (consent {record.consent_id[:8]}) + event {event.id[:8]}")

    audit_actions = [a.action for a in ledger.audit_for_candidate(ingest.candidate_id)]
    print(f"audit trail: {audit_actions}")

    ledger.revoke_consent(grant.id)
    revoked_blocks = False
    try:
        ledger.submit_interview_record(
            org_id=org.id, candidate_id=ingest.candidate_id, stage="hm",
            outcome="offer", interviewed_at=now,
        )
    except ConsentError:
        revoked_blocks = True
        print("submit after revocation refused")

    retained = len(ledger.records_for_candidate(ingest.candidate_id)) == 1

    erased = candidates.delete_candidate(ingest.candidate_id)
    swept = (
        ledger.records_for_candidate(ingest.candidate_id) == []
        and ledger.events_for_record(record.id) == []
        and ledger.audit_for_candidate(ingest.candidate_id) == []
    )
    org_survives = ledger.get_organization(org.id) is not None

    checks = {
        "ledger tables migrated": tables_ok,
        "submit without consent refused": refused,
        "default consent TTL applied": ttl_days == settings.ledger_consent_default_ttl_days,
        "record links authorizing grant": record.consent_id == grant.id,
        "event lands on record": event.record_id == record.id,
        "mutations audited in order": audit_actions
        == ["consent.grant", "record.submit", "event.append", "consent.revoke"],
        "revocation blocks new submissions": revoked_blocks,
        "pre-revocation record retained until erasure": retained,
        "DPDP erasure sweeps ledger rows": erased and swept,
        "organization survives erasure": org_survives,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if failed:
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: the audit-trail check expects `consent.revoke` as the 4th action because `revoke_consent` runs before erasure; keep the call order above intact.

- [ ] **Step 2: Run the smoke key-less**

Run (PowerShell): `$env:DEE_OPENROUTER_API_KEY = ""; python scripts/smoke_s31.py`
Expected: `SMOKE OK`, exit code 0, all 10 checks OK, extraction method `heuristic`.
(If a live key is configured in `.env`, also run once with it — the ledger path must be identical; only the printed extraction method changes to `llm`.)

- [ ] **Step 3: Write `LEDGER.md`**

Create `LEDGER.md`:

```markdown
# LEDGER.md — cross-company evaluation ledger (PI-3)

The ledger lets member companies share interview outcomes about consenting
candidates. DPDP consent is a first-class schema object, not a patch: no
write happens without an active grant, every mutation is audited, and
candidate erasure sweeps every ledger trace.

## S3.1 — schema + consent model (this sprint)

**Tables** (migration `0003_evaluation_ledger`, same DB/metadata root as
candidates — `candidates_db_url`):

| Table | What | DPDP linkage |
|---|---|---|
| `organizations` | member companies (`active`/`suspended`) | none — survives erasure |
| `consent_grants` | purpose-scoped, org-scoped, expiring, revocable consent | CASCADE from `candidates.id` |
| `interview_records` | one outcome one org submitted (stage: screen/tech/coding/hm) | CASCADE |
| `evaluation_events` | append-only detail per record (scores, notes) | CASCADE |
| `audit_log` | append-only audit of every mutation | candidate-linked rows CASCADE; org-only rows survive |

**Consent model** (`app/ledger/consent.py`, pure):
- Purpose-scoped: one purpose per grant — `ledger_write` (org may submit
  records) or `ledger_read` (org may query history; enforced in S3.2).
- Org-scoped: a specific org, or `org_id=NULL` = any member org.
- Always expires: grants without explicit expiry get
  `ledger_consent_default_ttl_days` (config, default 365). No perpetual consent.
- Revocable: revocation is an UPDATE (`revoked_at`), never a DELETE — the
  audit trail keeps the fact of having consented. Point-in-time checks before
  the revocation instant still see the grant as active (PI-4 needs this).
- Erasure trumps everything: `CandidateStore.delete_candidate` cascades away
  grants, records, events, and candidate-linked audit rows.

**Write-time gate** (`app/ledger/store.py`): `submit_interview_record` raises
`ConsentError` without an active `ledger_write` grant and stamps the record
with the authorizing `consent_id`. Every mutation writes its `audit_log` row
in the same transaction. Actor model pre-auth (S3.2 adds org API keys):
consent actions → `candidate`, record/event writes → `org`, org management
→ `system`.

**Not in S3.1:** HTTP APIs, query-time `ledger_read` enforcement, org API
keys, audit of reads (all S3.2); coding-round ingest (S3.3); reputation
aggregation (S3.4).
```

- [ ] **Step 4: Run the full suite one final time**

Run: `pytest -q` — expected: 393 passed.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: mark `[x] S3.1`.
- "Current state": current sprint → S3.2 (Ledger APIs), next action → write the S3.2 plan; move S3.1 into "Last session" with the delivered summary (tables, consent model, consent-gated store, audit, smoke result).
- Append a session-log entry (date 2026-07-19) in the established format.

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke_s31.py LEDGER.md docs/ROADMAP.md
git commit -m "feat(ledger): S3.1 smoke + LEDGER.md docs; roadmap S3.1 done"
```

---

## Self-Review Notes

- **Spec coverage:** spec's S3.1 line — "organizations, interview_records (stage taxonomy: screen/tech/coding/HM), evaluation_events, consent_grants (purpose, scope, expiry, revocation), audit_log" — maps to Tasks 3–4 (tables), Task 1 (taxonomies), Task 2 (purpose/scope/expiry/revocation semantics), Tasks 5–6 (audited lifecycle). Consent-at-query-time, org API keys, and audit-of-reads are explicitly S3.2 and out of scope here.
- **Type consistency:** `consent_status` (store) vs `check_consent` (pure fn) are deliberately different names to avoid the method/function clash; store imports the pure module as `consent_logic`. `ConsentPurpose | str` coercion happens once at each store method head via `ConsentPurpose(purpose)`.
- **Known SQLite quirk handled:** naive datetimes from `DateTime(timezone=True)` — all comparisons go through `as_utc` (Task 2), tested explicitly.
- **fr-style conservatism carried over:** nothing in the ledger touches verdicts/depth; no auto-anything.
