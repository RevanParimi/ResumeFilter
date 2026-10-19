"""Competing real writes must not bypass upload contact policy."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event, select, text, update

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.candidates.store import AssertedContactChangedError, CandidateStore
from app.core.db import make_session_factory
from tests.test_asserted_contact_policy import NOW
from tests.test_candidate_login_binding_concurrency import blocked
from tests.test_candidate_store import extraction
from tests.test_report_erasure_concurrency import database  # noqa: F401


@pytest.mark.parametrize('rollback', [False, True])
@pytest.mark.parametrize('change', ['proof_phone_match', 'review_phone_match',
    'proof_email_backfill', 'review_email_backfill', 'hint_email_match', 'hint_phone_backfill'])
def test_contact_write_waits_and_rechecks_current_state(database, change, rollback):
    engine, factory = database
    store = CandidateStore(factory)
    email = 'owner@example.com'
    original_profile = extraction(email=email, phone='9876543210' if 'phone_match' in change else None)
    original = store.ingest(original_profile, 'original')
    incoming = (extraction(phone='9876543210') if 'phone_match' in change else
                extraction(email=email, phone='9876543210'))
    writer_factory = make_session_factory(engine)
    writer = CandidateStore(writer_factory)
    ready, release, started = Event(), Event(), Event()
    pids = []

    def pause(*_):
        ready.set()
        assert release.wait(20)

    def update_started(connection, cursor, statement, *_):
        if statement.startswith('UPDATE candidates'):
            if engine.dialect.name == 'postgresql':
                pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
            started.set()

    event.listen(writer_factory, 'before_flush', pause, once=True)
    event.listen(engine, 'before_cursor_execute', update_started)
    controller = factory()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(writer.ingest, incoming, 'incoming')
            try:
                assert ready.wait(20)
                if change.startswith('proof'):
                    values = dict(login_email_hash=original_profile.profile.contact.email_hash,
                                  login_email_verified_at=NOW)
                elif change.startswith('review'):
                    values = dict(login_binding_review_required=True)
                elif change == 'hint_phone_backfill':
                    values = dict(phone_hash=extraction(phone='9123456789').profile.contact.phone_hash)
                else:
                    values = dict(email_hash=extraction(email='changed@example.com').profile.contact.email_hash)
                controller.execute(update(CandidateRow).where(
                    CandidateRow.id == original.candidate_id).values(**values))
                owner = (controller.connection().scalar(text('SELECT pg_backend_pid()'))
                         if engine.dialect.name == 'postgresql' else None)
                started.clear()
                pids.clear()
                release.set()
                assert started.wait(20)
                blocked(engine, pending, owner, pids)
                controller.rollback() if rollback else controller.commit()
                refused = not rollback and change.endswith('match')
                if refused:
                    with pytest.raises(AssertedContactChangedError, match='^candidate_contact_changed$'):
                        pending.result(timeout=20)
                else:
                    assert pending.result(timeout=20).candidate_id == original.candidate_id
            finally:
                release.set()
                controller.rollback()
    finally:
        controller.close()
        event.remove(engine, 'before_cursor_execute', update_started)
    with factory() as session:
        row = session.get(CandidateRow, original.candidate_id)
        assert len(session.scalars(select(ResumeRow).where(
            ResumeRow.candidate_id == row.id)).all()) == (1 if refused else 2)
        assert len(session.scalars(select(ExtractionRow).where(
            ExtractionRow.candidate_id == row.id)).all()) == (1 if refused else 2)
        if change in {'proof_email_backfill', 'review_email_backfill'}:
            assert (row.phone_hash is not None) is rollback
        elif change == 'hint_phone_backfill':
            expected = incoming if rollback else extraction(phone='9123456789')
            assert row.phone_hash == expected.profile.contact.phone_hash
        assert session.get(CandidateRow, 'b') is not None
    # A fresh phone-only retry becomes a separate submission after protection.
    if refused and 'phone_match' in change:
        assert store.ingest(incoming, 'incoming').candidate_id != original.candidate_id
