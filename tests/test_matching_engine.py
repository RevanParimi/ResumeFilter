from app.candidates.schema import CandidateProfile, ContactInfo, SkillItem
from app.core.config import Settings
from app.matching import match as M
from app.matching.schema import JobRequisitionInput


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _profile(skills=(), tier=None) -> CandidateProfile:
    return CandidateProfile(
        skills=[SkillItem(name=s, canonical=s) for s in skills],
        contact=ContactInfo(location_tier=tier),
    )


def test_synthetic_specs_are_valid_and_ranged():
    for name in (M.SKILL_COVERAGE, M.LOCATION_FIT):
        spec = M._SYNTHETIC_SPECS[name]
        assert spec.valid_range == (0.0, 1.0)
        assert spec.requires_consent is False


def test_canonical_skills_drops_uncanonical():
    p = _profile(skills=("python",))
    p.skills.append(SkillItem(name="mysterylang"))  # canonical=None
    assert M.canonical_skills(p) == {"python"}


def test_full_must_have_coverage():
    req = JobRequisitionInput(title="BE", must_have_skills=("python", "django"))
    sd = M.skill_coverage(req, {"python", "django"}, _settings())
    assert sd.coverage == 1.0
    assert sd.missing_must_have == ()


def test_partial_must_have_coverage():
    req = JobRequisitionInput(title="BE", must_have_skills=("python", "django", "aws"))
    sd = M.skill_coverage(req, {"python"}, _settings())
    assert sd.coverage == 1 / 3
    assert set(sd.missing_must_have) == {"django", "aws"}


def test_nice_to_have_blend():
    # both sets present: must_frac=1.0, nice_frac=0.5, f=0.3 -> 1.0*0.7 + 0.5*0.3
    req = JobRequisitionInput(
        title="BE", must_have_skills=("python",), nice_to_have_skills=("aws", "gcp"),
    )
    sd = M.skill_coverage(req, {"python", "aws"}, _settings())
    assert abs(sd.coverage - (1.0 * 0.7 + 0.5 * 0.3)) < 1e-9
    assert sd.matched_nice_to_have == ("aws",)


def test_pure_nice_to_have_uses_nice_frac():
    req = JobRequisitionInput(title="BE", nice_to_have_skills=("aws", "gcp"))
    sd = M.skill_coverage(req, {"aws"}, _settings())
    assert sd.coverage == 0.5


def test_location_fit_variants():
    base = dict(title="BE", must_have_skills=("python",))
    metro = JobRequisitionInput(**base, location_tiers=("metro",))
    assert M.location_fit(metro, "metro") == 1.0
    assert M.location_fit(metro, "tier_2") == 0.0
    assert M.location_fit(metro, None) is None            # unknown -> drops
    remote = JobRequisitionInput(**base, location_tiers=("metro",), remote=True)
    assert M.location_fit(remote, "metro") is None        # remote -> no term
    no_tiers = JobRequisitionInput(**base)
    assert M.location_fit(no_tiers, "metro") is None
