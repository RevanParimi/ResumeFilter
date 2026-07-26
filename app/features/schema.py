"""Feature-registry contracts (PI-4 / S4.1).

Pure, serializable definitions of ML features over candidate + eval + ledger
data. No I/O, no LLM. A FeatureSpec is metadata; the extractor callable lives
beside it in the registry (registry.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional, Union

FeatureValue = Union[float, int, bool, str, None]


class FeatureDType(StrEnum):
    NUMERIC = "numeric"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"


class FeatureSource(StrEnum):
    CANDIDATE = "candidate"
    DEPTH = "depth"
    FABRICATION = "fabrication"
    LEDGER = "ledger"
    REPUTATION = "reputation"


_CONSENT_SOURCES = {FeatureSource.LEDGER, FeatureSource.REPUTATION}
_NUMERIC = {FeatureDType.NUMERIC, FeatureDType.INTEGER}
_CATEGORICAL = {FeatureDType.CATEGORICAL, FeatureDType.ORDINAL}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class FeatureSpec:
    """Serializable metadata for one feature definition (no callable)."""

    name: str
    version: int
    dtype: FeatureDType
    source: FeatureSource
    description: str
    nullable: bool = True
    requires_consent: bool = False
    valid_range: Optional[tuple[float, float]] = None
    categories: Optional[tuple[str, ...]] = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(
                f"feature name must be '<namespace>.<snake_case>': {self.name!r}"
            )
        if self.version < 1:
            raise ValueError(f"feature version must be >= 1: {self.version}")
        if not self.description.strip():
            raise ValueError(f"feature {self.name!r} needs a non-empty description")
        if self.valid_range is not None:
            if self.dtype not in _NUMERIC:
                raise ValueError(
                    f"valid_range only valid for numeric dtypes: {self.name!r}"
                )
            lo, hi = self.valid_range
            if hi < lo:
                raise ValueError(f"valid_range hi < lo: {self.name!r}")
        if self.dtype in _CATEGORICAL and not self.categories:
            raise ValueError(f"{self.dtype} feature needs categories: {self.name!r}")
        if self.dtype not in _CATEGORICAL and self.categories is not None:
            raise ValueError(
                f"categories only valid for categorical/ordinal: {self.name!r}"
            )
        if self.requires_consent and self.source not in _CONSENT_SOURCES:
            raise ValueError(
                f"requires_consent implies a ledger/reputation source: {self.name!r}"
            )
        if self.source in _CONSENT_SOURCES and not self.requires_consent:
            raise ValueError(
                f"ledger/reputation feature must set requires_consent: {self.name!r}"
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "dtype": self.dtype.value,
            "source": self.source.value,
            "description": self.description,
            "nullable": self.nullable,
            "requires_consent": self.requires_consent,
            "valid_range": list(self.valid_range) if self.valid_range else None,
            "categories": list(self.categories) if self.categories else None,
            "tags": list(self.tags),
        }
