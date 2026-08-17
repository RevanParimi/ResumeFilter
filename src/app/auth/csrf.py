"""Double-submit CSRF tokens (S8.2). Pure.

The UI is same-origin now (S8.6 spec 2.3): the shipped `session_cookie_samesite`
is `lax`, not `none`, and Lax already blocks cross-site POST. The naive read is
that this layer is now redundant -- it is not. It stays because it is built,
tested and free; because Lax is a browser-side control and the server must not
delegate its only defence to the client's correctness; and because removing it
is a large change to the authenticated write path of every plane. See
tests/test_cookie_posture.py for the pin.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Optional


def generate_csrf_token(nbytes: int) -> str:
    return secrets.token_urlsafe(nbytes)


def csrf_matches(cookie_value: Optional[str], header_value: Optional[str]) -> bool:
    """Constant-time compare, with absent/empty rejected BEFORE the compare.

    The guard is the whole point: two empty strings are equal, so without it a
    request carrying neither cookie nor header passes -- which describes every
    CSRF attack this function exists to stop.
    """
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)
