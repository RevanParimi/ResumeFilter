"""Integrated R1-S2 authorization/identity journey on migrated scratch SQL.

Default SQLite; --postgres requires disposable DEE_TEST_DB_URL and owns one
fresh schema. Login uses capture mail; contact uses local echo/NullNotifier.
Exports/training are library operations because there is no HTTP endpoint.
No real mailbox delivery, browser or model-quality evidence is claimed.
"""

from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, select, text, update

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.candidates.models import CandidateRow
from app.core.db import make_session_factory
from app.features import default_view, get_feature_registry
from app.features.export import (export_view_csv, export_view_parquet,
                                 export_training_csv, export_training_parquet,
                                 ParquetUnavailable)
from app.features.store import FeatureStore
from app.features.training import build_training_set
from app.ledger.models import ConsentGrantRow
from app.ledger.store import LedgerStore
from app.verification.models import VerificationChallengeRow, VerificationRow

ROOT = Path(__file__).resolve().parents[1]
ADMIN = 'synthetic-integrated-authorization-admin'
RANKING = {'terms': [{'feature': name, 'weight': 1} for name in
                    ('candidate.num_skills', 'reputation.score')]}


def main():
    checks = Smoke('R1-S2 integrated authorization/identity HTTP/library/restart')
    scratch = Path(tempfile.mkdtemp(prefix='r1-s2-q-'))
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
            'DEE_VERIF_OTP_DEBUG_ECHO': 'true', 'DEE_SESSION_COOKIE_SECURE': 'false',
            'DEE_SESSION_COOKIE_SAMESITE': 'lax',
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
            require(http.post('/auth/candidate/login', json={'email': email}), 202)
            body = json.loads(capture.read_text(encoding='utf-8').splitlines()[-1])['body']
            return re.search(r'\b(\d{6})\b', body).group(1)

        def verify(http, email, code, status=200):
            return require(http.post('/auth/candidate/verify',
                                    json={'email': email, 'code': code}), status)

        def search(http, cut, gated=False):
            body = {'ranking': RANKING, 'as_of': cut.isoformat()}
            if gated:
                body['filters'] = [{'feature': 'reputation.score', 'op': 'exists'}]
            return require(http.post('/talent/search', json=body))

        engine = create_engine(url, hide_parameters=True,
                               connect_args={'options': pg_options} if pg_options else {})
        factory = make_session_factory(engine)
        features, ledger = FeatureStore(factory), LedgerStore(factory)
        registry = get_feature_registry()
        view = default_view(registry)

        def exports(raw, cached, tag, org_id=None):
            result = []
            for training in (False, True):
                prefix = f'{tag}-{"training" if training else "features"}'
                inputs = cached if training else raw
                kwargs = dict(view=view, registry=registry, ledger_store=ledger, org_id=org_id)
                path = scratch / f'{prefix}.csv'
                (export_training_csv if training else export_view_csv)(iter(inputs), path=str(path), **kwargs)
                with path.open(newline='', encoding='utf-8') as handle:
                    rows = {r['candidate_id']: r for r in csv.DictReader(handle)}
                result.append(rows)
                path = scratch / f'{prefix}.parquet'
                try:
                    (export_training_parquet if training else export_view_parquet)(iter(inputs), path=str(path), **kwargs)
                except ParquetUnavailable:
                    checks.check(prefix + ' optional Parquet refuses without artifact', not path.exists())
                else:
                    import pyarrow.parquet as pq
                    arrow = {r['candidate_id']: r for r in pq.read_table(path).to_pylist()}
                    checks.check(prefix + ' Parquet agrees on subjects, gated values and labels',
                        arrow.keys() == rows.keys() and all(
                            arrow[cid]['reputation.score'] == (None if row['reputation.score'] == ''
                                                             else float(row['reputation.score']))
                            and (not training or
                                 arrow[cid]['label_withheld'] == (row['label_withheld'] == 'True')
                                 and arrow[cid]['label_hired'] == (None if row['label_hired'] == ''
                                                                 else row['label_hired'] == 'True'))
                            for cid, row in rows.items()))
            return result

        try:
            with client(base) as alice, client(base) as bob:
                with server() as admin:
                    with engine.connect() as conn:
                        checks.check('actual app migrates scratch to 0030',
                            conn.scalar(text('SELECT version_num FROM alembic_version')) == '0030_screening_ingest_facts')
                    orgs = [require(admin.post('/ledger/orgs', json={'name': f'Synthetic Q {tag}'}))
                            for tag in ('A', 'B')]
                    org_headers = [{'X-Org-Key': org['api_key']} for org in orgs]
                    ids, csrf, keys, grants, jobs = [], [], [], [], []
                    for index, (tag, actor) in enumerate(zip(('alice', 'bob'), (alice, bob))):
                        email = f'{tag}@example.in'
                        document = f'Synthetic {tag}\nEmail: {email}\nPhone: 9876543210\nSKILLS\nPython\n'
                        cid = require(admin.post('/candidates', json={'resume_text': document}))['candidate_id']
                        ids.append(cid)
                        csrf.append(verify(actor, email, issue(actor, email))['csrf_token'])
                        keys.append(require(admin.post(f'/candidates/{cid}/auth-key'))['access_key'])
                        org_id = orgs[index]['org']['id']
                        require(admin.post(f'/ledger/candidates/{cid}/consent', json={'purpose': 'ledger_write', 'org_id': org_id}))
                        grants.append(require(actor.post('/portal/consents', headers={'X-CSRF-Token': csrf[index]},
                            json={'purpose': 'ledger_read', 'org_id': org_id})))
                        for days in (-1, 1):
                            require(admin.post('/ledger/records', headers=org_headers[index], json={
                                'candidate_id': cid, 'stage': 'hm', 'outcome': 'hired',
                                'interviewed_at': (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()}))
                        jobs.append(require(admin.post('/jobs', headers=org_headers[index],
                            json={'title': f'Engineer {tag}', 'must_have_skills': ['python']})))
                    checks.check('shared asserted phone preserves two mailbox-owned principals', ids[0] != ids[1]
                        and require(alice.get('/portal/me'))['candidate_id'] == ids[0]
                        and require(bob.get('/portal/me'))['candidate_id'] == ids[1])
                    require(alice.post('/portal/consents/' + grants[0]['id'] + '/revoke'), 403)
                    require(bob.post('/portal/consents/' + grants[0]['id'] + '/revoke',
                                     headers={'X-CSRF-Token': csrf[1]}), 404)
                    checks.check('missing CSRF and foreign candidate revocation refuse', True)
                    with client(base, headers=org_headers[1]) as foreign:
                        require(foreign.post('/talent/search', json={'ranking': RANKING}), 401)
                        require(foreign.post(f"/jobs/{jobs[0]['id']}/match", json={}), 404)
                    checks.check('org cannot use admin search or foreign job', True)

                    batch = require(admin.post('/features/materialize', json={}))
                    cut = datetime.fromisoformat(batch['as_of'])
                    raw = features.vectors_for_view(view.name, view.version, as_of=cut)
                    cached = build_training_set(raw, ledger_store=ledger, registry=registry)
                    checks.check('active historical serving and post-cut labels available', batch['materialized'] == 2
                        and search(admin, cut, True)['filtered_size'] == 2
                        and all(ex.label.hired and ex.label.lag_days > 0 for ex in cached))
                    frows, trows = exports(raw, cached, 'active')
                    checks.check('active feature and training CSV contain gated data', all(
                        frows[cid]['ledger.interview_record_count'] == '1' and trows[cid]['label_hired'] == 'True'
                        for cid in ids))
                    frows, trows = exports(raw, cached, 'foreign-scope', orgs[0]['org']['id'])
                    scoped = build_training_set(raw, ledger_store=ledger, registry=registry, org_id=orgs[0]['org']['id'])
                    checks.check('org scope denies foreign cached features and labels', frows[ids[1]]['reputation.score'] == ''
                        and trows[ids[1]]['label_withheld'] == 'True'
                        and next(ex for ex in scoped if ex.vector.candidate_id == ids[1]).label.withheld)

                    contact = require(alice.post('/portal/verifications', headers={'X-CSRF-Token': csrf[0]},
                        json={'method': 'otp_email', 'destination': 'alice@example.in'}))
                    vid = contact['verification']['id']
                    require(bob.post(f'/portal/verifications/{vid}/confirm', headers={'X-CSRF-Token': csrf[1]},
                                     json={'code': contact['debug_code']}), 404)
                    wrong = '000000' if contact['debug_code'] != '000000' else '111111'
                    require(alice.post(f'/portal/verifications/{vid}/confirm', headers={'X-CSRF-Token': csrf[0]},
                                       json={'code': wrong}), 400)
                    with factory() as session:
                        checks.check('only owner wrong contact attempt charges budget', session.scalar(select(
                            VerificationChallengeRow).where(VerificationChallengeRow.verification_id == vid)).attempts == 1)
                    require(alice.post(f'/portal/verifications/{vid}/confirm', headers={'X-CSRF-Token': csrf[0]},
                                       json={'code': contact['debug_code']}))
                    require(alice.post(f'/portal/verifications/{vid}/confirm', headers={'X-CSRF-Token': csrf[0]},
                                       json={'code': contact['debug_code']}), 400)
                    checks.check('contact success is single-use and does not move login ownership',
                        require(alice.get('/portal/me'))['candidate_id'] == ids[0]
                        and len([a for a in ledger.audit_for_candidate(ids[0])
                                 if a.action == 'verification.complete' and a.entity_id == vid]) == 1)

                    require(alice.post('/portal/consents/' + grants[0]['id'] + '/revoke',
                                       headers={'X-CSRF-Token': csrf[0]}))
                    denied = {r['candidate_id']: r for r in search(admin, cut)['ranked']}
                    frows, trows = exports(raw, cached, 'revoked')
                    joined = {ex.vector.candidate_id: ex for ex in build_training_set(raw, ledger_store=ledger, registry=registry)}
                    checks.check('same revoke masks serving/export/training at old cut', denied[ids[0]]['coverage'] == 0.5
                        and frows[ids[0]]['reputation.score'] == '' and trows[ids[0]]['label_withheld'] == 'True'
                        and joined[ids[0]].label.withheld and joined[ids[0]].vector.values['reputation.score'] is None)
                    checks.check('unrevoked candidate stays authorized across all consumers', denied[ids[1]]['coverage'] == 1
                        and frows[ids[1]]['reputation.score'] != '' and trows[ids[1]]['label_hired'] == 'True'
                        and joined[ids[1]].label.hired)
                    with engine.begin() as conn:
                        conn.execute(update(ConsentGrantRow).where(ConsentGrantRow.id == grants[1]['id']).values(expires_at=cut))
                    frows, trows = exports(raw, cached, 'expired')
                    checks.check('expiry masks serving/export/training without removing first-party data',
                        search(admin, cut, True)['filtered_size'] == 0
                        and all(r['coverage'] == 0.5 for r in search(admin, cut)['ranked'])
                        and all(r['reputation.score'] == '' and r['candidate.num_skills'] != '' for r in frows.values())
                        and all(r['label_withheld'] == 'True' for r in trows.values()))
                    for job, headers in zip(jobs, org_headers):
                        match = require(admin.post(f"/jobs/{job['id']}/match", headers=headers, json={'as_of': cut.isoformat()}))
                        checks.check('first-party advisory matching survives denial', match['advisory'] and match['pool_size'] == 2
                                     and all(r['score'] == 1 for r in match['ranked']))
                    checks.check('authorization reads preserve cached history', raw == features.vectors_for_view(view.name, view.version, as_of=cut)
                                 and all(ex.label.hired for ex in cached))
                    queued_a = issue(alice, 'alice@example.in')
                    queued_b = issue(bob, 'bob@example.in')

                with server() as admin:
                    checks.check('restart preserves subjects and current denial', require(alice.get('/portal/me'))['candidate_id'] == ids[0]
                        and require(bob.get('/portal/me'))['candidate_id'] == ids[1] and search(admin, cut, True)['filtered_size'] == 0)
                    require(alice.delete('/portal/me', headers={'X-CSRF-Token': csrf[0]}))
                    verify(alice, 'alice@example.in', queued_a, 400)
                    checks.check('erasure invalidates queued exact proof and old cookie', alice.get('/portal/me').status_code == 401)
                    with client(base, headers={'X-Candidate-Key': keys[0]}) as stale:
                        require(stale.get('/portal/me'), 401)
                    csrf[1] = verify(bob, 'bob@example.in', queued_b)['csrf_token']
                    verify(bob, 'bob@example.in', queued_b, 400)
                    checks.check('other queued proof survives erasure and is single-use', require(bob.get('/portal/me'))['candidate_id'] == ids[1])

                with server() as admin:
                    checks.check('restart excludes erased candidate from historical serving',
                        [r['candidate_id'] for r in search(admin, cut)['ranked']] == ids[1:])
                    frows, trows = exports(raw, cached, 'erased-restart')
                    checks.check('cached exports and joins omit erased candidate after restart', set(frows) == set(trows) == {ids[1]}
                        and [ex.vector.candidate_id for ex in build_training_set(raw, ledger_store=ledger, registry=registry, audit=False)] == ids[1:])
                    retry = require(admin.post('/features/materialize', json={'candidate_ids': ids, 'as_of': cut.isoformat()}))
                    checks.check('historical retry cannot recreate erased snapshot', retry['materialized'] == 1 and retry['skipped'] == 1)
                    with factory() as session:
                        checks.check('erased proof/contact rows stay absent; survivor proof stays bound',
                            session.get(CandidateRow, ids[0]) is None and session.get(VerificationRow, vid) is None
                            and session.get(CandidateRow, ids[1]).login_email_hash is not None)
                    with client(base, headers={'X-Candidate-Key': keys[1]}) as survivor:
                        checks.check('survivor candidate key remains usable', require(survivor.get('/portal/me'))['candidate_id'] == ids[1])
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == '__main__':
    raise SystemExit(main())
