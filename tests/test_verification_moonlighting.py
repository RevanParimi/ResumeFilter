"""S7.2 concurrent-employment advisory. Derived from the candidate's OWN
resume intervals, computed at read time, never stored, never an accusation."""

from datetime import date

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.moonlighting import assess_concurrent_employment

TODAY = date(2026, 7, 31)


def _p(*ranges):
    return CandidateProfile(experience=[
        ExperienceEntry(employer=f"Emp{i}", title="Engineer",
                        dates=DateRange(start=s, end=e))
        for i, (s, e) in enumerate(ranges)
    ])


def test_non_overlapping_roles_produce_no_advisory():
    assert assess_concurrent_employment(
        _p(("2020-01", "2021-12"), ("2022-01", "2023-12")), today=TODAY, min_months=12
    ) is None


def test_a_long_overlap_is_surfaced_with_its_period_and_months():
    ce = assess_concurrent_employment(
        _p(("2021-01", "2023-12"), ("2022-01", "2023-12")), today=TODAY, min_months=12
    )
    assert ce is not None
    assert ce.max_overlap_months == 24
    assert ce.periods == ["2022-01..2023-12"]
    assert ce.advisory is True


def test_an_overlap_below_the_threshold_is_ignored():
    """The threshold is deliberately higher than the S2.2 fabrication check:
    a 3-month overlap is a notice period, not a second job."""
    assert assess_concurrent_employment(
        _p(("2021-01", "2022-03"), ("2022-01", "2023-12")), today=TODAY, min_months=12
    ) is None


def test_severity_rises_with_the_length_of_the_overlap():
    short = assess_concurrent_employment(
        _p(("2021-01", "2022-06"), ("2022-01", "2023-12")), today=TODAY, min_months=6)
    long = assess_concurrent_employment(
        _p(("2019-01", "2023-12"), ("2020-01", "2023-12")), today=TODAY, min_months=6)
    assert short.severity == "info"
    assert long.severity == "soft"


def test_severity_never_exceeds_soft():
    """An overlap is context for a conversation, never an accusation, so the
    ladder deliberately has no 'hard' rung."""
    ce = assess_concurrent_employment(
        _p(("2010-01", "2023-12"), ("2011-01", "2023-12")), today=TODAY, min_months=6)
    assert ce.severity == "soft"


def test_internships_and_freelance_do_not_count_as_concurrent_primary_roles():
    from app.candidates.schema import EmploymentType
    profile = CandidateProfile(experience=[
        ExperienceEntry(employer="A", dates=DateRange(start="2021-01", end="2023-12")),
        ExperienceEntry(employer="B", dates=DateRange(start="2021-01", end="2023-12"),
                        employment_type=EmploymentType.INTERNSHIP),
    ])
    assert assess_concurrent_employment(profile, today=TODAY, min_months=12) is None


def test_part_time_and_contract_are_non_primary_exactly_as_in_cross_field():
    """One notion of "primary" across the codebase: S7.2 imports S2.2's set
    rather than keeping a second, drifting copy."""
    from app.candidates.schema import EmploymentType
    for kind in (EmploymentType.PART_TIME, EmploymentType.CONTRACT):
        profile = CandidateProfile(experience=[
            ExperienceEntry(employer="A",
                            dates=DateRange(start="2021-01", end="2023-12")),
            ExperienceEntry(employer="B", employment_type=kind,
                            dates=DateRange(start="2021-01", end="2023-12")),
        ])
        assert assess_concurrent_employment(profile, today=TODAY, min_months=12) is None


def test_an_empty_or_undated_profile_is_no_advisory_not_an_error():
    assert assess_concurrent_employment(CandidateProfile(), today=TODAY,
                                        min_months=12) is None
    assert assess_concurrent_employment(
        _p((None, None), (None, None)), today=TODAY, min_months=12) is None


def test_a_none_profile_is_no_advisory():
    assert assess_concurrent_employment(None, today=TODAY, min_months=12) is None


def test_multiple_overlapping_pairs_all_appear():
    """Three roles, three pairwise overlaps, three distinct windows."""
    ce = assess_concurrent_employment(
        _p(("2018-01", "2021-12"), ("2019-01", "2023-12"), ("2020-01", "2025-12")),
        today=TODAY, min_months=12,
    )
    assert ce.periods == [
        "2019-01..2021-12",   # roles 0 & 1
        "2020-01..2021-12",   # roles 0 & 2
        "2020-01..2023-12",   # roles 1 & 2
    ]
    assert ce.max_overlap_months == 48


def test_pairs_landing_on_the_same_window_are_reported_once():
    """Three roles ending together produce the same window twice; repeating it
    would inflate an advisory signal without adding information."""
    ce = assess_concurrent_employment(
        _p(("2020-01", "2023-12"), ("2021-01", "2023-12"), ("2022-01", "2023-12")),
        today=TODAY, min_months=12,
    )
    assert ce.periods == ["2021-01..2023-12", "2022-01..2023-12"]


def test_no_period_label_names_an_employer():
    """Advisory output is intervals only -- the org read is consent-gated but
    still has no business learning WHICH employers from this signal."""
    ce = assess_concurrent_employment(
        _p(("2021-01", "2023-12"), ("2022-01", "2023-12")), today=TODAY, min_months=12)
    assert all("Emp" not in p for p in ce.periods)
