# S3.2 — Ledger APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the S3.1 evaluation ledger over HTTP — orgs authenticate with their own API keys, submit interview records (write-consent gated), and query a candidate's ledger history only with an active `ledger_read` grant, with every read audited.

**Architecture:** Two auth planes over the existing `LedgerStore`. Platform/admin operations (org lifecycle, recording candidate consent) sit behind the existing shared-secret `X-API-Key` gate on the current `router`. Org operations (submit record, append event, query history) sit on a new `org_router` authenticated per-request by a DB-backed `X-Org-Key` that resolves to one organization. `ledger_read` is enforced at query time inside a new store method that writes an audit row for every read attempt — allowed or denied — in the same transaction. This sprint also lands the four S3.1 carry-over residuals, since they become correctness issues the moment records are stamped and reads are audited.

**Tech Stack:** FastAPI + Pydantic v2, SQLAlchemy + Alembic on SQLite (Postgres-shaped), `hashlib.sha256` + `secrets.token_urlsafe` for org keys, pytest (fully offline, NullLLM/in-memory stores), `httpx` + uvicorn for the smoke.

## Global Constraints

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` must be green before merge.
- **S3.2 is LLM-free** — no model calls anywhere; no deterministic-fallback obligation arises.
- Advisory only: the ledger records outcomes and enforces consent; it never auto-rejects or scores a candidate.
- DPDP: first-party data only; consent objects + delete paths already exist. Every new candidate-linked row (audit rows for reads) carries the existing `ondelete="CASCADE"` FK so erasure sweeps it. Org API keys are org secrets, not candidate PII.
- Config: tunables in `config.yaml`; secrets in `.env` (`DEE_*` prefix) only. The org API key is generated server-side and returned once — never stored in plaintext, never in YAML.
- DB: SQLAlchemy + Alembic on SQLite, written Postgres-shaped (String(36) UUIDs, FKs, JSON columns). The ledger shares `candidates_db_url` (one metadata root, one Alembic env). Schema changes ship as a new migration, never `create_all`.
- Actor model (audit `actor_type`): consent mutations → `candidate`; record/event/query (reads) → `org`; org lifecycle + key issuance → `system`.
- Every store mutation writes its `audit_log` row inside the same transaction as the change it records.
- List reads order by `(created_at, id)` — the established deterministic ordering.

---

## File Structure

**New files**
- `alembic/versions/0004_org_api_keys.py` — adds `organizations.api_key_hash` + its unique index.
- `scripts/smoke_s32.py` — uvicorn + scripted HTTP end-to-end for the sprint.

**Modified files**
- `app/ledger/consent.py` — deterministic authorizing-grant selection (residual A).
- `app/ledger/models.py` — `OrganizationRow.api_key_hash` column + unique index.
- `app/ledger/store.py` — org keys (`issue_api_key`/`authenticate_org`), `create_organization` IntegrityError→ValueError (residual C), `consent_status` LookupError (residual B), `get_record`, `query_records_for_org` (read enforcement + audit-of-reads), `api_key_bytes` ctor param, `build_ledger_store` wiring.
- `app/services/__init__.py` — `Services.ledger` + build wiring.
- `app/api/routes.py` — `require_org` dependency, `org_router`, admin ledger endpoints (orgs, consent), org-gated endpoints (records, events, query).
- `app/main.py` — include `org_router`; extend the root endpoint listing.
- `app/core/config.py` + `config.yaml` — `ledger_api_key_bytes` knob.
- `tests/conftest.py` — import `app.ledger.models`; build a `LedgerStore` sharing the candidate store's session factory; `Services.ledger` in `make_services`.
- `tests/test_migrations.py` — strengthen the drift guard to indexes / FK ondelete / nullability (residual D).
- `tests/test_ledger_consent.py`, `tests/test_ledger_store.py`, `tests/test_ledger_store_records.py` — unit tests for the store/consent changes.
- `tests/test_ledger_api.py` (new) — HTTP tests for every new endpoint.
- `LEDGER.md` — S3.2 section.
- `docs/ROADMAP.md` — status board + session log at end of sprint.

---

## Task 1: Deterministic consent selection + `consent_status` LookupError (residuals A & B)

Pure logic + one store method. No HTTP. Fixes the two S3.1 residuals that become live correctness issues once records are stamped with (and reads audited by) a specific `consent_id`.

**Files:**
- Modify: `app/ledger/consent.py`
- Modify: `app/ledger/store.py:305-319` (`consent_status`)
- Test: `tests/test_ledger_consent.py`, `tests/test_ledger_store.py`

**Interfaces:**
- Consumes: `ConsentGrant`, `ConsentDecision`, `ConsentPurpose` (`app/ledger/schema.py`); `as_utc`, `is_grant_active` (`app/ledger/consent.py`); `CandidateRow`, `OrganizationRow` (models).
- Produces: `check_consent(grants, *, org_id, purpose, at) -> ConsentDecision` now selects deterministically. `LedgerStore.consent_status(candidate_id, *, org_id, purpose, at=None) -> ConsentDecision` now raises `LookupError` for unknown candidate or org.

- [ ] **Step 1: Write the failing pure-logic test**

Add to `tests/test_ledger_consent.py`:

```python
def test_check_consent_prefers_org_specific_then_latest_grant():
    from datetime import datetime, timedelta, timezone
    from app.ledger.consent import check_consent
    from app.ledger.schema import ConsentGrant, ConsentPurpose

    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    common = dict(candidate_id="cand", purpose=ConsentPurpose.LEDGER_READ,
                  expires_at=at + timedelta(days=10))
    wildcard = ConsentGrant(id="w", org_id=None, granted_at=at - timedelta(days=1), **common)
    specific_old = ConsentGrant(id="s-old", org_id="org1", granted_at=at - timedelta(days=5), **common)
    specific_new = ConsentGrant(id="s-new", org_id="org1", granted_at=at - timedelta(days=2), **common)

    grants = [wildcard, specific_old, specific_new]
    decision = check_consent(grants, org_id="org1", purpose=ConsentPurpose.LEDGER_READ, at=at)
    assert decision.allowed and decision.grant_id == "s-new"  # org-specific beats wildcard; newest wins ties
    # Order-independent: shuffling the input must not change the authorizing grant.
    reshuffled = check_consent(list(reversed(grants)), org_id="org1",
                               purpose=ConsentPurpose.LEDGER_READ, at=at)
    assert reshuffled.grant_id == "s-new"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_ledger_consent.py::test_check_consent_prefers_org_specific_then_latest_grant -v`
Expected: FAIL — current `check_consent` returns the first active grant in input order (`w`), not `s-new`.

- [ ] **Step 3: Make `check_consent` deterministic**

In `app/ledger/consent.py`, replace the body of `check_consent` and add a sort helper:

```python
def _selection_key(grant: ConsentGrant) -> tuple[bool, float, str]:
    # Sort ascending: org-specific (False) before wildcard (True); most recent
    # grant first (negated epoch); lowest id as the final deterministic tiebreak.
    return (grant.org_id is None, -as_utc(grant.granted_at).timestamp(), grant.id)


def check_consent(
    grants: Sequence[ConsentGrant], *, org_id: str, purpose: ConsentPurpose, at: datetime
) -> ConsentDecision:
    active = [
        g for g in grants if is_grant_active(g, org_id=org_id, purpose=purpose, at=at)
    ]
    if not active:
        return ConsentDecision(
            allowed=False,
            reason=f"no active consent for purpose '{purpose.value}'",
        )
    best = min(active, key=_selection_key)
    return ConsentDecision(
        allowed=True,
        reason=f"active grant {best.id} covers purpose '{purpose.value}'",
        grant_id=best.id,
    )
```

- [ ] **Step 4: Run the pure-logic test to verify it passes**

Run: `pytest tests/test_ledger_consent.py::test_check_consent_prefers_org_specific_then_latest_grant -v`
Expected: PASS

- [ ] **Step 5: Write the failing store test for `consent_status`**

Add to `tests/test_ledger_store.py`:

```python
def test_consent_status_unknown_candidate_or_org_raises_lookup(store, candidate_id):
    org = store.create_organization("Probe Co")
    with pytest.raises(LookupError):
        store.consent_status("no-such-candidate", org_id=org.id,
                             purpose=ConsentPurpose.LEDGER_READ)
    with pytest.raises(LookupError):
        store.consent_status(candidate_id, org_id="no-such-org",
                             purpose=ConsentPurpose.LEDGER_READ)


def test_consent_status_known_but_ungranted_is_denied_not_error(store, candidate_id):
    org = store.create_organization("Known Co")
    decision = store.consent_status(candidate_id, org_id=org.id,
                                    purpose=ConsentPurpose.LEDGER_READ)
    assert decision.allowed is False and decision.grant_id is None
```

- [ ] **Step 6: Run them to verify they fail**

Run: `pytest tests/test_ledger_store.py -k consent_status -v`
Expected: FAIL on the unknown-candidate/org test — `consent_status` currently returns a denied decision instead of raising.

- [ ] **Step 7: Add existence checks to `consent_status`**

In `app/ledger/store.py`, update `consent_status` to guard existence before delegating to the pure logic:

```python
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
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            grants = self._grants_for(session, candidate_id, purpose)
        return consent_logic.check_consent(
            grants, org_id=org_id, purpose=purpose, at=moment
        )
```

- [ ] **Step 8: Run the store tests + the full ledger suite to verify green**

Run: `pytest tests/test_ledger_store.py tests/test_ledger_consent.py tests/test_ledger_store_records.py -q`
Expected: PASS (existing single-grant tests unaffected — deterministic selection returns the same lone grant).

- [ ] **Step 9: Commit**

```bash
git add app/ledger/consent.py app/ledger/store.py tests/test_ledger_consent.py tests/test_ledger_store.py
git commit -m "fix(ledger): deterministic authorizing-grant selection + consent_status 404 shape"
```

---

## Task 2: Org API keys — model column, migration 0004, store issue/authenticate (residual C)

Give each organization a rotatable API key (only its `sha256` hash is stored) and replace `create_organization`'s check-then-insert with insert-then-map so a duplicate name is a mapped `ValueError` with no TOCTOU window.

**Files:**
- Modify: `app/ledger/models.py:31-43` (`OrganizationRow`)
- Create: `alembic/versions/0004_org_api_keys.py`
- Modify: `app/ledger/store.py` (imports, ctor, `create_organization`, new `issue_api_key`/`authenticate_org`)
- Test: `tests/test_ledger_store.py`

**Interfaces:**
- Consumes: `OrganizationRow`, `select`, `Session` factory.
- Produces:
  - `OrganizationRow.api_key_hash: Optional[str]` (unique index `uq_organizations_api_key_hash`).
  - `LedgerStore.__init__(session_factory, *, default_consent_ttl_days=365, api_key_bytes=32)`.
  - `LedgerStore.issue_api_key(org_id: str) -> str` — returns the one-time plaintext key; raises `LookupError` for unknown org.
  - `LedgerStore.authenticate_org(api_key: str) -> Optional[str]` — returns `org_id` for an active org matching the key, else `None`.
  - `LedgerStore.create_organization(name: str) -> Organization` — raises `ValueError` on duplicate name (now via IntegrityError mapping).

- [ ] **Step 1: Add the model column + unique index**

In `app/ledger/models.py`, extend the imports and `OrganizationRow`:

```python
from sqlalchemy import (
    JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint,
)
```

```python
class OrganizationRow(Base):
    """One member company of the ledger network."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("name", name="uq_organizations_name"),
        Index("uq_organizations_api_key_hash", "api_key_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended
    # sha256 hex of the org's API key; NULL until a key is issued. Only the hash
    # is ever stored — the plaintext is returned once at issuance and discarded.
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
```

- [ ] **Step 2: Write migration 0004**

Create `alembic/versions/0004_org_api_keys.py`:

```python
"""org API keys: organizations.api_key_hash + unique index (S3.2)

Revision ID: 0004_org_api_keys
Revises: 0003_evaluation_ledger
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_org_api_keys"
down_revision = "0003_evaluation_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("api_key_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "uq_organizations_api_key_hash", "organizations", ["api_key_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_organizations_api_key_hash", table_name="organizations")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("api_key_hash")
```

- [ ] **Step 3: Verify the migration applies cleanly**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS — `upgrade head` builds the new column/index and the existing structural drift guard still sees no `add_column`/`remove_column` diff (the model and migration now agree).

- [ ] **Step 4: Write the failing store tests**

Add to `tests/test_ledger_store.py` (imports `hashlib` at top if not present):

```python
def test_issue_and_authenticate_api_key_roundtrip(store):
    org = store.create_organization("KeyCo")
    key = store.issue_api_key(org.id)
    assert isinstance(key, str) and len(key) >= 20
    assert store.authenticate_org(key) == org.id


def test_rotating_api_key_invalidates_the_old_one(store):
    org = store.create_organization("RotateCo")
    old = store.issue_api_key(org.id)
    new = store.issue_api_key(org.id)
    assert new != old
    assert store.authenticate_org(old) is None
    assert store.authenticate_org(new) == org.id


def test_authenticate_rejects_unknown_empty_and_suspended(store, session_factory):
    from app.ledger.models import OrganizationRow
    assert store.authenticate_org("not-a-key") is None
    assert store.authenticate_org("") is None
    org = store.create_organization("SuspendCo")
    key = store.issue_api_key(org.id)
    with session_factory() as s:
        s.get(OrganizationRow, org.id).status = "suspended"
        s.commit()
    assert store.authenticate_org(key) is None


def test_issue_api_key_unknown_org_raises_lookup(store):
    with pytest.raises(LookupError):
        store.issue_api_key("no-such-org")


def test_duplicate_org_name_maps_integrity_error_to_value_error(store):
    store.create_organization("Acme Talent")
    with pytest.raises(ValueError):
        store.create_organization("Acme Talent")
```

- [ ] **Step 5: Run them to verify they fail**

Run: `pytest tests/test_ledger_store.py -k "api_key or duplicate_org_name_maps" -v`
Expected: FAIL — `issue_api_key`/`authenticate_org` do not exist yet.

- [ ] **Step 6: Implement the store changes**

In `app/ledger/store.py`, add imports:

```python
import hashlib
import secrets

from sqlalchemy.exc import IntegrityError
```

Add a module-level helper near `_utcnow`:

```python
def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

Extend the constructor:

```python
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        default_consent_ttl_days: int = 365,
        api_key_bytes: int = 32,
    ) -> None:
        self._session_factory = session_factory
        self._default_consent_ttl_days = default_consent_ttl_days
        self._api_key_bytes = api_key_bytes
```

Replace `create_organization` with the insert-then-map form (drops the pre-check TOCTOU):

```python
    def create_organization(self, name: str) -> Organization:
        with self._session_factory() as session:
            row = OrganizationRow(name=name)
            session.add(row)
            try:
                session.flush()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(f"organization name already exists: {name!r}") from exc
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
```

Add the two key methods after `delete_organization`:

```python
    def issue_api_key(self, org_id: str) -> str:
        """Generate + store (hashed) a fresh API key, returning the plaintext
        ONCE. Overwrites any previous key — this is also key rotation."""
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            if row is None:
                raise LookupError(f"unknown organization: {org_id}")
            raw = secrets.token_urlsafe(self._api_key_bytes)
            row.api_key_hash = _hash_api_key(raw)
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.issue_key",
                entity_type="organization",
                entity_id=org_id,
            )
            session.commit()
            return raw

    def authenticate_org(self, api_key: str) -> Optional[str]:
        """org_id for the active org holding this key, else None. Suspended
        orgs never authenticate; empty/whitespace keys never match."""
        api_key = (api_key or "").strip()
        if not api_key:
            return None
        digest = _hash_api_key(api_key)
        with self._session_factory() as session:
            row = session.execute(
                select(OrganizationRow).where(
                    OrganizationRow.api_key_hash == digest,
                    OrganizationRow.status == "active",
                )
            ).scalar_one_or_none()
            return row.id if row else None
```

- [ ] **Step 7: Run the store tests + migrations to verify green**

Run: `pytest tests/test_ledger_store.py tests/test_migrations.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/ledger/models.py alembic/versions/0004_org_api_keys.py app/ledger/store.py tests/test_ledger_store.py
git commit -m "feat(ledger): org-scoped API keys (hashed, rotatable) + dup-name IntegrityError mapping"
```

---

## Task 3: Strengthen the migration drift guard (residual D)

`compare_metadata` in the existing guard only checks table/column presence. Extend it so the migrated SQLite schema and the ORM metadata must also agree on indexes, FK `ondelete`, and column nullability — the axes the S3.1 review flagged as blind spots. This validates 0003 and the new 0004.

**Files:**
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Consumes: `_migrated_engine`, `Base.metadata`, SQLAlchemy `inspect`.
- Produces: two new tests — index parity and FK-ondelete/nullability parity — over the ledger tables.

- [ ] **Step 1: Write the failing index/nullability/ondelete parity tests**

Add to `tests/test_migrations.py`:

```python
LEDGER_TABLES = (
    "organizations", "consent_grants", "interview_records",
    "evaluation_events", "audit_log",
)


def test_migrated_indexes_match_orm(tmp_path):
    """Every index the ORM declares on a ledger table exists in the migrated
    schema (name + column set + uniqueness)."""
    engine = _migrated_engine(tmp_path)
    insp = inspect(engine)
    for table in LEDGER_TABLES:
        migrated = {
            ix["name"]: (tuple(ix["column_names"]), bool(ix["unique"]))
            for ix in insp.get_indexes(table)
        }
        orm = {
            ix.name: (tuple(c.name for c in ix.columns), bool(ix.unique))
            for ix in Base.metadata.tables[table].indexes
        }
        for name, spec in orm.items():
            assert name in migrated, f"{table}: migration missing index {name}"
            assert migrated[name] == spec, f"{table}.{name} index mismatch: {migrated[name]} != {spec}"


def test_migrated_fks_and_nullability_match_orm(tmp_path):
    """FK ondelete and column nullability agree between migration and models —
    the DPDP CASCADE contract must survive on the real migrated schema."""
    engine = _migrated_engine(tmp_path)
    insp = inspect(engine)
    for table in LEDGER_TABLES:
        migrated_cols = {c["name"]: c["nullable"] for c in insp.get_columns(table)}
        orm_cols = {c.name: c.nullable for c in Base.metadata.tables[table].columns}
        for name, nullable in orm_cols.items():
            assert migrated_cols[name] == nullable, (
                f"{table}.{name} nullability mismatch: migrated={migrated_cols[name]} orm={nullable}"
            )
        migrated_fk = {
            (tuple(fk["constrained_columns"])): fk.get("options", {}).get("ondelete")
            for fk in insp.get_foreign_keys(table)
        }
        for fk in Base.metadata.tables[table].foreign_key_constraints:
            cols = tuple(c.name for c in fk.columns)
            assert cols in migrated_fk, f"{table}: migration missing FK on {cols}"
            assert (migrated_fk[cols] or None) == (fk.ondelete or None), (
                f"{table} FK {cols} ondelete mismatch: {migrated_fk[cols]} != {fk.ondelete}"
            )
```

- [ ] **Step 2: Run them to verify they pass against the real migrations**

Run: `pytest tests/test_migrations.py -q`
Expected: PASS. (These assert the migrations are already correct — the guard's job is to keep them that way. If either fails, the migration is genuinely out of sync with the models and must be corrected before proceeding.)

- [ ] **Step 3: Prove the guard bites — temporary sabotage check**

Temporarily edit `alembic/versions/0004_org_api_keys.py` and change the index line to `unique=False`. Run:
`pytest tests/test_migrations.py::test_migrated_indexes_match_orm -q`
Expected: FAIL (proves the guard detects uniqueness drift). Then revert the sabotage and re-run — Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_migrations.py
git commit -m "test(ledger): drift guard now covers indexes, FK ondelete, and nullability"
```

---

## Task 4: `query_records_for_org` — read enforcement + audit-of-reads

The centerpiece store method: `ledger_read` enforced at query time, and every read attempt — allowed or denied — written to `audit_log` in the same transaction. Also a small `get_record` used by the event-append ownership check.

**Files:**
- Modify: `app/ledger/store.py` (add `get_record`, `query_records_for_org`)
- Test: `tests/test_ledger_store_records.py`

**Interfaces:**
- Consumes: `ConsentError`, `consent_logic.check_consent`, `_grants_for`, `_audit`, `_record`, `InterviewRecordRow`, `OrganizationRow`, `CandidateRow`, `ConsentPurpose.LEDGER_READ`.
- Produces:
  - `LedgerStore.get_record(record_id: str) -> Optional[InterviewRecord]`.
  - `LedgerStore.query_records_for_org(*, org_id: str, candidate_id: str, at: Optional[datetime] = None) -> list[InterviewRecord]` — raises `LookupError` (unknown org/candidate, no audit written), raises `ConsentError` (known but ungranted, denied read audited), else returns records and audits an allowed read with the record count.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger_store_records.py` (reuse that file's existing fixtures for `store`, `candidate_id`, and a helper to grant + submit; if it lacks them, mirror the setup used elsewhere in the file). Minimal self-contained additions:

```python
def test_query_records_allowed_returns_records_and_audits_read(store, candidate_id):
    org = store.create_organization("ReaderCo")
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write", org_id=org.id)
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_read", org_id=org.id)
    rec = store.submit_interview_record(
        org_id=org.id, candidate_id=candidate_id, stage="tech",
        outcome="advanced", interviewed_at=NOW,
    )
    got = store.query_records_for_org(org_id=org.id, candidate_id=candidate_id)
    assert [r.id for r in got] == [rec.id]
    reads = [a for a in store.audit_for_candidate(candidate_id) if a.action == "record.query"]
    assert len(reads) == 1
    assert reads[0].actor_type == "org" and reads[0].actor_id == org.id
    assert reads[0].details["allowed"] is True and reads[0].details["record_count"] == 1


def test_query_records_without_read_consent_denied_and_audited(store, candidate_id):
    org = store.create_organization("NosyCo")
    with pytest.raises(ConsentError):
        store.query_records_for_org(org_id=org.id, candidate_id=candidate_id)
    reads = [a for a in store.audit_for_candidate(candidate_id) if a.action == "record.query"]
    assert len(reads) == 1 and reads[0].details["allowed"] is False


def test_query_records_unknown_candidate_or_org_raises_and_writes_no_audit(store, candidate_id):
    org = store.create_organization("EdgeCo")
    with pytest.raises(LookupError):
        store.query_records_for_org(org_id=org.id, candidate_id="no-such-candidate")
    with pytest.raises(LookupError):
        store.query_records_for_org(org_id="no-such-org", candidate_id=candidate_id)
    assert [a for a in store.audit_for_candidate(candidate_id) if a.action == "record.query"] == []


def test_query_records_denied_after_read_consent_revoked_point_in_time(store, candidate_id):
    from datetime import timedelta
    org = store.create_organization("RevokeReadCo")
    grant = store.grant_consent(candidate_id=candidate_id, purpose="ledger_read",
                                org_id=org.id, now=NOW)
    store.revoke_consent(grant.id, now=NOW + timedelta(days=1))
    # A query "at" a moment after revocation is denied.
    with pytest.raises(ConsentError):
        store.query_records_for_org(org_id=org.id, candidate_id=candidate_id,
                                    at=NOW + timedelta(days=2))
```

Ensure the file imports `ConsentError` and defines `NOW` (mirror `tests/test_ledger_store.py`: `NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)`) — add them if absent.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_store_records.py -k query_records -v`
Expected: FAIL — `query_records_for_org` does not exist.

- [ ] **Step 3: Implement `get_record` + `query_records_for_org`**

In `app/ledger/store.py`, add after `records_for_candidate`:

```python
    def get_record(self, record_id: str) -> Optional[InterviewRecord]:
        with self._session_factory() as session:
            row = session.get(InterviewRecordRow, record_id)
            return _record(row) if row else None

    def query_records_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
    ) -> list[InterviewRecord]:
        """Query-time DPDP gate: an org may read a candidate's records only under
        an active ledger_read grant. Every read attempt — allowed or denied — is
        audited in the same transaction (surveillance is itself observable)."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_READ)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_READ, at=moment
            )
            if not decision.allowed:
                self._audit(
                    session,
                    actor_type="org",
                    actor_id=org_id,
                    action="record.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "ledger_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)
            rows = (
                session.execute(
                    select(InterviewRecordRow)
                    .where(InterviewRecordRow.candidate_id == candidate_id)
                    .order_by(InterviewRecordRow.created_at, InterviewRecordRow.id)
                )
                .scalars()
                .all()
            )
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="record.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "record_count": len(rows),
                },
            )
            session.commit()
            return [_record(r) for r in rows]
```

- [ ] **Step 4: Run them to verify they pass**

Run: `pytest tests/test_ledger_store_records.py -k query_records -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_records.py
git commit -m "feat(ledger): query-time ledger_read enforcement + audit-of-reads"
```

---

## Task 5: Wire `LedgerStore` into `Services` + test scaffolding

Make the ledger store part of the injected service bundle, sharing the candidate store's DB so candidate FKs resolve. Offline tests build both stores on one in-memory engine.

**Files:**
- Modify: `app/services/__init__.py`
- Modify: `app/ledger/store.py` (`build_ledger_store` — pass `api_key_bytes`; the config knob itself lands in Task 10, so read it defensively here)
- Modify: `tests/conftest.py`
- Test: `tests/test_ledger_api.py` (new — one wiring test to start the file)

**Interfaces:**
- Consumes: `LedgerStore`, `build_ledger_store`, `CandidateStore._session_factory`.
- Produces: `Services.ledger: LedgerStore`; `build_default_services(...)` populates it; `make_services(..., ledger=None)` builds a ledger sharing the candidate store's session factory.

- [ ] **Step 1: Add `ledger` to the `Services` dataclass + default builder**

In `app/services/__init__.py`:

```python
from app.ledger.store import LedgerStore, build_ledger_store
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
```

```python
def build_default_services(settings: Optional[Settings] = None) -> Services:
    settings = settings or get_settings()
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=GitHubClient(settings),
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=build_candidate_store(settings),
        ledger=build_ledger_store(settings),
    )
```

- [ ] **Step 2: Make `build_ledger_store` pass `api_key_bytes` defensively**

In `app/ledger/store.py`, update `build_ledger_store` so it works before AND after Task 10 adds the config knob:

```python
def build_ledger_store(settings: Optional[Settings] = None) -> LedgerStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job (`alembic upgrade head`), NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return LedgerStore(
        make_session_factory(engine),
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        api_key_bytes=getattr(settings, "ledger_api_key_bytes", 32),
    )
```

- [ ] **Step 3: Update conftest to build a shared-DB ledger store**

In `tests/conftest.py`, add the model import (so `create_all` builds ledger tables) and the store import near the others:

```python
import app.ledger.models  # noqa: F401 — populate Base.metadata with ledger tables
from app.ledger.store import LedgerStore
```

Extend `make_services` to accept and default a `ledger`:

```python
def make_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    github: FakeGitHub | None = None,
    flywheel: InMemoryFlywheel | None = None,
    candidates: CandidateStore | None = None,
    ledger: LedgerStore | None = None,
) -> Services:
    candidates = candidates or make_candidate_store()
    ledger = ledger or LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
    )
    return Services(
        settings=settings,
        llm=llm or NullLLM(settings),
        vectorstore=InMemoryVectorStore(),
        github=github or FakeGitHub(),
        flywheel=flywheel or InMemoryFlywheel(),
        report_store=InMemoryReportStore(),
        candidates=candidates,
        ledger=ledger,
    )
```

- [ ] **Step 4: Write the wiring test**

Create `tests/test_ledger_api.py`:

```python
"""S3.2 ledger HTTP surface — offline TestClient over injected in-memory stores."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.ledger.store import LedgerStore
from app.main import create_app
from tests.conftest import make_services

RESUME = """Asha Rao
Email: asha.rao@example.com | Phone: +91 98765 43210

EXPERIENCE
- Senior ML Engineer, Acme AI (2021 - Present)

SKILLS
Python, PyTorch
"""


def test_services_bundle_has_ledger_sharing_candidate_db(services):
    assert isinstance(services.ledger, LedgerStore)
    assert isinstance(services.candidates, CandidateStore)
```

- [ ] **Step 5: Run the wiring test + the full suite**

Run: `pytest tests/test_ledger_api.py -q && pytest -q`
Expected: PASS. (The `services` fixture now builds a ledger sharing the candidate DB; all prior tests still green because `make_services` grew an optional param with a default.)

- [ ] **Step 6: Commit**

```bash
git add app/services/__init__.py app/ledger/store.py tests/conftest.py tests/test_ledger_api.py
git commit -m "feat(ledger): inject LedgerStore into Services (shared candidate DB)"
```

---

## Task 6: Org management endpoints (admin-gated)

Platform/admin surface to onboard orgs and issue their keys. On the existing `router`, so the shared-secret `X-API-Key` gate applies.

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_ledger_api.py`

**Interfaces:**
- Consumes: `Organization` (`app/ledger/schema.py`), `_services`, existing `router` (admin-gated).
- Produces (all under `/ledger/orgs`):
  - `POST /ledger/orgs` body `{name}` → `{org, api_key}` (201-style 200; key shown once); 409 on duplicate name.
  - `GET /ledger/orgs` → `list[Organization]` (no keys).
  - `POST /ledger/orgs/{org_id}/api-key` → `{org_id, api_key}` (rotate); 404 unknown org.
  - `DELETE /ledger/orgs/{org_id}` → `{org_id, deleted}`; 404 unknown org.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger_api.py`:

```python
@pytest.fixture
def api(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


def test_create_org_returns_one_time_key_and_lists_without_keys(api):
    client, _ = api
    resp = client.post("/ledger/orgs", json={"name": "Acme Talent"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["org"]["name"] == "Acme Talent" and body["org"]["status"] == "active"
    assert isinstance(body["api_key"], str) and body["api_key"]
    listed = client.get("/ledger/orgs").json()
    assert [o["name"] for o in listed] == ["Acme Talent"]
    assert "api_key" not in listed[0] and "api_key_hash" not in listed[0]


def test_create_org_duplicate_name_conflicts(api):
    client, _ = api
    client.post("/ledger/orgs", json={"name": "Dup Co"})
    assert client.post("/ledger/orgs", json={"name": "Dup Co"}).status_code == 409


def test_rotate_and_delete_org(api):
    client, _ = api
    org = client.post("/ledger/orgs", json={"name": "Rot Co"}).json()["org"]
    rotated = client.post(f"/ledger/orgs/{org['id']}/api-key")
    assert rotated.status_code == 200 and rotated.json()["api_key"]
    assert client.post("/ledger/orgs/no-such/api-key").status_code == 404
    assert client.delete(f"/ledger/orgs/{org['id']}").status_code == 200
    assert client.delete(f"/ledger/orgs/{org['id']}").status_code == 404


def test_org_endpoints_behind_admin_key(settings, flywheel):
    from pydantic import SecretStr
    locked = settings.model_copy(update={"api_auth_key": SecretStr("s3cret")})
    services = make_services(locked, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/ledger/orgs", json={"name": "X"}).status_code == 401
        ok = client.post("/ledger/orgs", json={"name": "X"}, headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_api.py -k "org" -v`
Expected: FAIL — endpoints not defined (404).

- [ ] **Step 3: Implement the org endpoints**

In `app/api/routes.py`, add imports:

```python
from app.ledger.schema import Organization
```

Add, after the candidate endpoints (still on the admin-gated `router`):

```python
# ── Evaluation ledger (S3.2) ────────────────────────────────────────────────
# Org lifecycle + consent are ADMIN operations (shared-secret X-API-Key gate).
# Org data operations (records/events/query) authenticate with an org's own key
# on `org_router` below.


class OrgCreateRequest(BaseModel):
    name: str


class OrgCreateResponse(BaseModel):
    org: Organization
    api_key: str  # returned once; only its hash is stored


@router.post("/ledger/orgs", response_model=OrgCreateResponse)
async def create_org(req: OrgCreateRequest, request: Request) -> OrgCreateResponse:
    ledger = _services(request).ledger
    try:
        org = ledger.create_organization(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OrgCreateResponse(org=org, api_key=ledger.issue_api_key(org.id))


@router.get("/ledger/orgs", response_model=list[Organization])
async def list_orgs(request: Request) -> list[Organization]:
    return _services(request).ledger.list_organizations()


@router.post("/ledger/orgs/{org_id}/api-key")
async def rotate_org_key(org_id: str, request: Request) -> dict:
    try:
        api_key = _services(request).ledger.issue_api_key(org_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"org_id": org_id, "api_key": api_key}


@router.delete("/ledger/orgs/{org_id}")
async def delete_org(org_id: str, request: Request) -> dict:
    if not _services(request).ledger.delete_organization(org_id):
        raise HTTPException(status_code=404, detail="organization not found")
    return {"org_id": org_id, "deleted": True}
```

- [ ] **Step 4: Run the org tests to verify they pass**

Run: `pytest tests/test_ledger_api.py -k "org" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_ledger_api.py
git commit -m "feat(api): ledger org management endpoints (admin-gated, one-time keys)"
```

---

## Task 7: Consent management endpoints (admin-gated)

Record and revoke candidate consent, and check status. Admin-gated (there is no candidate auth yet; the platform records consent on the data principal's behalf, and the store attributes it to `candidate` in the audit trail).

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_ledger_api.py`

**Interfaces:**
- Consumes: `ConsentGrant`, `ConsentDecision`, `ConsentPurpose`; `_services`.
- Produces:
  - `POST /ledger/candidates/{candidate_id}/consent` body `{purpose, org_id?, expires_at?}` → `ConsentGrant`; 404 unknown candidate/org.
  - `POST /ledger/consent/{consent_id}/revoke` → `{consent_id, revoked}`.
  - `GET /ledger/candidates/{candidate_id}/consent?org_id=&purpose=` → `ConsentDecision`; 404 unknown candidate/org.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger_api.py` (helper to create a candidate through the injected store):

```python
async def _ingest_candidate(services, text=RESUME):
    result = await extract_profile(text, llm=services.llm, settings=services.settings)
    return services.candidates.ingest(result, text).candidate_id


def test_grant_revoke_and_status_consent(api):
    import asyncio
    client, services = api
    cid = asyncio.get_event_loop().run_until_complete(_ingest_candidate(services))
    org = client.post("/ledger/orgs", json={"name": "Consent Co"}).json()["org"]

    granted = client.post(
        f"/ledger/candidates/{cid}/consent",
        json={"purpose": "ledger_read", "org_id": org["id"]},
    )
    assert granted.status_code == 200, granted.text
    grant = granted.json()
    assert grant["purpose"] == "ledger_read" and grant["org_id"] == org["id"]

    status = client.get(
        f"/ledger/candidates/{cid}/consent",
        params={"org_id": org["id"], "purpose": "ledger_read"},
    ).json()
    assert status["allowed"] is True and status["grant_id"] == grant["id"]

    revoked = client.post(f"/ledger/consent/{grant['id']}/revoke").json()
    assert revoked["revoked"] is True
    assert client.post(f"/ledger/consent/{grant['id']}/revoke").json()["revoked"] is False

    after = client.get(
        f"/ledger/candidates/{cid}/consent",
        params={"org_id": org["id"], "purpose": "ledger_read"},
    ).json()
    assert after["allowed"] is False


def test_consent_endpoints_404_on_unknown_candidate(api):
    client, _ = api
    org = client.post("/ledger/orgs", json={"name": "Ghost Co"}).json()["org"]
    assert client.post(
        "/ledger/candidates/nope/consent",
        json={"purpose": "ledger_read", "org_id": org["id"]},
    ).status_code == 404
    assert client.get(
        "/ledger/candidates/nope/consent",
        params={"org_id": org["id"], "purpose": "ledger_read"},
    ).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_api.py -k "consent" -v`
Expected: FAIL — endpoints not defined.

- [ ] **Step 3: Implement the consent endpoints**

In `app/api/routes.py`, extend the ledger schema import:

```python
from app.ledger.schema import ConsentDecision, ConsentGrant, ConsentPurpose, Organization
```

Add after the org endpoints:

```python
class ConsentGrantRequest(BaseModel):
    purpose: ConsentPurpose
    org_id: Optional[str] = None  # None = any member org
    expires_at: Optional[datetime] = None  # None ⇒ default TTL


@router.post("/ledger/candidates/{candidate_id}/consent", response_model=ConsentGrant)
async def grant_consent(
    candidate_id: str, req: ConsentGrantRequest, request: Request
) -> ConsentGrant:
    ledger = _services(request).ledger
    try:
        return ledger.grant_consent(
            candidate_id=candidate_id,
            purpose=req.purpose,
            org_id=req.org_id,
            expires_at=req.expires_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ledger/consent/{consent_id}/revoke")
async def revoke_consent(consent_id: str, request: Request) -> dict:
    revoked = _services(request).ledger.revoke_consent(consent_id)
    return {"consent_id": consent_id, "revoked": revoked}


@router.get("/ledger/candidates/{candidate_id}/consent", response_model=ConsentDecision)
async def consent_status(
    candidate_id: str, request: Request, org_id: str, purpose: ConsentPurpose
) -> ConsentDecision:
    try:
        return _services(request).ledger.consent_status(
            candidate_id, org_id=org_id, purpose=purpose
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 4: Run the consent tests to verify they pass**

Run: `pytest tests/test_ledger_api.py -k "consent" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_ledger_api.py
git commit -m "feat(api): ledger consent grant/revoke/status endpoints (admin-gated)"
```

---

## Task 8: Record submit + event append (org-gated) + `require_org`

Introduce the org auth plane: `require_org` resolves `X-Org-Key` → `org_id`, and `org_router` carries the org data endpoints (NOT admin-gated). Submit is write-consent gated at the store; event append enforces record ownership.

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py` (include `org_router`)
- Test: `tests/test_ledger_api.py`

**Interfaces:**
- Consumes: `authenticate_org`, `submit_interview_record`, `get_record`, `append_event`, `ConsentError`; `InterviewRecord`, `EvaluationEvent`, `InterviewStage`, `InterviewOutcome`.
- Produces:
  - `require_org(request, x_org_key) -> str` (401 if unresolved).
  - `org_router` included in the app.
  - `POST /ledger/records` (org-gated) body `{candidate_id, stage, outcome, interviewed_at, summary?}` → `InterviewRecord`; 403 no write consent, 404 unknown candidate.
  - `POST /ledger/records/{record_id}/events` (org-gated) body `{event_type, payload?}` → `EvaluationEvent`; 404 if record missing or owned by another org.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger_api.py` (a helper that sets up org + key + candidate + write-consent):

```python
def _org_with_key(client):
    body = client.post("/ledger/orgs", json={"name": f"Org {id(client)}"}).json()
    return body["org"]["id"], body["api_key"]


def _setup_org_candidate(api, *, read=False):
    import asyncio
    client, services = api
    cid = asyncio.get_event_loop().run_until_complete(_ingest_candidate(services))
    body = client.post("/ledger/orgs", json={"name": "Data Co"}).json()
    org_id, key = body["org"]["id"], body["api_key"]
    client.post(f"/ledger/candidates/{cid}/consent",
                json={"purpose": "ledger_write", "org_id": org_id})
    if read:
        client.post(f"/ledger/candidates/{cid}/consent",
                    json={"purpose": "ledger_read", "org_id": org_id})
    return client, cid, org_id, key


def test_submit_record_requires_valid_org_key(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    payload = {"candidate_id": cid, "stage": "tech", "outcome": "advanced",
               "interviewed_at": "2026-07-20T10:00:00+00:00"}
    assert client.post("/ledger/records", json=payload).status_code == 401
    assert client.post("/ledger/records", json=payload,
                       headers={"X-Org-Key": "wrong"}).status_code == 401
    ok = client.post("/ledger/records", json=payload, headers={"X-Org-Key": key})
    assert ok.status_code == 200, ok.text
    assert ok.json()["candidate_id"] == cid and ok.json()["consent_id"]


def test_submit_record_without_write_consent_is_403(api):
    import asyncio
    client, services = api
    cid = asyncio.get_event_loop().run_until_complete(_ingest_candidate(services))
    _, key = _org_with_key(client)  # org exists but no consent granted
    payload = {"candidate_id": cid, "stage": "tech", "outcome": "advanced",
               "interviewed_at": "2026-07-20T10:00:00+00:00"}
    resp = client.post("/ledger/records", json=payload, headers={"X-Org-Key": key})
    assert resp.status_code == 403


def test_submit_record_unknown_candidate_is_404(api):
    client = api[0]
    _, key = _org_with_key(client)
    payload = {"candidate_id": "no-such", "stage": "tech", "outcome": "advanced",
               "interviewed_at": "2026-07-20T10:00:00+00:00"}
    assert client.post("/ledger/records", json=payload,
                       headers={"X-Org-Key": key}).status_code == 404


def test_append_event_ownership_enforced(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    rec = client.post(
        "/ledger/records",
        json={"candidate_id": cid, "stage": "tech", "outcome": "advanced",
              "interviewed_at": "2026-07-20T10:00:00+00:00"},
        headers={"X-Org-Key": key},
    ).json()
    ok = client.post(f"/ledger/records/{rec['id']}/events",
                     json={"event_type": "score", "payload": {"value": 4}},
                     headers={"X-Org-Key": key})
    assert ok.status_code == 200 and ok.json()["record_id"] == rec["id"]
    # A different org cannot append to this record.
    other = client.post("/ledger/orgs", json={"name": "Other Co"}).json()["api_key"]
    resp = client.post(f"/ledger/records/{rec['id']}/events",
                       json={"event_type": "score", "payload": {"value": 1}},
                       headers={"X-Org-Key": other})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_api.py -k "submit_record or append_event" -v`
Expected: FAIL — org endpoints not defined.

- [ ] **Step 3: Implement `require_org`, `org_router`, and the two endpoints**

In `app/api/routes.py`, extend imports:

```python
from app.ledger.schema import (
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
)
from app.ledger.store import ConsentError
```

Add the dependency + router near the top (after `require_api_key` / router definitions):

```python
async def require_org(
    request: Request, x_org_key: Optional[str] = Header(default=None)
) -> str:
    """Resolve an org's own API key to its id (S3.2). Unlike the admin key,
    this is always enforced — org data operations are never open."""
    org_id = _services(request).ledger.authenticate_org(x_org_key or "")
    if org_id is None:
        raise HTTPException(status_code=401, detail="invalid or missing X-Org-Key")
    return org_id


# Org-authenticated data plane (X-Org-Key), separate from the admin router so an
# org never needs the platform's shared secret to submit or query its own data.
org_router = APIRouter()
```

Add the endpoints (after the consent endpoints):

```python
class RecordSubmitRequest(BaseModel):
    candidate_id: str
    stage: InterviewStage
    outcome: InterviewOutcome
    interviewed_at: datetime
    summary: Optional[str] = None


@org_router.post("/ledger/records", response_model=InterviewRecord)
async def submit_record(
    req: RecordSubmitRequest, request: Request, org_id: str = Depends(require_org)
) -> InterviewRecord:
    ledger = _services(request).ledger
    try:
        return ledger.submit_interview_record(
            org_id=org_id,
            candidate_id=req.candidate_id,
            stage=req.stage,
            outcome=req.outcome,
            interviewed_at=req.interviewed_at,
            summary=req.summary,
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class EventAppendRequest(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)


@org_router.post("/ledger/records/{record_id}/events", response_model=EvaluationEvent)
async def append_event(
    record_id: str,
    req: EventAppendRequest,
    request: Request,
    org_id: str = Depends(require_org),
) -> EvaluationEvent:
    ledger = _services(request).ledger
    record = ledger.get_record(record_id)
    if record is None or record.org_id != org_id:
        raise HTTPException(status_code=404, detail="record not found")
    return ledger.append_event(record_id, event_type=req.event_type, payload=req.payload)
```

- [ ] **Step 4: Include `org_router` in the app**

In `app/main.py`, update the import and include:

```python
from app.api.routes import org_router, public_router, router
```

```python
    app.include_router(router)
    app.include_router(org_router)
    app.include_router(public_router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_ledger_api.py -k "submit_record or append_event" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_ledger_api.py
git commit -m "feat(api): org-gated record submit + event append (X-Org-Key auth)"
```

---

## Task 9: Ledger read/query endpoint (org-gated, enforced + audited)

The read surface: an org queries a candidate's records only with active `ledger_read`; each attempt is audited by the store.

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_ledger_api.py`

**Interfaces:**
- Consumes: `query_records_for_org`, `ConsentError`, `require_org`, `InterviewRecord`.
- Produces: `GET /ledger/candidates/{candidate_id}/records` (org-gated) → `list[InterviewRecord]`; 403 no read consent, 404 unknown candidate, 401 bad key.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger_api.py`:

```python
def test_query_records_requires_read_consent_and_audits(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    services = api[1]
    client.post(
        "/ledger/records",
        json={"candidate_id": cid, "stage": "tech", "outcome": "advanced",
              "interviewed_at": "2026-07-20T10:00:00+00:00"},
        headers={"X-Org-Key": key},
    )
    resp = client.get(f"/ledger/candidates/{cid}/records", headers={"X-Org-Key": key})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1 and resp.json()[0]["candidate_id"] == cid
    reads = [a for a in services.ledger.audit_for_candidate(cid) if a.action == "record.query"]
    assert reads and reads[-1].details["allowed"] is True


def test_query_records_denied_without_read_consent(api):
    # write consent only (read=False) → query is forbidden and audited denied.
    client, cid, org_id, key = _setup_org_candidate(api, read=False)
    services = api[1]
    resp = client.get(f"/ledger/candidates/{cid}/records", headers={"X-Org-Key": key})
    assert resp.status_code == 403
    reads = [a for a in services.ledger.audit_for_candidate(cid) if a.action == "record.query"]
    assert reads and reads[-1].details["allowed"] is False


def test_query_records_bad_key_and_unknown_candidate(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    assert client.get(f"/ledger/candidates/{cid}/records").status_code == 401
    assert client.get("/ledger/candidates/nope/records",
                      headers={"X-Org-Key": key}).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_api.py -k "query_records" -v`
Expected: FAIL — endpoint not defined.

- [ ] **Step 3: Implement the query endpoint**

In `app/api/routes.py`, add after `append_event`:

```python
@org_router.get(
    "/ledger/candidates/{candidate_id}/records", response_model=list[InterviewRecord]
)
async def query_records(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> list[InterviewRecord]:
    """Query-time ledger_read enforcement. The store audits every attempt."""
    ledger = _services(request).ledger
    try:
        return ledger.query_records_for_org(org_id=org_id, candidate_id=candidate_id)
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 4: Run the query tests + the full HTTP file to verify they pass**

Run: `pytest tests/test_ledger_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_ledger_api.py
git commit -m "feat(api): org-gated ledger read query with query-time consent enforcement"
```

---

## Task 10: Config knob, root listing, LEDGER.md S3.2 docs

Land the one tunable, expose the new endpoints on the root index, and document the sprint.

**Files:**
- Modify: `app/core/config.py:178-182` (ledger section)
- Modify: `config.yaml` (ledger section, ~line 102-106)
- Modify: `app/main.py` (root endpoint listing)
- Modify: `LEDGER.md`
- Test: `tests/test_ledger_store.py` (one knob test)

**Interfaces:**
- Consumes: `Settings`.
- Produces: `Settings.ledger_api_key_bytes: int` (default 32, `ge=16`), consumed by `build_ledger_store`.

- [ ] **Step 1: Add the config knob (failing test first)**

Add to `tests/test_ledger_store.py`:

```python
def test_ledger_api_key_bytes_default_and_floor():
    from pydantic import ValidationError
    from app.core.config import Settings
    assert Settings(_env_file=None).ledger_api_key_bytes == 32
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ledger_api_key_bytes=8)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_ledger_store.py -k ledger_api_key_bytes -v`
Expected: FAIL — attribute does not exist.

- [ ] **Step 3: Add the knob to Settings + config.yaml**

In `app/core/config.py`, under the ledger section (after `ledger_consent_default_ttl_days`):

```python
    # Byte length of generated org API keys (secrets.token_urlsafe). Floor keeps
    # keys high-entropy; the plaintext is returned once and only its hash stored.
    ledger_api_key_bytes: int = Field(default=32, ge=16)
```

In `config.yaml`, under the `# --- Evaluation ledger (PI-3) ...` section:

```yaml
ledger_api_key_bytes: 32
```

- [ ] **Step 4: Run the knob test to verify it passes**

Run: `pytest tests/test_ledger_store.py -k ledger_api_key_bytes -q`
Expected: PASS

- [ ] **Step 5: Extend the root endpoint listing**

In `app/main.py`, add the ledger endpoints to the `"endpoints"` list in `root()`:

```python
                "POST /ledger/orgs",
                "GET /ledger/orgs",
                "POST /ledger/orgs/{id}/api-key",
                "DELETE /ledger/orgs/{id}",
                "POST /ledger/candidates/{id}/consent",
                "POST /ledger/consent/{id}/revoke",
                "GET /ledger/candidates/{id}/consent",
                "POST /ledger/records",
                "POST /ledger/records/{id}/events",
                "GET /ledger/candidates/{id}/records",
```

- [ ] **Step 6: Document S3.2 in LEDGER.md**

Append to `LEDGER.md`:

```markdown
## S3.2 — ledger APIs (this sprint)

Two auth planes over `LedgerStore`:

- **Admin plane** (existing `X-API-Key` shared secret, `router`): org lifecycle
  and consent recording — platform operations.
  - `POST /ledger/orgs` → creates an org, returns a one-time `api_key`
    (only its sha256 hash is stored); duplicate name → 409.
  - `GET /ledger/orgs` · `POST /ledger/orgs/{id}/api-key` (rotate) ·
    `DELETE /ledger/orgs/{id}` (hard cascade offboarding).
  - `POST /ledger/candidates/{id}/consent` (grant) ·
    `POST /ledger/consent/{id}/revoke` · `GET /ledger/candidates/{id}/consent`
    (status; 404 for unknown candidate/org, 200 with `allowed:false` when known
    but ungranted).
- **Org plane** (`X-Org-Key` → one org via `authenticate_org`, `org_router` — an
  org never needs the platform secret to touch its own data):
  - `POST /ledger/records` — write-consent gated at the store (403 without an
    active `ledger_write` grant; 404 unknown candidate).
  - `POST /ledger/records/{id}/events` — ownership enforced (404 if the record
    belongs to another org).
  - `GET /ledger/candidates/{id}/records` — **query-time `ledger_read`
    enforcement**: 403 without an active read grant. Every read attempt —
    allowed or denied — is written to `audit_log` (`record.query`, actor `org`)
    in the same transaction, so probing is itself observable.

**Org API keys:** `secrets.token_urlsafe(ledger_api_key_bytes)` (default 32),
stored as sha256 hex in `organizations.api_key_hash` (migration
`0004_org_api_keys`, unique index). Suspended orgs never authenticate. Rotation
overwrites the hash, invalidating the old key.

**S3.1 residuals closed this sprint:** deterministic authorizing-grant selection
(org-specific ▸ newest ▸ lowest id) so stamped `consent_id` and audited reads are
reproducible; `consent_status` raises `LookupError` (→ 404) for unknown
candidate/org vs a denied decision (→ 200) when known; `create_organization`
maps the unique-name `IntegrityError` to `ValueError` (→ 409), no TOCTOU; the
migration drift guard now also checks indexes, FK `ondelete`, and nullability.

**Not in S3.2:** coding-round ingest (S3.3); reputation aggregation (S3.4);
candidate-facing consent auth (platform records consent on the principal's
behalf, audited as actor `candidate`).
```

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS (all green).

- [ ] **Step 8: Commit**

```bash
git add app/core/config.py config.yaml app/main.py LEDGER.md tests/test_ledger_store.py
git commit -m "feat(ledger): api_key_bytes knob, root endpoint listing, S3.2 docs"
```

---

## Task 11: Smoke — `scripts/smoke_s32.py` (uvicorn HTTP end-to-end)

Boot the real app over a freshly-migrated scratch DB and drive the full S3.2 flow via HTTP, including the admin-key gate and the consent transitions (403 → grant → 200 → revoke → 403).

**Files:**
- Create: `scripts/smoke_s32.py`

**Interfaces:**
- Consumes: the running HTTP app (`app.main:app`), Alembic `command.upgrade`, `httpx`.
- Produces: a script that exits 0 on `SMOKE OK`, 1 on any failed check.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s32.py`:

```python
"""S3.2 smoke: the ledger HTTP surface end to end.

Migrates a scratch DB with Alembic, boots uvicorn with an admin key set, then:
create org (one-time key) → ingest a candidate → submit WITHOUT write consent
(403) → grant write consent → submit (200) → append event (200) → query WITHOUT
read consent (403) → grant read consent → query (200, 1 record) → revoke read →
query (403) → DPDP erase candidate → query 404. LLM-free; heuristic extraction
with no API key. Run from the repo root:
    python scripts/smoke_s32.py
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

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8032
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
INTERVIEWED_AT = "2026-07-20T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s32.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_API_AUTH_KEY": ADMIN,
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        admin_h = {"X-API-Key": ADMIN}
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

            # Admin gate: org creation without the key is rejected.
            unauth = c.post("/ledger/orgs", json={"name": "Acme Talent"})

            created = c.post("/ledger/orgs", json={"name": "Acme Talent"}, headers=admin_h).json()
            org_id, org_key = created["org"]["id"], created["api_key"]
            org_h = {"X-Org-Key": org_key}
            print(f"org: {org_id[:8]} key issued")

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            print(f"candidate [{cand['extraction_method']}]: {cid[:8]}")

            submit_payload = {
                "candidate_id": cid, "stage": "tech", "outcome": "advanced",
                "interviewed_at": INTERVIEWED_AT, "summary": "solid systems round",
            }
            refused = c.post("/ledger/records", json=submit_payload, headers=org_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_write", "org_id": org_id}, headers=admin_h)
            rec = c.post("/ledger/records", json=submit_payload, headers=org_h)
            rec_id = rec.json().get("id") if rec.status_code == 200 else None
            event = c.post(f"/ledger/records/{rec_id}/events",
                           json={"event_type": "score", "payload": {"value": 4}},
                           headers=org_h) if rec_id else None

            query_denied = c.get(f"/ledger/candidates/{cid}/records", headers=org_h)

            read_grant = c.post(f"/ledger/candidates/{cid}/consent",
                                json={"purpose": "ledger_read", "org_id": org_id},
                                headers=admin_h).json()
            query_ok = c.get(f"/ledger/candidates/{cid}/records", headers=org_h)

            c.post(f"/ledger/consent/{read_grant['id']}/revoke", headers=admin_h)
            query_after_revoke = c.get(f"/ledger/candidates/{cid}/records", headers=org_h)

            c.delete(f"/candidates/{cid}", headers=admin_h)
            query_after_erase = c.get(f"/ledger/candidates/{cid}/records", headers=org_h)

        checks = {
            "org create needs admin key": unauth.status_code == 401,
            "org created with one-time key": bool(org_key),
            "submit without write consent 403": refused.status_code == 403,
            "submit with consent 200": rec.status_code == 200,
            "event appended": event is not None and event.status_code == 200,
            "query without read consent 403": query_denied.status_code == 403,
            "query with read consent returns 1 record": query_ok.status_code == 200
            and len(query_ok.json()) == 1,
            "query after read revoke 403": query_after_revoke.status_code == 403,
            "query after DPDP erasure 404": query_after_erase.status_code == 404,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke key-less**

Run: `python scripts/smoke_s32.py`
Expected: all 9 checks `OK`, `SMOKE OK`, exit 0. (No OpenRouter key needed — candidate extraction falls to the heuristic floor, which the ledger flow does not depend on.)

- [ ] **Step 3: Run the full suite one final time**

Run: `pytest -q`
Expected: PASS (all green).

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_s32.py
git commit -m "test(ledger): S3.2 HTTP smoke — orgs, consent, submit/query, audit, DPDP"
```

---

## Post-implementation (end of sprint)

- [ ] Final whole-branch review (most capable model). Land any Important findings.
- [ ] Update `docs/ROADMAP.md`: flip S3.2 to `[x]` on the status board, refresh **Current state** (Current sprint → S3.3, Next action → S3.3 plan), add a session-log entry, and record any accepted residuals in `.superpowers/sdd/progress.md`.
- [ ] Merge to `main` (fast-forward), delete the branch.

---

## Self-Review

**Spec coverage** (roadmap S3.2 scope: "submit/query with consent enforced at query time; org-scoped API keys; audit trail" + four S3.1 residuals):
- submit endpoint → Task 8. query endpoint → Task 9. Query-time `ledger_read` enforcement → Task 4 (store) + Task 9 (HTTP). Org-scoped API keys → Task 2 (store/schema) + Tasks 6/8 (issue + authenticate over HTTP). Audit of reads → Task 4. Residual A (deterministic consent_id) → Task 1. Residual B (consent_status 404-vs-403) → Task 1. Residual C (org-create IntegrityError) → Task 2. Residual D (drift guard blind spots) → Task 3. All covered.

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step shows complete code; every run step names an exact command + expected result.

**Type consistency:** `authenticate_org(api_key) -> Optional[str]` (org_id) used identically in `require_org` (Task 8) and the store (Task 2). `issue_api_key(org_id) -> str` used in create_org + rotate (Task 6). `query_records_for_org(*, org_id, candidate_id, at=None)` signature identical in Task 4 (def) and Task 9 (call). `get_record(record_id) -> Optional[InterviewRecord]` returns a contract carrying `org_id`, consumed by the ownership check in Task 8. `check_consent(...)` return shape (`allowed`/`reason`/`grant_id`) unchanged — only selection determinism added (Task 1). `Services.ledger` added in Task 5 before any endpoint (Tasks 6-9) reads it. `org_router` defined in Task 8 and only extended (not redefined) in Task 9. Consent audit `record.query` action + `details.allowed`/`record_count` keys written in Task 4 and asserted in Tasks 4 & 9. Consistent throughout.
