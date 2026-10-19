"""Owned curation schema on migrated disposable SQLite/PostgreSQL databases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
from threading import Event
from time import monotonic
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DataError, IntegrityError

from app.core.db import Base, make_engine, make_session_factory
from app.curation.store import CurationStore

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
PREVIOUS = "0027_login_issuances"


@pytest.fixture(params=["sqlite", "postgresql"])
def migrated(request, tmp_path):
    bootstrap = None
    if request.param == "postgresql":
        raw = os.environ.get("DEE_TEST_DB_URL", "")
        if not raw:
            pytest.skip("Disposable PostgreSQL DEE_TEST_DB_URL not configured")
        bootstrap = make_engine(raw)
        schema = "curation_" + uuid.uuid4().hex
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(raw).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + (tmp_path / "curation.db").as_posix()
    engine = make_engine(url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    try:
        command.upgrade(cfg, "head")
        yield engine, cfg
    finally:
        engine.dispose()
        if bootstrap is not None:
            with bootstrap.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            bootstrap.dispose()


def tables(engine):
    names = set(inspect(engine).get_table_names())
    assert {"curation_observations", "curation_aliases"} <= names, "owned curation storage missing"
    metadata = MetaData()
    return {name: Table(name, metadata, autoload_with=engine) for name in
            ("candidates", "profile_sources", "curation_observations", "curation_aliases", "unmapped_terms")}


def seed(engine, t):
    with engine.begin() as conn:
        for cid in ("a", "b"):
            conn.execute(t["candidates"].insert().values(id=cid, created_at=NOW, updated_at=NOW))
            conn.execute(t["profile_sources"].insert().values(id="source-" + cid,
                candidate_id=cid, source_type="linkedin", identifier="synthetic",
                signal={}, method="parsed", fetched_at=NOW, created_at=NOW))


def observation(oid="obs-a", source="source-a", name="Cobol!", at=NOW):
    return dict(id=oid, source_id=source, norm_key="cobol", display_name=name, created_at=at)


def alias(**updates):
    return dict(norm_key="approved cobol", alias="Approved COBOL", canonical="cobol",
                category="language", action="create", decided_at=NOW, **updates)


@pytest.mark.parametrize("target", ["candidates", "profile_sources"])
def test_owned_rows_cascade_without_losing_survivor_or_approved_alias(migrated, target):
    engine, _ = migrated
    t = tables(engine)
    seed(engine, t)
    with engine.begin() as conn:
        conn.execute(t["curation_observations"].insert(), [observation(),
            observation("obs-b", "source-b", "COBOL", NOW + timedelta(days=1))])
        conn.execute(t["curation_aliases"].insert().values(**alias()))
        conn.execute(t[target].delete().where(t[target].c.id == ("a" if target == "candidates" else "source-a")))
    with engine.connect() as conn:
        rows = conn.execute(select(t["curation_observations"])).mappings().all()
        assert [(r["id"], r["display_name"]) for r in rows] == [("obs-b", "COBOL")]
        assert conn.scalar(select(t["curation_aliases"].c.alias)) == "Approved COBOL"
        assert conn.scalar(select(t["candidates"].c.id).where(t["candidates"].c.id == "b")) == "b"


def test_same_key_observations_preserve_independent_forms_and_times(migrated):
    engine, _ = migrated
    t = tables(engine)
    seed(engine, t)
    original = observation()
    with engine.begin() as conn:
        conn.execute(t["curation_observations"].insert().values(**original))
    with engine.connect() as conn:
        before = conn.execute(select(t["curation_observations"])).mappings().one()
    with engine.begin() as conn:
        conn.execute(t["curation_observations"].insert(), [
            observation("repeat", at=NOW + timedelta(days=29)),
            observation("other", "source-b", "COBOL", NOW + timedelta(days=2))])
    with engine.connect() as conn:
        rows = {r["id"]: r for r in conn.execute(select(t["curation_observations"])).mappings()}
    assert rows["obs-a"] == before
    assert len(rows) == 3
    assert rows["other"]["display_name"] == "COBOL"


@pytest.mark.parametrize("overrides,reason", [
    ({"source_id": "missing"}, "foreign key"),
    ({"source_id": None}, "not.null"),
    ({"display_name": "x" * 129}, "check constraint"),
    ({"norm_key": "x" * 129}, "check constraint"),
    ({"created_at": None}, "not.null"),
])
def test_invalid_observation_refused(migrated, overrides, reason):
    engine, _ = migrated
    t = tables(engine)
    seed(engine, t)
    values = observation() | overrides
    # PostgreSQL varchar length checks can precede the explicit CHECK.
    with pytest.raises((IntegrityError, DataError)) as exc:
        with engine.begin() as conn:
            conn.execute(t["curation_observations"].insert().values(**values))
    message = str(exc.value).lower()
    assert re.search(reason, message) or (reason == "check constraint" and "value too long" in message)
    with engine.connect() as conn:
        assert conn.execute(select(t["curation_observations"])).all() == []


def test_alias_requires_explicit_vocabulary_and_unique_key(migrated):
    engine, _ = migrated
    t = tables(engine)
    with engine.begin() as conn:
        conn.execute(t["curation_aliases"].insert().values(**alias()))
    for update in ({}, {"norm_key": "second", "alias": None},
                   {"norm_key": "second", "canonical": None},
                   {"norm_key": "second", "category": None},
                   {"norm_key": "second", "action": "ignore"},
                   {"norm_key": "second", "admin_user_id": "invented"}):
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(t["curation_aliases"].insert().values(**(alias() | update)))
    assert "note" not in t["curation_aliases"].c
    assert "decided_by" not in t["curation_aliases"].c


def test_approved_vocabulary_survives_operator_deletion(migrated):
    engine, _ = migrated
    t = tables(engine)
    admin = Table("admin_users", MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        conn.execute(admin.insert().values(id="operator", email_hash="synthetic-hash", label="", created_at=NOW))
        conn.execute(t["curation_aliases"].insert().values(**alias(admin_user_id="operator")))
        conn.execute(admin.delete().where(admin.c.id == "operator"))
    with engine.connect() as conn:
        row = conn.execute(select(t["curation_aliases"])).mappings().one()
    assert row["alias"] == "Approved COBOL"
    assert row["admin_user_id"] is None


def test_schema_constraints_and_legacy_writer_default_match_models(migrated):
    engine, _ = migrated
    t = tables(engine)
    inspector = inspect(engine)
    for name in ("curation_observations", "curation_aliases"):
        model = Base.metadata.tables[name]
        actual = inspector.get_check_constraints(name)
        assert {c["name"] for c in actual} == {
            c.name for c in model.constraints if c.__class__.__name__ == "CheckConstraint"}
        assert {c["name"]: c["nullable"] for c in inspector.get_columns(name)} == {
            c.name: c.nullable for c in model.columns}
        assert {(tuple(f["constrained_columns"]), f["referred_table"],
                 tuple(f["referred_columns"]), f.get("options", {}).get("ondelete"))
                for f in inspector.get_foreign_keys(name)} == {
            (tuple(c.name for c in f.columns), f.referred_table.name,
             tuple(e.column.name for e in f.elements), f.ondelete) for f in model.foreign_key_constraints}
        assert {i["name"]: (tuple(i["column_names"]), bool(i["unique"]))
                for i in inspector.get_indexes(name)} == {
            i.name: (tuple(c.name for c in i.columns), bool(i.unique)) for i in model.indexes}
    from tests.curation_helpers import legacy_term
    legacy_term(make_session_factory(engine))  # older-version insert, server classifies it
    with engine.connect() as conn:
        assert conn.scalar(select(t["unmapped_terms"].c.provenance)) == "legacy_unattributed"


def test_unicode_boundary_and_rollback_cannot_leave_detached_observation(migrated):
    engine, _ = migrated
    t = tables(engine)
    seed(engine, t)
    with engine.begin() as conn:
        conn.execute(t["curation_observations"].insert().values(**observation(name="\U0001f9ea" * 128)))
    with engine.connect() as conn:
        transaction = conn.begin()
        conn.execute(t["profile_sources"].insert().values(id="uncommitted-source",
            candidate_id="a", source_type="github", identifier="synthetic", signal={},
            method="parsed", fetched_at=NOW, created_at=NOW))
        conn.execute(t["curation_observations"].insert().values(
            **observation("rolled-back", "uncommitted-source")))
        transaction.rollback()
    with engine.connect() as conn:
        rows = conn.execute(select(t["curation_observations"])).mappings().all()
    assert len(rows) == 1
    assert rows[0]["display_name"] == "\U0001f9ea" * 128


def test_legacy_preserved_without_fabricated_ownership_and_roundtrip(migrated):
    engine, cfg = migrated
    command.downgrade(cfg, PREVIOUS)
    old = Table("unmapped_terms", MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        for status in ("pending", "ignored", "resolved"):
            conn.execute(old.insert().values(id=status, norm_key=status, display_name="Synthetic private " + status,
                source_types=["linkedin"], occurrences=3, first_seen=NOW, last_seen=NOW,
                status=status, action="map" if status == "resolved" else None,
                canonical="python" if status == "resolved" else None,
                category="language" if status == "resolved" else None,
                note="Synthetic private note", decided_by="Synthetic supplied name", created_at=NOW))
        before = conn.execute(select(old).order_by(old.c.id)).mappings().all()
    for _ in range(2):
        command.upgrade(cfg, "head")
        t = tables(engine)
        with engine.connect() as conn:
            rows = conn.execute(select(t["unmapped_terms"]).order_by(t["unmapped_terms"].c.id)).mappings().all()
            assert [r["provenance"] for r in rows] == ["legacy_unattributed"] * 3
            assert [{k: r[k] for k in old.c.keys()} for r in rows] == before
            assert conn.execute(select(t["curation_observations"])).all() == []
            assert conn.execute(select(t["curation_aliases"])).all() == []
        overlay = CurationStore(make_session_factory(engine)).load_overlay()
        assert overlay["resolved"].canonical == "python"
        command.downgrade(cfg, PREVIOUS)
        assert "curation_observations" not in inspect(engine).get_table_names()
        with engine.connect() as conn:
            assert conn.execute(select(old).order_by(old.c.id)).mappings().all() == before
    command.upgrade(cfg, "head")


@pytest.mark.parametrize("target", ["candidates", "profile_sources"])
@pytest.mark.parametrize("first", ["insert", "delete"])
def test_postgres_competing_insert_and_delete_cannot_leave_orphan(migrated, target, first):
    engine, _ = migrated
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL lock ordering")
    t = tables(engine)
    seed(engine, t)
    remove = t[target].delete().where(t[target].c.id == ("a" if target == "candidates" else "source-a"))
    insert = t["curation_observations"].insert().values(**observation())
    ready, pids = Event(), []

    def compete(statement):
        with engine.begin() as conn:
            pids.append(conn.scalar(text("SELECT pg_backend_pid()")))
            ready.set()
            conn.execute(statement)

    with engine.connect() as conn, ThreadPoolExecutor(max_workers=1) as pool:
        transaction = conn.begin()
        try:
            conn.execute(insert if first == "insert" else remove)
            pending = pool.submit(compete, remove if first == "insert" else insert)
            assert ready.wait(10)
            deadline = monotonic() + 10
            with engine.connect() as observer:
                while monotonic() < deadline:
                    if observer.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pids[0]}):
                        break
                else:
                    pytest.fail("competing operation never blocked on the owning transaction")
            assert not pending.done()
            transaction.commit()
            if first == "delete":
                with pytest.raises(IntegrityError, match="foreign key"):
                    pending.result(timeout=10)
            else:
                pending.result(timeout=10)
        finally:
            if transaction.is_active:
                transaction.rollback()
    with engine.connect() as conn:
        assert conn.execute(select(t["curation_observations"])).all() == []
        assert conn.scalar(select(t["profile_sources"].c.id).where(t["profile_sources"].c.id == "source-b")) == "source-b"
