import httpx
import pytest

from app.core.config import Settings
from app.services.github import GitHubClient, GitHubUserRaw


def _client(handler, settings=None):
    transport = httpx.MockTransport(handler)
    ac = httpx.AsyncClient(base_url="https://api.github.com", transport=transport)
    return GitHubClient(settings=settings or Settings(_env_file=None, openrouter_api_key=""), client=ac)


@pytest.mark.asyncio
async def test_gather_user_signal_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/users/octocat":
            return httpx.Response(200, json={"public_repos": 2, "followers": 5, "created_at": "2011-01-25T18:44:36Z"})
        if p == "/users/octocat/repos":
            return httpx.Response(200, json=[
                {"name": "hello", "language": "Python", "stargazers_count": 3, "pushed_at": "2025-01-05T00:00:00Z", "fork": False},
                {"name": "world", "language": "Go", "stargazers_count": 1, "pushed_at": "2024-06-01T00:00:00Z", "fork": False},
            ])
        if p == "/repos/octocat/hello/languages":
            return httpx.Response(200, json={"Python": 10000, "HTML": 500})
        if p == "/repos/octocat/world/languages":
            return httpx.Response(200, json={"Go": 8000})
        return httpx.Response(404, json={})

    raw = await _client(handler).gather_user_signal("octocat")
    assert isinstance(raw, GitHubUserRaw)
    assert raw.available is True
    assert raw.public_repos == 2
    assert {r.name for r in raw.repos} == {"hello", "world"}
    hello = next(r for r in raw.repos if r.name == "hello")
    assert hello.languages == {"Python": 10000, "HTML": 500}


@pytest.mark.asyncio
async def test_gather_user_signal_unknown_user_is_unavailable():
    def handler(request):
        return httpx.Response(404, json={})
    raw = await _client(handler).gather_user_signal("ghost")
    assert raw.available is False
    assert raw.repos == []
    assert any("ghost" in w for w in raw.warnings)


@pytest.mark.asyncio
async def test_gather_user_signal_network_error_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("boom")
    raw = await _client(handler).gather_user_signal("octocat")
    assert raw.available is False
    assert any("failed" in w.lower() for w in raw.warnings)
