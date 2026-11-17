"""LedgerStore per-org reliability weight."""

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.store import LedgerStore


def _settings() -> Settings:
    import os
    os.environ.setdefault("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365, settings=_settings())


def _org(store, name):
    return store.create_organization(name)


def test_set_org_reliability_validates_and_audits(store):
    org = _org(store, "Org A")
    updated = store.set_org_reliability(org.id, 1.5)
    assert updated.reliability_weight == 1.5
    assert store.get_organization(org.id).reliability_weight == 1.5
    with pytest.raises(ValueError):
        store.set_org_reliability(org.id, -0.1)
    with pytest.raises(LookupError):
        store.set_org_reliability("nope", 1.0)
