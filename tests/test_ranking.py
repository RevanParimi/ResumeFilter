import pytest

from app.features.ranking import normalize_value
from app.features.ranking_schema import SortDirection
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec

YEARS = FeatureSpec(name="candidate.years_experience", version=1, dtype=FeatureDType.NUMERIC,
                    source=FeatureSource.CANDIDATE, description="x", valid_range=(0.0, 60.0))
DEGREE = FeatureSpec(name="candidate.highest_degree_level", version=1, dtype=FeatureDType.ORDINAL,
                     source=FeatureSource.CANDIDATE, description="x",
                     categories=("none", "diploma", "bachelor", "master", "doctorate"))
GITHUB = FeatureSpec(name="candidate.has_github", version=1, dtype=FeatureDType.BOOLEAN,
                     source=FeatureSource.CANDIDATE, description="x")
COUNT = FeatureSpec(name="candidate.num_experiences", version=1, dtype=FeatureDType.INTEGER,
                    source=FeatureSource.CANDIDATE, description="x")  # no valid_range
CATEG = FeatureSpec(name="candidate.some_cat", version=1, dtype=FeatureDType.CATEGORICAL,
                    source=FeatureSource.CANDIDATE, description="x", categories=("a", "b"))


def test_numeric_uses_valid_range_and_clamps():
    assert normalize_value(YEARS, 30.0) == pytest.approx(0.5)
    assert normalize_value(YEARS, 999.0) == 1.0  # clamp above hi


def test_ordinal_uses_category_index():
    assert normalize_value(DEGREE, "master") == pytest.approx(3 / 4)
    assert normalize_value(DEGREE, "none") == 0.0


def test_boolean_and_none():
    assert normalize_value(GITHUB, True) == 1.0
    assert normalize_value(GITHUB, False) == 0.0
    assert normalize_value(GITHUB, None) is None


def test_lower_better_inverts():
    assert normalize_value(YEARS, 30.0, direction=SortDirection.LOWER_BETTER) == pytest.approx(0.5)
    assert normalize_value(YEARS, 0.0, direction=SortDirection.LOWER_BETTER) == 1.0


def test_range_less_numeric_falls_back_to_pool_min_max():
    # pool 2..10 -> value 6 normalizes to 0.5
    assert normalize_value(COUNT, 6, pool=[2, 4, 10]) == pytest.approx(0.5)
    # degenerate pool (all equal / singleton) -> neutral 0.5
    assert normalize_value(COUNT, 5, pool=[5]) == 0.5
    assert normalize_value(COUNT, 5, pool=None) == 0.5


def test_non_ordinal_categorical_is_not_rankable():
    with pytest.raises(ValueError):
        normalize_value(CATEG, "a")
