"""Alembic: upgrade head builds the schema; migrated schema matches the models."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
import app.features.models  # noqa: F401 — populate Base.metadata
import app.matching.models  # noqa: F401 — populate Base.metadata
import app.profile_sources.models  # noqa: F401 — populate Base.metadata
import app.curation.models  # noqa: F401 — populate Base.metadata
import app.verification.models  # noqa: F401 — populate Base.metadata
import app.interview.models  # noqa: F401 — populate Base.metadata
import app.reports.models  # noqa: F401 — populate Base.metadata
from app.core.db import Base, make_engine

ROOT = Path(__file__).resolve().parents[1]


def _scratch_config(tmp_path, name="mig.db"):
    """A throwaway DB URL plus the alembic Config pointed at it. Separate from
    _migrated_engine so a test can stop at an intermediate revision."""
    url = "sqlite:///" + (tmp_path / name).as_posix()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return url, cfg


def _migrated_engine(tmp_path):
    url, cfg = _scratch_config(tmp_path)
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
        "coding_round_results",
        "observed_offers",
    } <= names
    assert "ml_feature_vectors" in names  # S4.2 migration 0007
    assert "job_requisitions" in names  # S5.1 migration 0008
    assert "observed_offers" in names  # S5.2 migration 0009
    assert "profile_sources" in names  # S6.1 migration 0010
    assert "unmapped_terms" in names  # S6.3 migration 0011
    assert "candidate_credentials" in names  # S6.4 migration 0012
    assert "verifications" in names  # S7.1 migration 0013
    assert "verification_challenges" in names  # S7.1 migration 0013
    assert "interview_sessions" in names  # S7.3 migration 0015
    assert "reports" in names  # S8.1 migration 0016
    assert "outcomes" in names  # S8.1 migration 0016
    org_cols = {c["name"] for c in inspect(engine).get_columns("organizations")}
    assert "reliability_weight" in org_cols  # S3.4 migration 0006


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
    "evaluation_events", "audit_log", "coding_round_results", "observed_offers",
)

FEATURE_TABLES = ("ml_feature_vectors",)  # S4.2

MATCHING_TABLES = ("job_requisitions",)  # S5.1

PROFILE_SOURCE_TABLES = ("profile_sources",)  # S6.1

CURATION_TABLES = ("unmapped_terms",)  # S6.3 — candidate-agnostic (no FK)

CANDIDATE_AUTH_TABLES = ("candidate_credentials",)  # S6.4 — candidate CASCADE

VERIFICATION_TABLES = ("verifications", "verification_challenges")  # S7.1 — CASCADE

REPORT_TABLES = ("reports", "outcomes")  # S8.1 — reports CASCADE from candidates


def test_migrated_indexes_match_orm(tmp_path):
    """Every index the ORM declares on a ledger table exists in the migrated
    schema (name + column set + uniqueness)."""
    engine = _migrated_engine(tmp_path)
    insp = inspect(engine)
    for table in LEDGER_TABLES + FEATURE_TABLES + MATCHING_TABLES + PROFILE_SOURCE_TABLES + CURATION_TABLES + CANDIDATE_AUTH_TABLES + VERIFICATION_TABLES + REPORT_TABLES:
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


def test_0014_backfills_existing_verifications_to_identity(tmp_path):
    """A pre-S7.2 row is an identity verification by definition -- it predates
    the existence of any other subject, so the backfill is not a guess."""
    import sqlalchemy as sa

    url, cfg = _scratch_config(tmp_path, "backfill.db")
    command.upgrade(cfg, "0013_identity_verification")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO candidates (id, full_name, created_at, updated_at) "
            "VALUES ('c1', 'A', '2026-01-01', '2026-01-01')"))
        conn.execute(sa.text(
            "INSERT INTO verifications (id, candidate_id, method, assurance_level,"
            " status, details, requested_at, created_at) VALUES "
            "('v1', 'c1', 'self_attested', 1, 'verified', '{}', "
            "'2026-01-01', '2026-01-01')"))

    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        row = conn.execute(sa.text(
            "SELECT subject, claim_ref FROM verifications")).one()
    assert row.subject == "identity"
    assert row.claim_ref is None


def test_0014_leaves_no_server_default_behind_on_subject(tmp_path):
    """The default exists for the backfill only; the application stays the
    source of truth for new rows (the 0004 precedent)."""
    from sqlalchemy import inspect as sa_inspect

    engine = _migrated_engine(tmp_path)
    col = {c["name"]: c for c in sa_inspect(engine).get_columns("verifications")}["subject"]
    assert col["default"] is None
    assert col["nullable"] is False


def test_migrated_fks_and_nullability_match_orm(tmp_path):
    """FK ondelete and column nullability agree between migration and models —
    the DPDP CASCADE contract must survive on the real migrated schema."""
    engine = _migrated_engine(tmp_path)
    insp = inspect(engine)
    for table in LEDGER_TABLES + FEATURE_TABLES + MATCHING_TABLES + PROFILE_SOURCE_TABLES + CURATION_TABLES + CANDIDATE_AUTH_TABLES + VERIFICATION_TABLES + REPORT_TABLES:
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
