"""S8.4 Phase A: org signup with a taken name refused at signup, not by
rejecting a correct code at verify (spec §2.1).

The lockout this closes: 202 + a real code that then verifies as
400 invalid_code, burning the attempt counter. "Acme Staffing" is exactly the
name two customers pick.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mail.jsonl"


@pytest.fixture
def cfg(settings, capture_path):
    """Localhost-shaped, mirroring tests/test_auth_api.py: without capture
    email the provider is 'null' and every signup 503s."""
    return settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
    })


@pytest.fixture
def client(cfg, flywheel):
    services = make_services(cfg, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        c.app_services = services
        yield c


def _code(capture_path) -> str:
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def _sent(capture_path) -> int:
    if not capture_path.exists():
        return 0
    return len(capture_path.read_text(encoding="utf-8").splitlines())


def test_signup_with_a_taken_org_name_is_409_before_any_code_is_sent(
    client, capture_path
):
    client.app_services.ledger.create_organization("Acme Staffing")
    before = _sent(capture_path)

    r = client.post("/auth/org/signup",
                    json={"email": "ops@acme.example",
                          "organization_name": "Acme Staffing"})

    assert r.status_code == 409
    assert r.json()["detail"] == "organization_name_taken"
    assert _sent(capture_path) == before, "no code may be sent for a refused signup"


def test_a_free_org_name_still_returns_202(client):
    r = client.post("/auth/org/signup",
                    json={"email": "ops@new.example",
                          "organization_name": "Brand New Co"})
    assert r.status_code == 202


def test_unknown_and_known_ADDRESSES_are_still_indistinguishable(
    client, capture_path
):
    """The anti-enumeration property is about the ADDRESS, not the org name.

    Register an address by completing a signup, then compare a second signup
    from that KNOWN address against one from an unknown address, both with a
    FREE org name so the new 409 in this task cannot be the source of any
    difference.

    NOTE on what is (and is not) asserted here, deviating from the brief's
    literal text: the brief's draft additionally asserted
    `mid - before == after - mid` -- i.e. that the KNOWN address's re-signup
    and the UNKNOWN address's fresh signup send the SAME number of codes.
    That does not hold, independent of this task's change: S8.2 deliberately
    makes org-plane signup on an address that ALREADY has an org send
    NOTHING (see test_org_signup_on_a_taken_address_returns_202_and_sends_
    nothing in test_auth_api.py, and AuthService.request_code's own
    docstring -- "Signup on a taken address deliberately does NOT quietly
    send a login code instead: silently changing what the caller asked for
    is how confused-deputy bugs start"). Sending one here would mean
    `_establish` silently logs the known owner into their EXISTING org while
    ignoring the org_name they just supplied -- exactly the confused-deputy
    shape that guard exists to prevent. Reversing it is out of this task's
    scope (org_name_taken only) and is not touched.

    What DOES have to hold, and is what an external caller can ever actually
    observe, is response equivalence: identical status and identical body.
    Internally, the send counts are asserted against each address's OWN
    pre-existing, already-reviewed behaviour rather than against each other.
    """
    assert client.post("/auth/org/signup",
                       json={"email": "known@x.example",
                             "organization_name": "Known Co"}).status_code == 202
    assert client.post("/auth/org/verify",
                       json={"email": "known@x.example",
                             "code": _code(capture_path)}).status_code == 200

    before = _sent(capture_path)
    known = client.post("/auth/org/signup",
                        json={"email": "known@x.example",
                              "organization_name": "Some Free Name"})
    mid = _sent(capture_path)
    unknown = client.post("/auth/org/signup",
                          json={"email": "nobody-at-all@y.example",
                                "organization_name": "Another Free Name"})
    after = _sent(capture_path)

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert mid - before == 0, "a known address's re-signup must send nothing (S8.2)"
    assert after - mid == 1, "a genuinely new address's signup must still send a code"


def test_a_name_taken_during_the_window_is_409_not_invalid_code(
    client, capture_path
):
    """The race Task 8 cannot close: taken between signup and verify.

    This is the ONLY path that still reaches _establish's OrgNameTaken, and it
    is the one that must never resurface as 'your code is wrong'.
    """
    r = client.post("/auth/org/signup",
                    json={"email": "ops@acme.example",
                          "organization_name": "Acme Staffing"})
    assert r.status_code == 202
    code = _code(capture_path)

    # Somebody else registers the name in the window.
    client.app_services.ledger.create_organization("Acme Staffing")

    v = client.post("/auth/org/verify",
                    json={"email": "ops@acme.example", "code": code})
    assert v.status_code == 409, "a CORRECT code must never be reported as wrong"
    assert v.json()["detail"] == "organization_name_taken"


def test_every_genuine_code_failure_is_still_one_invalid_code(
    client, capture_path
):
    client.post("/auth/org/signup",
                json={"email": "ops@fresh.example",
                      "organization_name": "Fresh Co"})
    wrong = client.post("/auth/org/verify",
                        json={"email": "ops@fresh.example", "code": "000000"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "invalid_code"


def test_missing_organization_name_is_a_registration_failure_too(
    client, capture_path
):
    """Rides the same path as org_name_taken and must not read as a bad code.

    Driven through the service because the route schema requires the field --
    this state is reachable only from a machine client or a schema change, and
    it is precisely the kind of path that rots unwatched.
    """
    from datetime import datetime, timezone
    from app.auth.schema import AuthPlane, LoginPurpose

    client.app_services.auth.request_code(
        email="ops@noname.example", plane=AuthPlane.ORG,
        purpose=LoginPurpose.SIGNUP, payload={}, at=datetime.now(timezone.utc),
    )
    v = client.post("/auth/org/verify",
                    json={"email": "ops@noname.example",
                          "code": _code(capture_path)})
    assert v.status_code == 409
    assert v.json()["detail"] == "missing_organization_name"


def test_the_409_for_a_taken_name_does_not_vary_with_the_callers_address(
    client, capture_path
):
    """Deferred minor from the Task 8 review: the anti-enumeration property for
    THIS refusal is that it never varies with the caller's address, not just
    that it holds by code inspection. Pin it directly: same taken org name,
    one signup from a known address, one from an unknown address -- identical
    status, identical body, identical emails-sent delta (zero, since a 409 at
    signup never sends a code).
    """
    assert client.post("/auth/org/signup",
                       json={"email": "known2@x.example",
                             "organization_name": "Known Two Co"}).status_code == 202
    assert client.post("/auth/org/verify",
                       json={"email": "known2@x.example",
                             "code": _code(capture_path)}).status_code == 200

    client.app_services.ledger.create_organization("Contested Name")

    before = _sent(capture_path)
    known = client.post("/auth/org/signup",
                        json={"email": "known2@x.example",
                              "organization_name": "Contested Name"})
    mid = _sent(capture_path)
    unknown = client.post("/auth/org/signup",
                          json={"email": "nobody-else-at-all@y.example",
                                "organization_name": "Contested Name"})
    after = _sent(capture_path)

    assert known.status_code == unknown.status_code == 409
    assert known.json() == unknown.json() == {"detail": "organization_name_taken"}
    assert mid - before == 0
    assert after - mid == 0
