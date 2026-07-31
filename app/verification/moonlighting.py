"""Concurrent-employment advisory (S7.2).

Derived, never stored. The overlap arithmetic already exists -- S2.2's
`check_timeline_overlaps` has computed it since PI-2 -- so this module reuses
that machinery rather than growing a second notion of "when". Storing the
result would go stale exactly as a stored assurance would.

This is NOT an accusation. Overlapping intervals are consulting, notice
periods, and year-only date imprecision at least as often as dual employment,
so the threshold is deliberately higher than the fabrication check's and the
output tops out at "soft".
"""

from __future__ import annotations

import itertools
from datetime import date
from typing import Optional

from app.candidates.schema import CandidateProfile
# _NON_PRIMARY is imported rather than restated so the two modules cannot drift
# on what "primary" means: internships, part-time, contract and freelance work
# legitimately run alongside a full-time role.
from app.fabrication.cross_field import (
    _NON_PRIMARY, narrow_interval, overlap_months, ym_label,
)
from app.verification.schema import ConcurrentEmployment

_SOFT_MONTHS = 24   # two years of concurrency is worth a conversation


def assess_concurrent_employment(
    profile: Optional[CandidateProfile], *, today: date, min_months: int
) -> Optional[ConcurrentEmployment]:
    """Advisory overlap between concurrent PRIMARY roles, or None."""
    if profile is None or not profile.experience:
        return None

    dated = [
        (e, iv)
        for e in profile.experience
        if e.employment_type not in _NON_PRIMARY
        and (iv := narrow_interval(e.dates, today)) is not None
    ]

    periods: list[str] = []
    longest = 0
    for (_, ia), (_, ib) in itertools.combinations(dated, 2):
        months = overlap_months(ia, ib)
        if months < min_months:
            continue
        start, end = max(ia[0], ib[0]), min(ia[1], ib[1])
        label = f"{ym_label(start)}..{ym_label(end)}"
        if label not in periods:
            periods.append(label)
        longest = max(longest, months)

    if not periods:
        return None
    return ConcurrentEmployment(
        periods=periods,
        max_overlap_months=longest,
        severity="soft" if longest >= _SOFT_MONTHS else "info",
    )
