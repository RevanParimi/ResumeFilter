"""Document contact hints cannot select or mutate a proved login identity."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow, ExtractionRow
from tests.test_candidate_store import extraction, store  # noqa: F401

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def protect(store, cid, *, review=False, email='owner@example.com'):
    with store._session_factory.begin() as session:
        row = session.get(CandidateRow, cid)
        if review:
            row.login_binding_review_required = True
        else:
            row.login_email_hash = extraction(email=email).profile.contact.email_hash
            row.login_email_verified_at = NOW


def test_ambiguous_asserted_email_never_selects_first_candidate(store):
    incoming = extraction(email='same@example.com')
    with store._session_factory.begin() as session:
        session.add_all([CandidateRow(id=cid, email_hash=incoming.profile.contact.email_hash)
                         for cid in ('first', 'second')])
    result = store.ingest(incoming, 'separate ambiguous submission')
    assert result.candidate_id not in {'first', 'second'}
    assert not result.matched_existing and result.matched_on is None
    assert store.list_resumes('first') == store.list_resumes('second') == []


def test_changed_hint_cannot_select_differently_proved_subject(store):
    original = store.ingest(extraction(email='changed@example.com'), 'original')
    protect(store, original.candidate_id)
    result = store.ingest(extraction(email='changed@example.com'), 'other claimant')
    assert result.candidate_id != original.candidate_id
    assert len(store.list_resumes(original.candidate_id)) == 1


@pytest.mark.parametrize('review', [False, True])
def test_phone_only_cannot_attach_to_protected_subject(store, review):
    original = store.ingest(extraction(email='owner@example.com', phone='9876543210'), 'original')
    protect(store, original.candidate_id, review=review)
    result = store.ingest(extraction(phone='9876543210'), 'phone only')
    assert result.candidate_id != original.candidate_id
    assert len(store.list_resumes(original.candidate_id)) == 1


@pytest.mark.parametrize('review', [False, True])
def test_email_upload_preserves_protected_hints_and_document_claim(store, review):
    original = store.ingest(extraction(email='owner@example.com'), 'original')
    protect(store, original.candidate_id, review=review)
    incoming = extraction(email='owner@example.com', phone='9876543210')
    result = store.ingest(incoming, 'document adds a phone claim')
    assert result.candidate_id == original.candidate_id
    assert result.matched_on == 'email_hash' and result.resume_version == 2
    with store._session_factory() as session:
        row = session.get(CandidateRow, original.candidate_id)
        assert row.phone_hash is None
        assert row.login_binding_review_required is review
        assert (row.login_email_hash is None) is review
        saved = session.scalar(select(ExtractionRow).where(ExtractionRow.id == result.extraction_id))
        assert saved.profile['contact']['phone_hash'] == incoming.profile.contact.phone_hash


def test_original_resume_retry_does_not_backfill_missing_email_after_proof(store):
    original = store.ingest(extraction(phone='9876543210'), 'same original bytes')
    protect(store, original.candidate_id)
    result = store.ingest(extraction(email='other@example.com', phone='9876543210'),
        'same original bytes', expected_resume_id=original.resume_id)
    assert result.resume_id == original.resume_id
    assert store.get_candidate(original.candidate_id).email_hash is None
    with store._session_factory() as session:
        assert session.get(CandidateRow, original.candidate_id).login_email_hash == (
            extraction(email='owner@example.com').profile.contact.email_hash)
