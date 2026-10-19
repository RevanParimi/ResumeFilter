"""Verified mailbox HTTP/cookie/restart journey on disposable migrated stores.

CaptureEmail proves local mechanics only. --postgres requires DEE_TEST_DB_URL;
the shared harness creates and drops only a fresh owned schema.
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
from app.candidates.models import CandidateRow
from app.core.db import make_session_factory

ROOT = Path(__file__).resolve().parents[1]
ADMIN = 'synthetic-mailbox-binding-admin'


def main():
    checks = Smoke('verified mailbox HTTP/restart')
    scratch = Path(tempfile.mkdtemp(prefix='r1-mailbox-binding-'))
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

        def issue(http, email):
            result = require(http.post('/auth/candidate/login', json={'email': email}), 202)
            assert result.get('debug_code') is None
            body = json.loads(capture.read_text(encoding='utf-8').splitlines()[-1])['body']
            return re.search(r'\b(\d{6})\b', body).group(1)

        def verify(http, email, code, status=200):
            response = http.post('/auth/candidate/verify', json={'email': email, 'code': code})
            body = require(response, status)
            if status != 200:
                assert 'set-cookie' not in response.headers
            return body

        engine = create_engine(url, hide_parameters=True,
                               connect_args={'options': pg_options} if pg_options else {})
        factory = make_session_factory(engine)
        try:
            with client(base) as alice, client(base) as bob:
                with server() as admin:
                    with engine.connect() as connection:
                        checks.check('real app migrated scratch schema to 0029',
                            connection.scalar(text('SELECT version_num FROM alembic_version')) == '0029_candidate_login_binding')
                    aid = require(admin.post('/candidates', json={'resume_text':
                        'Synthetic Alice\nEmail: alice@example.in\nPhone: 9876543210\nSKILLS\nPython\n'}))['candidate_id']
                    acode = issue(alice, 'alice@example.in')
                    csrf = verify(alice, 'alice@example.in', acode)['csrf_token']
                    checks.check('mailbox proof claims uploaded subject', require(alice.get('/portal/me'))['candidate_id'] == aid)
                    bid = require(admin.post('/candidates', json={'resume_text':
                        'Synthetic Bob\nEmail: bob@example.in\nPhone: 9876543210\nSKILLS\nJava\n'}))['candidate_id']
                    verify(bob, 'bob@example.in', issue(bob, 'bob@example.in'))
                    checks.check('F01 shared phone keeps two proved subjects', bid != aid and require(bob.get('/portal/me'))['candidate_id'] == bid)
                    aview, bview = require(alice.get('/portal/me')), require(bob.get('/portal/me'))
                    checks.check('portal resumes remain separately owned',
                        {r['id'] for r in aview['resumes']}.isdisjoint({r['id'] for r in bview['resumes']}))
                    checks.check('login does not grant identity assurance or serialize proof fields',
                        aview['identity']['level'] == 0 and 'login_email_hash' not in json.dumps(aview))
                    with factory.begin() as session:
                        row = session.get(CandidateRow, aid)
                        original_hash, first_proof = row.login_email_hash, row.login_email_verified_at
                        # Model legacy hint edits only in the owned synthetic store.
                        row.email_hash = 'unused-synthetic-hint'
                        session.add(CandidateRow(id='shadow-hint', email_hash=original_hash))
                    csrf = verify(alice, 'alice@example.in', issue(alice, 'alice@example.in'))['csrf_token']
                    checks.check('original mailbox ignores changed and duplicated hints', require(alice.get('/portal/me'))['candidate_id'] == aid)
                    with factory() as session:
                        checks.check('repeat proof preserves original binding timestamp', session.get(CandidateRow, aid).login_email_verified_at == first_proof)
                    # Obtain the actual salt-derived hint from a harmless new upload.
                    hint_id = require(admin.post('/candidates', json={'resume_text':
                        'Synthetic hint\nEmail: alternate@example.in\nSKILLS\nPython\n'}))['candidate_id']
                    with factory.begin() as session:
                        hint = session.get(CandidateRow, hint_id)
                        session.get(CandidateRow, aid).email_hash = hint.email_hash
                        session.delete(hint)
                    verify(alice, 'alternate@example.in', issue(alice, 'alternate@example.in'), 409)
                    checks.check('other proved mailbox cannot replace bound subject; cookie stays valid', require(alice.get('/portal/me'))['candidate_id'] == aid)
                    ambiguous_id = require(admin.post('/candidates', json={'resume_text':
                        'Synthetic ambiguity\nEmail: ambiguous@example.in\nSKILLS\nPython\n'}))['candidate_id']
                    with factory.begin() as session:
                        hint = session.get(CandidateRow, ambiguous_id)
                        session.add_all([CandidateRow(id=cid, email_hash=hint.email_hash)
                                         for cid in ('ambiguous-a', 'ambiguous-b')])
                        session.delete(hint)
                    verify(alice, 'ambiguous@example.in', issue(alice, 'ambiguous@example.in'), 409)
                    checks.check('ambiguous initial claim refuses without setting cookie', require(alice.get('/portal/me'))['candidate_id'] == aid)
                    verify(alice, 'alice@example.in', acode, 400)
                    checks.check('spent code cannot rebind or establish a session', True)
                with server() as admin:
                    checks.check('restart preserves both cookie subjects', require(alice.get('/portal/me'))['candidate_id'] == aid
                        and require(bob.get('/portal/me'))['candidate_id'] == bid)
                    csrf = verify(alice, 'alice@example.in', issue(alice, 'alice@example.in'))['csrf_token']
                    checks.check('restart resolves durable proof before shadow hint', require(alice.get('/portal/me'))['candidate_id'] == aid)
                    with factory.begin() as session:
                        session.get(CandidateRow, aid).email_hash = session.get(CandidateRow, bid).login_email_hash
                    old_a, pending_b = issue(alice, 'alice@example.in'), issue(bob, 'bob@example.in')
                    require(alice.delete('/portal/me', headers={'X-CSRF-Token': csrf}))
                    verify(alice, 'alice@example.in', old_a, 400)
                    checks.check('portal erasure invalidates cookie and queued proof', alice.get('/portal/me').status_code == 401)
                    with factory() as session:
                        checks.check('erasure removes binding subject and preserves survivor',
                            session.get(CandidateRow, aid) is None and session.get(CandidateRow, bid).login_email_hash is not None)
                    verify(bob, 'bob@example.in', pending_b)
                    checks.check('stale foreign hint cannot cancel survivor login proof', require(bob.get('/portal/me'))['candidate_id'] == bid)
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == '__main__':
    raise SystemExit(main())
