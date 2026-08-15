"""S4.4 training-set contracts — leakage-free label + labeled example.

A TrainingLabel is derived ONLY from ledger outcomes strictly after the feature
vector's `as_of`. `observed=False` (right-censored) means no post-cut outcome
exists yet — NOT a negative. `withheld=True` means consent was not active at
`as_of` (the S4.2 decision), so no label was read and every value field is None.
Advisory: this is training data, never a gate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.features.schema import FeatureVector


class TrainingLabel(BaseModel):
    hired: Optional[bool] = None
    outcome: Optional[str] = None
    coding_best_percentile: Optional[float] = None
    event_at: Optional[datetime] = None
    lag_days: Optional[float] = None
    observed: bool = False
    withheld: bool = False


class TrainingExample(BaseModel):
    """One training row: an S4.2 feature vector joined to its post-cut label."""

    vector: FeatureVector
    label: TrainingLabel
