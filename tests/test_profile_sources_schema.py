from datetime import datetime, timezone

from app.profile_sources.schema import (
    GitHubActivity, LinkedInActivity, ProfileSourceSignal, ProfileSourceType,
    SourceSkillSignal,
)

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def test_source_skill_signal_defaults_and_bounds():
    s = SourceSkillSignal(name="Python", canonical="python", category="language", weight=10000)
    assert s.confidence == 0.5  # default until the transform sets it
    assert s.weight == 10000
    assert s.canonical == "python"


def test_profile_source_signal_available_shape():
    sig = ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB,
        identifier="octocat",
        skills=[SourceSkillSignal(name="Python", canonical="python", category="language", weight=10000, confidence=0.9)],
        activity=GitHubActivity(public_repos=8, total_stars=42, sampled_repos=8),
        method="api",
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
    )
    assert sig.id.startswith("psrc_")
    assert sig.advisory is True
    assert sig.method == "api"
    assert sig.activity.total_stars == 42


def test_profile_source_signal_unavailable_shape():
    sig = ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB,
        identifier="ghost",
        method="unavailable",
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
        warnings=["GitHub user ghost not found."],
    )
    assert sig.skills == []
    assert sig.activity.top_languages == {}
    assert sig.warnings == ["GitHub user ghost not found."]


def test_linkedin_signal_roundtrips_through_json():
    sig = ProfileSourceSignal(
        source_type=ProfileSourceType.LINKEDIN_EXPORT,
        identifier="linkedin_export",
        skills=[SourceSkillSignal(name="Python", canonical="python", weight=2, confidence=0.6)],
        activity=LinkedInActivity(positions_count=2, employers=["Infosys"], headline="Engineer"),
        method="export",
        fetched_at=FETCHED,
    )
    back = ProfileSourceSignal.model_validate(sig.model_dump(mode="json"))
    assert isinstance(back.activity, LinkedInActivity)
    assert back.activity.employers == ["Infosys"]
    assert back.method == "export"


def test_pre_s62_github_row_without_kind_still_validates():
    # A row stored before S6.2 has no activity.kind; the discriminator is
    # backfilled from the top-level source_type.
    legacy = {
        "id": "psrc_legacy01",
        "source_type": "github",
        "identifier": "octocat",
        "skills": [],
        "activity": {"public_repos": 3, "followers": 5, "total_stars": 4,
                     "top_languages": {"Python": 10}, "sampled_repos": 2},
        "method": "api",
        "fetched_at": "2026-07-28T00:00:00Z",
        "warnings": [],
        "advisory": True,
    }
    back = ProfileSourceSignal.model_validate(legacy)
    assert isinstance(back.activity, GitHubActivity)
    assert back.activity.public_repos == 3
