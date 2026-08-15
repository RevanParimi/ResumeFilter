"""Pure GitHub raw → ProfileSourceSignal transform (S6.1). No I/O, no LLM.

Aggregates per-language bytes across a user's non-fork repos, maps each language
to the S1.4 skill taxonomy (unknown languages kept with canonical=None), and
derives a bounded, evidence-monotone confidence. ADVISORY evidence only.
"""

from __future__ import annotations

from datetime import datetime

from app.candidates.normalize.skills import normalize_skill
from app.core.config import Settings
from app.profile_sources.schema import (
    GitHubActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)
from app.services.github import GitHubUserRaw

# Repos beyond ps_github_language_repos have no per-language byte breakdown; their
# primary `language` still counts, at this fixed nominal weight, so a large
# account's tail languages are not silently dropped.
PRIMARY_LANGUAGE_NOMINAL_BYTES = 2048


def to_signal(
    raw: GitHubUserRaw, settings: Settings, *, fetched_at: datetime
) -> ProfileSourceSignal:
    if not raw.available:
        return ProfileSourceSignal(
            source_type=ProfileSourceType.GITHUB,
            identifier=raw.login,
            skills=[],
            activity=GitHubActivity(),
            method="unavailable",
            fetched_at=fetched_at,
            warnings=list(raw.warnings),
        )

    repos = [r for r in raw.repos if settings.ps_github_include_forks or not r.fork]
    lang_bytes: dict[str, int] = {}
    total_stars = 0
    pushes: list[str] = []
    for r in repos:
        total_stars += r.stargazers_count
        if r.pushed_at:
            pushes.append(r.pushed_at)
        if r.languages:
            for lang, b in r.languages.items():
                lang_bytes[lang] = lang_bytes.get(lang, 0) + int(b)
        elif r.language:
            lang_bytes[r.language] = lang_bytes.get(r.language, 0) + PRIMARY_LANGUAGE_NOMINAL_BYTES

    max_w = max(lang_bytes.values(), default=0)
    skills: list[SourceSkillSignal] = []
    for lang, w in sorted(lang_bytes.items(), key=lambda kv: (-kv[1], kv[0])):
        match = normalize_skill(lang)
        conf = 0.3 + 0.6 * (w / max_w) if max_w else 0.3
        skills.append(SourceSkillSignal(
            name=lang,
            canonical=match.canonical if match else None,
            category=match.category if match else None,
            weight=w,
            confidence=round(min(0.9, conf), 4),
        ))

    activity = GitHubActivity(
        public_repos=raw.public_repos,
        followers=raw.followers,
        total_stars=total_stars,
        top_languages=dict(lang_bytes),
        most_recent_push=max(pushes) if pushes else None,  # ISO-8601 UTC sorts chronologically
        account_created=raw.account_created,
        sampled_repos=len(repos),
    )
    return ProfileSourceSignal(
        source_type=ProfileSourceType.GITHUB,
        identifier=raw.login,
        skills=skills,
        activity=activity,
        method="api",
        fetched_at=fetched_at,
        warnings=list(raw.warnings),
    )
