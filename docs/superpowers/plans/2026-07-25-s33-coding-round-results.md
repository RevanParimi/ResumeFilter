# S3.3 — Coding-round results (schema + ingest) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `coding_round_results` record type to the evaluation ledger — a peer of `interview_records` — so member orgs can submit structured automated-coding-assessment results (platform, score, percentile, problem tags) about consenting candidates and query them cross-org under read consent, all consent-gated and audited. Schema + ingest only: **no scoring, no normalization, no reputation** (S3.4).

**Architecture:** Reuse every S3.1/S3.2 mechanism unchanged. A new `CodingRoundResultRow` (on the shared candidates DB) carries CASCADE FKs to `candidates`, `organizations`, and `consent_grants` exactly like `interview_records`. New `LedgerStore` methods mirror `submit_interview_record` / `query_records_for_org` / `records_for_candidate`: submit is `ledger_write`-gated, query enforces `ledger_read` at query time and audits every attempt (allowed or denied) in the same transaction. Two `org_router` endpoints (`X-Org-Key`) expose them. Consent purposes are reused — no new taxonomy.

**Tech Stack:** FastAPI + Pydantic v2, SQLAlchemy + Alembic on SQLite (Postgres-shaped: `String(36)` UUIDs, FKs, JSON columns), pytest (fully offline, NullLLM / in-memory stores), `httpx` + uvicorn for the smoke.

## Global Constraints

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` must be green before merge.
- **S3.3 is LLM-free** — no model calls anywhere; no deterministic-fallback obligation arises.
- **Schema + ingest ONLY** — store and expose the data; never interpret `score`/`max_score`/`percentile`, never rank or aggregate. That is S3.4.
- Advisory only: the ledger records data and enforces consent; it never auto-rejects or scores a candidate.
- DPDP: first-party data only; consent objects + delete paths already exist. `coding_round_results` and its audit rows are candidate-linked with `ondelete="CASCADE"` so erasure sweeps them. Reuse the `ledger_write` (submit) / `ledger_read` (query) purposes — do NOT add coding-specific consent purposes.
- Config: no new knobs. No secret material is introduced.
- DB: SQLAlchemy + Alembic, Postgres-shaped. The ledger shares `candidates_db_url` (one metadata root, one Alembic env). Schema ships as migration `0005_coding_round_results`, never `create_all`.
- Actor model (audit `actor_type`): coding-round submit and query (reads) → `org`. Actions: `coding_round.submit`, `coding_round.query`.
- Every store mutation writes its `audit_log` row inside the same transaction as the change it records.
- List reads order by `(created_at, id)` — the established deterministic ordering.
- **Ordering caveat:** the metadata-wide drift guard (`tests/test_migrations.py::test_migrated_schema_matches_orm_models`) fails the moment `CodingRoundResultRow` is imported without the matching migration. So Task 2 lands the ORM row **and** migration `0005` together — never the model alone.

---

## File Structure

**New files**
- `alembic/versions/0005_coding_round_results.py` — creates the `coding_round_results` table + 3 indexes.
- `tests/test_ledger_store_coding.py` — store unit tests (consent gate, audit, cascade), mirroring `test_ledger_store_records.py`.
- `scripts/smoke_s33.py` — uvicorn + scripted HTTP end-to-end for the sprint.

**Modified files**
- `app/ledger/schema.py` — `CodingPlatform` StrEnum + `CodingRoundResult` model.
- `app/ledger/models.py` — `CodingRoundResultRow` (+ `Float` import).
- `app/ledger/store.py` — `_coding_round` converter, `submit_coding_round`, `coding_rounds_for_candidate`, `query_coding_rounds_for_org` (+ imports).
- `app/api/routes.py` — `CodingRoundSubmitRequest`, `POST /ledger/coding-rounds`, `GET /ledger/candidates/{id}/coding-rounds` on `org_router` (+ imports).
- `app/main.py` — extend the root endpoint listing with the two new paths.
- `tests/test_ledger_schema.py` — contract tests.
- `tests/test_ledger_models.py` — ORM defaults + cascade test.
- `tests/test_migrations.py` — add `coding_round_results` to the table-presence assertion and to `LEDGER_TABLES`.
- `tests/test_ledger_api.py` — HTTP tests for the two new endpoints.
- `LEDGER.md` — S3.3 section.
- `docs/ROADMAP.md` — status board + "Current state" + session log at end of sprint.

---

## Task 1: Contracts — `CodingPlatform` + `CodingRoundResult`

Pure Pydantic. No DB, no HTTP. Light data hygiene only (bounds/defaults) — **not** scoring.

**Files:**
- Modify: `app/ledger/schema.py`
- Test: `tests/test_ledger_schema.py`

**Interfaces:**
- Consumes: `StrEnum`, `BaseModel`, `Field`, `Optional`, `datetime` (already imported in `schema.py`).
- Produces:
  - `CodingPlatform(StrEnum)` with values `hackerrank`, `codility`, `leetcode`, `codesignal`, `hackerearth`, `internal`, `other`.
  - `CodingRoundResult(BaseModel)` with fields `id: str`, `org_id: str`, `candidate_id: str`, `consent_id: str`, `platform: CodingPlatform`, `platform_name: Optional[str]=None`, `assessment_name: Optional[str]=None`, `score: float (ge=0)`, `max_score: Optional[float]=None (ge=0)`, `percentile: Optional[float]=None (ge=0, le=100)`, `problem_tags: list[str]=[]`, `taken_at: datetime`, `raw: dict={}`, `created_at: datetime`.

- [ ] **Step 1: Write the failing contract tests**

Add to `tests/test_ledger_schema.py` (extend the existing import from `app.ledger.schema` to include `CodingPlatform, CodingRoundResult`):

```python
def test_coding_platform_taxonomy():
    from app.ledger.schema import CodingPlatform
    assert [p.value for p in CodingPlatform] == [
        "hackerrank", "codility", "leetcode", "codesignal",
        "hackerearth", "internal", "other",
    ]


def test_coding_round_result_defaults_and_coercion():
    from app.ledger.schema import CodingPlatform, CodingRoundResult
    r = CodingRoundResult(
        id="cr1", org_id="o1", candidate_id="c1", consent_id="g1",
        platform="hackerrank", score=740.0, taken_at=NOW, created_at=NOW,
    )
    assert r.platform is CodingPlatform.HACKERRANK  # str coerces to enum
    assert r.platform_name is None and r.assessment_name is None
    assert r.max_score is None and r.percentile is None
    assert r.problem_tags == [] and r.raw == {}


def test_coding_round_result_rejects_out_of_range():
    import pytest
    from pydantic import ValidationError
    from app.ledger.schema import CodingRoundResult
    common = dict(id="cr1", org_id="o1", candidate_id="c1", consent_id="g1",
                  platform="other", taken_at=NOW, created_at=NOW)
    with pytest.raises(ValidationError):  # percentile above 100
        CodingRoundResult(score=10.0, percentile=101, **common)
    with pytest.raises(ValidationError):  # negative score
        CodingRoundResult(score=-1.0, **common)
    with pytest.raises(ValidationError):  # negative max_score
        CodingRoundResult(score=10.0, max_score=-5.0, **common)


def test_coding_round_result_round_trips_json():
    from app.ledger.schema import CodingRoundResult
    r = CodingRoundResult(
        id="cr1", org_id="o1", candidate_id="c1", consent_id="g1",
        platform="codility", platform_name=None, assessment_name="Backend Screen",
        score=88.0, max_score=100.0, percentile=92.5,
        problem_tags=["arrays", "dynamic-programming"],
        taken_at=NOW, raw={"attempts": 1}, created_at=NOW,
    )
    assert CodingRoundResult.model_validate_json(r.model_dump_json()) == r
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_schema.py -k coding -v`
Expected: FAIL — `ImportError`/`AttributeError`: `CodingPlatform` / `CodingRoundResult` do not exist yet.

- [ ] **Step 3: Add the contracts**

Append to `app/ledger/schema.py` (after `ConsentPurpose`, before or after the row-mirroring models — keep enums grouped with the other StrEnums):

```python
class CodingPlatform(StrEnum):
    """Where an automated coding assessment ran. A code-constant taxonomy like
    InterviewStage/Outcome; OTHER + platform_name absorbs the long tail without
    losing a controlled vocabulary for S3.4 grouping."""

    HACKERRANK = "hackerrank"
    CODILITY = "codility"
    LEETCODE = "leetcode"
    CODESIGNAL = "codesignal"
    HACKEREARTH = "hackerearth"
    INTERNAL = "internal"
    OTHER = "other"


class CodingRoundResult(BaseModel):
    """One structured coding-assessment result an org submitted about a candidate
    (S3.3). A peer of InterviewRecord. Field bounds are data hygiene, NOT scoring:
    relating score to max_score is normalization and belongs to S3.4."""

    id: str
    org_id: str
    candidate_id: str
    consent_id: str  # the ledger_write grant this was submitted under
    platform: CodingPlatform
    platform_name: Optional[str] = None  # free name when platform == OTHER
    assessment_name: Optional[str] = None
    score: float = Field(ge=0)
    max_score: Optional[float] = Field(default=None, ge=0)
    percentile: Optional[float] = Field(default=None, ge=0, le=100)
    problem_tags: list[str] = Field(default_factory=list)
    taken_at: datetime
    raw: dict = Field(default_factory=dict)
    created_at: datetime
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ledger_schema.py -k coding -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ledger/schema.py tests/test_ledger_schema.py
git commit -m "feat(ledger): S3.3 coding-round contracts (CodingPlatform, CodingRoundResult)"
```

---

## Task 2: ORM row + migration `0005_coding_round_results`

Lands the table on the models **and** the migration together (drift guard requires it). No changes to existing tables.

**Files:**
- Modify: `app/ledger/models.py`
- Create: `alembic/versions/0005_coding_round_results.py`
- Modify: `tests/test_migrations.py`
- Test: `tests/test_ledger_models.py`, `tests/test_migrations.py`

**Interfaces:**
- Consumes: `Base`, `_uuid`, `_utcnow` (`app/ledger/models.py`); `String`, `Text`, `Float`, `JSON`, `DateTime`, `ForeignKey`, `Mapped`, `mapped_column` (SQLAlchemy).
- Produces: `CodingRoundResultRow` (`__tablename__ = "coding_round_results"`) with columns `id, org_id, candidate_id, consent_id, platform, platform_name, assessment_name, score, max_score, percentile, problem_tags, taken_at, raw, created_at` and auto-indexes `ix_coding_round_results_{org_id,candidate_id,consent_id}`. Migration `0005_coding_round_results` (down-revision `0004_org_api_keys`).

- [ ] **Step 1: Write the failing ORM + migration tests**

Add to `tests/test_ledger_models.py` (extend its import from `app.ledger.models` to include `CodingRoundResultRow`):

```python
def test_coding_round_row_defaults_and_cascade(session_factory):
    from sqlalchemy import select
    from app.candidates.models import CandidateRow
    from app.ledger.models import (
        CodingRoundResultRow, ConsentGrantRow, OrganizationRow, _utcnow,
    )
    with session_factory() as s:
        cand = CandidateRow()
        org = OrganizationRow(name="Coding Corp")
        s.add_all([cand, org])
        s.flush()
        g = ConsentGrantRow(candidate_id=cand.id, org_id=org.id,
                            purpose="ledger_write", expires_at=_utcnow())
        s.add(g)
        s.flush()
        row = CodingRoundResultRow(
            org_id=org.id, candidate_id=cand.id, consent_id=g.id,
            platform="hackerrank", score=740.0, taken_at=_utcnow(),
        )
        s.add(row)
        s.commit()
        assert len(row.id) == 36
        assert row.problem_tags == [] and row.raw == {}
        assert row.max_score is None and row.percentile is None
        assert row.created_at is not None

        s.delete(cand)   # DPDP erasure cascades the coding-round row
        s.commit()
        assert s.execute(select(CodingRoundResultRow)).scalars().all() == []
        # the org survives erasure
        assert s.execute(select(OrganizationRow)).scalars().all() != []
```

Modify `tests/test_migrations.py`:
- In `test_upgrade_head_creates_candidate_tables`, add `"coding_round_results"` to the asserted ledger-table set.
- Add `"coding_round_results"` to the module-level `LEDGER_TABLES` tuple (so the index / FK-ondelete / nullability guards cover it).

```python
# test_upgrade_head_creates_candidate_tables — second assertion becomes:
    assert {
        "organizations",
        "consent_grants",
        "interview_records",
        "evaluation_events",
        "audit_log",
        "coding_round_results",
    } <= names

# module-level tuple becomes:
LEDGER_TABLES = (
    "organizations", "consent_grants", "interview_records",
    "evaluation_events", "audit_log", "coding_round_results",
)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_models.py::test_coding_round_row_defaults_and_cascade tests/test_migrations.py -v`
Expected: FAIL — `ImportError` for `CodingRoundResultRow`; migration tests fail on the missing table / drift.

- [ ] **Step 3: Add the ORM row**

In `app/ledger/models.py`, add `Float` to the SQLAlchemy import line:

```python
from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint,
)
```

Then append the row class (after `EvaluationEventRow`, before `AuditLogRow` is fine):

```python
class CodingRoundResultRow(Base):
    """One structured coding-assessment result one org submitted about one
    candidate (S3.3). A peer of ``interview_records`` — same consent / audit /
    DPDP machinery, but typed platform-assessment fields (platform, score,
    percentile, tags) instead of a coarse pipeline-stage outcome. Append-only;
    candidate-linked so DPDP erasure cascades it."""

    __tablename__ = "coding_round_results"

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
    platform: Mapped[str] = mapped_column(String(32))  # CodingPlatform value
    platform_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assessment_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentile: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    problem_tags: Mapped[list] = mapped_column(JSON, default=list)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Add the migration**

Create `alembic/versions/0005_coding_round_results.py`:

```python
"""coding-round results: coding_round_results table (S3.3)

Revision ID: 0005_coding_round_results
Revises: 0004_org_api_keys
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_coding_round_results"
down_revision = "0004_org_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coding_round_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "candidate_id", sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "consent_id", sa.String(36),
            sa.ForeignKey("consent_grants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_name", sa.Text(), nullable=True),
        sa.Column("assessment_name", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("percentile", sa.Float(), nullable=True),
        sa.Column("problem_tags", sa.JSON(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_coding_round_results_org_id", "coding_round_results", ["org_id"]
    )
    op.create_index(
        "ix_coding_round_results_candidate_id", "coding_round_results", ["candidate_id"]
    )
    op.create_index(
        "ix_coding_round_results_consent_id", "coding_round_results", ["consent_id"]
    )


def downgrade() -> None:
    op.drop_table("coding_round_results")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ledger_models.py tests/test_migrations.py -v`
Expected: PASS — cascade test green; `test_upgrade_head_creates_candidate_tables`, `test_migrated_schema_matches_orm_models`, `test_migrated_indexes_match_orm`, `test_migrated_fks_and_nullability_match_orm` all green with the new table.

- [ ] **Step 6: Commit**

```bash
git add app/ledger/models.py alembic/versions/0005_coding_round_results.py tests/test_ledger_models.py tests/test_migrations.py
git commit -m "feat(ledger): S3.3 coding_round_results table + migration 0005"
```

---

## Task 3: Store — submit / query / raw read (consent-gated, audited)

Mirrors the interview-record store methods exactly, including the same-transaction audit rule and `as_utc` coercion.

**Files:**
- Modify: `app/ledger/store.py`
- Test: `tests/test_ledger_store_coding.py` (new)

**Interfaces:**
- Consumes: `CodingRoundResultRow` (models); `CodingPlatform`, `CodingRoundResult` (schema); existing `consent_logic`, `ConsentPurpose`, `_utcnow`, `_grants_for`, `_audit`, `ConsentError`, `CandidateRow`, `OrganizationRow`.
- Produces:
  - `LedgerStore.submit_coding_round(*, org_id, candidate_id, platform, score, taken_at, assessment_name=None, platform_name=None, max_score=None, percentile=None, problem_tags=None, raw=None, now=None) -> CodingRoundResult` — `ledger_write`-gated (`ConsentError`), stamps `consent_id`, audits `coding_round.submit`.
  - `LedgerStore.coding_rounds_for_candidate(candidate_id) -> list[CodingRoundResult]` — ungated raw read.
  - `LedgerStore.query_coding_rounds_for_org(*, org_id, candidate_id, at=None) -> list[CodingRoundResult]` — `ledger_read`-gated, audits `coding_round.query` on every attempt.

- [ ] **Step 1: Write the failing store tests**

Create `tests/test_ledger_store_coding.py`:

```python
"""S3.3 LedgerStore coding rounds: consent-gated writes/reads + DPDP cascade."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


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
    return store.create_organization("Coding Corp")


def test_submit_without_consent_is_refused(store, org, candidate_id):
    with pytest.raises(ConsentError):
        store.submit_coding_round(
            org_id=org.id, candidate_id=candidate_id, platform="hackerrank",
            score=740.0, taken_at=NOW, now=NOW,
        )
    assert store.coding_rounds_for_candidate(candidate_id) == []


def test_submit_with_consent_links_grant_and_persists_fields(store, org, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    cr = store.submit_coding_round(
        org_id=org.id, candidate_id=candidate_id, platform="codility",
        score=88.0, max_score=100.0, percentile=92.5, taken_at=NOW,
        assessment_name="Backend Screen", problem_tags=["arrays", "graphs"],
        raw={"attempts": 1}, now=NOW,
    )
    assert cr.consent_id == g.id
    assert cr.platform == "codility" and cr.score == 88.0 and cr.max_score == 100.0
    assert cr.percentile == 92.5 and cr.problem_tags == ["arrays", "graphs"]
    assert cr.raw == {"attempts": 1}
    assert [r.id for r in store.coding_rounds_for_candidate(candidate_id)] == [cr.id]


def test_submit_unknown_org_or_candidate(store, org, candidate_id):
    with pytest.raises(LookupError):
        store.submit_coding_round(org_id="nope", candidate_id=candidate_id,
                                  platform="leetcode", score=1.0, taken_at=NOW)
    with pytest.raises(LookupError):
        store.submit_coding_round(org_id=org.id, candidate_id="nope",
                                  platform="leetcode", score=1.0, taken_at=NOW)


def test_submit_is_audited(store, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                              platform="hackerrank", score=740.0, taken_at=NOW, now=NOW)
    entries = store.audit_for_candidate(candidate_id)
    actions = [a.action for a in entries]
    assert actions == ["consent.grant", "coding_round.submit"]
    submit = entries[1]
    assert submit.actor_type == "org" and submit.actor_id == org.id
    assert submit.entity_type == "coding_round_result"
    assert submit.details["platform"] == "hackerrank"


def test_query_allowed_returns_results_and_audits_read(store, candidate_id):
    org = store.create_organization("ReaderCo")
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write", org_id=org.id)
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_read", org_id=org.id)
    cr = store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                                   platform="hackerrank", score=740.0, taken_at=NOW)
    got = store.query_coding_rounds_for_org(org_id=org.id, candidate_id=candidate_id)
    assert [r.id for r in got] == [cr.id]
    reads = [a for a in store.audit_for_candidate(candidate_id)
             if a.action == "coding_round.query"]
    assert len(reads) == 1
    assert reads[0].details["allowed"] is True and reads[0].details["result_count"] == 1


def test_query_without_read_consent_denied_and_audited(store, candidate_id):
    org = store.create_organization("NosyCo")
    with pytest.raises(ConsentError):
        store.query_coding_rounds_for_org(org_id=org.id, candidate_id=candidate_id)
    reads = [a for a in store.audit_for_candidate(candidate_id)
             if a.action == "coding_round.query"]
    assert len(reads) == 1 and reads[0].details["allowed"] is False


def test_query_unknown_candidate_or_org_raises_and_writes_no_audit(store, candidate_id):
    org = store.create_organization("EdgeCo")
    with pytest.raises(LookupError):
        store.query_coding_rounds_for_org(org_id=org.id, candidate_id="no-such")
    with pytest.raises(LookupError):
        store.query_coding_rounds_for_org(org_id="no-such", candidate_id=candidate_id)
    assert [a for a in store.audit_for_candidate(candidate_id)
            if a.action == "coding_round.query"] == []


def test_dpdp_erasure_sweeps_coding_rounds(store, session_factory, org, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        org_id=org.id, now=NOW)
    store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                              platform="hackerrank", score=740.0, taken_at=NOW, now=NOW)
    assert CandidateStore(session_factory).delete_candidate(candidate_id) is True
    assert store.coding_rounds_for_candidate(candidate_id) == []
    assert store.get_organization(org.id) is not None  # org survives
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_store_coding.py -v`
Expected: FAIL — `AttributeError`: `LedgerStore` has no `submit_coding_round` / `coding_rounds_for_candidate` / `query_coding_rounds_for_org`.

- [ ] **Step 3: Add imports + converter**

In `app/ledger/store.py`, extend the model import:

```python
from app.ledger.models import (
    AuditLogRow,
    CodingRoundResultRow,
    ConsentGrantRow,
    EvaluationEventRow,
    InterviewRecordRow,
    OrganizationRow,
)
```

and the schema import (add `CodingPlatform`, `CodingRoundResult`):

```python
from app.ledger.schema import (
    AuditEntry,
    CodingPlatform,
    CodingRoundResult,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
)
```

Add the converter near the other `_row → contract` helpers (e.g. after `_event`):

```python
def _coding_round(row: CodingRoundResultRow) -> CodingRoundResult:
    return CodingRoundResult(
        id=row.id,
        org_id=row.org_id,
        candidate_id=row.candidate_id,
        consent_id=row.consent_id,
        platform=CodingPlatform(row.platform),
        platform_name=row.platform_name,
        assessment_name=row.assessment_name,
        score=row.score,
        max_score=row.max_score,
        percentile=row.percentile,
        problem_tags=list(row.problem_tags or []),
        taken_at=consent_logic.as_utc(row.taken_at),
        raw=dict(row.raw or {}),
        created_at=consent_logic.as_utc(row.created_at),
    )
```

- [ ] **Step 4: Add the three store methods**

Add to `LedgerStore` (place after the interview-record/event methods, before `build_ledger_store`):

```python
    # -- coding-round results (S3.3, consent-gated like interview records) -----

    def submit_coding_round(
        self,
        *,
        org_id: str,
        candidate_id: str,
        platform: CodingPlatform | str,
        score: float,
        taken_at: datetime,
        assessment_name: Optional[str] = None,
        platform_name: Optional[str] = None,
        max_score: Optional[float] = None,
        percentile: Optional[float] = None,
        problem_tags: Optional[list[str]] = None,
        raw: Optional[dict] = None,
        now: Optional[datetime] = None,
    ) -> CodingRoundResult:
        """Write-time DPDP gate: refuses without an active ledger_write grant."""
        platform = CodingPlatform(platform)
        moment = consent_logic.as_utc(now) if now else _utcnow()
        taken_at = consent_logic.as_utc(taken_at)
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
            row = CodingRoundResultRow(
                org_id=org_id,
                candidate_id=candidate_id,
                consent_id=decision.grant_id,
                platform=platform.value,
                platform_name=platform_name,
                assessment_name=assessment_name,
                score=score,
                max_score=max_score,
                percentile=percentile,
                problem_tags=list(problem_tags or []),
                taken_at=taken_at,
                raw=dict(raw or {}),
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="coding_round.submit",
                entity_type="coding_round_result",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "platform": platform.value,
                    "score": score,
                    "consent_id": decision.grant_id,
                },
            )
            session.commit()
            return _coding_round(row)

    def coding_rounds_for_candidate(self, candidate_id: str) -> list[CodingRoundResult]:
        """Raw store read — query-time ledger_read enforcement is the API's job."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(CodingRoundResultRow)
                    .where(CodingRoundResultRow.candidate_id == candidate_id)
                    .order_by(CodingRoundResultRow.created_at, CodingRoundResultRow.id)
                )
                .scalars()
                .all()
            )
            return [_coding_round(r) for r in rows]

    def query_coding_rounds_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
    ) -> list[CodingRoundResult]:
        """Query-time DPDP gate mirroring records: an org may read a candidate's
        coding rounds only under an active ledger_read grant. Every attempt —
        allowed or denied — is audited in the same transaction."""
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
                    action="coding_round.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "ledger_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)
            rows = (
                session.execute(
                    select(CodingRoundResultRow)
                    .where(CodingRoundResultRow.candidate_id == candidate_id)
                    .order_by(CodingRoundResultRow.created_at, CodingRoundResultRow.id)
                )
                .scalars()
                .all()
            )
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="coding_round.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "result_count": len(rows),
                },
            )
            session.commit()
            return [_coding_round(r) for r in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ledger_store_coding.py -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_coding.py
git commit -m "feat(ledger): S3.3 store — submit/query/read coding rounds, consent-gated + audited"
```

---

## Task 4: HTTP endpoints — submit + query on `org_router`

Two org-plane endpoints (`X-Org-Key`), mirroring the records endpoints. No admin-plane changes.

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py` (root endpoint listing)
- Test: `tests/test_ledger_api.py`

**Interfaces:**
- Consumes: `require_org`, `org_router`, `_services`, `ConsentError`, `HTTPException`, `Depends`, `Request`, `BaseModel`, `Field` (all present in `routes.py`); `CodingPlatform`, `CodingRoundResult` (schema); `LedgerStore.submit_coding_round` / `query_coding_rounds_for_org` (Task 3).
- Produces: `POST /ledger/coding-rounds` (403 no write-consent / 404 unknown candidate / 401 no key) and `GET /ledger/candidates/{candidate_id}/coding-rounds` (403 no read-consent / 404 unknown candidate / 401 no key), both returning `CodingRoundResult`(s).

- [ ] **Step 1: Write the failing API tests**

Add to `tests/test_ledger_api.py` (its `_setup_org_candidate` / `_org_with_key` / `api` fixtures already exist and grant write [+ optional read] consent):

```python
def _coding_payload(cid):
    return {
        "candidate_id": cid, "platform": "hackerrank", "score": 740.0,
        "max_score": 850.0, "percentile": 88.0,
        "problem_tags": ["arrays", "dynamic-programming"],
        "taken_at": "2026-07-24T10:00:00+00:00", "assessment_name": "SDE Screen",
        "raw": {"attempts": 1},
    }


def test_submit_coding_round_requires_valid_org_key(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    payload = _coding_payload(cid)
    assert client.post("/ledger/coding-rounds", json=payload).status_code == 401
    assert client.post("/ledger/coding-rounds", json=payload,
                       headers={"X-Org-Key": "wrong"}).status_code == 401
    ok = client.post("/ledger/coding-rounds", json=payload, headers={"X-Org-Key": key})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["candidate_id"] == cid and body["consent_id"]
    assert body["platform"] == "hackerrank" and body["percentile"] == 88.0
    assert body["problem_tags"] == ["arrays", "dynamic-programming"]


def test_submit_coding_round_without_write_consent_is_403(api):
    client, services = api
    cid = asyncio.run(_ingest_candidate(services))
    _, key = _org_with_key(client)  # org exists, no consent granted
    resp = client.post("/ledger/coding-rounds", json=_coding_payload(cid),
                       headers={"X-Org-Key": key})
    assert resp.status_code == 403


def test_submit_coding_round_unknown_candidate_is_404(api):
    client = api[0]
    _, key = _org_with_key(client)
    payload = _coding_payload("no-such")
    assert client.post("/ledger/coding-rounds", json=payload,
                       headers={"X-Org-Key": key}).status_code == 404


def test_submit_coding_round_rejects_bad_percentile(api):
    client, cid, org_id, key = _setup_org_candidate(api)
    payload = _coding_payload(cid)
    payload["percentile"] = 150  # out of range → 422 validation error
    assert client.post("/ledger/coding-rounds", json=payload,
                       headers={"X-Org-Key": key}).status_code == 422


def test_query_coding_rounds_requires_read_consent_and_audits(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    services = api[1]
    client.post("/ledger/coding-rounds", json=_coding_payload(cid),
                headers={"X-Org-Key": key})
    resp = client.get(f"/ledger/candidates/{cid}/coding-rounds",
                      headers={"X-Org-Key": key})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1 and resp.json()[0]["candidate_id"] == cid
    reads = [a for a in services.ledger.audit_for_candidate(cid)
             if a.action == "coding_round.query"]
    assert reads and reads[-1].details["allowed"] is True


def test_query_coding_rounds_denied_without_read_consent(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=False)  # write only
    services = api[1]
    resp = client.get(f"/ledger/candidates/{cid}/coding-rounds",
                      headers={"X-Org-Key": key})
    assert resp.status_code == 403
    reads = [a for a in services.ledger.audit_for_candidate(cid)
             if a.action == "coding_round.query"]
    assert reads and reads[-1].details["allowed"] is False


def test_query_coding_rounds_bad_key_and_unknown_candidate(api):
    client, cid, org_id, key = _setup_org_candidate(api, read=True)
    assert client.get(f"/ledger/candidates/{cid}/coding-rounds").status_code == 401
    assert client.get("/ledger/candidates/nope/coding-rounds",
                      headers={"X-Org-Key": key}).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger_api.py -k coding -v`
Expected: FAIL — the routes 404/405 (endpoints not registered yet).

- [ ] **Step 3: Add the request model + endpoints**

In `app/api/routes.py`, add `CodingPlatform, CodingRoundResult` to the `app.ledger.schema` import. Then add the request model near `RecordSubmitRequest` and the endpoints after the existing `query_records` handler on `org_router`:

```python
class CodingRoundSubmitRequest(BaseModel):
    candidate_id: str
    platform: CodingPlatform
    score: float = Field(ge=0)
    taken_at: datetime
    assessment_name: Optional[str] = None
    platform_name: Optional[str] = None
    max_score: Optional[float] = Field(default=None, ge=0)
    percentile: Optional[float] = Field(default=None, ge=0, le=100)
    problem_tags: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)


@org_router.post("/ledger/coding-rounds", response_model=CodingRoundResult)
async def submit_coding_round(
    req: CodingRoundSubmitRequest, request: Request, org_id: str = Depends(require_org)
) -> CodingRoundResult:
    ledger = _services(request).ledger
    try:
        return ledger.submit_coding_round(
            org_id=org_id,
            candidate_id=req.candidate_id,
            platform=req.platform,
            score=req.score,
            taken_at=req.taken_at,
            assessment_name=req.assessment_name,
            platform_name=req.platform_name,
            max_score=req.max_score,
            percentile=req.percentile,
            problem_tags=req.problem_tags,
            raw=req.raw,
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@org_router.get(
    "/ledger/candidates/{candidate_id}/coding-rounds",
    response_model=list[CodingRoundResult],
)
async def query_coding_rounds(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> list[CodingRoundResult]:
    """Query-time ledger_read enforcement. The store audits every attempt."""
    ledger = _services(request).ledger
    try:
        return ledger.query_coding_rounds_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 4: Extend the root endpoint listing**

In `app/main.py`, add the two paths to the `endpoints` list (after `"GET /ledger/candidates/{id}/records"`):

```python
                "POST /ledger/coding-rounds",
                "GET /ledger/candidates/{id}/coding-rounds",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ledger_api.py -k coding -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_ledger_api.py
git commit -m "feat(api): S3.3 coding-round submit + query endpoints (org plane)"
```

---

## Task 5: Smoke — `scripts/smoke_s33.py`

End-to-end over uvicorn HTTP, key-less-capable (heuristic extraction). Mirrors `smoke_s32.py`.

**Files:**
- Create: `scripts/smoke_s33.py`

**Interfaces:**
- Consumes: the running HTTP surface (admin plane for org/consent/candidate, org plane for coding rounds); `tests/fixtures/full_profile_resume.txt`.
- Produces: exit 0 + `SMOKE OK` when all checks pass.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s33.py`:

```python
"""S3.3 smoke: coding-round ingest over the ledger HTTP surface.

Migrates a scratch DB with Alembic, boots uvicorn with an admin key set, then:
create org (one-time key) → ingest a candidate → submit coding round WITHOUT
write consent (403) → grant write consent → submit (200) → query WITHOUT read
consent (403) → grant read consent → query (200, 1 result) → DPDP erase
candidate → query 404. LLM-free; heuristic extraction with no API key. Run from
the repo root:
    python scripts/smoke_s33.py
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
PORT = 8033
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
TAKEN_AT = "2026-07-24T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s33.db").as_posix()
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

            created = c.post("/ledger/orgs", json={"name": "Coding Corp"},
                             headers=admin_h).json()
            org_id, org_key = created["org"]["id"], created["api_key"]
            org_h = {"X-Org-Key": org_key}
            print(f"org: {org_id[:8]} key issued")

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            print(f"candidate [{cand['extraction_method']}]: {cid[:8]}")

            payload = {
                "candidate_id": cid, "platform": "hackerrank", "score": 740.0,
                "max_score": 850.0, "percentile": 88.0,
                "problem_tags": ["arrays", "dynamic-programming"],
                "taken_at": TAKEN_AT, "assessment_name": "SDE Screen",
            }
            refused = c.post("/ledger/coding-rounds", json=payload, headers=org_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_write", "org_id": org_id}, headers=admin_h)
            submitted = c.post("/ledger/coding-rounds", json=payload, headers=org_h)

            query_denied = c.get(f"/ledger/candidates/{cid}/coding-rounds", headers=org_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_read", "org_id": org_id}, headers=admin_h)
            query_ok = c.get(f"/ledger/candidates/{cid}/coding-rounds", headers=org_h)

            c.delete(f"/candidates/{cid}", headers=admin_h)
            query_after_erase = c.get(f"/ledger/candidates/{cid}/coding-rounds", headers=org_h)

        checks = {
            "org created with one-time key": bool(org_key),
            "submit without write consent 403": refused.status_code == 403,
            "submit with consent 200": submitted.status_code == 200,
            "submitted result has percentile": submitted.status_code == 200
            and submitted.json().get("percentile") == 88.0,
            "query without read consent 403": query_denied.status_code == 403,
            "query with read consent returns 1 result": query_ok.status_code == 200
            and len(query_ok.json()) == 1,
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

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_s33.py`
Expected: every line `OK`, final `SMOKE OK`, exit 0. (If `full_profile_resume.txt` is missing, substitute any fixture resume under `tests/fixtures/`.)

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_s33.py
git commit -m "test(ledger): S3.3 HTTP smoke — coding-round ingest + query + erasure"
```

---

## Task 6: Docs + sprint close

**Files:**
- Modify: `LEDGER.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Add the S3.3 section to `LEDGER.md`**

Append after the S3.2 section (and update the S3.2 "Not in S3.2" line's mention of coding-round ingest is now delivered — leave S3.2's text historical, add the new section):

```markdown
## S3.3 — coding-round results (this sprint)

A new **coding-round result** record type: structured automated-assessment
results (HackerRank / Codility / LeetCode / CodeSignal / HackerEarth / internal),
a standalone peer of `interview_records`. **Schema + ingest only — no scoring,
no cross-platform normalization, no reputation** (S3.4).

**Table** `coding_round_results` (migration `0005_coding_round_results`, same
DB/metadata root; CASCADE FKs to `candidates`, `organizations`, `consent_grants`):
`platform` (`CodingPlatform` enum; `other` + `platform_name` for the long tail),
`assessment_name?`, `score`, `max_score?`, `percentile?` (0–100), `problem_tags[]`
(JSON), `taken_at`, `raw{}` (JSON — platform extras, forward-compat), plus
`org_id`/`candidate_id`/`consent_id`. Field bounds are data hygiene, not scoring:
`score`/`max_score` are related only in S3.4.

**Consent:** reuses `ledger_write` (submit) / `ledger_read` (query) — one consent
object per candidate, no coding-specific purposes.

**Store** (`app/ledger/store.py`), mirroring interview records:
- `submit_coding_round` — write-consent gated (`ConsentError` → 403), stamps the
  authorizing `consent_id`, audits `coding_round.submit` (actor `org`) in-txn.
- `query_coding_rounds_for_org` — query-time `ledger_read` enforcement; audits
  **every** attempt allowed/denied as `coding_round.query` in the same txn. A
  reader with an active grant sees the candidate's coding rounds across ALL member
  orgs (reputation-network semantics).
- `coding_rounds_for_candidate` — raw ungated read for PI-4/internal use.

**Endpoints** (org plane, `X-Org-Key`):
- `POST /ledger/coding-rounds` — 403 without write consent, 404 unknown candidate.
- `GET /ledger/candidates/{id}/coding-rounds` — 403 without read consent (audited).

**DPDP:** `coding_round_results` + its audit rows CASCADE from `candidates.id`, so
candidate erasure sweeps them; `delete_organization` cascades them via the org's
grants and the `org_id` FK, identical to interview records.

**Not in S3.3:** any interpretation of `score`/`percentile`; reputation
aggregation, recency decay, per-org reliability weight (all S3.4); events on a
coding-round result; correlating a coding round to a specific interview record.
```

- [ ] **Step 2: Update `docs/ROADMAP.md`**

- Status board: flip `[ ] S3.3` to `[x] S3.3`.
- "▶ Current state": set Current sprint → S3.4 (Cross-company reputation), Next action → write the S3.4 plan; move the S3.3 summary into "Last session".
- Add a session-log entry dated 2026-07-25 summarizing S3.3 (standalone `coding_round_results` table, migration 0005, reused consent, two org-plane endpoints, N new tests, smoke `scripts/smoke_s33.py` result, merge status).

- [ ] **Step 3: Full offline suite green**

Run: `pytest -q`
Expected: all green (422 baseline + ~30 new). Investigate any failure before proceeding — do not merge red.

- [ ] **Step 4: Commit**

```bash
git add LEDGER.md docs/ROADMAP.md
git commit -m "docs(ledger): S3.3 coding-round results — LEDGER.md + roadmap"
```

- [ ] **Step 5: Whole-branch review + merge**

Request a whole-branch code review (spec conformance + correctness). Address any Critical/Important findings, triage Minors. When green and approved, fast-forward merge `s33-coding-round-results` → `main`, confirm `pytest -q` green on `main`, delete the branch. Update ROADMAP "Last session" with the final merge SHA.

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-07-25-s33-coding-round-results-design.md`):
- Standalone `coding_round_results` table (peer of records) → Task 2. ✓
- Contracts `CodingPlatform` + `CodingRoundResult` with the exact field set + bounds → Task 1. ✓
- Reuse `ledger_write`/`ledger_read` (no new purposes) → Tasks 3/4 use `ConsentPurpose.LEDGER_WRITE/READ`. ✓
- Store: submit (write-gated, `consent_id` stamped, audited), query (read-gated, audits every attempt), raw read → Task 3. ✓
- API: `POST /ledger/coding-rounds` + `GET /ledger/candidates/{id}/coding-rounds` on org plane, 403/404/401 → Task 4. ✓
- Migration `0005_coding_round_results` + drift/index/FK guards cover the new table → Task 2. ✓
- DPDP: candidate erasure + org deletion cascade → Task 2 cascade test + reused CASCADE FKs; Task 3 erasure test. ✓
- No config knobs, no LLM, no scoring → honored throughout (Global Constraints). ✓
- Smoke `scripts/smoke_s33.py` per the spec's flow → Task 5. ✓
- LEDGER.md S3.3 section + ROADMAP → Task 6. ✓

No spec requirement is left without a task.

**2. Placeholder scan:** No `TBD`/`TODO`/"add validation"/"similar to Task N" — every test and implementation block contains real code. ✓

**3. Type consistency:** `CodingPlatform`, `CodingRoundResult`, `CodingRoundResultRow`, `submit_coding_round`, `coding_rounds_for_candidate`, `query_coding_rounds_for_org`, audit actions `coding_round.submit`/`coding_round.query`, detail key `result_count`, entity_type `coding_round_result` are used identically across Tasks 1–6 and the smoke. The request model `CodingRoundSubmitRequest` field names match the store kwargs. Index names `ix_coding_round_results_*` match between the ORM auto-index (`index=True`) and the migration. ✓
