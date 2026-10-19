"""Feature schema regressions, grouped by behavior."""

import pytest
from datetime import datetime, timezone
from app.features.schema import (
    FeatureContext,
    FeatureDType,
    FeatureSource,
    FeatureSpec,
    FeatureVector,
    FeatureView,
)
from app.features.training_schema import TrainingExample, TrainingLabel
from pydantic import ValidationError
from app.features.ranking_schema import (
    FeatureFilter,
    FilterOp,
    RankingSpec,
    RankingTerm,
    SearchResult,
    SortDirection,
)


# Feature schema

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


# Features training schema

T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_label_defaults_are_unobserved_and_not_withheld():
    lab = TrainingLabel()
    assert lab.hired is None and lab.outcome is None
    assert lab.coding_best_percentile is None and lab.event_at is None and lab.lag_days is None
    assert lab.observed is False and lab.withheld is False


def test_example_wraps_a_vector_and_label():
    fv = FeatureVector(candidate_id="c1", as_of=T, view_name="core_v1", view_version=1,
                       values={"candidate.num_skills": 3}, missing=())
    lab = TrainingLabel(hired=True, outcome="hired", event_at=T, lag_days=30.0, observed=True)
    ex = TrainingExample(vector=fv, label=lab)
    assert ex.vector.candidate_id == "c1"
    assert ex.label.hired is True and ex.label.outcome == "hired"


# Ranking schema

def test_comparison_filter_requires_a_value():
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE)


def test_exists_filter_forbids_a_value():
    ok = FeatureFilter(feature="candidate.has_github", op=FilterOp.EXISTS)
    assert ok.value is None
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.has_github", op=FilterOp.EXISTS, value=True)


def test_in_filter_requires_a_list_and_scalar_ops_reject_lists():
    ok = FeatureFilter(feature="candidate.location_tier", op=FilterOp.IN, value=["metro", "tier_2"])
    assert ok.value == ["metro", "tier_2"]
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.location_tier", op=FilterOp.IN, value="metro")
    with pytest.raises(ValidationError):
        FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE, value=[5])


def test_ranking_term_weight_must_be_positive_and_spec_non_empty():
    with pytest.raises(ValidationError):
        RankingTerm(feature="candidate.years_experience", weight=0.0)
    with pytest.raises(ValidationError):
        RankingSpec(terms=())
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=1.0),))
    assert spec.terms[0].direction is SortDirection.HIGHER_BETTER


def test_search_result_is_advisory_by_default():
    r = SearchResult(view_name="core_v1", view_version=1, pool_size=0, filtered_size=0)
    assert r.advisory is True and r.ranked == ()
