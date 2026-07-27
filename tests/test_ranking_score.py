from datetime import datetime, timezone

import pytest

from app.features.ranking import score
from app.features.ranking_schema import RankingSpec, RankingTerm
from app.features.schema import FeatureDType, FeatureSource, FeatureSpec, FeatureVector

_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)
YEARS = FeatureSpec(name="candidate.years_experience", version=1, dtype=FeatureDType.NUMERIC,
                    source=FeatureSource.CANDIDATE, description="x", valid_range=(0.0, 60.0))
REP = FeatureSpec(name="reputation.score", version=1, dtype=FeatureDType.NUMERIC,
                  source=FeatureSource.REPUTATION, description="x",
                  valid_range=(0.0, 1.0), nullable=False, requires_consent=True)
SPECS = {YEARS.name: YEARS, REP.name: REP}


def _vec(cid, values):
    return FeatureVector(candidate_id=cid, as_of=_AS_OF, view_name="core_v1",
                         view_version=1, values=values)


def test_weighted_mean_and_sort_desc():
    vs = [_vec("a", {"candidate.years_experience": 6.0}),   # 0.1
          _vec("b", {"candidate.years_experience": 30.0})]  # 0.5
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=1.0),))
    ranked = score(vs, spec, SPECS)
    assert [r.candidate_id for r in ranked] == ["b", "a"]
    assert ranked[0].score == pytest.approx(0.5) and ranked[0].coverage == 1.0
    assert ranked[0].contributions[0].normalized == pytest.approx(0.5)


def test_missing_term_renormalizes_and_reports_coverage():
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=0.6),
                              RankingTerm(feature="reputation.score", weight=0.4)))
    v = _vec("a", {"candidate.years_experience": 30.0, "reputation.score": None})
    r = score([v], spec, SPECS)[0]
    assert r.missing == ("reputation.score",)
    assert r.coverage == pytest.approx(0.6)          # 0.6 of 1.0 total weight had data
    assert r.score == pytest.approx(0.5)             # only the present term counts


def test_consent_withheld_is_never_penalized_below_a_present_low_value():
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=0.5),
                              RankingTerm(feature="reputation.score", weight=0.5)))
    withheld = _vec("withheld", {"candidate.years_experience": 30.0, "reputation.score": None})
    low = _vec("low", {"candidate.years_experience": 30.0, "reputation.score": 0.1})
    ranked = {r.candidate_id: r for r in score([withheld, low], spec, SPECS)}
    assert ranked["withheld"].score >= ranked["low"].score
    assert ranked["withheld"].score == pytest.approx(0.5)  # scored on the present term alone


def test_tie_break_is_candidate_id_asc():
    spec = RankingSpec(terms=(RankingTerm(feature="candidate.years_experience", weight=1.0),))
    vs = [_vec("z", {"candidate.years_experience": 30.0}),
          _vec("a", {"candidate.years_experience": 30.0})]
    assert [r.candidate_id for r in score(vs, spec, SPECS)] == ["a", "z"]


def test_all_terms_missing_scores_zero_coverage_zero():
    spec = RankingSpec(terms=(RankingTerm(feature="reputation.score", weight=1.0),))
    r = score([_vec("a", {"reputation.score": None})], spec, SPECS)[0]
    assert r.score == 0.0 and r.coverage == 0.0 and r.missing == ("reputation.score",)


def test_unknown_ranking_feature_raises_keyerror():
    spec = RankingSpec(terms=(RankingTerm(feature="nope.bad", weight=1.0),))
    with pytest.raises(KeyError):
        score([_vec("a", {})], spec, SPECS)
