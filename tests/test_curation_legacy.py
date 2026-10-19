"""Legacy disposition on synthetic migrated SQLite/PostgreSQL stores."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.curation import legacy
from app.core.db import make_session_factory
from app.curation.store import CurationStore
from tests.test_curation_storage_migration import migrated, tables, NOW, seed, alias, observation

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dispose_legacy_curation.py"
APPROVE = dict(id="resolved", action="map", alias="Approved legacy vocabulary",
               canonical="python", category="language")


def run_cli(engine, tmp_path, *, selection=None, apply=False, payload=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEE_")}
    env["PYTHONPATH"] = str(ROOT / "src")
    if engine.dialect.name == "sqlite":
        args = ["--database", engine.url.database]
    else:
        env["SYNTHETIC_DISPOSITION_DB"] = engine.url.render_as_string(hide_password=False)
        args = ["--database-url-env", "SYNTHETIC_DISPOSITION_DB"]
    if selection is not None or payload is not None:
        path = tmp_path / "selection.json"
        path.write_text(payload if payload is not None else json.dumps(selection), encoding="utf-8")
        args += ["--selection", str(path)]
    if apply:
        args.append("--apply")
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, cwd=tmp_path,
        capture_output=True, text=True, timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def legacy_rows(engine):
    t = tables(engine)
    with engine.begin() as conn:
        for status in ("pending", "ignored", "resolved"):
            conn.execute(t["unmapped_terms"].insert().values(
                id=status, norm_key=status, display_name="Synthetic PRIVATE name",
                source_types=["github"], occurrences=3, first_seen=NOW, last_seen=NOW,
                status=status, canonical="python" if status == "resolved" else None,
                category="language" if status == "resolved" else None,
                note="Synthetic PRIVATE note", decided_by="Synthetic PRIVATE identity",
                created_at=NOW))
    return t


def test_counts_only_inventory_preserves_every_legacy_field(migrated):
    engine, _ = migrated
    t = legacy_rows(engine)
    with engine.connect() as conn:
        before = conn.execute(select(t["unmapped_terms"])).mappings().all()
        assert legacy.inventory(conn) == dict(total=3, pending=1, ignored=1, resolved=1, other=0)
        assert conn.execute(select(t["unmapped_terms"])).mappings().all() == before


def test_selected_disposition_removes_only_selected_legacy_row(migrated):
    engine, _ = migrated
    t = legacy_rows(engine)
    with engine.begin() as conn:
        result = legacy.dispose(conn, [{"id": "pending", "action": "remove"}], apply=True)
        assert result == dict(selected=1, matched=1, absent=0, removed=1, approved=0)
    with engine.connect() as conn:
        assert set(conn.scalars(select(t["unmapped_terms"].c.id))) == {"ignored", "resolved"}


def test_explicit_approval_deletes_all_legacy_text_preserves_owned_and_unselected(migrated):
    engine, _ = migrated
    t = legacy_rows(engine)
    seed(engine, t)
    with engine.begin() as conn:
        conn.execute(t["curation_aliases"].insert().values(**alias()))
        conn.execute(t["curation_observations"].insert().values(**observation(at=datetime.now(timezone.utc))))
        survivors = {name: conn.execute(select(t[name])).mappings().all() for name in
                     ("curation_aliases", "curation_observations", "candidates", "profile_sources")}
        result = legacy.dispose(conn, [APPROVE, dict(id="ignored", action="remove")], apply=True)
    assert result == dict(selected=2, matched=2, absent=0, removed=2, approved=1)
    store = CurationStore(make_session_factory(engine))
    assert store.load_owned_overlay()["approved legacy vocabulary"].canonical == "python"
    assert "resolved" not in store.load_owned_overlay()
    assert len(store.list_observations()[0]) == 1
    with engine.connect() as conn:
        assert set(conn.scalars(select(t["unmapped_terms"].c.id))) == {"pending"}
        approved = conn.execute(select(t["curation_aliases"]).where(
            t["curation_aliases"].c.norm_key == "approved legacy vocabulary")).mappings().one()
        assert approved["admin_user_id"] is None and approved["action"] == "map"
        assert "PRIVATE" not in str(approved)
        for name, before in survivors.items():
            remaining = conn.execute(select(t[name])).mappings().all()
            assert all(row in remaining for row in before)
    with engine.begin() as conn:
        again = legacy.dispose(conn, [APPROVE, dict(id="ignored", action="remove")], apply=True)
    assert again == dict(selected=2, matched=0, absent=2, removed=0, approved=0)


@pytest.mark.parametrize("existing", ["owned", "legacy"])
@pytest.mark.parametrize("apply", [False, True])
def test_conflict_refuses_entire_batch_preserving_raw_and_approved(migrated, existing, apply):
    engine, _ = migrated
    t = legacy_rows(engine)
    with engine.begin() as conn:
        if existing == "owned":
            conn.execute(t["curation_aliases"].insert().values(**alias()))
            key = "Approved COBOL"
        else:
            key = "resolved"
        before = conn.execute(select(t["unmapped_terms"])).mappings().all()
    with pytest.raises(legacy.LegacyDispositionError, match="conflicts"):
        with engine.begin() as conn:
            legacy.dispose(conn, [dict(APPROVE, id="pending", alias=key),
                                  dict(id="ignored", action="remove")], apply=apply)
    with engine.connect() as conn:
        assert conn.execute(select(t["unmapped_terms"])).mappings().all() == before


def test_same_reviewed_alias_and_new_domain_vocabulary_are_explicit_choices(migrated):
    engine, _ = migrated
    t = legacy_rows(engine)
    with engine.begin() as conn:
        legacy.dispose(conn, [dict(APPROVE, alias="resolved"),
            dict(id="pending", action="create", alias="Marine craft skill",
                 canonical="marine_craft", category="analytics")], apply=True)
    overlay = CurationStore(make_session_factory(engine)).load_owned_overlay()
    assert overlay["resolved"].canonical == "python"
    assert overlay["marine craft skill"].canonical == "marine_craft"


@pytest.mark.parametrize("entries", [[], [{}], [dict(APPROVE, note="PRIVATE")],
    [dict(APPROVE, admin_user_id="PRIVATE")], [dict(APPROVE, alias="x" * 129)],
    [dict(APPROVE, alias="bad\nterm")], [dict(APPROVE, alias="!!!")],
    [dict(APPROVE, category="tool")], [dict(APPROVE, canonical="PRIVATE")],
    [dict(APPROVE, action="create")], [dict(id="pending", action="ignore")],
    [dict(id="pending", action="remove", alias="PRIVATE")],
    [dict(id="pending", action="remove"), dict(id="pending", action="remove")],
    [dict(APPROVE, id="pending"), APPROVE],
    [dict(id=str(i), action="remove") for i in range(201)]])
def test_manifest_is_strict_bounded_and_errors_do_not_echo_values(entries):
    with pytest.raises(legacy.LegacyDispositionError) as exc:
        legacy.validate_selection(entries)
    assert "PRIVATE" not in str(exc.value)


def test_inventory_other_status_is_only_a_count_and_nonlegacy_selection_refused(migrated):
    engine, _ = migrated
    t = legacy_rows(engine)
    with engine.begin() as conn:
        conn.execute(t["unmapped_terms"].update().where(t["unmapped_terms"].c.id == "pending")
                     .values(status="PRIVATE"))
        conn.execute(t["unmapped_terms"].update().where(t["unmapped_terms"].c.id == "ignored")
                     .values(provenance="different"))
    with engine.connect() as conn:
        assert legacy.inventory(conn) == dict(total=2, pending=0, ignored=0, resolved=1, other=1)
    with pytest.raises(legacy.LegacyDispositionError, match="nonlegacy"):
        with engine.begin() as conn:
            legacy.dispose(conn, [dict(id="pending", action="remove"), dict(id="ignored", action="remove")], apply=True)
    with engine.connect() as conn:
        assert conn.scalar(select(text("count(*)")).select_from(t["unmapped_terms"])) == 3


def test_cli_dry_run_is_counts_only_read_only_then_apply_retry(migrated, tmp_path):
    engine, _ = migrated
    t = legacy_rows(engine)
    manifest = [APPROVE, dict(id="pending", action="remove")]
    before_bytes = Path(engine.url.database).read_bytes() if engine.dialect.name == "sqlite" else None
    with engine.connect() as conn:
        before = conn.execute(select(t["unmapped_terms"])).mappings().all()
    preview = run_cli(engine, tmp_path, selection=manifest)
    assert preview.returncode == 0, preview.stderr
    assert not preview.stderr and "PRIVATE" not in preview.stdout and "resolved" not in json.loads(preview.stdout)["disposition"]
    assert json.loads(preview.stdout)["disposition"]["approved"] == 1
    with engine.connect() as conn:
        assert conn.execute(select(t["unmapped_terms"])).mappings().all() == before
    if before_bytes is not None:
        assert Path(engine.url.database).read_bytes() == before_bytes
    applied = run_cli(engine, tmp_path, selection=manifest, apply=True)
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout)["inventory"]["total"] == 1
    retry = run_cli(engine, tmp_path, selection=manifest, apply=True)
    assert retry.returncode == 0, retry.stderr
    assert json.loads(retry.stdout)["disposition"]["absent"] == 2


@pytest.mark.parametrize("payload", ["null", "{}", '[{"id":"pending","action":"remove","note":"PRIVATE"}]',
    '[{"id":"pending","action":"remove","action":"map"}]', '"PRIVATE"',
    "[" * 2000, " " * (256 * 1024 + 1)],
    ids=["null", "object", "extra_note", "duplicate_field", "scalar", "nested", "oversize"])
def test_cli_invalid_manifest_no_writes_no_raw_error(migrated, tmp_path, payload):
    engine, _ = migrated
    t = legacy_rows(engine)
    result = run_cli(engine, tmp_path, payload=payload, apply=True)
    assert result.returncode == 2 and result.stdout == ""
    assert "PRIVATE" not in result.stderr and "Traceback" not in result.stderr
    with engine.connect() as conn:
        assert conn.scalar(select(text("count(*)")).select_from(t["unmapped_terms"])) == 3


def test_cli_missing_target_never_creates_database_or_parent(tmp_path):
    target = tmp_path / "missing" / "missing.db"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run([sys.executable, str(SCRIPT), "--database", str(target)],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and result.stdout == "" and not target.parent.exists()


def test_default_cli_connection_enforces_read_only_even_on_accidental_write(migrated, monkeypatch, capsys):
    from scripts import dispose_legacy_curation as cli

    engine, _ = migrated
    t = legacy_rows(engine)
    if engine.dialect.name == "sqlite":
        args = ["--database", engine.url.database]
    else:
        monkeypatch.setenv("SYNTHETIC_DISPOSITION_DB", engine.url.render_as_string(hide_password=False))
        args = ["--database-url-env", "SYNTHETIC_DISPOSITION_DB"]

    def accidental_write(conn):
        conn.execute(t["unmapped_terms"].delete())
        return {}

    monkeypatch.setattr(cli, "inventory", accidental_write)
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert output.out == "" and "PRIVATE" not in output.err and "Traceback" not in output.err
    with engine.connect() as conn:
        assert conn.scalar(select(text("count(*)")).select_from(t["unmapped_terms"])) == 3


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("classified", [False, True])
def test_cli_refuses_unmigrated_database_and_preserves_file(tmp_path, apply, classified):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unmapped_terms (id TEXT PRIMARY KEY, display_name TEXT)")
        db.execute("INSERT INTO unmapped_terms VALUES ('pending','PRIVATE')")
        if classified:
            db.execute("ALTER TABLE unmapped_terms ADD COLUMN provenance TEXT DEFAULT 'legacy_unattributed'")
    before = path.read_bytes()
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        result = run_cli(engine, tmp_path, selection=[dict(id="pending", action="remove")], apply=apply)
    finally:
        engine.dispose()
    assert result.returncode == 2 and result.stdout == ""
    assert "PRIVATE" not in result.stderr and "Traceback" not in result.stderr
    assert path.read_bytes() == before


def test_failure_after_deletion_rolls_back_legacy_batch(migrated):
    engine, _ = migrated
    t = legacy_rows(engine)

    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO curation_aliases"):
            raise RuntimeError("synthetic interrupted disposition")

    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="interrupted"):
            with engine.begin() as conn:
                legacy.dispose(conn, [APPROVE, dict(id="pending", action="remove")], apply=True)
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)
    with engine.connect() as conn:
        assert set(conn.scalars(select(t["unmapped_terms"].c.id))) == {"pending", "ignored", "resolved"}
        assert list(conn.scalars(select(t["curation_aliases"].c.norm_key))) == []


@pytest.mark.parametrize("competing", ["same_selection", "approved_conflict", "legacy_conflict"])
def test_postgres_controlled_competing_dispositions(migrated, competing):
    engine, _ = migrated
    if engine.dialect.name != "postgresql":
        pytest.skip("Controlled PostgreSQL transaction ordering")
    t = legacy_rows(engine)
    ready, pids = Event(), []

    def second():
        with engine.begin() as conn:
            pids.append(conn.scalar(text("SELECT pg_backend_pid()")))
            ready.set()
            return legacy.dispose(conn, [APPROVE, dict(id="pending", action="remove")], apply=True)

    with engine.connect() as first, ThreadPoolExecutor(max_workers=1) as pool:
        tx = first.begin()
        try:
            if competing == "same_selection":
                legacy.dispose(first, [APPROVE, dict(id="pending", action="remove")], apply=True)
            elif competing == "approved_conflict":
                first.execute(t["curation_aliases"].insert().values(**dict(alias(),
                    norm_key="approved legacy vocabulary", alias="Approved legacy vocabulary")))
            else:
                first.execute(t["unmapped_terms"].insert().values(id="racing", norm_key="approved legacy vocabulary",
                    display_name="PRIVATE race", source_types=[], occurrences=1, first_seen=NOW,
                    last_seen=NOW, status="resolved", canonical="python", category="language", created_at=NOW))
            future = pool.submit(second)
            assert ready.wait(10)
            with engine.connect() as observer:
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    if observer.scalar(text("SELECT cardinality(pg_blocking_pids(:pid))"), dict(pid=pids[0])):
                        break
                else:
                    pytest.fail("second transaction did not block on first writer")
            assert not future.done()
            tx.commit()
            if competing == "same_selection":
                assert future.result(timeout=10)["absent"] == 2
            else:
                error = IntegrityError if competing == "approved_conflict" else legacy.LegacyDispositionError
                with pytest.raises(error):
                    future.result(timeout=10)
        finally:
            if tx.is_active:
                tx.rollback()
    with engine.connect() as conn:
        assert conn.scalar(select(text("count(*)")).select_from(t["curation_aliases"])) == (0 if competing == "legacy_conflict" else 1)
        remaining = set(conn.scalars(select(t["unmapped_terms"].c.id)))
        assert remaining == ({"ignored"} if competing == "same_selection" else
                             {"pending", "ignored", "resolved"} | ({"racing"} if competing == "legacy_conflict" else set()))
