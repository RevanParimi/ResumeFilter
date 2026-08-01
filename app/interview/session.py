"""Session status + the header projection (S7.3). Pure, clock-injected.

Expiry is computed at READ time and never written. There is no scheduler in
this system, so a stored `abandoned` would be a lie nobody corrects -- the same
reasoning that keeps S7.1's `expired` derived rather than stamped.

`summarize` lives here rather than on the service because BOTH the service and
the store need it, and the transcript-free projection is exactly the kind of
rule that must have one implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.interview.schema import (
    InterviewBand, InterviewSession, InterviewStatus, InterviewSummary, ProxyBand,
)
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


def summarize(
    session: InterviewSession, *, at: Optional[datetime] = None
) -> InterviewSummary:
    """Header projection: no transcript, no turns, by construction. Used by the
    candidate's list view AND by the org read -- one implementation, so an org
    cannot end up one forgotten filter away from the candidate's words."""
    moment = at or datetime.now(timezone.utc)
    assessment = session.assessment
    return InterviewSummary(
        id=session.id,
        status=effective_status(session.status, session.expires_at, at=moment),
        domain=session.domain,
        band=assessment.band if assessment else InterviewBand.INSUFFICIENT_SIGNAL,
        overall=assessment.overall if assessment else 0.0,
        dimensions=dict(assessment.dimensions) if assessment else {},
        confidence=assessment.confidence if assessment else 0.0,
        proxy_band=assessment.proxy.band if assessment else ProxyBand.LOW,
        questions_planned=(
            assessment.questions_planned if assessment else len(session.questions)
        ),
        questions_answered=(
            assessment.questions_answered if assessment else len(session.turns)
        ),
        started_at=session.started_at,
        completed_at=session.completed_at,
    )
