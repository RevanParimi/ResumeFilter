"""Sweep targets, DERIVED from the portal's own retention table (S8.3 Phase B).

There is no second list of what to delete. Every target's knob is read out of
``RETENTION_KNOBS`` rather than written here, and
``tests/test_retention_plan.py`` asserts set equality in both directions -- the
metadata-drift-guard family that already caught a real migration-vs-ORM drift in
S7.1. A sweeper free to name its own window could delete on 7 days while the
portal promised 90, and nothing would say so.

ELEVEN CLASSES, TWELVE TARGETS: ``login_state`` covers two tables, because an
abandoned login challenge and a session that expired without a logout are the
same fact to the person they describe. That is why the guard compares a SET of
data classes and not a length.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from app.auth.models import AuthSessionRow, LoginChallengeRow
from app.candidates.models import ResumeRow
from app.core.config import Settings
from app.interview.models import InterviewSessionRow
from app.ledger.models import (
    AuditLogRow,
    CodingRoundResultRow,
    InterviewRecordRow,
    ObservedOfferRow,
)
from app.portal.retention import RETENTION_KNOBS
from app.profile_sources.models import ProfileSourceRow
from app.ratelimit.models import RateLimitCounterRow
from app.screening.models import BatchItemRow
from app.verification.models import VerificationRow


class SweepMode(StrEnum):
    """DELETE removes the row. CLEAR blanks one column and KEEPS the row."""

    DELETE = "delete"
    CLEAR = "clear"


@dataclass(frozen=True)
class SweepTarget:
    data_class: str
    model: type
    timestamp_column: str
    mode: SweepMode
    #: CLEAR only. The column blanked -- and the column whose NON-EMPTINESS is
    #: half the eligibility predicate. Without that half, a preview reports the
    #: same already-cleared rows every day forever.
    clear_column: Optional[str] = None

    @property
    def knob(self) -> str:
        """The Settings attribute holding this class's TTL.

        READ OFF RETENTION_KNOBS, never stored on the target: this is what makes
        the promise and the deletion one fact rather than two that agree today.
        """
        return RETENTION_KNOBS[self.data_class]


TARGETS: tuple[SweepTarget, ...] = (
    SweepTarget("resumes", ResumeRow, "created_at", SweepMode.DELETE),
    SweepTarget("profile_sources", ProfileSourceRow, "created_at", SweepMode.DELETE),
    SweepTarget("verifications", VerificationRow, "created_at", SweepMode.DELETE),
    SweepTarget("interviews", InterviewSessionRow, "created_at", SweepMode.DELETE),
    SweepTarget("interview_records", InterviewRecordRow, "created_at", SweepMode.DELETE),
    SweepTarget("coding_rounds", CodingRoundResultRow, "created_at", SweepMode.DELETE),
    SweepTarget("observed_offers", ObservedOfferRow, "created_at", SweepMode.DELETE),
    SweepTarget("audit_log", AuditLogRow, "created_at", SweepMode.DELETE),
    # The ROW SURVIVES: an organisation's record of what it screened must
    # outlive the text it screened, exactly as batch_items.candidate_id is SET
    # NULL rather than cascading. This is also where Phase A and Phase B meet --
    # past ret_batch_item_days a failed item is no longer retryable, because its
    # input is gone (SCREENING.md §7, OPERATING.md §6).
    SweepTarget(
        "batch_item_text", BatchItemRow, "created_at", SweepMode.CLEAR,
        clear_column="raw_text",
    ),
    # Keyed on expires_at rather than created_at: for a row that declares its
    # own end of life, that declaration is the honest start of the window.
    SweepTarget(
        "rate_limit_counters", RateLimitCounterRow, "expires_at", SweepMode.DELETE
    ),
    SweepTarget("login_state", LoginChallengeRow, "expires_at", SweepMode.DELETE),
    SweepTarget("login_state", AuthSessionRow, "expires_at", SweepMode.DELETE),
)


def data_classes() -> set[str]:
    return {t.data_class for t in TARGETS}


def ttl_days(target: SweepTarget, settings: Settings) -> int:
    return int(getattr(settings, target.knob))
