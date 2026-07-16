"""S1.4 degree canonicalization + CGPA normalization (10-point canonical)."""

import pytest

from app.candidates.normalize.degrees import normalize_degree, normalize_grade


def test_btech_aliases():
    for raw in ("B.Tech", "BTech", "b tech", "Bachelor of Technology"):
        m = normalize_degree(raw)
        assert m is not None and m.canonical == "btech", raw
        assert m.level == "bachelor"


def test_levels_across_families():
    assert normalize_degree("B.E.").level == "bachelor"
    assert normalize_degree("M.Tech").level == "master"
    assert normalize_degree("MBA").level == "master"
    assert normalize_degree("Ph.D").level == "doctorate"
    assert normalize_degree("Diploma").level == "diploma"


def test_degree_with_inline_field_of_study():
    assert normalize_degree("B.Tech (Computer Science)").canonical == "btech"
    assert normalize_degree("Bachelor of Engineering - ECE").canonical == "be"


def test_longest_alias_wins():
    # Long forms must resolve via their full alias, not a stray short token.
    assert normalize_degree("Master of Engineering").canonical == "me"
    assert normalize_degree("Post Graduate Diploma in Management").canonical == "pgdm"


def test_unknown_or_empty_degree_none():
    assert normalize_degree("Certificate in Yoga") is None
    assert normalize_degree("") is None


def test_grade_cgpa10_passthrough():
    assert normalize_grade(8.6, "cgpa_10") == 8.6


def test_grade_cgpa4_scaled():
    assert normalize_grade(3.6, "cgpa_4") == 9.0
    assert normalize_grade(4.0, "cgpa_4") == 10.0


def test_grade_percentage_cbse_conversion():
    assert normalize_grade(86.0, "percentage") == pytest.approx(9.05)
    assert normalize_grade(97.0, "percentage") == 10.0  # clamped


def test_grade_out_of_range_none():
    assert normalize_grade(11.2, "cgpa_10") is None
    assert normalize_grade(4.5, "cgpa_4") is None
    assert normalize_grade(101.0, "percentage") is None


def test_grade_missing_or_unknown_scale_none():
    assert normalize_grade(None, "cgpa_10") is None
    assert normalize_grade(8.6, None) is None
    assert normalize_grade(8.6, "letter") is None
