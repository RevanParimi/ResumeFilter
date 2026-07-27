from datetime import datetime, timezone

import pytest

from app.features.ranking import apply_filters
from app.features.ranking_schema import FeatureFilter, FilterOp
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec, FeatureVector

_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
DEGREE = FeatureSpec(name="candidate.highest_degree_level", version=1, dtype=FeatureDType.ORDINAL,
                     source=FeatureSource.CANDIDATE, description="x",
                     categories=("none", "diploma", "bachelor", "master", "doctorate"))
YEARS = FeatureSpec(name="candidate.years_experience", version=1, dtype=FeatureDType.NUMERIC,
                    source=FeatureSource.CANDIDATE, description="x", valid_range=(0.0, 60.0))
LOC = FeatureSpec(name="candidate.location_tier", version=1, dtype=FeatureDType.ORDINAL,
                  source=FeatureSource.CANDIDATE, description="x",
                  categories=("unknown", "tier_2", "metro"))
GITHUB = FeatureSpec(name="candidate.has_github", version=1, dtype=FeatureDType.BOOLEAN,
                     source=FeatureSource.CANDIDATE, description="x")
SPECS = {s.name: s for s in (DEGREE, YEARS, LOC, GITHUB)}


def _vec(cid, values):
    return FeatureVector(candidate_id=cid, as_of=_AS_OF, view_name="core_v1",
                         view_version=1, values=values)


def test_numeric_gte_filters():
    vs = [_vec("a", {"candidate.years_experience": 3.0}),
          _vec("b", {"candidate.years_experience": 8.0})]
    out = apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE, value=5)], SPECS)
    assert [v.candidate_id for v in out] == ["b"]


def test_ordinal_gte_uses_category_index():
    vs = [_vec("a", {"candidate.highest_degree_level": "bachelor"}),
          _vec("b", {"candidate.highest_degree_level": "master"}),
          _vec("c", {"candidate.highest_degree_level": "diploma"})]
    out = apply_filters(vs, [FeatureFilter(feature="candidate.highest_degree_level", op=FilterOp.GTE, value="bachelor")], SPECS)
    assert sorted(v.candidate_id for v in out) == ["a", "b"]


def test_in_and_eq_on_categorical():
    vs = [_vec("a", {"candidate.location_tier": "metro"}),
          _vec("b", {"candidate.location_tier": "tier_2"}),
          _vec("c", {"candidate.location_tier": "unknown"})]
    out = apply_filters(vs, [FeatureFilter(feature="candidate.location_tier", op=FilterOp.IN, value=["metro", "tier_2"])], SPECS)
    assert sorted(v.candidate_id for v in out) == ["a", "b"]


def test_missing_and_exists_and_null_fails_comparison():
    vs = [_vec("a", {"candidate.years_experience": 8.0}),
          _vec("b", {"candidate.years_experience": None})]
    assert [v.candidate_id for v in apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.EXISTS)], SPECS)] == ["a"]
    assert [v.candidate_id for v in apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.MISSING)], SPECS)] == ["b"]
    # a comparison against a null value never matches
    assert [v.candidate_id for v in apply_filters(vs, [FeatureFilter(feature="candidate.years_experience", op=FilterOp.GTE, value=1)], SPECS)] == ["a"]


def test_unknown_feature_raises_keyerror():
    with pytest.raises(KeyError):
        apply_filters([_vec("a", {})], [FeatureFilter(feature="nope.bad", op=FilterOp.EXISTS)], SPECS)


def test_ordered_op_on_boolean_raises_valueerror():
    vs = [_vec("a", {"candidate.has_github": True})]
    with pytest.raises(ValueError):
        apply_filters(vs, [FeatureFilter(feature="candidate.has_github", op=FilterOp.GT, value=True)], SPECS)
