"""GET /admin/signal-quality (S9.1 Task 10).

ADMIN PLANE, AND THERE IS NO ORG VARIANT. The report is cross-tenant by
construction: an organisation must not be able to learn how well the fraud
screen performs against other organisations' candidates.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


@pytest.fixture
def client(settings):
    with TestClient(create_app(make_services(settings)),
                    raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        yield c


@pytest.fixture
def anon(settings):
    with TestClient(create_app(make_services(settings)),
                    raise_server_exceptions=False) as c:
        yield c


def test_route_is_admin_gated(anon):
    assert anon.get("/admin/signal-quality").status_code in (401, 403)


def test_route_returns_refusals_on_an_empty_database(client):
    body = client.get("/admin/signal-quality").json()
    assert body["population"]["label_source"] == "outcomes"
    assert body["population"]["labels_usable"] == 0
    assert all(s["sufficient"] is False for s in body["signals"])
    assert len(body["signals"]) == 12


def test_the_ledger_source_is_selectable(client):
    body = client.get("/admin/signal-quality?source=ledger").json()
    assert body["population"]["label_source"] == "ledger"
    assert body["population"]["label_kind"] == "hire"
    fraud = next(s for s in body["signals"] if s["signal"] == "fabrication_risk.score")
    assert fraud["reason"] == "label_kind_mismatch"


def test_an_unknown_source_is_refused_with_422(client):
    assert client.get("/admin/signal-quality?source=nonsense").status_code == 422


def test_operator_labels_are_opt_in_over_the_wire(client):
    body = client.get("/admin/signal-quality?include_operator_labels=true").json()
    assert body["population"]["include_operator_labels"] is True


def test_the_default_is_to_EXCLUDE_operator_labels(client):
    """Opt-in, not opt-out: training on our own self-labels believing a
    customer produced them is circular, so the safe value is the default."""
    body = client.get("/admin/signal-quality").json()
    assert body["population"]["include_operator_labels"] is False


def test_the_sample_floor_comes_from_config_not_a_literal(settings):
    """The knob exists because the right floor is an empirical question this
    repo cannot yet answer; a hardcoded 30 would make it unanswerable."""
    settings = settings.model_copy(update={"min_signal_quality_samples": 1})
    with TestClient(create_app(make_services(settings)),
                    raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        body = c.get("/admin/signal-quality").json()
    fraud = next(s for s in body["signals"] if s["signal"] == "fabrication_risk.score")
    assert fraud["detail"].endswith("need 1")
