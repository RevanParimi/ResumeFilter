"""Double-submit CSRF tokens (S8.2). Pure."""

from __future__ import annotations

from app.auth.csrf import csrf_matches, generate_csrf_token


def test_tokens_are_distinct():
    assert generate_csrf_token(32) != generate_csrf_token(32)


def test_matching_tokens_pass():
    token = generate_csrf_token(32)
    assert csrf_matches(token, token) is True


def test_mismatched_tokens_fail():
    assert csrf_matches(generate_csrf_token(32), generate_csrf_token(32)) is False


def test_absent_or_empty_never_matches():
    """THE trap in a double-submit implementation: two empty strings are equal,
    so a naive compare passes a request carrying neither cookie nor header --
    which is every CSRF attack."""
    assert csrf_matches("", "") is False
    assert csrf_matches(None, None) is False
    assert csrf_matches("tok", "") is False
    assert csrf_matches("", "tok") is False
    assert csrf_matches("tok", None) is False
    assert csrf_matches(None, "tok") is False
