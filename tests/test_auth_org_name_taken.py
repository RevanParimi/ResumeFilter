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
