"""Same-origin retires SameSite=None (S8.6 spec 2.3).

CSRF is deliberately KEPT. SameSite=Lax already blocks cross-site POST, so the
naive read is that the CSRF layer is now redundant. It stays because it is
built, tested and free; because Lax is a browser-side control and the server
must not delegate its only defence to the client's correctness; and because
removing it is a large change to the authenticated write path of every plane in
the sprint that moves the cookie posture. Trading one property for another by
accident is how a defence disappears.
"""

from app.core.config import Settings


def test_the_shipped_default_is_lax(settings):
    assert settings.session_cookie_samesite == "lax"


def test_none_is_still_a_permitted_value():
    """A separately-hosted UI is still a supported deployment; it is simply no
    longer the one we ship."""
    s = Settings(session_cookie_samesite="none")
    assert s.session_cookie_samesite == "none"


def test_csrf_survives_the_change():
    """Pinned because 'Lax blocks cross-site POST' is exactly the argument
    someone will use to delete this layer.

    A bare `hasattr` would still pass against a gutted stub, so this proves
    the round trip instead: mint a token, and only a matching cookie+header
    pair clears `csrf_matches`. That is the actual behaviour a deletion would
    remove, not just a name.
    """
    from app.auth.csrf import csrf_matches, generate_csrf_token

    token = generate_csrf_token(32)
    assert csrf_matches(token, token) is True
    assert csrf_matches(token, "an-attacker-cannot-read-this-cookie") is False
    assert csrf_matches(None, token) is False
