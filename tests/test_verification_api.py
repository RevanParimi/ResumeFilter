"""S7.1 candidate-plane routes: the key is the only identity input that counts."""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.models import CandidateRow
from app.main import create_app
from app.verification.models import VerificationChallengeRow
from tests.conftest import ADMIN_HEADERS, make_services

EMAIL = "dev@example.com"


def _candidate(services, email=EMAIL, name="A Candidate"):
    store = services.candidates
    with store._session_factory() as s:
        row = CandidateRow(
            full_name=name,
            email_hash=contact_hash(
                normalize_email(email), services.settings.contact_hash_salt
            ),
        )
        s.add(row)
        s.commit()
        cid = row.id
    return cid, store.issue_access_key(cid)


@pytest.fixture
def client(settings, monkeypatch, tmp_path):
    # The lifespan (which sets app.state.services) only runs when TestClient is
    # used as a context manager -- the pattern every other tests/test_*_api.py
    # follows. create_app(services) injects the offline container.
    monkeypatch.setattr(settings, "verif_otp_debug_echo", True)
    monkeypatch.setattr(settings, "email_provider", "capture")
    monkeypatch.setattr(settings, "email_capture_path", str(tmp_path / "contact-mail.jsonl"))
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        yield c, services


def test_verifications_require_a_candidate_key(client):
    c, _ = client
    assert c.get("/portal/verifications").status_code == 401
    assert c.get("/portal/verifications", headers={"X-Candidate-Key": "bogus"}).status_code == 401


def test_self_attest_lifts_the_level(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    r = c.post("/portal/verifications", json={"method": "self_attested"}, headers=h)
    assert r.status_code == 200
    assert r.json()["verification"]["status"] == "verified"

    listed = c.get("/portal/verifications", headers=h).json()
    assert listed["assurance"]["level"] == 1  # SELF_ATTESTED
    assert listed["assurance"]["advisory"] is True


def test_otp_flow_start_wrong_code_then_correct_code(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    started = c.post(
        "/portal/verifications",
        json={"method": "otp_email", "destination": EMAIL}, headers=h,
    )
    assert started.status_code == 200
    body = started.json()
    vid = body["verification"]["id"]
    code = body["debug_code"]  # double-guarded echo, enabled in this fixture
    assert code is not None

    wrong = "0" * len(code) if code != "0" * len(code) else "1" * len(code)
    assert c.post(
        f"/portal/verifications/{vid}/confirm", json={"code": wrong}, headers=h
    ).status_code == 400

    ok = c.post(f"/portal/verifications/{vid}/confirm", json={"code": code}, headers=h)
    assert ok.status_code == 200
    assert ok.json()["status"] == "verified"
    assert c.get("/portal/verifications", headers=h).json()["assurance"]["level"] == 2

    for _ in range(2):
        assert c.post(f"/portal/verifications/{vid}/confirm", json={"code": code}, headers=h).status_code == 400
    assert services.verification._store.get_verification(vid).model_dump(mode='json') == ok.json()


@pytest.mark.parametrize('reason', ['exhausted', 'expired', 'superseded'])
def test_correct_code_cannot_revive_inactive_api_challenge(client, reason):
    c, services = client
    cid, key = _candidate(services)
    h = {'X-Candidate-Key': key}
    started = c.post('/portal/verifications', json={'method': 'otp_email', 'destination': EMAIL}, headers=h).json()
    vid, code = started['verification']['id'], started['debug_code']
    factory = services.candidates._session_factory
    with factory.begin() as session:
        values = ({'attempts': services.settings.verif_otp_max_attempts} if reason == 'exhausted' else
                  {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)} if reason == 'expired' else
                  {'last_sent_at': datetime.now(timezone.utc) - timedelta(seconds=services.settings.verif_otp_resend_cooldown_seconds + 1)})
        session.execute(update(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == vid).values(**values))
    if reason == 'superseded':
        newer = c.post('/portal/verifications', json={'method': 'otp_email', 'destination': EMAIL}, headers=h)
        assert newer.status_code == 200
    assert c.post(f'/portal/verifications/{vid}/confirm', json={'code': code}, headers=h).status_code == 400
    assert services.verification._store.get_verification(vid).status.value == ('failed' if reason == 'exhausted' else 'pending')
    completed = [a for a in services.ledger.audit_for_candidate(cid) if a.action == 'verification.complete' and a.entity_id == vid]
    assert len(completed) == (1 if reason == 'exhausted' else 0)
    if reason == 'superseded':
        body = newer.json()
        assert c.post(f"/portal/verifications/{body['verification']['id']}/confirm", json={'code': body['debug_code']}, headers=h).status_code == 200


def test_a_destination_that_is_not_on_file_is_a_400(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications",
        json={"method": "otp_email", "destination": "attacker@example.com"},
        headers={"X-Candidate-Key": key},
    )
    assert r.status_code == 400


def test_a_missing_destination_for_an_otp_method_is_a_400(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications", json={"method": "otp_email"},
        headers={"X-Candidate-Key": key},
    )
    assert r.status_code == 400


def test_an_unknown_method_is_a_422(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications", json={"method": "telepathy"},
        headers={"X-Candidate-Key": key},
    )
    assert r.status_code == 422


def test_government_id_is_not_reachable_from_the_candidate_plane(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications", json={"method": "government_id"},
        headers={"X-Candidate-Key": key},
    )
    # Refused (no IDENTITY_VERIFY grant) rather than executed -- never a 500.
    assert r.status_code in (400, 403, 422)


def test_government_id_stays_unreachable_after_a_self_granted_consent(client):
    """The consent gate alone does NOT make an unimplemented method safe: a
    candidate can grant IDENTITY_VERIFY to themselves from this very plane
    (S6.4 first-party consent), so the spine must refuse on its own."""
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    assert c.post(
        "/portal/consents", json={"purpose": "identity_verify"}, headers=h
    ).status_code == 200

    r = c.post("/portal/verifications", json={"method": "government_id"}, headers=h)
    assert r.status_code == 422
    assert c.get("/portal/verifications", headers=h).json()["assurance"]["level"] == 0


def test_a_candidate_cannot_self_award_an_operator_review(client):
    """L3 REVIEWED asserts a human checked this person. It is admin-plane only."""
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    r = c.post("/portal/verifications", json={"method": "manual_review"}, headers=h)
    assert r.status_code == 403

    listed = c.get("/portal/verifications", headers=h).json()
    assert listed["verifications"] == []
    assert listed["assurance"]["level"] == 0


def test_one_candidate_cannot_confirm_anothers_verification(client):
    c, services = client
    _, key_a = _candidate(services)
    _, key_b = _candidate(services, email="other@example.com", name="Other")
    started = c.post(
        "/portal/verifications", json={"method": "otp_email", "destination": EMAIL},
        headers={"X-Candidate-Key": key_a},
    ).json()
    vid, code = started["verification"]["id"], started["debug_code"]

    stolen = c.post(
        f"/portal/verifications/{vid}/confirm", json={"code": code},
        headers={"X-Candidate-Key": key_b},
    )
    assert stolen.status_code == 404  # indistinguishable from "no such id"

    # A's verification is untouched and still confirmable by A.
    assert c.post(
        f"/portal/verifications/{vid}/confirm", json={"code": code},
        headers={"X-Candidate-Key": key_a},
    ).status_code == 200


def test_the_debug_echo_is_absent_when_the_knob_is_off(settings, tmp_path):
    settings = settings.model_copy(update={"email_provider": "capture",
        "email_capture_path": str(tmp_path / "contact-mail.jsonl")})
    services = make_services(settings)  # verif_otp_debug_echo defaults to False
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        _, key = _candidate(services)
        body = c.post(
            "/portal/verifications", json={"method": "otp_email", "destination": EMAIL},
            headers={"X-Candidate-Key": key},
        ).json()
        assert "verification" in body
        assert body.get("debug_code") is None
