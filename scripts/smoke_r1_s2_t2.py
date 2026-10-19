"""Migrated HTTP materialize/revoke plus direct export/training and restart.

No export/training HTTP route exists. Default scratch SQLite; --postgres uses
an explicitly configured disposable DEE_TEST_DB_URL and a fresh owned schema.
External providers are disabled; all candidates and artifacts are synthetic.
"""

from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, update

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.core.db import make_session_factory
from app.features import default_view, get_feature_registry
from app.features.export import (export_view_csv, export_view_parquet,
                                 export_training_csv, export_training_parquet, ParquetUnavailable)
from app.features.store import FeatureStore
from app.features.training import build_training_set
from app.ledger.models import ConsentGrantRow
from app.ledger.store import LedgerStore

ROOT = Path(__file__).resolve().parents[1]
ADMIN = 'synthetic-export-consent-admin'


def main():
    checks = Smoke('current consent export/training HTTP/restart')
    scratch = Path(tempfile.mkdtemp(prefix='r1-consent-export-'))
    print(f'Synthetic artifacts: {scratch}')
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith('DEE_')}
        env.update({
            'DEE_CONFIG_FILE': str(scratch / 'no-config.yaml'),
            'DEE_CANDIDATES_DB_URL': url, 'DEE_ENV': 'local', 'DEE_API_AUTH_KEY': ADMIN,
            'DEE_OPENROUTER_API_KEY': '', 'DEE_GITHUB_TOKEN': '',
            'DEE_GITHUB_API_BASE': 'http://127.0.0.1:9', 'DEE_EMAIL_PROVIDER': 'null',
            'DEE_VECTORSTORE_BACKEND': 'memory', 'DEE_LOGIN_OTP_DEBUG_ECHO': 'false',
            'DEE_LOGIN_OTP_STATIC_CODE': '', 'DEE_FLYWHEEL_PATH': str(scratch / 'flywheel.jsonl'),
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
            features, ledger = FeatureStore(factory), LedgerStore(factory)
            registry = get_feature_registry()
            view = default_view(registry)

            def exports(raw, examples, name, org_id=None):
                outputs = []
                for training in (False, True):
                    prefix = f'{name}-{"training" if training else "features"}'
                    inputs = examples if training else raw
                    csv_writer = export_training_csv if training else export_view_csv
                    parquet_writer = export_training_parquet if training else export_view_parquet
                    kwargs = dict(view=view, registry=registry, ledger_store=ledger, org_id=org_id)
                    path = scratch / f'{prefix}.csv'
                    csv_writer(iter(inputs), path=str(path), **kwargs)
                    with path.open(newline='', encoding='utf-8') as handle:
                        rows = {r['candidate_id']: r for r in csv.DictReader(handle)}
                    outputs.append(rows)
                    path = scratch / f'{prefix}.parquet'
                    try:
                        parquet_writer(iter(inputs), path=str(path), **kwargs)
                    except ParquetUnavailable:
                        checks.check(f'{prefix} optional format unavailable without artifact', not path.exists())
                    else:
                        import pyarrow.parquet as pq
                        arrow = {r['candidate_id']: r for r in pq.read_table(path).to_pylist()}
                        checks.check(f'{prefix} Parquet gated/null/label values agree with CSV',
                            all(arrow[cid]['reputation.score'] ==
                                (None if row['reputation.score'] == '' else float(row['reputation.score']))
                                and (not training or
                                     arrow[cid]['label_withheld'] == (row['label_withheld'] == 'True')
                                     and arrow[cid]['label_hired'] ==
                                         (None if row['label_hired'] == '' else row['label_hired'] == 'True'))
                                for cid, row in rows.items()))
                return outputs

            with server() as http:
                checks.check('real migrated app starts', True)
                orgs = [require(http.post('/ledger/orgs', json={'name': f'Synthetic {tag}'}))
                        for tag in ('A', 'B')]
                ids, grants = [], []
                for index, tag in enumerate(('A', 'B', 'C')):
                    org = orgs[index % 2]
                    cid = require(http.post('/candidates', json={'resume_text':
                        f'Candidate {tag}\nEmail: export-{tag.lower()}@example.com\nSKILLS\nPython\n'}))['candidate_id']
                    ids.append(cid)
                    require(http.post(f'/ledger/candidates/{cid}/consent', json={
                        'purpose': 'ledger_write', 'org_id': org['org']['id']}))
                    if tag != 'C':
                        grants.append(require(http.post(f'/ledger/candidates/{cid}/consent', json={
                            'purpose': 'ledger_read', 'org_id': org['org']['id']})))
                    headers = {'X-Org-Key': org['api_key']}
                    for offset in (-1, 1):
                        require(http.post('/ledger/records', headers=headers, json={
                            'candidate_id': cid, 'stage': 'hm', 'outcome': 'hired',
                            'interviewed_at': (datetime.now(timezone.utc) + timedelta(days=offset)).isoformat()}))
                    require(http.post('/ledger/coding-rounds', headers=headers, json={
                        'candidate_id': cid, 'platform': 'internal', 'score': 90, 'percentile': 90,
                        'taken_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}))
                batch = require(http.post('/features/materialize', json={}))
                cut = datetime.fromisoformat(batch['as_of'])
                raw = features.vectors_for_view(view.name, view.version, as_of=cut)
                cached = build_training_set(raw, ledger_store=ledger, registry=registry)
                by_id = {ex.vector.candidate_id: ex for ex in cached}
                checks.check('active labels use post-cut hired and coding', all(
                    by_id[cid].label.hired and by_id[cid].label.coding_best_percentile == 90
                    and by_id[cid].label.lag_days > 0 for cid in ids[:2]))
                checks.check('missing read grant withholds label', by_id[ids[2]].label.withheld)
                active_features, active_training = exports(raw, cached, 'active')
                checks.check('active CSV retains gated features and labels', all(
                    active_features[cid]['ledger.interview_record_count'] == '1'
                    and active_training[cid]['label_hired'] == 'True' for cid in ids[:2]))
                scoped = build_training_set(raw, ledger_store=ledger, registry=registry, org_id=orgs[0]['org']['id'])
                scoped_features, scoped_training = exports(raw, cached, 'scoped', orgs[0]['org']['id'])
                checks.check('other org cannot use candidate B features or cached labels',
                    scoped_features[ids[1]]['reputation.score'] == ''
                    and scoped_training[ids[1]]['label_withheld'] == 'True'
                    and next(ex for ex in scoped if ex.vector.candidate_id == ids[1]).label.withheld)
                require(http.post(f"/ledger/consent/{grants[0]['id']}/revoke"))
                expiry = cut + timedelta(microseconds=1)
                assert datetime.now(timezone.utc) > expiry
                with engine.begin() as conn:
                    conn.execute(update(ConsentGrantRow).where(ConsentGrantRow.id == grants[1]['id'])
                                 .values(expires_at=expiry))
                denied_features, denied_training = exports(raw, cached, 'denied')
                checks.check('cached gated CSV cells denied after revoke/expiry', all(
                    row['reputation.score'] == '' and row['candidate.num_skills'] == '1'
                    and row['as_of'] == cut.isoformat() for row in denied_features.values()))
                checks.check('every cached label value denied', all(
                    row['label_withheld'] == 'True' and row['label_observed'] == 'False'
                    and all(row['label_' + name] == '' for name in
                            ('hired', 'outcome', 'coding_best_percentile', 'event_at', 'lag_days'))
                    for row in denied_training.values()))
                fresh = build_training_set(raw, ledger_store=ledger, registry=registry, audit=False)
                checks.check('audit=False join cannot bypass current denial', all(ex.label.withheld for ex in fresh))
                checks.check('exports preserve historical snapshots and cached labels',
                    raw == features.vectors_for_view(view.name, view.version, as_of=cut)
                    and by_id[ids[0]].label.hired is True)
                require(http.post('/features/materialize', json={'as_of': cut.isoformat()}))
                remat = features.vectors_for_view(view.name, view.version, as_of=cut)
                checks.check('historical re-materialization retains historical decisions',
                    {mv.vector.candidate_id: mv.vector for mv in raw} ==
                    {mv.vector.candidate_id: mv.vector for mv in remat}
                    and all(mv.consent_state['allowed'] for mv in remat if mv.vector.candidate_id in ids[:2]))
                checks.check('re-materializing old cut cannot authorize training', all(
                    ex.label.withheld for ex in build_training_set(remat, ledger_store=ledger, registry=registry)))
            with server() as http:
                checks.check('restarted migrated app starts', True)
                loaded = features.vectors_for_view(view.name, view.version, as_of=cut)
                checks.check('restart preserves current training denial', all(
                    ex.label.withheld for ex in build_training_set(loaded, ledger_store=ledger, registry=registry)))
                rows, labels = exports(loaded, cached, 'restart')
                checks.check('restart export denies cached features and labels', all(
                    row['reputation.score'] == '' for row in rows.values())
                    and all(row['label_withheld'] == 'True' for row in labels.values()))
                require(http.post(f'/ledger/candidates/{ids[2]}/consent', json={'purpose': 'ledger_read'}))
                historical = build_training_set(loaded, ledger_store=ledger, registry=registry)
                checks.check('new grant cannot fill historically withheld label',
                    next(ex for ex in historical if ex.vector.candidate_id == ids[2]).label.withheld)
                latest = require(http.post('/features/materialize', json={'candidate_ids': ids[2:]}))
                newer = features.vectors_for_view(view.name, view.version, as_of=datetime.fromisoformat(latest['as_of']))
                checks.check('explicit fresh materialization records new permission', len(newer) == 1
                             and newer[0].consent_state['allowed'] and newer[0].vector.values['reputation.score'] is not None)
                checks.check('old withheld snapshot remains withheld', next(mv for mv in
                    features.vectors_for_view(view.name, view.version, as_of=cut)
                    if mv.vector.candidate_id == ids[2]).consent_state['allowed'] is False)
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == '__main__':
    raise SystemExit(main())
