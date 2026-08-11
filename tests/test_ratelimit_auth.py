"""S8.3 Phase A: the OTP surface, limited.

The brute-force surface PI-8 created is the one the limiter exists for. These
run over real HTTP because the 429, the Retry-After header and the
indistinguishability of a known from an unknown address are properties of the
WIRE -- the same argument tests/test_auth_api.py makes for cookies and CSRF.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.auth.models import AuthSessionRow
from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mail.jsonl"


def _cfg(settings, capture_path, **over):
    """Localhost-shaped and capture-email, like tests/test_auth_api.py::cfg.

    Without a provider `request_code` raises EmailUnavailableError before it
    reaches anything this file is about.
    """
    base = {
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
        # Small limits keep these tests to a handful of requests each; the
        # DEFAULTS are asserted in tests/test_config_ratelimit.py.
        "rate_limit_login_per_hour_per_email": 3,
        "rate_limit_login_per_hour_per_ip": 100,
        "rate_limit_verify_per_hour_per_email": 3,
        "rate_limit_verify_per_hour_per_ip": 100,
    }
    base.update(over)
    return settings.model_copy(update=base)


def _client(cfg, flywheel, **kw) -> TestClient:
    services = make_services(cfg, flywheel=flywheel)
    client = TestClient(create_app(services), raise_server_exceptions=False, **kw)
    client.app_services = services
    return client


@pytest.fixture
def client(settings, capture_path, flywheel):
    with _client(_cfg(settings, capture_path), flywheel) as c:
        yield c


def _code(capture_path) -> str:
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def _login(client, email: str, **kw):
    return client.post("/auth/org/login", json={"email": email}, **kw)


def test_login_is_refused_after_the_per_email_limit(client):
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        assert _login(client, "a@example.com").status_code == 202
    refused = _login(client, "a@example.com")
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"


def test_the_429_carries_a_retry_after_header(client):
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        _login(client, "a@example.com")
    refused = _login(client, "a@example.com")
    assert int(refused.headers["Retry-After"]) > 0


def test_a_known_and_an_unknown_address_are_refused_IDENTICALLY(
    settings, capture_path, flywheel
):
    """AUTH.md's anti-enumeration rule, from the other side.

    A 429 that appeared only for registered addresses would reopen the hole the
    uniform 202 closed -- so the counter keys on the SUBMITTED address and is
    incremented BEFORE the has-an-account branch.
    """
    with _client(_cfg(settings, capture_path), flywheel) as client:
        # Register one organisation so "registered@" genuinely has an account.
        client.post("/auth/org/signup", json={
            "email": "registered@example.com", "organization_name": "Acme Staffing",
        })
        client.post("/auth/org/verify", json={
            "email": "registered@example.com", "code": _code(capture_path),
        })
        client.cookies.clear()

        limit = client.app_services.settings.rate_limit_login_per_hour_per_email
        for _ in range(limit):
            _login(client, "registered@example.com")
        for _ in range(limit):
            _login(client, "nobody@example.com")
        known = _login(client, "registered@example.com")
        unknown = _login(client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()


def test_the_429_s_HEADERS_do_not_separate_a_known_from_an_unknown_address(
    settings, capture_path, flywheel
):
    """The same rule as the test above, checked one layer lower.

    A body can be identical while a header is not, and a client-visible header
    that appears only for registered addresses is the same enumeration oracle
    with extra steps. `Retry-After` is compared loosely on purpose: both
    refusals are in the same window, so the values differ only by the seconds
    that elapsed between the two requests -- what must NOT differ is whether
    the header is there at all, and what other headers ride along.
    """
    with _client(_cfg(settings, capture_path), flywheel) as client:
        client.post("/auth/org/signup", json={
            "email": "registered@example.com", "organization_name": "Acme Staffing",
        })
        client.post("/auth/org/verify", json={
            "email": "registered@example.com", "code": _code(capture_path),
        })
        client.cookies.clear()

        limit = client.app_services.settings.rate_limit_login_per_hour_per_email
        for _ in range(limit):
            _login(client, "registered@example.com")
        for _ in range(limit):
            _login(client, "nobody@example.com")
        known = _login(client, "registered@example.com")
        unknown = _login(client, "nobody@example.com")

    # X-Request-ID is unique per request BY DESIGN and says nothing about the
    # address; every other header name must match exactly.
    def names(resp):
        return {k.lower() for k in resp.headers} - {"x-request-id"}

    assert names(known) == names(unknown)
    assert "retry-after" in names(known)
    assert abs(int(known.headers["Retry-After"])
               - int(unknown.headers["Retry-After"])) <= 5
    assert known.headers["content-type"] == unknown.headers["content-type"]
    # No cookie is ever set on a refusal -- a Set-Cookie on one and not the
    # other would be the loudest possible oracle.
    assert "set-cookie" not in names(known)


# ── the other two planes ─────────────────────────────────────────────────────
#
# The OTP surface is eight routes across THREE planes, and every one of them
# funnels through the same two service methods -- which is the argument for
# enforcing in the service layer at all. These tests are what make that
# argument checkable rather than asserted: before the S8.3 review only the org
# plane was exercised, so "all three planes are limited" was a claim about
# code structure, not a measured property.


def test_the_candidate_plane_is_limited(client):
    """The candidate plane always sends -- signup and login are the same act
    there -- so it has no has-an-account branch to accidentally bound it."""
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        assert client.post("/auth/candidate/login",
                           json={"email": "c@example.com"}).status_code == 202
    refused = client.post("/auth/candidate/login", json={"email": "c@example.com"})
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0


def test_the_admin_plane_is_limited(client):
    """Admin login for an unknown address is a silent no-op (202, nothing
    sent). It must still COUNT: an endpoint that only counts the work it does
    is an endpoint an attacker can hammer for free."""
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        assert client.post("/auth/admin/login",
                           json={"email": "root@example.com"}).status_code == 202
    refused = client.post("/auth/admin/login", json={"email": "root@example.com"})
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0


def test_the_candidate_and_admin_verify_routes_are_limited(client):
    for path in ("/auth/candidate/verify", "/auth/admin/verify"):
        limit = client.app_services.settings.rate_limit_verify_per_hour_per_email
        email = f"v{path.count('/')}{path[6]}@example.com"
        for _ in range(limit):
            client.post(path, json={"email": email, "code": "000000"})
        refused = client.post(path, json={"email": email, "code": "000000"})
        assert refused.status_code == 429, f"{path} is not limited"


def test_the_planes_SHARE_one_budget_per_address(client):
    """MEASURED in the S8.3 review, and it is worth stating rather than
    discovering: `bucket_key` is salt|rule|scope|identity, and the PLANE is not
    in it. So one address has one `login_request` budget across all three
    planes.

    That is the conservative direction -- the attacker cannot buy three times
    the guesses by rotating planes -- and the cost is that somebody who is both
    a candidate and an org user shares a single 20/hour allowance. At 20/hour
    that is not a real constraint, but a future per-plane limit would silently
    triple the real bound, so the coupling is pinned here.
    """
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        assert _login(client, "both@example.com").status_code == 202
    assert client.post("/auth/candidate/login",
                       json={"email": "both@example.com"}).status_code == 429


def test_a_second_address_is_unaffected_below_the_ip_limit(client):
    """Proves the email scope is per address and not one global counter."""
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        _login(client, "a@example.com")
    assert _login(client, "a@example.com").status_code == 429
    assert _login(client, "b@example.com").status_code == 202


def test_the_ip_scope_denies_a_spray_across_many_addresses(
    settings, capture_path, flywheel
):
    """One guess against many addresses never trips a per-email counter. With a
    low IP limit the spray is refused on an address that has never been seen --
    which is the half a per-email limit cannot see."""
    cfg = _cfg(settings, capture_path, rate_limit_login_per_hour_per_ip=3)
    with _client(cfg, flywheel) as client:
        for i in range(3):
            assert _login(client, f"user{i}@example.com").status_code == 202
        assert _login(client, "never-seen@example.com").status_code == 429


def test_x_forwarded_for_is_IGNORED_when_no_proxy_is_trusted(
    settings, capture_path, flywheel
):
    """THE decision that makes the per-IP scope worth anything.

    If the header were trusted by default, an attacker would reset their own
    scope on every request with a header they fully control, and the limiter
    would pass every other test in this file while bounding nothing.
    """
    cfg = _cfg(settings, capture_path, rate_limit_login_per_hour_per_ip=3)
    with _client(cfg, flywheel) as client:
        for i in range(3):
            _login(client, f"u{i}@example.com",
                   headers={"X-Forwarded-For": f"9.9.9.{i}"})
        refused = _login(client, "u9@example.com",
                         headers={"X-Forwarded-For": "9.9.9.99"})
    assert refused.status_code == 429


def test_x_forwarded_for_is_honoured_when_one_proxy_is_trusted(
    settings, capture_path, flywheel
):
    cfg = _cfg(
        settings, capture_path,
        rate_limit_login_per_hour_per_ip=3, rate_limit_trusted_proxy_hops=1,
    )
    with _client(cfg, flywheel) as client:
        for i in range(3):
            _login(client, f"u{i}@example.com",
                   headers={"X-Forwarded-For": "9.9.9.1"})
        allowed = _login(client, "u9@example.com",
                         headers={"X-Forwarded-For": "9.9.9.2"})
    assert allowed.status_code == 202


def test_verify_has_its_own_rule_and_does_not_share_login_s_counter(client):
    limit = client.app_services.settings.rate_limit_login_per_hour_per_email
    for _ in range(limit):
        _login(client, "a@example.com")
    assert _login(client, "a@example.com").status_code == 429
    resp = client.post(
        "/auth/org/verify", json={"email": "a@example.com", "code": "000000"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_code"


def test_a_verify_storm_is_refused(client):
    limit = client.app_services.settings.rate_limit_verify_per_hour_per_email
    for _ in range(limit):
        client.post("/auth/org/verify",
                    json={"email": "a@example.com", "code": "000000"})
    refused = client.post(
        "/auth/org/verify", json={"email": "a@example.com", "code": "000000"}
    )
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"


def test_disabling_the_limiter_restores_the_old_behaviour(
    settings, capture_path, flywheel
):
    cfg = _cfg(settings, capture_path, rate_limit_enabled=False)
    with _client(cfg, flywheel) as client:
        for _ in range(12):
            assert _login(client, "a@example.com").status_code == 202


def test_a_session_records_the_ip_hash_and_never_the_ip(
    settings, capture_path, flywheel
):
    """auth_sessions.ip_hash was DECLARED, plumbed through AuthStore and
    AuthService, and never populated -- routes.py did not pass it, so every row
    held NULL while PI-8 §7 stated the rule as though implemented. S8.3 needs
    IP extraction for the limiter anyway, so one helper closes both.
    """
    with _client(_cfg(settings, capture_path), flywheel) as client:
        client.post("/auth/org/signup", json={
            "email": "founder@example.com", "organization_name": "Acme Staffing",
        })
        resp = client.post("/auth/org/verify", json={
            "email": "founder@example.com", "code": _code(capture_path),
        })
        assert resp.status_code == 200
        factory = client.app_services.candidates._session_factory
        with factory() as session:
            row = session.query(AuthSessionRow).one()
            assert row.ip_hash, "ip_hash must be populated"
            assert "." not in row.ip_hash, "an ip_hash is a hash, never an address"
            assert len(row.ip_hash) == 64
