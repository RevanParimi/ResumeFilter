"""S3.1 LedgerStore: orgs, consent grant/revoke/status, audit-in-transaction."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture()
def store(session_factory):
    return LedgerStore(session_factory, default_consent_ttl_days=365)


@pytest.fixture()
def candidate_id(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.commit()
        return cand.id


def test_create_and_get_organization(store):
    org = store.create_organization("Acme Talent")
    assert org.status == "active"
    assert store.get_organization(org.id) == org
    assert [o.id for o in store.list_organizations()] == [org.id]


def test_duplicate_org_name_rejected(store):
    store.create_organization("Acme Talent")
    with pytest.raises(ValueError):
        store.create_organization("Acme Talent")


def test_delete_organization(store):
    org = store.create_organization("Gone Inc")
    assert store.delete_organization(org.id) is True
    assert store.get_organization(org.id) is None
    assert store.delete_organization(org.id) is False


def test_grant_defaults_ttl(store, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id,
                            purpose=ConsentPurpose.LEDGER_WRITE, now=NOW)
    assert g.org_id is None and g.revoked_at is None
    assert g.expires_at - g.granted_at == timedelta(days=365)


def test_grant_unknown_candidate_or_org(store, candidate_id):
    with pytest.raises(LookupError):
        store.grant_consent(candidate_id="nope", purpose="ledger_write")
    with pytest.raises(LookupError):
        store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id="nope")


def test_consent_status_and_revocation(store, candidate_id):
    org = store.create_organization("Acme Talent")
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=NOW)
    d = store.consent_status(candidate_id, org_id=org.id,
                             purpose="ledger_write", at=NOW)
    assert d.allowed and d.grant_id == g.id
    # other org is out of scope; other purpose is out of scope
    assert not store.consent_status(candidate_id, org_id="other",
                                    purpose="ledger_write", at=NOW).allowed
    assert not store.consent_status(candidate_id, org_id=org.id,
                                    purpose="ledger_read", at=NOW).allowed

    assert store.revoke_consent(g.id, now=NOW) is True
    assert store.revoke_consent(g.id, now=NOW) is False  # already revoked
    assert store.revoke_consent("nope") is False
    after = store.consent_status(candidate_id, org_id=org.id,
                                 purpose="ledger_write",
                                 at=NOW + timedelta(hours=1))
    assert not after.allowed


def test_expired_grant_is_inactive(store, candidate_id):
    store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                        expires_at=NOW + timedelta(days=1), now=NOW)
    assert not store.consent_status(candidate_id, org_id="any",
                                    purpose="ledger_write",
                                    at=NOW + timedelta(days=2)).allowed


def test_mutations_are_audited(store, candidate_id):
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            now=NOW)
    store.revoke_consent(g.id, now=NOW)
    actions = [a.action for a in store.audit_for_candidate(candidate_id)]
    assert actions == ["consent.grant", "consent.revoke"]
    entries = store.audit_for_candidate(candidate_id)
    assert all(a.actor_type == "candidate" and a.actor_id == candidate_id
               for a in entries)
    assert entries[0].entity_id == g.id
    assert entries[0].details["purpose"] == "ledger_write"


def test_settings_knob_exists():
    from app.core.config import Settings

    assert Settings(_env_file=None).ledger_consent_default_ttl_days == 365


def test_non_utc_caller_datetimes_are_coerced_to_utc(store, candidate_id):
    """Caller-supplied aware non-UTC `now` must land at the right UTC instant.

    SQLite drops tzinfo on write, so a naive IST wall-clock value written
    without coercion would read back 5.5h off from true UTC — a revocation
    would fail open for 5.5h, and a grant would appear not-yet-active.
    """
    ist = timezone(timedelta(hours=5, minutes=30))
    # 2026-07-19 12:00 UTC == 2026-07-19 17:30 IST.
    now_ist = NOW.astimezone(ist)

    org = store.create_organization("IST Corp")
    g = store.grant_consent(candidate_id=candidate_id, purpose="ledger_write",
                            org_id=org.id, now=now_ist)
    # A UTC instant one minute after the true UTC equivalent should see the
    # grant as active — it wouldn't if the store had written shifted
    # wall-clock time instead of the true UTC instant.
    assert store.consent_status(candidate_id, org_id=org.id,
                                purpose="ledger_write",
                                at=NOW + timedelta(minutes=1)).allowed

    revoke_now_ist = (NOW + timedelta(minutes=2)).astimezone(ist)
    assert store.revoke_consent(g.id, now=revoke_now_ist) is True
    assert not store.consent_status(candidate_id, org_id=org.id,
                                    purpose="ledger_write",
                                    at=NOW + timedelta(minutes=3)).allowed


def test_build_ledger_store(tmp_path):
    from app.core.config import Settings
    from app.ledger.store import build_ledger_store

    url = "sqlite:///" + (tmp_path / "ledger.db").as_posix()
    store = build_ledger_store(Settings(_env_file=None, candidates_db_url=url))
    assert isinstance(store, LedgerStore)
