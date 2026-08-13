"""Run Alembic to head at boot (PI-8 blocker 1).

Nothing in the repo migrated anything: ``alembic upgrade head`` lived only in
developer muscle memory and in the smoke scripts. A fresh container therefore
started against an empty database and failed at the first query.

Postgres boots take an advisory lock for the duration. Blocker 2's fix is
multiple uvicorn workers, and multiple workers boot at once -- without the lock
they race the same migration. SQLite serializes writes already.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import make_engine
from app.core.logging import get_logger

log = get_logger("migrate")

ROOT = Path(__file__).resolve().parents[2]

#: Arbitrary but FIXED -- every process must ask for the same lock.
_MIGRATION_LOCK_KEY = 81_000_001


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def revision_state(settings: Settings) -> tuple[Optional[str], Optional[str]]:
    """``(revision the database is at, head revision)``.

    ``None`` for the first means the database has no ``alembic_version`` table
    at all -- it was never migrated. Added in S8.6 for the retention CLI, which
    is the one entry point that runs against a database NOTHING in the process
    has migrated: the web service migrates on boot, a Railway cron is a
    separate container that can start first.
    """
    cfg = _alembic_config(settings.candidates_db_url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = make_engine(settings.candidates_db_url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    return current, head


def upgrade_to_head(settings: Settings) -> None:
    """Bring ``settings.candidates_db_url`` up to the latest revision."""
    url = settings.candidates_db_url
    cfg = _alembic_config(url)

    if url.startswith("sqlite"):
        command.upgrade(cfg, "head")
    else:
        # Session-scoped lock, held on THIS connection while Alembic migrates on
        # its own. A second worker blocks here until the first one is finished.
        engine = make_engine(url)
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_KEY}
                )
                conn.commit()
                try:
                    command.upgrade(cfg, "head")
                finally:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"),
                        {"k": _MIGRATION_LOCK_KEY},
                    )
                    conn.commit()
        finally:
            engine.dispose()

    log.info("migrations_applied", backend=url.split("://", 1)[0])
