"""Extraction-coverage contracts (S9.2).

ADVISORY ONLY: coverage says what the PARSER may have missed, never anything
about the candidate. It feeds no score, no band and no verdict, and it is never
a rejection signal.

Lives in app/schemas/ rather than app/candidates/ so app/schemas/report.py
composes it the way it already composes app/schemas/fabrication.py -- the
Report's imports stay inside one package.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class CoverageBand(StrEnum):
    """Conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    COMPLETE = "complete"
    MINOR_GAPS = "minor_gaps"
    MAJOR_GAPS = "major_gaps"


class GapSeverity(StrEnum):
    """MAJOR = a field the text evidently describes is entirely absent.
    MINOR = informational; the profile is populated but something was odd.

    Deliberately NOT app.schemas.fabrication.FindingSeverity: reusing that enum
    would couple extraction quality to fabrication semantics, and a coverage gap
    is a statement about our parser, not about the candidate.
    """

    MINOR = "minor"
    MAJOR = "major"


class CoverageGap(BaseModel):
    """One thing the resume appears to state that the profile does not carry."""

    id: str  # stable check id, e.g. "experience_not_extracted"
    detail: str
    severity: GapSeverity = GapSeverity.MINOR
    field: Optional[str] = None   # profile field involved, e.g. "experience"
    #: The literal section header, for `section_unrecognized` ONLY. The only
    #: place coverage quotes the resume; a header is not personal data and it is
    #: length-bounded, because the report body is stored (S7.2's claim_ref).
    header: Optional[str] = None


class ExtractionCoverage(BaseModel):
    """Did the extractor read what the resume actually says?

    A refusal (INSUFFICIENT_DATA) carries NO gaps -- see S9.1's SIGNALS.md: a
    measurement that could not be taken must not be readable as one that was.
    """

    band: CoverageBand = CoverageBand.INSUFFICIENT_DATA
    gaps: list[CoverageGap] = Field(default_factory=list)
    checks_run: int = 0
    truncated: bool = False   # gaps were capped at coverage_max_gaps
    advisory: bool = True     # mirrors Report: never a rejection signal
