"""Repository fetch outcomes must not become claim verification."""

import httpx
import pytest

from app.services.github import GitHubClient


PRIVATE_DETAIL = "upstream-private-detail"


@pytest.mark.parametrize("mode", [403, 404, 429, 503, "timeout", "transport", "json", "shape"])
async def test_unavailable_repository_has_only_safe_diagnostics(settings, capsys, mode):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if mode == "timeout":
            raise httpx.ReadTimeout(PRIVATE_DETAIL, request=request)
        if mode == "transport":
            raise httpx.ConnectError(PRIVATE_DETAIL, request=request)
        if mode == "json":
            return httpx.Response(200, text=PRIVATE_DETAIL)
        if mode == "shape":
            return httpx.Response(200, json=[PRIVATE_DETAIL])
        return httpx.Response(mode, json={"message": PRIVATE_DETAIL})

    async with httpx.AsyncClient(base_url="https://api.github.com",
                                 transport=httpx.MockTransport(handler)) as http:
        result = await GitHubClient(settings, http).gather_repo_evidence("alice", "project")
    assert result.observations == []
    assert len(result.warnings) == 1
    assert "unavailable" in result.warnings[0]
    if mode == 404:
        assert "inaccessible" in result.warnings[0]
        assert "does not exist" not in result.warnings[0]
    assert calls == ["/repos/alice/project"]
    captured = capsys.readouterr()
    assert PRIVATE_DETAIL not in result.model_dump_json() + captured.out + captured.err


@pytest.mark.parametrize("component", ["languages", "commits"])
@pytest.mark.parametrize("mode", [403, 404, 429, 503, "timeout", "transport", "json", "shape"])
async def test_partial_failure_preserves_only_available_metadata(settings, component, mode):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/" + component):
            if mode == "timeout":
                raise httpx.ReadTimeout(PRIVATE_DETAIL, request=request)
            if mode == "transport":
                raise httpx.ConnectError(PRIVATE_DETAIL, request=request)
            if mode == "json":
                return httpx.Response(200, text=PRIVATE_DETAIL)
            if mode == "shape":
                payload = [] if component == "languages" else ["invalid commit"]
                return httpx.Response(200, json=payload)
            return httpx.Response(mode, json={"message": PRIVATE_DETAIL})
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 100})
        return httpx.Response(200, json={"language": "Python", "stargazers_count": 4})

    async with httpx.AsyncClient(base_url="https://api.github.com",
                                 transport=httpx.MockTransport(handler)) as http:
        result = await GitHubClient(settings, http).gather_repo_evidence("alice", "project")
    assert len(result.observations) == (1 if component == "languages" else 2)
    assert len(result.warnings) == 1
    assert component in result.warnings[0]
    assert PRIVATE_DETAIL not in result.model_dump_json()
    assert len(calls) == (2 if component == "languages" else 3)
    assert not any("Recent commits" in line for line in result.observations)


@pytest.mark.parametrize("commits", [[], [{"commit": {"author": {"date": "2026-10-01"}}}],
                                    [{"commit": None}], [{"commit": {"author": None}}]])
async def test_visible_public_metadata_is_context_not_ownership(settings, commits):
    def handler(request):
        if request.url.path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 100, "SQL": 50})
        if request.url.path.endswith("/commits"):
            assert request.url.params["per_page"] == "5"
            return httpx.Response(200, json=commits)
        return httpx.Response(200, json={"language": "Python", "stargazers_count": 4,
                                         "pushed_at": "2026-10-01"})

    async with httpx.AsyncClient(base_url="https://api.github.com",
                                 transport=httpx.MockTransport(handler)) as http:
        result = await GitHubClient(settings, http).gather_repo_evidence("alice", "project")
    assert result.warnings == []
    assert len(result.observations) == 3
    assert "alice/project" in result.observations[0]
    assert "Python, SQL" in result.observations[1]
    if not commits:
        assert "does not establish absence of work" in result.observations[2]
    else:
        assert "Recent commits visible (1 sampled)" in result.observations[2]
