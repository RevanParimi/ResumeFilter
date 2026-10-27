"""S7.1 candidate-plane routes: the key is the only identity input that counts."""

import pytest
import asyncio
from threading import Event
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.models import CandidateRow
from app.main import create_app
from app.verification.models import VerificationChallengeRow
from tests.conftest import ADMIN_HEADERS, make_services
from tests.test_report_erasure_concurrency import database  # noqa: F401

EMAIL = "dev@example.com"


@pytest.mark.parametrize('ending', ['release', 'timeout', 'cancel', 'failure', 'late_failure'])
async def test_contact_admission_keeps_owning_work_until_completion(database, settings, tmp_path, monkeypatch, ending):
    import httpx
    import json
    import re
    from threading import get_ident
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    from app.services.email import EmailSendFailed
    engine, factory = database
    settings.email_provider = 'capture'
    settings.email_capture_path = str(tmp_path / 'contact-mail.jsonl')
    settings.contact_code_max_concurrent_requests = 1
    settings.contact_code_wait_seconds = .05 if ending in {'timeout', 'late_failure'} else 20
    services = make_services(settings, candidates=CandidateStore(factory))
    cid, key = _candidate(services)
    other_id, other_key = _candidate(services, email='other-contact@example.com')
    headers, other = {'X-Candidate-Key': key}, {'X-Candidate-Key': other_key}
    entered, release = Event(), Event()
    caller, threads, calls = get_ident(), [], []
    send = services.email.send
    def mail(**kwargs):
        calls.append(kwargs['to'])
        assert get_ident() != caller
        entered.set()
        assert release.wait(15)
        if ending in {'failure', 'late_failure'}:
            raise EmailSendFailed('private-contact-worker-sentinel')
        return send(**kwargs)
    def begin(session, transaction, connection):
        owner = session.info.setdefault('contact_owner', get_ident())
        assert owner == get_ident(), 'a live Session crossed threads'
        threads.append(owner)
    def end(session, transaction):
        assert session.info.get('contact_owner', get_ident()) == get_ident()
    def state():
        with factory() as session:
            return {table: list(session.execute(text(f'SELECT * FROM {table} ORDER BY id')).tuples())
                for table in ('verifications', 'verification_challenges', 'audit_log')}
    monkeypatch.setattr(services.email, 'send', mail)
    event.listen(factory, 'after_begin', begin)
    event.listen(factory, 'after_transaction_end', end)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                pending = asyncio.create_task(http.post('/portal/verifications', headers=headers,
                    json={'method': 'otp_email', 'destination': EMAIL}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    before = state()
                    for actor, destination in ((headers, EMAIL), (other, 'other-contact@example.com')):
                        response = await http.post('/portal/verifications', headers=actor,
                            json={'method': 'otp_email', 'destination': destination})
                        assert response.status_code == 503
                        assert response.json() == {'detail': 'contact_code_capacity_exhausted'}
                        assert response.headers['retry-after'] == '1'
                    assert state() == before, 'an unadmitted request changed SQL state'
                    assert (await http.post('/portal/verifications', json={'method': 'otp_email', 'destination': EMAIL})).status_code == 401
                    if ending in {'timeout', 'late_failure'}:
                        response = await asyncio.wait_for(pending, 2)
                        assert response.status_code == 504 and response.json() == {'detail': 'contact_code_pending'}
                        assert 'set-cookie' not in response.headers
                        assert not (tmp_path / 'contact-mail.jsonl').exists()
                    elif ending == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                    busy = await http.post('/portal/verifications', headers=headers,
                        json={'method': 'otp_email', 'destination': EMAIL})
                    assert busy.status_code == 503
                finally:
                    release.set()
                    results = await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.contact_codes._active:
                            await asyncio.sleep(.01)
                assert calls == [EMAIL], 'the timed-out request was automatically replayed'
                listed = (await http.get('/portal/verifications', headers=headers)).json()['verifications']
                assert len(listed) == 1 and listed[0]['candidate_id'] == cid
                assert (await http.get('/portal/verifications', headers=other)).json()['verifications'] == []
                if ending in {'failure', 'late_failure'}:
                    assert listed[0]['status'] == 'failed'
                    assert not (tmp_path / 'contact-mail.jsonl').exists()
                    if ending == 'failure':
                        assert results[0].status_code == 503 and results[0].json() == {'detail': 'email_send_failed'}
                    with factory() as session:
                        assert session.scalar(text('SELECT count(*) FROM verification_challenges')) == 0
                else:
                    assert listed[0]['status'] == 'pending'
                    message = json.loads((tmp_path / 'contact-mail.jsonl').read_text().splitlines()[0])
                    code = re.search(r'\b(\d{6})\b', message['body'])[1]
                    path = f"/portal/verifications/{listed[0]['id']}/confirm"
                    assert (await http.post(path, headers=other, json={'code': code})).status_code == 404
                    confirmed = await http.post(path, headers=headers, json={'code': code})
                    assert confirmed.status_code == 200 and confirmed.json()['status'] == 'verified'
                # Freed capacity accepts a new owning operation (no mail involved).
                fresh = await http.post('/portal/verifications', headers=other, json={'method': 'self_attested'})
                assert fresh.status_code in {200, 504}, fresh.text
                async with asyncio.timeout(8):
                    while services.contact_codes._active:
                        await asyncio.sleep(.01)
                saved = (await http.get('/portal/verifications', headers=other)).json()['verifications']
                assert len(saved) == 1 and saved[0]['method'] == 'self_attested' and saved[0]['status'] == 'verified'
                assert services.candidates.get_candidate(other_id) is not None
        assert caller in threads and any(thread != caller for thread in threads)
    finally:
        release.set()
        await services.aclose()
        event.remove(factory, 'after_begin', begin)
        event.remove(factory, 'after_transaction_end', end)


async def test_contact_worker_waits_for_a_real_competing_transaction(database, settings, tmp_path):
    import httpx
    import json
    import re
    from sqlalchemy import event, text
    from app.candidates.store import CandidateStore
    engine, factory = database
    settings.email_provider = 'capture'
    settings.email_capture_path = str(tmp_path / 'locked-contact-mail.jsonl')
    settings.contact_code_max_concurrent_requests = 1
    settings.contact_code_wait_seconds = .1
    services = make_services(settings, candidates=CandidateStore(factory))
    cid, key = _candidate(services)
    headers = {'X-Candidate-Key': key}
    entered, pids = Event(), []
    def observing(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('INSERT INTO VERIFICATIONS'):
            if engine.dialect.name == 'postgresql':
                pids.append(conn.scalar(text('SELECT pg_backend_pid()')))
            entered.set()
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                blocker = engine.connect()
                if engine.dialect.name == 'sqlite':
                    blocker.exec_driver_sql('BEGIN IMMEDIATE')
                else:
                    blocker.execute(text('SELECT id FROM candidates WHERE id=:cid FOR UPDATE'), {'cid': cid}).all()
                event.listen(engine, 'before_cursor_execute', observing)
                pending = asyncio.create_task(http.post('/portal/verifications', headers=headers,
                    json={'method': 'otp_email', 'destination': EMAIL}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    if engine.dialect.name == 'postgresql':
                        async with asyncio.timeout(5):
                            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as observer:
                                while not observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid=:pid"), {'pid': pids[0]}):
                                    await asyncio.sleep(.01)
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users', headers=ADMIN_HEADERS)).status_code == 200
                    response = await pending
                    assert response.status_code == 504 and response.json() == {'detail': 'contact_code_pending'}
                    assert (await http.post('/portal/verifications', headers=headers, json={'method': 'self_attested'})).status_code == 503
                finally:
                    blocker.rollback()
                    blocker.close()
                    event.remove(engine, 'before_cursor_execute', observing)
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.contact_codes._active:
                            await asyncio.sleep(.01)
                row = (await http.get('/portal/verifications', headers=headers)).json()['verifications'][0]
                message = json.loads((tmp_path / 'locked-contact-mail.jsonl').read_text().splitlines()[0])
                code = re.search(r'\b(\d{6})\b', message['body'])[1]
                assert (await http.post(f"/portal/verifications/{row['id']}/confirm", headers=headers, json={'code': code})).status_code == 200
    finally:
        await services.aclose()


async def test_erasure_before_late_contact_issuance_does_not_restore_subject(database, settings, tmp_path, monkeypatch):
    import httpx
    from threading import get_ident
    from sqlalchemy import text
    from app.candidates.store import CandidateStore
    engine, factory = database
    settings.email_provider = 'capture'
    settings.email_capture_path = str(tmp_path / 'erased-contact-mail.jsonl')
    settings.contact_code_max_concurrent_requests = 1
    settings.contact_code_wait_seconds = .05
    services = make_services(settings, candidates=CandidateStore(factory))
    cid, key = _candidate(services)
    survivor, other_key = _candidate(services, email='surviving-contact@example.com')
    entered, release, caller = Event(), Event(), get_ident()
    read = services.candidates.get_candidate
    def held(subject):
        result = read(subject)
        if subject == cid and get_ident() != caller and not entered.is_set():
            entered.set()
            assert release.wait(15)
        return result
    monkeypatch.setattr(services.candidates, 'get_candidate', held)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                pending = asyncio.create_task(http.post('/portal/verifications', headers={'X-Candidate-Key': key},
                    json={'method': 'otp_email', 'destination': EMAIL}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await pending).status_code == 504
                    assert (await http.delete(f'/candidates/{cid}', headers=ADMIN_HEADERS)).status_code == 200
                    assert (await http.get('/portal/verifications', headers={'X-Candidate-Key': key})).status_code == 401
                    assert (await http.post('/portal/verifications', headers={'X-Candidate-Key': other_key},
                        json={'method': 'self_attested'})).status_code == 503
                finally:
                    release.set()
                    await asyncio.gather(pending, return_exceptions=True)
                    async with asyncio.timeout(8):
                        while services.contact_codes._active:
                            await asyncio.sleep(.01)
                assert services.candidates.get_candidate(cid) is None
                assert services.candidates.get_candidate(survivor) is not None
                assert not (tmp_path / 'erased-contact-mail.jsonl').exists()
                with factory() as session:
                    assert session.scalar(text('SELECT count(*) FROM verifications')) == 0
                    assert session.scalar(text('SELECT count(*) FROM verification_challenges')) == 0
    finally:
        release.set()
        await services.aclose()


@pytest.mark.parametrize('gate', ['mail', 'sql'])
async def test_slow_contact_start_keeps_unrelated_requests_responsive(database, settings, tmp_path, monkeypatch, gate):
    import httpx
    from sqlalchemy import event
    from app.candidates.store import CandidateStore
    engine, factory = database
    settings.email_provider = 'capture'
    settings.email_capture_path = str(tmp_path / 'held-contact-mail.jsonl')
    services = make_services(settings, candidates=CandidateStore(factory))
    _, key = _candidate(services)
    entered, release, finished = Event(), Event(), Event()
    send = services.email.send
    def hold():
        entered.set()
        release.wait(3)
        finished.set()
    def mail(**kwargs):
        if gate == 'mail':
            hold()
        return send(**kwargs)
    def sql(conn, cursor, statement, parameters, context, many):
        if gate == 'sql' and 'verifications' in statement and not entered.is_set():
            hold()
    monkeypatch.setattr(services.email, 'send', mail)
    event.listen(engine, 'before_cursor_execute', sql)
    app = create_app(services)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
                pending = asyncio.create_task(http.post('/portal/verifications', headers={'X-Candidate-Key': key},
                    json={'method': 'otp_email', 'destination': EMAIL}))
                try:
                    assert await asyncio.to_thread(entered.wait, 8)
                    assert (await http.get('/healthz')).status_code == 200
                    assert (await http.get('/admin/users', headers=ADMIN_HEADERS)).status_code == 200
                    assert not finished.is_set(), f'unrelated requests waited for contact {gate}'
                finally:
                    release.set()
                    response = await pending
                assert response.status_code == 200 and response.json()['verification']['status'] == 'pending'
    finally:
        release.set()
        await services.aclose()
        event.remove(engine, 'before_cursor_execute', sql)


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
    if services._contact_codes is not None:
        services._contact_codes.close()


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
