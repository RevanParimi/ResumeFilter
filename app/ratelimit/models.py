"""ORM row for the rate limiter (S8.3 Phase A). Postgres-shaped on SQLite.

There is ONE table and it has NO foreign keys, deliberately: a counter must be
writable on the login path BEFORE any principal exists, and an FK to
candidates/organizations would tie a pre-auth write to a subject we have not
identified yet.

``window_start`` is an INTEGER of epoch seconds rather than a timestamp. It is
only ever compared for exact equality (the WHERE of the conditional UPDATE),
and an integer has no timezone semantics for SQLite and Postgres to disagree
about. ``expires_at`` IS a real timestamp, because S8.3 Phase B's retention
sweep reads it the same way it reads every other retention column.

The row holds a salted hash and a count -- never the email, never the IP.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RateLimitCounterRow(Base):
    __tablename__ = "rate_limit_counters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    #: sha256 hex of salt|rule|scope|identity -- see app/ratelimit/schema.py.
    bucket_key: Mapped[str] = mapped_column(String(128), index=True)
    #: Epoch seconds at which this fixed window opened.
    window_start: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(Integer, default=0)
    #: When this row stops being useful. The Phase B sweep's access path.
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        # The whole limiter rests on this: it is what turns a lost INSERT race
        # into a catchable IntegrityError instead of a second uncounted row.
        UniqueConstraint(
            "bucket_key", "window_start", name="uq_rate_limit_counters_key_window"
        ),
    )
