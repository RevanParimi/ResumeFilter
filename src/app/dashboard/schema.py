"""Employer dashboard read-model contracts (S5.3). Pure, serializable. No I/O."""

from __future__ import annotations

from pydantic import BaseModel

from app.comp.schema import CompBenchmark
from app.matching.schema import JobRequisition, MatchResult


class RequisitionBoard(BaseModel):
    requisition: JobRequisition
    comp: CompBenchmark
    match: MatchResult
    advisory: bool = True
