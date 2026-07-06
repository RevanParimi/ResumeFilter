"""Resume → CandidateProfile extraction (S1.1).

Primary path: LLM (parsing tier) returns the profile as JSON with per-field
confidence and verbatim source excerpts, which are re-located in the resume to
produce character spans. Fallback path: a deterministic section parser, so the
pipeline works offline with no API key — the same NullLLM degradation contract
as the eval graph.

Heuristic confidences are fixed by evidence strength: regex-matched contact
0.85–0.95, section-structured entries 0.5–0.7. They are honest priors, not
measurements.
"""

from __future__ import annotations

import re
from typing import Optional

from app.candidates.dates import date_points, has_date_range, parse_date_range
from app.candidates.schema import (
    CandidateProfile,
    CertificationEntry,
    ContactInfo,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
    ExtractedStr,
    LinkItem,
    LinkType,
    ProjectEntry,
    SkillItem,
    SourceSpan,
)
from app.core.logging import get_logger

log = get_logger("candidates.extractor")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?91[-\s]?)?0?[6-9]\d{4}[-\s]?\d{5}\b")
_URL = re.compile(r"https?://[^\s)>\]]+")
_DEGREE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?e\b|m\.?e\b|b\.?sc|m\.?sc|bca|mca|mba|"
    r"ph\.?d|b\.?com|m\.?com|diploma)\b",
    re.IGNORECASE,
)
_GRADE = re.compile(
    r"(?:cgpa|gpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?", re.IGNORECASE
)
_PERCENT = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%")
_BULLET = re.compile(r"^[-•*·]\s*")

_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": ("education", "academics", "academic background", "qualifications"),
    "experience": (
        "experience", "work experience", "professional experience",
        "employment", "employment history", "work history",
    ),
    "skills": ("skills", "technical skills", "core skills", "skill set", "technologies"),
    "projects": ("projects", "personal projects", "key projects", "academic projects"),
    "certifications": (
        "certifications", "certificates", "licenses",
        "licenses & certifications", "courses & certifications",
    ),
}
_SENIORITY_HINTS: tuple[tuple[str, str], ...] = (
    ("principal", "staff"), ("staff", "staff"), ("lead", "senior"),
    ("senior", "senior"), ("sr.", "senior"), ("junior", "junior"),
    ("jr.", "junior"), ("intern", "junior"),
)


def _line_span(start: int, line: str) -> SourceSpan:
    return SourceSpan(start=start, end=start + len(line), text=line)


def _split_sections(text: str) -> dict[str, list[tuple[int, str]]]:
    """Map section → [(char_offset_of_stripped_line, stripped_line)].
    Content before any recognized header lands in pseudo-section 'header'."""
    alias_to_section = {
        alias: section
        for section, aliases in _SECTION_ALIASES.items()
        for alias in aliases
    }
    sections: dict[str, list[tuple[int, str]]] = {"header": []}
    current = "header"
    offset = 0
    for raw in text.splitlines(keepends=True):
        line = raw.strip()
        if line:
            key = line.rstrip(":").strip().lower()
            if key in alias_to_section:
                current = alias_to_section[key]
                sections.setdefault(current, [])
            else:
                start = offset + (len(raw) - len(raw.lstrip()))
                sections.setdefault(current, []).append((start, line))
        offset += len(raw)
    return sections


def _header_identity(
    sections: dict[str, list[tuple[int, str]]],
) -> tuple[Optional[ExtractedStr], Optional[ExtractedStr]]:
    """(full_name, headline) from the pre-section header block."""
    prose = [
        (s, l)
        for s, l in sections.get("header", [])
        if "@" not in l and not _URL.search(l)
    ]
    full_name = headline = None
    if prose:
        start, line = prose[0]
        name = re.split(r"[|—–]", line)[0].strip()
        words = name.split()
        if 1 < len(words) <= 5 and not any(ch.isdigit() for ch in name):
            full_name = ExtractedStr(
                value=name, confidence=0.6, span=_line_span(start, line)
            )
    if len(prose) > 1:
        start, line = prose[1]
        headline = ExtractedStr(value=line, confidence=0.5, span=_line_span(start, line))
    return full_name, headline


def _contact(text: str) -> ContactInfo:
    contact = ContactInfo()
    m = _EMAIL.search(text)
    if m:
        contact.email = ExtractedStr(
            value=m.group(0),
            confidence=0.95,
            span=SourceSpan(start=m.start(), end=m.end(), text=m.group(0)),
        )
    m = _PHONE.search(text)
    if m:
        contact.phone = ExtractedStr(
            value=m.group(0).strip(),
            confidence=0.85,
            span=SourceSpan(start=m.start(), end=m.end(), text=m.group(0)),
        )
    return contact


def _links(text: str) -> list[LinkItem]:
    links: list[LinkItem] = []
    seen: set[str] = set()
    for m in _URL.finditer(text):
        url = m.group(0).rstrip(").,;")
        if url in seen:
            continue
        seen.add(url)
        low = url.lower()
        if "github.com" in low:
            ltype = LinkType.GITHUB
        elif "linkedin.com" in low:
            ltype = LinkType.LINKEDIN
        else:
            ltype = LinkType.OTHER
        links.append(
            LinkItem(
                type=ltype,
                url=url,
                span=SourceSpan(start=m.start(), end=m.start() + len(url), text=url),
            )
        )
    return links


def _education(lines: list[tuple[int, str]]) -> list[EducationEntry]:
    entries: list[EducationEntry] = []
    for start, line in lines:
        content = _BULLET.sub("", line)
        if not (_DEGREE.search(content) or _GRADE.search(content)):
            continue
        degree = field_of_study = institution = None
        for seg in (s.strip() for s in re.split(r"[—–,]", content) if s.strip()):
            if degree is None and _DEGREE.search(seg):
                lower = seg.lower()
                if " in " in lower:
                    i = lower.index(" in ")
                    degree, field_of_study = seg[:i].strip(), seg[i + 4 :].strip()
                else:
                    degree = seg
            elif (
                degree is not None
                and institution is None
                and not any(ch.isdigit() for ch in seg)
            ):
                institution = seg
        grade_value = grade_scale = None
        gm = _GRADE.search(content)
        pm = _PERCENT.search(content)
        if gm:
            grade_value = float(gm.group(1))
            denom = gm.group(2)
            grade_scale = f"cgpa_{denom}" if denom else (
                "cgpa_10" if grade_value <= 10 else None
            )
        elif pm:
            grade_value, grade_scale = float(pm.group(1)), "percentage"
        entries.append(
            EducationEntry(
                degree=degree,
                field_of_study=field_of_study,
                institution=institution,
                grade_value=grade_value,
                grade_scale=grade_scale,
                dates=parse_date_range(content),
                confidence=0.6,
                span=_line_span(start, line),
            )
        )
    return entries


def _experience(lines: list[tuple[int, str]]) -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    for start, line in lines:
        content = _BULLET.sub("", line)
        # Only dated, non-bullet lines open an entry; bullets are duties.
        if _BULLET.match(line) or not has_date_range(content):
            continue
        head = content[: date_points(content)[0][0]].strip().rstrip("—–-|,").strip()
        title = employer = None
        if " at " in head.lower():
            i = head.lower().rindex(" at ")
            title, employer = head[:i].strip(), head[i + 4 :].strip()
        elif "," in head:
            title, employer = (p.strip() for p in head.rsplit(",", 1))
        elif head:
            title = head
        low = content.lower()
        if "intern" in low:
            etype = EmploymentType.INTERNSHIP
        elif "freelance" in low:
            etype = EmploymentType.FREELANCE
        elif "contract" in low:
            etype = EmploymentType.CONTRACT
        else:
            etype = EmploymentType.UNKNOWN
        seniority = next(
            (v for k, v in _SENIORITY_HINTS if k in (title or "").lower()), None
        )
        entries.append(
            ExperienceEntry(
                employer=employer,
                title=title,
                seniority=seniority,
                employment_type=etype,
                dates=parse_date_range(content),
                confidence=0.6,
                span=_line_span(start, line),
            )
        )
    return entries


def _skills(lines: list[tuple[int, str]]) -> list[SkillItem]:
    items: list[SkillItem] = []
    seen: set[str] = set()
    for start, line in lines:
        content = _BULLET.sub("", line)
        for part in re.split(r"[,;·|]", content):
            name = part.strip().rstrip(".")
            if not 1 < len(name) <= 40 or name.lower() in seen:
                continue
            seen.add(name.lower())
            items.append(SkillItem(name=name, confidence=0.7, span=_line_span(start, line)))
    return items


def _projects(lines: list[tuple[int, str]]) -> list[ProjectEntry]:
    projects: list[ProjectEntry] = []
    for start, line in lines:
        if _BULLET.match(line):
            if projects:  # bullet = description of the last project
                desc = _BULLET.sub("", line)
                cur = projects[-1]
                cur.description = (
                    f"{cur.description} {desc}".strip() if cur.description else desc
                )
            continue
        m = _URL.search(line)
        url = m.group(0).rstrip(").,;") if m else None
        name = _URL.sub("", line).strip().strip("—–-|:").strip()
        if not name and not url:
            continue
        projects.append(
            ProjectEntry(
                name=name or url, url=url, confidence=0.5, span=_line_span(start, line)
            )
        )
    return projects


def _certifications(lines: list[tuple[int, str]]) -> list[CertificationEntry]:
    entries: list[CertificationEntry] = []
    for start, line in lines:
        content = _BULLET.sub("", line)
        if len(content) < 4:
            continue
        parts = [p.strip() for p in content.split(",")]
        year = None
        if parts and re.fullmatch(r"(?:19|20)\d{2}", parts[-1]):
            year = int(parts.pop())
        entries.append(
            CertificationEntry(
                name=parts[0] if parts else content,
                issuer=", ".join(parts[1:]) or None,
                year=year,
                confidence=0.5,
                span=_line_span(start, line),
            )
        )
    return entries


def heuristic_profile(text: str) -> CandidateProfile:
    """Deterministic extraction — the no-LLM floor the pipeline can trust."""
    sections = _split_sections(text)
    full_name, headline = _header_identity(sections)
    return CandidateProfile(
        full_name=full_name,
        headline=headline,
        contact=_contact(text),
        education=_education(sections.get("education", [])),
        experience=_experience(sections.get("experience", [])),
        skills=_skills(sections.get("skills", [])),
        projects=_projects(sections.get("projects", [])),
        certifications=_certifications(sections.get("certifications", [])),
        links=_links(text),
    )
