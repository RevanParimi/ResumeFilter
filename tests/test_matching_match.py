from datetime import datetime, timezone

from app.candidates.schema import CandidateProfile, ContactInfo, SkillItem
from app.core.config import Settings
from app.features.schema import FeatureVector
from app.matching import match as M
from app.matching.schema import JobRequisitionInput


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _vec(cid: str, values: dict) -> FeatureVector:
    return FeatureVector(
        candidate_id=cid, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        view_name="core_v1", view_version=1, values=values,
    )


def _profile(skills=(), tier=None) -> CandidateProfile:
    return CandidateProfile(
        skills=[SkillItem(name=s, canonical=s) for s in skills],
        contact=ContactInfo(location_tier=tier),
    )


def test_full_skill_candidate_outranks_partial():
    req = JobRequisitionInput(title="BE", must_have_skills=("python", "django"))
    vectors = [_vec("a", {}), _vec("b", {})]
    profiles = {"a": _profile(("python", "django")), "b": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, {}, _settings())
    assert [m.candidate_id for m in ranked] == ["a", "b"]
    assert ranked[0].skill.coverage == 1.0
    assert ranked[1].skill.coverage == 0.5


def test_missing_scalar_feature_drops_term_not_candidate():
    # requisition ranks on skills + years; candidate b has no years feature at all.
    from app.features import get_feature_registry
    reg = get_feature_registry()
    specs = {"candidate.years_experience": reg.get("candidate.years_experience").spec}
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), min_years_experience=2.0,
    )
    vectors = [_vec("a", {"candidate.years_experience": 8.0}), _vec("b", {})]
    profiles = {"a": _profile(("python",)), "b": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, specs, _settings())
    ids = {m.candidate_id for m in ranked}
    assert ids == {"a", "b"}  # b NOT dropped
    b = next(m for m in ranked if m.candidate_id == "b")
    assert "candidate.years_experience" in b.missing
    assert b.coverage < 1.0  # its years term had no data


def test_min_skill_coverage_gate_drops_below_floor():
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python", "django"), min_skill_coverage=0.75,
    )
    vectors = [_vec("a", {}), _vec("b", {})]
    profiles = {"a": _profile(("python", "django")), "b": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, {}, _settings())
    assert [m.candidate_id for m in ranked] == ["a"]  # b (0.5) gated out


def test_deterministic_tie_break_by_candidate_id():
    req = JobRequisitionInput(title="BE", must_have_skills=("python",))
    vectors = [_vec("z", {}), _vec("a", {})]
    profiles = {"z": _profile(("python",)), "a": _profile(("python",))}
    ranked = M.match(req, vectors, profiles, {}, _settings())
    assert [m.candidate_id for m in ranked] == ["a", "z"]  # equal score -> id asc
