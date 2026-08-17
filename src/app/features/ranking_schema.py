"""Talent-search / ranking contracts (PI-4 / S4.3).

Pure, serializable request/result models + enums for the advisory ranking
engine. No I/O, no callables. The engine lives in ranking.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator

from app.features.schema import FeatureValue

FilterValue = Union[float, int, bool, str, list]


class FilterOp(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in_"
    NOT_IN = "not_in"
    EXISTS = "exists"
    MISSING = "missing"


class SortDirection(StrEnum):
    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"


_NO_VALUE_OPS = {FilterOp.EXISTS, FilterOp.MISSING}
_LIST_OPS = {FilterOp.IN, FilterOp.NOT_IN}


class FeatureFilter(BaseModel):
    feature: str
    op: FilterOp
    value: Optional[FilterValue] = None

    @model_validator(mode="after")
    def _value_matches_op(self) -> "FeatureFilter":
        if self.op in _NO_VALUE_OPS:
            if self.value is not None:
                raise ValueError(f"{self.op.value} takes no value")
            return self
        if self.value is None:
            raise ValueError(f"{self.op.value} requires a value")
        if self.op in _LIST_OPS and not isinstance(self.value, list):
            raise ValueError(f"{self.op.value} requires a list value")
        if self.op not in _LIST_OPS and isinstance(self.value, list):
            raise ValueError(f"{self.op.value} does not take a list value")
        return self


class RankingTerm(BaseModel):
    feature: str
    weight: float = Field(gt=0.0)
    direction: SortDirection = SortDirection.HIGHER_BETTER


class RankingSpec(BaseModel):
    terms: tuple[RankingTerm, ...]

    @model_validator(mode="after")
    def _non_empty(self) -> "RankingSpec":
        if not self.terms:
            raise ValueError("ranking needs at least one term")
        return self


class Contribution(BaseModel):
    feature: str
    raw: FeatureValue
    normalized: float
    weight: float
    weighted: float


class RankedCandidate(BaseModel):
    candidate_id: str
    score: float
    coverage: float
    contributions: tuple[Contribution, ...] = ()
    missing: tuple[str, ...] = ()


class SearchResult(BaseModel):
    advisory: bool = True
    as_of: Optional[datetime] = None
    view_name: str
    view_version: int
    pool_size: int
    filtered_size: int
    ranked: tuple[RankedCandidate, ...] = ()
