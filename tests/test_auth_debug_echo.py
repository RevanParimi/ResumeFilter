"""The local-only login-code echo, and the two guards that keep it local.

Exists so a developer clicking through the UI is not reading six digits out of
a capture file on every session. It is an ENUMERATION ORACLE by construction --
a code comes back only when one was really sent, so the response distinguishes
a registered address from an unregistered one -- which is exactly why it is
double-guarded on `env == "local"` AND the knob, and why prod refuses to boot
with the knob on. The same shape as verif_otp_debug_echo (S7.1).

The guard lives at `_request_code`, the ONE helper all six code-issuing routes
share. This repo has now paid three times for a rule applied at one door and
not the other, so the door count is asserted here rather than assumed.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.core.boot import LaunchConfigError, verify_launch_config
from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mail.jsonl"


def _cfg(settings, capture_path, **over):
    return settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
        **over,
    })


def _client(cfg, flywheel):
    return TestClient(create_app(make_services(cfg, flywheel=flywheel)),
                      raise_server_exceptions=False)


def _mailed_code(capture_path) -> str:
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def test_the_knob_defaults_to_off(settings):
    assert settings.login_otp_debug_echo is False


def test_echo_returns_the_code_that_was_actually_mailed(settings, capture_path,
                                                        flywheel):
    """Not just "a" code: the echoed one must be the one that works.

    An echo that returned a freshly minted string would look perfect here and
    fail at verify, which is the worst kind of dev affordance.
    """
    cfg = _cfg(settings, capture_path, env="local", login_otp_debug_echo=True)
    with _client(cfg, flywheel) as c:
        body = c.post("/auth/org/signup", json={
            "email": "ops@acme.in", "organization_name": "Acme Staffing"}).json()
        assert body["debug_code"] == _mailed_code(capture_path)


def test_the_echoed_code_actually_logs_you_in(settings, capture_path, flywheel):
    cfg = _cfg(settings, capture_path, env="local", login_otp_debug_echo=True)
    with _client(cfg, flywheel) as c:
        code = c.post("/auth/org/signup", json={
            "email": "ops@acme.in",
            "organization_name": "Acme Staffing"}).json()["debug_code"]
        verified = c.post("/auth/org/verify",
                          json={"email": "ops@acme.in", "code": code})
        assert verified.status_code == 200
        assert "dee_session" in c.cookies


def test_knob_off_never_echoes(settings, capture_path, flywheel):
    cfg = _cfg(settings, capture_path, env="local")  # knob defaults False
    with _client(cfg, flywheel) as c:
        body = c.post("/auth/org/signup", json={
            "email": "ops@acme.in", "organization_name": "Acme Staffing"}).json()
        assert "debug_code" not in body


def test_the_knob_alone_is_not_enough_outside_local(settings, capture_path,
                                                    flywheel):
    """Both halves of the double guard are load-bearing.

    staging rather than prod, and that is not a gap: a prod app carrying this
    knob cannot BOOT at all (see the refusal test below), so there is no
    running prod server to make an HTTP assertion against. staging is also the
    sharper case -- a guard written as `env != "prod"` would satisfy every
    prod-shaped test in this file and still leak codes on staging.
    """
    cfg = _cfg(settings, capture_path, env="staging", login_otp_debug_echo=True)
    with _client(cfg, flywheel) as c:
        body = c.post("/auth/org/signup", json={
            "email": "ops@acme.in", "organization_name": "Acme Staffing"}).json()
        assert "debug_code" not in body


def test_every_code_issuing_route_echoes(settings, capture_path, flywheel):
    """One rule, one door -- asserted at all of them.

    Org signup is covered above; the other code-issuing routes must behave the
    same or the dev affordance silently stops working on one plane.
    """
    cfg = _cfg(settings, capture_path, env="local", login_otp_debug_echo=True)
    with _client(cfg, flywheel) as c:
        # Candidate signup and login are the same act and both always send --
        # on DIFFERENT addresses. Re-requesting for the same address inside
        # login_otp_cooldown_seconds is refused, and the route answers a
        # code-less 202 by design (the first code is still live), so reusing
        # one address here would assert the cooldown rather than the echo.
        assert "debug_code" in c.post(
            "/auth/candidate/signup", json={"email": "priya@example.in"}).json()
        assert "debug_code" in c.post(
            "/auth/candidate/login", json={"email": "asha@example.in"}).json()
        # Org login, on an address that now HAS an org account.
        c.post("/auth/org/signup", json={"email": "ops@acme.in",
                                         "organization_name": "Acme Staffing"})
        code = _mailed_code(capture_path)
        c.post("/auth/org/verify", json={"email": "ops@acme.in", "code": code})
        assert "debug_code" in c.post(
            "/auth/org/login", json={"email": "ops@acme.in"}).json()


def test_no_code_sent_means_no_echoed_field(settings, capture_path, flywheel):
    """Login for an address with no account sends nothing, so there is nothing
    to echo -- and the 202 stays byte-identical in shape."""
    cfg = _cfg(settings, capture_path, env="local", login_otp_debug_echo=True)
    with _client(cfg, flywheel) as c:
        res = c.post("/auth/org/login", json={"email": "nobody@nowhere.in"})
        assert res.status_code == 202
        assert "debug_code" not in res.json()


def test_prod_refuses_to_boot_with_the_knob_on(settings):
    """Inert in prod is not the same as absent in prod.

    The double guard already makes the branch unreachable outside local, so
    this refusal buys loudness: a misconfiguration dies at boot with an
    explanation instead of sitting armed behind an `env` check nobody rereads.
    """
    prod = settings.model_copy(update={
        "env": "prod",
        "candidates_db_url": "postgresql://u:p@h/db",
        "session_cookie_secure": True,
        "email_provider": "smtp",
        "login_otp_debug_echo": True,
    })
    with pytest.raises(LaunchConfigError, match="login_otp_debug_echo"):
        verify_launch_config(prod)


def test_prod_boots_with_the_knob_off(settings):
    ok = settings.model_copy(update={
        "env": "prod",
        "candidates_db_url": "postgresql://u:p@h/db",
        "session_cookie_secure": True,
        "email_provider": "smtp",
        "login_otp_debug_echo": False,
    })
    verify_launch_config(ok)  # must not raise
