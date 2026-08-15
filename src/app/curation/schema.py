"""Curation contracts (PI-6 / S6.3): the review queue for unmapped skill terms.

A skill term normalize_skill can't map (canonical=None) surfaces here as an
UnmappedTerm. A human reviewer resolves it (map / create / ignore); the
resolution feeds a deterministic overlay consulted by normalize_skill. No LLM,
no auto-learning. The queue is candidate-agnostic — taxonomy-gap metadata, not
personal data (no candidate_id, no consent, no CASCADE).
"""

from __future__ import annotations

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
    """One unmapped skill term in the review queue (aggregate, candidate-agnostic)."""

    norm_key: str                                    # stable identity + API handle
    display_name: str                                # human-readable raw form (most recent)
    source_types: list[str] = Field(default_factory=list)
    occurrences: int = Field(default=1, ge=1)
    first_seen: datetime
    last_seen: datetime
    status: CurationStatus = CurationStatus.PENDING
    # resolution — set only when resolved/ignored
    action: Optional[CurationAction] = None
    canonical: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None


class UnmappedPage(BaseModel):
    """S8.4 Phase B: a page of the review queue.

    NOTE the sort key (occurrences, last_seen) is MUTABLE -- a term seen again
    moves. Paging is therefore stable against inserts and not against
    re-observation. Acceptable here and stated rather than hidden: this is an
    internal operator queue (UI.md §4.F), not a customer surface.
    """

    terms: list[UnmappedTerm] = Field(default_factory=list)
    next_cursor: Optional[str] = None
