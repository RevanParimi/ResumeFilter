"""Candidate area: migrated scratch HTTP, shared employer intake and restart.

Reuses the fake-provider production SQL composition and graceful server loop.
No working data, external provider calls or existing demo restart.
"""

import asyncio
from contextlib import contextmanager, asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from threading import get_ident, local

from _smoke import Smoke, base_env, client, wait_healthy
from smoke_r4_s1_t1a import serve
from smoke_s62 import _export_b64
from smoke_s82 import _code_for
from smoke_r1_s1_t3a_v1 import database


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-candidate-router-admin"
RESUME = "Synthetic Candidate Router\nEmail: candidate-router@example.in\n" + "\n".join(
    (ROOT / "tests/fixtures/genuine_genai_resume.txt").read_text(encoding="utf-8").splitlines()[1:]
)


def create_candidate_fingerprint_smoke_app():
    return create_candidate_ingest_smoke_app(fingerprint=True)


def create_candidate_report_smoke_app():
    return create_candidate_ingest_smoke_app(report_sql=True)


def create_candidate_ingest_smoke_app(*, fingerprint=False, report_sql=False):
    """Hold initial ingest or fingerprint work in the scratch application."""
    from sqlalchemy import event
    from app.candidates.models import FingerprintRow
    from app.fabrication import similarity
    from smoke_r4_s1_t1a import create_smoke_app
    app = create_smoke_app()
    from app.screening import ingest as pipeline
    original = app.router.lifespan_context
    scratch = Path(os.environ['VERITAS_SQL_SMOKE_EVENTS']).parent
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            services = app.state.services
            ingest, now = services.candidates.ingest, services.screening._now
            farm, compute, compare = pipeline._assess_ingest_farm, similarity.fingerprint_text, services.candidates.similar_resumes
            guard, report_save, report_get = services.candidates.require_ingest_subject, services.report_store.save, services.report_store.get
            evaluate, caller = app.state.engine.evaluate, get_ident()
            state, guard_calls = local(), {}
            if report_sql:
                (scratch / 'ingest-operations.jsonl').touch(exist_ok=True)
                (scratch / 'ingest-evaluations.jsonl').touch(exist_ok=True)
            def hold():
                (scratch / 'ingest-entered').touch()
                deadline = time.monotonic() + 20
                while not (scratch / 'ingest-release').exists():
                    assert time.monotonic() < deadline, 'synthetic fingerprint gate timed out'
                    time.sleep(.01)
            def mode():
                path = scratch / 'ingest-mode'
                return path.read_text() if path.exists() else None
            def controlled_compute(*args, **kwargs):
                if mode() == 'compute':
                    hold()
                return compute(*args, **kwargs)
            def controlled_compare(*args, **kwargs):
                result = compare(*args, **kwargs)
                if mode() == 'compare':
                    hold()
                return result
            def flushed(session, context):
                if mode() == 'save' and any(isinstance(row, FingerprintRow) for row in session.new):
                    hold()
            def controlled_farm(*args, **kwargs):
                with (scratch / 'ingest-operations.jsonl').open('a') as log:
                    log.write(json.dumps({'thread': get_ident()}) + '\n')
                held = mode() is not None
                try:
                    return farm(*args, **kwargs)
                finally:
                    if held:
                        (scratch / 'ingest-completed').touch()
            def report_sql_gate(conn, cursor, statement, parameters, context, many):
                operation = getattr(state, 'operation', None)
                target = operation != 'save' or statement.lstrip().upper().startswith('INSERT INTO REPORTS')
                if target and mode() == operation and mode() is not None and not state.held:
                    state.held = True
                    with (scratch / 'ingest-operations.jsonl').open('a') as log:
                        log.write(json.dumps({'thread': get_ident(), 'phase': state.operation}) + '\n')
                    hold()
            def controlled_guard(*args):
                guard_calls[args] = guard_calls.get(args, 0) + 1
                state.operation, state.held = ('pre' if guard_calls[args] == 1 else None), False
                try:
                    return guard(*args)
                finally:
                    if state.held:
                        (scratch / 'ingest-completed').touch()
                    state.operation = None
            def controlled_report_save(report, **kwargs):
                state.operation, state.held = 'save', False
                if mode() == 'save':
                    (scratch / 'ingest-report.json').write_text(json.dumps({'id': report.id}))
                try:
                    return report_save(report, **kwargs)
                finally:
                    if state.held:
                        (scratch / 'ingest-completed').touch()
                    state.operation = None
            def controlled_report_get(*args):
                state.operation, state.held = 'publication', False
                if mode() == 'publication':
                    (scratch / 'ingest-report.json').write_text(json.dumps({'id': args[0]}))
                try:
                    return report_get(*args)
                finally:
                    if state.held:
                        (scratch / 'ingest-completed').touch()
                    state.operation = None
            async def controlled_evaluate(**kwargs):
                assert get_ident() == caller, 'async evaluation moved off its caller'
                report = await evaluate(**kwargs)
                with (scratch / 'ingest-evaluations.jsonl').open('a') as log:
                    log.write(json.dumps({'id': report.id, 'thread': get_ident()}) + '\n')
                return report
            def controlled_now():
                offset = services.settings.screening_claim_timeout_seconds + 1 if (scratch / 'ingest-advanced').exists() else 0
                return now() + timedelta(seconds=offset)
            def controlled_ingest(*args, **kwargs):
                if fingerprint or report_sql:
                    outcome = ingest(*args, **kwargs)
                    (scratch / 'ingest-outcome.json').write_text(json.dumps(outcome.model_dump()))
                    guard_calls[(outcome.candidate_id, outcome.resume_id)] = 0
                    return outcome
                with (scratch / 'ingest-operations.jsonl').open('a') as log:
                    log.write(json.dumps({'thread': get_ident()}) + '\n')
                mode = scratch / 'ingest-mode'
                held = mode.exists()
                if held:
                    callback = kwargs.get('before_commit')
                    def checkpoint(session, outcome):
                        if callback is not None:
                            callback(session, outcome)
                        (scratch / 'ingest-outcome.json').write_text(json.dumps(outcome.model_dump()))
                        (scratch / 'ingest-entered').touch()
                        deadline = time.monotonic() + 20
                        while not (scratch / 'ingest-release').exists():
                            assert time.monotonic() < deadline, 'synthetic ingest SQL gate timed out'
                            time.sleep(.01)
                    kwargs['before_commit'] = checkpoint
                try:
                    return ingest(*args, **kwargs)
                finally:
                    if held:
                        (scratch / 'ingest-completed').touch()
            def owner(session, transaction, connection):
                assert session.info.setdefault('ingest_owner', get_ident()) == get_ident()
            def end(session, transaction):
                assert session.info.get('ingest_owner', get_ident()) == get_ident()
            services.candidates.ingest, services.screening._now = controlled_ingest, controlled_now
            if fingerprint:
                pipeline._assess_ingest_farm = controlled_farm
                similarity.fingerprint_text, services.candidates.similar_resumes = controlled_compute, controlled_compare
                event.listen(services.session_factory, 'after_flush', flushed)
            if report_sql:
                services.candidates.require_ingest_subject = controlled_guard
                services.report_store.save, services.report_store.get = controlled_report_save, controlled_report_get
                app.state.engine.evaluate = controlled_evaluate
                event.listen(services.session_factory.kw['bind'], 'before_cursor_execute', report_sql_gate)
            event.listen(services.session_factory, 'after_begin', owner)
            event.listen(services.session_factory, 'after_transaction_end', end)
            try:
                yield
            finally:
                services.candidates.ingest, services.screening._now = ingest, now
                if fingerprint:
                    pipeline._assess_ingest_farm = farm
                    similarity.fingerprint_text, services.candidates.similar_resumes = compute, compare
                    event.remove(services.session_factory, 'after_flush', flushed)
                if report_sql:
                    services.candidates.require_ingest_subject = guard
                    services.report_store.save, services.report_store.get = report_save, report_get
                    app.state.engine.evaluate = evaluate
                    event.remove(services.session_factory.kw['bind'], 'before_cursor_execute', report_sql_gate)
                event.remove(services.session_factory, 'after_begin', owner)
                event.remove(services.session_factory, 'after_transaction_end', end)
    app.router.lifespan_context = lifespan
    return app


def check_candidate_ingests(checks, scratch, control, operator, org_a, org_b, *, fingerprint=False, report_sql=False):
    saved = {}
    for door, actor in [('admin', operator), ('org', org_a), ('batch', org_a)]:
        phase = {'admin': 'compute', 'org': 'save', 'batch': 'compare'}[door] if fingerprint else 'initial write'
        if report_sql:
            phase = {'admin': 'pre', 'org': 'save', 'batch': 'publication'}[door]
        text = RESUME.replace('candidate-router@example.in', f'ingest-{door}@example.in')
        path, body = ('/candidates' if door == 'admin' else '/screening/candidates'), {'resume_text': text}
        batch = None
        if door == 'batch':
            batch = actor.post('/screening/batches', json={'name': 'Uncertain ingest', 'items': [{'resume_text': text}]}).json()['id']
            path, body = f'/screening/batches/{batch}/process', None
        for name in ('ingest-entered', 'ingest-release', 'ingest-completed'):
            (scratch / name).unlink(missing_ok=True)
        operations = scratch / 'ingest-operations.jsonl'
        before = len(operations.read_text().splitlines())
        (scratch / 'ingest-mode').write_text(phase)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(actor.post, path, json=body)
            try:
                deadline = time.monotonic() + 10
                while not (scratch / 'ingest-entered').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                start = time.monotonic()
                checks.check(door + ': held ' + phase + ' leaves health and admitted read responsive',
                    control.get('/healthz').status_code == control.get('/admin/users').status_code == 200
                    and time.monotonic() - start < 1, f'{time.monotonic() - start:.4f}s')
                for url, peer in [('/candidates', operator), ('/screening/candidates', org_b)]:
                    busy = peer.post(url, json={'resume_text': text})
                    checks.check(door + ': shared ingest admission refuses ' + url,
                        busy.status_code == 503 and busy.json() == {'detail': 'candidate_ingest_capacity_exhausted'}
                        and busy.headers.get('retry-after') == '1')
                response = pending.result(timeout=8)
                checks.check(door + ': pending write returns no IDs or misleading success',
                    response.status_code == 503 and response.json() == {'detail': 'candidate_ingest_pending'}
                    and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
            finally:
                (scratch / 'ingest-release').touch()
                deadline = time.monotonic() + 8
                while not (scratch / 'ingest-completed').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                (scratch / 'ingest-mode').unlink(missing_ok=True)
        outcome = json.loads((scratch / 'ingest-outcome.json').read_text())
        cid, resume = outcome['candidate_id'], outcome['resume_id']
        reports = control.get(f'/candidates/{cid}/reports').json()
        committed_report = report_sql and phase != 'pre'
        checks.check(door + ': late work preserves saved subject/report state without replay',
            len(operations.read_text().splitlines()) == before + 1
            and control.get(f'/candidates/{cid}').json()['resume_count'] == 1
            and len(reports) == int(committed_report))
        report_id = reports[0]['id'] if reports else None
        evaluations = len((scratch / 'ingest-evaluations.jsonl').read_text().splitlines()) if report_sql else None
        if batch:
            queue = actor.get(f'/screening/batches/{batch}/queue').json()['rows']
            checks.check('batch uncertainty retains its lease without a false failure or cross-tenant read',
                queue[0]['status'] == 'processing' and queue[0]['error'] is None
                and org_b.get(f'/screening/batches/{batch}/queue').status_code == 404)
            (scratch / 'ingest-advanced').touch()
        recovered = actor.post(path, json=body)
        assert recovered.status_code == 200
        if batch:
            row = actor.get(f'/screening/batches/{batch}/queue').json()['rows'][0]
            checks.check('explicit process after lease expiry recovers the committed input',
                recovered.json()['processed'] == 1 and row['candidate_id'] == cid and row['resume_id'] == resume)
            if committed_report:
                checks.check('deliberate saved-report recovery avoids another evaluation',
                    row['report_id'] == report_id and len((scratch / 'ingest-evaluations.jsonl').read_text().splitlines()) == evaluations)
        else:
            checks.check(door + ': deliberate upload deduplicates the saved resume', recovered.json()['duplicate_resume']
                and recovered.json()['resume_id'] == resume and recovered.json()['resume_version'] == 1)
        url = f'/candidates/{cid}/resumes'
        saved[url] = control.get(url).json()
        if report_sql:
            url = f'/candidates/{cid}/reports'
            saved[url] = control.get(url).json()
    return saved


def create_source_read_smoke_app():
    return create_candidate_record_smoke_app(source_reads=True)


def create_github_source_smoke_app():
    return create_candidate_record_smoke_app(github_sources=True)


def create_candidate_record_smoke_app(*, source_reads=False, github_sources=False):
    from sqlalchemy import event
    from app.api import candidates as routes
    from smoke_r4_s1_t1a import create_smoke_app
    app = create_smoke_app()
    original = app.router.lifespan_context
    scratch = Path(os.environ['VERITAS_SQL_SMOKE_EVENTS']).parent
    state = local()
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            services = app.state.services
            target = services.profile_sources if source_reads or github_sources else routes
            names = ('_github_login', '_save_github_signal') if github_sources else ('list_sources',) if source_reads else ('_candidate_snapshot', '_candidate_key')
            functions = {name: getattr(target, name) for name in names}
            fetch, caller = services.github.gather_user_signal, get_ident()
            async def provider(login):
                from app.services.github import GitHubRepoRaw, GitHubUserRaw
                assert get_ident() == caller, 'GitHub provider moved off its caller'
                with (scratch / 'github-providers.jsonl').open('a') as log:
                    log.write(json.dumps({'thread': get_ident()}) + '\n')
                if (scratch / 'github-provider-mode').exists():
                    (scratch / 'github-provider-entered').touch()
                    deadline = time.monotonic() + 15
                    while not (scratch / 'github-provider-release').exists():
                        assert time.monotonic() < deadline
                        await asyncio.sleep(.01)
                raw = await fetch(login)
                if login.startswith('worker-'):
                    return GitHubUserRaw(login=login, available=True, repos=[GitHubRepoRaw(
                        name='demo', language='SyntheticLang', languages={'SyntheticLang': 1000})])
                return raw
            if github_sources:
                services.github.gather_user_signal = provider
            for name, function in functions.items():
                def observed(*args, _function=function, _name=name, **kwargs):
                    state.active, state.held, state.history = True, False, False
                    with (scratch / 'record-operations.jsonl').open('a') as log:
                        log.write(json.dumps({'operation': _name, 'thread': get_ident()}) + '\n')
                    try:
                        return _function(*args, **kwargs)
                    finally:
                        state.active = False
                        if state.held:
                            (scratch / 'record-completed').touch()
                setattr(target, name, observed)
            def sql(conn, cursor, statement, parameters, context, many):
                mode = scratch / 'record-mode'
                if mode.exists() and getattr(state, 'active', False) and not state.held:
                    query = statement.upper()
                    phase = mode.read_text()
                    if github_sources:
                        hit = {
                            'initial': 'FROM CANDIDATES' in query and 'JOIN PROFILE_SOURCES' not in query,
                            'handle': 'FROM EXTRACTIONS' in query,
                            'save': query.lstrip().startswith('INSERT INTO PROFILE_SOURCES'),
                            'curation': query.lstrip().startswith('INSERT INTO CURATION_OBSERVATIONS'),
                            'final': 'FROM CANDIDATES' in query and 'JOIN PROFILE_SOURCES' in query,
                        }[phase]
                    elif source_reads:
                        history = 'FROM PROFILE_SOURCES' in query
                        candidate = 'FROM CANDIDATES' in query
                        hit = (phase == 'initial' and candidate or phase == 'history' and history
                               or phase == 'final' and candidate and state.history)
                        state.history = state.history or history
                    else:
                        hit = ('candidates' in statement if phase == 'read' else
                               statement.lstrip().upper().startswith('UPDATE CANDIDATE_CREDENTIALS'))
                    if hit:
                        state.held = True
                        (scratch / 'record-entered').touch()
                        deadline = time.monotonic() + 20
                        while not (scratch / 'record-release').exists():
                            assert time.monotonic() < deadline, 'synthetic candidate SQL gate timed out'
                            time.sleep(.01)
            def owner(session, transaction, connection):
                assert session.info.setdefault('record_owner', get_ident()) == get_ident()
                with (scratch / 'record-thread-ownership.jsonl').open('a') as log:
                    log.write(json.dumps({'owner': session.info['record_owner'], 'current': get_ident()}) + '\n')
            def end(session, transaction):
                assert session.info.get('record_owner', get_ident()) == get_ident()
            engine = services.session_factory.kw['bind']
            event.listen(engine, 'before_cursor_execute', sql)
            event.listen(services.session_factory, 'after_begin', owner)
            event.listen(services.session_factory, 'after_transaction_end', end)
            try:
                yield
            finally:
                if github_sources:
                    services.github.gather_user_signal = fetch
                for name, function in functions.items():
                    setattr(target, name, function)
                event.remove(engine, 'before_cursor_execute', sql)
                event.remove(services.session_factory, 'after_begin', owner)
                event.remove(services.session_factory, 'after_transaction_end', end)
    app.router.lifespan_context = lifespan
    return app


def check_candidate_records(checks, scratch, base, control, operator, cid, other_id, key, *, source_reads=False):
    operations = scratch / 'record-operations.jsonl'
    cases = [('/sources', 'GET', phase) for phase in ('initial', 'history', 'final')] if source_reads else [
        (suffix, method, 'key' if method == 'POST' else 'read')
        for suffix, method in [('', 'GET'), ('/resumes', 'GET'), ('/reports', 'GET'), ('/auth-key', 'POST')]]
    for suffix, method, phase in cases:
        path = f'/candidates/{cid}' + suffix
        expected = operator.get(path).json() if source_reads else None
        before = len(operations.read_text().splitlines())
        for name in ('record-entered', 'record-completed', 'record-release'):
            (scratch / name).unlink(missing_ok=True)
        (scratch / 'record-mode').write_text(phase)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(operator.request, method, path)
            try:
                deadline = time.monotonic() + 8
                while not (scratch / 'record-entered').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                start = time.monotonic()
                health, read = control.get('/healthz'), control.get('/admin/users')
                elapsed = time.monotonic() - start
                checks.check(f'{phase} {suffix or "detail"}: health and unrelated admitted SQL read stay responsive',
                    health.status_code == read.status_code == 200 and elapsed < 1, f'{elapsed:.4f}s')
                busy_cases = [('', 'GET'), ('/resumes', 'GET'), ('/reports', 'GET'), ('/auth-key', 'POST')]
                if source_reads:
                    busy_cases.append(('/sources', 'GET'))
                for busy_suffix, verb in busy_cases:
                    busy = control.request(verb, f'/candidates/{other_id}' + busy_suffix)
                    checks.check(f'{suffix or "detail"}: shared admission refuses {busy_suffix or "detail"}',
                        busy.status_code == 503 and busy.json() == {'detail': 'candidate_record_capacity_exhausted'}
                        and busy.headers.get('retry-after') == '1' and 'set-cookie' not in busy.headers)
                response = pending.result(timeout=8)
                checks.check(f'{suffix or "detail"}: wait expiry returns no partial read or replacement key',
                    response.status_code == 503 and response.json() == {'detail': 'candidate_record_pending'}
                    and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers
                    and len(operations.read_text().splitlines()) == before + 1)
            finally:
                (scratch / 'record-release').touch()
                deadline = time.monotonic() + 8
                while not (scratch / 'record-completed').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                (scratch / 'record-mode').unlink(missing_ok=True)
        with client(base, headers={'X-Candidate-Key': key}) as candidate:
            checks.check(f'{suffix or "detail"}: late completion has the documented credential outcome',
                candidate.get('/portal/me').status_code == (401 if method == 'POST' else 200))
        if method == 'POST':
            fresh = operator.post(path)
            checks.check('deliberate fresh rotation recovers after an undisclosed late key', fresh.status_code == 200)
            key = fresh.json()['access_key']
        else:
            fresh = operator.get(path)
            checks.check(f'{phase} {suffix or "detail"}: explicit read recovers saved state', fresh.status_code == 200
                and (expected is None or fresh.json() == expected))
    if source_reads:
        erased = operator.post('/candidates', json={'resume_text': RESUME.replace('candidate-router@example.in', 'source-erasure@example.in'), 'evaluate': False}).json()['candidate_id']
        path = f'/candidates/{erased}'
        assert operator.post(path + '/sources/github', json={'handle': 'octocat'}).status_code == 200
        for name in ('record-entered', 'record-completed', 'record-release'):
            (scratch / name).unlink(missing_ok=True)
        (scratch / 'record-mode').write_text('final')
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(operator.get, path + '/sources')
            try:
                deadline = time.monotonic() + 8
                while not (scratch / 'record-entered').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                assert control.delete(path).status_code == 200
            finally:
                (scratch / 'record-release').touch()
            response = pending.result(timeout=8)
            checks.check('competing erasure before the final source snapshot refuses loaded history',
                response.status_code == 404 and response.json() == {'detail': 'candidate not found'}
                and operator.get(f'/candidates/{other_id}/sources').status_code == 200)
        (scratch / 'record-mode').unlink(missing_ok=True)
    rows = [json.loads(line) for line in (scratch / 'record-thread-ownership.jsonl').read_text().splitlines()]
    checks.check('candidate SQL sessions keep their owning thread through transactions', rows and all(row['owner'] == row['current'] for row in rows))
    return key


def check_github_sources(checks, scratch, control, operator, other_id):
    def subject(phase):
        text = RESUME.replace('candidate-router@example.in', f'worker-{phase}@example.in').replace(
            'https://github.com/priya-nair/rag-support-bot', f'https://github.com/worker-{phase}')
        response = operator.post('/candidates', json={'resume_text': text, 'evaluate': False})
        assert response.status_code == 200
        return response.json()['candidate_id']
    operations = scratch / 'record-operations.jsonl'
    providers = scratch / 'github-providers.jsonl'
    for phase in ('initial', 'handle', 'save', 'curation', 'final'):
        cid = subject(phase)
        path = f'/candidates/{cid}/sources/github'
        before_ops = len(operations.read_text().splitlines())
        before_fetch = len(providers.read_text().splitlines())
        for name in ('record-entered', 'record-completed', 'record-release'):
            (scratch / name).unlink(missing_ok=True)
        (scratch / 'record-mode').write_text(phase)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(operator.post, path, json={})
            try:
                deadline = time.monotonic() + 8
                while not (scratch / 'record-entered').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                start = time.monotonic()
                checks.check(phase + ': held GitHub SQL leaves health and admitted reads responsive',
                    control.get('/healthz').status_code == control.get('/admin/users').status_code == 200
                    and time.monotonic() - start < 1, f'{time.monotonic()-start:.4f}s')
                for suffix, verb, body in [('', 'GET', None), ('/sources', 'GET', None),
                        ('/sources/github', 'POST', {'handle': 'worker-probe'})]:
                    busy = control.request(verb, f'/candidates/{other_id}' + suffix, json=body)
                    checks.check(phase + ': shared admission refuses ' + suffix,
                        busy.status_code == 503 and busy.json() == {'detail': 'candidate_record_capacity_exhausted'}
                        and busy.headers.get('retry-after') == '1' and 'set-cookie' not in busy.headers)
                response = pending.result(timeout=8)
                checks.check(phase + ': pending GitHub work returns no partial signal or cookies',
                    response.status_code == 503 and response.json() == {'detail': 'candidate_record_pending'}
                    and response.headers.get('retry-after') == '1' and 'set-cookie' not in response.headers)
            finally:
                (scratch / 'record-release').touch()
                deadline = time.monotonic() + 8
                while not (scratch / 'record-completed').exists():
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                (scratch / 'record-mode').unlink(missing_ok=True)
        post = phase not in ('initial', 'handle')
        saved = operator.get(f'/candidates/{cid}/sources').json()['sources']
        checks.check(phase + ': late work has exact saved history without provider replay',
            len(saved) == int(post) and len(providers.read_text().splitlines()) == before_fetch + int(post)
            and len(operations.read_text().splitlines()) == before_ops + (2 if post else 1))
        fresh = operator.post(path, json={})
        history = operator.get(f'/candidates/{cid}/sources').json()['sources']
        checks.check(phase + ': deliberate fresh POST appends one provider result', fresh.status_code == 200
            and len(history) == int(post) + 1 and len(providers.read_text().splitlines()) == before_fetch + int(post) + 1
            and (not saved or fresh.json()['id'] != saved[0]['id']))
    cid = subject('provider')
    for name in ('github-provider-entered', 'github-provider-release'):
        (scratch / name).unlink(missing_ok=True)
    (scratch / 'github-provider-mode').touch()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(operator.post, f'/candidates/{cid}/sources/github', json={})
        try:
            deadline = time.monotonic() + 8
            while not (scratch / 'github-provider-entered').exists():
                assert time.monotonic() < deadline
                time.sleep(.01)
            checks.check('awaited GitHub provider holds no SQL admission',
                control.get(f'/candidates/{other_id}').status_code == 200
                and operator.get(f'/candidates/{cid}/sources').json()['sources'] == [] and not pending.done())
        finally:
            (scratch / 'github-provider-release').touch()
            (scratch / 'github-provider-mode').unlink(missing_ok=True)
        checks.check('released caller-owned provider completes one GitHub source', pending.result(timeout=8).status_code == 200)
    cid = subject('erasure')
    for name in ('record-entered', 'record-completed', 'record-release'):
        (scratch / name).unlink(missing_ok=True)
    (scratch / 'record-mode').write_text('final')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(operator.post, f'/candidates/{cid}/sources/github', json={})
        try:
            deadline = time.monotonic() + 8
            while not (scratch / 'record-entered').exists():
                assert time.monotonic() < deadline
                time.sleep(.01)
            assert control.delete(f'/candidates/{cid}').status_code == 200
        finally:
            (scratch / 'record-release').touch()
        response = pending.result(timeout=8)
        checks.check('competing erasure refuses the GitHub publication snapshot without recreating its subject',
            response.status_code == 404 and response.json() == {'detail': 'candidate not found'}
            and operator.get(f'/candidates/{cid}/sources').status_code == 404
            and operator.get(f'/candidates/{other_id}/sources').status_code == 200)
    (scratch / 'record-mode').unlink(missing_ok=True)
    rows = [json.loads(line) for line in (scratch / 'record-thread-ownership.jsonl').read_text().splitlines()]
    checks.check('GitHub SQL sessions keep ownership through save curations and guards',
        rows and all(row['owner'] == row['current'] for row in rows))


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t3c-"))
    with database(scratch) as (url, pg_options):
        return run(scratch, url, pg_options)


def run(scratch, url, pg_options):
    checks = Smoke("R4-S1-T3C candidate/source HTTP and graceful restart")
    print(f"Synthetic candidate evidence: {scratch}", flush=True)
    stop, events, mailbox = scratch / "stop", scratch / "lifecycle.jsonl", scratch / "mail.jsonl"
    env = {key: value for key, value in base_env().items() if not key.startswith("DEE_")}
    factory = next((f'smoke_r4_s1_t3c:{name}' for flag, name in (
        ('--github-source-workers', 'create_github_source_smoke_app'),
        ('--source-read-workers', 'create_source_read_smoke_app'),
        ('--candidate-report-workers', 'create_candidate_report_smoke_app'),
        ('--candidate-fingerprint-workers', 'create_candidate_fingerprint_smoke_app'),
        ('--candidate-ingest-workers', 'create_candidate_ingest_smoke_app'),
        ('--candidate-record-workers', 'create_candidate_record_smoke_app')) if flag in sys.argv),
        'smoke_r4_s1_t1a:create_smoke_app')
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
        "DEE_CANDIDATES_DB_URL": url, 'PGOPTIONS': pg_options,
        "DEE_DB_MIGRATE_ON_BOOT": "true", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_SPEECH_PROVIDER": "local",
        "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_COOLDOWN_SECONDS": "0",
        "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": factory,
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    if any(flag in sys.argv for flag in ('--candidate-record-workers', '--source-read-workers', '--github-source-workers')):
        env.update(DEE_CANDIDATE_RECORD_MAX_CONCURRENT_REQUESTS='1', DEE_CANDIDATE_RECORD_WAIT_SECONDS='2' if '--source-read-workers' in sys.argv or '--github-source-workers' in sys.argv else '.3',
                   DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600')
    if any(flag in sys.argv for flag in ('--candidate-ingest-workers', '--candidate-fingerprint-workers', '--candidate-report-workers')):
        env.update(DEE_CANDIDATE_INGEST_MAX_CONCURRENT_REQUESTS='1', DEE_CANDIDATE_INGEST_WAIT_SECONDS='.3',
                   DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600')
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        stop.unlink(missing_ok=True)
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port), str(stop)],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base) as health:
                    assert wait_healthy(health), "scratch candidate app failed to start"
                yield
            finally:
                stop.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("scratch candidate app failed graceful shutdown")
                assert proc.returncode == 0, "scratch candidate app failed during lifespan"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def upload(http, text, **extra):
        return require(http.post("/candidates", json={"resume_text": text, "domain": "data_eng", **extra}))

    with client(base, headers={"X-API-Key": ADMIN}) as control, client(base) as operator, \
            client(base) as org_a, client(base) as org_b:
        with server():
            email = "candidate-router-admin@example.in"
            require(control.post("/admin/users", json={"email": email, "label": "Synthetic candidate reviewer"}))
            require(operator.post("/auth/admin/login", json={"email": email}), 202)
            session = require(operator.post("/auth/admin/verify", json={"email": email, "code": _code_for(mailbox, email)}))
            checks.check("operator cookie write refuses missing CSRF", operator.post("/candidates", json={"resume_text": RESUME}).status_code == 403)
            operator.headers["X-CSRF-Token"] = session["csrf_token"]
            for http, name in ((org_a, "A"), (org_b, "B")):
                org = require(control.post("/ledger/orgs", json={"name": "Candidate Router " + name}))
                http.headers["X-Org-Key"] = org["api_key"]
            checks.check("employer credential cannot use operator candidate area", org_a.get("/candidates/missing").status_code == 401
                and org_a.post("/candidates", json={"resume_text": RESUME}).status_code == 401)
            for body in ({}, {"resume_text": "   "}, {"resume_pdf_b64": "!!!"}, {"resume_text": RESUME, "domain": "missing"}):
                require(operator.post("/candidates", json=body), 422)
            checks.check("invalid intake refuses before persistence", True)
            first = upload(operator, RESUME)
            cid, rid = first["candidate_id"], first["report"]["id"]
            path = f"/candidates/{cid}"
            checks.check("operator intake keeps linked advisory report", first["resume_version"] == 1 and first["extraction_method"] == "heuristic"
                and first["report"]["candidate_id"] == cid and first["report"]["advisory"] and first["report"]["human_review_required"])
            duplicate = upload(operator, RESUME, evaluate=False)
            updated = upload(operator, RESUME + "\nAWS certification.", evaluate=False)
            checks.check("dedup and new versions use the same candidate", duplicate["duplicate_resume"] and duplicate["resume_id"] == first["resume_id"]
                and updated["candidate_id"] == cid and updated["resume_version"] == 2 and updated["report"] is None)
            other = upload(control, RESUME.replace("candidate-router@example.in", "candidate-other@example.in"), evaluate=False)
            checks.check("cross-candidate resume deletion refuses", operator.delete(path + f"/resumes/{other['resume_id']}").status_code == 404
                and require(control.get(f"/candidates/{other['candidate_id']}"))["resume_count"] == 1)
            require(operator.delete(path + f"/resumes/{updated['resume_id']}"))
            detail, resumes, reports = (require(operator.get(path + suffix)) for suffix in ("", "/resumes", "/reports"))
            checks.check("detail resume and report reads reflect one retained version", detail["resume_count"] == 1
                and detail["latest_profile"] is not None and len(resumes["resumes"]) == 1 and [row["id"] for row in reports] == [rid])
            invalid = require(operator.post(path + "/sources/github", json={"handle": "invalid handle!"}), 400)
            github = require(operator.post(path + "/sources/github", json={"handle": "octocat"}))
            checks.check("GitHub invalid handle refuses and fake public signal remains advisory", bool(invalid["detail"])
                and github["method"] == "api" and any(skill["canonical"] == "python" for skill in github["skills"]))
            linkedin = require(operator.post(path + "/sources/linkedin", json={"export_b64": _export_b64()}))
            checks.check("LinkedIn export and filtered history persist", linkedin["method"] == "export"
                and linkedin["activity"]["employers"] == ["Infosys", "TCS"]
                and require(operator.get(path + "/sources", params={"source_type": "linkedin_export"}))["sources"] == [linkedin])
            checks.check("invalid LinkedIn base64 preserves history", require(operator.post(path + "/sources/linkedin", json={"export_b64": "!!!"}), 422) == {"detail": "invalid_base64"}
                and len(require(operator.get(path + "/sources"))["sources"]) == 2)
            key = require(operator.post(path + "/auth-key"))["access_key"]
            with client(base, headers={"X-Candidate-Key": key}) as candidate:
                checks.check("issued candidate key resolves the retained subject", require(candidate.get("/portal/me"))["candidate_id"] == cid)
            if any(flag in sys.argv for flag in ('--candidate-record-workers', '--source-read-workers')):
                key = check_candidate_records(checks, scratch, base, control, operator, cid, other['candidate_id'], key,
                    source_reads='--source-read-workers' in sys.argv)
            if '--github-source-workers' in sys.argv:
                check_github_sources(checks, scratch, control, operator, other['candidate_id'])
            intake_saved = check_candidate_ingests(checks, scratch, control, operator, org_a, org_b,
                fingerprint='--candidate-fingerprint-workers' in sys.argv,
                report_sql='--candidate-report-workers' in sys.argv) if any(flag in sys.argv for flag in ('--candidate-ingest-workers', '--candidate-fingerprint-workers', '--candidate-report-workers')) else {}

            owned = require(org_a.post("/screening/candidates", json={"resume_text": RESUME.replace("candidate-router@example.in", "candidate-employer@example.in"), "domain": "data_eng"}))
            employer_rid = owned["report"]["id"]
            checks.check("shared employer intake retains tenant ownership", org_b.get(f"/screening/reports/{employer_rid}").status_code == 404
                and require(org_a.get(f"/screening/reports/{employer_rid}"))["id"] == employer_rid)
            farms = (owned["resume_farm"], owned["report"]["resume_farm"])
            checks.check("both employer farm fields redact counterparty identity", all(farm and farm["matches"] for farm in farms)
                and all(match["candidate_id"] is None and match["resume_id"] is None for farm in farms for match in farm["matches"]))
            saved = {suffix: require(control.get(path + suffix)) for suffix in ("", "/resumes", "/reports", "/sources")}

        with server():
            if intake_saved:
                checks.check('uncertain intake and deliberate recovery survive restart',
                    all(require(control.get(url)) == data for url, data in intake_saved.items()))
            checks.check("exact candidate resume report and source state survives restart", all(require(control.get(path + suffix)) == body for suffix, body in saved.items()))
            with client(base, headers={"X-Candidate-Key": key}) as candidate:
                checks.check("candidate credential survives restart", require(candidate.get("/portal/me"))["candidate_id"] == cid)
            deleted = require(control.delete(path))
            checks.check("operator erasure reports linked cleanup", deleted == {"candidate_id": cid, "deleted": True, "reports_deleted": 1})
            checks.check("erased candidate reads and writes refuse", all(control.get(path + suffix).status_code == 404 for suffix in ("", "/resumes", "/reports", "/sources"))
                and control.post(path + "/auth-key").status_code == 404
                and control.post(path + "/sources/github", json={"handle": "octocat"}).status_code == 404
                and control.post(path + "/sources/linkedin", json={"export_b64": _export_b64()}).status_code == 404
                and control.get(f"/report/{rid}").status_code == 404)
            with client(base, headers={"X-Candidate-Key": key}) as candidate:
                checks.check("erasure invalidates candidate key", candidate.get("/portal/me").status_code == 401)
            checks.check("unrelated candidate and employer report remain", require(control.get(f"/candidates/{other['candidate_id']}"))["resume_count"] == 1
                and require(org_a.get(f"/screening/reports/{employer_rid}"))["id"] == employer_rid)

    lifecycle = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    checks.check("both starts use migrated shared SQL and graceful cleanup", len([row for row in lifecycle if row["event"] == "started" and row["revision"] == "0030_screening_ingest_facts" and row["one_factory"]]) == 2
        and sum(row["event"] == "disposed" for row in lifecycle) == 2
        and sum(row["event"] == "stopped" and row["detached"] for row in lifecycle) == 2)
    logs = (scratch / "server.log").read_text(encoding="utf-8")
    checks.check("app logs omit issued key and candidate mailbox", key not in logs and "candidate-router@example.in" not in logs)
    return checks.summary()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
