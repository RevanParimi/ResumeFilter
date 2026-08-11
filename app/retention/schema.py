"""Retention sweep contracts (S8.3 Phase B). Pure Pydantic -- no I/O."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ClassSweepResult(BaseModel):
    """What one data class contributed.

    ``affected`` is rows DELETED for a delete target and rows CLEARED for a
    clear target -- one number, because the operator's question is "how much
    moved". Which mode a class uses is a property of the class, stated once in
    OPERATING.md rather than repeated on every run.
    """

    data_class: str
    affected: int
    truncated: bool = False


class SweepReport(BaseModel):
    by_class: list[ClassSweepResult] = Field(default_factory=list)
    dry_run: bool
    #: True when ANY class hit its cap, so a cron's log line does not have to
    #: walk the list to learn there is more to do.
    truncated: bool = False
    at: datetime
