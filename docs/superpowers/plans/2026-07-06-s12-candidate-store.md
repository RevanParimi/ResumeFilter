# S1.2 Candidate Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist S1.1 `ExtractionResult`s into a versioned candidate database (SQLAlchemy + Alembic on SQLite, Postgres-shaped) with hash-based identity resolution and DPDP hard-delete paths.

**Architecture:** A shared SQLAlchemy foundation (`app/core/db.py`: declarative `Base`, engine + session factory — later reused by ledger/features) plus candidate-specific ORM rows (`app/candidates/models.py`) and a `CandidateStore` facade (`app/candidates/store.py`) that owns identity resolution (email-hash first, phone-hash second), per-candidate resume versioning, and extraction audit rows. Alembic owns the schema (no `create_all` in production paths); tests use in-memory SQLite with `create_all` for speed, plus a migration-vs-models drift guard.

**Tech Stack:** SQLAlchemy 2.x (typed `Mapped`/`mapped_column`), Alembic, SQLite (Postgres-shaped: UUID-string PKs, real FKs with `ondelete=CASCADE`, JSON columns), Pydantic v2 for all public return types.

## Global Constraints

- TDD, fully offline tests; `pytest -q` green before merge (88 tests green today — never fewer).
- No LLM calls anywhere in this sprint (the store is deterministic by nature).
- Advisory only: the store never scores or rejects; it records.
- DPDP: `delete_candidate` and `delete_resume` are HARD deletes that cascade to children.
- Config: tunables in `config.yaml` + `Settings` (`app/core/config.py`, `DEE_` env prefix); no secrets in YAML.
- DB Postgres-shaped: UUID-string PKs (`String(36)`), FKs with `ondelete="CASCADE"`, `JSON` columns, `DateTime(timezone=True)`; the PG switch must be a connection-string change only.
- Windows venv: run Python as `.resume\Scripts\python.exe`; tests as `.resume\Scripts\python.exe -m pytest -q` from repo root.
- Work on branch `s12-candidate-store` (create from `main` before Task 1).
- Deliberate design point (document, don't relitigate): unlike the report store, `resumes.raw_text` DOES persist the resume text — it is first-party submitted data, S1.1 `SourceSpan` offsets index into it, and both delete paths erase it. This is the DPDP-compliant way to keep provenance auditable.

**Existing interfaces this plan consumes (already on `main`):**

- `app.candidates.schema.ExtractionResult` — fields: `profile: CandidateProfile`, `method: Literal["llm","heuristic"]`, `warnings: list[str]`.
- `app.candidates.schema.CandidateProfile` — has `full_name: Optional[ExtractedStr]` (`.value: str`), `contact: ContactInfo` with `email_hash: Optional[str]`, `phone_hash: Optional[str]` (filled by `app.candidates.hashing.apply_contact_hashes(profile, salt)`).
- `tests/conftest.py` `settings` fixture — hermetic `Settings` on pure code defaults.

---

### Task 1: Dependencies + shared DB core (`app/core/db.py`)

**Files:**
- Modify: `requirements.txt`
- Modify: `app/core/config.py` (add `candidates_db_url` after `contact_hash_salt`, ~line 118)
- Modify: `config.yaml` (add candidate-store section after `contact_hash_salt`, ~line 48)
- Create: `app/core/db.py`
- Test: `tests/test_db_core.py`

**Interfaces:**
- Consumes: `app.core.config.Settings` (existing).
- Produces: `Base` (DeclarativeBase subclass — the single metadata root for ALL subsystems), `make_engine(url: str) -> Engine`, `make_session_factory(engine: Engine) -> sessionmaker`, and `Settings.candidates_db_url: str` (default `"sqlite:///./data/veritas.db"`).

- [ ] **Step 1: Create branch and install dependencies**

```powershell
git checkout -b s12-candidate-store
```

Add to `requirements.txt` after the `# --- Vector store ---` block:

```
# --- Relational store (candidates; ledger/features later) ---
sqlalchemy>=2.0
alembic>=1.13
```

Run: `.resume\Scripts\python.exe -m pip install -r requirements.txt`
Expected: `Successfully installed SQLAlchemy-2.x alembic-1.x ...` (Mako comes with alembic).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_db_core.py`:

```python
"""app/core/db.py — shared engine/session plumbing + SQLite accommodations."""

from sqlalchemy import inspect, text

from app.core.db import make_engine, make_session_factory


def test_settings_default_candidates_db_url(settings):
    assert settings.candidates_db_url == "sqlite:///./data/veritas.db"


def test_memory_sqlite_shares_one_database_across_connections():
    engine = make_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.commit()
    # StaticPool: a *second* connection must see the same in-memory DB.
    assert "t" in inspect(engine).get_table_names()


def test_sqlite_foreign_keys_are_enforced():
    engine = make_engine("sqlite://")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_file_sqlite_creates_parent_directory(tmp_path):
    db = tmp_path / "nested" / "dir" / "c.db"
    engine = make_engine("sqlite:///" + db.as_posix())
    with engine.connect():
        pass
    assert db.parent.is_dir()


def test_session_factory_yields_working_sessions():
    factory = make_session_factory(make_engine("sqlite://"))
    with factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_db_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.db'` (collection error is fine).

- [ ] **Step 4: Implement `app/core/db.py` and the settings key**

Create `app/core/db.py`:

```python
"""Shared SQLAlchemy foundation: declarative Base, engine, session factory.

SQLite now, Postgres-shaped: models use UUID-string PKs, real FKs and JSON
columns, so the PG switch is a connection-string change (``candidates_db_url``),
never a schema rewrite. SQLite needs two accommodations, both handled here:
``PRAGMA foreign_keys=ON`` per connection (SQLite ships with FKs OFF, which
would silently break our CASCADE delete paths) and a StaticPool for in-memory
URLs so every session in a test sees the same database.

``Base`` is the single metadata root for every subsystem (candidates now;
ledger and features later) so one Alembic environment migrates everything.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

_SQLITE_FILE_PREFIX = "sqlite:///"
_SQLITE_MEMORY_URLS = ("sqlite://", "sqlite:///:memory:")


class Base(DeclarativeBase):
    """Single metadata root shared by all subsystems."""


def _sqlite_fk_on(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in _SQLITE_MEMORY_URLS:
            kwargs["poolclass"] = StaticPool
        else:
            directory = os.path.dirname(url.removeprefix(_SQLITE_FILE_PREFIX))
            if directory:
                os.makedirs(directory, exist_ok=True)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listens_for(engine, "connect")(_sqlite_fk_on)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
```

In `app/core/config.py`, directly under the `contact_hash_salt` field (keep the `# --- Candidates (PI-1) ---` section), add:

```python
    # SQLAlchemy URL for the candidate store (S1.2). SQLite file locally; the
    # Postgres migration is this one string plus `alembic upgrade head`.
    candidates_db_url: str = "sqlite:///./data/veritas.db"
```

In `config.yaml`, under the `# --- Candidates (PI-1) ---` section after `contact_hash_salt`, add:

```yaml
# SQLAlchemy URL for the candidate store (S1.2; SQLAlchemy + Alembic).
# Postgres later = change this string and run `alembic upgrade head`.
candidates_db_url: "sqlite:///./data/veritas.db"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_db_core.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```powershell
git add requirements.txt app/core/db.py app/core/config.py config.yaml tests/test_db_core.py
git commit -m "feat(db): shared SQLAlchemy core (Base, engine, sessions) + candidates_db_url"
```

---

### Task 2: ORM models — `candidates` / `resumes` / `extractions`

**Files:**
- Create: `app/candidates/models.py`
- Test: `tests/test_candidate_models.py`

**Interfaces:**
- Consumes: `Base` from `app.core.db` (Task 1).
- Produces: `CandidateRow` (`id`, `email_hash`, `phone_hash`, `full_name`, `created_at`, `updated_at`, `resumes` rel), `ResumeRow` (`id`, `candidate_id`, `version`, `raw_text`, `text_sha256`, `created_at`, `candidate`/`extractions` rels, unique `(candidate_id, version)`), `ExtractionRow` (`id`, `resume_id`, `candidate_id`, `method`, `profile: JSON`, `warnings: JSON`, `created_at`). Also `_utcnow()` helper.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_models.py`:

```python
"""ORM table shapes: UUID PKs, FK cascades, version uniqueness, JSON round-trip."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.core.db import Base, make_engine, make_session_factory


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_tables_registered_on_shared_base():
    assert {"candidates", "resumes", "extractions"} <= set(Base.metadata.tables)


def test_candidate_gets_uuid_id_and_timestamps(session_factory):
    with session_factory() as s:
        cand = CandidateRow(full_name="Asha Rao")
        s.add(cand)
        s.commit()
        assert len(cand.id) == 36
        assert cand.created_at is not None
        assert cand.updated_at is not None


def test_resume_version_unique_per_candidate(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        s.add(ResumeRow(candidate_id=cand.id, version=1, raw_text="a", text_sha256="x" * 64))
        s.add(ResumeRow(candidate_id=cand.id, version=1, raw_text="b", text_sha256="y" * 64))
        with pytest.raises(IntegrityError):
            s.commit()


def test_extraction_profile_json_round_trips(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        resume = ResumeRow(candidate_id=cand.id, version=1, raw_text="r", text_sha256="z" * 64)
        s.add(resume)
        s.flush()
        s.add(
            ExtractionRow(
                resume_id=resume.id,
                candidate_id=cand.id,
                method="heuristic",
                profile={"id": "cand_x", "skills": [{"name": "python", "confidence": 0.7}]},
            )
        )
        s.commit()
    with session_factory() as s:
        row = s.query(ExtractionRow).one()
        assert row.profile["skills"][0]["name"] == "python"
        assert row.warnings == []


def test_deleting_candidate_cascades_to_resumes_and_extractions(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        resume = ResumeRow(candidate_id=cand.id, version=1, raw_text="r", text_sha256="z" * 64)
        s.add(resume)
        s.flush()
        s.add(ExtractionRow(resume_id=resume.id, candidate_id=cand.id, method="llm", profile={}))
        s.commit()
        s.delete(cand)
        s.commit()
        assert s.query(ResumeRow).count() == 0
        assert s.query(ExtractionRow).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidate_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.models'`.

- [ ] **Step 3: Implement `app/candidates/models.py`**

```python
"""ORM rows for the candidate store (S1.2). Postgres-shaped on SQLite.

``*Row`` naming keeps ORM classes distinct from the Pydantic contracts in
``app.candidates.schema``: the profile payload stays Pydantic's to validate,
SQL only stores it (JSON column). ``resumes.raw_text`` deliberately persists
the submitted resume — S1.1 SourceSpan offsets index into it, and the DPDP
delete paths in the store erase it on request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandidateRow(Base):
    """One human. Identity = salted email/phone hashes (S1.1 hashing module)."""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    phone_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    resumes: Mapped[list["ResumeRow"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )


class ResumeRow(Base):
    """One submitted resume text, versioned per candidate (1, 2, ...)."""

    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_resumes_candidate_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    candidate: Mapped[CandidateRow] = relationship(back_populates="resumes")
    extractions: Mapped[list["ExtractionRow"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", passive_deletes=True
    )


class ExtractionRow(Base):
    """One extractor run over one resume — full CandidateProfile as JSON."""

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(16))  # "llm" | "heuristic"
    profile: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    resume: Mapped[ResumeRow] = relationship(back_populates="extractions")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidate_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/models.py tests/test_candidate_models.py
git commit -m "feat(candidates): ORM rows for candidates/resumes/extractions (PG-shaped)"
```

---

### Task 3: Alembic scaffolding + initial migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_candidate_store.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Consumes: `Base` (Task 1), models module import side-effect (Task 2), `Settings.candidates_db_url` (Task 1).
- Produces: `alembic upgrade head` working against any URL; URL precedence: explicit `sqlalchemy.url` in the Config (tests/smoke set it) → `Settings.candidates_db_url`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_migrations.py`:

```python
"""Alembic: upgrade head builds the schema; migrated schema matches the models."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

import app.candidates.models  # noqa: F401 — populate Base.metadata
from app.core.db import Base, make_engine

ROOT = Path(__file__).resolve().parents[1]


def _migrated_engine(tmp_path):
    url = "sqlite:///" + (tmp_path / "mig.db").as_posix()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return make_engine(url)


def test_upgrade_head_creates_candidate_tables(tmp_path):
    engine = _migrated_engine(tmp_path)
    names = set(inspect(engine).get_table_names())
    assert {"candidates", "resumes", "extractions"} <= names


def test_migrated_schema_matches_orm_models(tmp_path):
    """Drift guard: migration and models must describe the same tables/columns."""
    engine = _migrated_engine(tmp_path)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    structural = [
        d
        for d in diff
        if (d[0] if isinstance(d, tuple) else d[0][0])
        in ("add_table", "remove_table", "add_column", "remove_column")
    ]
    assert structural == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_migrations.py -v`
Expected: FAIL — alembic.ini not found (`FileNotFoundError` / `CommandError: No config file`).

- [ ] **Step 3: Create the Alembic environment**

Create `alembic.ini` (repo root):

```ini
# Alembic config — schema migrations for the shared SQLAlchemy Base.
# The URL is injected at runtime: an explicit sqlalchemy.url (tests, smoke,
# CLI -x) wins; otherwise alembic/env.py falls back to Settings.candidates_db_url.

[alembic]
script_location = alembic
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `alembic/env.py`:

```python
"""Alembic environment — migrates the shared Base (all subsystems, one head).

URL precedence: sqlalchemy.url already set on the Config (tests/smoke set it
programmatically) > Settings.candidates_db_url. render_as_batch=True makes
future ALTERs work on SQLite; harmless on Postgres.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.candidates.models  # noqa: F401 — register tables on Base.metadata
from app.core.config import get_settings
from app.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().candidates_db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Create `alembic/versions/0001_candidate_store.py` (hand-written so the schema is exactly the models — index names follow SQLAlchemy's `ix_<table>_<column>` convention):

```python
"""candidate store: candidates, resumes, extractions

Revision ID: 0001_candidate_store
Revises:
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_candidate_store"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email_hash", sa.String(64), nullable=True),
        sa.Column("phone_hash", sa.String(64), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_candidates_email_hash", "candidates", ["email_hash"])
    op.create_index("ix_candidates_phone_hash", "candidates", ["phone_hash"])

    op.create_table(
        "resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("candidate_id", "version", name="uq_resumes_candidate_version"),
    )
    op.create_index("ix_resumes_candidate_id", "resumes", ["candidate_id"])
    op.create_index("ix_resumes_text_sha256", "resumes", ["text_sha256"])

    op.create_table(
        "extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extractions_resume_id", "extractions", ["resume_id"])
    op.create_index("ix_extractions_candidate_id", "extractions", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("extractions")
    op.drop_table("resumes")
    op.drop_table("candidates")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_migrations.py -v`
Expected: 2 passed. If `test_migrated_schema_matches_orm_models` reports a structural diff, the migration and models disagree — fix the migration (or model), do NOT loosen the test filter further.

- [ ] **Step 5: Commit**

```powershell
git add alembic.ini alembic/ tests/test_migrations.py
git commit -m "feat(db): alembic environment + initial candidate-store migration"
```

---

### Task 4: `CandidateStore.ingest` — identity resolution + resume versioning

**Files:**
- Create: `app/candidates/store.py`
- Test: `tests/test_candidate_store.py`

**Interfaces:**
- Consumes: models (Task 2), `make_engine`/`make_session_factory` (Task 1), `ExtractionResult`/`CandidateProfile` + `hashing.apply_contact_hashes` (existing S1.1).
- Produces: `CandidateStore(session_factory)` with `ingest(result: ExtractionResult, resume_text: str) -> IngestOutcome`; `IngestOutcome` pydantic model with fields `candidate_id: str`, `resume_id: str`, `extraction_id: str`, `resume_version: int`, `matched_existing: bool`, `matched_on: Optional[Literal["email_hash","phone_hash"]]`, `duplicate_resume: bool`. Task 5 extends this same class/file.

**Resolution policy (encode exactly):** match on `email_hash` first, then `phone_hash`; a match attaches the resume to that candidate and backfills any hash the candidate is missing; matching never merges two existing candidates. No hashes ⇒ always a new candidate. Same `text_sha256` for the same candidate ⇒ reuse the resume row (no new version) but still record a new extraction.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_candidate_store.py`:

```python
"""CandidateStore — ingest, identity resolution (email/phone hash), versioning."""

import pytest

from app.candidates import hashing
from app.candidates.schema import CandidateProfile, ExtractedStr, ExtractionResult
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory

SALT = "test-salt"


@pytest.fixture
def store() -> CandidateStore:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return CandidateStore(make_session_factory(engine))


def extraction(name=None, email=None, phone=None) -> ExtractionResult:
    profile = CandidateProfile()
    if name:
        profile.full_name = ExtractedStr(value=name)
    if email:
        profile.contact.email = ExtractedStr(value=email)
    if phone:
        profile.contact.phone = ExtractedStr(value=phone)
    hashing.apply_contact_hashes(profile, salt=SALT)
    return ExtractionResult(profile=profile, method="heuristic")


def test_ingest_new_candidate(store):
    out = store.ingest(extraction(name="Asha Rao", email="asha@example.com"), "resume one")
    assert out.matched_existing is False
    assert out.matched_on is None
    assert out.resume_version == 1
    assert out.duplicate_resume is False
    assert out.candidate_id and out.resume_id and out.extraction_id


def test_same_email_attaches_second_resume_version(store):
    first = store.ingest(extraction(email="asha@example.com"), "resume one")
    second = store.ingest(extraction(email="Asha@Example.com "), "resume two")
    assert second.candidate_id == first.candidate_id
    assert second.matched_existing is True
    assert second.matched_on == "email_hash"
    assert second.resume_version == 2


def test_phone_match_when_email_absent(store):
    first = store.ingest(extraction(email="asha@example.com", phone="+91 98765 43210"), "r1")
    second = store.ingest(extraction(phone="09876543210"), "r2")
    assert second.candidate_id == first.candidate_id
    assert second.matched_on == "phone_hash"


def test_email_match_takes_precedence_over_phone(store):
    store.ingest(extraction(email="a@example.com", phone="9876543210"), "ra")
    b = store.ingest(extraction(email="b@example.com"), "rb")
    hit = store.ingest(extraction(email="b@example.com", phone="9876543210"), "rc")
    assert hit.candidate_id == b.candidate_id
    assert hit.matched_on == "email_hash"


def test_no_contact_always_creates_new_candidate(store):
    a = store.ingest(extraction(name="Anon One"), "r1")
    b = store.ingest(extraction(name="Anon Two"), "r2")
    assert a.candidate_id != b.candidate_id


def test_identical_text_reuses_resume_but_records_new_extraction(store):
    first = store.ingest(extraction(email="asha@example.com"), "same text")
    again = store.ingest(extraction(email="asha@example.com"), "same text")
    assert again.duplicate_resume is True
    assert again.resume_id == first.resume_id
    assert again.resume_version == 1
    assert again.extraction_id != first.extraction_id


def test_missing_hash_backfilled_on_match(store):
    first = store.ingest(extraction(email="asha@example.com"), "r1")
    store.ingest(extraction(email="asha@example.com", phone="9876543210"), "r2")
    by_phone = store.ingest(extraction(phone="9876543210"), "r3")
    assert by_phone.candidate_id == first.candidate_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidate_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.candidates.store'`.

- [ ] **Step 3: Implement `app/candidates/store.py`**

```python
"""Candidate store — identity resolution, versioned resumes, extraction audit.

Identity resolution matches on the S1.1 salted contact hashes: email_hash
first, phone_hash second. A match attaches the new resume to that candidate
(and backfills any hash the candidate is missing); it NEVER merges two
existing candidates — that needs human judgment, not a heuristic. No hashes
at all ⇒ a new candidate every time (advisory system: never guess identity).

DPDP: delete_candidate / delete_resume (Task 5) are hard deletes that cascade
to resumes and extractions, erasing raw resume text on request.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow, _utcnow
from app.candidates.schema import CandidateProfile, ExtractionResult
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory

MatchedOn = Literal["email_hash", "phone_hash"]


class IngestOutcome(BaseModel):
    """What one ingest did: which candidate/resume/extraction, and why."""

    candidate_id: str
    resume_id: str
    extraction_id: str
    resume_version: int
    matched_existing: bool = False
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool = False


class CandidateStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def ingest(self, result: ExtractionResult, resume_text: str) -> IngestOutcome:
        sha = hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
        profile = result.profile
        with self._session_factory() as session:
            cand, matched_on = self._resolve_candidate(session, profile)
            matched = cand is not None
            if cand is None:
                cand = CandidateRow()
                session.add(cand)
            self._refresh_identity(cand, profile)
            session.flush()

            resume = (
                session.execute(
                    select(ResumeRow).where(
                        ResumeRow.candidate_id == cand.id,
                        ResumeRow.text_sha256 == sha,
                    )
                )
                .scalars()
                .first()
            )
            duplicate = resume is not None
            if resume is None:
                latest = session.execute(
                    select(func.max(ResumeRow.version)).where(
                        ResumeRow.candidate_id == cand.id
                    )
                ).scalar()
                resume = ResumeRow(
                    candidate_id=cand.id,
                    version=(latest or 0) + 1,
                    raw_text=resume_text,
                    text_sha256=sha,
                )
                session.add(resume)
                session.flush()

            extraction = ExtractionRow(
                resume_id=resume.id,
                candidate_id=cand.id,
                method=result.method,
                profile=profile.model_dump(mode="json"),
                warnings=list(result.warnings),
            )
            session.add(extraction)
            session.commit()
            return IngestOutcome(
                candidate_id=cand.id,
                resume_id=resume.id,
                extraction_id=extraction.id,
                resume_version=resume.version,
                matched_existing=matched,
                matched_on=matched_on,
                duplicate_resume=duplicate,
            )

    @staticmethod
    def _resolve_candidate(
        session: Session, profile: CandidateProfile
    ) -> tuple[Optional[CandidateRow], Optional[MatchedOn]]:
        contact = profile.contact
        if contact.email_hash:
            row = (
                session.execute(
                    select(CandidateRow).where(CandidateRow.email_hash == contact.email_hash)
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row, "email_hash"
        if contact.phone_hash:
            row = (
                session.execute(
                    select(CandidateRow).where(CandidateRow.phone_hash == contact.phone_hash)
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row, "phone_hash"
        return None, None

    @staticmethod
    def _refresh_identity(cand: CandidateRow, profile: CandidateProfile) -> None:
        """Backfill hashes this resume adds; latest non-empty name wins."""
        contact = profile.contact
        if contact.email_hash and not cand.email_hash:
            cand.email_hash = contact.email_hash
        if contact.phone_hash and not cand.phone_hash:
            cand.phone_hash = contact.phone_hash
        if profile.full_name and profile.full_name.value:
            cand.full_name = profile.full_name.value
        cand.updated_at = _utcnow()
```

(`datetime`, `Settings`, `get_settings`, `make_engine`, `make_session_factory` imports are used by Task 5 — leave them even if this task's linting flags them, or add them in Task 5 if you prefer a clean intermediate state.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidate_store.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/store.py tests/test_candidate_store.py
git commit -m "feat(candidates): CandidateStore.ingest with hash-based identity resolution"
```

---

### Task 5: Store reads + DPDP delete paths + builder

**Files:**
- Modify: `app/candidates/store.py` (extend `CandidateStore`; add summary models + builder)
- Test: `tests/test_candidate_store.py` (append)

**Interfaces:**
- Consumes: Task 4's `CandidateStore` + `IngestOutcome`.
- Produces: `CandidateSummary` (`id`, `full_name`, `email_hash`, `phone_hash`, `created_at`, `updated_at`, `resume_count`), `ResumeSummary` (`id`, `version`, `text_sha256`, `created_at`), and methods `get_candidate(candidate_id) -> Optional[CandidateSummary]`, `latest_profile(candidate_id) -> Optional[CandidateProfile]`, `list_resumes(candidate_id) -> list[ResumeSummary]`, `delete_candidate(candidate_id) -> bool`, `delete_resume(resume_id) -> bool`, `build_candidate_store(settings: Optional[Settings]) -> CandidateStore`. S1.3 wires the builder into `Services`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidate_store.py`:

```python
def test_get_candidate_summary(store):
    out = store.ingest(extraction(name="Asha Rao", email="asha@example.com"), "r1")
    store.ingest(extraction(name="Asha R. Rao", email="asha@example.com"), "r2")
    summary = store.get_candidate(out.candidate_id)
    assert summary is not None
    assert summary.full_name == "Asha R. Rao"  # latest resume's name wins
    assert summary.resume_count == 2
    assert summary.email_hash
    assert store.get_candidate("missing-id") is None


def test_latest_profile_comes_from_newest_resume_version(store):
    out = store.ingest(extraction(name="Asha Rao", email="asha@example.com"), "r1")
    store.ingest(extraction(name="Asha R. Rao", email="asha@example.com"), "r2")
    profile = store.latest_profile(out.candidate_id)
    assert profile is not None
    assert profile.full_name.value == "Asha R. Rao"
    assert store.latest_profile("missing-id") is None


def test_list_resumes_ordered_by_version(store):
    out = store.ingest(extraction(email="a@x.com"), "r1")
    store.ingest(extraction(email="a@x.com"), "r2")
    resumes = store.list_resumes(out.candidate_id)
    assert [r.version for r in resumes] == [1, 2]
    assert all(len(r.text_sha256) == 64 for r in resumes)


def test_delete_candidate_erases_everything(store):
    out = store.ingest(extraction(email="a@x.com"), "r1")
    assert store.delete_candidate(out.candidate_id) is True
    assert store.get_candidate(out.candidate_id) is None
    assert store.list_resumes(out.candidate_id) == []
    assert store.delete_candidate(out.candidate_id) is False


def test_delete_resume_keeps_candidate(store):
    out = store.ingest(extraction(email="a@x.com"), "r1")
    second = store.ingest(extraction(email="a@x.com"), "r2")
    assert store.delete_resume(second.resume_id) is True
    assert [r.version for r in store.list_resumes(out.candidate_id)] == [1]
    assert store.get_candidate(out.candidate_id) is not None
    assert store.delete_resume(second.resume_id) is False


def test_build_candidate_store_from_settings(settings):
    from app.candidates.store import build_candidate_store

    store = build_candidate_store(settings.model_copy(update={"candidates_db_url": "sqlite://"}))
    assert isinstance(store, CandidateStore)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidate_store.py -v`
Expected: 7 pass (Task 4), 6 FAIL with `AttributeError: 'CandidateStore' object has no attribute 'get_candidate'` (and similar / ImportError for the builder).

- [ ] **Step 3: Implement reads, deletes, and builder in `app/candidates/store.py`**

Add after `IngestOutcome`:

```python
class ResumeSummary(BaseModel):
    id: str
    version: int
    text_sha256: str
    created_at: datetime


class CandidateSummary(BaseModel):
    id: str
    full_name: Optional[str] = None
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resume_count: int = 0
```

Add these methods to `CandidateStore`:

```python
    def get_candidate(self, candidate_id: str) -> Optional[CandidateSummary]:
        with self._session_factory() as session:
            cand = session.get(CandidateRow, candidate_id)
            if cand is None:
                return None
            return CandidateSummary(
                id=cand.id,
                full_name=cand.full_name,
                email_hash=cand.email_hash,
                phone_hash=cand.phone_hash,
                created_at=cand.created_at,
                updated_at=cand.updated_at,
                resume_count=len(cand.resumes),
            )

    def latest_profile(self, candidate_id: str) -> Optional[CandidateProfile]:
        """Profile from the newest resume version (ties: newest extraction)."""
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(ExtractionRow)
                    .join(ResumeRow, ExtractionRow.resume_id == ResumeRow.id)
                    .where(ExtractionRow.candidate_id == candidate_id)
                    .order_by(ResumeRow.version.desc(), ExtractionRow.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            return CandidateProfile.model_validate(row.profile) if row else None

    def list_resumes(self, candidate_id: str) -> list[ResumeSummary]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ResumeRow)
                    .where(ResumeRow.candidate_id == candidate_id)
                    .order_by(ResumeRow.version)
                )
                .scalars()
                .all()
            )
            return [
                ResumeSummary(
                    id=r.id,
                    version=r.version,
                    text_sha256=r.text_sha256,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def delete_candidate(self, candidate_id: str) -> bool:
        """DPDP erasure: candidate + all resumes (raw text) + extractions."""
        with self._session_factory() as session:
            cand = session.get(CandidateRow, candidate_id)
            if cand is None:
                return False
            session.delete(cand)
            session.commit()
            return True

    def delete_resume(self, resume_id: str) -> bool:
        """DPDP erasure of ONE resume version + its extractions; candidate stays."""
        with self._session_factory() as session:
            resume = session.get(ResumeRow, resume_id)
            if resume is None:
                return False
            session.delete(resume)
            session.commit()
            return True
```

Add at module bottom:

```python
def build_candidate_store(settings: Optional[Settings] = None) -> CandidateStore:
    """Store on the configured URL. Schema is Alembic's job (`alembic upgrade
    head`), NOT the builder's — no create_all here by design."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return CandidateStore(make_session_factory(engine))
```

- [ ] **Step 4: Run the full suite**

Run: `.resume\Scripts\python.exe -m pytest -q`
Expected: all pass (88 pre-existing + 5 db-core + 5 models + 2 migrations + 13 store = 113 total, 0 failures).

- [ ] **Step 5: Commit**

```powershell
git add app/candidates/store.py tests/test_candidate_store.py
git commit -m "feat(candidates): store reads + DPDP delete paths + settings builder"
```

---

### Task 6: Smoke script + roadmap close-out

**Files:**
- Create: `scripts/smoke_s12.py`
- Modify: `docs/ROADMAP.md` (current state, status board `[~]`→`[x]` for S1.2, session log)

**Interfaces:**
- Consumes: everything above + existing `extract_profile(resume_text, *, llm, settings)` and `build_llm(settings)`; fixture `tests/fixtures/full_profile_resume.txt`.
- Produces: `python scripts/smoke_s12.py` exiting 0 with `SMOKE OK` (works with and without an API key).

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s12.py`:

```python
"""S1.2 smoke: migrate a scratch DB with Alembic, then run the real flow —
extract → ingest → dedup/versioning → latest_profile → DPDP delete.

With no API key this exercises the heuristic extractor; with a key, the LLM
path. Both must land in the store identically. Run from the repo root:
    python scripts/smoke_s12.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.services.llm import build_llm

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "smoke_s12.db"
    url = "sqlite:///" + db_path.as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    settings = get_settings()
    store = CandidateStore(make_session_factory(make_engine(url)))
    llm = build_llm(settings)

    text = FIXTURE.read_text(encoding="utf-8")
    result = asyncio.run(extract_profile(text, llm=llm, settings=settings))
    first = store.ingest(result, text)
    print(
        f"ingest #1 [{result.method}]: candidate={first.candidate_id[:8]}"
        f" v{first.resume_version} matched={first.matched_existing}"
    )

    second = store.ingest(result, text + "\n\nUpdate: AWS certification added.")
    print(
        f"ingest #2 (updated text): matched={second.matched_existing}"
        f" on={second.matched_on} v{second.resume_version}"
    )

    dup = store.ingest(result, text)
    print(f"ingest #3 (same text as #1): duplicate_resume={dup.duplicate_resume}")

    profile = store.latest_profile(first.candidate_id)
    resumes = store.list_resumes(first.candidate_id)
    deleted = store.delete_candidate(first.candidate_id)
    gone = store.get_candidate(first.candidate_id) is None

    checks = {
        "identity matched on re-ingest": second.matched_existing
        and second.matched_on == "email_hash",
        "second resume is version 2": second.resume_version == 2,
        "identical text deduplicated": dup.duplicate_resume and dup.resume_version == 1,
        "latest profile readable": profile is not None,
        "two resume versions listed": [r.version for r in resumes] == [1, 2],
        "DPDP delete erases candidate": deleted and gone,
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

Note: the identity-match checks require the fixture resume to contain an email the extractor lifts (it does — `smoke_s11.py` prints its `email_hash`). If ingest #2 fails to match, that is a real regression to investigate, not a smoke-script bug.

- [ ] **Step 2: Run the smoke offline (deterministic floor)**

Run (PowerShell, repo root):

```powershell
$env:DEE_OPENROUTER_API_KEY = ""; .resume\Scripts\python.exe scripts/smoke_s12.py
```

Expected: `method=heuristic` ingest line, all checks `OK`, exit 0 with `SMOKE OK`.

- [ ] **Step 3: Run the smoke live (if a key is configured in .env)**

Run: `.resume\Scripts\python.exe scripts/smoke_s12.py`
Expected: `[llm]` (or `[heuristic]` if no key present) and `SMOKE OK`. Key-less environments may skip this step.

- [ ] **Step 4: Full suite one last time**

Run: `.resume\Scripts\python.exe -m pytest -q`
Expected: 113 passed, 0 failed.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: `[~] S1.2` → `[x] S1.2`, `[ ] S1.3` → `[~] S1.3`.
- "Current state": current sprint → S1.3 (API + engine wiring); next action → write S1.3 plan (POST /candidates upload → extract → store → auto depth-eval, reports linked to candidate_id, wire `build_candidate_store` into `Services`); last-session line summarizing S1.2.
- Session log: append a dated S1.2 entry (branch, files, test count, smoke result).

- [ ] **Step 6: Commit**

```powershell
git add scripts/smoke_s12.py docs/ROADMAP.md
git commit -m "chore: S1.2 smoke script + roadmap close-out"
```

---

## Execution notes

- Run everything from the repo root; the venv is `.resume\Scripts\python.exe` (Windows).
- If `pip install` is slow/flaky under OneDrive, retry once; sqlalchemy + alembic are pure-python wheels.
- Merge flow (matches S1.1): after all tasks green, merge `s12-candidate-store` into `main` per superpowers:finishing-a-development-branch.
