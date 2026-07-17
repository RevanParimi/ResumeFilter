"""Interval math + timeline checks — pure, offline, conservative by design."""

from datetime import date

from app.candidates.schema import DateRange, EmploymentType, ExperienceEntry
from app.fabrication.cross_field import (
    check_timeline_gaps,
    check_timeline_overlaps,
    month_precise_interval,
    narrow_interval,
    overlap_months,
    wide_interval,
)
from app.schemas.fabrication import FindingSeverity

TODAY = date(2026, 7, 1)


def _exp(start, end, *, current=False, etype=EmploymentType.FULL_TIME, title="Engineer"):
    return ExperienceEntry(
        title=title,
        employer="Acme",
        employment_type=etype,
        dates=DateRange(start=start, end=end, is_current=current),
    )


def test_narrow_interval_shrinks_year_only_points_inward():
    # 2018–2022 certainly covers only Dec 2018 .. Jan 2022.
    iv = narrow_interval(DateRange(start="2018", end="2022"), TODAY)
    assert iv == (2018 * 12 + 11, 2022 * 12 + 0)
    # Month-precise points are exact.
    assert narrow_interval(DateRange(start="2021-01", end="2022-08"), TODAY) == (
        2021 * 12 + 0,
        2022 * 12 + 7,
    )


def test_wide_interval_expands_year_only_points_outward():
    iv = wide_interval(DateRange(start="2018", end="2022"), TODAY)
    assert iv == (2018 * 12 + 0, 2022 * 12 + 11)


def test_intervals_unusable_without_start_or_end():
    assert narrow_interval(DateRange(), TODAY) is None
    assert narrow_interval(DateRange(start="2021-01"), TODAY) is None  # open, not current
    # is_current resolves the open end to today.
    iv = narrow_interval(DateRange(start="2021-01", is_current=True), TODAY)
    assert iv == (2021 * 12 + 0, 2026 * 12 + 6)
    # Same-year year-only range shrinks to nothing -> unusable, never flagged.
    assert narrow_interval(DateRange(start="2022", end="2022"), TODAY) is None


def test_month_precise_rejects_year_only_points():
    assert month_precise_interval(DateRange(start="2020", end="2022-01"), TODAY) is None
    assert month_precise_interval(DateRange(start="2020-03", end="2022"), TODAY) is None
    assert month_precise_interval(
        DateRange(start="2020-03", is_current=True), TODAY
    ) == (2020 * 12 + 2, 2026 * 12 + 6)


def test_overlap_months_math():
    assert overlap_months((0, 11), (6, 20)) == 6
    assert overlap_months((0, 5), (6, 10)) == 0  # adjacent, not overlapping


def test_overlap_fires_major_on_long_concurrent_primary_roles():
    a = _exp("2021-01", "2022-08")
    b = _exp("2020-06", "2022-08")
    findings = check_timeline_overlaps([a, b], today=TODAY, min_months=3)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "timeline_overlap"
    assert f.severity is FindingSeverity.MAJOR  # 20 months >= 12
    assert set(f.entry_ids) == {a.id, b.id}
    assert "20 months" in f.detail


def test_overlap_below_threshold_is_silent():
    a = _exp("2021-01", "2022-12")
    b = _exp("2022-11", "2023-12")  # 2-month overlap < min 3
    assert check_timeline_overlaps([a, b], today=TODAY, min_months=3) == []


def test_overlap_ignores_internships_and_freelance():
    a = _exp("2021-01", "2022-08")
    b = _exp("2020-06", "2022-08", etype=EmploymentType.INTERNSHIP)
    c = _exp("2020-06", "2022-08", etype=EmploymentType.FREELANCE)
    assert check_timeline_overlaps([a, b, c], today=TODAY, min_months=3) == []


def test_year_only_dates_cannot_false_positive_an_overlap():
    # 2020–2022 vs 2021–2023 look overlapping, but the certain overlap is only
    # Dec 2021 .. Jan 2022 = 2 months < 3 -> silent. Conservative by design.
    a = _exp("2020", "2022")
    b = _exp("2021", "2023")
    assert check_timeline_overlaps([a, b], today=TODAY, min_months=3) == []


def test_gap_fires_minor_only_and_reads_neutral():
    a = _exp("2019-01", "2020-12")
    b = _exp("2022-03", "2023-06")  # 14-month gap
    findings = check_timeline_gaps([a, b], today=TODAY, min_months=12)
    assert len(findings) == 1
    f = findings[0]
    assert f.id == "timeline_gap"
    assert f.severity is FindingSeverity.MINOR  # gaps are NEVER major
    assert "14-month" in f.detail
    assert "legitimate" in f.detail  # neutral copy mandated


def test_contiguous_roles_have_no_gap():
    a = _exp("2019-01", "2020-12")
    b = _exp("2021-01", "2023-06")
    assert check_timeline_gaps([a, b], today=TODAY, min_months=12) == []


def test_gaps_skip_year_only_dates_entirely():
    # Year precision can't measure a gap honestly -> never flagged.
    a = _exp("2018", "2019")
    b = _exp("2022", "2023")
    assert check_timeline_gaps([a, b], today=TODAY, min_months=12) == []
