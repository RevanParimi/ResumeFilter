from datetime import datetime, timezone
import pytest
from app.features.schema import (
    FeatureContext, FeatureDType, FeatureSource, FeatureSpec, FeatureView,
)
from app.features.registry import FeatureRegistry, _register, latest_view


def _ctx():
    return FeatureContext(candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))


def _num_spec(name="candidate.x", version=1, **kw):
    return FeatureSpec(name=name, version=version, dtype=FeatureDType.NUMERIC,
                       source=FeatureSource.CANDIDATE, description="x", **kw)


def test_register_get_latest_and_collision():
    reg = FeatureRegistry()
    _register(_num_spec(version=1), lambda c: 1.0, registry=reg)
    _register(_num_spec(version=2), lambda c: 2.0, registry=reg)
    assert reg.latest_version("candidate.x") == 2
    assert reg.get("candidate.x").spec.version == 2       # latest
    assert reg.get("candidate.x", version=1).spec.version == 1
    with pytest.raises(ValueError):
        _register(_num_spec(version=2), lambda c: 9.0, registry=reg)  # dup key
    with pytest.raises(KeyError):
        reg.get("candidate.missing")


def test_compute_one_validates_output():
    reg = FeatureRegistry()
    _register(_num_spec(name="candidate.r", valid_range=(0.0, 1.0)),
              lambda c: 5.0, registry=reg)                # out of range
    with pytest.raises(ValueError):
        reg.compute_one("candidate.r", _ctx())

    _register(FeatureSpec(name="candidate.b", version=1, dtype=FeatureDType.BOOLEAN,
                          source=FeatureSource.CANDIDATE, description="b", nullable=False),
              lambda c: None, registry=reg)               # None but not nullable
    with pytest.raises(ValueError):
        reg.compute_one("candidate.b", _ctx())

    _register(FeatureSpec(name="candidate.o", version=1, dtype=FeatureDType.ORDINAL,
                          source=FeatureSource.CANDIDATE, description="o",
                          categories=("none", "high")),
              lambda c: "medium", registry=reg)           # not a category
    with pytest.raises(ValueError):
        reg.compute_one("candidate.o", _ctx())


def test_integer_coerces_integral_float():
    reg = FeatureRegistry()
    _register(FeatureSpec(name="candidate.n", version=1, dtype=FeatureDType.INTEGER,
                          source=FeatureSource.CANDIDATE, description="n"),
              lambda c: 3.0, registry=reg)
    out = reg.compute_one("candidate.n", _ctx())
    assert out == 3 and isinstance(out, int)


def test_compute_view_collects_missing_and_manifest_sorted():
    reg = FeatureRegistry()
    _register(_num_spec(name="candidate.a"), lambda c: 1.0, registry=reg)
    _register(_num_spec(name="candidate.z"), lambda c: None, registry=reg)  # nullable default
    view = latest_view(reg, name="core_v1", version=1)
    fv = reg.compute_view(view, _ctx())
    assert fv.values["candidate.a"] == 1.0
    assert fv.missing == ("candidate.z",)
    assert [s["name"] for s in reg.manifest()] == ["candidate.a", "candidate.z"]
