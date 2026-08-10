"""Human outcome records (FR-7/FR-8): how a reviewer closed the loop.

Moved verbatim from ``app/services/report_store.py`` in S8.1; the contracts did
not change, only where the rows live.

S8.5 added provenance, because customers can now write here too and an
unattributed judgment is worth very little to a calibration harness. See
``app/reports/outcomes.py`` for the one constructor that stamps it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class OutcomeLabel(StrEnum):
    """How a human closed the loop on a report/claim."""

    VERIFIED_GENUINE = "verified_genuine"
    VERIFIED_FABRICATED = "verified_fabricated"
    CANDIDATE_CLARIFIED = "candidate_clarified"
    INCONCLUSIVE = "inconclusive"


class OutcomeSource(StrEnum):
    """Who produced this judgment -- and it is NOT derivable from ``org_id``.

    ``outcomes.org_id`` is ``ON DELETE SET NULL`` (the label must survive an
    organisation offboarding, exactly as ``reports.org_id`` does), so a null
    org would conflate "our own operator recorded this" with "the customer who
    recorded this has gone". PI-9 must never train on our operator's self-labels
    believing a customer produced them; that is circular, and the derived answer
    would always look plausible.
    """

    OPERATOR = "operator"
    ORGANIZATION = "organization"


class OutcomeRecord(BaseModel):
    """One human judgment; claim_id=None means it applies to the whole report.

    ``recorded_by`` is REQUIRED and has no default. A default is the forget-me
    hazard ``app/reports/outcomes.build_outcome`` exists to remove: a wrong
    provenance stamp is invisible until something draws a conclusion from it.
    """

    report_id: str
    claim_id: Optional[str] = None
    outcome: OutcomeLabel
    notes: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    #: Which plane wrote this. Required -- see the class docstring.
    recorded_by: OutcomeSource
    #: Which customer, when one did. NULL for an operator's judgment AND for an
    #: offboarded organisation's, which is why ``recorded_by`` exists.
    org_id: Optional[str] = None
    #: Which human, when there was one. NULL for an ``X-Org-Key`` machine
    #: caller -- inventing one would be a false audit trail (the same decision,
    #: and the same words, as ``screening_batches.created_by_org_user_id``).
    recorded_by_org_user_id: Optional[str] = None
