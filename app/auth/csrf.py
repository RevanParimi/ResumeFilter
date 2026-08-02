"""Double-submit CSRF tokens (S8.2). Pure.

SameSite=None is required rather than chosen -- the UI is separately hosted
(PI-8 decision 0.1), so every request is cross-site and Lax would drop the
cookie entirely. That is precisely why this layer is non-optional here rather
than belt-and-braces: the browser is not filtering anything for us.
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
