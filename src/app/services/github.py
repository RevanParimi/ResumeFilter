"""GitHub provenance — FIRST-PARTY only.

We fetch ONLY repos/users from URLs the candidate themselves shared. We never
scrape third-party profiles (DPDP consent-clean). Returns human-readable
evidence strings the provenance node embeds and the report surfaces.
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


class GitHubRepoRaw(BaseModel):
    name: str
    language: Optional[str] = None
    languages: dict[str, int] = Field(default_factory=dict)
    stargazers_count: int = 0
    pushed_at: Optional[str] = None
    fork: bool = False


class GitHubUserRaw(BaseModel):
    """Raw, source-shaped GitHub account data. ``available=False`` ⇒ the fetch
    could not complete (404 / rate-limit / network) — never an exception."""

    login: str
    available: bool = True
    public_repos: int = 0
    followers: int = 0
    account_created: Optional[str] = None
    repos: list[GitHubRepoRaw] = Field(default_factory=list)
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
    async def gather_repo_evidence(self, owner: str, repo: str) -> list[str]: ...
    async def gather_user_signal(self, login: str) -> "GitHubUserRaw": ...


class GitHubClient:
    """Thin async GitHub API client (injectable httpx client for tests)."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.settings = settings or get_settings()
        headers = {"Accept": "application/vnd.github+json"}
        if self.settings.has_github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token.get_secret_value()}"
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.github_api_base,
            headers=headers,
            timeout=20.0,
        )

    async def gather_repo_evidence(self, owner: str, repo: str) -> list[str]:
        """Repo existence + languages + recency/commit signal as evidence lines."""
        evidence: list[str] = []
        try:
            r = await self._client.get(f"/repos/{owner}/{repo}")
        except httpx.HTTPError as exc:  # network failure: report, don't crash
            log.warning("github_fetch_error", owner=owner, repo=repo, error=str(exc))
            return [f"GitHub fetch failed for {owner}/{repo}: {exc}"]

        if r.status_code == 404:
            return [f"GitHub repo {owner}/{repo} does not exist (claim anchor unverifiable)."]
        if r.status_code >= 400:
            return [f"GitHub returned {r.status_code} for {owner}/{repo}."]

        data = r.json()
        evidence.append(
            f"Repo {owner}/{repo} exists: stars={data.get('stargazers_count', 0)}, "
            f"primary_language={data.get('language')}, pushed_at={data.get('pushed_at')}."
        )

        langs = await self._safe_get_json(f"/repos/{owner}/{repo}/languages")
        if langs:
            evidence.append(f"Languages: {', '.join(langs.keys())}.")

        commits = await self._safe_get_json(f"/repos/{owner}/{repo}/commits?per_page=5")
        if isinstance(commits, list) and commits:
            last = commits[0].get("commit", {}).get("author", {}).get("date")
            evidence.append(f"Recent commits found ({len(commits)} sampled); latest {last}.")
        elif isinstance(commits, list):
            evidence.append("No commit history visible (empty or inaccessible).")
        return evidence

    async def gather_user_signal(self, login: str) -> GitHubUserRaw:
        """A user's public repos aggregated into a raw signal DTO. Any fetch
        failure yields available=False + a warning — never raises."""
        try:
            r = await self._client.get(f"/users/{login}")
        except httpx.HTTPError as exc:
            log.warning("github_user_fetch_error", login=login, error=str(exc))
            return GitHubUserRaw(
                login=login, available=False,
                warnings=[f"GitHub user fetch failed for {login}: {exc}"],
            )
        if r.status_code == 404:
            return GitHubUserRaw(
                login=login, available=False,
                warnings=[f"GitHub user {login} not found."],
            )
        if r.status_code >= 400:
            return GitHubUserRaw(
                login=login, available=False,
                warnings=[f"GitHub returned {r.status_code} for user {login}."],
            )
        u = r.json()
        repos_json = await self._safe_get_json(f"/users/{login}/repos?per_page=100&sort=pushed")
        repos_json = repos_json if isinstance(repos_json, list) else []
        repos_json = repos_json[: self.settings.ps_github_repo_limit]

        repos: list[GitHubRepoRaw] = []
        for i, rp in enumerate(repos_json):
            is_fork = bool(rp.get("fork", False))
            languages: dict[str, int] = {}
            if i < self.settings.ps_github_language_repos and not is_fork:
                langs = await self._safe_get_json(f"/repos/{login}/{rp.get('name')}/languages")
                if isinstance(langs, dict):
                    languages = {k: int(v) for k, v in langs.items()}
            repos.append(GitHubRepoRaw(
                name=rp.get("name", ""),
                language=rp.get("language"),
                languages=languages,
                stargazers_count=int(rp.get("stargazers_count", 0) or 0),
                pushed_at=rp.get("pushed_at"),
                fork=is_fork,
            ))
        return GitHubUserRaw(
            login=login, available=True,
            public_repos=int(u.get("public_repos", 0) or 0),
            followers=int(u.get("followers", 0) or 0),
            account_created=u.get("created_at"),
            repos=repos,
        )

    async def _safe_get_json(self, path: str):
        try:
            r = await self._client.get(path)
            if r.status_code < 400:
                return r.json()
        except httpx.HTTPError as exc:
            log.warning("github_subfetch_error", path=path, error=str(exc))
        return None

    async def aclose(self) -> None:
        await self._client.aclose()
