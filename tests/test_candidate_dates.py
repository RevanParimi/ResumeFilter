"""Deterministic career date-range parsing (S1.1)."""

from app.candidates.dates import date_points, has_date_range, parse_date_range


def test_month_year_range_with_present():
    d = parse_date_range("Jun 2021 - Present")
    assert d.start == "2021-06" and d.end is None and d.is_current is True


def test_full_month_names_and_to_separator():
    d = parse_date_range("January 2020 to March 2022")
    assert d.start == "2020-01" and d.end == "2022-03" and d.is_current is False


def test_year_only_range():
    d = parse_date_range("2014 - 2018")
    assert d.start == "2014" and d.end == "2018" and d.is_current is False


def test_numeric_month_slash_year():
    d = parse_date_range("03/2021 - 06/2023")
    assert d.start == "2021-03" and d.end == "2023-06"


def test_no_dates_returns_open_range():
    d = parse_date_range("Built streaming pipelines processing 2TB/day")
    assert d.start is None and d.end is None


def test_date_points_positions_are_ordered():
    pts = date_points("Data Engineer, Infosys — Jul 2018 - May 2021")
    assert [v for _, v in pts] == ["2018-07", "2021-05"]
    assert pts[0][0] < pts[1][0]


def test_has_date_range_detects_career_lines():
    assert has_date_range("Jun 2021 - Present") is True
    assert has_date_range("2014 - 2018, CGPA: 8.6/10") is True
    assert has_date_range("Built pipelines processing 2TB/day") is False
    assert has_date_range("CGPA: 8.6/10") is False
