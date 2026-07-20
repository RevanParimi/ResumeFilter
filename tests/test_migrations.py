"""Alembic: upgrade head builds the schema; migrated schema matches the models."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
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
    assert {"candidates", "resumes", "extractions", "resume_fingerprints"} <= names
    assert {
        "organizations",
        "consent_grants",
        "interview_records",
        "evaluation_events",
        "audit_log",
    } <= names


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
