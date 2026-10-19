"""Source-owned review snapshots and raw-free approved decision receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class CurationStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class CurationAction(StrEnum):
    MAP = "map"        # alias -> an existing canonical
    CREATE = "create"  # a new canonical id + category
    IGNORE = "ignore"  # confirmed not-a-skill


class UnmappedTerm(BaseModel):
    """Snapshot derived only from surviving, unexpired source observations."""

    norm_key: str                                    # snapshot API handle
    display_name: str                                # human-readable raw form (most recent)
    source_types: list[str] = Field(default_factory=list)
    occurrences: int = Field(default=1, ge=1)
    first_seen: datetime
    last_seen: datetime
    review_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: CurationStatus = CurationStatus.PENDING


class UnmappedPage(BaseModel):
    """S8.4 Phase B: a page of the review queue.

    NOTE the sort key (occurrences, last_seen) is MUTABLE -- a term seen again
    moves. Paging is therefore stable against inserts and not against
    re-observation, expiry or erasure. Acceptable here and stated rather than hidden: this is an
    internal operator queue (UI.md §4.F), not a customer surface.
    """

    terms: list[UnmappedTerm] = Field(default_factory=list)
    next_cursor: Optional[str] = None


@dataclass(frozen=True)
class CurationDecision:
    """Only explicitly approved vocabulary; no submitted raw term or notes."""

    action: CurationAction
    alias: str | None
    canonical: str | None
    category: str | None
    decided_at: datetime
    admin_user_id: str | None
