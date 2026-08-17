"""The feature registry (PI-4 / S4.1).

Mirrors app/domains/base.py: a module-global registry + a decorator. Extractors
are pure ``FeatureContext -> FeatureValue``; ``compute_one`` validates every
output against its spec so an out-of-contract value is a loud bug, never a
silent clamp.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from app.features.schema import (
    FeatureContext,
    FeatureDType,
    FeatureSpec,
    FeatureValue,
    FeatureVector,
    FeatureView,
)


@dataclass(frozen=True)
class RegisteredFeature:
    spec: FeatureSpec
    fn: Callable[[FeatureContext], FeatureValue]


def _check_range(spec: FeatureSpec, value: float) -> None:
    if spec.valid_range is not None:
        lo, hi = spec.valid_range
        if value < lo or value > hi:
            raise ValueError(
                f"feature {spec.name!r} value {value} outside {spec.valid_range}"
            )


def _validate_value(spec: FeatureSpec, value: FeatureValue) -> FeatureValue:
    if value is None:
        if not spec.nullable:
            raise ValueError(f"feature {spec.name!r} returned None but is not nullable")
        return None
    if spec.dtype is FeatureDType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError(f"feature {spec.name!r} expected bool, got {value!r}")
        return value
    if spec.dtype is FeatureDType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {spec.name!r} expected int, got {value!r}")
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError(f"feature {spec.name!r} expected integral, got {value!r}")
            value = int(value)
        _check_range(spec, value)
        return value
    if spec.dtype is FeatureDType.NUMERIC:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"feature {spec.name!r} expected numeric, got {value!r}")
        value = float(value)
        _check_range(spec, value)
        return value
    # CATEGORICAL / ORDINAL
    if not isinstance(value, str):
        raise ValueError(f"feature {spec.name!r} expected str category, got {value!r}")
    if spec.categories and value not in spec.categories:
        raise ValueError(
            f"feature {spec.name!r} value {value!r} not in {spec.categories}"
        )
    return value


class FeatureRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int], RegisteredFeature] = {}

    def register(self, spec: FeatureSpec, fn: Callable[[FeatureContext], FeatureValue]) -> None:
        key = (spec.name, spec.version)
        if key in self._by_key:
            raise ValueError(f"feature already registered: {spec.name} v{spec.version}")
        self._by_key[key] = RegisteredFeature(spec, fn)

    def latest_version(self, name: str) -> int:
        versions = [v for (n, v) in self._by_key if n == name]
        if not versions:
            raise KeyError(f"unknown feature {name!r}. Registered: {self.names()}")
        return max(versions)

    def get(self, name: str, *, version: Optional[int] = None) -> RegisteredFeature:
        v = version if version is not None else self.latest_version(name)
        try:
            return self._by_key[(name, v)]
        except KeyError:
            raise KeyError(
                f"unknown feature {name!r} v{version}. Registered: {sorted(self._by_key)}"
            ) from None

    def names(self) -> list[str]:
        return sorted({n for (n, _) in self._by_key})

    def specs(self) -> list[FeatureSpec]:
        return [
            rf.spec
            for rf in sorted(self._by_key.values(), key=lambda r: (r.spec.name, r.spec.version))
        ]

    def compute_one(self, name: str, ctx: FeatureContext, *, version: Optional[int] = None) -> FeatureValue:
        rf = self.get(name, version=version)
        return _validate_value(rf.spec, rf.fn(ctx))

    def compute_view(self, view: FeatureView, ctx: FeatureContext) -> FeatureVector:
        values: dict[str, FeatureValue] = {}
        missing: list[str] = []
        for rf in view.resolve(self):
            value = _validate_value(rf.spec, rf.fn(ctx))
            values[rf.spec.name] = value
            if value is None:
                missing.append(rf.spec.name)
        return FeatureVector(
            candidate_id=ctx.candidate_id, as_of=ctx.as_of,
            view_name=view.name, view_version=view.version,
            values=values, missing=tuple(missing),
        )

    def manifest(self) -> list[dict]:
        return [s.to_dict() for s in self.specs()]

    def manifest_json(self) -> str:
        return json.dumps(self.manifest(), indent=2, sort_keys=True)


# --- module-global default registry (mirrors domains/base.py `_REGISTRY`) ------
_DEFAULT_REGISTRY = FeatureRegistry()


def register_feature(
    *,
    name: str,
    version: int,
    dtype: FeatureDType,
    source: FeatureSource,
    description: str,
    nullable: bool = True,
    requires_consent: bool = False,
    valid_range: Optional[tuple[float, float]] = None,
    categories: Optional[tuple[str, ...]] = None,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[[FeatureContext], FeatureValue]], Callable[[FeatureContext], FeatureValue]]:
    """Decorator: build a FeatureSpec from kwargs and register the wrapped
    extractor into the module-global registry, returning it unchanged."""
    spec = FeatureSpec(
        name=name, version=version, dtype=dtype, source=source,
        description=description, nullable=nullable, requires_consent=requires_consent,
        valid_range=valid_range, categories=categories, tags=tuple(tags),
    )

    def _decorator(fn: Callable[[FeatureContext], FeatureValue]):
        _DEFAULT_REGISTRY.register(spec, fn)
        return fn

    return _decorator


def _register(
    spec: FeatureSpec,
    fn: Callable[[FeatureContext], FeatureValue],
    *,
    registry: Optional[FeatureRegistry] = None,
) -> None:
    """Escape hatch for tests / programmatic registration."""
    (registry or _DEFAULT_REGISTRY).register(spec, fn)


def latest_view(registry: FeatureRegistry, *, name: str, version: int) -> FeatureView:
    """A view pinning every registered feature at its latest version."""
    members = tuple((n, registry.latest_version(n)) for n in registry.names())
    return FeatureView(name=name, version=version, members=members)
