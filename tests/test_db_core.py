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
