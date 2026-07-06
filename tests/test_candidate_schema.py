"""Schema contracts for the candidate extraction models (S1.1)."""

import pytest
from pydantic import ValidationError

from app.candidates.schema import DateRange, ExtractedStr, SourceSpan


def test_source_span_rejects_reversed_range():
    with pytest.raises(ValidationError):
        SourceSpan(start=10, end=5, text="x")


def test_source_span_accepts_ordered_range():
    span = SourceSpan(start=3, end=8, text="hello")
    assert (span.start, span.end, span.text) == (3, 8, "hello")


def test_extracted_str_confidence_bounds():
    with pytest.raises(ValidationError):
        ExtractedStr(value="x", confidence=1.5)
    with pytest.raises(ValidationError):
        ExtractedStr(value="x", confidence=-0.1)


def test_extracted_str_defaults():
    f = ExtractedStr(value="Arjun")
    assert f.confidence == 0.5 and f.span is None


def test_date_range_defaults_to_open():
    d = DateRange()
    assert d.start is None and d.end is None and d.is_current is False
