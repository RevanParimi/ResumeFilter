"""Screening HTTP contract and persisted employer workflow on scratch SQL.

Uses the existing fake-provider production SQL app and graceful restart loop.
The reused UI contract is HTTP simulation, not actual browser execution.
--leases adds R4-S2-T1A's two-app-process slow-provider scheduling journey.
--outcomes adds R4-S2-T1B1's terminal refusal/erasure journey to --leases.
--expiry adds R4-S2-T1B2a's no-reclaimer terminal expiry and recovery.
--persistence adds R4-S2-T1B2b1's input/report expiry rollback and recovery.
Its checkpoints also verify B2b2a's private original facts across workers.
B2b2b adds first-report reuse without provider replay, including after restart.
--ingest-races adds R4-S2-T2's controlled candidate/resume creation contention.
--body-limit adds R4-S2-T3A's aggregate ingress refusal and slow-upload checks.
--pdf-execution adds R4-S2-T3B's real child stall/admission/timeout checks.
--batch-management composes A/B/C controls and cross-pool/erasure acceptance.
--batch-admission-workers verifies process admission/claims without late continuation.
--batch-recovery-workers verifies held input/report recovery without late continuation.
--postgres uses an explicitly disposable DEE_TEST_DB_URL and an owned schema.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from hashlib import sha256
from http.client import HTTPResponse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from threading import get_ident, local, Lock

import check_ui_screening_contract as contract
from _smoke import Smoke, base_env, client, wait_healthy
from smoke_r4_s1_t1a import create_smoke_app as sql_app, serve
from smoke_r1_s1_t3a_v1 import database
from smoke_s82 import _code_for


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-screening-router-admin"


def create_batch_admission_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    return create_batch_admission_smoke_app(base_factory=create_smoke_app)


def create_batch_admission_smoke_app(*, base_factory=None):
    """Hold real admission SQL; another app still contends through the database."""
    from sqlalchemy import event
    app = (base_factory or create_smoke_app)()
    original = app.router.lifespan_context
    scratch = Path(os.environ['VERITAS_SQL_SMOKE_EVENTS']).parent
    state, mutex = local(), Lock()
    def record(kind, **values):
        with mutex, (scratch / ('admission-' + kind + '.jsonl')).open('a') as log:
            log.write(json.dumps({'pid': os.getpid(), **values}) + '\n')
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            services, caller = app.state.services, get_ident()
            pool = services.batch_admissions
            run, assess, now = pool.run, app.state.engine.evaluate, services.screening._now
            complete = services.screening._store.complete
            async def tracked(operation, *args, **kwargs):
                def owned():
                    assert get_ident() != caller
                    state.active, state.held, state.claiming, state.mode = True, False, False, None
                    state.recovering = operation.__name__ == 'recover_report'
                    record('operations', subject_id=getattr(args[1], 'id', args[1]), action=operation.__name__)
                    try:
                        return operation(*args, **kwargs)
                    finally:
                        if state.held:
                            record('completed')
                        record('finished')
                        state.active = False
                return await run(owned)
            async def evaluate(**kwargs):
                assert get_ident() == caller
                if (scratch / 'recovery-seed-input').exists():
                    raise RuntimeError('synthetic-interrupted-input')
                record('evaluations')
                return await assess(**kwargs)
            def checkpoint(item_id, **kwargs):
                if (scratch / 'recovery-seed-report').exists():
                    from app.screening.store import CompletionOutcome
                    (scratch / 'recovery-seeded.json').write_text(json.dumps({
                        key: kwargs[key] for key in ('candidate_id', 'resume_id', 'report_id')}))
                    return CompletionOutcome.REFUSED
                return complete(item_id, **kwargs)
            def clock():
                advance = scratch / 'admission-advance'
                steps = int(advance.read_text() or '1') if advance.exists() else 0
                offset = (services.settings.screening_claim_timeout_seconds + 1) * steps
                return now() + timedelta(seconds=offset)
            def gate(phase):
                if not getattr(state, 'active', False) or state.held:
                    return
                mode_file = scratch / 'admission-mode'
                selected = mode_file.read_text() if mode_file.exists() else ''
                if selected.split(':')[0] != phase:
                    return
                owner = scratch / 'admission-owner'
                try:
                    with owner.open('x') as file:
                        file.write(str(os.getpid()))
                except FileExistsError:
                    if owner.read_text() != str(os.getpid()):
                        return
                state.held, state.mode = True, selected
                record('entered', mode=selected)
                deadline = time.monotonic() + 30
                while not (scratch / 'admission-release').exists():
                    assert time.monotonic() < deadline, 'synthetic admission hold timed out'
                    time.sleep(.01)
            def sql(conn, cursor, statement, parameters, context, many):
                if not getattr(state, 'active', False):
                    return
                statement = statement.lower()
                if state.recovering and 'from screening_item_inputs' in statement:
                    gate('recovery')
                    if state.mode == 'recovery:rollback':
                        raise RuntimeError('synthetic-private-recovery-rollback')
                if 'rate_limit_counters' in statement:
                    gate('limiter')
                elif 'from screening_batches' in statement:
                    gate('ownership')
                if 'update batch_items' in statement:
                    state.claiming = True
            def begin(session, transaction, connection):
                assert session.info.setdefault('admission_owner', get_ident()) == get_ident()
            def end(session, transaction):
                assert session.info.get('admission_owner', get_ident()) == get_ident()
            def commit(session):
                if getattr(state, 'active', False) and state.claiming:
                    gate('claim')
                    if state.mode == 'claim:rollback':
                        raise RuntimeError('synthetic-private-admission-rollback')
            listeners = [(services.session_factory.kw['bind'], 'before_cursor_execute', sql),
                (services.session_factory, 'after_begin', begin), (services.session_factory, 'after_transaction_end', end),
                (services.session_factory, 'before_commit', commit)]
            pool.run, app.state.engine.evaluate, services.screening._now = tracked, evaluate, clock
            services.screening._store.complete = checkpoint
            for target, name, listener in listeners:
                event.listen(target, name, listener)
            try:
                yield
            finally:
                (scratch / 'admission-release').touch()
                await pool.aclose()
                pool.run, app.state.engine.evaluate, services.screening._now = run, assess, now
                services.screening._store.complete = complete
                for target, name, listener in listeners:
                    event.remove(target, name, listener)
    app.router.lifespan_context = lifespan
    return app


def seed_batch_recovery(actor, scratch, saved, name):
    """Create real interrupted input/report state through HTTP, never a DB edit."""
    created = actor.post('/screening/batches', json={'name': name,
        'items': [{'resume_text': contract._resume('Synthetic ' + name, 'recovery@example.in')}]}).json()
    path = '/screening/batches/' + created['id']
    if saved != 'none':
        marker = scratch / ('recovery-seed-' + saved)
        marker.touch()
        try:
            response = actor.post(path + '/process')
            assert response.status_code == 200 and response.json()['processed'] == 0
            assert response.json()['failed'] == int(saved == 'input')
        finally:
            marker.unlink(missing_ok=True)
        if saved == 'input':
            assert actor.post(path + '/retry').json()['requeued'] == 1
    (scratch / 'admission-advance').write_text('1')
    return created


def check_batch_recovery(checks, scratch, control, actor, other, server):
    def count(kind):
        file = scratch / ('admission-' + kind + '.jsonl')
        return len(file.read_text().splitlines()) if file.exists() else 0
    def require(response, status=200):
        assert response.status_code == status, (response.status_code, response.text)
        return response.json()
    snapshots = []
    for saved in ('none', 'input', 'report'):
        for ending in ('commit', 'rollback'):
            mode = saved + '/' + ending
            created = seed_batch_recovery(actor, scratch, saved, 'Recovery ' + mode)
            path = '/screening/batches/' + created['id']
            seeded = json.loads((scratch / 'recovery-seeded.json').read_text()) if saved == 'report' else None
            entered, completed, finished, evaluations = [count(kind) for kind in ('entered', 'completed', 'finished', 'evaluations')]
            for marker in ('admission-release', 'admission-owner'):
                (scratch / marker).unlink(missing_ok=True)
            (scratch / 'admission-mode').write_text('recovery:' + ending)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); second_port = sock.getsockname()[1]
            with server(second_port, scratch / 'recovery-second-stop') as second_base:
                with client(second_base, cookies=actor.cookies, headers={'X-CSRF-Token': actor.headers['X-CSRF-Token']}) as peer:
                    try:
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            pending = pool.submit(actor.post, path + '/process')
                            try:
                                deadline = time.monotonic() + 10
                                while count('entered') == entered:
                                    assert time.monotonic() < deadline
                                    time.sleep(.01)
                                checks.check(mode + ': held recovery leaves health/admin and tenant-scoped saved GET responsive',
                                    control.get('/healthz').status_code == control.get('/admin/users').status_code == actor.get(path).status_code == 200
                                    and other.get(path).status_code == 404)
                                refused = other.post(path + '/process')
                                checks.check(mode + ': recovery retains admission without leaking another tenant',
                                    require(refused, 503) == {'detail': 'batch_admission_capacity_exhausted'})
                                response = pending.result(timeout=5)
                                checks.check(mode + ': timeout stops without provider or partial success',
                                    require(response, 503) == {'detail': 'batch_admission_pending'}
                                    and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers
                                    and count('evaluations') == evaluations)
                                checks.check(mode + ': second app is admitted but waits on the shared SQL guard',
                                    require(peer.post(path + '/process'), 503) == {'detail': 'batch_admission_pending'}
                                    and count('evaluations') == evaluations)
                            finally:
                                (scratch / 'admission-release').touch()
                    finally:
                        (scratch / 'admission-release').touch()
            deadline = time.monotonic() + 10
            while count('completed') == completed or count('finished') < finished + 3:
                assert time.monotonic() < deadline
                time.sleep(.01)
            (scratch / 'admission-mode').unlink(missing_ok=True)
            settled = saved == 'report' and ending == 'commit'
            counts = require(actor.get(path))['counts']
            checks.check(mode + ': late operation only settles the saved report or retains its live lease',
                counts == {'pending': 0, 'processing': int(not settled), 'done': int(settled), 'failed': 0}
                and count('evaluations') == evaluations)
            (scratch / 'admission-advance').write_text('2')
            checks.check(mode + ': explicit saved-state read never replays intake',
                require(actor.get(path))['counts']['pending'] == int(not settled) and count('evaluations') == evaluations)
            result = require(actor.post(path + '/process'))
            row = require(actor.get(path + '/queue'))['rows'][0]
            checks.check(mode + ': only separate intent continues, with no reevaluation of a checkpoint',
                result['processed'] == int(not settled) and result['remaining'] == 0
                and count('evaluations') == evaluations + int(saved != 'report')
                and (seeded is None or row['report_id'] == seeded['report_id']))
            snapshots.append((path, {suffix: require(actor.get(path + suffix)) for suffix in ('', '/queue', '/summary')}))
            (scratch / 'admission-advance').unlink(missing_ok=True)
    return snapshots


def check_batch_admission(checks, scratch, control, actor, other, server):
    def count(kind):
        file = scratch / ('admission-' + kind + '.jsonl')
        return len(file.read_text().splitlines()) if file.exists() else 0
    def require(response, status=200):
        assert response.status_code == status, (response.status_code, response.text)
        return response.json()
    saved = []
    for mode in ('limiter', 'ownership', 'claim:commit', 'claim:rollback'):
        created = require(actor.post('/screening/batches', json={'name': 'Admission ' + mode,
            'items': [{'resume_text': contract._resume('Synthetic Admission ' + mode, 'admission@example.in')}]}))
        path = '/screening/batches/' + created['id']
        entered, completed, finished, operations, evaluations = [count(kind) for kind in
            ('entered', 'completed', 'finished', 'operations', 'evaluations')]
        for name in ('admission-release', 'admission-owner'):
            (scratch / name).unlink(missing_ok=True)
        (scratch / 'admission-mode').write_text(mode)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); second_port = sock.getsockname()[1]
        with server(second_port, scratch / 'admission-second-stop') as second_base:
            with client(second_base, cookies=actor.cookies, headers={'X-CSRF-Token': actor.headers['X-CSRF-Token']}) as peer:
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        pending = executor.submit(actor.post, path + '/process')
                        try:
                            deadline = time.monotonic() + 10
                            while count('entered') == entered:
                                assert time.monotonic() < deadline
                                time.sleep(.01)
                            checks.check(mode + ': held admission leaves health/admin/saved GET responsive',
                                control.get('/healthz').status_code == control.get('/admin/users').status_code == actor.get(path).status_code == 200)
                            refused = other.post(path + '/process')
                            checks.check(mode + ': full admission refuses before scope lookup',
                                require(refused, 503) == {'detail': 'batch_admission_capacity_exhausted'}
                                and refused.headers.get('retry-after') == '1' and 'set-cookie' not in refused.headers)
                            checks.check(mode + ': pending admission has no partial success or provider continuation',
                                require(pending.result(timeout=5), 503) == {'detail': 'batch_admission_pending'}
                                and count('operations') == operations + 1 and count('evaluations') == evaluations)
                            if mode == 'claim:commit':
                                peer_response = peer.post(path + '/process')
                                checks.check('second app independently admits but times out on the shared claim lock',
                                    require(peer_response, 503) == {'detail': 'batch_admission_pending'}
                                    and count('operations') == operations + 2 and count('evaluations') == evaluations)
                        finally:
                            (scratch / 'admission-release').touch()
                finally:
                    (scratch / 'admission-release').touch()
        deadline = time.monotonic() + 10
        accepted = 2 if mode == 'claim:commit' else 1
        while count('completed') == completed or count('finished') < finished + accepted:
            assert time.monotonic() < deadline
            time.sleep(.01)
        (scratch / 'admission-mode').unlink(missing_ok=True)
        current = require(actor.get(path))
        checks.check(mode + ': late claim/rollback changes only saved lease state, never assessment',
            current['counts'] == {'pending': int(mode == 'claim:rollback'),
                'processing': int(mode != 'claim:rollback'), 'done': 0, 'failed': 0}
            and count('evaluations') == evaluations and other.get(path).status_code == 404)
        (scratch / 'admission-advance').touch()
        try:
            checks.check(mode + ': explicit GET after deterministic expiry does not process',
                require(actor.get(path))['counts']['pending'] == 1 and count('evaluations') == evaluations)
            processed = require(actor.post(path + '/process'))
            checks.check(mode + ': only separate human intent assesses once after lease recovery',
                processed['processed'] == 1 and processed['remaining'] == 0 and count('evaluations') == evaluations + 1)
        finally:
            (scratch / 'admission-advance').unlink(missing_ok=True)
        saved.append((path, {suffix: require(actor.get(path + suffix)) for suffix in ('', '/queue', '/summary')}))
    return saved


def create_batch_management_smoke_app(*, base_factory=None):
    """Compose existing A/B/C controls over one real Services/app lifecycle."""
    def mutation():
        return create_batch_registration_smoke_app(base_factory=base_factory, _mutation=True)
    def registration():
        return create_batch_registration_smoke_app(base_factory=mutation)
    return create_batch_read_smoke_app(base_factory=registration)


def create_batch_management_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    return create_batch_management_smoke_app(base_factory=create_smoke_app)


def check_batch_management_isolation(checks, scratch, control, actor, other, path):
    """Each occupied plane leaves the other two usable, in one migrated app."""
    def count(prefix, kind):
        file = scratch / (prefix + '-' + kind + '.jsonl')
        return len(file.read_text().splitlines()) if file.exists() else 0
    def require(response, status=200):
        assert response.status_code == status, (response.status_code, response.text)
        return response.json()
    def payload(label):
        return {'name': 'Combined ' + label, 'items': [{'resume_text':
            contract._resume('Synthetic Combined', 'combined@example.in')}]}
    registrations = []
    planes = [('batch-read', 'get', actor.get, path, None, 'batch_read'),
        ('registration', 'commit', actor.post, '/screening/batches', payload('held registration'), 'batch_registration'),
        ('mutation', 'retry:commit', actor.post, path + '/retry', None, 'batch_mutation')]
    for prefix, mode, operation, url, body, code in planes:
        entered, completed = count(prefix, 'entered'), count(prefix, 'completed')
        operations = count(prefix, 'operations')
        evaluations = [count(name, 'evaluations') for name, *_ in planes]
        (scratch / (prefix + '-release')).unlink(missing_ok=True)
        (scratch / (prefix + '-mode')).write_text(mode)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(operation, url, **({'json': body} if body else {}))
                try:
                    deadline = time.monotonic() + 10
                    while count(prefix, 'entered') == entered:
                        assert time.monotonic() < deadline
                        time.sleep(.01)
                    checks.check(prefix + ': unrelated admin/health remain responsive',
                        control.get('/healthz').status_code == control.get('/admin/users').status_code == 200)
                    if prefix != 'batch-read':
                        checks.check(prefix + ': saved-state read has separate admission', actor.get(path).status_code == 200)
                    if prefix != 'registration':
                        created = require(other.post('/screening/batches', json=payload(prefix + ' neighbour')))
                        registrations.append(('other', '/screening/batches/' + created['id'], created))
                        checks.check(prefix + ': another tenant can register without processing', created['counts']['pending'] == 1)
                    if prefix != 'mutation':
                        checks.check(prefix + ': retry admission is independent and does not assess',
                            require(actor.post(path + '/retry'))['requeued'] == 0)
                    if prefix == 'batch-read':
                        refused = other.get(path)
                    elif prefix == 'registration':
                        refused = other.post('/screening/batches', json=payload('refused'))
                    else:
                        refused = other.delete(path)
                    checks.check(prefix + ': only its own full pool refuses admission',
                        require(refused, 503) == {'detail': code + '_capacity_exhausted'}
                        and refused.headers.get('retry-after') == '1' and 'set-cookie' not in refused.headers)
                    response = pending.result(timeout=5)
                    detail = require(response, 503)['detail']
                    checks.check(prefix + ': uncertainty retains the accepted operation without replay',
                        (detail['code'] if isinstance(detail, dict) else detail) == code + '_pending'
                        and count(prefix, 'operations') == operations + 1)
                    pending_id = detail['batch_id'] if prefix == 'registration' else None
                finally:
                    (scratch / (prefix + '-release')).touch()
        finally:
            (scratch / (prefix + '-release')).touch()
        deadline = time.monotonic() + 10
        while count(prefix, 'completed') == completed:
            assert time.monotonic() < deadline
            time.sleep(.01)
        (scratch / (prefix + '-mode')).unlink(missing_ok=True)
        checks.check(prefix + ': no management operation assesses a resume',
            [count(name, 'evaluations') for name, *_ in planes] == evaluations)
        if pending_id:
            target = '/screening/batches/' + pending_id
            created = require(actor.get(target))
            registrations.append(('actor', target, created))
            checks.check('held registration commits once with scoped GET recovery',
                created['counts']['pending'] == 1 and other.get(target).status_code == 404)
    return registrations


def check_combined_erasure_fence(checks, scratch, actor, other, registrations, neighbours):
    """A's deliberate erasure changes older unresolved B/neighbor snapshots."""
    def count():
        file = scratch / 'batch-read-evaluations.jsonl'
        return len(file.read_text().splitlines()) if file.exists() else 0
    evaluations, snapshots = count(), []
    for owner, path, original in neighbours + [('actor', path, body) for path, status, body in registrations if status == 200]:
        client, foreign = (actor, other) if owner == 'actor' else (other, actor)
        response = client.get(path)
        assert response.status_code == 200, response.text
        current, total = response.json(), sum(original['counts'].values())
        checks.check(owner + ': actual erasure blocks older unresolved registrations across tenants',
            current['counts'] == {'pending': 0, 'processing': 0, 'done': 0, 'failed': total}
            and all(current[key] == value for key, value in original.items() if key not in ('counts', 'status'))
            and foreign.get(path).status_code == 404)
        retried = client.post(path + '/retry')
        checks.check(owner + ': blocked input is skipped without another assessment',
            retried.status_code == 200 and retried.json()['requeued'] == 0 and retried.json()['skipped'] == total
            and count() == evaluations)
        snapshots.append((owner, path, current))
    registrations = [(path, status, next(body for owner, target, body in snapshots if owner == 'actor' and target == path))
        if status == 200 else (path, status, body) for path, status, body in registrations]
    return registrations, snapshots


def create_batch_registration_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    return create_batch_registration_smoke_app(base_factory=create_smoke_app)


def create_batch_mutation_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    return create_batch_registration_smoke_app(base_factory=create_smoke_app, _mutation=True)


def create_batch_mutation_smoke_app():
    return create_batch_registration_smoke_app(_mutation=True)


def create_batch_registration_smoke_app(*, base_factory=None, _mutation=False):
    """Controlled real batch SQL, confined to the scratch harness."""
    from sqlalchemy import event
    app = (base_factory or sql_app)()
    original = app.router.lifespan_context
    scratch = Path(os.environ['VERITAS_SQL_SMOKE_EVENTS']).parent
    state, mutex = local(), Lock()
    prefix = 'mutation' if _mutation else 'registration'
    def record(kind, **values):
        with mutex, (scratch / (prefix + '-' + kind + '.jsonl')).open('a') as log:
            log.write(json.dumps(values) + '\n')
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            services, caller = app.state.services, get_ident()
            pool = services.batch_mutations if _mutation else services.batch_registrations
            run, assess = pool.run, app.state.engine.evaluate
            create_batch = services.screening._store.create_batch
            def seeded_batch(*args, **kwargs):
                bid = create_batch(*args, **kwargs)
                if kwargs['name'].startswith('Mutation '):
                    from sqlalchemy import select
                    from app.screening.models import BatchItemRow
                    with services.session_factory() as session:
                        rows = session.scalars(select(BatchItemRow).where(BatchItemRow.batch_id == bid)
                            .order_by(BatchItemRow.created_at, BatchItemRow.id)).all()
                        assert len(rows) == 2
                        for row in rows:
                            row.status, row.error = 'failed', 'internal_error'
                        rows[1].raw_text = ''
                        session.commit()
                return bid
            async def tracked(operation, *args, **kwargs):
                def owned():
                    assert get_ident() != caller
                    bid = args[-1] if _mutation else kwargs['batch_id']
                    state.active, state.held, state.mode, state.action = True, False, None, operation.__name__
                    record('operations', batch_id=bid, action=state.action)
                    try:
                        return operation(*args, **kwargs)
                    finally:
                        if state.held:
                            record('completed', batch_id=bid)
                        state.active = False
                return await run(owned)
            async def evaluate(**kwargs):
                assert get_ident() == caller
                record('evaluations')
                return await assess(**kwargs)
            def sql(conn, cursor, statement, parameters, context, many):
                mode = scratch / (prefix + '-mode')
                needle = 'delete from screening_batches' if _mutation and getattr(state, 'action', None) == 'delete' else 'screening_erasure_state'
                if not getattr(state, 'active', False) or state.held or needle not in statement.lower():
                    return
                selected = mode.read_text() if mode.exists() else None
                if selected and (not _mutation or selected.split(':')[0] == state.action):
                    state.held, state.mode = True, selected
                    record('entered')
                    deadline = time.monotonic() + 30
                    while not (scratch / (prefix + '-release')).exists():
                        assert time.monotonic() < deadline, 'synthetic registration hold timed out'
                        time.sleep(.01)
            def begin(session, transaction, connection):
                assert session.info.setdefault('registration_owner', get_ident()) == get_ident()
            def end(session, transaction):
                assert session.info.get('registration_owner', get_ident()) == get_ident()
            def commit(session):
                if getattr(state, 'active', False) and state.mode and state.mode.split(':')[-1] == 'rollback':
                    session.flush()
                    raise RuntimeError('synthetic-private-registration-rollback')
            listeners = [(services.session_factory.kw['bind'], 'before_cursor_execute', sql),
                (services.session_factory, 'after_begin', begin), (services.session_factory, 'after_transaction_end', end),
                (services.session_factory, 'before_commit', commit)]
            pool.run, app.state.engine.evaluate = tracked, evaluate
            if _mutation:
                services.screening._store.create_batch = seeded_batch
            for target, name, listener in listeners:
                event.listen(target, name, listener)
            try:
                yield
            finally:
                (scratch / (prefix + '-release')).touch()
                await pool.aclose()
                pool.run, app.state.engine.evaluate = run, assess
                services.screening._store.create_batch = create_batch
                for target, name, listener in listeners:
                    event.remove(target, name, listener)
    app.router.lifespan_context = lifespan
    return app


def check_batch_mutations(checks, scratch, control, actor, other):
    def require(response, status=200):
        assert response.status_code == status, (response.status_code, response.text)
        return response.json()
    def count(kind):
        p = scratch / ('mutation-' + kind + '.jsonl')
        return len(p.read_text().splitlines()) if p.exists() else 0
    saved = []
    for action in ('retry', 'delete'):
        for ending in ('commit', 'rollback'):
            label = action + '/' + ending
            resume = contract._resume('Synthetic Mutation', 'mutation@example.in')
            created = require(actor.post('/screening/batches', json={'name': 'Mutation ' + label,
                'items': [{'resume_text': resume}] * 2}))
            path = '/screening/batches/' + created['id']
            assert created['counts']['failed'] == 2
            operations, evaluations = count('operations'), count('evaluations')
            entered, completed = count('entered'), count('completed')
            (scratch / 'mutation-release').unlink(missing_ok=True)
            (scratch / 'mutation-mode').write_text(action + ':' + ending)
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    pending = executor.submit(actor.post if action == 'retry' else actor.delete,
                        path + ('/retry' if action == 'retry' else ''))
                    try:
                        deadline = time.monotonic() + 10
                        while count('entered') == entered:
                            assert time.monotonic() < deadline
                            time.sleep(.01)
                        start = time.monotonic()
                        checks.check(label + ': held mutation SQL leaves unrelated HTTP responsive',
                            control.get('/healthz').status_code == control.get('/admin/users').status_code == 200
                            and time.monotonic() - start < 1)
                        for verb, suffix in ((other.post, '/retry'), (other.delete, '')):
                            response = verb(path + suffix)
                            checks.check(label + ': retry/delete share full admission before scope lookup',
                                require(response, 503) == {'detail': 'batch_mutation_capacity_exhausted'}
                                and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
                        response = pending.result(timeout=5)
                        checks.check(label + ': pending mutation returns no false confirmation',
                            require(response, 503) == {'detail': 'batch_mutation_pending'}
                            and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
                        checks.check(label + ': early GET still sees the pre-write state without replay',
                            require(actor.get(path)) == created and other.get(path).status_code == 404
                            and count('operations') == operations + 1 and count('evaluations') == evaluations)
                    finally:
                        (scratch / 'mutation-release').touch()
            finally:
                (scratch / 'mutation-release').touch()
            deadline = time.monotonic() + 10
            while count('completed') == completed:
                assert time.monotonic() < deadline
                time.sleep(.01)
            (scratch / 'mutation-mode').unlink(missing_ok=True)
            gone = action == 'delete' and ending == 'commit'
            response = actor.get(path)
            body = require(response, 404 if gone else 200)
            checks.check(label + ': late atomic result is readable with no provider or write replay',
                count('operations') == operations + 1 and count('evaluations') == evaluations
                and (gone or body['counts'] == {'pending': int(action == 'retry' and ending == 'commit'),
                    'processing': 0, 'done': 0, 'failed': 1 if action == 'retry' and ending == 'commit' else 2}))
            checks.check(label + ': foreign writes and reads remain indistinguishable from absence',
                all(verb(path + suffix).status_code == verb('/screening/batches/missing' + suffix).status_code == 404
                    for verb, suffix in ((other.get, ''), (other.post, '/retry'), (other.delete, ''))))
            if action == 'retry' and ending == 'commit':
                # Human intent is a distinct later request, after read recovery.
                result = require(actor.post(path + '/process'))
                checks.check('explicit later process alone evaluates the requeued item',
                    result['processed'] == 1 and count('evaluations') == evaluations + 1)
                body = require(actor.get(path))
            saved.append((path, response.status_code, body))
    return saved


def check_batch_registration(checks, scratch, control, actor, other):
    def require(response, status=200):
        assert response.status_code == status, (response.status_code, response.text)
        return response.json()
    def count(kind):
        p = scratch / ('registration-' + kind + '.jsonl')
        return len(p.read_text().splitlines()) if p.exists() else 0
    saved = []
    for ending in ('commit', 'rollback'):
        (scratch / 'registration-release').unlink(missing_ok=True)
        (scratch / 'registration-mode').write_text(ending)
        entered, completed = count('entered'), count('completed')
        operations, evaluations = count('operations'), count('evaluations')
        payload = {'name': 'Uncertain ' + ending, 'domain': 'data_eng',
            'items': [{'resume_text': contract._resume('Synthetic Registration', 'registration@example.in')}] * 2}
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(actor.post, '/screening/batches', json=payload)
                try:
                    deadline = time.monotonic() + 10
                    while count('entered') == entered:
                        assert time.monotonic() < deadline
                        time.sleep(.01)
                    start = time.monotonic()
                    checks.check(ending + ': held registration leaves unrelated HTTP responsive',
                        control.get('/healthz').status_code == control.get('/admin/users').status_code == 200
                        and time.monotonic() - start < 1)
                    refused = other.post('/screening/batches', json=payload)
                    checks.check(ending + ': full admission never creates a peer batch',
                        require(refused, 503) == {'detail': 'batch_registration_capacity_exhausted'}
                        and refused.headers.get('retry-after') == '1' and 'set-cookie' not in refused.headers)
                    response = pending.result(timeout=5)
                    detail = require(response, 503)['detail']
                    bid, path = detail['batch_id'], '/screening/batches/' + detail['batch_id']
                    checks.check(ending + ': pending response provides only a recovery reference',
                        set(detail) == {'code', 'batch_id'} and detail['code'] == 'batch_registration_pending'
                        and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
                    checks.check(ending + ': early saved-state read can be absent while registration is live',
                        actor.get(path).status_code == other.get(path).status_code == 404)
                finally:
                    (scratch / 'registration-release').touch()
        finally:
            (scratch / 'registration-release').touch()
        deadline = time.monotonic() + 10
        while count('completed') == completed:
            assert time.monotonic() < deadline
            time.sleep(.01)
        (scratch / 'registration-mode').unlink(missing_ok=True)
        response = actor.get(path)
        body = require(response, 200 if ending == 'commit' else 404)
        checks.check(ending + ': late atomic result is recovered without replay or processing',
            count('operations') == operations + 1 and count('evaluations') == evaluations
            and (ending != 'commit' or body['counts'] == {'pending': 2, 'processing': 0, 'done': 0, 'failed': 0}))
        checks.check(ending + ': saved result remains scoped to its author and tenant',
            other.get(path).status_code == 404 and (ending != 'commit' or bool(body['created_by_org_user_id'])))
        saved.append((path, response.status_code, body))
    return saved


def create_batch_read_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    return create_batch_read_smoke_app(base_factory=create_smoke_app)


def create_batch_read_smoke_app(*, base_factory=None):
    """Real batch SQL holds; instrumentation never runs in the demo app."""
    from sqlalchemy import event
    app = (base_factory or sql_app)()
    original = app.router.lifespan_context
    scratch = Path(os.environ['VERITAS_SQL_SMOKE_EVENTS']).parent
    state, mutex = local(), Lock()
    def record(kind, **values):
        with mutex, (scratch / ('batch-read-' + kind + '.jsonl')).open('a') as log:
            log.write(json.dumps(values) + '\n')
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            services, caller = app.state.services, get_ident()
            pool = services.batch_reads
            run, assess = pool.run, app.state.engine.evaluate
            async def tracked(operation, *args, **kwargs):
                def owned():
                    assert get_ident() != caller
                    state.method, state.held = operation.__name__, False
                    record('operations', method=state.method)
                    try:
                        return operation(*args, **kwargs)
                    finally:
                        if state.held:
                            record('completed', method=state.method)
                        state.method = None
                return await run(owned)
            async def evaluate(**kwargs):
                assert get_ident() == caller
                record('evaluations')
                return await assess(**kwargs)
            def sql(conn, cursor, statement, parameters, context, many):
                mode = scratch / 'batch-read-mode'
                method = getattr(state, 'method', None)
                if method and not state.held and 'from screening_batches' in statement.lower() and mode.exists() and mode.read_text() == method:
                    state.held = True
                    record('entered', method=method)
                    deadline = time.monotonic() + 30
                    while not (scratch / 'batch-read-release').exists():
                        assert time.monotonic() < deadline, 'synthetic batch read hold timed out'
                        time.sleep(.01)
            def begin(session, transaction, connection):
                assert session.info.setdefault('batch_read_owner', get_ident()) == get_ident()
            def end(session, transaction):
                assert session.info.get('batch_read_owner', get_ident()) == get_ident()
            listeners = [(services.session_factory.kw['bind'], 'before_cursor_execute', sql),
                (services.session_factory, 'after_begin', begin), (services.session_factory, 'after_transaction_end', end)]
            pool.run, app.state.engine.evaluate = tracked, evaluate
            for target, name, listener in listeners:
                event.listen(target, name, listener)
            try:
                yield
            finally:
                (scratch / 'batch-read-release').touch()
                await pool.aclose()
                pool.run, app.state.engine.evaluate = run, assess
                for target, name, listener in listeners:
                    event.remove(target, name, listener)
    app.router.lifespan_context = lifespan
    return app


def check_batch_reads(checks, scratch, control, actor, other, path):
    def require(response, status=200):
        assert response.status_code == status, (response.status_code, response.text)
        return response.json()
    def count(kind):
        p = scratch / ('batch-read-' + kind + '.jsonl')
        return len(p.read_text().splitlines()) if p.exists() else 0
    def arm(method):
        for kind in ('entered', 'completed'):
            (scratch / ('batch-read-' + kind + '.jsonl')).unlink(missing_ok=True)
        (scratch / 'batch-read-release').unlink(missing_ok=True)
        (scratch / 'batch-read-mode').write_text(method)
    def release():
        (scratch / 'batch-read-release').touch()
        deadline = time.monotonic() + 10
        while count('completed') < 1:
            assert time.monotonic() < deadline
            time.sleep(.01)
        (scratch / 'batch-read-mode').unlink(missing_ok=True)
    views = [('get', path), ('list', '/screening/batches?limit=1'),
        ('queue', path + '/queue?limit=1'), ('summary', path + '/summary')]
    for method, url in views:
        expected = require(actor.get(url))
        operations, evaluations = count('operations'), count('evaluations')
        arm(method)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(actor.get, url)
                try:
                    deadline = time.monotonic() + 10
                    while count('entered') < 1:
                        assert time.monotonic() < deadline
                        time.sleep(.01)
                    start = time.monotonic()
                    checks.check(method + ': held batch SQL leaves unrelated HTTP responsive',
                        control.get('/healthz').status_code == control.get('/admin/users').status_code == 200
                        and time.monotonic() - start < 1)
                    for _, peer in views:
                        refused = other.get(peer)
                        checks.check(method + ': all batch read doors share retained admission',
                            require(refused, 503) == {'detail': 'batch_read_capacity_exhausted'}
                            and refused.headers.get('retry-after') == '1' and 'set-cookie' not in refused.headers)
                    response = pending.result(timeout=5)
                    checks.check(method + ': pending read returns safe 503 without a partial view',
                        require(response, 503) == {'detail': 'batch_read_pending'}
                        and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
                finally:
                    release()
        finally:
            (scratch / 'batch-read-release').touch()
        checks.check(method + ': late read is not replayed and recovery only reads saved state',
            count('operations') == operations + 1 and count('evaluations') == evaluations
            and require(actor.get(url)) == expected)
    # Actual erasure while a worker is held before its SELECT; this is distinct
    # from the competing-driver lock cases in pytest.
    resume = contract._resume('Synthetic Batch Read Erasure', 'batch-read-erasure@example.in')
    erased = require(actor.post('/screening/batches', json={'name': 'Read erasure', 'items': [{'resume_text': resume}]}))
    erase_path = '/screening/batches/' + erased['id']
    require(actor.post(erase_path + '/process'))
    subject = require(actor.get(erase_path + '/queue'))['rows'][0]['candidate_id']
    evaluations = count('evaluations')
    arm('queue')
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(actor.get, erase_path + '/queue')
            try:
                deadline = time.monotonic() + 10
                while count('entered') < 1:
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                require(control.delete('/candidates/' + subject))
                require(pending.result(timeout=5), 503)
            finally:
                release()
    finally:
        (scratch / 'batch-read-release').touch()
    row = require(actor.get(erase_path + '/queue'))['rows'][0]
    checks.check('worker reads retain real erasure projection and saved counters',
        all(row[key] is None for key in ('candidate_id', 'resume_id', 'report_id'))
        and require(actor.get(erase_path))['counts']['done'] == 1 and count('evaluations') == evaluations)
    return [(url, require(actor.get(url))) for _, url in views] + [(erase_path + '/queue', {'rows': [row], 'next_cursor': None})]


def install_controlled_pdf_worker(scratch):
    """Instrument the real disposable parser after reader construction."""
    import app.core.pdf as pdf
    source = Path(pdf.__file__).with_name('pdf_worker.py').read_text(encoding='utf-8')
    source = source.replace('reader = PdfReader(io.BytesIO(data), strict=limits["strict"])',
        'reader = PdfReader(io.BytesIO(data), strict=limits["strict"])\n'
        f'    gate = __import__("pathlib").Path({str(scratch)!r})\n'
        '    if (gate / "pdf-mode").exists():\n'
        '        mode = (gate / "pdf-mode").read_text()\n'
        '        (gate / "pdf-entered").touch()\n'
        '        if mode == "error": raise ValueError("private-pdf-smoke-sentinel")\n'
        '        while not (gate / "pdf-release").exists(): __import__("time").sleep(.01)')
    directory = scratch / 'pdf-worker'
    directory.mkdir(exist_ok=True)
    (directory / 'pdf_worker.py').write_text(source, encoding='utf-8')
    pdf.__file__ = str(directory / 'pdf.py')


class ObservePausedUpload:
    """Test-only acknowledgement that the real ASGI server delivered the prefix."""
    def __init__(self, app, *, marker):
        self.app, self.marker = app, marker

    async def __call__(self, scope, receive, send):
        async def observed_receive():
            message = await receive()
            if message.get("body"):
                self.marker.touch()
            return message
        paused = scope["type"] == "http" and (
            b"x-smoke-paused-upload", b"true") in scope.get("headers", ())
        await self.app(scope, observed_receive if paused else receive, send)


def create_smoke_app():
    """Pause one synthetic evaluation across two real app processes."""
    app = sql_app()
    original = app.router.lifespan_context
    scratch = Path(os.environ["VERITAS_SQL_SMOKE_EVENTS"]).parent
    if os.environ.get("VERITAS_BODY_LIMIT_SMOKE") == "true":
        app.add_middleware(ObservePausedUpload, marker=scratch / "body-upload-waiting")
    if os.environ.get("VERITAS_PDF_EXECUTION_SMOKE") == "true":
        install_controlled_pdf_worker(scratch)

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            evaluate = app.state.engine.evaluate
            svc = app.state.services.screening
            now, complete = svc._now, svc._store.complete
            retain, bind = svc._store.retain_ingested_input, svc._store.bind_input_report

            def controlled_now():
                # Deterministic expiry for competing OS processes, not a
                # measured wall-clock timeout.
                offset = svc._settings.screening_claim_timeout_seconds + 1 if (scratch / "outcome-advanced").exists() else 0
                return now() + timedelta(seconds=offset)

            def gate(mode, subject):
                armed = scratch / "outcome-mode"
                if armed.exists() and armed.read_text(encoding="utf-8") == mode:
                    try:
                        (scratch / f"outcome-claimed-{mode}").open("x").close()
                    except FileExistsError:
                        pass
                    else:
                        entered = scratch / f"outcome-entered-{mode}.json"
                        temporary = entered.with_suffix(".tmp")
                        temporary.write_text(json.dumps(subject), encoding="utf-8")
                        temporary.replace(entered)
                        deadline = time.monotonic() + 30
                        while not (scratch / f"outcome-release-{mode}").exists():
                            assert time.monotonic() < deadline, "synthetic persistence gate timed out"
                            time.sleep(.05)

            def controlled_complete(item_id, **kwargs):
                from app.screening.models import ScreeningInputRow
                with svc._store._session_factory() as session:
                    ref = session.get(ScreeningInputRow, item_id)
                    checkpoint = {"ingest_facts": ref.ingest_facts if ref else None,
                                  "input_created_at": ref.created_at.isoformat() if ref else None}
                target = scratch / f"checkpoint-{kwargs['report_id']}.json"
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(checkpoint), encoding="utf-8")
                temporary.replace(target)
                armed = scratch / "outcome-mode"
                if armed.exists():
                    mode = armed.read_text(encoding="utf-8")
                    if mode in {"stolen", "erased", "expired", "restart"}:
                        gate(mode, {"candidate_id": kwargs["candidate_id"], "report_id": kwargs["report_id"],
                                    **checkpoint})
                return complete(item_id, **kwargs)

            def controlled_retain(session, org, item, outcome, **kwargs):
                (scratch / f"ingested-{outcome.extraction_id}.json").write_text(json.dumps({
                    "candidate_id": outcome.candidate_id}), encoding="utf-8")
                gate("input-expired", {"candidate_id": outcome.candidate_id, "report_id": None})
                return retain(session, org, item, outcome, **kwargs)

            def controlled_bind(session, org, item, report, **kwargs):
                from app.screening.models import ScreeningInputRow
                ref = session.get(ScreeningInputRow, item.id)
                gate("report-expired", {"candidate_id": report.candidate_id, "report_id": report.id,
                    "ingest_facts": ref.ingest_facts if ref else None,
                    "input_created_at": ref.created_at.isoformat() if ref else None})
                return bind(session, org, item, report, **kwargs)

            svc._now = controlled_now
            svc._store.complete = controlled_complete
            svc._store.retain_ingested_input = controlled_retain
            svc._store.bind_input_report = controlled_bind

            candidates = app.state.services.candidates
            ingest, resolve = candidates.ingest, candidates._resolve_candidate

            def observe_resolve(session, profile):
                result = resolve(session, profile)
                armed = scratch / "outcome-mode"
                if armed.exists():
                    mode = armed.read_text(encoding="utf-8")
                    if mode.startswith("ingest-") and (scratch / f"outcome-entered-{mode}.json").exists():
                        (scratch / f"outcome-resolved-{mode}").touch()
                return result

            def controlled_ingest(result, resume_text, **kwargs):
                if "R4-S2-T2" in resume_text:
                    callback = kwargs.get("before_commit")
                    def checkpoint(session, outcome):
                        if callback is not None:
                            callback(session, outcome)
                        armed = scratch / "outcome-mode"
                        if armed.exists():
                            mode = armed.read_text(encoding="utf-8")
                            if mode.startswith("ingest-"):
                                gate(mode, outcome.model_dump())
                    kwargs["before_commit"] = checkpoint
                return ingest(result, resume_text, **kwargs)

            candidates._resolve_candidate = observe_resolve
            candidates.ingest = controlled_ingest

            if os.environ.get("VERITAS_BODY_LIMIT_SMOKE") == "true":
                import app.core.resume as resume_input
                parse = resume_input.pdf_b64_to_text
                def observed_pdf(*args, **kwargs):
                    if (scratch / "body-checks-armed").exists():
                        (scratch / "body-pdf-called").touch()
                    return parse(*args, **kwargs)
                resume_input.pdf_b64_to_text = observed_pdf

            async def controlled(**kwargs):
                if "R4-S2-T1A slow fake gate" in (kwargs.get("resume_text") or ""):
                    try:
                        (scratch / "lease-claimed").open("x").close()
                    except FileExistsError:
                        pass
                    else:
                        (scratch / "lease-entered").write_text("ready", encoding="utf-8")
                        deadline = time.monotonic() + 30
                        while not (scratch / "lease-release").exists():
                            assert time.monotonic() < deadline, "synthetic provider gate timed out"
                            await asyncio.sleep(.05)
                report = await evaluate(**kwargs)
                (scratch / f"evaluated-{report.id}.json").write_text(json.dumps({
                    "sha256": sha256((kwargs.get("resume_text") or "").encode("utf-8")).hexdigest()}), encoding="utf-8")
                return report

            app.state.engine.evaluate = controlled
            yield

    app.router.lifespan_context = lifespan
    return app


def check_ingest_races(checks, scratch, control, worker_a, worker_b):
    """Hold a committed-write candidate transaction while another process resolves it."""
    def require(response):
        assert response.status_code == 200, (response.request.url.path, response.status_code)
        return response.json()

    def wait_for(path):
        deadline = time.monotonic() + 20
        while not path.exists():
            assert time.monotonic() < deadline, "synthetic ingest gate timed out"
            time.sleep(.05)

    other = require(control.post("/ledger/orgs", json={"name": "Synthetic ingest counterparty"}))
    snapshots = {}
    for case in ("new-email", "new-phone", "existing-identical", "existing-changed",
                 "other-tenant", "operator-employer"):
        text = contract._resume("Synthetic Ingest Race", f"ingest-{case}@example.in") + "\nR4-S2-T2"
        if case == "new-phone":
            text = text.replace("ingest-new-phone@example.in", "") + "\nPhone: +91 98765 43210"
        body = {"resume_text": text, "evaluate": case == "other-tenant", "domain": "genai"}
        if case.startswith("existing-"):
            require(worker_a.post("/screening/candidates", json={**body, "resume_text": text + "\nSeed version"}))
        mode = "ingest-" + case
        (scratch / "outcome-mode").write_text(mode, encoding="utf-8")
        first_client = control if case == "operator-employer" else worker_a
        first_path = "/candidates" if case == "operator-employer" else "/screening/candidates"
        second_body = {**body, "resume_text": text + "\nNew availability"} if case == "existing-changed" else body
        second_headers = {"X-Org-Key": other["api_key"]} if case == "other-tenant" else {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(first_client.post, first_path, json=body)
            try:
                wait_for(scratch / f"outcome-entered-{mode}.json")
                two = pool.submit(worker_b.post, "/screening/candidates", json=second_body, headers=second_headers)
                wait_for(scratch / f"outcome-resolved-{mode}")
            finally:
                (scratch / f"outcome-release-{mode}").touch()
            first, second = require(one.result(timeout=30)), require(two.result(timeout=30))
        (scratch / "outcome-mode").unlink()
        extra_row = case in {"existing-changed", "other-tenant", "operator-employer"}
        checks.check(f"{case}: concurrent uploads share subject and defined resume/version outcome",
            first["candidate_id"] == second["candidate_id"]
            and (first["resume_id"] == second["resume_id"]) is (not extra_row)
            and second["resume_version"] == first["resume_version"] + int(extra_row)
            and second["matched_existing"] and second["duplicate_resume"] is (case != "existing-changed")
            and ((first["report"] is second["report"] is None) if case != "other-tenant" else
                 first["report"]["advisory"] and second["report"]["human_review_required"]))
        cid = first["candidate_id"]
        path = f"/candidates/{cid}/resumes"
        snapshots[path] = require(control.get(path))
        versions = [row["version"] for row in snapshots[path]["resumes"]]
        checks.check(f"{case}: persisted versions are unique with no failed-write gaps",
            versions == list(range(1, second["resume_version"] + 1)))
        if case == "other-tenant":
            with client(str(worker_b.base_url), headers=second_headers) as counterparty:
                left, right = first["report"]["id"], second["report"]["id"]
                checks.check("concurrent counterparties retain separate advisory reports and scoped reads",
                    [row["id"] for row in require(worker_a.get(f"/screening/candidates/{cid}/reports"))] == [left]
                    and [row["id"] for row in require(counterparty.get(f"/screening/candidates/{cid}/reports"))] == [right]
                    and worker_a.get(f"/screening/reports/{right}").status_code == 404
                    and counterparty.get(f"/screening/reports/{left}").status_code == 404)
    return snapshots


def check_request_body_limit(checks, scratch, base, control, actor):
    """Real HTTP framing, paused uploads and exact-size accepted registration."""
    from urllib.parse import urlsplit
    cap = 64_000
    expected = {"detail": f"request body exceeds max_request_body_bytes={cap}"}
    origin = contract.UI_ORIGIN
    def require(response):
        assert response.status_code == 200, (response.request.url.path, response.status_code)
        return response.json()
    before = require(actor.get("/screening/batches"))
    (scratch / "body-checks-armed").touch()
    address = (urlsplit(base).hostname, urlsplit(base).port)
    # A peer which sends no body still receives a refusal from the length hint.
    with socket.create_connection(address, timeout=3) as peer:
        peer.sendall((f"POST /screening/batches HTTP/1.1\r\nHost: {address[0]}\r\n"
                      f"Content-Length: {cap + 1}\r\nConnection: close\r\n\r\n").encode())
        response = HTTPResponse(peer)
        response.begin()
        checks.check("oversized declared length refuses before any upload bytes arrive",
            response.status == 413 and json.loads(response.read()) == expected
            and bool(response.getheader("X-Request-ID")))
    payload = json.dumps({"items": [{"resume_pdf_b64": "A" * 40_000}] * 2,
                          "name": "private-body-smoke-sentinel"}).encode()
    for mode, content in (("known", payload), ("chunked", iter((payload[:32_000], payload[32_000:]))),
                          ("invalid-json", b"{" + b"x" * cap)):
        response = actor.post("/screening/batches", content=content,
            headers={"Content-Type": "application/json", "Origin": origin})
        checks.check(f"{mode}: aggregate refusal precedes parsing/PDF and keeps CORS/request ID",
            response.status_code == 413 and response.json() == expected
            and response.headers.get("access-control-allow-origin") == origin
            and bool(response.headers.get("x-request-id")))
    checks.check("refused batch input performs no PDF parse or durable registration",
        not (scratch / "body-pdf-called").exists()
        and require(actor.get("/screening/batches")) == before)

    # Hold one incomplete application request while unrelated requests complete.
    with socket.create_connection(address, timeout=3) as peer:
        peer.sendall((f"POST /screening/batches HTTP/1.1\r\nHost: {address[0]}\r\n"
                      f"Content-Length: {cap}\r\nContent-Type: application/json\r\n"
                      "X-Smoke-Paused-Upload: true\r\n\r\n{").encode())
        deadline = time.monotonic() + 5
        while not (scratch / "body-upload-waiting").exists():
            assert time.monotonic() < deadline, "server did not receive the paused upload prefix"
            time.sleep(.01)
        start = time.monotonic()
        health = control.get("/healthz")
        listing = actor.get("/screening/batches")
        elapsed = time.monotonic() - start
        checks.check("paused upload permits health and authorized read within one second",
            health.status_code == listing.status_code == 200 and elapsed <= 1,
            f"two_requests_seconds={elapsed:.4f}; budget=1.0000")
    (scratch / "body-checks-armed").unlink()
    # Whitespace is part of the HTTP body, even though JSON ignores it.
    raw = json.dumps({"name": "Exact body budget", "items": [{"resume_text": "Python"}]}).encode()
    exact = raw + b" " * (cap - len(raw))
    accepted = require(actor.post("/screening/batches", content=exact,
        headers={"Content-Type": "application/json"}))
    checks.check("exact-byte request budget accepts ordinary intake after refusals/disconnect",
        accepted["name"] == "Exact body budget" and accepted["counts"]["pending"] == 1)
    path = "/screening/batches/" + accepted["id"]
    return path, require(actor.get(path))


def check_pdf_execution(checks, scratch, base, control, actor):
    from tests.pdf_helpers import resume_pdf
    def require(response):
        assert response.status_code == 200, (response.request.url.path, response.status_code)
        return response.json()
    candidate = require(control.post('/candidates', json={'resume_text': 'Synthetic PDF portal', 'evaluate': False}))
    key = require(control.post(f"/candidates/{candidate['candidate_id']}/auth-key"))['access_key']
    pdf = resume_pdf('Python SQL synthetic PDF intake')
    accepted_path = None
    with client(base, headers={'X-Candidate-Key': key}) as portal:
        for path, caller in (('/evaluate', control), ('/candidates', control),
                ('/screening/candidates', actor), ('/screening/batches', actor), ('/portal/documents', portal)):
            (scratch / 'pdf-entered').unlink(missing_ok=True)
            (scratch / 'pdf-release').unlink(missing_ok=True)
            (scratch / 'pdf-mode').write_text('stall')
            payload = {'resume_pdf_b64': pdf}
            if path.endswith('/batches'):
                payload = {'name': 'Bounded PDF intake', 'items': [payload, payload]}
            elif path.endswith('/documents'):
                payload = {'doc_type': 'experience_letter', 'content_b64': pdf}
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(caller.post, path, json=payload)
                try:
                    deadline = time.monotonic() + 8
                    while not (scratch / 'pdf-entered').exists():
                        assert time.monotonic() < deadline, 'PDF child did not reach controlled stall'
                        time.sleep(.01)
                    started = time.monotonic()
                    health, listing = control.get('/healthz'), actor.get('/screening/batches')
                    elapsed = time.monotonic() - started
                    checks.check(f'{path}: health plus authorized read finish during PDF stall',
                        health.status_code == listing.status_code == 200 and elapsed <= 1,
                        f'two_requests_seconds={elapsed:.4f}; budget=1.0000')
                    before = listing.json()
                    refused = actor.post('/screening/batches', json={'items': [
                        {'resume_text': 'Validated before busy item'}, {'resume_pdf_b64': pdf}]})
                    checks.check(f'{path}: shared capacity refuses with no partial registration',
                        refused.status_code == 503 and refused.json() == {'detail': 'pdf_capacity_exhausted'}
                        and refused.headers.get('retry-after') == '1'
                        and require(actor.get('/screening/batches')) == before)
                finally:
                    (scratch / 'pdf-release').touch()
                saved = require(pending.result(timeout=15))
                checks.check(f'{path}: held valid PDF completes after release',
                    bool(saved) and (not path.endswith('/batches') or saved['counts']['pending'] == 2))
                if path.endswith('/batches'):
                    accepted_path = '/screening/batches/' + saved['id']
            (scratch / 'pdf-mode').unlink()
        for mode, value in (('timeout', pdf), ('error', pdf), ('invalid', 'not-base64')):
            before = require(actor.get('/screening/batches'))
            (scratch / 'pdf-release').unlink(missing_ok=True)
            (scratch / 'pdf-mode').write_text(mode)
            if mode == 'invalid':
                (scratch / 'pdf-release').touch()
            response = actor.post('/screening/batches', json={'items': [
                {'resume_pdf_b64': pdf if mode == 'invalid' else value}, {'resume_pdf_b64': value}]})
            (scratch / 'pdf-mode').unlink()
            checks.check(f'{mode}: PDF refusal is safe and atomic', response.status_code == 422
                and 'pdf_parse_failed' in response.json()['detail']
                and 'private-pdf-smoke-sentinel' not in response.text
                and require(actor.get('/screening/batches')) == before)
            checks.check(f'{mode}: valid PDF immediately recovers capacity',
                actor.post('/screening/batches', json={'items': [{'resume_pdf_b64': pdf}]}).status_code == 200)
    return accepted_path, require(actor.get(accepted_path))


def run(scratch, url, pg_options):
    batch_recovery = '--batch-recovery-workers' in sys.argv
    batch_admissions = '--batch-admission-workers' in sys.argv or batch_recovery
    batch_management = '--batch-management' in sys.argv
    batch_mutations = batch_management or '--batch-mutation-workers' in sys.argv
    batch_registrations = batch_management or '--batch-registration-workers' in sys.argv
    batch_reads = batch_management or '--batch-read-workers' in sys.argv
    pdf_execution = '--pdf-execution' in sys.argv
    body_limit = "--body-limit" in sys.argv
    ingest_races = "--ingest-races" in sys.argv
    persistence = "--persistence" in sys.argv
    expiry = "--expiry" in sys.argv or persistence
    terminal_outcomes = "--outcomes" in sys.argv or expiry
    leases = "--leases" in sys.argv or terminal_outcomes or ingest_races or batch_admissions
    cap = 2 if leases else 1
    print(f"Synthetic screening HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R4-S2-T3C3D5B batch recovery / two processes / restart" if batch_recovery
                   else "R4-S2-T3C3D5A batch admission / two processes / restart" if batch_admissions
                   else "R4-S2-T3C3D4Q combined batch management / HTTP / restart" if batch_management
                   else "R4-S2-T3B bounded PDF execution / HTTP / restart" if pdf_execution
                   else "R4-S2-T3A aggregate request body limits / HTTP / restart" if body_limit
                   else "R4-S2-T2 candidate/resume ingest races / two workers / restart" if ingest_races
                   else "R4-S2-T1B2b2b authorized report recovery / two workers / restart" if persistence
                   else "R4-S2-T1B2a terminal expiry / two workers / graceful restart" if expiry
                   else "R4-S2-T1B1 terminal outcomes / two workers / graceful restart" if terminal_outcomes
                   else "R4-S2-T1A two-worker leases / screening HTTP / graceful restart" if leases
                   else "R4-S1-T3D screening HTTP and graceful restart")
    stop, events, mailbox = scratch / "stop", scratch / "lifecycle.jsonl", scratch / "mail.jsonl"
    env = {key: value for key, value in base_env().items() if not key.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
        "DEE_CANDIDATES_DB_URL": url, "PGOPTIONS": pg_options,
        "DEE_DB_MIGRATE_ON_BOOT": "true", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_SPEECH_PROVIDER": "local",
        "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "DEE_CORS_ALLOWED_ORIGINS": json.dumps([contract.UI_ORIGIN]),
        "DEE_SCREENING_MAX_ITEMS_PER_CALL": str(cap),
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": "smoke_r4_s1_t3d:create_batch_admission_smoke_app" if batch_admissions else "smoke_r4_s1_t3d:create_batch_management_smoke_app" if batch_management else "smoke_r4_s1_t3d:create_batch_mutation_smoke_app" if batch_mutations else "smoke_r4_s1_t3d:create_batch_registration_smoke_app" if batch_registrations else "smoke_r4_s1_t3d:create_batch_read_smoke_app" if batch_reads else "smoke_r4_s1_t3d:create_smoke_app" if leases or body_limit or pdf_execution else "smoke_r4_s1_t1a:create_smoke_app",
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    if batch_admissions:
        env.update(DEE_BATCH_ADMISSION_MAX_CONCURRENT_REQUESTS='1', DEE_BATCH_ADMISSION_WAIT_SECONDS='.5',
            DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600')
    if batch_registrations:
        env.update(DEE_BATCH_REGISTRATION_MAX_CONCURRENT_REQUESTS='1', DEE_BATCH_REGISTRATION_WAIT_SECONDS='.5',
            DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600')
    if batch_mutations:
        env.update(DEE_BATCH_MUTATION_MAX_CONCURRENT_REQUESTS='1', DEE_BATCH_MUTATION_WAIT_SECONDS='.5',
            DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600')
    if batch_reads:
        env.update(DEE_BATCH_READ_MAX_CONCURRENT_REQUESTS='1', DEE_BATCH_READ_WAIT_SECONDS='.5',
            DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600')
    if body_limit:
        env.update(DEE_MAX_REQUEST_BODY_BYTES="64000", VERITAS_BODY_LIMIT_SMOKE="true")
    if pdf_execution:
        env.update(DEE_PDF_MAX_CONCURRENT_PARSES='1', DEE_PDF_PARSE_TIMEOUT_SECONDS='4',
                   VERITAS_PDF_EXECUTION_SMOKE='true')
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    contract.BASE = base

    @contextmanager
    def server(server_port=port, stop_path=stop):
        stop_path.unlink(missing_ok=True)
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(server_port), str(stop_path)],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                server_base = f"http://127.0.0.1:{server_port}"
                with client(server_base) as health:
                    assert wait_healthy(health), "scratch screening app failed to start"
                yield server_base
            finally:
                stop_path.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("scratch screening app failed graceful shutdown")
                assert proc.returncode == 0, "scratch screening app failed during lifespan"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def evaluations(text):
        digest = sha256(text.encode("utf-8")).hexdigest()
        return sum(json.loads(path.read_text(encoding="utf-8"))["sha256"] == digest
                   for path in scratch.glob("evaluated-*.json"))

    def ingestions(candidate_id):
        return sum(json.loads(path.read_text(encoding="utf-8"))["candidate_id"] == candidate_id
                   for path in scratch.glob("ingested-*.json"))

    def login(http, email, name):
        require(http.post("/auth/org/signup", json={"email": email, "organization_name": name}), 202)
        session = require(http.post("/auth/org/verify", json={"email": email, "code": _code_for(mailbox, email)}))
        http.headers["X-CSRF-Token"] = session["csrf_token"]
        return session

    def public_ui():
        with client(base) as page:
            entry = page.get("/ui/")
            for name in ("evaluation-report.js", "screening.js"):
                module = page.get(f"/ui/{name}")
                checks.check(f"anonymous UI delivers its declared {name} module",
                    entry.status_code == module.status_code == 200
                    and f'<script src="./{name}"></script>' in entry.text
                    and module.content == (ROOT / "frontend" / name).read_bytes()
                    and "javascript" in module.headers["content-type"]
                    and page.get("/ui/not-an-asset.txt").status_code == 404)

    with client(base, headers={"X-API-Key": ADMIN}) as control, client(base) as actor, client(base) as other:
        with server():
            public_ui()
            contract.run_checks(mailbox)
            checks.check("reused UI HTTP contract passes", contract.S.summary() == 0)
            login(actor, "screening-router-a@example.in", "Screening Router A")
            login(other, "screening-router-b@example.in", "Screening Router B")
            if body_limit:
                body_path, body_saved = check_request_body_limit(checks, scratch, base, control, actor)
            if pdf_execution:
                pdf_path, pdf_saved = check_pdf_execution(checks, scratch, base, control, actor)
            text = contract._resume("Synthetic Screening Router", "screening-intake@example.in")
            uploaded = require(actor.post("/screening/candidates", json={"resume_text": text}))
            rid, cid = uploaded["report"]["id"], uploaded["candidate_id"]
            report_path = f"/screening/reports/{rid}"
            checks.check("single intake keeps advisory report and scoped candidate reads", uploaded["report"]["advisory"]
                and uploaded["report"]["human_review_required"]
                and [row["id"] for row in require(actor.get(f"/screening/candidates/{cid}/reports"))] == [rid]
                and require(other.get(f"/screening/candidates/{cid}/reports")) == [])
            require(control.post(f"/report/{rid}/outcome", json={"outcome": "inconclusive", "notes": "Internal operator note"}))
            checks.check("operator note remains private", require(actor.get(report_path + "/outcomes"))["outcomes"] == [])
            require(actor.post(report_path + "/outcome", json={"outcome": "candidate_clarified", "notes": "Named human reviewer"}))
            outcomes = require(actor.get(report_path + "/outcomes"))["outcomes"]
            checks.check("cookie reviewer provenance survives write/read", len(outcomes) == 1 and bool(outcomes[0]["recorded_by_org_user_id"])
                and outcomes[0]["recorded_by"] == "organization")
            checks.check("other tenant report and outcome doors remain absent", all(other.get(report_path + suffix).status_code == 404 for suffix in ("", "/outcomes"))
                and other.post(report_path + "/outcome", json={"outcome": "inconclusive"}).status_code == 404)
            created = require(actor.post("/screening/batches", json={"name": "Restarted screening", "items": [
                {"resume_text": text + f"\nUpdated availability {i}."} for i in range(cap + 1)]}))
            bid, path = created["id"], f"/screening/batches/{created['id']}"
            checks.check("batch registration records the same named human", created["created_by_org_user_id"] == outcomes[0]["recorded_by_org_user_id"]
                and created["counts"]["pending"] == cap + 1)
            first = require(actor.post(path + "/process"))
            checks.check("processing respects configured item bound", first["processed"] == cap and first["remaining"] == 1)
            require(actor.post(path + "/process"))
            checks.check("successful items are not replayed by retry", require(actor.post(path + "/retry")) == {"batch_id": bid, "requeued": 0, "skipped": 0})
            admissions = (check_batch_recovery if batch_recovery else check_batch_admission)(checks, scratch, control, actor, other, server) if batch_admissions else []
            neighbours = check_batch_management_isolation(checks, scratch, control, actor, other, path) if batch_management else []
            registrations = check_batch_registration(checks, scratch, control, actor, other) if batch_registrations else []
            mutations = check_batch_mutations(checks, scratch, control, actor, other) if batch_mutations else []
            batch_views = check_batch_reads(checks, scratch, control, actor, other, path) if batch_reads else []
            if batch_management:
                registrations, neighbours = check_combined_erasure_fence(checks, scratch, actor, other, registrations, neighbours)
            saved = {suffix: require(actor.get(path + suffix)) for suffix in ("", "/queue", "/summary")}
            saved_report = require(actor.get(report_path))
            checks.check("completed queue and summary remain advisory", saved[""]["counts"]["done"] == cap + 1
                and saved["/summary"]["n_screened"] == cap + 1 and all(row["advisory"] and row["human_review_required"] for row in saved["/queue"]["rows"]))
            if leases:
                org = require(control.post("/ledger/orgs", json={"name": "Two process lease worker"}))
                headers = {"X-Org-Key": org["api_key"]}
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0)); worker_port = sock.getsockname()[1]
                with server(worker_port, scratch / "stop-worker") as worker_base:
                    with client(base, headers=headers) as worker_a, client(worker_base, headers=headers) as worker_b:
                        if ingest_races:
                            ingest_saved = check_ingest_races(checks, scratch, control, worker_a, worker_b)
                        batch = require(worker_b.post("/screening/batches", json={"name": "Concurrent lease intake", "items": [
                            {"resume_text": contract._resume(f"Lease candidate {i}", f"lease-worker-{i}@example.com")
                             + "\nR4-S2-T1A slow fake gate"} for i in range(3)]}))
                        lease_path = "/screening/batches/" + batch["id"]
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            pending = executor.submit(worker_a.post, lease_path + "/process")
                            try:
                                deadline = time.monotonic() + 15
                                while not (scratch / "lease-entered").exists():
                                    assert time.monotonic() < deadline, "first worker never reached provider gate"
                                    time.sleep(.05)
                                counts = require(worker_b.get(lease_path))["counts"]
                                checks.check("waiting worker leases only its active item", counts["processing"] == 1 and counts["pending"] == 2)
                                second = require(worker_b.post(lease_path + "/process"))
                                checks.check("second app process consumes unstarted work within its own cap",
                                    (second["processed"], second["failed"], second["remaining"]) == (2, 0, 1))
                                checks.check("retry does not replay active or completed work",
                                    require(worker_b.post(lease_path + "/retry"))["requeued"] == 0)
                            finally:
                                (scratch / "lease-release").write_text("release", encoding="utf-8")
                            first_worker = require(pending.result(timeout=30))
                        checks.check("first worker commits only its own item after provider release",
                            (first_worker["processed"], first_worker["failed"], first_worker["remaining"]) == (1, 0, 0))
                        lease_saved = {suffix: require(worker_b.get(lease_path + suffix)) for suffix in ("", "/queue", "/summary")}
                        checks.check("two processes persist exactly three advisory queue results",
                            lease_saved[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":3}
                            and len({row["report_id"] for row in lease_saved["/queue"]["rows"]}) == 3
                            and lease_saved["/summary"]["n_screened"] == 3
                            and all(row["advisory"] and row["human_review_required"] for row in lease_saved["/queue"]["rows"]))
                        checks.check("another tenant cannot read or process worker intake", other.get(lease_path).status_code == 404
                            and other.post(lease_path + "/process").status_code == 404)
                        outcome_saved, recovery_restart = {}, None
                        if terminal_outcomes:
                            modes = ["stolen", "erased"] + (["expired"] if expiry else [])
                            if persistence:
                                modes += ["input-expired", "report-expired", "restart"]
                            expired_modes = {"expired", "input-expired", "report-expired", "restart"}
                            for mode in modes:
                                resume_text = contract._resume(f"Outcome {mode}", f"outcome-{mode}@example.com")
                                batch = require(worker_b.post("/screening/batches", json={"name": f"Terminal {mode}", "items": [{
                                    "resume_text": resume_text }]}))
                                outcome_path = "/screening/batches/" + batch["id"]
                                (scratch / "outcome-mode").write_text(mode, encoding="utf-8")
                                with ThreadPoolExecutor(max_workers=1) as executor:
                                    pending = executor.submit(worker_a.post, outcome_path + "/process")
                                    try:
                                        entered = scratch / f"outcome-entered-{mode}.json"
                                        deadline = time.monotonic() + 15
                                        while True:
                                            assert time.monotonic() < deadline, "worker never reached persistence gate"
                                            try:
                                                subject = json.loads(entered.read_text(encoding="utf-8"))
                                                break
                                            except (FileNotFoundError, PermissionError):
                                                # Windows can expose a renamed gate before its
                                                # writer releases the transient sharing lock.
                                                time.sleep(.05)
                                        if mode in {"stolen", "expired", "restart"}:
                                            subject["saved_report"] = require(worker_b.get(f"/screening/reports/{subject['report_id']}"))
                                        if mode == "stolen" or mode in expired_modes:
                                            (scratch / "outcome-advanced").write_text("advance", encoding="utf-8")
                                            if mode == "stolen":
                                                winner = require(worker_b.post(outcome_path + "/process"))
                                                checks.check("replacement worker alone acknowledges completion",
                                                    (winner["processed"], winner["failed"], winner["remaining"]) == (1, 0, 0))
                                        else:
                                            erased = require(worker_b.delete(f"/candidates/{subject['candidate_id']}", headers={"X-API-Key": ADMIN}))
                                            checks.check("second app erases subject before terminal write", erased["deleted"])
                                    finally:
                                        (scratch / f"outcome-release-{mode}").write_text("release", encoding="utf-8")
                                    loser = require(pending.result(timeout=30))
                                (scratch / "outcome-mode").unlink()
                                state = {suffix: require(worker_b.get(outcome_path + suffix)) for suffix in ("", "/queue", "/summary")}
                                row = state["/queue"]["rows"][0]
                                checks.check(f"{mode}: response counts only this call's acknowledged transitions",
                                    (loser["processed"], loser["failed"], loser["remaining"]) == (0, int(mode == "erased"), int(mode in expired_modes)))
                                if mode in expired_modes:
                                    if mode == "input-expired":
                                        checks.check("expired ingest rolls back its subject through HTTP",
                                            control.get(f"/candidates/{subject['candidate_id']}").status_code == 404)
                                    elif mode == "report-expired":
                                        checks.check("expired report rolls back while earlier subject survives",
                                            control.get(f"/candidates/{subject['candidate_id']}").status_code == 200
                                            and worker_b.get(f"/screening/reports/{subject['report_id']}").status_code == 404)
                                    checks.check(f"{mode}: expired attempt stays pending without public result links",
                                        row["status"] == "pending" and row["error"] is None
                                        and row["candidate_id"] is row["resume_id"] is row["report_id"] is row["signals"] is None
                                        and state[""]["counts"] == {"pending":1, "processing":0, "failed":0, "done":0}
                                        and state["/summary"]["n_screened"] == 0)
                                    if mode == "restart":
                                        recovery_restart = outcome_path, subject, resume_text
                                    else:
                                        recovered = require(worker_b.post(outcome_path + "/process"))
                                        checks.check("later request recovers expired work using retained input",
                                            (recovered["processed"], recovered["failed"], recovered["remaining"]) == (1, 0, 0))
                                        state = {suffix: require(worker_b.get(outcome_path + suffix)) for suffix in ("", "/queue", "/summary")}
                                        row = state["/queue"]["rows"][0]
                                        checks.check(f"{mode}: recovery commits expected subject and exactly one queue result",
                                            (row["candidate_id"] != subject["candidate_id"] if mode == "input-expired"
                                             else row["candidate_id"] == subject["candidate_id"]) and row["status"] == "done"
                                            and state[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":1}
                                            and state["/summary"]["n_screened"] == 1)
                                if mode != "restart": (scratch / "outcome-advanced").unlink(missing_ok=True)
                                if mode in {"stolen", "expired", "report-expired"}:
                                    checkpoint = json.loads((scratch / f"checkpoint-{row['report_id']}.json").read_text(encoding="utf-8"))
                                    checks.check(f"{mode}: original private matching facts and TTL survive recovery",
                                        checkpoint == {key: subject[key] for key in ("ingest_facts", "input_created_at")}
                                        and checkpoint["ingest_facts"] == {"version":1, "matched_existing":False,
                                            "matched_on":None, "duplicate_resume":False})
                                checks.check(f"{mode}: private ingest checkpoint never enters public batch reads",
                                    "ingest_facts" not in json.dumps(state) and "input_created_at" not in json.dumps(state))
                                if mode == "stolen":
                                    checks.check("stale completion cannot overwrite recovered report or saved counts",
                                        row["status"] == "done" and row["report_id"] == subject["report_id"]
                                        and state[""]["counts"] == {"pending":0, "processing":0, "failed":0, "done":1})
                                elif mode == "erased":
                                    checks.check("acknowledged erasure failure has no subject links or signals",
                                        row["status"] == "failed" and row["error"] == "candidate_erased"
                                        and row["candidate_id"] is row["resume_id"] is row["report_id"] is row["signals"] is None
                                        and state[""]["counts"] == {"pending":0, "processing":0, "failed":1, "done":0})
                                if mode in {"stolen", "expired"}:
                                    checks.check(f"{mode}: reuse preserves report/body/original facts without provider or ingest replay",
                                        row["report_id"] == subject["report_id"]
                                        and require(worker_b.get(f"/screening/reports/{row['report_id']}")) == subject["saved_report"]
                                        and all(row["signals"][key] == subject["ingest_facts"][key] for key in (
                                            "matched_existing", "matched_on", "duplicate_resume"))
                                        and evaluations(resume_text) == ingestions(subject["candidate_id"]) == 1
                                        and len(require(worker_b.get(f"/screening/candidates/{row['candidate_id']}/reports"))) == 1)
                                elif mode in {"input-expired", "report-expired"}:
                                    checks.check(f"{mode}: pre-checkpoint provider cost is distinct from one persisted report",
                                        evaluations(resume_text) == (2 if mode == "report-expired" else 1)
                                        and len(require(worker_b.get(f"/screening/candidates/{row['candidate_id']}/reports"))) == 1)
                                checks.check(f"{mode}: retries do not replay settled or scrubbed input",
                                    require(worker_b.post(outcome_path + "/retry")) == {"batch_id":batch["id"], "requeued":0, "skipped":int(mode == "erased")}
                                    and (mode == "restart" or require(worker_b.post(outcome_path + "/process"))["processed"] == 0)
                                    and row["advisory"] and row["human_review_required"]
                                    and other.get(outcome_path + "/queue").status_code == 404)
                                outcome_saved[outcome_path] = state
        with server():
            public_ui()
            if batch_admissions:
                checks.check('late admission recovery survives graceful restart without foreign visibility',
                    all(require(actor.get(target + suffix)) == body and other.get(target + suffix).status_code == 404
                        for target, views in admissions for suffix, body in views.items()))
            if batch_management:
                checks.check('both tenants retain exact blocked registrations across combined graceful restart',
                    all((actor if owner == 'actor' else other).get(url).json() == body
                        for owner, url, body in neighbours))
            if batch_mutations:
                checks.check('all late mutation results survive graceful restart with tenant isolation',
                    all(actor.get(url).status_code == status and require(actor.get(url), status) == body
                        and other.get(url).status_code == 404 for url, status, body in mutations))
            if batch_registrations:
                checks.check('late registration commit and rollback survive graceful restart without processing',
                    all(actor.get(url).status_code == status and require(actor.get(url), status) == body
                        and other.get(url).status_code == 404 for url, status, body in registrations))
            if batch_reads:
                checks.check('exact scoped batch views and erased projection survive graceful restart',
                    all(require(actor.get(url)) == body for url, body in batch_views))
            if pdf_execution:
                checks.check('PDF intake persists with tenant isolation after graceful restart',
                    require(actor.get(pdf_path)) == pdf_saved and other.get(pdf_path).status_code == 404)
            if body_limit:
                checks.check("exact-boundary intake and response persist after graceful restart",
                    require(actor.get(body_path)) == body_saved
                    and other.get(body_path).status_code == 404)
            if ingest_races:
                checks.check("exact concurrent candidate/resume state survives graceful app restart",
                    all(require(control.get(path)) == body for path, body in ingest_saved.items()))
            if leases:
                with client(base, headers=headers) as worker:
                    checks.check("exact concurrent queue and counters survive graceful app restart",
                        all(require(worker.get(lease_path + suffix)) == body for suffix, body in lease_saved.items())
                        and require(worker.post(lease_path + "/process"))["processed"] == 0
                        and require(worker.post(lease_path + "/retry"))["requeued"] == 0)
                    if terminal_outcomes:
                        checks.check("terminal outcomes and exact saved queue summaries survive graceful restart",
                            all(require(worker.get(path + suffix)) == body for path, state in outcome_saved.items() for suffix, body in state.items()))
                    if recovery_restart is not None:
                        restart_path, subject, resume_text = recovery_restart
                        try:
                            recovered = require(worker.post(restart_path + "/process"))
                            state = {suffix: require(worker.get(restart_path + suffix)) for suffix in ("", "/queue", "/summary")}
                            row = state["/queue"]["rows"][0]
                            checks.check("pending report checkpoint recovers after app restart with exact original result and counts",
                                (recovered["processed"], recovered["failed"], recovered["remaining"]) == (1,0,0)
                                and row["report_id"] == subject["report_id"]
                                and require(worker.get(f"/screening/reports/{row['report_id']}")) == subject["saved_report"]
                                and all(row["signals"][key] == subject["ingest_facts"][key] for key in (
                                    "matched_existing", "matched_on", "duplicate_resume"))
                                and state["/summary"]["n_screened"] == 1 and state[""]["counts"]["done"] == 1
                                and evaluations(resume_text) == ingestions(subject["candidate_id"]) == 1)
                            checks.check("recovered checkpoint cannot replay after restart",
                                require(worker.post(restart_path + "/process"))["processed"] == 0
                                and require(worker.post(restart_path + "/retry"))["requeued"] == 0)
                        finally: (scratch / "outcome-advanced").unlink(missing_ok=True)
            checks.check("cookie session and exact batch queue summary survive restart", all(require(actor.get(path + suffix)) == body for suffix, body in saved.items()))
            checks.check("report and employer judgments survive restart exactly", require(actor.get(report_path)) == saved_report
                and require(actor.get(report_path + "/outcomes"))["outcomes"] == outcomes)
            checks.check("tenant isolation survives restart on all batch doors", all(other.get(path + suffix).status_code == 404 for suffix in ("", "/queue", "/summary"))
                and all(other.post(path + suffix).status_code == 404 for suffix in ("/process", "/retry")) and other.delete(path).status_code == 404)
            checks.check("malformed cursors still return 422", all(actor.get(target, params={"cursor": "!!!"}).status_code == 422 for target in ("/screening/batches", path + "/queue")))
            csrf = actor.headers.pop("X-CSRF-Token")
            checks.check("persisted cookie still requires CSRF for writes", actor.delete(path).status_code == 403
                and actor.post(path + "/process").status_code == 403)
            actor.headers["X-CSRF-Token"] = csrf
            checks.check("owner can delete batch after restart", require(actor.delete(path)) == {"batch_id": bid, "deleted": True}
                and actor.get(path).status_code == 404 and actor.get(report_path).status_code == 200)
    lifecycle = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    starts = (3 if leases else 2) + len(admissions)
    checks.check("all migrated workers share SQL topology and shut down gracefully", sum(row["event"] == "started" and row["revision"] == "0030_screening_ingest_facts" and row["one_factory"] for row in lifecycle) == starts
        and sum(row["event"] == "disposed" for row in lifecycle) == starts
        and sum(row["event"] == "stopped" and row["detached"] for row in lifecycle) == starts)
    return checks.summary()


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r4-s2-t3b-" if "--pdf-execution" in sys.argv else "r4-s2-t3a-" if "--body-limit" in sys.argv else "r4-s2-t2-" if "--ingest-races" in sys.argv else "r4-s2-t1b2b2b-" if "--persistence" in sys.argv else "r4-s2-t1b2a-" if "--expiry" in sys.argv else "r4-s2-t1b1-" if "--outcomes" in sys.argv else "r4-s2-t1a-" if "--leases" in sys.argv else "r4-s1-t3d-"))
    with database(scratch) as (url, pg_options):
        return run(scratch, url, pg_options)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
