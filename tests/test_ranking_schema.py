import pytest
from pydantic import ValidationError

from app.features.ranking_schema import (
    FeatureFilter, FilterOp, RankingSpec, RankingTerm, SearchResult, SortDirection,
)


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
