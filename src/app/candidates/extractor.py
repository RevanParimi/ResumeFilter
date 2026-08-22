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

from app.candidates import hashing
from app.candidates.coverage import assess_coverage
from app.candidates.dates import date_points, date_spans, has_date_range, parse_date_range
from app.candidates.normalize import normalize_profile
from app.candidates.normalize.location import find_city, parse_notice_period
from app.candidates.schema import (
    CandidateProfile,
    CertificationEntry,
    ContactInfo,
    DateRange,
    EducationEntry,
    EmploymentType,
    ExperienceEntry,
    ExtractedStr,
    ExtractionResult,
    LinkItem,
    LinkType,
    ProjectEntry,
    SkillItem,
    SourceSpan,
)
from app.candidates.sections import SECTION_ALIASES
from app.core.config import Settings
from app.core.logging import get_logger
from app.services.llm import LLMClient

log = get_logger("candidates.extractor")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?91[-\s]?)?0?[6-9]\d{4}[-\s]?\d{5}\b")
_URL = re.compile(r"https?://[^\s)>\]]+")
_DEGREE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?e\b|m\.?e\b|b\.?sc|m\.?sc|bca|mca|mba|"
    r"bba|b\.?a\b|m\.?a\b|ph\.?d|b\.?com|m\.?com|diploma|"
    r"bachelors?|masters?)\b",
    re.IGNORECASE,
)
_GRADE = re.compile(
    r"(?:cgpa|gpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?", re.IGNORECASE
)
_PERCENT = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%")
_BULLET = re.compile(r"^[-•*·]\s*")
_SKILL_LABEL = re.compile(r"^[A-Za-z][A-Za-z /&+-]{0,29}:\s*")

_SENIORITY_HINTS: tuple[tuple[str, str], ...] = (
    ("principal", "staff"), ("staff", "staff"), ("lead", "senior"),
    ("senior", "senior"), ("sr.", "senior"), ("junior", "junior"),
    ("jr.", "junior"), ("intern", "junior"),
)


def _line_span(start: int, line: str) -> SourceSpan:
    return SourceSpan(start=start, end=start + len(line), text=line)


_HEADER_DASH_DECORATION = re.compile(r"[_\-–—=~]{2,}")
_HEADER_PAREN = re.compile(r"\([^)]*\)")


def _header_key(line: str) -> str:
    """Section-header lookup key: decoration and punctuation removed (S9.2).

    Parenthetical stripping is bounded (S9.2 I1 review): applied only when
    the remainder -- the line with its parenthetical content removed -- is
    ALL-CAPS, or nothing but the parenthetical remains. Without the bound,
    "Technologies (Python, Django, PostgreSQL)" -- a Title-Case body line
    under PROJECTS -- strips to "Technologies", which normalizes to the
    "technologies" skills alias and gets silently consumed as a SKILLS
    header, deleting the technology list and re-parenting everything after
    it into skills. "WORK EXPERIENCE (5 YEARS)" must still resolve: its
    remainder ("WORK EXPERIENCE") is ALL-CAPS, so stripping still applies.
    """
    s = _HEADER_DASH_DECORATION.sub("", line)
    without_parens = _HEADER_PAREN.sub("", s)
    remainder = " ".join(without_parens.split()).strip(" :.-–—")
    if not remainder or remainder.isupper():
        s = without_parens
    return " ".join(s.split()).strip(" :.-–—").lower()


def _split_sections(text: str) -> dict[str, list[tuple[int, str]]]:
    """Map section → [(char_offset_of_stripped_line, stripped_line)].
    Content before any recognized header lands in pseudo-section 'header'."""
    alias_to_section = {
        alias: section
        for section, aliases in SECTION_ALIASES.items()
        for alias in aliases
    }
    sections: dict[str, list[tuple[int, str]]] = {"header": []}
    current = "header"
    offset = 0
    for raw in text.splitlines(keepends=True):
        line = raw.strip()
        if line:
            key = _header_key(line)
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


def _location(sections: dict[str, list[tuple[int, str]]]) -> Optional[ExtractedStr]:
    """First known Indian city in the pre-section header block."""
    for start, line in sections.get("header", []):
        hit = find_city(line)
        if hit:
            return ExtractedStr(
                value=hit.text,
                confidence=0.7,
                span=SourceSpan(
                    start=start + hit.start, end=start + hit.end, text=hit.text
                ),
            )
    return None


def _notice_period(text: str) -> Optional[ExtractedStr]:
    """Whole-text notice-period scan; normalization to days is S1.4's
    normalize_profile, this only captures the claim + provenance."""
    hit = parse_notice_period(text)
    if hit is None:
        return None
    return ExtractedStr(
        value=hit.text,
        confidence=0.85,
        span=SourceSpan(start=hit.start, end=hit.end, text=hit.text),
    )


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


_PRESENT_MARKER = re.compile(
    r"\b(?:present|current|till date|to date|ongoing|now)\b", re.IGNORECASE
)
_ROLE_TAIL_PUNCT = " \t\r\n-–—|,.()[]:;"


def _looks_like_role(content: str) -> bool:
    """A bulleted dated line only opens a new employment entry when it reads
    like a role line (title, employer, dates), not an achievement bullet
    that happens to mention a year range (S9.2 fix 1, C2 review: measured
    "Led the 2019 - 2021 migration of the reporting stack to Snowflake"
    fabricating title='Led the', employer=None).

    A role line's dates sit at the END of the line ("Title, Employer (2019 -
    Present)"), while an achievement sentence's dates sit mid-sentence with
    the sentence continuing after them ("... the 2019 - 2021 migration of
    the reporting stack to Snowflake"). So the position of the LAST date
    token, not the word count of the head, is the discriminator: nothing
    meaningful may trail it. Trailing "present"/"current"-style markers and
    punctuation/parens don't count as "meaningful".

    An earlier fix wave also capped the head at <=6 words, reasoning that
    role titles and "Title, Employer" phrases are short. Measured regression
    (S9.2 final review fix-wave, NEW-2): multi-word employer names are the
    norm in this product's stated market -- "Tata Consultancy Services",
    "Larsen and Toubro Infotech", "Flipkart Internet Private Limited" -- and
    the cap silently dropped every one of those roles even though their
    dates sat cleanly at the end. The cap is gone; only a non-empty head is
    still required.
    """
    spans = date_spans(content)
    if not spans:
        return False
    head = content[: spans[0][0]].strip().rstrip("—–-|,(").strip()
    if not head:
        return False
    tail = content[spans[-1][1] :]
    tail = _PRESENT_MARKER.sub("", tail)
    return not tail.strip(_ROLE_TAIL_PUNCT)


def _experience(lines: list[tuple[int, str]]) -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    dated = [(s, l) for s, l in lines if has_date_range(_BULLET.sub("", l))]
    # A duty list under a role ALWAYS has an unbulleted dated line above it. So
    # when every dated line in this section is bulleted, there is no role line
    # for them to be duties OF -- they are the roles (S9.2). But a role line
    # carrying no date of its own (e.g. "Acme Analytics - Senior Data
    # Engineer" with the dates only on its achievement bullets) ALSO makes
    # every dated line bulleted -- so a bulleted dated line must additionally
    # look like a role (_looks_like_role) before it is trusted to open one
    # (S9.2 fix 1, C2 review).
    all_dated_are_bullets = bool(dated) and all(_BULLET.match(l) for _, l in dated)
    for start, line in lines:
        content = _BULLET.sub("", line)
        if not has_date_range(content):
            continue
        if _BULLET.match(line):
            if not all_dated_are_bullets:
                continue  # a duty under a role
            if not _looks_like_role(content):
                continue  # an achievement bullet, not a role (C2)
        head = content[: date_points(content)[0][0]].strip().rstrip("—–-|,(").strip()
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


def _strip_skill_label(content: str) -> str:
    """"Programming Languages: Python, Java" -- the label is a CATEGORY, not a
    skill, and left in place it also poisons S1.4 normalization and floods
    S6.3's curation queue with terms that can never map (S9.2).

    But "Python: 5 years" is a per-skill proficiency annotation, a common
    Indian-resume shape, and "Python:" is the skill's own NAME -- stripping it
    destroys the skill rather than a category. Ruling R15: strip only when the
    line has exactly ONE colon AND at least two comma-separated items follow
    it (a real category introduces a list). Two colons ("Python: 5 years,
    Java: 3 years") or one item after the colon ("C++: advanced") are left
    alone -- the latter survives ugly as a single skill named "C++: advanced",
    which keeps the skill name instead of deleting it."""
    if content.count(":") != 1:
        return content
    after = content.split(":", 1)[1]
    items = [p for p in after.split(",") if p.strip()]
    if len(items) < 2:
        return content
    return _SKILL_LABEL.sub("", content)


def _skills(lines: list[tuple[int, str]]) -> list[SkillItem]:
    items: list[SkillItem] = []
    seen: set[str] = set()
    for start, line in lines:
        content = _BULLET.sub("", line)
        content = _strip_skill_label(content)
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
    contact = _contact(text)
    contact.location = _location(sections)
    return CandidateProfile(
        full_name=full_name,
        headline=headline,
        contact=contact,
        notice_period=_notice_period(text),
        education=_education(sections.get("education", [])),
        experience=_experience(sections.get("experience", [])),
        skills=_skills(sections.get("skills", [])),
        projects=_projects(sections.get("projects", [])),
        certifications=_certifications(sections.get("certifications", [])),
        links=_links(text),
    )


PROFILE_EXTRACTION_SYSTEM = """You are a precise resume parser for the Indian job market.
Extract a structured candidate profile from the resume.

Return ONE JSON object with exactly these keys (use null / [] when absent):
{
  "full_name":  {"value": str, "confidence": 0-1, "source_excerpt": str},
  "headline":   {"value": str, "confidence": 0-1, "source_excerpt": str},
  "contact": {
    "email":    {"value": str, "confidence": 0-1, "source_excerpt": str},
    "phone":    {"value": str, "confidence": 0-1, "source_excerpt": str},
    "location": {"value": str, "confidence": 0-1, "source_excerpt": str}
  },
  "notice_period": {"value": str, "confidence": 0-1, "source_excerpt": str},
  "education":  [{"degree": str, "field_of_study": str, "institution": str,
                  "grade_value": number, "grade_scale": "cgpa_10"|"cgpa_4"|"percentage",
                  "start": "YYYY-MM"|"YYYY", "end": "YYYY-MM"|"YYYY"|null, "is_current": bool,
                  "confidence": 0-1, "source_excerpt": str}],
  "experience": [{"employer": str, "title": str,
                  "seniority": "junior"|"mid"|"senior"|"staff",
                  "employment_type": "full_time"|"part_time"|"internship"|"contract"|"freelance"|"unknown",
                  "start": "YYYY-MM"|"YYYY", "end": "YYYY-MM"|"YYYY"|null, "is_current": bool,
                  "confidence": 0-1, "source_excerpt": str}],
  "skills":         [{"name": str, "confidence": 0-1, "source_excerpt": str}],
  "projects":       [{"name": str, "description": str, "technologies": [str],
                      "url": str, "confidence": 0-1, "source_excerpt": str}],
  "certifications": [{"name": str, "issuer": str, "year": int,
                      "confidence": 0-1, "source_excerpt": str}],
  "links":          [{"type": "github"|"linkedin"|"portfolio"|"other", "url": str}]
}

Rules:
- Copy each source_excerpt VERBATIM from the resume; it is used to locate provenance spans.
- Report only what the resume states; never invent values. Lower confidence when inferring.
- Dates: "YYYY-MM" when the month is stated, else "YYYY".
- notice_period: the stated notice period / joining availability, verbatim (e.g. "30 days", "immediate joiner"); null when the resume does not state one.
"""


def _clamp(value: object, default: float = 0.5) -> float:
    try:
        return min(1.0, max(0.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _find_span(text: str, excerpt: str) -> Optional[SourceSpan]:
    """Re-locate an LLM-quoted excerpt in the resume (case-insensitive rescue)."""
    if not excerpt:
        return None
    idx = text.find(excerpt)
    if idx < 0:
        idx = text.lower().find(excerpt.lower())
    if idx < 0:
        return None
    return SourceSpan(start=idx, end=idx + len(excerpt), text=text[idx : idx + len(excerpt)])


def _scalar(node: object, text: str) -> Optional[ExtractedStr]:
    if not isinstance(node, dict) or not node.get("value"):
        return None
    return ExtractedStr(
        value=str(node["value"]),
        confidence=_clamp(node.get("confidence")),
        span=_find_span(text, str(node.get("source_excerpt") or "")),
    )


def _node_dates(node: dict) -> DateRange:
    return DateRange(
        start=node.get("start") or None,
        end=node.get("end") or None,
        is_current=bool(node.get("is_current")),
    )


def _parse_llm_profile(payload: dict, text: str) -> CandidateProfile:
    """Defensive payload→profile mapping: skip malformed entries, never raise."""
    contact_raw = payload.get("contact") or {}
    profile = CandidateProfile(
        full_name=_scalar(payload.get("full_name"), text),
        headline=_scalar(payload.get("headline"), text),
        contact=ContactInfo(
            email=_scalar(contact_raw.get("email"), text),
            phone=_scalar(contact_raw.get("phone"), text),
            location=_scalar(contact_raw.get("location"), text),
        ),
        notice_period=_scalar(payload.get("notice_period"), text),
    )
    for e in payload.get("education") or []:
        if not isinstance(e, dict):
            continue
        try:
            profile.education.append(
                EducationEntry(
                    degree=e.get("degree"),
                    field_of_study=e.get("field_of_study"),
                    institution=e.get("institution"),
                    grade_value=e.get("grade_value"),
                    grade_scale=e.get("grade_scale"),
                    dates=_node_dates(e),
                    confidence=_clamp(e.get("confidence")),
                    span=_find_span(text, str(e.get("source_excerpt") or "")),
                )
            )
        except (TypeError, ValueError):
            continue
    for x in payload.get("experience") or []:
        if not isinstance(x, dict):
            continue
        try:
            raw_type = str(x.get("employment_type") or "unknown")
            etype = (
                EmploymentType(raw_type)
                if raw_type in EmploymentType._value2member_map_
                else EmploymentType.UNKNOWN
            )
            profile.experience.append(
                ExperienceEntry(
                    employer=x.get("employer"),
                    title=x.get("title"),
                    seniority=x.get("seniority"),
                    employment_type=etype,
                    dates=_node_dates(x),
                    confidence=_clamp(x.get("confidence")),
                    span=_find_span(text, str(x.get("source_excerpt") or "")),
                )
            )
        except (TypeError, ValueError):
            continue
    for s in payload.get("skills") or []:
        if isinstance(s, dict) and s.get("name"):
            profile.skills.append(
                SkillItem(
                    name=str(s["name"]),
                    confidence=_clamp(s.get("confidence")),
                    span=_find_span(text, str(s.get("source_excerpt") or "")),
                )
            )
    for pr in payload.get("projects") or []:
        if isinstance(pr, dict) and pr.get("name"):
            profile.projects.append(
                ProjectEntry(
                    name=str(pr["name"]),
                    description=pr.get("description"),
                    technologies=[str(t) for t in pr.get("technologies") or []],
                    url=pr.get("url"),
                    confidence=_clamp(pr.get("confidence")),
                    span=_find_span(text, str(pr.get("source_excerpt") or "")),
                )
            )
    for c in payload.get("certifications") or []:
        if isinstance(c, dict) and c.get("name"):
            try:
                year = int(c["year"]) if c.get("year") is not None else None
            except (TypeError, ValueError):
                year = None
            profile.certifications.append(
                CertificationEntry(
                    name=str(c["name"]),
                    issuer=c.get("issuer"),
                    year=year,
                    confidence=_clamp(c.get("confidence")),
                    span=_find_span(text, str(c.get("source_excerpt") or "")),
                )
            )
    for lk in payload.get("links") or []:
        if isinstance(lk, dict) and lk.get("url"):
            raw_type = str(lk.get("type") or "other")
            ltype = (
                LinkType(raw_type)
                if raw_type in LinkType._value2member_map_
                else LinkType.OTHER
            )
            profile.links.append(
                LinkItem(type=ltype, url=str(lk["url"]), span=_find_span(text, str(lk["url"])))
            )
    return profile


def _is_empty(profile: CandidateProfile) -> bool:
    return (
        profile.full_name is None
        and profile.contact.email is None
        and profile.contact.phone is None
        and not profile.education
        and not profile.experience
        and not profile.skills
    )


async def extract_profile(
    resume_text: str, *, llm: LLMClient, settings: Optional[Settings] = None
) -> ExtractionResult:
    """LLM extraction with a deterministic floor — never returns nothing."""
    settings = settings or llm.settings
    warnings: list[str] = []
    profile: Optional[CandidateProfile] = None
    method = "heuristic"
    try:
        payload = await llm.acomplete_json(
            tier="parsing",
            system=PROFILE_EXTRACTION_SYSTEM,
            prompt=f"RESUME:\n{resume_text}",
        )
        if payload:
            profile = _parse_llm_profile(payload, resume_text)
            method = "llm"
    except Exception as exc:  # any LLM failure → heuristic floor
        warnings.append(f"llm_extraction_failed: {exc}")
        log.warning("profile_llm_failed", error=str(exc))
    if profile is None or _is_empty(profile):
        profile = heuristic_profile(resume_text)
        method = "heuristic"
    normalize_profile(profile)  # S1.4: same enrichment for both paths
    # S9.2: measured HERE -- after both doors (LLM / heuristic) have already
    # converged on `profile` -- so one instrument covers both paths.
    coverage = assess_coverage(
        resume_text,
        profile,
        min_chars=settings.coverage_min_chars,
        max_header_chars=settings.coverage_max_header_chars,
        max_gaps=settings.coverage_max_gaps,
    )
    hashing.apply_contact_hashes(profile, settings.contact_hash_salt)
    log.info(
        "profile_extracted",
        method=method,
        education=len(profile.education),
        experience=len(profile.experience),
        skills=len(profile.skills),
        coverage=coverage.band.value,
    )
    return ExtractionResult(profile=profile, method=method, warnings=warnings, coverage=coverage)
