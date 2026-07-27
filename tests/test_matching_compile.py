from app.core.config import Settings
from app.features.ranking_schema import FilterOp, SortDirection
from app.matching import match as M
from app.matching.schema import JobRequisitionInput, MatchWeights


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def test_ranking_has_skill_term_always():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",))
    terms = {t.feature: t for t in M.compile_ranking(req, _settings()).terms}
    assert M.SKILL_COVERAGE in terms
    assert terms[M.SKILL_COVERAGE].weight == 3.0  # match_skill_weight default
    # no other criteria set -> only the skill term
    assert set(terms) == {M.SKILL_COVERAGE}


def test_ranking_includes_set_scalar_terms_with_correct_direction():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",),
        min_years_experience=3.0, min_degree_level="bachelor",
        max_notice_days=30, location_tiers=("metro",),
    )
    terms = {t.feature: t for t in M.compile_ranking(req, _settings()).terms}
    assert terms["candidate.years_experience"].direction is SortDirection.HIGHER_BETTER
    assert terms["candidate.highest_degree_level"].direction is SortDirection.HIGHER_BETTER
    assert terms["candidate.notice_period_days"].direction is SortDirection.LOWER_BETTER
    assert M.LOCATION_FIT in terms


def test_remote_drops_location_term():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), location_tiers=("metro",), remote=True,
    )
    terms = {t.feature for t in M.compile_ranking(req, _settings()).terms}
    assert M.LOCATION_FIT not in terms


def test_weight_overrides_beat_defaults():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), min_years_experience=1.0,
        weights=MatchWeights(skill_coverage=5.0, years=2.0),
    )
    terms = {t.feature: t for t in M.compile_ranking(req, _settings()).terms}
    assert terms[M.SKILL_COVERAGE].weight == 5.0
    assert terms["candidate.years_experience"].weight == 2.0


def test_min_skill_coverage_becomes_one_filter():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",), min_skill_coverage=0.5)
    filters = M.compile_filters(req)
    assert len(filters) == 1
    assert filters[0].feature == M.SKILL_COVERAGE
    assert filters[0].op is FilterOp.GTE
    assert filters[0].value == 0.5


def test_no_filter_when_no_floor():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",))
    assert M.compile_filters(req) == []
