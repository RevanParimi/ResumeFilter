# S3.4 — Cross-company reputation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggregate a candidate's consented `interview_records` + `coding_round_results` into a single **advisory** cross-company reputation band + score (Bayesian shrinkage toward a neutral prior, recency half-life decay, per-org reliability weight), exposed as a consent-gated, audited org-plane read.

**Architecture:** Reputation is a *derived read* over the two existing ledger record types — **no new record type, no graph node, no `Report` field, no LLM**. A pure module `app/ledger/reputation.py` (mirroring `app/fabrication/risk.py`) computes a `ReputationAssessment` from lists of the existing contracts. A new `LedgerStore.reputation_for_org` enforces `ledger_read` at query time and audits every attempt (allowed or denied) in the same transaction — identical machinery to `query_records_for_org`. Per-org reliability is a nullable `organizations.reliability_weight` column (default neutral 1.0) set via a minimal admin endpoint. One org-plane endpoint returns the assessment.

**Tech Stack:** FastAPI + Pydantic v2, SQLAlchemy + Alembic on SQLite (Postgres-shaped: `String(36)` UUIDs, FKs, JSON), pytest (fully offline, NullLLM / in-memory stores), `httpx` + uvicorn for the smoke.

## Global Constraints

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` must be green before merge.
- **S3.4 is LLM-free** — no model calls anywhere; no deterministic-fallback obligation arises (the whole subsystem is already deterministic).
- **Advisory only** — the reputation band/score is reviewer context; it never changes a verdict, depth score, or depth band, and is **never a rejection signal**. Nothing auto-rejects. Every user-facing string says so.
- **No new record type** — reputation derives from `interview_records` + `coding_round_results` already in the ledger.
- **Reuse `ledger_read`** for the reputation query — no new consent purpose/taxonomy.
- DPDP: first-party data only; consent object + delete path already exist. No new candidate-linked table ⇒ no new erasure path; an erased candidate ⇒ `LookupError` (404). `reliability_weight` is org-level, not candidate data. Every reputation query (allowed or denied) is audited.
- Config: tunables in `config.yaml`, mirrored in `app/core/config.py` as `DEE_*`-overridable `rep_*` knobs. The outcome→value map is a **code constant**, not config.
- DB: SQLAlchemy + Alembic, Postgres-shaped. The ledger shares `candidates_db_url` (one metadata root, one Alembic env). The column ships as migration `0006_org_reliability_weight`, never `create_all`.
- Actor model (audit `actor_type`): reputation query (a read) → `org`, action `reputation.query`; reliability set → `system`, action `org.set_reliability`.
- Every store mutation writes its `audit_log` row inside the same transaction as the change it records.
- List reads order by `(created_at, id)` — the established deterministic ordering.
- **Windows gotcha (logged in ROADMAP):** `config.yaml` comments must stay ASCII (the file is read as cp1252). No non-ASCII in new comments.
- **Drift-guard ordering caveat:** `tests/test_migrations.py::test_migrated_schema_matches_orm_models` fails the moment `OrganizationRow` gains `reliability_weight` without the matching migration. So Task 2 lands the ORM column **and** migration `0006` together — never the model change alone.

---

## File Structure

**New files**
- `app/ledger/reputation.py` — pure aggregation: outcome map, normalization, weighting, Bayesian posterior, banding, `assess_reputation`.
- `alembic/versions/0006_org_reliability_weight.py` — adds `organizations.reliability_weight`.
- `tests/test_ledger_reputation.py` — pure-function unit tests (math, gates, determinism).
- `tests/test_ledger_store_reputation.py` — store tests (consent gate, audit, row inclusion, reliability, cascade).
- `scripts/smoke_s34.py` — uvicorn + scripted HTTP end-to-end for the sprint.

**Modified files**
- `app/ledger/schema.py` — `ReputationBand` StrEnum, `ReputationComponent`, `ReputationAssessment`; add `reliability_weight: float = 1.0` to `Organization`.
- `app/ledger/models.py` — `reliability_weight` column on `OrganizationRow`.
- `app/ledger/store.py` — `_org` reads `reliability_weight`; `set_org_reliability`; `reputation_for_org`; `LedgerStore.__init__` gains optional `settings`; `build_ledger_store` passes it.
- `app/core/config.py` — `rep_*` knobs.
- `config.yaml` — `rep_*` knobs (ASCII comments).
- `app/api/routes.py` — `GET /ledger/candidates/{id}/reputation` (org_router); `ReliabilityRequest` + `POST /ledger/orgs/{id}/reliability` (admin router).
- `app/main.py` — extend the root endpoint listing with the two new paths.
- `tests/conftest.py` — `make_services` passes `settings=settings` to the default `LedgerStore` (hermetic knobs through the app).
- `tests/test_ledger_schema.py` — contract tests.
- `tests/test_ledger_models.py` — `reliability_weight` default test.
- `tests/test_migrations.py` — no change needed (drift guard + existing table assertion cover the new column automatically; a one-line targeted assert is added in Task 2).
- `tests/test_ledger_api.py` — HTTP tests for the two new endpoints.
- `LEDGER.md` — S3.4 section.
- `docs/ROADMAP.md` — status board + "Current state" + session log at end of sprint.

---

## Task 1: Contracts — reputation shapes + `Organization.reliability_weight`

Pure Pydantic. No DB, no HTTP.

**Files:**
- Modify: `app/ledger/schema.py`
- Test: `tests/test_ledger_schema.py`

**Interfaces:**
- Consumes: `StrEnum`, `BaseModel`, `Field` (already imported in `schema.py`).
- Produces:
  - `ReputationBand(StrEnum)`: `INSUFFICIENT_DATA="insufficient_data"`, `GUARDED="guarded"`, `MIXED="mixed"`, `FAVORABLE="favorable"`, `STRONG="strong"`.
  - `ReputationComponent(BaseModel)`: `id: str`, `observations: int = 0`, `effective_weight: float = Field(default=0.0, ge=0.0)`, `mean_value: float = Field(default=0.0, ge=0.0, le=1.0)`.
  - `ReputationAssessment(BaseModel)`: `score: float = Field(default=0.5, ge=0.0, le=1.0)`, `confidence: float = Field(default=0.0, ge=0.0, le=1.0)`, `band: ReputationBand = ReputationBand.INSUFFICIENT_DATA`, `components: list[ReputationComponent] = []`, `total_observations: int = 0`, `distinct_orgs: int = 0`, `evidence_mass: float = Field(default=0.0, ge=0.0)`, `excluded_observations: int = 0`, `reasoning: str = ""`, `advisory: bool = True`.
  - `Organization` gains `reliability_weight: float = 1.0`.

- [ ] **Step 1: Write the failing contract tests**

Add to `tests/test_ledger_schema.py` (extend the existing `from app.ledger.schema import ...` to include the new names):

```python
def test_reputation_band_taxonomy():
    from app.ledger.schema import ReputationBand
    assert [b.value for b in ReputationBand] == [
        "insufficient_data", "guarded", "mixed", "favorable", "strong",
    ]


def test_reputation_assessment_defaults_are_neutral_and_advisory():
    from app.ledger.schema import ReputationAssessment, ReputationBand
    a = ReputationAssessment()
    assert a.score == 0.5  # neutral prior
    assert a.band is ReputationBand.INSUFFICIENT_DATA
    assert a.advisory is True
    assert a.components == [] and a.distinct_orgs == 0


def test_reputation_component_bounds():
    import pytest
    from pydantic import ValidationError
    from app.ledger.schema import ReputationComponent
    ReputationComponent(id="interview_records", observations=3,
                        effective_weight=2.5, mean_value=0.8)
    with pytest.raises(ValidationError):
        ReputationComponent(id="x", mean_value=1.5)   # > 1
    with pytest.raises(ValidationError):
        ReputationComponent(id="x", effective_weight=-0.1)


def test_organization_reliability_weight_defaults_to_one():
    from datetime import datetime, timezone
    from app.ledger.schema import Organization
    o = Organization(id="o1", name="Acme", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert o.reliability_weight == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ledger_schema.py -k "reputation or reliability" -v`
Expected: FAIL with `ImportError` / `AttributeError` (names not defined).

- [ ] **Step 3: Add the contracts**

In `app/ledger/schema.py`, add `reliability_weight: float = 1.0` to `Organization` (after `status`), and append at the end of the module:

```python
class ReputationBand(StrEnum):
    """S3.4 — conservative advisory bands over a candidate's cross-company
    track record. INSUFFICIENT_DATA when we can't say. GUARDED is the only
    negative-leaning band and is corroboration-gated (>= rep_corroboration_orgs
    distinct orgs); a single org can never brand a candidate."""

    INSUFFICIENT_DATA = "insufficient_data"
    GUARDED = "guarded"
    MIXED = "mixed"
    FAVORABLE = "favorable"
    STRONG = "strong"


class ReputationComponent(BaseModel):
    """One evidence type's contribution to the reputation aggregate."""

    id: str  # "interview_records" | "coding_rounds"
    observations: int = 0
    effective_weight: float = Field(default=0.0, ge=0.0)   # sum of recency*reliability*type weights
    mean_value: float = Field(default=0.0, ge=0.0, le=1.0)  # weight-weighted mean outcome value


class ReputationAssessment(BaseModel):
    """S3.4 — advisory cross-company reputation. Beta-Binomial posterior mean
    shrunk toward a neutral prior, recency-decayed, per-org-reliability weighted.

    ADVISORY ONLY: never changes verdicts/depth, never a rejection signal.
    Carries no per-org identities (the raw-records endpoint exposes those under
    the same grant; the aggregate deliberately does not re-leak them)."""

    score: float = Field(default=0.5, ge=0.0, le=1.0)       # posterior mean
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # evidence-mass coverage
    band: ReputationBand = ReputationBand.INSUFFICIENT_DATA
    components: list[ReputationComponent] = Field(default_factory=list)
    total_observations: int = 0     # included observations
    distinct_orgs: int = 0          # distinct contributing orgs
    evidence_mass: float = Field(default=0.0, ge=0.0)  # sum of observation weights
    excluded_observations: int = 0  # withdrawn / un-normalizable coding rounds
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ledger_schema.py -k "reputation or reliability" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ledger/schema.py tests/test_ledger_schema.py
git commit -m "feat(s34): reputation contracts + Organization.reliability_weight"
```

---

## Task 2: Model column + migration `0006_org_reliability_weight`

Lands the ORM column **and** the migration together (drift-guard caveat).

**Files:**
- Modify: `app/ledger/models.py`
- Create: `alembic/versions/0006_org_reliability_weight.py`
- Modify: `app/ledger/store.py` (only the `_org` converter — read the new column)
- Test: `tests/test_ledger_models.py`, `tests/test_migrations.py`

**Interfaces:**
- Consumes: `Float` (add to the `sqlalchemy` import in `models.py`), `OrganizationRow`.
- Produces: `OrganizationRow.reliability_weight: Mapped[Optional[float]]` (nullable, python default `1.0`); migration revision id `"0006_org_reliability_weight"`, down-revision `"0005_coding_round_results"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ledger_models.py`:

```python
def test_org_reliability_weight_defaults_to_one(session_factory):
    from app.ledger.models import OrganizationRow
    with session_factory() as s:
        org = OrganizationRow(name="Rel Corp")
        s.add(org)
        s.commit()
        assert org.reliability_weight == 1.0
```

Add to `tests/test_migrations.py` inside `test_upgrade_head_creates_candidate_tables` (after the existing ledger-table assertion), a targeted column check:

```python
    from sqlalchemy import inspect as _inspect
    org_cols = {c["name"] for c in _inspect(engine).get_columns("organizations")}
    assert "reliability_weight" in org_cols
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ledger_models.py::test_org_reliability_weight_defaults_to_one tests/test_migrations.py -v`
Expected: `test_org_reliability_weight_defaults_to_one` FAILs (`AttributeError`); after the model change but before the migration, `test_migrated_schema_matches_orm_models` would FAIL with an `add_column` diff — proving the drift guard bites (do not commit in that state).

- [ ] **Step 3: Add the ORM column**

In `app/ledger/models.py`: add `Float` to the `from sqlalchemy import (...)` line, and in `OrganizationRow` add after `api_key_hash`:

```python
    # Per-org reliability multiplier for S3.4 reputation aggregation. Nullable +
    # python-default 1.0 (neutral) so existing rows read as neutral; the
    # calibrated values are a PI-8 concern.
    reliability_weight: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=1.0
    )
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/0006_org_reliability_weight.py`:

```python
"""org reliability weight: organizations.reliability_weight (S3.4)

Revision ID: 0006_org_reliability_weight
Revises: 0005_coding_round_results
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

revision = "0006_org_reliability_weight"
down_revision = "0005_coding_round_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("reliability_weight", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("reliability_weight")
```

- [ ] **Step 5: Update the `_org` converter to read the column**

In `app/ledger/store.py`, replace the `_org` function body:

```python
def _org(row: OrganizationRow) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        status=row.status,
        reliability_weight=(
            row.reliability_weight if row.reliability_weight is not None else 1.0
        ),
        created_at=consent_logic.as_utc(row.created_at),
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_ledger_models.py tests/test_migrations.py -v`
Expected: PASS (drift guard green — model and migration agree; new column present + defaults to 1.0).

- [ ] **Step 7: Commit**

```bash
git add app/ledger/models.py alembic/versions/0006_org_reliability_weight.py app/ledger/store.py tests/test_ledger_models.py tests/test_migrations.py
git commit -m "feat(s34): organizations.reliability_weight column + migration 0006"
```

---

## Task 3: Config knobs + pure `app/ledger/reputation.py`

The heart of the sprint: deterministic aggregation. Config knobs land here because the module consumes them.

**Files:**
- Modify: `app/core/config.py`, `config.yaml`
- Create: `app/ledger/reputation.py`
- Test: `tests/test_ledger_reputation.py`

**Interfaces:**
- Consumes: `InterviewRecord`, `InterviewOutcome`, `CodingRoundResult`, `ReputationAssessment`, `ReputationBand`, `ReputationComponent` (from `app.ledger.schema`); `Settings`, `get_settings` (from `app.core.config`).
- Produces: `assess_reputation(records: list[InterviewRecord], coding_rounds: list[CodingRoundResult], *, now: datetime, reliability_by_org: dict[str, float] | None = None, settings: Settings | None = None) -> ReputationAssessment`. Helpers `_outcome_value`, `_coding_value`, `_recency_weight`, `_posterior`, `_band_for` may exist but only `assess_reputation` is relied upon by later tasks.

- [ ] **Step 1: Add the config knobs**

In `app/core/config.py`, after the `ledger_api_key_bytes` field (end of the ledger block), add:

```python
    # --- Cross-company reputation (PI-3, S3.4) --------------------------------
    # Advisory Beta-Binomial aggregation of interview_records + coding_round
    # results, shrunk toward a neutral prior, recency-decayed, per-org
    # reliability weighted. Never auto-rejects; GUARDED (the only negative band)
    # and STRONG both require >= rep_corroboration_orgs distinct orgs.
    rep_prior_mean: float = Field(default=0.5, ge=0.0, le=1.0)
    rep_prior_strength: float = Field(default=4.0, gt=0.0)
    rep_recency_halflife_days: float = Field(default=365.0, gt=0.0)
    rep_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    rep_confidence_k: float = Field(default=4.0, gt=0.0)
    rep_confidence_cap: float = Field(default=0.90, ge=0.0, le=1.0)
    rep_corroboration_orgs: int = Field(default=2, ge=1)
    rep_strong_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    rep_favorable_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    rep_guarded_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    rep_interview_weight: float = Field(default=1.0, ge=0.0)
    rep_coding_weight: float = Field(default=1.0, ge=0.0)
```

In `config.yaml`, after the `ledger_api_key_bytes: 32` line, add (ASCII-only comments):

```yaml

# --- Cross-company reputation (PI-3, S3.4): advisory aggregation ---
rep_prior_mean: 0.5              # Beta prior mean (neutral: no assumption)
rep_prior_strength: 4.0          # prior pseudo-count; higher = more shrinkage
rep_recency_halflife_days: 365   # age at which an outcome's weight halves
rep_min_confidence: 0.50         # below this -> insufficient_data, never assert
rep_confidence_k: 4.0            # evidence mass where confidence = 0.5
rep_confidence_cap: 0.90         # confidence ceiling
rep_corroboration_orgs: 2        # distinct orgs required for STRONG / GUARDED
rep_strong_threshold: 0.75       # score >= this (AND corroborated) -> strong
rep_favorable_threshold: 0.60    # score >= this -> favorable
rep_guarded_threshold: 0.35      # score <= this (AND corroborated) -> guarded
rep_interview_weight: 1.0        # interview-record evidence type weight
rep_coding_weight: 1.0           # coding-round evidence type weight
```

- [ ] **Step 2: Write the failing pure-function tests**

Create `tests/test_ledger_reputation.py`:

```python
"""S3.4 pure reputation aggregation: math, gates, determinism. Fully offline."""

from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.ledger.reputation import assess_reputation
from app.ledger.schema import (
    CodingRoundResult, InterviewRecord, ReputationBand,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _settings() -> Settings:
    # Hermetic: code defaults, independent of config.yaml/.env.
    import os
    os.environ.setdefault("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def _rec(outcome, org="orgA", at=NOW, stage="tech"):
    return InterviewRecord(
        id=f"r-{outcome}-{org}-{at.isoformat()}", org_id=org, candidate_id="c1",
        consent_id="g1", stage=stage, outcome=outcome, interviewed_at=at,
        created_at=at,
    )


def _coding(org="orgA", at=NOW, score=88.0, max_score=None, percentile=None):
    return CodingRoundResult(
        id=f"cr-{org}-{at.isoformat()}-{score}", org_id=org, candidate_id="c1",
        consent_id="g1", platform="hackerrank", score=score, max_score=max_score,
        percentile=percentile, taken_at=at, created_at=at,
    )


def test_no_evidence_returns_neutral_prior_insufficient():
    a = assess_reputation([], [], now=NOW, settings=_settings())
    assert a.score == 0.5
    assert a.band is ReputationBand.INSUFFICIENT_DATA
    assert a.total_observations == 0 and a.distinct_orgs == 0
    assert a.advisory is True


def test_withdrawn_is_excluded_from_evidence():
    a = assess_reputation([_rec("withdrawn")], [], now=NOW, settings=_settings())
    assert a.total_observations == 0
    assert a.excluded_observations == 1
    assert a.score == 0.5  # nothing moved the prior


def test_coding_normalization_percentile_then_maxscore_then_excluded():
    s = _settings()
    # percentile wins
    a = assess_reputation([], [_coding(percentile=90.0, score=1.0, max_score=2.0)],
                          now=NOW, settings=s)
    assert a.components[0].mean_value == 0.9
    # max_score path
    b = assess_reputation([], [_coding(score=740.0, max_score=1000.0)], now=NOW, settings=s)
    assert round(b.components[0].mean_value, 4) == 0.74
    # bare score excluded
    c = assess_reputation([], [_coding(score=740.0)], now=NOW, settings=s)
    assert c.total_observations == 0 and c.excluded_observations == 1


def test_recency_halves_weight_at_halflife():
    s = _settings()  # halflife 365 days
    old = NOW - timedelta(days=365)
    a = assess_reputation([_rec("hired", at=old)], [], now=NOW, settings=s)
    # one hired (value 1.0), weight 0.5: score = (2 + 0.5*1)/(4 + 0.5) = 2.5/4.5
    assert round(a.score, 4) == round(2.5 / 4.5, 4)
    assert round(a.evidence_mass, 4) == 0.5


def test_reliability_weight_scales_a_contribution():
    s = _settings()
    a = assess_reputation([_rec("hired")], [], now=NOW,
                          reliability_by_org={"orgA": 2.0}, settings=s)
    # weight 2.0: score = (2 + 2*1)/(4 + 2) = 4/6
    assert round(a.score, 4) == round(4 / 6, 4)


def test_single_source_high_caps_at_favorable_not_strong():
    s = _settings()
    recs = [_rec("hired", org="orgA") for _ in range(6)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.distinct_orgs == 1
    assert a.score >= s.rep_strong_threshold          # score qualifies for STRONG
    assert a.band is ReputationBand.FAVORABLE          # but single-source caps it


def test_two_orgs_high_unlocks_strong():
    s = _settings()
    recs = [_rec("hired", org="orgA") for _ in range(3)] + \
           [_rec("hired", org="orgB") for _ in range(3)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.distinct_orgs == 2
    assert a.band is ReputationBand.STRONG


def test_single_source_low_caps_at_mixed_not_guarded():
    s = _settings()
    recs = [_rec("rejected", org="orgA") for _ in range(6)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.score <= s.rep_guarded_threshold
    assert a.distinct_orgs == 1
    assert a.band is ReputationBand.MIXED              # one org can't brand


def test_two_orgs_low_unlocks_guarded():
    s = _settings()
    recs = [_rec("rejected", org="orgA") for _ in range(3)] + \
           [_rec("rejected", org="orgB") for _ in range(3)]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.distinct_orgs == 2
    assert a.band is ReputationBand.GUARDED
    assert a.advisory is True


def test_thin_evidence_stays_insufficient():
    s = _settings()
    a = assess_reputation([_rec("hired")], [], now=NOW, settings=s)  # mass 1
    assert a.confidence < s.rep_min_confidence
    assert a.band is ReputationBand.INSUFFICIENT_DATA


def test_components_split_by_evidence_type():
    s = _settings()
    a = assess_reputation([_rec("hired", org="orgA"), _rec("advanced", org="orgB")],
                          [_coding(org="orgA", percentile=80.0)], now=NOW, settings=s)
    ids = {c.id for c in a.components}
    assert ids == {"interview_records", "coding_rounds"}
    assert a.total_observations == 3 and a.distinct_orgs == 2


def test_deterministic():
    s = _settings()
    recs = [_rec("hired", org="orgA"), _rec("rejected", org="orgB")]
    a = assess_reputation(recs, [], now=NOW, settings=s)
    b = assess_reputation(recs, [], now=NOW, settings=s)
    assert a.model_dump() == b.model_dump()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_ledger_reputation.py -v`
Expected: FAIL with `ModuleNotFoundError: app.ledger.reputation`.

- [ ] **Step 4: Write `app/ledger/reputation.py`**

```python
"""S3.4 — cross-company reputation: advisory Bayesian aggregation.

Pure functions, no I/O, no LLM (the app/fabrication/risk.py pattern). ADVISORY
ONLY: the band/score is reviewer context computed on demand for a consented
read. It never changes a verdict, depth score, or depth band, and is NEVER a
rejection signal. Conservative by construction: the estimate shrinks toward a
neutral prior (sparse evidence stays neutral), older outcomes decay, and the
only negative-leaning band (GUARDED) plus the top band (STRONG) both require
corroboration across >= rep_corroboration_orgs distinct orgs, so a single org
can never brand a candidate.
"""

from __future__ import annotations

from datetime import datetime

from app.core.config import Settings, get_settings
from app.ledger.schema import (
    CodingRoundResult,
    InterviewOutcome,
    InterviewRecord,
    ReputationAssessment,
    ReputationBand,
    ReputationComponent,
)

# Outcome -> success value in [0,1]. Code constants, NOT config: changing outcome
# polarity is a reviewed schema decision. WITHDRAWN is intentionally absent —
# a candidate-initiated withdrawal is not an evaluation of the candidate, so it
# is excluded from the evidence entirely.
_OUTCOME_VALUE = {
    InterviewOutcome.HIRED: 1.00,
    InterviewOutcome.OFFER: 0.90,
    InterviewOutcome.ADVANCED: 0.65,
    InterviewOutcome.REJECTED: 0.15,
    InterviewOutcome.NO_SHOW: 0.10,
}


def _outcome_value(outcome: InterviewOutcome) -> float | None:
    return _OUTCOME_VALUE.get(outcome)


def _coding_value(cr: CodingRoundResult) -> float | None:
    """Normalize a coding round to [0,1]. percentile (a rank) is the best signal;
    else score/max_score; else un-normalizable (bare score has no cross-platform
    meaning) -> excluded."""
    if cr.percentile is not None:
        return max(0.0, min(1.0, cr.percentile / 100.0))
    if cr.max_score is not None and cr.max_score > 0:
        return max(0.0, min(1.0, cr.score / cr.max_score))
    return None


def _recency_weight(at: datetime, now: datetime, halflife_days: float) -> float:
    age_days = max(0.0, (now - at).total_seconds() / 86400.0)  # future-dated -> 0
    return 0.5 ** (age_days / halflife_days)


class _Obs:
    __slots__ = ("value", "weight", "org")

    def __init__(self, value: float, weight: float, org: str) -> None:
        self.value = value
        self.weight = weight
        self.org = org


def _component(cid: str, obs: list[_Obs]) -> ReputationComponent:
    w = sum(o.weight for o in obs)
    mean = (sum(o.weight * o.value for o in obs) / w) if w > 0 else 0.0
    return ReputationComponent(
        id=cid, observations=len(obs), effective_weight=w,
        mean_value=max(0.0, min(1.0, mean)),
    )


def _band_for(
    score: float, confidence: float, distinct_orgs: int, s: Settings
) -> ReputationBand:
    """Conservative, corroboration-gated. Never assert below the confidence
    floor. STRONG and GUARDED both require >= rep_corroboration_orgs distinct
    orgs: single-source high caps at FAVORABLE, single-source low at MIXED."""
    if confidence < s.rep_min_confidence:
        return ReputationBand.INSUFFICIENT_DATA
    corroborated = distinct_orgs >= s.rep_corroboration_orgs
    if score >= s.rep_strong_threshold and corroborated:
        return ReputationBand.STRONG
    if score >= s.rep_favorable_threshold:
        return ReputationBand.FAVORABLE
    if score <= s.rep_guarded_threshold and corroborated:
        return ReputationBand.GUARDED
    return ReputationBand.MIXED


def assess_reputation(
    records: list[InterviewRecord],
    coding_rounds: list[CodingRoundResult],
    *,
    now: datetime,
    reliability_by_org: dict[str, float] | None = None,
    settings: Settings | None = None,
) -> ReputationAssessment:
    s = settings or get_settings()
    rel = reliability_by_org or {}

    def _rel(org: str) -> float:
        w = rel.get(org, 1.0)
        return w if w >= 0 else 0.0

    interview_obs: list[_Obs] = []
    coding_obs: list[_Obs] = []
    excluded = 0

    for r in records:
        v = _outcome_value(r.outcome)
        if v is None:  # WITHDRAWN or any non-scored outcome
            excluded += 1
            continue
        w = s.rep_interview_weight * _recency_weight(
            r.interviewed_at, now, s.rep_recency_halflife_days
        ) * _rel(r.org_id)
        interview_obs.append(_Obs(v, w, r.org_id))

    for cr in coding_rounds:
        v = _coding_value(cr)
        if v is None:
            excluded += 1
            continue
        w = s.rep_coding_weight * _recency_weight(
            cr.taken_at, now, s.rep_recency_halflife_days
        ) * _rel(cr.org_id)
        coding_obs.append(_Obs(v, w, cr.org_id))

    obs = interview_obs + coding_obs
    if not obs:
        return ReputationAssessment(
            score=s.rep_prior_mean,
            confidence=0.0,
            band=ReputationBand.INSUFFICIENT_DATA,
            excluded_observations=excluded,
            reasoning=(
                "No consented, interpretable cross-company evidence to aggregate; "
                "reputation stays at the neutral prior. Advisory only — never a "
                "rejection signal."
            ),
        )

    mass = sum(o.weight for o in obs)
    alpha0 = s.rep_prior_mean * s.rep_prior_strength
    # Beta-Binomial posterior mean, shrunk toward the prior.
    score = (alpha0 + sum(o.weight * o.value for o in obs)) / (s.rep_prior_strength + mass)
    confidence = min(s.rep_confidence_cap, round(mass / (mass + s.rep_confidence_k), 2))
    distinct_orgs = len({o.org for o in obs})

    components: list[ReputationComponent] = []
    if interview_obs:
        components.append(_component("interview_records", interview_obs))
    if coding_obs:
        components.append(_component("coding_rounds", coding_obs))

    band = _band_for(score, confidence, distinct_orgs, s)
    parts = ", ".join(f"{c.id}={c.observations}" for c in components)
    reasoning = (
        f"Aggregated {len(obs)} consented cross-company observation(s) [{parts}] "
        f"from {distinct_orgs} org(s): reputation {score:.2f} (confidence "
        f"{confidence:.2f}) -> {band.value}. Bayesian shrinkage toward a neutral "
        f"prior, recency-decayed, per-org reliability weighted. Advisory context "
        f"for a human reviewer — never changes verdicts or depth scores, and is "
        f"never a rejection signal."
    )
    return ReputationAssessment(
        score=max(0.0, min(1.0, score)),
        confidence=confidence,
        band=band,
        components=components,
        total_observations=len(obs),
        distinct_orgs=distinct_orgs,
        evidence_mass=mass,
        excluded_observations=excluded,
        reasoning=reasoning,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ledger_reputation.py -v`
Expected: PASS (12 tests). If `test_single_source_high_caps_at_favorable_not_strong` shows the score just under 0.75, note 6×hired mass 6 ⇒ score `(2+6)/(4+6)=0.8` — comfortably above; if it fails, the outcome map or posterior is wrong, fix the implementation (not the test).

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py config.yaml app/ledger/reputation.py tests/test_ledger_reputation.py
git commit -m "feat(s34): pure reputation aggregation + rep_* config knobs"
```

---

## Task 4: Store — `reputation_for_org` + `set_org_reliability`

Consent-gated read + audit, mirroring `query_records_for_org`; the admin reliability setter; wire `settings` into the store.

**Files:**
- Modify: `app/ledger/store.py`, `tests/conftest.py`
- Test: `tests/test_ledger_store_reputation.py`

**Interfaces:**
- Consumes: `assess_reputation` (Task 3); `records_for_candidate`, `coding_rounds_for_candidate`, `_grants_for`, `consent_logic`, `ConsentError`, `_org` (existing in `store.py`); `OrganizationRow`, `CandidateRow` (imported).
- Produces:
  - `LedgerStore.__init__(..., settings: Optional[Settings] = None)` storing `self._settings`.
  - `reputation_for_org(*, org_id: str, candidate_id: str, at: Optional[datetime] = None) -> ReputationAssessment`.
  - `set_org_reliability(org_id: str, weight: float) -> Organization`.

- [ ] **Step 1: Write the failing store tests**

Create `tests/test_ledger_store_reputation.py`:

```python
"""S3.4 LedgerStore reputation: consent-gated read + audit, inclusion, reliability."""

from datetime import datetime, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.schema import ReputationBand
from app.ledger.store import ConsentError, LedgerStore

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _settings() -> Settings:
    import os
    os.environ.setdefault("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365, settings=_settings())


@pytest.fixture()
def candidate_id(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


def _org(store, name):
    return store.create_organization(name)


def _write_grant(store, cid, org):
    return store.grant_consent(candidate_id=cid, purpose="ledger_write",
                               org_id=org.id, now=NOW)


def _read_grant(store, cid, org):
    return store.grant_consent(candidate_id=cid, purpose="ledger_read",
                               org_id=org.id, now=NOW)


def test_reputation_without_read_consent_is_refused_and_audited(store, candidate_id):
    org = _org(store, "Reader Co")
    with pytest.raises(ConsentError):
        store.reputation_for_org(org_id=org.id, candidate_id=candidate_id, at=NOW)
    actions = [a.action for a in store.audit_for_candidate(candidate_id)]
    assert "reputation.query" in actions  # denied attempt is observable
    denied = [a for a in store.audit_for_candidate(candidate_id)
              if a.action == "reputation.query"][-1]
    assert denied.details.get("allowed") is False


def test_reputation_with_read_consent_aggregates_two_orgs(store, candidate_id):
    a = _org(store, "Org A")
    b = _org(store, "Org B")
    reader = _org(store, "Reader")
    for org in (a, b):
        _write_grant(store, candidate_id, org)
        for _ in range(3):
            store.submit_interview_record(
                org_id=org.id, candidate_id=candidate_id, stage="hm",
                outcome="hired", interviewed_at=NOW, now=NOW,
            )
    _read_grant(store, candidate_id, reader)
    rep = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    assert rep.distinct_orgs == 2
    assert rep.band is ReputationBand.STRONG
    assert rep.score > 0.5 and rep.advisory is True
    allowed = [x for x in store.audit_for_candidate(candidate_id)
               if x.action == "reputation.query"][-1]
    assert allowed.details.get("allowed") is True
    assert allowed.details.get("band") == "strong"


def test_reputation_excludes_withdrawn_and_bare_coding(store, candidate_id):
    org = _org(store, "Org A")
    reader = _org(store, "Reader")
    _write_grant(store, candidate_id, org)
    store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                  stage="tech", outcome="withdrawn",
                                  interviewed_at=NOW, now=NOW)
    store.submit_coding_round(org_id=org.id, candidate_id=candidate_id,
                              platform="internal", score=500.0, taken_at=NOW, now=NOW)
    _read_grant(store, candidate_id, reader)
    rep = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    assert rep.total_observations == 0
    assert rep.excluded_observations == 2
    assert rep.band is ReputationBand.INSUFFICIENT_DATA


def test_reputation_honors_reliability_weight(store, candidate_id):
    org = _org(store, "Org A")
    reader = _org(store, "Reader")
    _write_grant(store, candidate_id, org)
    for _ in range(4):
        store.submit_interview_record(org_id=org.id, candidate_id=candidate_id,
                                      stage="hm", outcome="hired",
                                      interviewed_at=NOW, now=NOW)
    _read_grant(store, candidate_id, reader)
    base = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    store.set_org_reliability(org.id, 0.25)  # down-weight org A's evidence
    down = store.reputation_for_org(org_id=reader.id, candidate_id=candidate_id, at=NOW)
    assert down.evidence_mass < base.evidence_mass
    assert down.score < base.score  # less pull away from the 0.5 prior


def test_reputation_unknown_org_or_candidate(store, candidate_id):
    org = _org(store, "Org A")
    with pytest.raises(LookupError):
        store.reputation_for_org(org_id="nope", candidate_id=candidate_id, at=NOW)
    with pytest.raises(LookupError):
        store.reputation_for_org(org_id=org.id, candidate_id="nope", at=NOW)


def test_set_org_reliability_validates_and_audits(store):
    org = _org(store, "Org A")
    updated = store.set_org_reliability(org.id, 1.5)
    assert updated.reliability_weight == 1.5
    assert store.get_organization(org.id).reliability_weight == 1.5
    with pytest.raises(ValueError):
        store.set_org_reliability(org.id, -0.1)
    with pytest.raises(LookupError):
        store.set_org_reliability("nope", 1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ledger_store_reputation.py -v`
Expected: FAIL (`TypeError` on the `settings=` kwarg / `AttributeError: reputation_for_org`).

- [ ] **Step 3: Wire `settings` into the store + add the methods**

In `app/ledger/store.py`:

(a) Import the aggregator and the assessment type at the top with the other schema imports:

```python
from app.ledger.reputation import assess_reputation
```

and add `Organization` is already imported; add `ReputationAssessment` to the `from app.ledger.schema import (...)` block.

(b) Extend `__init__`:

```python
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        default_consent_ttl_days: int = 365,
        api_key_bytes: int = 32,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._default_consent_ttl_days = default_consent_ttl_days
        self._api_key_bytes = api_key_bytes
        self._settings = settings
```

(c) Add `set_org_reliability` in the organizations section (after `authenticate_org`):

```python
    def set_org_reliability(self, org_id: str, weight: float) -> Organization:
        """Admin: set an org's reliability multiplier for S3.4 reputation.
        weight >= 0 (0 mutes the org's evidence); audited as org.set_reliability."""
        if weight < 0:
            raise ValueError(f"reliability weight must be >= 0, got {weight}")
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            if row is None:
                raise LookupError(f"unknown organization: {org_id}")
            row.reliability_weight = float(weight)
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.set_reliability",
                entity_type="organization",
                entity_id=org_id,
                details={"reliability_weight": float(weight)},
            )
            session.commit()
            return _org(row)
```

(d) Add `reputation_for_org` at the end of the coding-round section (after `query_coding_rounds_for_org`):

```python
    def reputation_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
    ) -> ReputationAssessment:
        """Advisory cross-company reputation, ledger_read-gated. Reads the
        candidate's interview records + coding rounds, aggregates them (Bayesian
        shrinkage + recency decay + per-org reliability), and audits every
        attempt — allowed or denied — as reputation.query in the same
        transaction. Never a rejection signal."""
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
                    action="reputation.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "ledger_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)

            record_rows = (
                session.execute(
                    select(InterviewRecordRow)
                    .where(InterviewRecordRow.candidate_id == candidate_id)
                    .order_by(InterviewRecordRow.created_at, InterviewRecordRow.id)
                ).scalars().all()
            )
            coding_rows = (
                session.execute(
                    select(CodingRoundResultRow)
                    .where(CodingRoundResultRow.candidate_id == candidate_id)
                    .order_by(CodingRoundResultRow.created_at, CodingRoundResultRow.id)
                ).scalars().all()
            )
            records = [_record(r) for r in record_rows]
            coding = [_coding_round(r) for r in coding_rows]

            org_ids = {r.org_id for r in records} | {c.org_id for c in coding}
            reliability_by_org: dict[str, float] = {}
            for oid in org_ids:
                o = session.get(OrganizationRow, oid)
                reliability_by_org[oid] = (
                    o.reliability_weight if o and o.reliability_weight is not None else 1.0
                )

            assessment = assess_reputation(
                records, coding, now=moment,
                reliability_by_org=reliability_by_org, settings=self._settings,
            )
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="reputation.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "band": assessment.band.value,
                    "total_observations": assessment.total_observations,
                    "distinct_orgs": assessment.distinct_orgs,
                },
            )
            session.commit()
            return assessment
```

(e) In `build_ledger_store`, pass `settings=settings`:

```python
    return LedgerStore(
        make_session_factory(engine),
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        api_key_bytes=getattr(settings, "ledger_api_key_bytes", 32),
        settings=settings,
    )
```

- [ ] **Step 4: Make service-level tests hermetic on the knobs**

In `tests/conftest.py`, `make_services`, pass settings to the default ledger:

```python
    ledger = ledger or LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ledger_store_reputation.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app/ledger/store.py tests/test_ledger_store_reputation.py tests/conftest.py
git commit -m "feat(s34): reputation_for_org (ledger_read-gated + audited) + set_org_reliability"
```

---

## Task 5: API — reputation read + reliability admin endpoint

**Files:**
- Modify: `app/api/routes.py`, `app/main.py`
- Test: `tests/test_ledger_api.py`

**Interfaces:**
- Consumes: `org_router`, `router`, `require_org`, `_services`, `HTTPException`, `Depends`, `Request`, `BaseModel`, `Field` (all present in `routes.py`); `ReputationAssessment`, `Organization` (add to the schema import in `routes.py`).
- Produces: `GET /ledger/candidates/{candidate_id}/reputation -> ReputationAssessment`; `POST /ledger/orgs/{org_id}/reliability` body `ReliabilityRequest{weight: float}` `-> Organization`.

- [ ] **Step 1: Write the failing API tests**

Add to `tests/test_ledger_api.py` (reuse whatever org-creation / consent helpers the file already defines; the snippet below assumes the existing pattern of an admin `X-API-Key` client and creating an org + candidate — mirror the existing coding-round API tests in this file):

```python
def test_reputation_requires_read_consent_then_returns_band(client, admin_headers):
    # org + key
    created = client.post("/ledger/orgs", json={"name": "Rep Org"},
                          headers=admin_headers).json()
    org_id, org_key = created["org"]["id"], created["api_key"]
    org_h = {"X-Org-Key": org_key}
    # candidate
    cid = client.post("/candidates", json={"resume_text": "Jane Doe\nEngineer"},
                      headers=admin_headers).json()["candidate_id"]
    # write consent + a few hired records
    client.post(f"/ledger/candidates/{cid}/consent",
                json={"purpose": "ledger_write", "org_id": org_id}, headers=admin_headers)
    for _ in range(4):
        client.post("/ledger/records",
                    json={"candidate_id": cid, "stage": "hm", "outcome": "hired",
                          "interviewed_at": "2026-07-26T10:00:00+00:00"}, headers=org_h)
    # reputation without read consent -> 403
    denied = client.get(f"/ledger/candidates/{cid}/reputation", headers=org_h)
    assert denied.status_code == 403
    # grant read -> 200 with a band
    client.post(f"/ledger/candidates/{cid}/consent",
                json={"purpose": "ledger_read", "org_id": org_id}, headers=admin_headers)
    ok = client.get(f"/ledger/candidates/{cid}/reputation", headers=org_h)
    assert ok.status_code == 200
    body = ok.json()
    assert body["advisory"] is True
    assert body["band"] in {"insufficient_data", "mixed", "favorable", "strong", "guarded"}


def test_reputation_missing_key_401_and_unknown_candidate_404(client, admin_headers):
    created = client.post("/ledger/orgs", json={"name": "Rep Org 2"},
                          headers=admin_headers).json()
    org_key = created["api_key"]
    assert client.get("/ledger/candidates/whatever/reputation").status_code == 401
    r = client.get("/ledger/candidates/does-not-exist/reputation",
                   headers={"X-Org-Key": org_key})
    assert r.status_code == 404


def test_set_org_reliability_admin_endpoint(client, admin_headers):
    org_id = client.post("/ledger/orgs", json={"name": "Rel Org"},
                         headers=admin_headers).json()["org"]["id"]
    ok = client.post(f"/ledger/orgs/{org_id}/reliability", json={"weight": 1.5},
                     headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["reliability_weight"] == 1.5
    bad = client.post(f"/ledger/orgs/{org_id}/reliability", json={"weight": -1.0},
                      headers=admin_headers)
    assert bad.status_code == 422
    missing = client.post("/ledger/orgs/nope/reliability", json={"weight": 1.0},
                          headers=admin_headers)
    assert missing.status_code == 404
```

> **Note for the implementer:** match `client` / `admin_headers` to the fixtures already used in `tests/test_ledger_api.py`. If that file constructs the app + admin header inline per test instead of via fixtures, follow that local style — do not invent new fixtures. Read the top of the file first.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ledger_api.py -k "reputation or reliability" -v`
Expected: FAIL (404 route not found / assertion errors).

- [ ] **Step 3: Add the endpoints**

In `app/api/routes.py`, add `ReputationAssessment` and `Organization` to the `from app.ledger.schema import (...)` block, then:

(a) Org-plane reputation read — add after `query_coding_rounds` (near line 540):

```python
@org_router.get(
    "/ledger/candidates/{candidate_id}/reputation",
    response_model=ReputationAssessment,
)
async def candidate_reputation(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> ReputationAssessment:
    """Advisory cross-company reputation. Query-time ledger_read enforcement;
    the store audits every attempt. Never a rejection signal."""
    ledger = _services(request).ledger
    try:
        return ledger.reputation_for_org(org_id=org_id, candidate_id=candidate_id)
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

(b) Admin reliability setter — add near the other admin org routes (after `rotate_org_key`, ~line 375):

```python
class ReliabilityRequest(BaseModel):
    weight: float = Field(ge=0.0)


@router.post("/ledger/orgs/{org_id}/reliability", response_model=Organization)
async def set_org_reliability(
    org_id: str, req: ReliabilityRequest, request: Request
) -> Organization:
    try:
        return _services(request).ledger.set_org_reliability(org_id, req.weight)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

(The `Field(ge=0.0)` makes a negative weight a 422 at the request boundary; the store's own `ValueError` guard covers direct callers.)

- [ ] **Step 4: Extend the root endpoint listing**

In `app/main.py`, in the `"endpoints"` list, after `"GET /ledger/candidates/{id}/coding-rounds"` add:

```python
                "GET /ledger/candidates/{id}/reputation",
                "POST /ledger/orgs/{id}/reliability",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ledger_api.py -k "reputation or reliability" -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Full suite green**

Run: `pytest -q`
Expected: all pass (442 + new tests). Fix any regression before committing.

- [ ] **Step 7: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_ledger_api.py
git commit -m "feat(s34): reputation read endpoint + admin reliability setter"
```

---

## Task 6: Smoke `scripts/smoke_s34.py` + `LEDGER.md`

End-to-end over HTTP, then docs.

**Files:**
- Create: `scripts/smoke_s34.py`
- Modify: `LEDGER.md`

**Interfaces:**
- Consumes: the two new endpoints + existing admin/org/consent endpoints. No new code.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s34.py` (models `scripts/smoke_s33.py`; two orgs so reputation is corroborated):

```python
"""S3.4 smoke: advisory cross-company reputation over the ledger HTTP surface.

Migrates a scratch DB, boots uvicorn with an admin key, then:
create 2 orgs (A, B) + keys -> ingest a candidate -> grant ledger_write to each
-> A and B each submit a couple of favorable interview records + a coding round
-> reputation query WITHOUT read consent (403) -> grant ledger_read -> query
(200: corroborated band, score > 0.5) -> admin lowers B's reliability, re-query
(200, coherent shift) -> DPDP-erase candidate -> reputation 404. LLM-free;
heuristic extraction with no API key. Run from the repo root:
    python scripts/smoke_s34.py
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
PORT = 8034
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
AT = "2026-07-24T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s34.db").as_posix()
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

            orgs = {}
            for name in ("Org A", "Org B"):
                created = c.post("/ledger/orgs", json={"name": name},
                                 headers=admin_h).json()
                orgs[name] = (created["org"]["id"], created["api_key"])
            reader = c.post("/ledger/orgs", json={"name": "Reader Co"},
                            headers=admin_h).json()
            reader_id, reader_key = reader["org"]["id"], reader["api_key"]
            reader_h = {"X-Org-Key": reader_key}

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            print(f"candidate [{cand['extraction_method']}]: {cid[:8]}")

            for name, (oid, okey) in orgs.items():
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

            denied = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)

            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_read", "org_id": reader_id}, headers=admin_h)
            ok = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)
            rep = ok.json() if ok.status_code == 200 else {}

            # lower Org B's reliability and re-query (score should stay valid, shift)
            b_id = orgs["Org B"][0]
            rel = c.post(f"/ledger/orgs/{b_id}/reliability", json={"weight": 0.2},
                         headers=admin_h)
            ok2 = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)
            rep2 = ok2.json() if ok2.status_code == 200 else {}

            c.delete(f"/candidates/{cid}", headers=admin_h)
            after = c.get(f"/ledger/candidates/{cid}/reputation", headers=reader_h)

        checks = {
            "reputation without read consent 403": denied.status_code == 403,
            "reputation with read consent 200": ok.status_code == 200,
            "corroborated across 2 orgs": rep.get("distinct_orgs") == 2,
            "band favorable or strong": rep.get("band") in {"favorable", "strong"},
            "score above neutral prior": rep.get("score", 0) > 0.5,
            "assessment is advisory": rep.get("advisory") is True,
            "reliability set 200": rel.status_code == 200,
            "reliability shift keeps valid score": ok2.status_code == 200
            and 0.0 <= rep2.get("score", -1) <= 1.0,
            "reputation after DPDP erasure 404": after.status_code == 404,
        }
        failed = [name for name, v in checks.items() if not v]
        for name, v in checks.items():
            print(f"  {'OK  ' if v else 'FAIL'} {name}")
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

Run: `python scripts/smoke_s34.py`
Expected: all checks `OK`, `SMOKE OK`, exit 0. (2 orgs × 2 hired + 1 coding = 6 obs, mass ~6 ⇒ confidence 0.6 ≥ 0.5; score ≈ (2 + ~5.6)/(4+6) well above 0.6 ⇒ FAVORABLE/STRONG.) If reputation lands INSUFFICIENT_DATA, evidence mass is short — add another record per org rather than lowering the floor.

- [ ] **Step 3: Write the `LEDGER.md` S3.4 section**

Append a `## S3.4 — cross-company reputation (this sprint)` section to `LEDGER.md` covering: the model (Beta-Binomial shrinkage + recency half-life + per-org reliability), the corroboration-gated bands (GUARDED is the only negative band, needs ≥2 orgs; single-source high caps at FAVORABLE), that it is a derived `ledger_read`-gated read (no new record type, every attempt audited as `reputation.query`), the `reliability_weight` column + admin endpoint (`org.set_reliability` audit), the `rep_*` knobs, and the standing advisory/never-auto-reject guarantee. Follow the prose style of the S3.3 section.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_s34.py LEDGER.md
git commit -m "test(s34): reputation HTTP smoke + LEDGER.md S3.4 section"
```

---

## Sprint close (not a task — done in the session after all tasks + review)

- `pytest -q` green; `python scripts/smoke_s34.py` OK.
- Whole-branch review (`superpowers:requesting-code-review`); triage/fix findings.
- Update `docs/ROADMAP.md`: status board `S3.4 [x]` (**PI-3 COMPLETE**), "Current state" (next action = PI-4 / S4.1 planning, consult vision-gap §6), session log entry.
- Merge to `main`, delete the branch.

---

## Self-Review

**Spec coverage** (each spec section → task):
- Bayesian shrinkage / recency decay / reliability weight → Task 3 (`assess_reputation`) + knobs.
- Corroboration-gated bands (GUARDED/STRONG need ≥2 orgs) → Task 3 `_band_for` + tests.
- Coding normalization (percentile ▸ max_score ▸ excluded) → Task 3 `_coding_value` + test.
- WITHDRAWN excluded → Task 3 `_OUTCOME_VALUE` (absent) + tests.
- Derived consent-gated read + audit every attempt → Task 4 `reputation_for_org`.
- `reliability_weight` column + admin setter → Task 2 (column/migration) + Task 4 (`set_org_reliability`) + Task 5 (endpoint).
- Org-plane reputation endpoint → Task 5.
- No new record type / no graph / no Report / no LLM → honored throughout (no such files touched).
- DPDP erased candidate ⇒ 404 → Task 4 `LookupError`, Task 6 smoke check.
- Contracts → Task 1. Config knobs → Task 3. Smoke + LEDGER.md → Task 6. ROADMAP → sprint close.

**Placeholder scan:** no TBD/TODO; every code step has literal code; test bodies are concrete. Task 5's test-fixture note points the implementer to the file's existing style rather than inventing fixtures — acceptable (it names exactly what to reuse).

**Type consistency:** `assess_reputation` signature identical in Task 3 (definition), Task 4 (call). `ReputationAssessment`/`ReputationBand`/`ReputationComponent` fields defined in Task 1 match their use in Tasks 3–5. `set_org_reliability(org_id, weight)` and `reputation_for_org(*, org_id, candidate_id, at=None)` identical across Task 4 (def) and Task 5 (call). `_org` gains `reliability_weight` in Task 2, consumed by `set_org_reliability`/`get_organization` in Task 4. Migration id `0006_org_reliability_weight` / down-revision `0005_coding_round_results` consistent.
