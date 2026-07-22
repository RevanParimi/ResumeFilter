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
