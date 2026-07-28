"""Profile-source ingestion orchestration (S6.1).

Resolves a GitHub handle (explicit arg, else the candidate's profile GitHub
link), fetches the public signal, transforms it, and persists it. Advisory:
a missing/unreachable GitHub yields a stored ``method="unavailable"`` signal,
not an error. No LLM.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.candidates.schema import LinkType
from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.profile_sources.github import to_signal
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
from app.profile_sources.store import ProfileSourceStore, build_profile_source_store
from app.services.github import GitHubClient, GitHubService, parse_github_url

_LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}")


class ProfileSourceService:
    def __init__(
        self,
        *,
        github: GitHubService,
        store: ProfileSourceStore,
        candidates: CandidateStore,
        settings: Settings,
    ) -> None:
        self._github = github
        self._store = store
        self._candidates = candidates
        self._settings = settings

    async def ingest_github(
        self, candidate_id: str, handle: Optional[str] = None
    ) -> ProfileSourceSignal:
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"candidate {candidate_id} not found")
        login = self._resolve_handle(candidate_id, handle)
        raw = await self._github.gather_user_signal(login)
        signal = to_signal(raw, self._settings, fetched_at=datetime.now(timezone.utc))
        self._store.save_signal(candidate_id, signal)
        return signal

    def list_sources(
        self, candidate_id: str, source_type: Optional[ProfileSourceType] = None
    ) -> list[ProfileSourceSignal]:
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"candidate {candidate_id} not found")
        return self._store.signals_for_candidate(candidate_id, source_type)

    def _resolve_handle(self, candidate_id: str, handle: Optional[str]) -> str:
        if handle and handle.strip():
            return self._parse_login(handle.strip())
        profile = self._candidates.latest_profile(candidate_id)
        if profile is not None:
            for link in profile.links:
                if link.type == LinkType.GITHUB:
                    anchor = parse_github_url(link.url)
                    if anchor is not None and anchor.owner:
                        return anchor.owner
        raise ValueError("no GitHub handle supplied or found on the candidate profile")

    @staticmethod
    def _parse_login(raw: str) -> str:
        if "github.com" in raw:
            anchor = parse_github_url(raw)
            if anchor is not None and anchor.owner:
                return anchor.owner
            raise ValueError(f"unparseable GitHub URL: {raw}")
        if _LOGIN_RE.fullmatch(raw):
            return raw
        raise ValueError(f"invalid GitHub handle: {raw}")


def build_profile_source_service(
    settings: Optional[Settings] = None,
    *,
    github: Optional[GitHubService] = None,
    candidates: Optional[CandidateStore] = None,
) -> ProfileSourceService:
    settings = settings or get_settings()
    candidates = candidates or build_candidate_store(settings)
    github = github or GitHubClient(settings)
    store = build_profile_source_store(settings)
    return ProfileSourceService(
        github=github, store=store, candidates=candidates, settings=settings
    )
