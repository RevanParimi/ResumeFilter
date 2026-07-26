import pytest
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec


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
