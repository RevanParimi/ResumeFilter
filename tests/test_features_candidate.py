from datetime import datetime, timezone
from app.candidates.schema import (
    CandidateProfile, ContactInfo, DateRange, EducationEntry, ExperienceEntry,
    LinkItem, LinkType, SkillItem,
)
from app.features.registry import FeatureRegistry, _register
import app.features.definitions.candidate as cand
from app.features.schema import FeatureContext


AS_OF = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ctx(profile):
    return FeatureContext(candidate_id="c1", as_of=AS_OF, profile=profile)


def test_years_experience_merges_overlaps():
    # 2020-01..2021-12 (24m) overlapping 2021-01..2022-12 (24m) -> union 36m = 3.0y
    p = CandidateProfile(experience=[
        ExperienceEntry(dates=DateRange(start="2020-01", end="2021-12")),
        ExperienceEntry(dates=DateRange(start="2021-01", end="2022-12")),
    ])
    assert cand.years_experience(_ctx(p)) == 3.0


def test_years_experience_is_current_uses_as_of():
    p = CandidateProfile(experience=[
        ExperienceEntry(dates=DateRange(start="2023-01", is_current=True)),
    ])
    # 2023-01 .. 2024-01 inclusive = 13 months
    assert cand.years_experience(_ctx(p)) == round(13 / 12, 2)


def test_years_experience_none_without_dates():
    assert cand.years_experience(_ctx(CandidateProfile())) is None


def test_highest_degree_level_ordinal():
    p = CandidateProfile(education=[
        EducationEntry(degree_level="bachelor"),
        EducationEntry(degree_level="master"),
    ])
    assert cand.highest_degree_level(_ctx(p)) == "master"
    assert cand.highest_degree_level(_ctx(CandidateProfile())) == "none"


def test_top_institution_tier_and_cgpa():
    p = CandidateProfile(education=[
        EducationEntry(institution_tier="tier_2", grade_cgpa_10=7.5),
        EducationEntry(institution_tier="tier_1", grade_cgpa_10=8.9),
    ])
    assert cand.top_institution_tier(_ctx(p)) == "tier_1"
    assert cand.max_cgpa_10(_ctx(p)) == 8.9
    assert cand.max_cgpa_10(_ctx(CandidateProfile())) is None


def test_has_github_and_counts():
    p = CandidateProfile(
        skills=[SkillItem(name="python", canonical="python"), SkillItem(name="foo")],
        links=[LinkItem(type=LinkType.GITHUB, url="https://github.com/x")],
    )
    assert cand.has_github(_ctx(p)) is True
    assert cand.num_skills(_ctx(p)) == 2
    assert cand.num_canonical_skills(_ctx(p)) == 1
    assert cand.has_github(_ctx(CandidateProfile())) is False


def test_location_and_notice():
    p = CandidateProfile(
        contact=ContactInfo(location_tier="metro"), notice_period_days=45,
    )
    assert cand.location_tier(_ctx(p)) == "metro"
    assert cand.notice_period_days(_ctx(p)) == 45


def test_all_candidate_features_registered_and_validated():
    # Every candidate.* feature computes + validates on a rich profile.
    reg = FeatureRegistry()
    from app.features.registry import _DEFAULT_REGISTRY
    for rf in _DEFAULT_REGISTRY._by_key.values():
        if rf.spec.source.value == "candidate":
            _register(rf.spec, rf.fn, registry=reg)
    p = CandidateProfile(
        experience=[ExperienceEntry(dates=DateRange(start="2020-01", end="2022-01"))],
        education=[EducationEntry(degree_level="master", institution_tier="tier_1", grade_cgpa_10=9.0)],
        skills=[SkillItem(name="python", canonical="python")],
    )
    for name in reg.names():
        reg.compute_one(name, _ctx(p))   # raises if any output violates its spec
