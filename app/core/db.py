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
