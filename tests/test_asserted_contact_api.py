"""Two candidate sessions, two org uploads and reviewed change refusal."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.test_auth_api import client, cfg, capture_path, _signup_candidate, _code  # noqa: F401


def upload(http, text, *, headers=ADMIN_HEADERS, door='/candidates', evaluate=False):
    response = http.post(door, headers=headers, json={'resume_text': text, 'evaluate': evaluate})
    assert response.status_code == 200, response.text
    return response.json()


def test_two_principals_phone_claim_and_contact_backfill_stay_separate(client, capture_path):
    aid = upload(client, 'Synthetic Alice\nEmail: alice@example.in\nSKILLS\nPython\n')['candidate_id']
    _signup_candidate(client, capture_path, 'alice@example.in')
    services = client.app_services
    with TestClient(create_app(services)) as bob:
        bid = upload(bob, 'Synthetic Bob\nEmail: bob@example.in\nPhone: 9876543210\nSKILLS\nJava\n')['candidate_id']
        _signup_candidate(bob, capture_path, 'bob@example.in')
        key = services.candidates.issue_access_key(aid)
        a2 = upload(client, 'Synthetic Alice\nEmail: alice@example.in\nPhone: 9876543210\nSKILLS\nPython\n')
        unknown = upload(client, 'Synthetic phone claimant\nPhone: 9876543210\nSKILLS\nGo\n')
        assert a2['candidate_id'] == aid and unknown['candidate_id'] not in {aid, bid}
        with services.session_factory() as session:
            assert session.get(CandidateRow, aid).phone_hash is None
            assert session.get(CandidateRow, bid).phone_hash is not None
            extracted = session.scalar(select(ExtractionRow).where(ExtractionRow.resume_id == a2['resume_id']))
            assert extracted.profile['contact']['phone_hash'] is not None
        av, bv = client.get('/portal/me').json(), bob.get('/portal/me').json()
        assert av['candidate_id'] == aid and bv['candidate_id'] == bid
        assert av['identity']['level'] == bv['identity']['level'] == 0
        assert {r['id'] for r in av['resumes']}.isdisjoint({r['id'] for r in bv['resumes']})
        assert services.candidates.authenticate_candidate(key) == aid


def test_two_orgs_reupload_proved_candidate_owns_distinct_resume_rows(client, capture_path):
    services = client.app_services
    original = 'Synthetic Alice\nEmail: alice@example.in\nSKILLS\nPython\n'
    aid = upload(client, original)['candidate_id']
    _signup_candidate(client, capture_path, 'alice@example.in')
    orgs = [services.ledger.create_organization(name) for name in ('Agency A', 'Agency B')]
    headers = [{'X-Org-Key': services.ledger.issue_api_key(org.id)} for org in orgs]
    with TestClient(create_app(services)) as uploader:
        responses = [upload(uploader, original, headers=h, door='/screening/candidates', evaluate=True) for h in headers]
        assert all(r['candidate_id'] == aid for r in responses)
        assert len({r['resume_id'] for r in responses}) == 2
        repeated = upload(uploader, original, headers=headers[1], door='/screening/candidates')
        assert repeated['resume_id'] == responses[1]['resume_id']
        with services.session_factory() as session:
            assert [session.get(ResumeRow, r['resume_id']).org_id for r in responses] == [o.id for o in orgs]
        for index, (h, response) in enumerate(zip(headers, responses)):
            own = uploader.get(f"/screening/reports/{response['report']['id']}", headers=h)
            assert own.status_code == 200
            assert uploader.get(f"/screening/reports/{response['report']['id']}", headers=headers[1-index]).status_code == 404
        assert len(client.get('/portal/me').json()['resumes']) == 3


@pytest.mark.parametrize('field,value', [('email', 'bob@example.in'), ('phone', '+91 9876543210')])
def test_contact_correction_refuses_apply_and_records_review_without_mutation(client, capture_path, field, value):
    aid = upload(client, 'Synthetic Alice\nEmail: alice@example.in\nSKILLS\nPython\n')['candidate_id']
    csrf = _signup_candidate(client, capture_path, 'alice@example.in')
    services = client.app_services
    with services.session_factory() as session:
        row = session.get(CandidateRow, aid)
        before = (row.email_hash, row.phone_hash, row.login_email_hash, row.login_email_verified_at,
                  row.login_binding_review_required)
    submitted = client.post('/portal/corrections', headers={'X-CSRF-Token': csrf},
        json={'field': field, 'requested_value': value, 'candidate_id': 'foreign-target'})
    assert submitted.status_code == 200
    request_id = submitted.json()['id']
    decision = {'status': 'resolved', 'resolution': 'Reviewed: change/merge unsupported.', 'apply': True}
    refused = client.post(f'/admin/requests/{request_id}/resolve', headers=ADMIN_HEADERS, json=decision)
    assert refused.status_code == 422 and 'unsupported' in refused.json()['detail']
    pending = client.get('/portal/requests').json()
    assert pending[0]['status'] == 'open' and not pending[0]['applied']
    decision['apply'] = False
    resolved = client.post(f'/admin/requests/{request_id}/resolve', headers=ADMIN_HEADERS, json=decision)
    assert resolved.status_code == 200 and not resolved.json()['applied']
    with services.session_factory() as session:
        row = session.get(CandidateRow, aid)
        assert (row.email_hash, row.phone_hash, row.login_email_hash, row.login_email_verified_at,
                row.login_binding_review_required) == before
    assert client.get('/portal/me').json()['candidate_id'] == aid


@pytest.mark.parametrize('door', ['/candidates', '/screening/candidates'])
def test_stale_match_refusal_uses_existing_ingest_transport(client, monkeypatch, door):
    from app.candidates.store import AssertedContactChangedError

    def refused(*args, **kwargs):
        raise AssertedContactChangedError()

    monkeypatch.setattr(client.app_services.candidates, 'ingest', refused)
    if door == '/candidates':
        headers = ADMIN_HEADERS
    else:
        org = client.app_services.ledger.create_organization('Agency')
        headers = {'X-Org-Key': client.app_services.ledger.issue_api_key(org.id)}
    result = client.post(door, headers=headers, json={'resume_text': 'Synthetic resume\nSKILLS\nPython\n'})
    assert result.status_code == 422 and result.json()['detail'] == 'candidate_contact_changed'
