"""The rate limiter's only I/O (S8.3 Phase A).

``hit`` is check-and-increment as ONE decision. Two concurrent requests on one
bucket must not both read count=19 and both write 20, so the check lives in the
WHERE clause of a conditional UPDATE and ``rowcount`` is the answer -- the exact
shape ``ScreeningStore._try_claim`` uses, for the exact same reason.

``_try_increment`` is a separate method because the race it defends against is
UNREACHABLE through two sequential ``hit`` calls: the second call's UPDATE
simply finds a row already at its limit. S8.4 Phase B measured two mutants
surviving in precisely that way, so the seam exists to let a test build the
interleaved state directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ratelimit.models import RateLimitCounterRow


class RateLimitStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def hit(
        self,
        *,
        bucket_key: str,
        window_start: int,
        limit: int,
        expires_at: Optional[datetime],
    ) -> bool:
        """Count one event against a bucket. True = allowed.

        A refused hit does NOT increment: the count would otherwise climb
        forever under attack, and that number is what the deny metric reports.
        """
        if limit <= 0:
            # Config forbids this (ge=1). Defence in depth, because the path
            # below would otherwise INSERT count=1 and ALLOW -- the opposite of
            # what a zero limit means.
            return False

        with self._session_factory() as session:
            if self._try_increment(
                session, bucket_key=bucket_key, window_start=window_start, limit=limit
            ):
                session.commit()
                return True

            # rowcount 0 means EITHER the row is at its limit OR it does not
            # exist yet. Those need opposite answers, so distinguish them.
            existing = session.execute(
                select(RateLimitCounterRow.id).where(
                    RateLimitCounterRow.bucket_key == bucket_key,
                    RateLimitCounterRow.window_start == window_start,
                )
            ).first()
            if existing is not None:
                session.rollback()
                return False

            try:
                # Housekeeping on a path that already runs (the S7.1 challenge
                # hygiene precedent): opening a new window for this key retires
                # the previous one. Bounded to this key -- the Phase B sweep
                # owns keys that are never seen again.
                session.execute(
                    delete(RateLimitCounterRow).where(
                        RateLimitCounterRow.bucket_key == bucket_key,
                        RateLimitCounterRow.window_start < window_start,
                    )
                )
                session.add(
                    RateLimitCounterRow(
                        bucket_key=bucket_key,
                        window_start=window_start,
                        count=1,
                        expires_at=expires_at,
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                # Somebody else opened the window between our SELECT and our
                # INSERT. Their row is authoritative; count against it.
                session.rollback()
                allowed = self._try_increment(
                    session, bucket_key=bucket_key,
                    window_start=window_start, limit=limit,
                )
                session.commit()
                return allowed

    @staticmethod
    def _try_increment(
        session: Session, *, bucket_key: str, window_start: int, limit: int
    ) -> bool:
        """Increment IF under the limit. The check and the write, one statement.

        Driven directly by tests/test_ratelimit_store.py -- see the module
        docstring for why an end-to-end test cannot reach the state this
        defends against.
        """
        res = session.execute(
            update(RateLimitCounterRow)
            .where(
                RateLimitCounterRow.bucket_key == bucket_key,
                RateLimitCounterRow.window_start == window_start,
                RateLimitCounterRow.count < limit,
            )
            .values(count=RateLimitCounterRow.count + 1)
        )
        return res.rowcount == 1


def build_rate_limit_store(session_factory: sessionmaker) -> RateLimitStore:
    return RateLimitStore(session_factory)
