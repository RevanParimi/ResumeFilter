# S6.4 — Candidate Auth + DPDP Portal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give candidates a first-party auth plane (`X-Candidate-Key`) and a thin `app/portal/` DPDP portal — access (my-data), transparency (who-accessed), first-party consent grant/revoke, and self-service erasure — over the store data + audit trail that already exist.

**Architecture:** Mirror the existing org auth plane: a `candidate_credentials` table + `CandidateStore.issue_access_key`/`authenticate_candidate` + a `require_candidate` dependency + a new `candidate_router`. A pure `PortalService` (peer of `DashboardService`) composes `CandidateStore` + `LedgerStore` + `ReportStore` + `ProfileSourceService` into DPDP read/consent/erase endpoints. Retention posture is surfaced (per-data-class window + `retained_until`); the mechanical purge is deferred to PI-8. No LLM, no scoring, no new `ConsentPurpose`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy + Alembic on SQLite (Postgres-shaped), Pydantic v2, pytest (fully offline).

## Global Constraints

- **TDD, fully offline.** Every test runs with no API key / no network (NullLLM + in-memory stores + `FakeGitHub`, per `tests/conftest.py`). `pytest -q` green before any merge.
- **First-party data only; advisory; no auto-anything.** The portal changes no verdict/score. Erasure stays a hard delete.
- **No new `ConsentPurpose`.** Self-access is gated by candidate authentication == identity of the data subject, not a consent object.
- **DPDP:** the one new table (`candidate_credentials`) is candidate-linked with an `ON DELETE CASCADE` FK and is swept by the existing erasure path.
- **Config:** tunables in `config.yaml` / `Settings` (`candidate_access_key_bytes`, `ret_*_days`); no new secrets. Secrets stay `DEE_*` in `.env`.
- **DB:** SQLAlchemy + Alembic on SQLite, Postgres-shaped. Alembic owns schema — builders never `create_all` (tests may, per the S1.2 decision).
- **Commits:** no `Co-Authored-By` trailer (repo convention). Conventional-commit style `feat(s64): …` / `test(s64): …` / `docs(s64): …`.
- **Cross-candidate isolation is structural:** every portal endpoint operates on the `candidate_id` resolved from the key by `require_candidate` — never a path/body param. The only named id (`consent_id` on revoke) is ownership-enforced.

**Reference (read before starting):**
- Spec: `docs/superpowers/specs/2026-07-30-s64-candidate-auth-dpdp-portal-design.md`.
- Org auth precedent: `app/ledger/store.py` (`_hash_api_key`, `issue_api_key`, `authenticate_org`) + `app/api/routes.py` (`require_org`, `org_router`, `rotate_org_key`).
- Composition-layer precedent: `app/dashboard/service.py`, its `Services` wiring in `app/services/__init__.py`, and `tests/conftest.py::make_services`.
- Migration + guards precedent: `alembic/versions/0010_profile_sources.py` + `tests/test_migrations.py`.

---

### Task 1: `candidate_credentials` table — model + migration + guards

**Files:**
- Modify: `app/candidates/models.py` (add `CandidateCredentialRow`)
- Create: `alembic/versions/0012_candidate_credentials.py`
- Modify: `tests/test_migrations.py` (extend existence + index + FK/nullability guards)

**Interfaces:**
- Produces: ORM `CandidateCredentialRow` (table `candidate_credentials`) with columns `id`, `candidate_id` (FK `candidates.id` ON DELETE CASCADE, unique index), `access_key_hash` (indexed), `created_at`, `rotated_at` (nullable).

- [ ] **Step 1: Write the failing migration tests**

In `tests/test_migrations.py`, add `"candidate_credentials"` to the existence assertion in `test_upgrade_head_creates_candidate_tables`, and add a new table-group tuple used by the index + FK/nullability guards:

```python
# in test_upgrade_head_creates_candidate_tables, after the S6.3 assert:
    assert "candidate_credentials" in names  # S6.4 migration 0012
```

```python
# near the other *_TABLES tuples:
CANDIDATE_AUTH_TABLES = ("candidate_credentials",)  # S6.4 — candidate CASCADE
```

Then append `+ CANDIDATE_AUTH_TABLES` to the `for table in …` loops in BOTH
`test_migrated_indexes_match_orm` and `test_migrated_fks_and_nullability_match_orm`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_migrations.py -q`
Expected: FAIL — `candidate_credentials` not in table names (migration + model don't exist yet).

- [ ] **Step 3: Add the ORM model**

In `app/candidates/models.py`, after `FingerprintRow`, add (imports `ForeignKey`, `String`, `DateTime` already present):

```python
class CandidateCredentialRow(Base):
    """One candidate access credential (S6.4). Mirrors org API keys but as a
    peer table so auth material stays out of the PI-1 identity row. One per
    candidate (unique candidate_id); minting again rotates it. CASCADE erases
    it with the candidate."""

    __tablename__ = "candidate_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), unique=True, index=True
    )
    access_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    rotated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/0012_candidate_credentials.py` (mirror `0010`):

```python
"""candidate credentials: first-party auth for the DPDP portal (S6.4)

Revision ID: 0012_candidate_credentials
Revises: 0011_skill_curation
Create Date: 2026-07-30

One credential per candidate (unique candidate_id); CASCADE on candidate erasure.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_candidate_credentials"
down_revision = "0011_skill_curation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("access_key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_candidate_credentials_candidate_id",
        "candidate_credentials", ["candidate_id"], unique=True,
    )
    op.create_index(
        "ix_candidate_credentials_access_key_hash",
        "candidate_credentials", ["access_key_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_credentials_access_key_hash", table_name="candidate_credentials")
    op.drop_index("ix_candidate_credentials_candidate_id", table_name="candidate_credentials")
    op.drop_table("candidate_credentials")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS (all four migration tests, including the drift guard `test_migrated_schema_matches_orm_models` — the model + migration now agree).

- [ ] **Step 6: Commit**

```bash
git add app/candidates/models.py alembic/versions/0012_candidate_credentials.py tests/test_migrations.py
git commit -m "feat(s64): candidate_credentials table + migration 0012"
```

---

### Task 2: Config knobs (`candidate_access_key_bytes`, `ret_*_days`)

**Files:**
- Modify: `app/core/config.py` (add the S6.4 knobs after the `cur_*` block, ~line 142)
- Modify: `tests/test_config.py` (assert the new defaults) — if the file does not exist, create it with just the test below.

**Interfaces:**
- Produces: `Settings.candidate_access_key_bytes: int` (default 32), and `ret_resume_days` / `ret_interview_record_days` / `ret_coding_round_days` / `ret_observed_offer_days` / `ret_profile_source_days` / `ret_audit_log_days` (int day-count defaults).

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py` (create if absent, with `from app.core.config import Settings`):

```python
def test_s64_portal_config_defaults():
    s = Settings(_env_file=None, openrouter_api_key="")
    assert s.candidate_access_key_bytes == 32
    assert s.ret_resume_days == 1095
    assert s.ret_interview_record_days == 1825
    assert s.ret_coding_round_days == 1825
    assert s.ret_observed_offer_days == 1825
    assert s.ret_profile_source_days == 1095
    assert s.ret_audit_log_days == 2555
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_config.py::test_s64_portal_config_defaults -q`
Expected: FAIL — `AttributeError`/validation: no such fields yet.

- [ ] **Step 3: Add the knobs**

In `app/core/config.py`, immediately after the `cur_max_term_len` line (~142), add:

```python
    # --- Candidate auth + DPDP portal (PI-6, S6.4) ----------------------------
    # First-party candidate auth (minted access key, mirrors ledger_api_key_bytes)
    # + retention POSTURE surfaced by the portal. These day-counts parametrize the
    # `retained_until` the portal shows; they do NOT enforce deletion — the
    # mechanical retention sweep is PI-8. Illustrative windows.
    candidate_access_key_bytes: int = Field(default=32, ge=16)
    ret_resume_days: int = Field(default=1095, ge=1)            # 3y
    ret_interview_record_days: int = Field(default=1825, ge=1)  # 5y
    ret_coding_round_days: int = Field(default=1825, ge=1)      # 5y
    ret_observed_offer_days: int = Field(default=1825, ge=1)    # 5y
    ret_profile_source_days: int = Field(default=1095, ge=1)    # 3y
    ret_audit_log_days: int = Field(default=2555, ge=1)         # 7y — longest
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_config.py::test_s64_portal_config_defaults -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py tests/test_config.py
git commit -m "feat(s64): candidate auth + retention config knobs"
```

---

### Task 3: Candidate auth store methods (`issue_access_key`, `authenticate_candidate`)

**Files:**
- Modify: `app/candidates/store.py` (add `_hash_access_key`, `CandidateStore.__init__` gains `access_key_bytes`, two methods, `build_candidate_store` passes the knob)
- Test: `tests/test_candidate_auth.py` (create)

**Interfaces:**
- Consumes: `CandidateCredentialRow` (Task 1); `Settings.candidate_access_key_bytes` (Task 2).
- Produces: `CandidateStore.issue_access_key(candidate_id: str) -> str` (mint/rotate, returns plaintext once; `LookupError` on unknown candidate) and `CandidateStore.authenticate_candidate(access_key: str) -> Optional[str]` (candidate_id or None).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_auth.py`:

```python
import pytest

from app.candidates.models import CandidateRow
from tests.conftest import make_candidate_store


def _new_candidate(store) -> str:
    with store._session_factory() as s:
        row = CandidateRow(full_name="Asha")
        s.add(row)
        s.commit()
        return row.id


def test_issue_and_authenticate_roundtrip():
    store = make_candidate_store()
    cid = _new_candidate(store)
    key = store.issue_access_key(cid)
    assert isinstance(key, str) and key
    assert store.authenticate_candidate(key) == cid


def test_authenticate_rejects_bad_and_empty_keys():
    store = make_candidate_store()
    cid = _new_candidate(store)
    store.issue_access_key(cid)
    assert store.authenticate_candidate("nope") is None
    assert store.authenticate_candidate("") is None
    assert store.authenticate_candidate("   ") is None


def test_issue_rotates_and_old_key_dies():
    store = make_candidate_store()
    cid = _new_candidate(store)
    k1 = store.issue_access_key(cid)
    k2 = store.issue_access_key(cid)
    assert k1 != k2
    assert store.authenticate_candidate(k1) is None   # rotated out
    assert store.authenticate_candidate(k2) == cid
    # still exactly one credential row (unique candidate_id upsert, not append)
    from app.candidates.models import CandidateCredentialRow
    from sqlalchemy import select, func
    with store._session_factory() as s:
        n = s.execute(
            select(func.count()).select_from(CandidateCredentialRow)
            .where(CandidateCredentialRow.candidate_id == cid)
        ).scalar()
    assert n == 1


def test_issue_unknown_candidate_raises():
    store = make_candidate_store()
    with pytest.raises(LookupError):
        store.issue_access_key("does-not-exist")


def test_credential_cascades_on_candidate_delete():
    store = make_candidate_store()
    cid = _new_candidate(store)
    key = store.issue_access_key(cid)
    assert store.delete_candidate(cid) is True
    assert store.authenticate_candidate(key) is None  # credential gone with candidate
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_candidate_auth.py -q`
Expected: FAIL — `AttributeError: 'CandidateStore' object has no attribute 'issue_access_key'`.

- [ ] **Step 3: Implement the store methods**

In `app/candidates/store.py`:

Add `import secrets` next to `import hashlib`; add `CandidateCredentialRow` to the `app.candidates.models` import line.

Add a module helper near `_as_utc`:

```python
def _hash_access_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

Change `__init__` to accept the knob:

```python
    def __init__(self, session_factory: sessionmaker, *, access_key_bytes: int = 32) -> None:
        self._session_factory = session_factory
        self._access_key_bytes = access_key_bytes
```

Add the two methods (e.g. after `delete_resume`):

```python
    # -- candidate auth (S6.4): minted access key, mirrors org API keys ---------

    def issue_access_key(self, candidate_id: str) -> str:
        """Mint (or rotate) this candidate's access key; return the plaintext
        ONCE, storing only its hash. Overwriting an existing credential is
        rotation. LookupError if the candidate is unknown."""
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            raw = secrets.token_urlsafe(self._access_key_bytes)
            cred = (
                session.execute(
                    select(CandidateCredentialRow).where(
                        CandidateCredentialRow.candidate_id == candidate_id
                    )
                ).scalars().first()
            )
            if cred is None:
                session.add(
                    CandidateCredentialRow(
                        candidate_id=candidate_id, access_key_hash=_hash_access_key(raw)
                    )
                )
            else:
                cred.access_key_hash = _hash_access_key(raw)
                cred.rotated_at = _utcnow()
            session.commit()
            return raw

    def authenticate_candidate(self, access_key: str) -> Optional[str]:
        """candidate_id for the credential holding this key, else None.
        Empty/whitespace keys never match."""
        access_key = (access_key or "").strip()
        if not access_key:
            return None
        digest = _hash_access_key(access_key)
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(CandidateCredentialRow).where(
                        CandidateCredentialRow.access_key_hash == digest
                    )
                ).scalars().first()
            )
            return row.candidate_id if row else None
```

Update `build_candidate_store` to pass the knob:

```python
    return CandidateStore(
        make_session_factory(engine),
        access_key_bytes=settings.candidate_access_key_bytes,
    )
```

(`_utcnow` is already imported from `app.candidates.models`; `select` and `sessionmaker` are already imported.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_candidate_auth.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/candidates/store.py tests/test_candidate_auth.py
git commit -m "feat(s64): candidate access-key issue + authenticate"
```

---

### Task 4: Ledger store additions (`consents_for_candidate`, `get_grant`)

**Files:**
- Modify: `app/ledger/store.py` (two thin reads)
- Test: `tests/test_ledger_consents_for_candidate.py` (create)

**Interfaces:**
- Produces: `LedgerStore.consents_for_candidate(candidate_id: str) -> list[ConsentGrant]` (all grants, active + revoked + expired, ordered by `granted_at` then `id`) and `LedgerStore.get_grant(consent_id: str) -> Optional[ConsentGrant]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ledger_consents_for_candidate.py`:

```python
from datetime import datetime, timedelta, timezone

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store


def _store():
    cs = make_candidate_store()
    return cs, LedgerStore(cs._session_factory, default_consent_ttl_days=365)


def _candidate(cs) -> str:
    with cs._session_factory() as s:
        row = CandidateRow(full_name="Ravi")
        s.add(row)
        s.commit()
        return row.id


def test_consents_for_candidate_lists_all_states_ordered():
    cs, ledger = _store()
    cid = _candidate(cs)
    g1 = ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ)
    g2 = ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE)
    ledger.revoke_consent(g2.id)
    grants = ledger.consents_for_candidate(cid)
    assert [g.id for g in grants] == [g1.id, g2.id]        # granted_at order
    assert grants[0].revoked_at is None
    assert grants[1].revoked_at is not None                # revoked state preserved


def test_consents_for_candidate_empty():
    cs, ledger = _store()
    cid = _candidate(cs)
    assert ledger.consents_for_candidate(cid) == []


def test_get_grant_hit_and_miss():
    cs, ledger = _store()
    cid = _candidate(cs)
    g = ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ)
    assert ledger.get_grant(g.id).id == g.id
    assert ledger.get_grant("missing") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_ledger_consents_for_candidate.py -q`
Expected: FAIL — `AttributeError: 'LedgerStore' object has no attribute 'consents_for_candidate'`.

- [ ] **Step 3: Implement the two reads**

In `app/ledger/store.py`, in the `-- consent lifecycle --` section (after `consent_status`), add:

```python
    def consents_for_candidate(self, candidate_id: str) -> list[ConsentGrant]:
        """All grants for a candidate — active, revoked, and expired — ordered by
        grant time. A raw candidate-own read (the candidate's own consent ledger);
        no consent gate. Powers the S6.4 portal `/portal/consents` view."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ConsentGrantRow)
                    .where(ConsentGrantRow.candidate_id == candidate_id)
                    .order_by(ConsentGrantRow.granted_at, ConsentGrantRow.id)
                ).scalars().all()
            )
            return [_grant(r) for r in rows]

    def get_grant(self, consent_id: str) -> Optional[ConsentGrant]:
        """One grant by id, or None. Used by the S6.4 portal to enforce ownership
        before a first-party revoke."""
        with self._session_factory() as session:
            row = session.get(ConsentGrantRow, consent_id)
            return _grant(row) if row else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_ledger_consents_for_candidate.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_consents_for_candidate.py
git commit -m "feat(s64): ledger consents_for_candidate + get_grant reads"
```

---

### Task 5: Portal schema contracts

**Files:**
- Create: `app/portal/__init__.py` (empty package marker)
- Create: `app/portal/schema.py`
- Test: `tests/test_portal_schema.py` (create)

**Interfaces:**
- Consumes: `CandidateProfile` (`app.candidates.schema`), `ResumeSummary` (`app.candidates.store`), `ProfileSourceSignal` (`app.profile_sources.schema`), `ConsentGrant`/`InterviewRecord`/`CodingRoundResult` (`app.ledger.schema`).
- Produces: `ConsentState` (StrEnum: `active`/`revoked`/`expired`), `RetentionWindow`, `RetentionPolicy`, `ReportRef`, `AccessLogEntry`, `ConsentView`, `MyData`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_portal_schema.py`:

```python
from datetime import datetime, timezone

from app.portal.schema import (
    AccessLogEntry, ConsentState, ConsentView, MyData, ReportRef,
    RetentionPolicy, RetentionWindow,
)
from app.ledger.schema import ConsentGrant, ConsentPurpose


def test_retention_window_and_policy_shapes():
    w = RetentionWindow(data_class="resumes", ttl_days=1095,
                        oldest_item_at=None, retained_until=None)
    p = RetentionPolicy(windows=[w])
    assert p.sweep_active is False           # honest: posture only, no purge
    assert p.windows[0].data_class == "resumes"


def test_report_ref_is_existence_only():
    r = ReportRef(report_id="rep_1", domain="genai",
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    # No verdicts / fabrication fields on the ref.
    assert set(r.model_dump().keys()) == {"report_id", "domain", "created_at"}


def test_consent_view_wraps_grant_and_state():
    g = ConsentGrant(id="c1", candidate_id="cand1", purpose=ConsentPurpose.LEDGER_READ,
                     granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                     expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    v = ConsentView(grant=g, state=ConsentState.ACTIVE)
    assert v.grant.id == "c1" and v.state == "active"


def test_my_data_defaults_are_empty_collections():
    md = MyData(candidate_id="cand1", retention=RetentionPolicy(windows=[]))
    assert md.resumes == [] and md.interview_records == [] and md.reports == []
    assert md.profile is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_portal_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.portal'`.

- [ ] **Step 3: Create the package + schema**

Create empty `app/portal/__init__.py`.

Create `app/portal/schema.py`:

```python
"""Candidate DPDP portal contracts (S6.4). Read/consent shapes only — no scoring.

These are the render-ready projections the PortalService assembles from the
candidate + ledger + report + profile-source stores. A data principal accessing
their own data needs no consent object; auth == identity of the subject.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.schema import CandidateProfile
from app.candidates.store import ResumeSummary
from app.ledger.schema import CodingRoundResult, ConsentGrant, InterviewRecord
from app.profile_sources.schema import ProfileSourceSignal


class ConsentState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RetentionWindow(BaseModel):
    """One data class's retention posture. `ttl_days` is always the policy;
    `retained_until` is populated only for classes the portal materializes."""

    data_class: str
    ttl_days: int
    oldest_item_at: Optional[datetime] = None
    retained_until: Optional[datetime] = None


class RetentionPolicy(BaseModel):
    windows: list[RetentionWindow] = Field(default_factory=list)
    sweep_active: bool = False  # posture surfaced; mechanical purge is PI-8


class ReportRef(BaseModel):
    """A depth report's existence + when — NOT its advisory internals (v0)."""

    report_id: str
    domain: str
    created_at: datetime


class AccessLogEntry(BaseModel):
    """Candidate-friendly projection of one AuditEntry (who/what/when/allowed)."""

    at: datetime
    actor_type: str                       # "org" | "candidate" | "system"
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None      # org name resolved from actor_id, else None
    action: str
    allowed: Optional[bool] = None        # from details["allowed"] when present
    entity_type: str


class ConsentView(BaseModel):
    grant: ConsentGrant
    state: ConsentState


class MyData(BaseModel):
    """DPDP access view — everything the platform holds about the candidate that
    the portal surfaces. Reports appear as refs only."""

    candidate_id: str
    profile: Optional[CandidateProfile] = None
    resumes: list[ResumeSummary] = Field(default_factory=list)
    sources: list[ProfileSourceSignal] = Field(default_factory=list)
    interview_records: list[InterviewRecord] = Field(default_factory=list)
    coding_rounds: list[CodingRoundResult] = Field(default_factory=list)
    reports: list[ReportRef] = Field(default_factory=list)
    consents: list[ConsentGrant] = Field(default_factory=list)
    retention: RetentionPolicy
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_portal_schema.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/portal/__init__.py app/portal/schema.py tests/test_portal_schema.py
git commit -m "feat(s64): portal DPDP contracts"
```

---

### Task 6: Portal retention (pure)

**Files:**
- Create: `app/portal/retention.py`
- Test: `tests/test_portal_retention.py` (create)

**Interfaces:**
- Consumes: `RetentionWindow`/`RetentionPolicy` (Task 5); `Settings` `ret_*_days` (Task 2); `as_utc` (`app.ledger.consent`).
- Produces: `retained_until(oldest_at: datetime, ttl_days: int) -> datetime`; `build_retention_policy(oldest_by_class: dict[str, Optional[datetime]], settings: Settings) -> RetentionPolicy`; module constant `RETENTION_KNOBS: dict[str, str]` (data_class → Settings attr name).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_portal_retention.py`:

```python
from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.portal.retention import RETENTION_KNOBS, build_retention_policy, retained_until


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def test_retained_until_adds_ttl():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retained_until(base, 10) == base + timedelta(days=10)


def test_retained_until_coerces_naive_to_utc():
    naive = datetime(2026, 1, 1)  # SQLite-style naive
    out = retained_until(naive, 5)
    assert out.tzinfo is not None
    assert out == datetime(2026, 1, 6, tzinfo=timezone.utc)


def test_build_policy_covers_every_class_ttl_always_shown():
    policy = build_retention_policy({}, _settings())
    classes = {w.data_class for w in policy.windows}
    assert classes == set(RETENTION_KNOBS)          # every class present as posture
    assert all(w.ttl_days >= 1 for w in policy.windows)
    assert all(w.retained_until is None for w in policy.windows)  # no items
    assert policy.sweep_active is False


def test_build_policy_computes_retained_until_where_oldest_known():
    oldest = datetime(2026, 1, 1, tzinfo=timezone.utc)
    policy = build_retention_policy({"resumes": oldest}, _settings())
    resumes = next(w for w in policy.windows if w.data_class == "resumes")
    assert resumes.oldest_item_at == oldest
    assert resumes.retained_until == oldest + timedelta(days=resumes.ttl_days)
    # a class with no oldest stays policy-only
    audit = next(w for w in policy.windows if w.data_class == "audit_log")
    assert audit.retained_until is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_portal_retention.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.portal.retention'`.

- [ ] **Step 3: Implement retention**

Create `app/portal/retention.py`:

```python
"""Pure retention-posture helpers (S6.4). No I/O. The portal surfaces the policy
window per data class and a computed `retained_until` for the classes it
materializes; the mechanical purge is deferred to PI-8 (`sweep_active=False`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.core.config import Settings
from app.ledger.consent import as_utc
from app.portal.schema import RetentionPolicy, RetentionWindow

# data_class -> Settings attribute holding its TTL in days.
RETENTION_KNOBS: dict[str, str] = {
    "resumes": "ret_resume_days",
    "profile_sources": "ret_profile_source_days",
    "interview_records": "ret_interview_record_days",
    "coding_rounds": "ret_coding_round_days",
    "observed_offers": "ret_observed_offer_days",
    "audit_log": "ret_audit_log_days",
}


def retained_until(oldest_at: datetime, ttl_days: int) -> datetime:
    """When the oldest item in a class ages out under the policy (aware UTC)."""
    return as_utc(oldest_at) + timedelta(days=ttl_days)


def build_retention_policy(
    oldest_by_class: dict[str, Optional[datetime]], settings: Settings
) -> RetentionPolicy:
    """Every class appears (ttl_days = the policy). `oldest_item_at` /
    `retained_until` are filled only where the caller supplied an oldest
    timestamp (classes the portal materializes); others stay policy-only."""
    windows: list[RetentionWindow] = []
    for data_class, attr in RETENTION_KNOBS.items():
        ttl = getattr(settings, attr)
        oldest = oldest_by_class.get(data_class)
        windows.append(
            RetentionWindow(
                data_class=data_class,
                ttl_days=ttl,
                oldest_item_at=oldest,
                retained_until=retained_until(oldest, ttl) if oldest else None,
            )
        )
    return RetentionPolicy(windows=windows, sweep_active=False)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_portal_retention.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/portal/retention.py tests/test_portal_retention.py
git commit -m "feat(s64): pure retention posture helpers"
```

---

### Task 7: `PortalService` + wiring (`Services.portal`, `build_portal_service`, conftest)

**Files:**
- Create: `app/portal/service.py`
- Modify: `app/services/__init__.py` (add `Services.portal` field + `TYPE_CHECKING` import + build in `build_default_services`, hoisting `ledger`/`report_store`/`profile_sources`)
- Modify: `tests/conftest.py` (`make_services` gains `portal=None` + builds it; hoist `report_store`)
- Test: `tests/test_portal_service.py` (create)

**Interfaces:**
- Consumes: `CandidateStore` (Tasks 3), `LedgerStore` (Task 4), `ReportStore`, `ProfileSourceService`, `build_retention_policy` (Task 6), portal contracts (Task 5).
- Produces: `PortalService(candidates, ledger, report_store, profile_sources, *, settings=None)` with methods `my_data(candidate_id) -> MyData`, `access_log(candidate_id) -> list[AccessLogEntry]`, `consents(candidate_id, *, now=None) -> list[ConsentView]`, `grant(candidate_id, *, purpose, org_id=None, expires_at=None) -> ConsentGrant`, `revoke(candidate_id, consent_id) -> bool` (raises `LookupError` when the grant is unknown or not owned); `build_portal_service(settings=None, *, candidates, ledger, report_store, profile_sources) -> PortalService`. `Services.portal: PortalService`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_portal_service.py`:

```python
from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.ledger.schema import (
    ConsentPurpose, InterviewOutcome, InterviewStage,
)
from app.portal.schema import ConsentState
from app.portal.service import PortalService
from app.schemas.report import Report
from tests.conftest import make_services


def _cid(services) -> str:
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="Meera")
        s.add(row)
        s.commit()
        return row.id


def _portal(services) -> PortalService:
    return services.portal


def test_my_data_composes_reports_as_refs_only(settings):
    services = make_services(settings)
    cid = _cid(services)
    services.report_store.save(Report(candidate_id=cid, domain="genai"))
    md = _portal(services).my_data(cid)
    assert md.candidate_id == cid
    assert len(md.reports) == 1
    dumped = md.reports[0].model_dump()
    assert set(dumped) == {"report_id", "domain", "created_at"}  # no internals
    # retention posture present for every class
    assert {w.data_class for w in md.retention.windows}  # non-empty
    assert md.retention.sweep_active is False


def test_my_data_unknown_candidate_raises(settings):
    services = make_services(settings)
    with pytest.raises(LookupError):
        _portal(services).my_data("nope")


def test_access_log_projects_audit_with_org_name_newest_first(settings):
    services = make_services(settings)
    cid = _cid(services)
    org = services.ledger.create_organization("Acme")
    # write + read consent so a disclosure gets audited
    services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id)
    services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id)
    services.ledger.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    services.ledger.query_records_for_org(org_id=org.id, candidate_id=cid)  # allowed read
    log = _portal(services).access_log(cid)
    assert log, "expected audit entries"
    actions = {e.action for e in log}
    assert "record.query" in actions and "record.submit" in actions
    q = next(e for e in log if e.action == "record.query")
    assert q.actor_type == "org" and q.actor_name == "Acme" and q.allowed is True
    # newest first
    ats = [e.at for e in log]
    assert ats == sorted(ats, reverse=True)


def test_consents_labels_states(settings):
    services = make_services(settings)
    cid = _cid(services)
    g_active = services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ)
    g_revoked = services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE)
    services.ledger.revoke_consent(g_revoked.id)
    views = {v.grant.id: v.state for v in _portal(services).consents(cid)}
    assert views[g_active.id] == ConsentState.ACTIVE
    assert views[g_revoked.id] == ConsentState.REVOKED


def test_grant_writes_first_party_consent(settings):
    services = make_services(settings)
    cid = _cid(services)
    g = _portal(services).grant(cid, purpose=ConsentPurpose.LEDGER_READ)
    assert g.candidate_id == cid
    # audited as actor_type="candidate"
    audit = services.ledger.audit_for_candidate(cid)
    grant_rows = [a for a in audit if a.action == "consent.grant"]
    assert grant_rows and grant_rows[-1].actor_type == "candidate"


def test_revoke_is_ownership_enforced(settings):
    services = make_services(settings)
    a = _cid(services)
    b = _cid(services)
    g_b = services.ledger.grant_consent(candidate_id=b, purpose=ConsentPurpose.LEDGER_READ)
    # candidate A cannot revoke candidate B's grant
    with pytest.raises(LookupError):
        _portal(services).revoke(a, g_b.id)
    assert services.ledger.get_grant(g_b.id).revoked_at is None  # untouched
    # owner can
    assert _portal(services).revoke(b, g_b.id) is True
    assert services.ledger.get_grant(g_b.id).revoked_at is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_portal_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.portal.service'` (and `Services` has no `portal`).

- [ ] **Step 3: Implement `PortalService`**

Create `app/portal/service.py`:

```python
"""Candidate DPDP portal service (S6.4). Pure composition over CandidateStore +
LedgerStore + ReportStore + ProfileSourceService. Owns no tables/state. Every
method operates on ONE candidate_id (resolved from the caller's key upstream);
self-access needs no org consent. Reports surface as refs (no internals)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.ledger.consent import as_utc
from app.ledger.schema import ConsentGrant, ConsentPurpose
from app.ledger.store import LedgerStore
from app.portal.retention import build_retention_policy
from app.portal.schema import (
    AccessLogEntry, ConsentState, ConsentView, MyData, ReportRef,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortalService:
    def __init__(
        self,
        candidates: CandidateStore,
        ledger: LedgerStore,
        report_store,
        profile_sources,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self._candidates = candidates
        self._ledger = ledger
        self._report_store = report_store
        self._profile_sources = profile_sources
        self._settings = settings or get_settings()

    def my_data(self, candidate_id: str) -> MyData:
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")
        resumes = self._candidates.list_resumes(candidate_id)
        sources = self._profile_sources.list_sources(candidate_id)
        records = self._ledger.records_for_candidate(candidate_id)
        coding = self._ledger.coding_rounds_for_candidate(candidate_id)
        reports = [
            ReportRef(report_id=r.id, domain=r.domain, created_at=r.created_at)
            for r in self._report_store.for_candidate(candidate_id)
        ]
        oldest = {
            "resumes": min((r.created_at for r in resumes), default=None),
            "profile_sources": min((s.fetched_at for s in sources), default=None),
            "interview_records": min((r.created_at for r in records), default=None),
            "coding_rounds": min((c.created_at for c in coding), default=None),
        }
        return MyData(
            candidate_id=candidate_id,
            profile=self._candidates.latest_profile(candidate_id),
            resumes=resumes,
            sources=sources,
            interview_records=records,
            coding_rounds=coding,
            reports=reports,
            consents=self._ledger.consents_for_candidate(candidate_id),
            retention=build_retention_policy(oldest, self._settings),
        )

    def access_log(self, candidate_id: str) -> list[AccessLogEntry]:
        entries = self._ledger.audit_for_candidate(candidate_id)  # ascending
        names: dict[str, Optional[str]] = {}
        out: list[AccessLogEntry] = []
        for e in reversed(entries):  # newest first
            actor_name: Optional[str] = None
            if e.actor_type == "org" and e.actor_id:
                if e.actor_id not in names:
                    org = self._ledger.get_organization(e.actor_id)
                    names[e.actor_id] = org.name if org else None
                actor_name = names[e.actor_id]
            out.append(
                AccessLogEntry(
                    at=e.created_at,
                    actor_type=e.actor_type,
                    actor_id=e.actor_id,
                    actor_name=actor_name,
                    action=e.action,
                    allowed=e.details.get("allowed"),
                    entity_type=e.entity_type,
                )
            )
        return out

    def consents(self, candidate_id: str, *, now: Optional[datetime] = None) -> list[ConsentView]:
        moment = as_utc(now) if now else _utcnow()
        return [
            ConsentView(grant=g, state=self._state(g, moment))
            for g in self._ledger.consents_for_candidate(candidate_id)
        ]

    @staticmethod
    def _state(grant: ConsentGrant, now: datetime) -> ConsentState:
        if grant.revoked_at is not None:
            return ConsentState.REVOKED
        if as_utc(grant.expires_at) <= now:
            return ConsentState.EXPIRED
        return ConsentState.ACTIVE

    def grant(
        self,
        candidate_id: str,
        *,
        purpose: ConsentPurpose,
        org_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> ConsentGrant:
        return self._ledger.grant_consent(
            candidate_id=candidate_id, purpose=purpose, org_id=org_id, expires_at=expires_at
        )

    def revoke(self, candidate_id: str, consent_id: str) -> bool:
        grant = self._ledger.get_grant(consent_id)
        if grant is None or grant.candidate_id != candidate_id:
            # Same error whether missing or not-owned: a candidate can't probe
            # for another's grant ids.
            raise LookupError(f"unknown consent grant for candidate: {consent_id}")
        return self._ledger.revoke_consent(consent_id)


def build_portal_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
    report_store,
    profile_sources,
) -> PortalService:
    return PortalService(
        candidates, ledger, report_store, profile_sources,
        settings=settings or get_settings(),
    )
```

- [ ] **Step 4: Wire `Services.portal`**

In `app/services/__init__.py`:

Add to the `TYPE_CHECKING` block:
```python
    from app.portal.service import PortalService
```

Add the field to the `Services` dataclass (last field):
```python
    portal: PortalService
```

In `build_default_services`, add the function-local import and hoist the shared
instances so the portal reuses them. Replace the build body so `ledger`,
`report_store`, and `profile_sources` are locals passed into both `Services(...)`
and `build_portal_service`:

```python
    from app.portal.service import build_portal_service
    # ... existing function-local imports ...

    settings = settings or get_settings()
    github = GitHubClient(settings)
    candidates = build_candidate_store(settings)
    curation = build_curation_service(settings)
    curation.refresh_overlay()
    ledger = build_ledger_store(settings)
    report_store = build_report_store(settings)
    profile_sources = build_profile_source_service(
        settings, github=github, candidates=candidates, curation=curation
    )
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=github,
        flywheel=build_flywheel(settings),
        report_store=report_store,
        candidates=candidates,
        ledger=ledger,
        features=build_feature_store(settings),
        jobs=build_job_store(settings),
        comp=build_comp_service(settings),
        dashboard=build_dashboard_service(settings),
        profile_sources=profile_sources,
        curation=curation,
        portal=build_portal_service(
            settings, candidates=candidates, ledger=ledger,
            report_store=report_store, profile_sources=profile_sources,
        ),
    )
```

- [ ] **Step 5: Wire the test harness**

In `tests/conftest.py::make_services`, add `portal=None` to the signature (next to `curation=None`). Hoist the report store and build the portal before the `Services(...)` return. Immediately before `return Services(`:

```python
    report_store = InMemoryReportStore()
    if portal is None:
        from app.portal.service import PortalService
        portal = PortalService(candidates, ledger, report_store, profile_sources, settings=settings)
```

Change `report_store=InMemoryReportStore(),` in the `Services(...)` call to
`report_store=report_store,` and add `portal=portal,` to it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_portal_service.py -q`
Expected: PASS (6 tests).

- [ ] **Step 7: Full suite (nothing else broke from the Services/conftest change)**

Run: `pytest -q`
Expected: PASS (all prior tests + the new ones). If any direct `Services(...)`
construction outside `make_services`/`build_default_services` now fails for a
missing `portal=`, run `grep -rn "Services(" tests app | grep -v make_services`
and add `portal=` there.

- [ ] **Step 8: Commit**

```bash
git add app/portal/service.py app/services/__init__.py tests/conftest.py tests/test_portal_service.py
git commit -m "feat(s64): PortalService + Services.portal wiring"
```

---

### Task 8: Candidate auth plane — `require_candidate`, `candidate_router`, admin mint endpoint

**Files:**
- Modify: `app/api/routes.py` (add `require_candidate`, `candidate_router`, `POST /candidates/{id}/auth-key`)
- Modify: `app/main.py` (include `candidate_router`; add endpoints to the root list)
- Test: `tests/test_candidate_auth_api.py` (create)

**Interfaces:**
- Consumes: `CandidateStore.issue_access_key`/`authenticate_candidate` (Task 3).
- Produces: `require_candidate(request, x_candidate_key) -> str` FastAPI dependency (401 on bad key); `candidate_router: APIRouter`; admin `POST /candidates/{candidate_id}/auth-key` → `{candidate_id, access_key}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_auth_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


def _client(settings):
    services = make_services(settings)
    return TestClient(create_app(services)), services


def _make_candidate(client) -> str:
    r = client.post("/candidates", json={"resume_text": "Dev\nEmail: d@e.com\nSKILLS\nPython\n",
                                         "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def test_admin_mints_candidate_key_and_it_authenticates(settings):
    client, _ = _client(settings)
    cid = _make_candidate(client)
    r = client.post(f"/candidates/{cid}/auth-key")
    assert r.status_code == 200
    key = r.json()["access_key"]
    assert r.json()["candidate_id"] == cid and key
    # the key authenticates on a portal route
    ok = client.get("/portal/me", headers={"X-Candidate-Key": key})
    assert ok.status_code == 200


def test_mint_unknown_candidate_404(settings):
    client, _ = _client(settings)
    r = client.post("/candidates/nope/auth-key")
    assert r.status_code == 404


def test_portal_route_without_key_is_401(settings):
    client, _ = _client(settings)
    assert client.get("/portal/me").status_code == 401
    assert client.get("/portal/me", headers={"X-Candidate-Key": "bad"}).status_code == 401
```

(`GET /portal/me` is delivered in Task 9; this test needs Task 9's route to pass
its 200 assertion. Implement Steps 3–4 here, then this file goes green after
Task 9. Run only `test_mint_unknown_candidate_404` + `test_portal_route_without_key_is_401`
now — see Step 6.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_candidate_auth_api.py::test_mint_unknown_candidate_404 -q`
Expected: FAIL — 404 route doesn't exist (405/404 on unknown path shape).

- [ ] **Step 3: Add the dependency, router, and admin endpoint**

In `app/api/routes.py`:

Add the portal-contract imports near the other `app.*` imports:
```python
from app.portal.schema import AccessLogEntry, ConsentView, MyData
```

After `require_org` (~line 82), add:
```python
async def require_candidate(
    request: Request, x_candidate_key: Optional[str] = Header(default=None)
) -> str:
    """Resolve a candidate's own access key to their id (S6.4). Always enforced —
    the portal is the data principal's private surface."""
    candidate_id = _services(request).candidates.authenticate_candidate(x_candidate_key or "")
    if candidate_id is None:
        raise HTTPException(status_code=401, detail="invalid or missing X-Candidate-Key")
    return candidate_id
```

After the `org_router = APIRouter()` line (~89), add:
```python
# Candidate-authenticated DPDP portal plane (X-Candidate-Key). Every route acts
# on the candidate resolved from the key — never a path/body param.
candidate_router = APIRouter()
```

Add the admin mint endpoint near the other `/candidates/{id}` admin routes (e.g.
after `delete_candidate_resume`, ~line 352):
```python
@router.post("/candidates/{candidate_id}/auth-key")
async def issue_candidate_key(candidate_id: str, request: Request) -> dict:
    """Admin/system mints (or rotates) a candidate's portal access key, returned
    ONCE. First-party self-serve registration is a productionization concern
    (PI-8); this is the offline-deterministic issuance path."""
    services = _services(request)
    try:
        access_key = services.candidates.issue_access_key(candidate_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="candidate not found") from exc
    return {"candidate_id": candidate_id, "access_key": access_key}
```

- [ ] **Step 4: Include the router + document it**

In `app/main.py`:
- Change the import to `from app.api.routes import candidate_router, org_router, public_router, router`.
- After `app.include_router(org_router)`, add `app.include_router(candidate_router)`.
- In the `root()` endpoint's `endpoints` list, add:
  `"POST /candidates/{id}/auth-key"`, `"GET /portal/me"`, `"GET /portal/access-log"`,
  `"GET /portal/consents"`, `"POST /portal/consents"`,
  `"POST /portal/consents/{id}/revoke"`, `"DELETE /portal/me"`.

- [ ] **Step 5: Run the failing-now-passing subset**

Run: `pytest tests/test_candidate_auth_api.py::test_mint_unknown_candidate_404 tests/test_candidate_auth_api.py::test_portal_route_without_key_is_401 -q`
Expected: PASS. (The `test_admin_mints_...` 200 assertion depends on `GET /portal/me` from Task 9 — leave it for Task 9's run.)

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_candidate_auth_api.py
git commit -m "feat(s64): candidate auth plane (require_candidate + mint endpoint)"
```

---

### Task 9: Portal endpoints (the six routes) + isolation

**Files:**
- Modify: `app/api/routes.py` (six `candidate_router` routes + a request model)
- Test: `tests/test_portal_api.py` (create)

**Interfaces:**
- Consumes: `require_candidate`, `candidate_router` (Task 8); `Services.portal` (Task 7); `MyData`/`AccessLogEntry`/`ConsentView` (Task 5); `ConsentGrant`/`ConsentPurpose` (already imported in routes).
- Produces: `GET /portal/me`, `GET /portal/access-log`, `GET /portal/consents`, `POST /portal/consents`, `POST /portal/consents/{consent_id}/revoke`, `DELETE /portal/me`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_portal_api.py`:

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.ledger.schema import InterviewOutcome, InterviewStage
from tests.conftest import make_services


def _setup(settings):
    services = make_services(settings)
    client = TestClient(create_app(services))
    return client, services


def _candidate_with_key(client):
    cid = client.post("/candidates", json={
        "resume_text": "Dev\nEmail: d@e.com\nSKILLS\nPython\n", "evaluate": False,
    }).json()["candidate_id"]
    key = client.post(f"/candidates/{cid}/auth-key").json()["access_key"]
    return cid, {"X-Candidate-Key": key}


def test_portal_me_returns_access_view(settings):
    client, _ = _setup(settings)
    cid, h = _candidate_with_key(client)
    r = client.get("/portal/me", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["candidate_id"] == cid
    assert len(body["resumes"]) == 1
    assert body["retention"]["sweep_active"] is False
    assert body["retention"]["windows"]  # posture present


def test_portal_access_log_shows_org_disclosure(settings):
    client, services = _setup(settings)
    cid, h = _candidate_with_key(client)
    org = services.ledger.create_organization("Acme")
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_write", org_id=org.id)
    services.ledger.grant_consent(candidate_id=cid, purpose="ledger_read", org_id=org.id)
    services.ledger.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    services.ledger.query_records_for_org(org_id=org.id, candidate_id=cid)
    r = client.get("/portal/access-log", headers=h)
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()}
    assert "record.query" in actions and "record.submit" in actions
    q = next(e for e in r.json() if e["action"] == "record.query")
    assert q["actor_name"] == "Acme" and q["allowed"] is True


def test_portal_first_party_grant_then_revoke(settings):
    client, _ = _setup(settings)
    cid, h = _candidate_with_key(client)
    g = client.post("/portal/consents", headers=h, json={"purpose": "ledger_read"})
    assert g.status_code == 200
    gid = g.json()["id"]
    assert client.get("/portal/consents", headers=h).status_code == 200
    rv = client.post(f"/portal/consents/{gid}/revoke", headers=h)
    assert rv.status_code == 200 and rv.json()["revoked"] is True
    # state now revoked
    states = {c["grant"]["id"]: c["state"] for c in client.get("/portal/consents", headers=h).json()}
    assert states[gid] == "revoked"


def test_grant_unknown_org_404(settings):
    client, _ = _setup(settings)
    _, h = _candidate_with_key(client)
    r = client.post("/portal/consents", headers=h, json={"purpose": "ledger_read", "org_id": "ghost"})
    assert r.status_code == 404


def test_cross_candidate_isolation(settings):
    client, services = _setup(settings)
    a, ha = _candidate_with_key(client)
    b, hb = _candidate_with_key(client)
    g_b = services.ledger.grant_consent(candidate_id=b, purpose="ledger_read")
    # A revoking B's grant → 404, B's grant untouched
    assert client.post(f"/portal/consents/{g_b.id}/revoke", headers=ha).status_code == 404
    assert services.ledger.get_grant(g_b.id).revoked_at is None
    # A's /portal/me never contains B
    assert client.get("/portal/me", headers=ha).json()["candidate_id"] == a


def test_self_erase_kills_the_key(settings):
    client, _ = _setup(settings)
    cid, h = _candidate_with_key(client)
    d = client.delete("/portal/me", headers=h)
    assert d.status_code == 200 and d.json()["deleted"] is True
    # key no longer authenticates
    assert client.get("/portal/me", headers=h).status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_portal_api.py -q`
Expected: FAIL — the `/portal/*` routes don't exist yet (404/405).

- [ ] **Step 3: Add the six routes**

In `app/api/routes.py`, add a portal section (e.g. after the dashboard routes,
before the talent-search section):

```python
# ── Candidate DPDP portal (S6.4) ─────────────────────────────────────────────
# Candidate plane (X-Candidate-Key). First-party access / transparency / consent
# control / erasure over the candidate's own data. No new ConsentPurpose — auth
# == identity of the data subject. Every route acts on the resolved candidate_id.


@candidate_router.get("/portal/me", response_model=MyData)
async def portal_me(request: Request, candidate_id: str = Depends(require_candidate)) -> MyData:
    return _services(request).portal.my_data(candidate_id)


@candidate_router.get("/portal/access-log", response_model=list[AccessLogEntry])
async def portal_access_log(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[AccessLogEntry]:
    return _services(request).portal.access_log(candidate_id)


@candidate_router.get("/portal/consents", response_model=list[ConsentView])
async def portal_list_consents(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> list[ConsentView]:
    return _services(request).portal.consents(candidate_id)


class PortalConsentGrantRequest(BaseModel):
    purpose: ConsentPurpose
    org_id: Optional[str] = None
    expires_at: Optional[datetime] = None


@candidate_router.post("/portal/consents", response_model=ConsentGrant)
async def portal_grant_consent(
    req: PortalConsentGrantRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> ConsentGrant:
    try:
        return _services(request).portal.grant(
            candidate_id, purpose=req.purpose, org_id=req.org_id, expires_at=req.expires_at
        )
    except LookupError as exc:  # unknown org_id
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@candidate_router.post("/portal/consents/{consent_id}/revoke")
async def portal_revoke_consent(
    consent_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    try:
        revoked = _services(request).portal.revoke(candidate_id, consent_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="consent grant not found") from exc
    return {"consent_id": consent_id, "revoked": revoked}


@candidate_router.delete("/portal/me")
async def portal_erase(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    """DPDP erasure, self-service. Reuses the candidate erasure path (candidate +
    resumes + extractions + reports + cascaded ledger rows + the credential). The
    key stops authenticating afterward (credential CASCADEs)."""
    services = _services(request)
    reports_deleted = services.report_store.delete_for_candidate(candidate_id)
    services.candidates.delete_candidate(candidate_id)
    return {"candidate_id": candidate_id, "deleted": True, "reports_deleted": reports_deleted}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_portal_api.py tests/test_candidate_auth_api.py -q`
Expected: PASS (all of `test_portal_api.py` + the previously-deferred
`test_admin_mints_candidate_key_and_it_authenticates` now green).

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_portal_api.py
git commit -m "feat(s64): candidate DPDP portal endpoints"
```

---

### Task 10: Smoke `scripts/smoke_s64.py`

**Files:**
- Create: `scripts/smoke_s64.py`

**Interfaces:**
- Consumes: the full HTTP surface (admin + candidate + org planes). No network, no LLM (`DEE_VECTORSTORE_BACKEND=memory`, no API key needed for the flow beyond the admin key).

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s64.py` (mirror `scripts/smoke_s63.py`'s boot/scaffold):

```python
"""S6.4 smoke: boot uvicorn on a migrated scratch DB, mint a candidate key, walk
the DPDP portal — access (my-data + retention posture), transparency (who
accessed my data), first-party consent grant/revoke, cross-candidate isolation,
and self-service erasure (the key dies). No network, no LLM.
Run from repo root: python scripts/smoke_s64.py
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

PORT = 8064
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"


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
    url = "sqlite:///" + (scratch / "smoke_s64.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not _wait_healthy(c):
                print("server did not become healthy")
                return 1

            # 1. create candidate + mint key
            cid = c.post("/candidates", headers=admin_h,
                         json={"resume_text": RESUME, "evaluate": False}).json()["candidate_id"]
            key = c.post(f"/candidates/{cid}/auth-key", headers=admin_h).json()["access_key"]
            ch = {"X-Candidate-Key": key}
            checks["mint_key"] = bool(key)

            # 2. /portal/me — access view + retention posture, reports are refs
            me = c.get("/portal/me", headers=ch).json()
            checks["me_profile_resumes"] = me["candidate_id"] == cid and len(me["resumes"]) == 1
            checks["me_retention_posture"] = (
                me["retention"]["sweep_active"] is False and bool(me["retention"]["windows"])
            )

            # 3. org submits + reads under consent
            org = c.post("/ledger/orgs", headers=admin_h, json={"name": "Acme"}).json()
            org_id, org_key = org["org"]["id"], org["api_key"]
            org_h = {"X-Org-Key": org_key}
            for purpose in ("ledger_write", "ledger_read"):
                c.post(f"/ledger/candidates/{cid}/consent", headers=admin_h,
                       json={"purpose": purpose, "org_id": org_id})
            c.post("/ledger/records", headers=org_h, json={
                "candidate_id": cid, "stage": "tech", "outcome": "advanced",
                "interviewed_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            })
            c.get(f"/ledger/candidates/{cid}/records", headers=org_h)

            # 4. /portal/access-log — the org's read + submit are visible, named
            log = c.get("/portal/access-log", headers=ch).json()
            actions = {e["action"] for e in log}
            q = next((e for e in log if e["action"] == "record.query"), {})
            checks["access_log_shows_disclosure"] = (
                {"record.query", "record.submit"} <= actions
                and q.get("actor_name") == "Acme" and q.get("allowed") is True
            )

            # 5. first-party grant + list + revoke
            gid = c.post("/portal/consents", headers=ch, json={"purpose": "ledger_read"}).json()["id"]
            rv = c.post(f"/portal/consents/{gid}/revoke", headers=ch).json()
            states = {v["grant"]["id"]: v["state"] for v in c.get("/portal/consents", headers=ch).json()}
            checks["grant_then_revoke"] = rv["revoked"] is True and states[gid] == "revoked"

            # 6. wrong/absent key 401; a second candidate can't touch the first
            checks["no_key_401"] = c.get("/portal/me").status_code == 401
            cid2 = c.post("/candidates", headers=admin_h,
                          json={"resume_text": RESUME.replace("dev@", "two@"), "evaluate": False}
                          ).json()["candidate_id"]
            key2 = c.post(f"/candidates/{cid2}/auth-key", headers=admin_h).json()["access_key"]
            g1 = c.post("/portal/consents", headers=ch, json={"purpose": "ledger_read"}).json()["id"]
            cross = c.post(f"/portal/consents/{g1}/revoke", headers={"X-Candidate-Key": key2})
            checks["cross_candidate_404"] = cross.status_code == 404

            # 7. self-erase → key dies, candidate gone
            d = c.delete("/portal/me", headers=ch).json()
            checks["self_erase"] = d["deleted"] is True
            checks["key_dead_after_erase"] = c.get("/portal/me", headers=ch).status_code == 401
            checks["candidate_gone"] = c.get(f"/candidates/{cid}", headers=admin_h).status_code == 404
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok = sum(checks.values())
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'XX'}] {name}")
    print(f"{ok}/{len(checks)} checks OK")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_s64.py`
Expected: `12/12 checks OK`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_s64.py
git commit -m "test(s64): DPDP portal uvicorn smoke (12/12)"
```

---

### Task 11: `PORTAL.md` + ROADMAP closeout

**Files:**
- Create: `PORTAL.md`
- Modify: `docs/ROADMAP.md` (status board S6.4 → `[x]`; Current state; Next action; Session log; mark PI-6 complete)

**Interfaces:** none (docs only).

- [ ] **Step 1: Write `PORTAL.md`**

Create `PORTAL.md` (peer of `LEDGER.md` / `DASHBOARD.md`). Cover, in prose an
engineer can act on:
- **The candidate plane** — `X-Candidate-Key`, `require_candidate`,
  `candidate_router`; how a key is minted (admin `POST /candidates/{id}/auth-key`,
  returned once, sha256-hashed, rotatable) and why (offline-deterministic; real
  registration is PI-8).
- **The DPDP rights map** — access (`GET /portal/me`), transparency
  (`GET /portal/access-log`), consent control (`GET/POST /portal/consents`,
  `POST /portal/consents/{id}/revoke`, ownership-enforced), erasure
  (`DELETE /portal/me`). Note **no new `ConsentPurpose`** and why (self-access ==
  identity of the subject).
- **Cross-candidate isolation** — structural (resolved id, never a param), the one
  ownership check on revoke, the identical-404 no-probing rule.
- **Reports** — existence-only in v0 (decision (a)); internals not disclosed.
- **Retention posture** — per-class windows + `retained_until`, `sweep_active=False`;
  the mechanical sweep is PI-8. List the `ret_*` knobs + `candidate_access_key_bytes`.
- **DPDP** — `candidate_credentials` CASCADE; erasure completeness.
- **What's deferred** — the §9 non-goals from the spec.

- [ ] **Step 2: Full suite green + smoke green (evidence before closeout)**

Run: `pytest -q` → expect green (752 → ~785).
Run: `python scripts/smoke_s64.py` → expect `12/12 checks OK`, exit 0.
Record the exact final test count for the ROADMAP.

- [ ] **Step 3: Update `docs/ROADMAP.md`**

- Status board: `S6.4` → `[x]`; annotate PI-6 header as complete.
- **Current state:** replace the S6.3 block with the S6.4 summary (package
  `app/portal/`, candidate auth plane, migration `0012`, six endpoints, retention
  posture surfaced / sweep deferred, no new consent purpose, final test count,
  smoke 12/12). Note the two deferred decisions (reports existence-only;
  access-log includes platform actions) and the PI-8 follow-ups (retention sweep,
  real registration, report-internals disclosure, correction/grievance rights).
- **Next action:** PI-6 complete → shape PI-7 (verification & assessment depth)
  per the gap analysis §6, when its turn comes.
- **Session log:** add a dated `2026-07-30` entry summarizing S6.4.

- [ ] **Step 4: Commit**

```bash
git add PORTAL.md docs/ROADMAP.md
git commit -m "docs(s64): PORTAL.md + ROADMAP closeout — S6.4 done, PI-6 complete"
```

---

## Self-Review (completed while writing)

**Spec coverage** — every spec section maps to a task:
- §5.1 candidate auth (table/model/migration/store/dep/router/mint) → Tasks 1, 3, 8.
- §5.2 `app/portal/` (schema, retention, service) → Tasks 5, 6, 7.
- §5.3 ledger `consents_for_candidate` + `get_grant` → Task 4.
- §5.4 `Services.portal` wiring → Task 7.
- §5.5 migration `0012` + guards → Task 1.
- §6 API (admin mint + six candidate routes) → Tasks 8, 9.
- §7 config knobs → Task 2 (with a defaults test — closes the S6.3 deferred minor).
- §8 tests + smoke → Tasks 1–10 (each has failing-first tests) + Task 10 smoke.
- §9 non-goals → documented in Task 11 (`PORTAL.md` + ROADMAP).
- §10 definition of done → Tasks 1–11 collectively.

**Type consistency** — names checked across tasks: `issue_access_key` /
`authenticate_candidate` (Tasks 3, 8), `consents_for_candidate` / `get_grant`
(Tasks 4, 7), `build_retention_policy` / `RETENTION_KNOBS` (Tasks 6, 7),
`PortalService.my_data`/`access_log`/`consents`/`grant`/`revoke` (Tasks 7, 9),
`MyData`/`AccessLogEntry`/`ConsentView`/`ReportRef`/`RetentionPolicy` (Tasks 5, 7,
9), `require_candidate`/`candidate_router` (Tasks 8, 9). `ReportRef` fields
(`report_id`/`domain`/`created_at`) match `Report.id`/`domain`/`created_at`.

**Placeholder scan** — no TBD/TODO; every code + test step carries real content.

**Ordering note** — `tests/test_candidate_auth_api.py::test_admin_mints_...` asserts
a `GET /portal/me` 200 that only exists after Task 9; the plan calls this out and
scopes Task 8's run to the two independent assertions, closing the loop in Task 9.
