"""Human outcome records (FR-7/FR-8): how a reviewer closed the loop.

Moved verbatim from ``app/services/report_store.py`` in S8.1; the contracts did
not change, only where the rows live.
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


class OutcomeRecord(BaseModel):
    """One human judgment; claim_id=None means it applies to the whole report."""

    report_id: str
    claim_id: Optional[str] = None
    outcome: OutcomeLabel
    notes: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
