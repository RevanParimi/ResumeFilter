from datetime import datetime, timezone

from app.core.config import Settings
from app.profile_sources.linkedin import (
    LinkedInEducationRaw, LinkedInExportRaw, LinkedInPositionRaw, to_signal,
)
from app.profile_sources.schema import LinkedInActivity, ProfileSourceType

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def _raw(**kw):
    base = dict(available=True, skills=[], positions=[], education=[])
    base.update(kw)
    return LinkedInExportRaw(**base)


def test_maps_canonical_and_keeps_unknown():
    raw = _raw(skills=["Python", "Wingdings"])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.source_type == ProfileSourceType.LINKEDIN_EXPORT
    assert sig.method == "export"
    by = {s.name: s for s in sig.skills}
    assert by["Python"].canonical == "python"
    assert by["Wingdings"].canonical is None


def test_corroboration_bumps_confidence_and_weight():
    raw = _raw(
        skills=["Python", "Leadership"],
        positions=[LinkedInPositionRaw(title="Python Developer", description="Built services")],
        headline="Senior Python Engineer",
    )
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    by = {s.name: s for s in sig.skills}
    # Python appears in a position title AND the headline -> corroborated.
    assert by["Python"].confidence == 0.6
    assert by["Python"].weight >= 1
    # Leadership appears nowhere in positions/headline -> base.
    assert by["Leadership"].confidence == 0.4
    assert by["Leadership"].weight == 0
    # sorted corroborated-first.
    assert sig.skills[0].name == "Python"


def test_short_skill_names_do_not_substring_false_match():
    # "Go" must not match "Good"; token-based corroboration.
    raw = _raw(skills=["Go"], positions=[LinkedInPositionRaw(title="Good manager", description="")])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.skills[0].weight == 0
    assert sig.skills[0].confidence == 0.4


def test_duplicate_skill_collapses_keeping_max_corroboration():
    raw = _raw(skills=["Python", "python"],
               positions=[LinkedInPositionRaw(title="Python dev", description="")])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    pys = [s for s in sig.skills if s.name.lower() == "python"]
    assert len(pys) == 1
    assert pys[0].confidence == 0.6


def test_activity_aggregates_and_canonicalizes():
    raw = _raw(
        skills=["Python"],
        positions=[
            LinkedInPositionRaw(company="Infosys Technologies", finished_on="Dec 2021"),
            LinkedInPositionRaw(company="TCS", finished_on=""),
        ],
        education=[LinkedInEducationRaw(school="IIT Madras", degree="B.Tech")],
        certifications=["AWS SAA"],
        languages=["English", "Hindi"],
        headline="Engineer",
        industry="IT",
    )
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    act = sig.activity
    assert isinstance(act, LinkedInActivity)
    assert act.positions_count == 2
    assert act.current_positions == 1
    assert act.employers == ["Infosys", "TCS"]        # canonical, deduped, ordered
    assert act.institutions == ["IIT Madras"]
    assert act.education_count == 1
    assert act.certifications_count == 1
    assert act.languages == ["English", "Hindi"]
    assert act.skills_listed == 1


def test_unavailable_raw_yields_unavailable_signal():
    raw = LinkedInExportRaw(available=False, warnings=["not a valid zip archive"])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.method == "unavailable"
    assert sig.skills == []
    assert isinstance(sig.activity, LinkedInActivity)
    assert sig.warnings == ["not a valid zip archive"]


def test_trailing_period_still_corroborates():
    # "Worked in Python." has a trailing period that should not prevent corroboration.
    raw = _raw(
        skills=["Python"],
        positions=[LinkedInPositionRaw(title="Developer", description="Worked in Python.")],
    )
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    py = [s for s in sig.skills if s.name == "Python"][0]
    assert py.weight >= 1
    assert py.confidence == 0.6


def test_dotnet_at_sentence_end_corroborates():
    # ".NET." at the end of a sentence should still corroborate a ".NET" skill.
    raw = _raw(
        skills=[".NET"],
        positions=[LinkedInPositionRaw(title="Engineer", description="Built microservices in .NET.")],
    )
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    dotnet = [s for s in sig.skills if s.name == ".NET"][0]
    assert dotnet.weight >= 1
    assert dotnet.confidence == 0.6
