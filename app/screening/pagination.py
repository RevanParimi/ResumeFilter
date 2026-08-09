"""One cursor codec, for every list that has a stored order (S8.4 §1.4).

A cursor is the SORT-KEY TUPLE of the last row on a page -- a keyset position,
not an offset -- so a row inserted while a client is paging can neither be
skipped nor served twice. It is base64 so callers cannot read it, hand-build
one, and then depend on a shape we mean to change.

WHAT A CURSOR IS NOT: a capability. Ownership is enforced by each query's own
``org_id`` filter, and a cursor minted on one batch and replayed against
another merely positions inside the second. Nothing here should ever grow an
ownership claim -- that would make a client-supplied string load-bearing for
tenancy, which is the opposite of Phase A's whole argument.

Deliberately NOT applied to ``POST /jobs/{id}/match`` or
``POST /talent/search``: both re-rank their pool on every request, so there is
no stored key to page on and a cursor would promise a stability it cannot keep.
They keep ``limit``, and their OpenAPI descriptions say so.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any, Optional, Union

from app.core.config import Settings


class InvalidCursor(ValueError):
    """The caller sent a cursor this code cannot read. A 422, never a 500."""


def encode_cursor(values: tuple[Any, ...]) -> str:
    """Encode a sort-key tuple. ``datetime`` serialises ISO-8601 via ``str``."""
    raw = json.dumps(list(values), default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(
    cursor: str,
    *,
    arity: int,
    types: Optional[tuple[Union[type, tuple[type, ...]], ...]] = None,
) -> tuple[Any, ...]:
    """Decode, or raise :class:`InvalidCursor`.

    ``types`` is one spec per element (a type or tuple of types, isinstance
    style). base64 is not validation: the payload is attacker-typed JSON, and
    an element of the wrong type surfaces later as ``TypeError`` from
    ``fromisoformat`` or as a DBAPI error on a typed backend -- neither of
    which is the 422 this module promises.
    """
    if not cursor:
        raise InvalidCursor("empty cursor")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        values = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InvalidCursor("malformed cursor") from exc
    if not isinstance(values, list) or len(values) != arity:
        raise InvalidCursor("malformed cursor")
    if types is not None:
        for value, spec in zip(values, types):
            if not isinstance(value, spec):
                raise InvalidCursor("malformed cursor")
    return tuple(values)


def iso_datetime(value: Any) -> datetime:
    """A cursor element as a datetime, or :class:`InvalidCursor`.

    ``datetime.fromisoformat`` raises ``TypeError`` on a non-string and
    ``ValueError`` on a non-ISO string; a cursor's caller must see one refusal
    for both.
    """
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InvalidCursor("malformed cursor") from exc


def clamp_limit(limit: Optional[int], settings: Settings) -> int:
    """Default when absent, cap when excessive, refuse when nonsensical.

    Capping rather than refusing an over-large limit is deliberate: a client
    asking for too much should get a page, not an error it has no way to size
    correctly on its first call.
    """
    if limit is None:
        return settings.page_default_limit
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return min(limit, settings.page_max_limit)
