# Normalization Curation Loop (S6.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A human-in-the-loop taxonomy repair loop — unmapped skill terms surfaced by the GitHub + LinkedIn adapters queue for admin review; a reviewer maps/creates/ignores each; the decision feeds a deterministic overlay that `normalize_skill` consults everywhere.

**Architecture:** New pure-ish `app/curation/` package (schema · ORM model · store · service) on the shared candidates DB. Capture happens in `ProfileSourceService` (service-layer I/O); `normalize_skill` gains an in-memory `_CURATED_OVERLAY` loaded once at startup and refreshed on each resolve (no per-call I/O; static taxonomy always wins). Two admin-plane endpoints. One migration; the queue table is **candidate-agnostic** (no candidate FK, no consent, no CASCADE — it is taxonomy-gap metadata, not personal data).

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 ORM, Alembic, Pydantic v2, pytest. No LLM, no network.

## Global Constraints

- **Advisory / no auto-anything.** A curation decision is a real data change, but the guardrail is that only a human review produces it — no ML, no heuristic auto-mapping. Depth-eval scoring/verdicts untouched.
- **Deterministic, no LLM, no network.** Capture, queue, resolve, overlay all pure Python + one DB table.
- **TDD offline.** `pytest -q` green before merge; every test runs with no API key (the `settings` fixture forces `openrouter_api_key=""` and bypasses `config.yaml`).
- **DB:** SQLAlchemy + Alembic on SQLite, Postgres-shaped. Migration extends the drift/index/nullability guards in `tests/test_migrations.py`.
- **DPDP:** the queue stores **no `candidate_id`** — no new `ConsentPurpose`, no CASCADE. Candidate erasure deliberately leaves queue terms intact.
- **Static taxonomy always wins** over the overlay: `normalize_skill` returns `_INDEX.get(key) or _CURATED_OVERLAY.get(key)`. Curation only fills gaps.
- **No decision-history table** — a re-resolve overwrites the prior resolution. **Forward-only** — resolving does not re-normalize already-stored signals.
- **Config:** tunables in `config.yaml` + `Settings`, prefix `cur_*`. No secrets.
- **Commits:** conventional-commit messages scoped `s63`; **never** append a `Co-Authored-By` trailer (user preference).
- Spec: `docs/superpowers/specs/2026-07-30-s63-normalization-curation-loop-design.md`.

---

### Task 1: Config knobs + curation schema contracts

**Files:**
- Create: `app/curation/__init__.py` (empty package marker)
- Create: `app/curation/schema.py`
- Modify: `app/core/config.py` (add `cur_*` knobs after the S6.2 block, ~line 133)
- Modify: `config.yaml` (add `cur_*` after the S6.2 block, ~line 192)
- Test: `tests/test_curation_schema.py`

**Interfaces:**
- Produces: `CurationStatus(StrEnum)` = `PENDING|RESOLVED|IGNORED`; `CurationAction(StrEnum)` = `MAP|CREATE|IGNORE`; `UnmappedTerm(BaseModel)` with fields `norm_key, display_name, source_types, occurrences, first_seen, last_seen, status, action?, canonical?, category?, note?, decided_by?, decided_at?`.
- Produces: `Settings.cur_queue_default_limit` (200), `Settings.cur_min_term_len` (2), `Settings.cur_max_term_len` (64).

- [ ] **Step 1: Write the failing test**

Create `tests/test_curation_schema.py`:

```python
from datetime import datetime, timezone

from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm


def test_status_and_action_values():
    assert [s.value for s in CurationStatus] == ["pending", "resolved", "ignored"]
    assert [a.value for a in CurationAction] == ["map", "create", "ignore"]


def test_unmapped_term_defaults_pending_no_resolution():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    t = UnmappedTerm(
        norm_key="cobol", display_name="COBOL", source_types=["linkedin_export"],
        first_seen=now, last_seen=now,
    )
    assert t.status == CurationStatus.PENDING
    assert t.occurrences == 1
    assert t.action is None and t.canonical is None and t.category is None


def test_unmapped_term_carries_resolution():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    t = UnmappedTerm(
        norm_key="cobol", display_name="COBOL", first_seen=now, last_seen=now,
        status=CurationStatus.RESOLVED, action=CurationAction.CREATE,
        canonical="cobol", category="language", decided_by="ops", decided_at=now,
    )
    assert t.action == CurationAction.CREATE and t.canonical == "cobol"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_curation_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.curation'`.

- [ ] **Step 3: Create the package + schema**

Create `app/curation/__init__.py` (empty).

Create `app/curation/schema.py`:

```python
"""Curation contracts (PI-6 / S6.3): the review queue for unmapped skill terms.

A skill term normalize_skill can't map (canonical=None) surfaces here as an
UnmappedTerm. A human reviewer resolves it (map / create / ignore); the
resolution feeds a deterministic overlay consulted by normalize_skill. No LLM,
no auto-learning. The queue is candidate-agnostic — taxonomy-gap metadata, not
personal data (no candidate_id, no consent, no CASCADE).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class CurationStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class CurationAction(StrEnum):
    MAP = "map"        # alias -> an existing canonical
    CREATE = "create"  # a new canonical id + category
    IGNORE = "ignore"  # confirmed not-a-skill


class UnmappedTerm(BaseModel):
    """One unmapped skill term in the review queue (aggregate, candidate-agnostic)."""

    norm_key: str                                    # stable identity + API handle
    display_name: str                                # human-readable raw form (most recent)
    source_types: list[str] = Field(default_factory=list)
    occurrences: int = Field(default=1, ge=1)
    first_seen: datetime
    last_seen: datetime
    status: CurationStatus = CurationStatus.PENDING
    # resolution — set only when resolved/ignored
    action: Optional[CurationAction] = None
    canonical: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
```

- [ ] **Step 4: Add config knobs**

In `app/core/config.py`, after the S6.2 block (the line `ps_linkedin_max_rows: int = Field(default=5_000, ge=1)  # per-CSV row cap`), add:

```python
    # --- Normalization curation loop (PI-6, S6.3) ------------------------------
    # Human-in-the-loop taxonomy repair: unmapped skill terms surfaced by the
    # profile-source adapters queue for admin review; a resolution feeds a
    # deterministic normalize_skill overlay. No LLM. The queue is
    # candidate-agnostic (taxonomy-gap metadata — no candidate_id, no consent).
    cur_queue_default_limit: int = Field(default=200, ge=1)   # default + max rows returned
    cur_min_term_len: int = Field(default=2, ge=1)            # skip single-char noise
    cur_max_term_len: int = Field(default=64, ge=1)           # drop overlong junk
```

In `config.yaml`, after the S6.2 block (`ps_linkedin_max_rows: 5000`), add:

```yaml
# --- Normalization curation loop (PI-6) - S6.3 review queue + overlay ----------
cur_queue_default_limit: 200     # default + max rows returned by the queue endpoint
cur_min_term_len: 2              # skip single-char noise before queueing
cur_max_term_len: 64             # drop overlong junk (also caps what we persist)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_curation_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/curation/__init__.py app/curation/schema.py app/core/config.py config.yaml tests/test_curation_schema.py
git commit -m "feat(s63): curation schema contracts + cur_* config knobs"
```

---

### Task 2: `normalize_skill` overlay hook

**Files:**
- Modify: `app/candidates/normalize/skills.py` (add overlay + helpers; change `normalize_skill`)
- Test: `tests/test_curation_overlay.py`

**Interfaces:**
- Consumes: `SkillMatch` (already in `skills.py`).
- Produces: `set_curated_overlay(mapping: dict[str, SkillMatch]) -> None`; `clear_curated_overlay() -> None`; `canonical_ids() -> frozenset[str]`; `category_for_canonical(canonical: str) -> Optional[str]`. `normalize_skill(name)` now consults the overlay after the static index.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curation_overlay.py`:

```python
from app.candidates.normalize.skills import (
    SKILL_CATEGORIES, SkillMatch, canonical_ids, category_for_canonical,
    clear_curated_overlay, normalize_skill, set_curated_overlay,
)


def teardown_function():
    clear_curated_overlay()  # never leak module state between tests


def test_overlay_fills_a_gap():
    assert normalize_skill("COBOL") is None
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    m = normalize_skill("COBOL")
    assert m is not None and m.canonical == "cobol" and m.category == "language"


def test_static_taxonomy_wins_over_overlay():
    # try to shadow a known canonical; static index must still win
    set_curated_overlay({"python": SkillMatch(canonical="hijacked", category="ml")})
    assert normalize_skill("Python").canonical == "python"


def test_clear_overlay_restores_gap():
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    clear_curated_overlay()
    assert normalize_skill("COBOL") is None


def test_canonical_ids_and_category_span_static_and_overlay():
    assert "python" in canonical_ids()
    assert category_for_canonical("python") == "language"
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    assert "cobol" in canonical_ids()
    assert category_for_canonical("cobol") == "language"
    assert category_for_canonical("nope") is None


def test_empty_name_is_none_even_with_overlay():
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    assert normalize_skill("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_curation_overlay.py -v`
Expected: FAIL with `ImportError: cannot import name 'set_curated_overlay'`.

- [ ] **Step 3: Add the overlay + helpers, update `normalize_skill`**

In `app/candidates/normalize/skills.py`, after `_INDEX = _build_index()` add:

```python
# Curation overlay (S6.3): human-reviewed alias -> SkillMatch, loaded from the
# curation store at startup and refreshed on each resolve. Static _INDEX always
# wins; the overlay only fills genuine gaps. No per-call I/O — normalize_skill
# stays a pure dict lookup.
_CURATED_OVERLAY: dict[str, SkillMatch] = {}


def set_curated_overlay(mapping: dict[str, SkillMatch]) -> None:
    """Replace the curation overlay (a copy is stored)."""
    global _CURATED_OVERLAY
    _CURATED_OVERLAY = dict(mapping)


def clear_curated_overlay() -> None:
    _CURATED_OVERLAY.clear()


def canonical_ids() -> frozenset[str]:
    """Every known canonical skill id — static plus curated — for validation."""
    return frozenset(_TAXONOMY.keys()) | {m.canonical for m in _CURATED_OVERLAY.values()}


def category_for_canonical(canonical: str) -> Optional[str]:
    """Category of a known canonical id (static first, then curated); None if unknown."""
    entry = _TAXONOMY.get(canonical)
    if entry is not None:
        return entry[0]
    for m in _CURATED_OVERLAY.values():
        if m.canonical == canonical:
            return m.category
    return None
```

Then change `normalize_skill` from:

```python
def normalize_skill(name: str) -> Optional[SkillMatch]:
    key = norm_key(name or "")
    return _INDEX.get(key) if key else None
```

to:

```python
def normalize_skill(name: str) -> Optional[SkillMatch]:
    key = norm_key(name or "")
    if not key:
        return None
    return _INDEX.get(key) or _CURATED_OVERLAY.get(key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_curation_overlay.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Guard against regressing existing normalization**

Run: `pytest tests/test_normalize_profile.py -q` (and any `test_*skill*`)
Expected: PASS — the overlay defaults empty, so existing behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add app/candidates/normalize/skills.py tests/test_curation_overlay.py
git commit -m "feat(s63): curation overlay hook on normalize_skill (static wins)"
```

---

### Task 3: ORM model + migration `0011_skill_curation`

**Files:**
- Create: `app/curation/models.py`
- Create: `alembic/versions/0011_skill_curation.py`
- Modify: `alembic/env.py` (register the new model for autogenerate parity)
- Modify: `tests/conftest.py` (import the model so `create_all` builds the table)
- Modify: `tests/test_migrations.py` (assert the table + extend guard tuples)

**Interfaces:**
- Produces: `UnmappedTermRow` ORM (table `unmapped_terms`). Columns: `id` (PK), `norm_key` (unique, indexed, not null), `display_name`, `source_types` (JSON), `occurrences`, `first_seen`, `last_seen`, `status` (indexed), `action?`, `canonical?`, `category?`, `note?`, `decided_by?`, `decided_at?`, `created_at`. **No candidate FK.**

- [ ] **Step 1: Write the failing test**

In `tests/test_migrations.py`, add the model import beside the others (after line 15 `import app.profile_sources.models`):

```python
import app.curation.models  # noqa: F401 — populate Base.metadata
```

In `test_upgrade_head_creates_candidate_tables`, after the `profile_sources` assertion add:

```python
    assert "unmapped_terms" in names  # S6.3 migration 0011
```

Add a guard tuple beside the others (after `PROFILE_SOURCE_TABLES = ("profile_sources",)`):

```python
CURATION_TABLES = ("unmapped_terms",)  # S6.3 — candidate-agnostic (no FK)
```

Extend both guard loops to include it — change the two loop headers:

```python
    for table in LEDGER_TABLES + FEATURE_TABLES + MATCHING_TABLES + PROFILE_SOURCE_TABLES + CURATION_TABLES:
```

(in `test_migrated_indexes_match_orm` **and** `test_migrated_fks_and_nullability_match_orm`).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.curation.models'` (and, once that exists but the migration doesn't, `assert "unmapped_terms" in names`).

- [ ] **Step 3: Create the ORM model**

Create `app/curation/models.py`:

```python
"""ORM row for the skill-curation review queue (S6.3). Postgres-shaped on SQLite.

Candidate-AGNOSTIC by design: NO candidate FK. It is taxonomy-gap metadata, so
DPDP erasure of a candidate must NOT remove a known taxonomy gap. Keyed by a
unique norm_key (the upsert key); a surrogate id PK matches the other tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UnmappedTermRow(Base):
    __tablename__ = "unmapped_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    norm_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(Text)
    source_types: Mapped[list] = mapped_column(JSON, default=list)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    canonical: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Create the migration**

Create `alembic/versions/0011_skill_curation.py`:

```python
"""skill curation: unmapped-term review queue (S6.3)

Revision ID: 0011_skill_curation
Revises: 0010_profile_sources
Create Date: 2026-07-30

Candidate-agnostic taxonomy-gap queue: NO candidate FK (survives candidate
erasure by design). Surrogate id PK + unique index on norm_key (the upsert key).
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_skill_curation"
down_revision = "0010_profile_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unmapped_terms",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("norm_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("source_types", sa.JSON(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=True),
        sa.Column("canonical", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_unmapped_terms_norm_key", "unmapped_terms", ["norm_key"], unique=True)
    op.create_index("ix_unmapped_terms_status", "unmapped_terms", ["status"])


def downgrade() -> None:
    op.drop_index("ix_unmapped_terms_status", table_name="unmapped_terms")
    op.drop_index("ix_unmapped_terms_norm_key", table_name="unmapped_terms")
    op.drop_table("unmapped_terms")
```

- [ ] **Step 5: Register the model for env autogenerate + test create_all**

In `alembic/env.py`, after `import app.features.models` (line 15) add:

```python
import app.curation.models  # noqa: F401 — register curation table on Base.metadata
```

In `tests/conftest.py`, after `import app.profile_sources.models` (line 18) add:

```python
import app.curation.models  # noqa: F401 — populate Base.metadata with the curation table
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_migrations.py -v`
Expected: PASS — table present; drift guard clean (ORM ↔ migration match on columns, the two indexes, and nullability); the FK loop is a no-op for `unmapped_terms` (no FKs).

- [ ] **Step 7: Commit**

```bash
git add app/curation/models.py alembic/versions/0011_skill_curation.py alembic/env.py tests/conftest.py tests/test_migrations.py
git commit -m "feat(s63): unmapped_terms table + migration 0011 (candidate-agnostic)"
```

---

### Task 4: `CurationStore`

**Files:**
- Create: `app/curation/store.py`
- Test: `tests/test_curation_store.py`

**Interfaces:**
- Consumes: `UnmappedTermRow`, `SkillMatch`, `CurationAction`, `CurationStatus`, `UnmappedTerm`.
- Produces: `CurationStore(session_factory)` with `record_unmapped(norm_key, display_name, *, source_type, now)`, `list_terms(status=None, limit=200) -> list[UnmappedTerm]`, `get_term(norm_key) -> Optional[UnmappedTerm]`, `resolve(norm_key, *, action, canonical, category, note, decided_by, now) -> UnmappedTerm` (raises `LookupError` if unknown), `load_overlay() -> dict[str, SkillMatch]`. Plus `build_curation_store(settings=None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curation_store.py`:

```python
from datetime import datetime, timedelta, timezone

from app.candidates.normalize.skills import SkillMatch
from app.curation.schema import CurationAction, CurationStatus
from app.curation.store import CurationStore
from tests.conftest import make_candidate_store

T0 = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _store() -> CurationStore:
    cs = make_candidate_store()  # in-memory engine; create_all built unmapped_terms
    return CurationStore(cs._session_factory)


def test_record_inserts_then_bumps_and_unions_sources():
    st = _store()
    st.record_unmapped("cobol", "COBOL", source_type="linkedin_export", now=T0)
    st.record_unmapped("cobol", "Cobol", source_type="github", now=T0 + timedelta(days=1))
    term = st.get_term("cobol")
    assert term.occurrences == 2
    assert set(term.source_types) == {"linkedin_export", "github"}
    assert term.display_name == "Cobol"          # refreshed to most recent
    assert term.last_seen == T0 + timedelta(days=1)
    assert term.status == CurationStatus.PENDING


def test_resolved_term_is_not_requeued_or_recounted():
    st = _store()
    st.record_unmapped("cobol", "COBOL", source_type="linkedin_export", now=T0)
    st.resolve("cobol", action=CurationAction.CREATE, canonical="cobol",
               category="language", note=None, decided_by="ops", now=T0)
    st.record_unmapped("cobol", "COBOL", source_type="github", now=T0 + timedelta(days=2))
    term = st.get_term("cobol")
    assert term.status == CurationStatus.RESOLVED
    assert term.occurrences == 1                  # not bumped
    assert term.source_types == ["linkedin_export"]  # not unioned


def test_list_orders_by_occurrences_then_recency_and_filters_status():
    st = _store()
    st.record_unmapped("aterm", "Aterm", source_type="github", now=T0)
    st.record_unmapped("bterm", "Bterm", source_type="github", now=T0)
    st.record_unmapped("bterm", "Bterm", source_type="github", now=T0 + timedelta(days=1))
    pending = st.list_terms(CurationStatus.PENDING, limit=10)
    assert [t.norm_key for t in pending] == ["bterm", "aterm"]  # bterm has 2 occ
    st.resolve("aterm", action=CurationAction.IGNORE, canonical=None, category=None,
               note=None, decided_by=None, now=T0)
    assert [t.norm_key for t in st.list_terms(CurationStatus.PENDING, limit=10)] == ["bterm"]
    assert [t.norm_key for t in st.list_terms(CurationStatus.IGNORED, limit=10)] == ["aterm"]
    assert len(st.list_terms(None, limit=10)) == 2  # no filter


def test_resolve_unknown_raises():
    st = _store()
    try:
        st.resolve("ghost", action=CurationAction.IGNORE, canonical=None, category=None,
                   note=None, decided_by=None, now=T0)
        assert False, "expected LookupError"
    except LookupError:
        pass


def test_ignore_stores_no_canonical_and_load_overlay_skips_it():
    st = _store()
    st.record_unmapped("team player", "Team Player", source_type="linkedin_export", now=T0)
    st.record_unmapped("cobol", "COBOL", source_type="linkedin_export", now=T0)
    st.resolve("team player", action=CurationAction.IGNORE, canonical=None, category=None,
               note=None, decided_by=None, now=T0)
    st.resolve("cobol", action=CurationAction.CREATE, canonical="cobol", category="language",
               note=None, decided_by=None, now=T0)
    overlay = st.load_overlay()
    assert overlay == {"cobol": SkillMatch(canonical="cobol", category="language")}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_curation_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.curation.store'`.

- [ ] **Step 3: Implement the store**

Create `app/curation/store.py`:

```python
"""Curation store (S6.3) — the unmapped-term review queue, on the candidates DB.

Candidate-agnostic; no delete path (taxonomy-gap metadata survives candidate
erasure by design). Upsert by norm_key. Datetimes are coerced to UTC because
SQLite refetches naive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.candidates.normalize.skills import SkillMatch
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.curation.models import UnmappedTermRow
from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_term(row: UnmappedTermRow) -> UnmappedTerm:
    return UnmappedTerm(
        norm_key=row.norm_key,
        display_name=row.display_name,
        source_types=list(row.source_types or []),
        occurrences=row.occurrences,
        first_seen=_as_utc(row.first_seen),
        last_seen=_as_utc(row.last_seen),
        status=CurationStatus(row.status),
        action=CurationAction(row.action) if row.action else None,
        canonical=row.canonical,
        category=row.category,
        note=row.note,
        decided_by=row.decided_by,
        decided_at=_as_utc(row.decided_at) if row.decided_at else None,
    )


class CurationStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def record_unmapped(
        self, norm_key: str, display_name: str, *, source_type: str, now: datetime
    ) -> None:
        now = _as_utc(now)
        with self._session_factory() as session:
            row = session.execute(
                select(UnmappedTermRow).where(UnmappedTermRow.norm_key == norm_key)
            ).scalar_one_or_none()
            if row is None:
                session.add(UnmappedTermRow(
                    norm_key=norm_key, display_name=display_name,
                    source_types=[source_type], occurrences=1,
                    first_seen=now, last_seen=now,
                    status=CurationStatus.PENDING.value,
                ))
                session.commit()
                return
            if row.status != CurationStatus.PENDING.value:
                return  # resolved/ignored terms are final; never re-queue or recount
            row.occurrences += 1
            row.last_seen = now
            row.display_name = display_name
            if source_type not in (row.source_types or []):
                row.source_types = list(row.source_types or []) + [source_type]
            session.commit()

    def list_terms(
        self, status: Optional[CurationStatus] = None, limit: int = 200
    ) -> list[UnmappedTerm]:
        with self._session_factory() as session:
            q = select(UnmappedTermRow)
            if status is not None:
                q = q.where(UnmappedTermRow.status == status.value)
            q = q.order_by(
                UnmappedTermRow.occurrences.desc(), UnmappedTermRow.last_seen.desc()
            ).limit(limit)
            return [_to_term(r) for r in session.execute(q).scalars().all()]

    def get_term(self, norm_key: str) -> Optional[UnmappedTerm]:
        with self._session_factory() as session:
            row = session.execute(
                select(UnmappedTermRow).where(UnmappedTermRow.norm_key == norm_key)
            ).scalar_one_or_none()
            return _to_term(row) if row else None

    def resolve(
        self, norm_key: str, *, action: CurationAction, canonical: Optional[str],
        category: Optional[str], note: Optional[str], decided_by: Optional[str],
        now: datetime,
    ) -> UnmappedTerm:
        now = _as_utc(now)
        with self._session_factory() as session:
            row = session.execute(
                select(UnmappedTermRow).where(UnmappedTermRow.norm_key == norm_key)
            ).scalar_one_or_none()
            if row is None:
                raise LookupError(f"unmapped term {norm_key!r} not found")
            row.action = action.value
            row.status = (
                CurationStatus.IGNORED if action == CurationAction.IGNORE
                else CurationStatus.RESOLVED
            ).value
            row.canonical = None if action == CurationAction.IGNORE else canonical
            row.category = None if action == CurationAction.IGNORE else category
            row.note = note
            row.decided_by = decided_by
            row.decided_at = now
            session.commit()
            return _to_term(row)

    def load_overlay(self) -> dict[str, SkillMatch]:
        with self._session_factory() as session:
            rows = session.execute(
                select(UnmappedTermRow).where(
                    UnmappedTermRow.status == CurationStatus.RESOLVED.value
                )
            ).scalars().all()
            overlay: dict[str, SkillMatch] = {}
            for r in rows:
                if r.canonical and r.category:
                    overlay[r.norm_key] = SkillMatch(canonical=r.canonical, category=r.category)
            return overlay


def build_curation_store(settings: Optional[Settings] = None) -> CurationStore:
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return CurationStore(make_session_factory(engine))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_curation_store.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/curation/store.py tests/test_curation_store.py
git commit -m "feat(s63): CurationStore (upsert queue, resolve, load_overlay)"
```

---

### Task 5: `CurationService`

**Files:**
- Create: `app/curation/service.py`
- Test: `tests/test_curation_service.py`

**Interfaces:**
- Consumes: `CurationStore`, `norm_key`, `SKILL_CATEGORIES`, `canonical_ids`, `category_for_canonical`, `set_curated_overlay` (all from `app.candidates.normalize.skills`), `CurationAction`, `CurationStatus`, `UnmappedTerm`.
- Produces: `CurationService(*, store, settings)` with `record_unmapped(name, *, source_type)`, `list_unmapped(status=None, limit=None) -> list[UnmappedTerm]`, `resolve(norm_key, action, *, canonical=None, category=None, note=None, decided_by=None) -> UnmappedTerm` (raises `LookupError` → 404, `ValueError` → 422), `refresh_overlay()`. Plus `build_curation_service(settings=None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curation_service.py`:

```python
import pytest

from app.candidates.normalize.skills import clear_curated_overlay, normalize_skill
from app.curation.schema import CurationAction, CurationStatus
from app.curation.service import CurationService
from app.curation.store import CurationStore
from tests.conftest import make_candidate_store


def _svc(settings) -> CurationService:
    cs = make_candidate_store()
    return CurationService(store=CurationStore(cs._session_factory), settings=settings)


def teardown_function():
    clear_curated_overlay()


def test_record_applies_length_guards(settings):
    svc = _svc(settings)  # cur_min_term_len=2, cur_max_term_len=64
    svc.record_unmapped("x", source_type="github")             # too short
    svc.record_unmapped("a" * 65, source_type="github")        # too long
    svc.record_unmapped("   ", source_type="github")           # empty norm_key
    svc.record_unmapped("COBOL", source_type="linkedin_export")
    keys = [t.norm_key for t in svc.list_unmapped(CurationStatus.PENDING)]
    assert keys == ["cobol"]


def test_list_limit_clamped_to_config(settings):
    svc = _svc(settings)
    for i in range(5):
        svc.record_unmapped(f"term{i}", source_type="github")
    assert len(svc.list_unmapped(limit=2)) == 2
    assert len(svc.list_unmapped(limit=10_000)) == 5  # clamped to cur_queue_default_limit


def test_resolve_create_makes_normalize_skill_resolve(settings):
    svc = _svc(settings)
    svc.record_unmapped("COBOL", source_type="linkedin_export")
    assert normalize_skill("COBOL") is None
    term = svc.resolve("cobol", CurationAction.CREATE, canonical="cobol", category="language")
    assert term.status == CurationStatus.RESOLVED
    assert normalize_skill("COBOL").canonical == "cobol"   # overlay refreshed live


def test_resolve_map_to_existing_canonical(settings):
    svc = _svc(settings)
    svc.record_unmapped("PyTorch Lightning", source_type="github")
    term = svc.resolve("pytorch lightning", CurationAction.MAP, canonical="pytorch")
    assert term.canonical == "pytorch" and term.category == "ml"  # category derived
    assert normalize_skill("PyTorch Lightning").canonical == "pytorch"


def test_resolve_validation_matrix(settings):
    svc = _svc(settings)
    for k in ("t1", "t2", "t3", "t4", "t5"):
        svc.record_unmapped(k, source_type="github")
    with pytest.raises(ValueError):  # map to unknown canonical
        svc.resolve("t1", CurationAction.MAP, canonical="not_a_real_skill")
    with pytest.raises(ValueError):  # map with no canonical
        svc.resolve("t2", CurationAction.MAP)
    with pytest.raises(ValueError):  # create bad category
        svc.resolve("t3", CurationAction.CREATE, canonical="cobol", category="nope")
    with pytest.raises(ValueError):  # create canonical that already exists
        svc.resolve("t4", CurationAction.CREATE, canonical="python", category="language")
    with pytest.raises(ValueError):  # ignore with a canonical is contradictory
        svc.resolve("t5", CurationAction.IGNORE, canonical="python")


def test_resolve_unknown_term_raises_lookup(settings):
    svc = _svc(settings)
    with pytest.raises(LookupError):
        svc.resolve("ghost", CurationAction.IGNORE)


def test_create_bad_id_shape_rejected(settings):
    svc = _svc(settings)
    svc.record_unmapped("Some Skill", source_type="github")
    with pytest.raises(ValueError):  # not snake_case
        svc.resolve("some skill", CurationAction.CREATE, canonical="Not Snake", category="language")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_curation_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.curation.service'`.

- [ ] **Step 3: Implement the service**

Create `app/curation/service.py`:

```python
"""Curation service (S6.3): capture unmapped terms, serve the review queue,
resolve a term, and refresh the deterministic normalize_skill overlay.

Validation is deterministic; no LLM. On resolve the in-memory overlay is
refreshed so the correction is live for the running process immediately.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.candidates.normalize.skills import (
    SKILL_CATEGORIES, canonical_ids, category_for_canonical, norm_key,
    set_curated_overlay,
)
from app.core.config import Settings, get_settings
from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm
from app.curation.store import CurationStore, build_curation_store

_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CurationService:
    def __init__(self, *, store: CurationStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    # --- capture (called by profile-source ingestion) -------------------------
    def record_unmapped(self, name: str, *, source_type: str) -> None:
        key = norm_key(name or "")
        if not key:
            return
        if not (self._settings.cur_min_term_len <= len(key) <= self._settings.cur_max_term_len):
            return
        self._store.record_unmapped(
            key, name.strip(), source_type=source_type, now=datetime.now(timezone.utc)
        )

    # --- review ---------------------------------------------------------------
    def list_unmapped(
        self, status: Optional[CurationStatus] = None, limit: Optional[int] = None
    ) -> list[UnmappedTerm]:
        cap = self._settings.cur_queue_default_limit
        limit = cap if limit is None else max(1, min(limit, cap))
        return self._store.list_terms(status, limit)

    # --- resolve --------------------------------------------------------------
    def resolve(
        self, norm_key_value: str, action: CurationAction, *,
        canonical: Optional[str] = None, category: Optional[str] = None,
        note: Optional[str] = None, decided_by: Optional[str] = None,
    ) -> UnmappedTerm:
        if self._store.get_term(norm_key_value) is None:
            raise LookupError(f"unmapped term {norm_key_value!r} not found")
        canonical, category = self._validate(action, canonical, category)
        term = self._store.resolve(
            norm_key_value, action=action, canonical=canonical, category=category,
            note=note, decided_by=decided_by, now=datetime.now(timezone.utc),
        )
        self.refresh_overlay()
        return term

    def _validate(
        self, action: CurationAction, canonical: Optional[str], category: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        if action == CurationAction.IGNORE:
            if canonical or category:
                raise ValueError("ignore takes no canonical/category")
            return None, None
        if action == CurationAction.MAP:
            if not canonical:
                raise ValueError("map requires a canonical")
            if canonical not in canonical_ids():
                raise ValueError(f"unknown canonical {canonical!r}")
            return canonical, category_for_canonical(canonical)  # category derived
        if action == CurationAction.CREATE:
            if not canonical or not _CANONICAL_ID_RE.fullmatch(canonical):
                raise ValueError("create requires a snake_case canonical id")
            if canonical in canonical_ids():
                raise ValueError(f"canonical {canonical!r} already exists (use map)")
            if not category or category not in SKILL_CATEGORIES:
                raise ValueError(f"create requires a category in {sorted(SKILL_CATEGORIES)}")
            return canonical, category
        raise ValueError(f"unknown action {action!r}")

    def refresh_overlay(self) -> None:
        set_curated_overlay(self._store.load_overlay())


def build_curation_service(settings: Optional[Settings] = None) -> CurationService:
    settings = settings or get_settings()
    return CurationService(store=build_curation_store(settings), settings=settings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_curation_service.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/curation/service.py tests/test_curation_service.py
git commit -m "feat(s63): CurationService (capture guards, resolve validation, overlay refresh)"
```

---

### Task 6: Capture wiring + Services container + conftest

**Files:**
- Modify: `app/profile_sources/service.py` (optional `curation` dep + `_capture_unmapped` after each `to_signal`)
- Modify: `app/services/__init__.py` (add `Services.curation`; build + inject + `refresh_overlay()` at startup)
- Modify: `tests/conftest.py` (add `curation` to `make_services`; add an autouse fixture that resets the overlay)
- Test: `tests/test_curation_capture.py`

**Interfaces:**
- Consumes: `CurationService`, `ProfileSourceService`, `Services`, `build_curation_service`.
- Produces: `ProfileSourceService(..., curation: Optional[CurationService] = None)`; `build_profile_source_service(..., curation=None)`; `Services.curation: CurationService`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curation_capture.py`:

```python
from app.candidates.normalize.skills import clear_curated_overlay
from app.curation.schema import CurationStatus
from tests.conftest import make_services


def teardown_function():
    clear_curated_overlay()


def _candidate(services) -> str:
    from app.candidates.models import CandidateRow
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="Cap")
        s.add(row)
        s.commit()
        return row.id


async def test_github_ingest_captures_unmapped_skill(settings, fake_github):
    # FakeGitHub default user signal reports language "Python" (maps) — inject an
    # unknown language so an unmapped skill flows to the queue.
    from app.services.github import GitHubRepoRaw, GitHubUserRaw
    from tests.conftest import FakeGitHub
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True, public_repos=1, followers=0,
        repos=[GitHubRepoRaw(name="r", language="Cobol", languages={"Cobol": 5000},
                             stargazers_count=1, pushed_at="2025-01-01T00:00:00Z")],
    )})
    services = make_services(settings, github=gh)
    cid = _candidate(services)
    await services.profile_sources.ingest_github(cid, handle="dev")
    pending = services.curation.list_unmapped(CurationStatus.PENDING)
    assert any(t.norm_key == "cobol" and "github" in t.source_types for t in pending)


async def test_fully_mapped_signal_queues_nothing(settings):
    from app.services.github import GitHubRepoRaw, GitHubUserRaw
    from tests.conftest import FakeGitHub
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True, public_repos=1, followers=0,
        repos=[GitHubRepoRaw(name="r", language="Python", languages={"Python": 5000},
                             stargazers_count=1, pushed_at="2025-01-01T00:00:00Z")],
    )})
    services = make_services(settings, github=gh)
    cid = _candidate(services)
    await services.profile_sources.ingest_github(cid, handle="dev")
    assert services.curation.list_unmapped(CurationStatus.PENDING) == []


async def test_capture_failure_does_not_break_ingest(settings):
    # Inject an UNMAPPED language so _capture_unmapped actually calls record_unmapped
    # (the default FakeGitHub reports "Python", which maps and would never capture).
    from app.services.github import GitHubRepoRaw, GitHubUserRaw
    from tests.conftest import FakeGitHub
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True, public_repos=1, followers=0,
        repos=[GitHubRepoRaw(name="r", language="Cobol", languages={"Cobol": 5000},
                             stargazers_count=1, pushed_at="2025-01-01T00:00:00Z")],
    )})
    services = make_services(settings, github=gh)

    class Boom:
        def record_unmapped(self, *a, **k):
            raise RuntimeError("boom")

    services.profile_sources._curation = Boom()
    cid = _candidate(services)
    sig = await services.profile_sources.ingest_github(cid, handle="dev")
    assert sig is not None  # ingestion still succeeds despite capture blowing up
    assert any(s.canonical is None for s in sig.skills)  # capture path was exercised
```

Note: these are `async def` tests — the repo already runs async tests (see `test_profile_sources_service.py`); `pytest-asyncio` is configured. If a test is skipped as "async not natively supported", check `pyproject.toml`/`pytest.ini` for `asyncio_mode = auto` (already set for existing async service tests).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_curation_capture.py -v`
Expected: FAIL — `Services` has no `curation` attribute / `make_services` rejects it (depending on order), or capture is absent so the queue is empty.

- [ ] **Step 3: Add the capture hook to `ProfileSourceService`**

In `app/profile_sources/service.py`:

Add to imports (top-level is fine — no cycle: `curation.service` does not import `profile_sources`):

```python
from app.curation.service import CurationService
```

Change `__init__` to accept the optional dep:

```python
    def __init__(
        self,
        *,
        github: GitHubService,
        store: ProfileSourceStore,
        candidates: CandidateStore,
        settings: Settings,
        curation: Optional[CurationService] = None,
    ) -> None:
        self._github = github
        self._store = store
        self._candidates = candidates
        self._settings = settings
        self._curation = curation
```

In `ingest_github`, after `signal = github_to_signal(...)` and before `self._store.save_signal(...)`, add:

```python
        self._capture_unmapped(signal)
```

In `ingest_linkedin`, after `signal = linkedin_to_signal(...)` and before `self._store.save_signal(...)`, add:

```python
        self._capture_unmapped(signal)
```

Add the helper method to the class:

```python
    def _capture_unmapped(self, signal: ProfileSourceSignal) -> None:
        """Queue every skill the taxonomy couldn't map (canonical is None) for
        curation review. Best-effort — capture must never break ingestion."""
        if self._curation is None:
            return
        for skill in signal.skills:
            if skill.canonical is None:
                try:
                    self._curation.record_unmapped(
                        skill.name, source_type=signal.source_type.value
                    )
                except Exception:  # noqa: BLE001 — advisory capture, never fatal
                    pass
```

Update `build_profile_source_service` to thread the optional dep:

```python
def build_profile_source_service(
    settings: Optional[Settings] = None,
    *,
    github: Optional[GitHubService] = None,
    candidates: Optional[CandidateStore] = None,
    curation: Optional["CurationService"] = None,
) -> ProfileSourceService:
    settings = settings or get_settings()
    candidates = candidates or build_candidate_store(settings)
    github = github or GitHubClient(settings)
    store = build_profile_source_store(settings)
    return ProfileSourceService(
        github=github, store=store, candidates=candidates, settings=settings,
        curation=curation,
    )
```

- [ ] **Step 4: Wire `Services.curation`**

In `app/services/__init__.py`:

Add to the `TYPE_CHECKING` block:

```python
    from app.curation.service import CurationService
```

Add the field to the `Services` dataclass (after `profile_sources`):

```python
    curation: CurationService
```

In `build_default_services`, add the function-local import:

```python
    from app.curation.service import build_curation_service
```

Then build it, load the overlay once, inject it into profile sources, and put it on the container:

```python
    github = GitHubClient(settings)
    candidates = build_candidate_store(settings)
    curation = build_curation_service(settings)
    curation.refresh_overlay()  # load prior curation into the normalize_skill overlay
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=github,
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=candidates,
        ledger=build_ledger_store(settings),
        features=build_feature_store(settings),
        jobs=build_job_store(settings),
        comp=build_comp_service(settings),
        dashboard=build_dashboard_service(settings),
        profile_sources=build_profile_source_service(
            settings, github=github, candidates=candidates, curation=curation
        ),
        curation=curation,
    )
```

- [ ] **Step 5: Update `tests/conftest.py`**

Add `curation=None` to the `make_services` signature (after `profile_sources=None`):

```python
    profile_sources=None,
    curation=None,
) -> Services:
```

Build the curation service on the shared candidate session factory **before** `profile_sources` (so it can be injected), replacing the `profile_sources` block:

```python
    if curation is None:
        from app.curation.service import CurationService
        from app.curation.store import CurationStore
        curation = CurationService(
            store=CurationStore(candidates._session_factory), settings=settings
        )
    if profile_sources is None:
        from app.profile_sources.service import ProfileSourceService
        from app.profile_sources.store import ProfileSourceStore
        profile_sources = ProfileSourceService(
            github=github,
            store=ProfileSourceStore(candidates._session_factory),
            candidates=candidates, settings=settings, curation=curation,
        )
```

Add `curation=curation` to the returned `Services(...)` (after `profile_sources=profile_sources,`):

```python
        profile_sources=profile_sources,
        curation=curation,
    )
```

Add an autouse fixture (place it after the `settings` fixture) so the module-global overlay never leaks between tests:

```python
@pytest.fixture(autouse=True)
def _reset_curation_overlay():
    from app.candidates.normalize.skills import clear_curated_overlay
    clear_curated_overlay()
    yield
    clear_curated_overlay()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_curation_capture.py tests/test_profile_sources_service.py tests/test_profile_sources_api.py -v`
Expected: PASS — capture works; existing profile-source tests still green (they pass `curation` implicitly via `make_services`).

- [ ] **Step 7: Commit**

```bash
git add app/profile_sources/service.py app/services/__init__.py tests/conftest.py tests/test_curation_capture.py
git commit -m "feat(s63): capture unmapped skills on ingest + wire Services.curation"
```

---

### Task 7: Admin-plane API endpoints

**Files:**
- Modify: `app/api/routes.py` (imports; `CurationResolveRequest`; two endpoints on `router`)
- Test: `tests/test_curation_api.py`

**Interfaces:**
- Consumes: `Services.curation`, `CurationAction`, `CurationStatus`, `UnmappedTerm`.
- Produces: `GET /curation/skills/unmapped?status=&limit=` → `list[UnmappedTerm]`; `POST /curation/skills/resolve` (body `CurationResolveRequest`) → `UnmappedTerm` (404 unknown / 422 invalid).

- [ ] **Step 1: Write the failing test**

Create `tests/test_curation_api.py`:

```python
import base64
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


def _client(services):
    return TestClient(create_app(services), raise_server_exceptions=False)


def _candidate(client) -> str:
    r = client.post("/candidates", json={
        "resume_text": "Dev\nEmail: dev@example.com\nSKILLS\nPython\n", "evaluate": False})
    assert r.status_code == 200
    return r.json()["candidate_id"]


def _linkedin_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nCOBOL\n")
        zf.writestr("Profile.csv", "Headline,Industry\nEngineer,IT\n")
    return base64.b64encode(buf.getvalue()).decode()


def test_unmapped_queue_lists_captured_term(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.get("/curation/skills/unmapped?status=pending")
        assert r.status_code == 200
        keys = [t["norm_key"] for t in r.json()]
        assert "cobol" in keys


def test_resolve_create_then_term_no_longer_pending(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.post("/curation/skills/resolve", json={
            "norm_key": "cobol", "action": "create", "canonical": "cobol", "category": "language"})
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"
        pending = client.get("/curation/skills/unmapped?status=pending").json()
        assert "cobol" not in [t["norm_key"] for t in pending]


def test_resolve_unknown_term_404(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        r = client.post("/curation/skills/resolve", json={"norm_key": "ghost", "action": "ignore"})
        assert r.status_code == 404


def test_resolve_invalid_decision_422(settings, fake_github):
    services = make_services(settings, github=fake_github)
    with _client(services) as client:
        cid = _candidate(client)
        client.post(f"/candidates/{cid}/sources/linkedin", json={"export_b64": _linkedin_b64()})
        r = client.post("/curation/skills/resolve", json={
            "norm_key": "cobol", "action": "map", "canonical": "not_a_real_skill"})
        assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_curation_api.py -v`
Expected: FAIL — 404 on `GET /curation/skills/unmapped` (route not registered).

- [ ] **Step 3: Implement the endpoints**

In `app/api/routes.py`, add to the imports near the other schema imports:

```python
from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm
```

Add a request model next to the other `BaseModel` request classes (e.g. just before the profile-source section, or grouped with a new comment header). Place the endpoints on `router` (the `X-API-Key` admin plane) — a natural spot is right after `list_candidate_sources` (~line 421):

```python
# ── Normalization curation loop (S6.3) ───────────────────────────────────────
# Admin-plane review of unmapped skill terms surfaced by the profile-source
# adapters. Resolving a term feeds the deterministic normalize_skill overlay.
# (Candidate/org auth is S6.4; until then this rides the shared X-API-Key.)


class CurationResolveRequest(BaseModel):
    norm_key: str
    action: CurationAction
    canonical: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None
    decided_by: Optional[str] = None


@router.get("/curation/skills/unmapped", response_model=list[UnmappedTerm])
async def list_unmapped_terms(
    request: Request,
    status: Optional[CurationStatus] = None,
    limit: Optional[int] = None,
) -> list[UnmappedTerm]:
    return _services(request).curation.list_unmapped(status, limit)


@router.post("/curation/skills/resolve", response_model=UnmappedTerm)
async def resolve_unmapped_term(
    req: CurationResolveRequest, request: Request
) -> UnmappedTerm:
    services = _services(request)
    try:
        return services.curation.resolve(
            req.norm_key, req.action, canonical=req.canonical, category=req.category,
            note=req.note, decided_by=req.decided_by,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

(`Optional` and `BaseModel` are already imported in `routes.py`; `Request`/`HTTPException` too.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_curation_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS — all prior tests plus the new curation tests (~725 → ~750+ green).

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py tests/test_curation_api.py
git commit -m "feat(s63): admin-plane curation endpoints (GET unmapped, POST resolve)"
```

---

### Task 8: Docs + smoke

**Files:**
- Create: `CURATION.md`
- Modify: `PROFILE_SOURCES.md` (flip the "S6.3 deferred" note to "shipped")
- Create: `scripts/smoke_s63.py`

**Interfaces:** none new — this task documents and end-to-end-verifies the built feature.

- [ ] **Step 1: Write `CURATION.md`**

Create `CURATION.md` (peer of `PROFILE_SOURCES.md`) covering: the loop (capture → queue → resolve → overlay), the pure/impure seams (`normalize_skill` stays pure; capture + store do I/O; overlay loaded once at startup + on each resolve), the **static-wins precedence rule**, the **DPDP posture** (candidate-agnostic queue, no consent/CASCADE, candidate erasure leaves terms), the API contract (GET unmapped / POST resolve with the 200/404/422 matrix), the `cur_*` config table, and the non-goals/follow-ups (employers/institutions, resume capture, retroactive re-normalization, decision history, cross-process propagation, LLM suggestions). Use this skeleton:

```markdown
# Normalization curation loop (skills) — PI-6 / S6.3

A human-in-the-loop taxonomy repair loop. Skill terms that `normalize_skill`
can't map (`canonical=None`), surfaced by the GitHub + LinkedIn adapters, are
captured into a candidate-agnostic review queue. An admin reviewer resolves each
term — **map** to an existing canonical, **create** a new canonical, or
**ignore** — and the resolution feeds a deterministic in-memory overlay that
`normalize_skill` consults everywhere. No LLM, no auto-learning.

## The loop
[ingest → _capture_unmapped → CurationStore(queue) → admin GET/POST resolve →
CurationService.refresh_overlay → set_curated_overlay → normalize_skill]

## Pure / impure seams
- `normalize_skill` stays a pure dict lookup: `_INDEX.get(key) or _CURATED_OVERLAY.get(key)`.
  **Static taxonomy always wins**; the overlay only fills gaps. No per-call I/O.
- `_CURATED_OVERLAY` is loaded once in `build_default_services` (startup) and
  refreshed in-process on every `resolve`.
- Capture (`ProfileSourceService._capture_unmapped`) is best-effort and never
  breaks ingestion.

## DPDP posture
The queue (`unmapped_terms`) holds **no candidate_id** — aggregate taxonomy-gap
metadata (norm_key + counts + source_types), not personal data. No new
`ConsentPurpose`, no CASCADE. Candidate erasure deliberately leaves queue terms
intact. `cur_min_term_len`/`cur_max_term_len` drop noise/overlong junk before it
is ever persisted.

## API (admin plane, X-API-Key)
- `GET /curation/skills/unmapped?status=pending&limit=N` → 200 `list[UnmappedTerm]`
  (occurrence-ranked; `status` ∈ pending|resolved|ignored|omitted).
- `POST /curation/skills/resolve` — body `{norm_key, action, canonical?, category?,
  note?, decided_by?}` → 200 updated term · 404 unknown term · 422 invalid
  (map without/to unknown canonical; create bad id/category or an existing
  canonical; ignore with canonical/category). Term rides in the body — `norm_key`
  is not URL-safe.

## Config
| knob | default | purpose |
|---|---|---|
| `cur_queue_default_limit` | 200 | default + max rows returned by the queue endpoint |
| `cur_min_term_len` | 2 | skip single-char noise before queueing |
| `cur_max_term_len` | 64 | drop overlong junk (also caps what we persist) |

## Non-goals / follow-ups
Employers/institutions curation · resume-extraction capture · retroactive
re-normalization of stored signals (forward-only) · decision-history/audit table
(re-resolve overwrites) · cross-process overlay propagation (single-process
today; restart reloads) · LLM-suggested mappings (deterministic-only per vision)
· candidate-facing UX (S6.4).
```

- [ ] **Step 2: Flip the `PROFILE_SOURCES.md` note**

In `PROFILE_SOURCES.md`, change the "Non-goals / follow-ups" bullet

```markdown
- **Normalization curation loop** (reviewing/correcting unmapped taxonomy
  terms surfaced by either adapter) — **S6.3**.
```

to:

```markdown
- **Normalization curation loop** (reviewing/correcting unmapped skill terms
  surfaced by either adapter) — **shipped in S6.3, see `CURATION.md`.**
```

Also update the intro line (~line 14) from "The **normalization curation loop** (…) is deferred to **S6.3**." to "The **normalization curation loop** (…) shipped in **S6.3** — see `CURATION.md`."

- [ ] **Step 3: Write the smoke script**

Create `scripts/smoke_s63.py` (mirror `scripts/smoke_s62.py`'s uvicorn + migrated-scratch-DB harness):

```python
"""S6.3 smoke: boot uvicorn on a migrated scratch DB, ingest a LinkedIn export
containing novel skills, verify they queue for curation, resolve them
(create / map / ignore), re-ingest and confirm the overlay now maps them, then
prove the queue is candidate-agnostic (survives DPDP erasure). No network, no
LLM. Run from repo root: python scripts/smoke_s63.py
"""

import base64
import io
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

PORT = 8063
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
RESUME = "Dev\nEmail: dev@example.com\nSKILLS\nPython\n"


def _export_b64() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Skills.csv", "Name\nPython\nCOBOL\nPyTorch Lightning\nTeam Player\n")
        zf.writestr("Profile.csv", "Headline,Industry\nEngineer,Information Technology\n")
    return base64.b64encode(buf.getvalue()).decode()


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
    url = "sqlite:///" + (scratch / "smoke_s63.db").as_posix()
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
                print("FAIL server never became healthy")
                return 1

            cid = c.post("/candidates", json={"resume_text": RESUME, "evaluate": False},
                         headers=admin_h).json()["candidate_id"]

            r = c.post(f"/candidates/{cid}/sources/linkedin",
                       json={"export_b64": _export_b64()}, headers=admin_h)
            checks["POST linkedin -> 200"] = r.status_code == 200

            pend = c.get("/curation/skills/unmapped?status=pending", headers=admin_h).json()
            pkeys = {t["norm_key"] for t in pend}
            checks["cobol queued pending"] = "cobol" in pkeys
            checks["pytorch lightning queued pending"] = "pytorch lightning" in pkeys
            checks["team player queued pending"] = "team player" in pkeys

            r1 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "cobol", "action": "create",
                "canonical": "cobol", "category": "language"})
            checks["resolve create cobol -> 200"] = r1.status_code == 200
            r2 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "pytorch lightning", "action": "map", "canonical": "pytorch"})
            checks["resolve map pytorch -> 200"] = r2.status_code == 200
            checks["map derived category ml"] = r2.json().get("category") == "ml"
            r3 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "team player", "action": "ignore"})
            checks["resolve ignore -> 200"] = r3.status_code == 200

            bad = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "nope", "action": "ignore"})
            checks["resolve unknown -> 404"] = bad.status_code == 404
            bad2 = c.post("/curation/skills/resolve", headers=admin_h, json={
                "norm_key": "cobol", "action": "map", "canonical": "not_real"})
            # cobol is already resolved, but validation runs after existence: map to
            # unknown canonical is 422.
            checks["resolve invalid -> 422"] = bad2.status_code == 422

            # re-ingest: overlay now maps cobol + pytorch lightning; team player stays unmapped
            r = c.post(f"/candidates/{cid}/sources/linkedin",
                       json={"export_b64": _export_b64()}, headers=admin_h)
            skills = {s["name"]: s for s in r.json().get("skills", [])}
            checks["COBOL now canonical cobol"] = skills.get("COBOL", {}).get("canonical") == "cobol"
            checks["PyTorch Lightning now pytorch"] = (
                skills.get("PyTorch Lightning", {}).get("canonical") == "pytorch")
            checks["Team Player still unmapped"] = skills.get("Team Player", {}).get("canonical") is None

            still_pending = {t["norm_key"] for t in
                             c.get("/curation/skills/unmapped?status=pending", headers=admin_h).json()}
            checks["nothing re-queued pending"] = not (
                {"cobol", "pytorch lightning", "team player"} & still_pending)

            # DPDP: erasing the candidate must NOT sweep the candidate-agnostic queue
            deleted = c.delete(f"/candidates/{cid}", headers=admin_h)
            checks["DPDP delete candidate -> 200"] = deleted.status_code == 200
            all_terms = {t["norm_key"] for t in
                         c.get("/curation/skills/unmapped", headers=admin_h).json()}
            checks["queue survives erasure"] = {"cobol", "pytorch lightning", "team player"} <= all_terms
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the smoke**

Run: `python scripts/smoke_s63.py`
Expected: every check `OK`, final `SMOKE OK`, exit 0.

- [ ] **Step 5: Run the full suite once more**

Run: `pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add CURATION.md PROFILE_SOURCES.md scripts/smoke_s63.py
git commit -m "docs(s63): CURATION.md + PROFILE_SOURCES note + smoke_s63 (12/12)"
```

---

### Task 9: ROADMAP closeout

**Files:**
- Modify: `docs/ROADMAP.md` (status board S6.3 `[ ]`→`[x]`; "Current state"; "Next action" → S6.4; new session-log entry dated 2026-07-30)

**Interfaces:** none — bookkeeping that ends the sprint per CLAUDE.md.

- [ ] **Step 1: Update the status board**

In `docs/ROADMAP.md`, change the S6.3 line in the PI-6 block from `[ ] S6.3` to `[x] S6.3` and mark it done.

- [ ] **Step 2: Update "Current state" + "Next action"**

Rewrite the "▶ Current state" top bullet to describe S6.3 as COMPLETE (package `app/curation/`, overlay hook, capture wiring, migration 0011, two admin endpoints, `cur_*` knobs, `CURATION.md`, smoke, test count, candidate-agnostic DPDP posture, forward-only, static-wins). Set "Next action" to shape/plan **S6.4** (candidate auth + DPDP portal), noting the S6.3 follow-ups to fold in (employers/institutions curation, resume-extraction capture, retroactive re-normalization, decision history).

- [ ] **Step 3: Add a session-log entry**

Add a `**2026-07-30** — **S6.3 (normalization curation loop) built** …` entry at the top of the Session log summarizing scope, decisions (skills-only; system-wide overlay; profile-sources capture; static-wins; no history), test delta, and the smoke result.

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(s63): ROADMAP closeout — S6.3 curation loop complete"
```

- [ ] **Step 5: Finish the branch**

Use the **superpowers:finishing-a-development-branch** skill: run a whole-branch review, confirm `pytest -q` green + smoke exit 0, then fast-forward merge `s63-normalization-curation` into `main` and delete the branch (matching every prior sprint's close).

---

## Self-Review

**Spec coverage** (each §5/§6/§8 item → task):
- §5.1 `app/curation/schema.py` → T1 · `store.py` → T4 · `service.py` → T5 ✓
- §5.2 overlay hook (`_CURATED_OVERLAY`, precedence, set/clear, `canonical_ids`, `category_for_canonical`) → T2 ✓
- §5.2 startup load in `build_default_services` → T6 ✓
- §5.3 capture wiring in `ProfileSourceService` → T6 ✓
- §5.4 `Services.curation` cycle-safe wiring → T6 ✓
- §5.5 migration `0011` + guards → T3 ✓
- §6 two admin endpoints + 200/404/422 → T7 ✓
- §7 `cur_*` config → T1 ✓
- §4 DPDP candidate-agnostic (no FK; survives erasure) → T3 (no-FK migration + guard) + T8 smoke assertion ✓
- §8 unit/integration/API tests → T2/T4/T5/T6/T7 · smoke `scripts/smoke_s63.py` → T8 ✓
- §10 DoD (`CURATION.md`, `PROFILE_SOURCES.md` note, ROADMAP) → T8/T9 ✓

**Placeholder scan:** every code + test step carries real content; no TBD/TODO/"handle edge cases". ✓

**Type consistency:** `SkillMatch(canonical, category)` used identically in T2/T4/T5; `record_unmapped(norm_key, display_name, *, source_type, now)` (store, T4) vs `record_unmapped(name, *, source_type)` (service, T5) — deliberately different layers, the service computes `norm_key`/`display_name` and stamps `now` before calling the store; `resolve(...)` store signature (kw-only `action, canonical, category, note, decided_by, now`) matches the service's call in T5; `list_terms(status, limit)` (store) vs `list_unmapped(status, limit)` (service) consistent; endpoints (T7) call `list_unmapped`/`resolve` with the names defined in T5. ✓
