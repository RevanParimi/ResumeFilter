"""Contact challenge HTTP/restart on migrated disposable SQLite/PostgreSQL.

Synthetic local debug echo and captured email exercise mechanics, not live delivery.
--postgres requires DEE_TEST_DB_URL; only a fresh owned schema is touched.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, select, update

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.verification.models import VerificationChallengeRow
from app.verification.store import VerificationStore

ROOT = Path(__file__).resolve().parents[1]
ADMIN = 'synthetic-contact-race-admin'


def main():
    checks = Smoke('contact challenge HTTP/restart')
    scratch = Path(tempfile.mkdtemp(prefix='r1-contact-challenge-'))
    print(f'Synthetic artifacts: {scratch}')
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith('DEE_')}
        env.update({
            'DEE_CONFIG_FILE': str(scratch / 'no-config.yaml'),
            'DEE_CANDIDATES_DB_URL': url, 'DEE_ENV': 'local', 'DEE_API_AUTH_KEY': ADMIN,
            'DEE_OPENROUTER_API_KEY': '', 'DEE_GITHUB_TOKEN': '',
            'DEE_GITHUB_API_BASE': 'http://127.0.0.1:9', 'DEE_EMAIL_PROVIDER': 'capture',
            'DEE_EMAIL_CAPTURE_PATH': str(scratch / 'mail.jsonl'),
            'DEE_VECTORSTORE_BACKEND': 'memory', 'DEE_LOGIN_OTP_DEBUG_ECHO': 'false',
            'DEE_LOGIN_OTP_STATIC_CODE': '', 'DEE_VERIF_OTP_DEBUG_ECHO': 'true',
            'DEE_FLYWHEEL_PATH': str(scratch / 'flywheel.jsonl'),
            'PYTHONPATH': str(ROOT / 'src'), 'NO_PROXY': '127.0.0.1,localhost',
            'PGOPTIONS': pg_options,
        })
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]

        @contextmanager
        def server():
            with (scratch / 'server.log').open('a', encoding='utf-8') as log:
                proc = subprocess.Popen(uvicorn_argv(port), env=env, cwd=scratch,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                try:
                    with client(f'http://127.0.0.1:{port}', headers={'X-API-Key': ADMIN}) as http:
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

        engine = create_engine(url, hide_parameters=True,
                               connect_args={'options': pg_options} if pg_options else {})
        try:
            factory = make_session_factory(engine)
            ledger = LedgerStore(factory)
            store = VerificationStore(factory, ledger=ledger)

            def age(vid, **values):
                # Only the synthetic owned store: model expiry/cooldown without waiting.
                with factory.begin() as session:
                    session.execute(update(VerificationChallengeRow).where(
                        VerificationChallengeRow.verification_id == vid).values(**values))

            def completion_count(cid, vid):
                return len([a for a in ledger.audit_for_candidate(cid)
                            if a.action == 'verification.complete' and a.entity_id == vid])

            with server() as http:
                checks.check('real migrated app starts', True)
                candidates = []
                for tag in ('a', 'b'):
                    email = f'contact-{tag}@example.com'
                    cid = require(http.post('/candidates', json={'resume_text':
                        f'Synthetic {tag}\nEmail: {email}\nSKILLS\nPython\n'}))['candidate_id']
                    key = require(http.post(f'/candidates/{cid}/auth-key'))['access_key']
                    candidates.append((cid, email, {'X-Candidate-Key': key}))
                cid, email, headers = candidates[0]
                other, other_email, other_headers = candidates[1]

                def start(email=email, headers=headers):
                    return require(http.post('/portal/verifications', headers=headers,
                        json={'method': 'otp_email', 'destination': email}))

                def confirm(body, code=None, headers=headers, status=200):
                    return require(http.post(f"/portal/verifications/{body['verification']['id']}/confirm",
                        headers=headers, json={'code': body['debug_code'] if code is None else code}), status)

                require(http.post('/portal/verifications', headers=headers,
                    json={'method': 'otp_email', 'destination': 'intruder@example.com'}), 400)
                checks.check('wrong destination is refused', True)
                body = start()
                vid, code = body['verification']['id'], body['debug_code']
                checks.check('local synthetic echo agrees with captured email', bool(code) and
                    any(code in json.loads(line)['body'] for line in (scratch / 'mail.jsonl').read_text().splitlines()))
                confirm(body, headers=other_headers, status=404)
                confirm(body, code='0' * len(code) if code != '0' * len(code) else '1' * len(code), status=400)
                with factory() as session:
                    challenge = session.scalar(select(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == vid))
                    checks.check('foreign attempt does not charge; wrong owner attempt charges once', challenge.attempts == 1)
                saved = confirm(body)
                checks.check('correct code verifies advisory contact control', saved['status'] == 'verified'
                    and require(http.get('/portal/verifications', headers=headers))['assurance']['advisory'])
                confirm(body, status=400)
                checks.check('replay preserves timestamps and one completion audit',
                    store.get_verification(vid).model_dump(mode='json') == saved and completion_count(cid, vid) == 1)
                with factory() as session:
                    checks.check('consumed secret is deleted', session.scalar(select(VerificationChallengeRow).where(
                        VerificationChallengeRow.verification_id == vid)) is None)
                replacement_old = start()
                require(http.post('/portal/verifications', headers=headers,
                    json={'method': 'otp_email', 'destination': email}), 429)
                checks.check('new verification cannot bypass candidate/channel cooldown', True)
                age(replacement_old['verification']['id'], last_sent_at=datetime.now(timezone.utc) - timedelta(minutes=2))
                replacement = start()
                confirm(replacement_old, status=400)
                confirm(replacement)
                checks.check('superseded code refused; replacement succeeds', True)
                exhausted = start()
                age(exhausted['verification']['id'], attempts=store._settings.verif_otp_max_attempts)
                confirm(exhausted, status=400)
                checks.check('stored exhausted budget fails even with correct code',
                    store.get_verification(exhausted['verification']['id']).status.value == 'failed'
                    and completion_count(cid, exhausted['verification']['id']) == 1)
                expired = start()
                age(expired['verification']['id'], expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                confirm(expired, status=400)
                checks.check('expired code cannot verify', store.get_verification(expired['verification']['id']).status.value == 'pending')
                active = start(other_email, other_headers)
                checks.check('other candidate has independent live challenge', active['verification']['status'] == 'pending')
                orgs = [require(http.post('/ledger/orgs', json={'name': f'Synthetic contact {tag}'})) for tag in ('a', 'b')]
                path = f'/verification/candidates/{cid}/assurance'
                require(http.get(path, headers={'X-Org-Key': orgs[0]['api_key']}), 403)
                require(http.post(f'/ledger/candidates/{cid}/consent', json={
                    'purpose': 'verification_read', 'org_id': orgs[0]['org']['id']}))
                permitted = require(http.get(path, headers={'X-Org-Key': orgs[0]['api_key']}))
                require(http.get(path, headers={'X-Org-Key': orgs[1]['api_key']}), 403)
                checks.check('advisory assurance remains consent and org scoped', permitted['advisory'] and permitted['level'] == 2)
            with server() as http:
                checks.check('restarted migrated app starts', True)
                confirm(body, status=400)
                checks.check('restart preserves completed outcome and one audit',
                    store.get_verification(vid).model_dump(mode='json') == saved and completion_count(cid, vid) == 1)
                confirm(exhausted, status=400)
                confirm(expired, status=400)
                confirm(replacement_old, status=400)
                checks.check('restart preserves exhausted expired and superseded refusal', True)
                confirm(active, headers=other_headers)
                checks.check('other candidate live challenge survives restart', True)
                # Reuse existing admin erasure route only on synthetic data.
                require(http.delete(f'/candidates/{cid}'))
                require(http.get(path, headers={'X-Org-Key': orgs[0]['api_key']}), 404)
                checks.check('erasure removes contact outcomes and challenges', store.get_verification(vid) is None)
                checks.check('erasure preserves other candidate outcome', store.get_verification(active['verification']['id']).status.value == 'verified')
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == '__main__':
    raise SystemExit(main())
