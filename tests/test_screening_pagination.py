"""S8.4 Phase B: the shared cursor codec.

A cursor is a keyset POSITION -- not an offset, and not a capability.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.screening.pagination import (
    InvalidCursor, clamp_limit, decode_cursor, encode_cursor,
)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def test_round_trips_a_tuple():
    assert decode_cursor(encode_cursor((0.42, "abc")), arity=2) == (0.42, "abc")


def test_round_trips_a_datetime_as_an_iso_string():
    dt = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    raw, ident = decode_cursor(encode_cursor((dt, "id-1")), arity=2)
    assert datetime.fromisoformat(raw) == dt
    assert ident == "id-1"


def test_the_cursor_is_opaque():
    """Not a promise about the encoding -- a promise that clients cannot build
    one by hand and then depend on the shape."""
    c = encode_cursor((1.0, "id-1"))
    assert "id-1" not in c and "1.0" not in c


@pytest.mark.parametrize("bad", ["", "!!!", "YWJj", "bm90LWpzb24"])
def test_a_malformed_cursor_raises_invalid_cursor(bad):
    """422 at the route, never a 500: the caller sent it, so the caller can fix
    it -- and an unhandled decode is a stack trace on the wire."""
    with pytest.raises(InvalidCursor):
        decode_cursor(bad, arity=2)


def test_wrong_arity_is_refused():
    """A cursor of the wrong width would compare a timestamp against an id."""
    with pytest.raises(InvalidCursor):
        decode_cursor(encode_cursor((1.0,)), arity=2)


def test_wrong_element_types_are_refused():
    """base64 is not validation: a cursor is attacker-typed JSON, and a decoded
    element of the wrong type raises TypeError from fromisoformat -- or a
    DBAPI error on Postgres -- neither of which is the promised 422."""
    with pytest.raises(InvalidCursor):
        decode_cursor(encode_cursor((1, "x")), arity=2, types=(str, str))
    with pytest.raises(InvalidCursor):
        decode_cursor(encode_cursor(("x", "y")), arity=2, types=((int, float), str))
    # And the passing direction, so the guard cannot refuse every cursor.
    assert decode_cursor(
        encode_cursor((0.5, "id-1")), arity=2, types=((int, float), str)
    ) == (0.5, "id-1")


def test_a_non_iso_string_where_a_datetime_belongs_is_refused():
    from app.screening.pagination import iso_datetime

    with pytest.raises(InvalidCursor):
        iso_datetime("not-a-date")
    dt = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    assert iso_datetime(str(dt)) == dt


def test_limit_defaults_and_clamps():
    s = _settings()
    assert clamp_limit(None, s) == s.page_default_limit
    assert clamp_limit(10, s) == 10
    assert clamp_limit(10_000, s) == s.page_max_limit


@pytest.mark.parametrize("bad", [0, -1])
def test_a_nonsense_limit_is_refused(bad):
    with pytest.raises(ValueError):
        clamp_limit(bad, _settings())
