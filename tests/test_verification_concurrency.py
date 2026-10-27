"""Verification concurrency regressions, grouped by behavior."""

import random
import pytest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic
from sqlalchemy import event, select, text, update
from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.ledger.store import LedgerStore
from app.verification.models import VerificationChallengeRow
from app.verification.otp import hash_code, generate_code
from app.verification.schema import VerificationMethod, VerificationStatus
from app.verification.store import ChallengeError, VerificationStore
from tests.test_report_erasure_concurrency import database
from app.services.email import EmailSendFailed


# Verification concurrency

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def store(factory, settings):
    return VerificationStore(factory, ledger=LedgerStore(factory, settings=settings), settings=settings)


def seed(factory, settings, cid='a'):
    service = store(factory, settings)
    verification = service.create_verification(candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW)
    code = service.create_challenge(verification_id=verification.id, channel='email',
                                    destination_hash='e' * 64, rng=random.Random(17), at=NOW)
    return service, verification, code


def wrong(code):
    return '0' * len(code) if code != '0' * len(code) else '1' * len(code)


def attempt(job):
    try:
        return ('ok', job())
    except ChallengeError as exc:
        return ('refused', str(exc))
    except LookupError as exc:
        return ('missing', str(exc))


def race(engine, settings, first_job, second_job, *, pause='before_flush', before_release=None):
    """Let the old code finish B before A writes; fixed code queues B's lock.

    Observe actual PostgreSQL blockers before release. SQLite's SQL-entry event
    schedules competing connections, but is not PostgreSQL lock evidence.
    """
    first, second = make_session_factory(engine), make_session_factory(engine)
    ready, release, boundary = Event(), Event(), Event()
    pids = {}

    def paused(session, *_):
        if engine.dialect.name == 'postgresql':
            pids['first'] = session.connection().scalar(text('SELECT pg_backend_pid()'))
        ready.set()
        assert release.wait(20), 'first transaction was not released'

    def began(session, transaction, connection):
        connection.info['verification_race_second'] = True
        if engine.dialect.name == 'postgresql':
            pids['second'] = connection.scalar(text('SELECT pg_backend_pid()'))

    def lock_entered(connection, cursor, statement, *_):
        sql = statement.upper()
        if connection.info.get('verification_race_second') and (
                sql.startswith(('UPDATE CANDIDATES', 'DELETE FROM CANDIDATES'))
                or ('FROM CANDIDATES' in sql and 'FOR UPDATE' in sql)):
            boundary.set()

    event.listen(first, pause, paused, once=True)
    event.listen(second, 'after_begin', began, once=True)
    event.listen(engine, 'before_cursor_execute', lock_entered)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(attempt, lambda: first_job(store(first, settings)))
            try:
                assert ready.wait(20)
                b = executor.submit(attempt, lambda: second_job(store(second, settings)))
                b.add_done_callback(lambda _: boundary.set())
                assert boundary.wait(20), 'second transaction did not start'
                if engine.dialect.name == 'postgresql' and not b.done():
                    with engine.connect() as observer:
                        deadline = monotonic() + 15
                        while monotonic() < deadline:
                            if pids['first'] in observer.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': pids['second']}):
                                break
                        else:
                            pytest.fail('candidate lock did not serialize the competing transaction')
                if before_release:
                    before_release()
            finally:
                release.set()
            return a.result(timeout=20), b.result(timeout=20)
    finally:
        event.remove(engine, 'before_cursor_execute', lock_entered)
        with engine.connect() as connection:
            connection.info.pop('verification_race_second', None)


def completions(factory, vid):
    return [a for a in LedgerStore(factory).audit_for_candidate('a')
            if a.action == 'verification.complete' and a.entity_id == vid]


def test_competing_wrong_guesses_charge_two_attempts(database, settings):
    engine, factory = database
    _, v, code = seed(factory, settings)
    results = race(engine, settings,
        lambda s: s.confirm_challenge(v.id, wrong(code), at=NOW),
        lambda s: s.confirm_challenge(v.id, wrong(code), at=NOW))
    assert [r[0] for r in results] == ['refused', 'refused']
    with factory() as session:
        challenge = session.scalar(select(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == v.id))
        assert challenge.attempts == 2


def test_competing_correct_guesses_consume_once_and_audit_once(database, settings):
    engine, factory = database
    _, v, code = seed(factory, settings)
    results = race(engine, settings,
        lambda s: s.confirm_challenge(v.id, code, at=NOW),
        lambda s: s.confirm_challenge(v.id, code, at=NOW))
    assert sorted(r[0] for r in results) == ['ok', 'refused']
    assert len(completions(factory, v.id)) == 1


def test_already_exhausted_budget_cannot_verify_even_with_correct_code(database, settings):
    _, factory = database
    service, v, code = seed(factory, settings)
    with factory.begin() as session:
        session.execute(update(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == v.id)
                        .values(attempts=settings.verif_otp_max_attempts))
    with pytest.raises(ChallengeError):
        service.confirm_challenge(v.id, code, at=NOW)
    assert service.get_verification(v.id).status is VerificationStatus.FAILED


def test_legacy_competing_codes_fail_closed_until_resend(database, settings):
    _, factory = database
    service, v, code = seed(factory, settings)
    new = service.create_verification(candidate_id='a', method=VerificationMethod.OTP_EMAIL, at=NOW)
    # The former issuance race could persist two live codes across different IDs.
    with factory.begin() as session:
        session.add(VerificationChallengeRow(id='legacy-race', verification_id=new.id,
            code_hash=hash_code('123456', settings.contact_hash_salt), channel='email', destination_hash='e' * 64,
            attempts=0, max_attempts=settings.verif_otp_max_attempts,
            expires_at=NOW + timedelta(minutes=settings.verif_otp_ttl_minutes), last_sent_at=NOW))
    for vid, supplied in [(v.id, code), (new.id, '123456')]:
        with pytest.raises(ChallengeError):
            service.confirm_challenge(vid, supplied, at=NOW)
    assert completions(factory, v.id) == completions(factory, new.id) == []
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    replacement = service.create_challenge(verification_id=new.id, channel='email', destination_hash='e' * 64, at=later)
    with pytest.raises(ChallengeError):
        service.confirm_challenge(v.id, code, at=later)
    assert service.confirm_challenge(new.id, replacement, at=later).status is VerificationStatus.VERIFIED


@pytest.mark.parametrize('correct_first', [False, True])
def test_last_attempt_and_correct_code_obey_lock_order(database, settings, correct_first):
    engine, factory = database
    service, v, code = seed(factory, settings)
    with factory.begin() as session:
        session.execute(update(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == v.id)
                        .values(attempts=settings.verif_otp_max_attempts - 1))
    first, second = (code, wrong(code)) if correct_first else (wrong(code), code)
    results = race(engine, settings,
        lambda s: s.confirm_challenge(v.id, first, at=NOW),
        lambda s: s.confirm_challenge(v.id, second, at=NOW))
    assert [r[0] for r in results] == (['ok', 'refused'] if correct_first else ['refused', 'refused'])
    assert service.get_verification(v.id).status is (
        VerificationStatus.VERIFIED if correct_first else VerificationStatus.FAILED)
    assert len(completions(factory, v.id)) == 1
    with factory() as session:
        assert session.scalar(select(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == v.id)) is None


def test_concurrent_issuance_honors_candidate_channel_cooldown(database, settings):
    engine, factory = database
    service = store(factory, settings)
    rows = [service.create_verification(candidate_id='a', method=VerificationMethod.OTP_EMAIL, at=NOW) for _ in range(2)]
    results = race(engine, settings,
        lambda s: s.create_challenge(verification_id=rows[0].id, channel='email', destination_hash='e' * 64, at=NOW),
        lambda s: s.create_challenge(verification_id=rows[1].id, channel='email', destination_hash='e' * 64, at=NOW),
        pause='before_commit')
    assert [r[0] for r in results] == ['ok', 'refused']
    with factory() as session:
        challenges = session.scalars(select(VerificationChallengeRow)).all()
        assert len(challenges) == 1 and challenges[0].verification_id == rows[0].id
        assert challenges[0].attempts == 0


@pytest.mark.parametrize('resend_first', [False, True])
def test_resend_and_confirmation_cannot_use_superseded_secret(database, settings, resend_first):
    engine, factory = database
    service, old, code = seed(factory, settings)
    new = service.create_verification(candidate_id='a', method=VerificationMethod.OTP_EMAIL, at=NOW)
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    confirm = lambda s: s.confirm_challenge(old.id, code, at=later)
    resend = lambda s: s.create_challenge(verification_id=new.id, channel='email', destination_hash='e' * 64, at=later)
    results = race(engine, settings, resend if resend_first else confirm, confirm if resend_first else resend,
                   pause='before_commit' if resend_first else 'before_flush')
    assert [r[0] for r in results] == (['ok', 'refused'] if resend_first else ['ok', 'ok'])
    assert service.get_verification(old.id).status is (VerificationStatus.PENDING if resend_first else VerificationStatus.VERIFIED)
    new_code = results[0 if resend_first else 1][1]
    with factory() as session:
        challenges = session.scalars(select(VerificationChallengeRow)).all()
        assert len(challenges) == 1 and challenges[0].verification_id == new.id and challenges[0].attempts == 0
    assert service.confirm_challenge(new.id, new_code, at=later).status is VerificationStatus.VERIFIED


def test_default_clock_is_read_after_waiting_for_lock(database, settings, monkeypatch):
    engine, factory = database
    service, v, code = seed(factory, settings)
    clock = [NOW]
    monkeypatch.setattr('app.verification.store._utcnow', lambda: clock[0])
    expiry = NOW + timedelta(minutes=settings.verif_otp_ttl_minutes)
    results = race(engine, settings,
        lambda s: s.confirm_challenge(v.id, wrong(code)),
        lambda s: s.confirm_challenge(v.id, code), before_release=lambda: clock.__setitem__(0, expiry))
    assert [r[0] for r in results] == ['refused', 'refused']
    assert service.get_verification(v.id).status is VerificationStatus.PENDING
    assert completions(factory, v.id) == []
    with factory() as session:
        assert session.scalar(select(VerificationChallengeRow)) is None


def test_failed_audit_rolls_back_outcome_secret_and_lock(database, settings):
    engine, factory = database
    service, v, code = seed(factory, settings)

    def fails(s):
        audit = s._ledger._audit

        def fail_after_flush(session, **kwargs):
            audit(session, **kwargs)
            session.flush()  # force real SQL, then pause while the second waits
            raise RuntimeError('synthetic audit failure')

        s._ledger._audit = fail_after_flush
        try:
            s.confirm_challenge(v.id, code, at=NOW)
        except RuntimeError as exc:
            assert str(exc) == 'synthetic audit failure'
            return 'rolled back'
        pytest.fail('audit failure did not propagate')

    results = race(engine, settings, fails, lambda s: s.confirm_challenge(v.id, code, at=NOW), pause='after_flush')
    assert results[0] == ('ok', 'rolled back') and results[1][0] == 'ok'
    assert service.get_verification(v.id).status is VerificationStatus.VERIFIED
    assert len(completions(factory, v.id)) == 1


@pytest.mark.parametrize('erase_first', [False, True])
def test_erasure_and_confirmation_leave_no_challenge_or_outcome(database, settings, erase_first):
    engine, factory = database
    service, v, code = seed(factory, settings)
    _, survivor, survivor_code = seed(factory, settings, cid='b')
    confirm = lambda s: s.confirm_challenge(v.id, code, at=NOW)
    erase = lambda s: CandidateStore(s._session_factory).delete_candidate('a')
    results = race(engine, settings, erase if erase_first else confirm, confirm if erase_first else erase,
                   pause='after_flush' if erase_first else 'before_flush')
    assert [r[0] for r in results] == (['ok', 'missing'] if erase_first else ['ok', 'ok'])
    assert service.get_verification(v.id) is None
    with factory() as session:
        assert session.get(CandidateRow, 'a') is None
        assert session.scalar(select(VerificationChallengeRow).where(VerificationChallengeRow.verification_id == v.id)) is None
    with pytest.raises(LookupError):
        service.confirm_challenge(v.id, code, at=NOW)
    assert service.confirm_challenge(survivor.id, survivor_code, at=NOW).status is VerificationStatus.VERIFIED


# Verification delivery transactions

@pytest.mark.parametrize("send_failed", [False, True])
def test_confirmation_cannot_pass_uncommitted_dispatch_or_verify_failed_send(database, settings, send_failed):
    engine, factory = database
    store, old, old_code = seed(factory, settings)
    new = store.create_verification(candidate_id="a", method=VerificationMethod.OTP_EMAIL, at=NOW)
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    expected_code = generate_code(settings.verif_otp_length, rng=random.Random(29))
    dispatches = []

    def first(s):
        def dispatch(code):
            dispatches.append(code)
            if send_failed:
                raise EmailSendFailed("synthetic delivery failure")
        try:
            return s.create_challenge(verification_id=new.id, channel="email", destination_hash="e" * 64,
                rng=random.Random(29), at=later, dispatch=dispatch)
        except EmailSendFailed:
            raise ChallengeError("delivery refused") from None

    # The reused harness pauses within issuance and observes actual PG blockers
    # before release. Even a recipient who already knows the new code must wait.
    results = race(engine, settings, first,
        lambda s: s.confirm_challenge(new.id, expected_code, at=later))
    assert dispatches == [expected_code]
    assert [r[0] for r in results] == (["refused", "refused"] if send_failed else ["ok", "ok"])
    if send_failed:
        with factory() as session:
            survivor = session.scalar(select(VerificationChallengeRow))
            assert survivor.verification_id == old.id and survivor.attempts == 0
        assert store.confirm_challenge(old.id, old_code, at=later).status is VerificationStatus.VERIFIED
    else:
        assert store.get_verification(new.id).status is VerificationStatus.VERIFIED
        with factory() as session:
            assert session.scalar(select(VerificationChallengeRow)) is None


def test_candidate_erasure_serializes_with_dispatch_and_sweeps_activated_secret(database, settings):
    engine, factory = database
    store, _, _ = seed(factory, settings)
    new = store.create_verification(candidate_id="a", method=VerificationMethod.OTP_EMAIL, at=NOW)
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    sent = []
    results = race(engine, settings,
        lambda s: s.create_challenge(verification_id=new.id, channel="email", destination_hash="e" * 64,
            at=later, dispatch=sent.append),
        lambda s: CandidateStore(s._session_factory).delete_candidate("a"))
    assert [r[0] for r in results] == ["ok", "ok"]
    assert len(sent) == 1
    assert store.get_verification(new.id) is None
    assert CandidateStore(factory).get_candidate('b') is not None
    with factory() as session:
        assert session.scalar(select(VerificationChallengeRow)) is None
