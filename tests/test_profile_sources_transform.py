from datetime import datetime, timezone

from app.core.config import Settings
from app.profile_sources.github import PRIMARY_LANGUAGE_NOMINAL_BYTES, to_signal
from app.services.github import GitHubRepoRaw, GitHubUserRaw

FETCHED = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def _raw(**kw):
    return GitHubUserRaw(login="octocat", available=True, public_repos=3, followers=5,
                         account_created="2011-01-25T18:44:36Z", **kw)


def test_aggregates_languages_and_maps_canonical():
    raw = _raw(repos=[
        GitHubRepoRaw(name="a", languages={"Python": 8000, "HTML": 500}, stargazers_count=3, pushed_at="2025-01-05T00:00:00Z"),
        GitHubRepoRaw(name="b", languages={"Python": 2000, "Go": 4000}, stargazers_count=1, pushed_at="2024-06-01T00:00:00Z"),
    ])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.method == "api"
    by_name = {s.name: s for s in sig.skills}
    assert by_name["Python"].weight == 10000
    assert by_name["Python"].canonical == "python"
    assert by_name["Go"].canonical == "go"
    # skills sorted by weight desc: Python (10000) first.
    assert sig.skills[0].name == "Python"
    assert sig.activity.total_stars == 4
    assert sig.activity.most_recent_push == "2025-01-05T00:00:00Z"
    assert sig.activity.sampled_repos == 2


def test_unknown_language_kept_with_none_canonical():
    raw = _raw(repos=[GitHubRepoRaw(name="a", languages={"Brainfuck": 500})])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    bf = next(s for s in sig.skills if s.name == "Brainfuck")
    assert bf.canonical is None and bf.category is None


def test_confidence_is_bounded_and_monotone():
    raw = _raw(repos=[GitHubRepoRaw(name="a", languages={"Python": 10000, "Ruby": 1000})])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    conf = {s.name: s.confidence for s in sig.skills}
    assert conf["Python"] == 0.9            # dominant hits the cap
    assert 0.3 <= conf["Ruby"] < conf["Python"]  # smaller share, lower, floored at 0.3


def test_forks_excluded_by_default_included_when_configured():
    raw = _raw(repos=[
        GitHubRepoRaw(name="mine", languages={"Python": 5000}, fork=False),
        GitHubRepoRaw(name="forked", languages={"Java": 9000}, fork=True),
    ])
    default = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert {s.name for s in default.skills} == {"Python"}
    assert default.activity.sampled_repos == 1
    withforks = to_signal(raw, _settings(ps_github_include_forks=True), fetched_at=FETCHED)
    assert {s.name for s in withforks.skills} == {"Python", "Java"}


def test_primary_language_only_repo_uses_nominal_weight():
    raw = _raw(repos=[GitHubRepoRaw(name="a", language="Python", languages={})])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.skills[0].weight == PRIMARY_LANGUAGE_NOMINAL_BYTES


def test_unavailable_raw_produces_unavailable_signal():
    raw = GitHubUserRaw(login="ghost", available=False, warnings=["GitHub user ghost not found."])
    sig = to_signal(raw, _settings(), fetched_at=FETCHED)
    assert sig.method == "unavailable"
    assert sig.skills == []
    assert sig.identifier == "ghost"
    assert sig.warnings == ["GitHub user ghost not found."]
