from datetime import datetime, timezone

import pytest
from app.features.schema import (
    FeatureContext, FeatureDType, FeatureSource, FeatureSpec, FeatureVector, FeatureView,
)


def _spec(**kw):
    base = dict(
        name="candidate.years_experience", version=1,
        dtype=FeatureDType.NUMERIC, source=FeatureSource.CANDIDATE,
        description="Years of experience.",
    )
    base.update(kw)
    return FeatureSpec(**base)


def test_valid_numeric_spec_roundtrips():
    s = _spec(valid_range=(0.0, 60.0))
    assert s.name == "candidate.years_experience"
    d = s.to_dict()
    assert d["dtype"] == "numeric" and d["valid_range"] == [0.0, 60.0]
    assert d["requires_consent"] is False


def test_bad_name_rejected():
    with pytest.raises(ValueError):
        _spec(name="BadName")           # no namespace, uppercase
    with pytest.raises(ValueError):
        _spec(name="candidate..x")


def test_version_and_description_bounds():
    with pytest.raises(ValueError):
        _spec(version=0)
    with pytest.raises(ValueError):
        _spec(description="   ")


def test_valid_range_only_numeric():
    with pytest.raises(ValueError):
        _spec(dtype=FeatureDType.BOOLEAN, valid_range=(0.0, 1.0))


def test_categorical_requires_categories_and_ordering():
    with pytest.raises(ValueError):
        _spec(dtype=FeatureDType.ORDINAL)                 # missing categories
    with pytest.raises(ValueError):
        _spec(dtype=FeatureDType.NUMERIC, categories=("a", "b"))  # forbidden
    ok = _spec(dtype=FeatureDType.ORDINAL, categories=("none", "bachelor"))
    assert ok.categories == ("none", "bachelor")


def test_consent_source_coherence():
    # ledger/reputation source MUST set requires_consent
    with pytest.raises(ValueError):
        _spec(source=FeatureSource.LEDGER)
    # requires_consent MUST come from a ledger/reputation source
    with pytest.raises(ValueError):
        _spec(requires_consent=True)
    ok = _spec(source=FeatureSource.REPUTATION, requires_consent=True)
    assert ok.requires_consent is True


def test_context_reputation_is_cached_and_uses_as_of():
    ctx = FeatureContext(candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    rep_a = ctx.reputation
    rep_b = ctx.reputation
    assert rep_a is rep_b                      # memoized
    assert rep_a.band.value == "insufficient_data"   # no records -> prior


def test_feature_vector_shape():
    fv = FeatureVector(
        candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        view_name="core_v1", view_version=1,
        values={"candidate.num_skills": 3, "candidate.max_cgpa_10": None},
        missing=("candidate.max_cgpa_10",),
    )
    assert fv.values["candidate.num_skills"] == 3
    assert fv.missing == ("candidate.max_cgpa_10",)
