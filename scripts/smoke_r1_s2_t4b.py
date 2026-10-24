"""Asserted-contact upload/change refusal HTTP/restart journey on scratch SQL.

Capture provider proves mechanics only; --postgres uses an owned fresh schema.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, select, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.core.db import make_session_factory

ROOT = Path(__file__).resolve().parents[1]
ADMIN = 'synthetic-asserted-contact-admin'


def main():
    checks = Smoke('asserted contact HTTP/restart')
    scratch = Path(tempfile.mkdtemp(prefix='r1-asserted-contact-'))
    print(f'Synthetic artifacts: {scratch}')
    capture = scratch / 'mail.jsonl'
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith('DEE_')}
        env.update({
            'DEE_CONFIG_FILE': str(scratch / 'no-config.yaml'),
            'DEE_CANDIDATES_DB_URL': url, 'DEE_ENV': 'local', 'DEE_API_AUTH_KEY': ADMIN,
            'DEE_OPENROUTER_API_KEY': '', 'DEE_GITHUB_TOKEN': '',
            'DEE_GITHUB_API_BASE': 'http://127.0.0.1:9',
            'DEE_EMAIL_PROVIDER': 'capture', 'DEE_EMAIL_CAPTURE_PATH': str(capture),
            'DEE_VECTORSTORE_BACKEND': 'memory', 'DEE_LOGIN_OTP_DEBUG_ECHO': 'false',
            'DEE_LOGIN_OTP_STATIC_CODE': '', 'DEE_LOGIN_OTP_COOLDOWN_SECONDS': '0',
            'DEE_SESSION_COOKIE_SECURE': 'false', 'DEE_SESSION_COOKIE_SAMESITE': 'lax',
            'DEE_FLYWHEEL_PATH': str(scratch / 'flywheel.jsonl'),
            'PYTHONPATH': str(ROOT / 'src'), 'NO_PROXY': '127.0.0.1,localhost',
            'PGOPTIONS': pg_options,
        })
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'

        @contextmanager
        def server():
            with (scratch / 'server.log').open('a', encoding='utf-8') as log:
                proc = subprocess.Popen(uvicorn_argv(port), env=env, cwd=scratch,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                try:
                    with client(base, headers={'X-API-Key': ADMIN}) as http:
                        assert wait_healthy(http), 'scratch app failed to start'
                        yield http
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()

        def login(http, email):
            require(http.post('/auth/candidate/login', json={'email': email}), 202)
            body = json.loads(capture.read_text(encoding='utf-8').splitlines()[-1])['body']
            code = re.search(r'\b(\d{6})\b', body).group(1)
            return require(http.post('/auth/candidate/verify', json={'email': email, 'code': code}))['csrf_token']

        def upload(http, document, *, headers=None, door='/candidates', evaluate=False):
            return require(http.post(door, headers=headers,
                json={'resume_text': document, 'evaluate': evaluate}))

        engine = create_engine(url, hide_parameters=True,
                               connect_args={'options': pg_options} if pg_options else {})
        factory = make_session_factory(engine)
        document_a = 'Synthetic Alice\nEmail: alice@example.in\nSKILLS\nPython\n'
        document_b = 'Synthetic Bob\nEmail: bob@example.in\nPhone: 9876543210\nSKILLS\nJava\n'
        try:
            with client(base) as alice, client(base) as bob:
                with server() as admin:
                    with engine.connect() as connection:
                        checks.check('real app migrates fresh scratch schema',
                            connection.scalar(text('SELECT version_num FROM alembic_version')) == '0030_screening_ingest_facts')
                    aid, bid = upload(admin, document_a)['candidate_id'], upload(admin, document_b)['candidate_id']
                    csrf = login(alice, 'alice@example.in')
                    login(bob, 'bob@example.in')
                    key = require(admin.post(f'/candidates/{aid}/auth-key'))['access_key']
                    with factory() as session:
                        row = session.get(CandidateRow, aid)
                        proof, proved_at = row.login_email_hash, row.login_email_verified_at
                    added = upload(admin, document_a + 'Phone: 9876543210\n')
                    with factory() as session:
                        row = session.get(CandidateRow, aid)
                        saved = session.scalar(select(ExtractionRow).where(ExtractionRow.resume_id == added['resume_id']))
                        checks.check('upload keeps proved contact hints and records document claim',
                            added['candidate_id'] == aid and row.phone_hash is None
                            and saved.profile['contact']['phone_hash'] is not None)
                    phone_only = upload(admin, 'Synthetic shared phone\nPhone: 9876543210\nSKILLS\nGo\n')
                    checks.check('phone-only upload cannot choose a proved subject', phone_only['candidate_id'] not in {aid, bid})
                    checks.check('candidate session cannot use operator upload door', alice.post('/candidates', json={'resume_text': document_a}).status_code == 401)
                    orgs = [require(admin.post('/ledger/orgs', json={'name': name})) for name in ('Synthetic agency A', 'Synthetic agency B')]
                    headers = [{'X-Org-Key': org['api_key']} for org in orgs]
                    uploads = [upload(admin, document_a, headers=h, door='/screening/candidates', evaluate=True) for h in headers]
                    checks.check('two org uploads dedup person and preserve separate ownership',
                        all(result['candidate_id'] == aid for result in uploads)
                        and uploads[0]['resume_id'] != uploads[1]['resume_id'])
                    with factory() as session:
                        checks.check('resume org IDs match authenticated upload owners',
                            [session.get(ResumeRow, result['resume_id']).org_id for result in uploads] == [org['org']['id'] for org in orgs])
                    for index, result in enumerate(uploads):
                        with client(base, headers=headers[index]) as org_http:
                            require(org_http.get(f"/screening/reports/{result['report']['id']}"))
                            require(org_http.get(f"/screening/reports/{uploads[1-index]['report']['id']}"), 404)
                    checks.check('foreign org reports remain undisclosed', True)
                    repeat = upload(admin, document_a, headers=headers[1], door='/screening/candidates')
                    checks.check('same org duplicate retry reuses its own resume', repeat['resume_id'] == uploads[1]['resume_id'])
                    for field, value in [('email', 'bob@example.in'), ('phone', '+91 9876543210')]:
                        request = require(alice.post('/portal/corrections', headers={'X-CSRF-Token': csrf},
                            json={'field': field, 'requested_value': value, 'candidate_id': bid}))
                        decision = {'status': 'resolved', 'resolution': 'Reviewed: change/merge unsupported.', 'apply': True}
                        refusal = require(admin.post(f"/admin/requests/{request['id']}/resolve", json=decision), 422)
                        assert 'unsupported' in refusal['detail']
                        assert next(r for r in require(alice.get('/portal/requests')) if r['id'] == request['id'])['status'] == 'open'
                        decision['apply'] = False
                        resolved = require(admin.post(f"/admin/requests/{request['id']}/resolve", json=decision))
                        checks.check(field + ' change refuses apply and records non-applied review', not resolved['applied'])
                    aview, bview = require(alice.get('/portal/me')), require(bob.get('/portal/me'))
                    checks.check('proved principal portals stay disjoint with no assurance uplift',
                        aview['candidate_id'] == aid and bview['candidate_id'] == bid
                        and aview['identity']['level'] == bview['identity']['level'] == 0
                        and {r['id'] for r in aview['resumes']}.isdisjoint({r['id'] for r in bview['resumes']}))
                    # Seed anomalies exclusively in this owned synthetic store.
                    with factory.begin() as session:
                        session.get(CandidateRow, aid).email_hash = session.get(CandidateRow, bid).login_email_hash
                    shadow = upload(admin, document_b + 'Different document content\n')
                    checks.check('duplicated/conflicting email hints never select an existing subject', shadow['candidate_id'] not in {aid, bid})
                    csrf = login(alice, 'alice@example.in')
                    login(bob, 'bob@example.in')
                    checks.check('both original mailbox proofs still resolve their pinned subjects',
                        require(alice.get('/portal/me'))['candidate_id'] == aid and require(bob.get('/portal/me'))['candidate_id'] == bid)
                with server():
                    checks.check('restart preserves both cookies and candidate key ownership',
                        require(alice.get('/portal/me'))['candidate_id'] == aid
                        and require(bob.get('/portal/me'))['candidate_id'] == bid)
                    with client(base, headers={'X-Candidate-Key': key}) as credential:
                        assert require(credential.get('/portal/me'))['candidate_id'] == aid
                    with factory() as session:
                        row = session.get(CandidateRow, aid)
                        checks.check('restart keeps proof timestamp and contact freeze',
                            row.login_email_hash == proof and row.login_email_verified_at == proved_at and row.phone_hash is None)
                    require(alice.delete('/portal/me', headers={'X-CSRF-Token': csrf}))
                    checks.check('erasure invalidates old cookie and keeps survivor subject',
                        alice.get('/portal/me').status_code == 401 and require(bob.get('/portal/me'))['candidate_id'] == bid)
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == '__main__':
    raise SystemExit(main())
