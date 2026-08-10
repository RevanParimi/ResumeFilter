"""S8.3 Phase A: bounded per CALL is not bounded per CALLER.

`process` is capped at screening_max_items_per_call, which bounds ONE request
and says nothing at all about a client in a loop -- and every call bills a
model. The S8.5 wiring session named this gap when it made ANY error stop the
browser's driver loop, because there was no limiter to stop it properly.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def test_process_is_refused_past_the_per_org_hourly_limit(
    settings, fake_github, flywheel, genuine_resume
):
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 2})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume, genuine_resume]).json()["id"]
        for _ in range(2):
            assert c.post(f"/screening/batches/{bid}/process",
                          headers={"X-Org-Key": key}).status_code == 200
        refused = c.post(f"/screening/batches/{bid}/process",
                         headers={"X-Org-Key": key})
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0


def test_one_org_s_spend_does_not_limit_another(
    settings, fake_github, flywheel, genuine_resume
):
    """The scope is the ORG. A global counter would let one noisy customer stop
    every other customer's screening -- a denial of service we would be
    inflicting on ourselves."""
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 1})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        bid_a = _register(c, key_a, [genuine_resume]).json()["id"]
        assert c.post(f"/screening/batches/{bid_a}/process",
                      headers={"X-Org-Key": key_a}).status_code == 200
        # A is now at its limit for the hour...
        bid_a2 = _register(c, key_a, [genuine_resume], name="Q4").json()["id"]
        assert c.post(f"/screening/batches/{bid_a2}/process",
                      headers={"X-Org-Key": key_a}).status_code == 429
        # ...and B is entirely unaffected.
        bid_b = _register(c, key_b, [genuine_resume]).json()["id"]
        assert c.post(f"/screening/batches/{bid_b}/process",
                      headers={"X-Org-Key": key_b}).status_code == 200


def test_the_limit_is_checked_before_any_item_is_claimed(
    settings, fake_github, flywheel, genuine_resume
):
    """A refused call must not leave items stuck in `processing` waiting out a
    claim timeout -- the S8.4 Phase B finding (4) shape: a bound that runs
    AFTER the work it bounds."""
    tuned = settings.model_copy(update={
        "rate_limit_process_per_hour_per_org": 1,
        "screening_max_items_per_call": 1,
    })
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume, genuine_resume]).json()["id"]
        assert c.post(f"/screening/batches/{bid}/process",
                      headers={"X-Org-Key": key}).status_code == 200
        assert c.post(f"/screening/batches/{bid}/process",
                      headers={"X-Org-Key": key}).status_code == 429
        detail = c.get(f"/screening/batches/{bid}",
                       headers={"X-Org-Key": key}).json()
    assert detail["counts"].get("processing", 0) == 0
    assert detail["counts"].get("pending", 0) == 1


def test_an_unlimited_org_is_unaffected_when_the_limiter_is_off(
    settings, fake_github, flywheel, genuine_resume
):
    tuned = settings.model_copy(update={
        "rate_limit_enabled": False, "rate_limit_process_per_hour_per_org": 1,
    })
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        for _ in range(4):
            assert c.post(f"/screening/batches/{bid}/process",
                          headers={"X-Org-Key": key}).status_code == 200
