from datetime import datetime, timezone

from app.profile_sources.schema import (
    GitHubActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)


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
