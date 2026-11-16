"""GitHub provenance — FIRST-PARTY only.

We fetch ONLY repos/users from URLs the candidate themselves shared. We never
scrape third-party profiles (DPDP consent-clean). Returns human-readable
repository observations and fetch diagnostics separately. Repository metadata
does not verify a claim or the candidate's ownership.
"""

from __future__ import annotations

from typing import Optional, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.claims import AnchorType, ExternalAnchor

log = get_logger(__name__)


class GitHubRepoEvidence(BaseModel):
    """Visible repository metadata and unavailable fetch context, kept separate."""

    observations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def parse_github_url(url: str) -> Optional[ExternalAnchor]:
    """Turn a GitHub URL into an anchor (repo or user). None if not GitHub."""
    try:
        p = urlparse(url)
    except (ValueError, TypeError):
        return None
    if "github.com" not in (p.netloc or ""):
        return None
    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) >= 2:
        return ExternalAnchor(
            type=AnchorType.GITHUB_REPO, url=url, owner=parts[0], repo=parts[1]
        )
    if len(parts) == 1:
        return ExternalAnchor(type=AnchorType.GITHUB_USER, url=url, owner=parts[0])
    return None


class GitHubService(Protocol):
    async def gather_repo_evidence(self, owner: str, repo: str) -> GitHubRepoEvidence: ...


class GitHubClient:
    """Thin async GitHub API client (injectable httpx client for tests)."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._closed = False

    def _get_client(self):
        if self._closed:
            raise RuntimeError("GitHub client is closed")
        if self._client is not None:
            return self._client
        headers = {"Accept": "application/vnd.github+json"}
        if self.settings.has_github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token.get_secret_value()}"
        self._client = httpx.AsyncClient(
            base_url=self.settings.github_api_base,
            headers=headers,
            timeout=20.0,
        )
        return self._client

    async def _repo_get_json(self, path: str, component: str):
        """Fixed diagnostics omit upstream bodies and exception details."""
        try:
            r = await self._get_client().get(path)
        except httpx.HTTPError as exc:
            log.warning("github_repo_fetch_error", component=component, error_type=type(exc).__name__)
            reason = "request timed out" if isinstance(exc, httpx.TimeoutException) else "request failed"
            return None, f"GitHub {component} unavailable: {reason}."
        if r.status_code == 404:
            return None, f"GitHub {component} unavailable: not found or inaccessible (HTTP 404)."
        if r.status_code in (403, 429):
            return None, f"GitHub {component} unavailable: access denied or rate limited (HTTP {r.status_code})."
        if r.status_code != 200:
            return None, f"GitHub {component} unavailable: HTTP {r.status_code}."
        try:
            return r.json(), None
        except ValueError:
            log.warning("github_repo_response_invalid", component=component)
            return None, f"GitHub {component} unavailable: invalid response."

    async def gather_repo_evidence(self, owner: str, repo: str) -> GitHubRepoEvidence:
        """Public metadata is context only; partial failures remain explicit."""
        result = GitHubRepoEvidence()
        path = f"/repos/{owner}/{repo}"
        data, warning = await self._repo_get_json(path, "repository")
        if warning or not isinstance(data, dict):
            result.warnings.append(warning or "GitHub repository unavailable: invalid response.")
            return result
        result.observations.append(
            f"Repo {owner}/{repo} is visible: stars={data.get('stargazers_count', 0)}, "
            f"primary_language={data.get('language')}, pushed_at={data.get('pushed_at')}."
        )

        langs, warning = await self._repo_get_json(path + "/languages", "languages")
        if warning or not isinstance(langs, dict):
            result.warnings.append(warning or "GitHub languages unavailable: invalid response.")
            # Do not issue another request immediately after a failed/rate-limited fetch.
            return result
        if langs:
            result.observations.append(f"Languages: {', '.join(langs.keys())}.")

        commits, warning = await self._repo_get_json(path + "/commits?per_page=5", "commits")
        if warning or not isinstance(commits, list) or any(not isinstance(c, dict) for c in commits):
            result.warnings.append(warning or "GitHub commits unavailable: invalid response.")
        elif commits:
            commit = commits[0].get("commit")
            author = commit.get("author") if isinstance(commit, dict) else None
            last = author.get("date") if isinstance(author, dict) else None
            result.observations.append(f"Recent commits visible ({len(commits)} sampled); latest {last}.")
        else:
            result.observations.append("Public commit sample is empty; this does not establish absence of work.")
        return result

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            await self._client.aclose()
