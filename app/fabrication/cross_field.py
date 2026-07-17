"""Deterministic cross-field forensics (S2.2) — pure, offline, no LLM.

Checks the extracted CandidateProfile against itself: concurrent primary
roles, unexplained gaps, full-time work inside a bachelor's, and seniority
claims that outrun the visible career span. Conservative by construction:

* Year-only dates shrink INWARD for overlap checks (start -> December,
  end -> January), so every flagged overlap is a lower bound.
* Year-only dates expand OUTWARD for tenure (start -> January, end ->
  December), so career span is an upper bound and seniority under-fires.
* Gaps are always MINOR: career breaks are legitimate; the finding is
  context for a reviewer, never an accusation.
"""

from __future__ import annotations

import itertools
import re
from datetime import date

from app.candidates.schema import DateRange, EducationEntry, EmploymentType, ExperienceEntry
from app.schemas.fabrication import CrossFieldFinding, FindingSeverity

# Employment types that legitimately run concurrently with a primary role.
_NON_PRIMARY = {
    EmploymentType.INTERNSHIP,
    EmploymentType.PART_TIME,
    EmploymentType.FREELANCE,
    EmploymentType.CONTRACT,
}

_OVERLAP_MAJOR_MONTHS = 12  # a year+ of concurrent primary roles is probe-worthy

_POINT_RE = re.compile(r"(\d{4})(?:-(\d{2}))?$")


def _point(p: str | None) -> tuple[int, int | None] | None:
    """'YYYY-MM' -> (year, month); 'YYYY' -> (year, None); anything else None."""
    if not p:
        return None
    m = _POINT_RE.fullmatch(p)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)) if m.group(2) else None


def _idx(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _ym(idx: int) -> str:
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def _interval(
    dates: DateRange, today: date, *, start_fill: int, end_fill: int
) -> tuple[int, int] | None:
    """Shared interval builder; fills in the month for year-only points."""
    start = _point(dates.start)
    if start is None:
        return None
    s = _idx(start[0], start[1] or start_fill)
    end = _point(dates.end)
    if end is not None:
        e = _idx(end[0], end[1] or end_fill)
    elif dates.is_current:
        e = _idx(today.year, today.month)
    else:
        return None
    return (s, e) if s <= e else None


def narrow_interval(dates: DateRange, today: date) -> tuple[int, int] | None:
    """Months this range CERTAINLY covers — overlaps become lower bounds."""
    return _interval(dates, today, start_fill=12, end_fill=1)


def wide_interval(dates: DateRange, today: date) -> tuple[int, int] | None:
    """Widest plausible cover — tenure becomes an upper bound."""
    return _interval(dates, today, start_fill=1, end_fill=12)


def month_precise_interval(dates: DateRange, today: date) -> tuple[int, int] | None:
    """Only when both endpoints carry a month (is_current counts, via today)."""
    start = _point(dates.start)
    if start is None or start[1] is None:
        return None
    end = _point(dates.end)
    if end is not None:
        if end[1] is None:
            return None
        e = _idx(end[0], end[1])
    elif dates.is_current:
        e = _idx(today.year, today.month)
    else:
        return None
    s = _idx(start[0], start[1])
    return (s, e) if s <= e else None


def overlap_months(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)


def _label(e: ExperienceEntry) -> str:
    return " — ".join(x for x in (e.title, e.employer) if x) or e.id


def _primary(experience: list[ExperienceEntry]) -> list[ExperienceEntry]:
    return [e for e in experience if e.employment_type not in _NON_PRIMARY]


def check_timeline_overlaps(
    experience: list[ExperienceEntry], *, today: date, min_months: int
) -> list[CrossFieldFinding]:
    """Concurrent primary roles. UNKNOWN counts as primary (the heuristic
    extractor never labels full_time); the month threshold absorbs the noise."""
    dated = [
        (e, iv)
        for e in _primary(experience)
        if (iv := narrow_interval(e.dates, today)) is not None
    ]
    findings: list[CrossFieldFinding] = []
    for (a, ia), (b, ib) in itertools.combinations(dated, 2):
        months = overlap_months(ia, ib)
        if months < min_months:
            continue
        severity = (
            FindingSeverity.MAJOR
            if months >= _OVERLAP_MAJOR_MONTHS
            else FindingSeverity.MINOR
        )
        findings.append(
            CrossFieldFinding(
                id="timeline_overlap",
                severity=severity,
                score=min(1.0, months / 24),
                detail=(
                    f"'{_label(a)}' and '{_label(b)}' overlap by at least "
                    f"{months} months of concurrent primary employment"
                ),
                entry_ids=[a.id, b.id],
            )
        )
    return findings


def check_timeline_gaps(
    experience: list[ExperienceEntry], *, today: date, min_months: int
) -> list[CrossFieldFinding]:
    """Gaps between merged month-precise primary intervals. Year-only dates
    can't measure a gap honestly, so they are skipped — never flagged."""
    intervals = sorted(
        iv
        for e in _primary(experience)
        if (iv := month_precise_interval(e.dates, today)) is not None
    )
    merged: list[list[int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    findings: list[CrossFieldFinding] = []
    for (_, e1), (s2, _) in zip(merged, merged[1:]):
        gap = s2 - e1 - 1
        if gap < min_months:
            continue
        findings.append(
            CrossFieldFinding(
                id="timeline_gap",
                severity=FindingSeverity.MINOR,  # NEVER major: breaks are normal
                score=min(1.0, gap / 36),
                detail=(
                    f"{gap}-month gap between primary roles ({_ym(e1)} -> {_ym(s2)}); "
                    f"career breaks are legitimate — context only"
                ),
            )
        )
    return findings


_EDU_MAJOR_MONTHS = 24  # two years of full-time work inside a degree

# Bachelor-only: part-time/executive master's programmes (WILP, distance MBA)
# are common in India, so postgraduate overlap is never flagged.
_BACHELOR_RE = re.compile(
    r"\b(b\.?\s?tech|b\.?e\b|b\.?sc|bca|bachelor)", re.IGNORECASE
)

# Seniority ladders. "lead-level" floors are for lead/principal/staff/head+.
_LEAD_RE = re.compile(
    r"\b(lead|principal|staff|head|director|vp|vice president|chief|cto)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE)


def is_bachelor(edu: EducationEntry) -> bool:
    """Canonical level (S1.4) first; keyword fallback for un-normalized rows."""
    if edu.degree_level is not None:
        return edu.degree_level == "bachelor"
    return bool(edu.degree and _BACHELOR_RE.search(edu.degree))


def check_education_overlap(
    education: list[EducationEntry],
    experience: list[ExperienceEntry],
    *,
    today: date,
    min_months: int,
) -> list[CrossFieldFinding]:
    """Primary employment running inside a bachelor's programme."""
    dated_exp = [
        (e, iv)
        for e in _primary(experience)
        if (iv := narrow_interval(e.dates, today)) is not None
    ]
    findings: list[CrossFieldFinding] = []
    for edu in education:
        if not is_bachelor(edu):
            continue
        edu_iv = narrow_interval(edu.dates, today)
        if edu_iv is None:
            continue
        for exp, exp_iv in dated_exp:
            months = overlap_months(edu_iv, exp_iv)
            if months < min_months:
                continue
            severity = (
                FindingSeverity.MAJOR
                if months >= _EDU_MAJOR_MONTHS
                else FindingSeverity.MINOR
            )
            findings.append(
                CrossFieldFinding(
                    id="education_employment_overlap",
                    severity=severity,
                    score=min(1.0, months / 24),
                    detail=(
                        f"primary role '{_label(exp)}' overlaps the bachelor's at "
                        f"{edu.institution or 'unknown institution'} by at least "
                        f"{months} months"
                    ),
                    entry_ids=[edu.id, exp.id],
                )
            )
    return findings


def check_seniority_vs_tenure(
    experience: list[ExperienceEntry],
    *,
    today: date,
    senior_min_months: int,
    lead_min_months: int,
) -> list[CrossFieldFinding]:
    """Claimed rank vs. the widest possible career span. Uses wide intervals
    (span is an upper bound) and requires >= 2 dated entries, so a truncated
    single-role resume never fires. Lead-level -> major; senior -> minor
    (title inflation at 'senior' is common — context, not accusation)."""
    intervals = [
        iv for e in experience if (iv := wide_interval(e.dates, today)) is not None
    ]
    if len(intervals) < 2:
        return []
    span = max(e for _, e in intervals) - min(s for s, _ in intervals) + 1

    def _first(pattern: re.Pattern[str], level: str) -> ExperienceEntry | None:
        return next(
            (
                e
                for e in experience
                if pattern.search(e.title or "") or (e.seniority or "") == level
            ),
            None,
        )

    lead = _first(_LEAD_RE, "staff")
    senior = _first(_SENIOR_RE, "senior")
    if lead is not None and span < lead_min_months:
        entry, floor, severity = lead, lead_min_months, FindingSeverity.MAJOR
    elif senior is not None and span < senior_min_months:
        entry, floor, severity = senior, senior_min_months, FindingSeverity.MINOR
    else:
        return []
    return [
        CrossFieldFinding(
            id="seniority_vs_tenure",
            severity=severity,
            score=min(1.0, 0.5 + 0.5 * (floor - span) / floor),
            detail=(
                f"'{entry.title}' claimed with roughly {span} months of total "
                f"career span (conservative floor for this level: {floor} months)"
            ),
            entry_ids=[entry.id],
        )
    ]
