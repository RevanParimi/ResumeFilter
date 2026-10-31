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
from app.core.blocking import BoundedExecutor
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.curation.service import CurationService, reviewable_raw_term
from app.profile_sources.github import to_signal as github_to_signal
from app.profile_sources.linkedin import parse_linkedin_export
from app.profile_sources.linkedin import to_signal as linkedin_to_signal
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
from app.profile_sources.store import ProfileSourceStore, SourceSubjectErasedError, build_profile_source_store
from app.services.github import GitHubClient, GitHubService, parse_github_url

_LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}")


_log = get_logger("profile_sources.service")


class ProfileSourceService:
    def __init__(
        self,
        *,
        github: GitHubService,
        store: ProfileSourceStore,
        candidates: CandidateStore,
        settings: Settings,
        curation: Optional[CurationService] = None,
    ) -> None:
        self._github = github
        self._store = store
        self._candidates = candidates
        self._settings = settings
        self._curation = curation

    async def ingest_github(
        self, candidate_id: str, handle: Optional[str] = None, *,
        executor: Optional[BoundedExecutor] = None,
    ) -> ProfileSourceSignal:
        # HTTP supplies the shared record pool. Direct callers own scheduling.
        # Admission/wait is separate before and after the caller-owned provider.
        if executor is None:
            login = self._github_login(candidate_id, handle)
        else:
            login = await executor.run(self._github_login, candidate_id, handle)
        raw = await self._github.gather_user_signal(login)
        signal = github_to_signal(raw, self._settings, fetched_at=datetime.now(timezone.utc))
        if executor is None:
            self._save_github_signal(candidate_id, signal)
        else:
            await executor.run(self._save_github_signal, candidate_id, signal)
        return signal

    def _github_login(self, candidate_id: str, handle: Optional[str]) -> str:
        if self._candidates.get_candidate(candidate_id) is None:
            raise SourceSubjectErasedError()
        return self._resolve_handle(candidate_id, handle)

    def _save_github_signal(self, candidate_id: str, signal: ProfileSourceSignal) -> None:
        # Own all save/curation/final-guard sessions. A late completion may
        # commit; it never resumes an abandoned caller or repeats the provider.
        row_id = self._store.save_signal(candidate_id, signal)
        self._capture_unmapped(signal, source_id=row_id)
        self._store.require_saved_signal(candidate_id, row_id)

    async def ingest_linkedin(
        self, candidate_id: str, data: bytes
    ) -> ProfileSourceSignal:
        if self._candidates.get_candidate(candidate_id) is None:
            raise SourceSubjectErasedError()
        raw = parse_linkedin_export(data, self._settings)
        signal = linkedin_to_signal(
            raw, self._settings, fetched_at=datetime.now(timezone.utc)
        )
        row_id = self._store.save_signal(candidate_id, signal)
        self._capture_unmapped(signal, source_id=row_id, raw_names=raw.skills)
        self._store.require_saved_signal(candidate_id, row_id)
        return signal

    def list_sources(
        self, candidate_id: str, source_type: Optional[ProfileSourceType] = None
    ) -> list[ProfileSourceSignal]:
        if self._candidates.get_candidate(candidate_id) is None:
            raise SourceSubjectErasedError()
        signals = self._store.signals_for_candidate(candidate_id, source_type)
        # A loaded list is only a snapshot. Refuse erasure observed before
        # return; this read does not lock subsequent HTTP delivery.
        if self._candidates.get_candidate(candidate_id) is None:
            raise SourceSubjectErasedError()
        return signals

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
        if self._candidates.get_candidate(candidate_id) is None:
            raise SourceSubjectErasedError()
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

    def _capture_unmapped(
        self, signal: ProfileSourceSignal, *, source_id: str,
        raw_names: Optional[list[str]] = None,
    ) -> None:
        """Queue every skill the taxonomy couldn't map (canonical is None) for
        curation review. Best-effort — capture must never break ingestion."""
        if self._curation is None:
            return
        names = [skill.name for skill in signal.skills if skill.canonical is None]
        if raw_names is not None:
            # LinkedIn display names are trimmed and case-deduplicated. Check
            # original CSV cells so padding/controls cannot bypass the guard,
            # retaining at most one valid observation per displayed skill.
            pending = {name.lower() for name in names}
            names = []
            for name in raw_names:
                if not reviewable_raw_term(name):
                    continue
                key = name.strip().lower()
                if key in pending:
                    names.append(name)
                    pending.remove(key)
        for name in names:
            try:
                self._curation.record_unmapped(name, source_id=source_id)
            except Exception:  # noqa: BLE001 — advisory, never fatal
                # Keep failures observable without SQL parameters, raw input
                # or exception details escaping into retained logs.
                _log.warning(
                    "unmapped_skill_capture_failed",
                    source_type=signal.source_type.value,
                )


def build_profile_source_service(
    settings: Optional[Settings] = None,
    *,
    github: Optional[GitHubService] = None,
    candidates: Optional[CandidateStore] = None,
    curation: Optional["CurationService"] = None,
) -> ProfileSourceService:
    settings = settings or get_settings()
    candidates = candidates or build_candidate_store(settings)
    github = github or GitHubClient(settings)
    store = build_profile_source_store(settings, session_factory=candidates._session_factory)
    return ProfileSourceService(
        github=github, store=store, candidates=candidates, settings=settings,
        curation=curation,
    )
