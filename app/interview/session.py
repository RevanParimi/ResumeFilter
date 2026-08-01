"""The session-status rule (S7.3). Pure, clock-injected, small on purpose.

Expiry is computed at READ time and never written. There is no scheduler in
this system, so a stored `abandoned` would be a lie nobody corrects -- the same
reasoning that keeps S7.1's `expired` derived rather than stamped.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.interview.schema import InterviewStatus
from app.ledger.consent import as_utc


def effective_status(
    status: InterviewStatus, expires_at: Optional[datetime], *, at: datetime
) -> InterviewStatus:
    """`abandoned` once an unfinished session passes its TTL. A finished
    session is finished forever."""
    if status is not InterviewStatus.IN_PROGRESS:
        return status
    if expires_at is not None and as_utc(expires_at) <= as_utc(at):
        return InterviewStatus.ABANDONED
    return status
