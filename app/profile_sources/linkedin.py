"""Pure LinkedIn-export parse + raw → ProfileSourceSignal transform (S6.2).

No I/O beyond reading the in-memory ZIP bytes handed in; no network, no LLM. The
candidate uploads their own "Get a copy of your data" export. Advisory evidence
only. Self-reported skills are treated as CLAIMS (conservative confidence),
bumped only when a position/headline corroborates.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.candidates.normalize.orgs import (
    canonicalize_employer, canonicalize_institution,
)
from app.candidates.normalize.skills import normalize_skill
from app.core.config import Settings
from app.profile_sources.schema import (
    LinkedInActivity, ProfileSourceSignal, ProfileSourceType, SourceSkillSignal,
)


class LinkedInPositionRaw(BaseModel):
    company: str = ""
    title: str = ""
    description: str = ""
    started_on: str = ""
    finished_on: str = ""


class LinkedInEducationRaw(BaseModel):
    school: str = ""
    degree: str = ""


class LinkedInExportRaw(BaseModel):
    available: bool = False
    skills: list[str] = Field(default_factory=list)
    positions: list[LinkedInPositionRaw] = Field(default_factory=list)
    education: list[LinkedInEducationRaw] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    headline: Optional[str] = None
    industry: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


# Filename stems (lower-cased, no extension) we recognise inside the archive.
_KNOWN_STEMS = {"skills", "positions", "education", "profile", "certifications", "languages"}


def _find_member(names: list[str], stem: str) -> Optional[str]:
    """Return the archive member whose basename is ``<stem>.csv`` (case-insensitive),
    tolerating a nested export directory."""
    want = f"{stem}.csv"
    for n in names:
        if n.rsplit("/", 1)[-1].lower() == want:
            return n
    return None


def _read_rows(zf: zipfile.ZipFile, member: str, settings: Settings, warnings: list[str]) -> list[dict[str, str]]:
    try:
        with zf.open(member) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace")
            reader = csv.DictReader(text)
            rows: list[dict[str, str]] = []
            for i, row in enumerate(reader):
                if i >= settings.ps_linkedin_max_rows:
                    break
                # Handle ragged rows: skip None key (csv restkey for extra unheadered columns)
                # and join any list values (defensive against csv restkey = list).
                cleaned = {}
                for k, v in row.items():
                    if k is None:            # extra unheadered columns (csv restkey)
                        continue
                    if isinstance(v, list):  # defensive: extras can arrive as a list
                        v = " ".join(x for x in v if x)
                    cleaned[k.strip() if k else ""] = (v or "").strip()
                rows.append(cleaned)
            return rows
    except Exception as exc:  # a corrupt member is a warning, never a crash
        warnings.append(f"could not read {member}: {exc}")
        return []


def _col(row: dict[str, str], *names: str) -> str:
    for n in names:
        v = row.get(n, "")
        if v:
            return v
    return ""


def parse_linkedin_export(data: bytes, settings: Settings) -> LinkedInExportRaw:
    warnings: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        return LinkedInExportRaw(available=False, warnings=["not a valid zip archive"])

    names = zf.namelist()
    members = {stem: _find_member(names, stem) for stem in _KNOWN_STEMS}
    if not any(members.values()):
        return LinkedInExportRaw(
            available=False, warnings=["no LinkedIn export CSVs found in archive"]
        )

    raw = LinkedInExportRaw(available=True)

    if members["skills"]:
        raw.skills = [
            _col(r, "Name") for r in _read_rows(zf, members["skills"], settings, warnings)
            if _col(r, "Name")
        ]
    if members["certifications"]:
        raw.certifications = [
            _col(r, "Name") for r in _read_rows(zf, members["certifications"], settings, warnings)
            if _col(r, "Name")
        ]
    if members["languages"]:
        raw.languages = [
            _col(r, "Name") for r in _read_rows(zf, members["languages"], settings, warnings)
            if _col(r, "Name")
        ]
    if members["positions"]:
        for r in _read_rows(zf, members["positions"], settings, warnings):
            raw.positions.append(LinkedInPositionRaw(
                company=_col(r, "Company Name", "Company"),
                title=_col(r, "Title"),
                description=_col(r, "Description"),
                started_on=_col(r, "Started On"),
                finished_on=_col(r, "Finished On"),
            ))
    if members["education"]:
        for r in _read_rows(zf, members["education"], settings, warnings):
            raw.education.append(LinkedInEducationRaw(
                school=_col(r, "School Name", "School"),
                degree=_col(r, "Degree Name", "Degree"),
            ))
    if members["profile"]:
        prows = _read_rows(zf, members["profile"], settings, warnings)
        if prows:
            raw.headline = _col(prows[0], "Headline") or None
            raw.industry = _col(prows[0], "Industry") or None

    raw.warnings = warnings
    return raw


# Tokens for whole-token corroboration: alnum plus the punctuation real skill
# names carry (c++, c#, .net). Short names ("go", "c", "r") match only as a
# standalone token, never as a substring.
_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _corroboration(skill: str, positions: list[LinkedInPositionRaw], headline: Optional[str]) -> int:
    """How many positions (title+description) + the headline mention the skill as
    a standalone token. A bounded evidence count, not a score."""
    tok = skill.lower().strip()
    if not tok:
        return 0
    count = 0
    for p in positions:
        if tok in _tokens(f"{p.title} {p.description}"):
            count += 1
    if headline and tok in _tokens(headline):
        count += 1
    return count


def _dedup(values: list[Optional[str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _build_skills(raw: LinkedInExportRaw, settings: Settings) -> list[SourceSkillSignal]:
    best: dict[str, tuple[str, int]] = {}  # lower(name) -> (display, corroboration)
    for name in raw.skills:
        display = name.strip()
        if not display:
            continue
        corr = _corroboration(display, raw.positions, raw.headline)
        key = display.lower()
        if key not in best or corr > best[key][1]:
            best[key] = (display, corr)
    out: list[SourceSkillSignal] = []
    for display, corr in best.values():
        match = normalize_skill(display)
        conf = (
            settings.ps_linkedin_skill_corroborated_confidence if corr >= 1
            else settings.ps_linkedin_skill_base_confidence
        )
        out.append(SourceSkillSignal(
            name=display,
            canonical=match.canonical if match else None,
            category=match.category if match else None,
            weight=corr,
            confidence=round(conf, 4),
        ))
    out.sort(key=lambda s: (-s.weight, s.name.lower()))
    return out


def _build_activity(raw: LinkedInExportRaw) -> LinkedInActivity:
    employers = _dedup([canonicalize_employer(p.company) for p in raw.positions])
    institutions = _dedup([
        (m.canonical if (m := canonicalize_institution(e.school)) else None)
        for e in raw.education
    ])
    current = sum(1 for p in raw.positions if not p.finished_on.strip())
    return LinkedInActivity(
        positions_count=len(raw.positions),
        current_positions=current,
        employers=employers,
        education_count=len(raw.education),
        institutions=institutions,
        certifications_count=len(raw.certifications),
        languages=list(raw.languages),
        headline=raw.headline,
        industry=raw.industry,
        skills_listed=len(raw.skills),
    )


def to_signal(
    raw: LinkedInExportRaw, settings: Settings, *, fetched_at: datetime
) -> ProfileSourceSignal:
    if not raw.available:
        return ProfileSourceSignal(
            source_type=ProfileSourceType.LINKEDIN_EXPORT,
            identifier="linkedin_export",
            skills=[],
            activity=LinkedInActivity(),
            method="unavailable",
            fetched_at=fetched_at,
            warnings=list(raw.warnings),
        )
    return ProfileSourceSignal(
        source_type=ProfileSourceType.LINKEDIN_EXPORT,
        identifier="linkedin_export",
        skills=_build_skills(raw, settings),
        activity=_build_activity(raw),
        method="export",
        fetched_at=fetched_at,
        warnings=list(raw.warnings),
    )
