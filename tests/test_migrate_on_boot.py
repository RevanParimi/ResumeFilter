"""Blocker 1 (gap-analysis v2 §9): nothing ran `alembic upgrade head` in the
boot path, so a fresh container started against no schema at all."""

from __future__ import annotations

from sqlalchemy import inspect

from app.core.db import make_engine
from app.core.migrate import upgrade_to_head


def test_upgrade_to_head_builds_the_schema_from_empty(settings, tmp_path):
    url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    fresh = settings.model_copy(update={"candidates_db_url": url})

    upgrade_to_head(fresh)

    names = set(inspect(make_engine(url)).get_table_names())
    assert {"candidates", "organizations", "interview_sessions"} <= names
    assert "alembic_version" in names


def test_upgrade_to_head_is_idempotent(settings, tmp_path):
    url = "sqlite:///" + (tmp_path / "twice.db").as_posix()
    fresh = settings.model_copy(update={"candidates_db_url": url})

    upgrade_to_head(fresh)
    upgrade_to_head(fresh)  # a second boot must be a no-op, not an error

    assert "candidates" in set(inspect(make_engine(url)).get_table_names())
