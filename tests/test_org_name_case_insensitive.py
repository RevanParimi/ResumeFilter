"""S8.4 Phase B: 'Acme Staffing' and 'acme staffing' are one organisation.

Phase A deliberately did NOT fix this, and its reason is this task's design: a
case-insensitive CHECK without a case-insensitive CONSTRAINT creates a new
lockout -- signup refuses the name, the insert at verify succeeds anyway, and
two orgs end up sharing a name the UI treats as unique.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def cfg(settings, tmp_path):
    """Localhost-shaped, mirroring tests/test_auth_org_name_taken.py: without
    capture email the provider is 'null' and every signup 503s."""
    return settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(tmp_path / "mail.jsonl"),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
    })


@pytest.fixture
def client(cfg, flywheel):
    services = make_services(cfg, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        c.app_services = services
        yield c


def test_the_store_sees_a_case_variant_as_taken(services):
    services.ledger.create_organization("Acme Staffing")
    assert services.auth._store.organization_name_exists("acme staffing") is True
    assert services.auth._store.organization_name_exists("ACME STAFFING") is True
    assert services.auth._store.organization_name_exists("Acme  Staffing") is False, (
        "only CASE is normalised -- collapsing whitespace too would silently "
        "merge two names a customer chose to make different"
    )


def test_ledger_refuses_a_case_variant(services):
    services.ledger.create_organization("Acme Staffing")
    with pytest.raises(ValueError):
        services.ledger.create_organization("acme staffing")


def test_auth_store_refuses_a_case_variant(services):
    from app.auth.store import OrgNameTaken

    services.ledger.create_organization("Acme Staffing")
    with pytest.raises(OrgNameTaken):
        services.auth._store.create_org_with_owner(
            name="ACME STAFFING", email_hash="h" * 64
        )


def test_signup_409s_on_a_case_variant_before_a_code_is_sent(client):
    client.app_services.ledger.create_organization("Acme Staffing")
    r = client.post("/auth/org/signup",
                    json={"email": "ops@acme.in", "organization_name": "acme staffing"})
    assert r.status_code == 409
    assert r.json()["detail"] == "organization_name_taken"


def test_the_address_enumeration_property_is_untouched(client):
    """The protected fact is whether an ADDRESS has an account. A name is not an
    address, and nothing added here varies with one."""
    client.app_services.ledger.create_organization("Acme Staffing")
    known = client.post("/auth/org/signup",
                        json={"email": "ops@acme.in", "organization_name": "Fresh Co"})
    unknown = client.post("/auth/org/signup",
                          json={"email": "nobody@nowhere.in", "organization_name": "Other Co"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
