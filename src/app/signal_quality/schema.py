"""Result types for the signal quality harness (S9.1).

A REFUSAL AND A MEASUREMENT ARE DIFFERENT TYPES, deliberately. One model with
optional metric fields would let a refusal travel as ``{"auc": null}``, which a
caller reads as "AUC could not be computed" when the truth is "we refused to
compute anything and here is why". Two types make the wrong reading
unrepresentable rather than merely discouraged -- the same move S7.1 made for
"no column can hold a document".
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class LabelKind(StrEnum):
    """What a label is ABOUT. See schema 4.1: OutcomeLabel is a fraud
    vocabulary and InterviewOutcome is a hiring one, and scoring a signal
    against the wrong one produces a plausible-looking number for a question
    nobody asked."""

    FRAUD = "fraud"
    HIRE = "hire"


class MetricKind(StrEnum):
    AUC = "auc"
    BRIER = "brier"
    LIFT = "lift"


class RefusalReason(StrEnum):
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    DEGENERATE_CLASS = "degenerate_class"
    LABEL_KIND_MISMATCH = "label_kind_mismatch"


class CalibrationBin(BaseModel):
    """One bin of the reliability curve. ``n`` is NOT optional: a bin's
    predicted-vs-observed gap is uninterpretable without it, and a chart that
    hides it is how a 2-sample bin gets read as a finding."""

    model_config = ConfigDict(frozen=True)

    lower: float
    upper: float
    n: int
    mean_predicted: Optional[float] = None
    observed_rate: Optional[float] = None


class BandLift(BaseModel):
    model_config = ConfigDict(frozen=True)

    band: str
    n: int
    positive_rate: float
    lift: Optional[float] = None  # None when the base rate is 0


class SignalMeasured(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: str
    sufficient: Literal[True] = True
    n: int
    positives: int
    auc: Optional[float] = None
    brier: Optional[float] = None
    curve: tuple[CalibrationBin, ...] = ()
    lift: tuple[BandLift, ...] = ()


class SignalRefused(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: str
    sufficient: Literal[False] = False
    reason: RefusalReason
    n: int
    detail: str


SignalResult = Union[SignalMeasured, SignalRefused]


class Population(BaseModel):
    """The run's own population. A metric without this is not interpretable,
    so it is never optional and never omitted from a response."""

    model_config = ConfigDict(frozen=True)

    label_source: str
    label_kind: LabelKind
    include_operator_labels: bool
    labels_usable: int
    earliest_report: Optional[datetime] = None
    latest_report: Optional[datetime] = None


class SignalQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    population: Population
    signals: tuple[SignalResult, ...] = ()
