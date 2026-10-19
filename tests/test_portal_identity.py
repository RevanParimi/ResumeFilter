"""S7.1: the DPDP access view surfaces identity assurance + its retention window."""

from app.candidates.models import CandidateRow
from app.verification.schema import AssuranceLevel, VerificationMethod
from tests.conftest import make_services
from tests.test_auth_api import client, cfg, capture_path, _signup_candidate, _code  # noqa: F401


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def test_my_data_reports_identity_assurance(settings):
    services = make_services(settings)
    cid = _candidate(services)
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    data = services.portal.my_data(cid)
    assert data.identity is not None
    assert data.identity.level is AssuranceLevel.SELF_ATTESTED


def test_my_data_reports_level_none_before_any_verification(settings):
    services = make_services(settings)
    cid = _candidate(services)
    assert services.portal.my_data(cid).identity.level is AssuranceLevel.NONE


def test_retention_policy_includes_the_verifications_window(settings):
    services = make_services(settings)
    cid = _candidate(services)
    classes = {w.data_class for w in services.portal.my_data(cid).retention.windows}
    assert "verifications" in classes


def test_my_data_carries_the_claim_roll_up(settings):
    """S7.2: the DPDP access view surfaces claim evidence beside identity, and
    the two stay separate numbers."""
    import base64

    from app.verification.schema import ClaimStrength, DocumentType

    services = make_services(settings)
    cid = _candidate(services)
    services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        base64.b64encode(b"Employed with Acme from March 2021 to January 2024. "
                         b"Head of Human Resources.").decode("ascii"))
    data = services.portal.my_data(cid)
    assert data.claims is not None
    assert data.claims.strength is ClaimStrength.DOCUMENTED
    assert data.identity is not None                      # S7.1 unchanged
    assert data.identity.level is AssuranceLevel.NONE     # and unlifted


def test_two_proved_principals_keep_subjects_after_conflicting_uploads(client, capture_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.conftest import ADMIN_HEADERS

    a = client.post('/candidates', headers=ADMIN_HEADERS, json={'resume_text':
        'Synthetic Alice\nEmail: alice@example.in\nPhone: 9876543210\nSKILLS\nPython\n'}).json()['candidate_id']
    _signup_candidate(client, capture_path, 'alice@example.in')
    assert client.get('/portal/me').json()['candidate_id'] == a
    b = client.post('/candidates', headers=ADMIN_HEADERS, json={'resume_text':
        'Synthetic Bob\nEmail: bob@example.in\nPhone: 9876543210\nSKILLS\nJava\n'}).json()['candidate_id']
    assert a != b
    with TestClient(create_app(client.app_services)) as other:
        assert other.post('/auth/candidate/signup', json={'email': 'bob@example.in'}).status_code == 202
        assert other.post('/auth/candidate/verify', json={'email': 'bob@example.in', 'code': _code(capture_path),
            'candidate_id': a}).status_code == 200
        assert other.get('/portal/me').json()['candidate_id'] == b
        own = client.get('/portal/me')
        assert own.json()['candidate_id'] == a
        assert own.json()['identity']['level'] == 0
        assert 'login_email_hash' not in own.text
        assert {r['id'] for r in own.json()['resumes']}.isdisjoint(
            {r['id'] for r in other.get('/portal/me').json()['resumes']})


def test_legacy_review_refusal_keeps_existing_cookie_subject(client, capture_path, cfg):
    from app.auth.schema import PrincipalKind
    from datetime import datetime, timezone

    services = client.app_services
    with services.session_factory.begin() as session:
        row = CandidateRow(id='legacy-subject', email_hash=services.auth.hash_email('legacy@example.in'),
                           login_binding_review_required=True)
        session.add(row)
    token, _ = services.auth._store.create_session(kind=PrincipalKind.CANDIDATE, subject_id='legacy-subject',
        csrf_token='synthetic-csrf', at=datetime.now(timezone.utc))
    client.cookies.set(cfg.session_cookie_name, token)
    assert client.get('/portal/me').json()['candidate_id'] == 'legacy-subject'
    assert client.post('/auth/candidate/login', json={'email': 'legacy@example.in'}).status_code == 202
    refused = client.post('/auth/candidate/verify', json={'email': 'legacy@example.in', 'code': _code(capture_path)})
    assert refused.status_code == 409
    assert 'set-cookie' not in refused.headers
    assert client.get('/portal/me').json()['candidate_id'] == 'legacy-subject'
