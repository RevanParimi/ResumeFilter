"""CandidateStore — ingest, identity resolution (email/phone hash), versioning."""

import pytest

from app.candidates import hashing
from app.candidates.schema import CandidateProfile, ExtractedStr, ExtractionResult
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory

SALT = "test-salt"


@pytest.fixture
def store() -> CandidateStore:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return CandidateStore(make_session_factory(engine))


def extraction(name=None, email=None, phone=None) -> ExtractionResult:
    profile = CandidateProfile()
    if name:
        profile.full_name = ExtractedStr(value=name)
    if email:
        profile.contact.email = ExtractedStr(value=email)
    if phone:
        profile.contact.phone = ExtractedStr(value=phone)
    hashing.apply_contact_hashes(profile, salt=SALT)
    return ExtractionResult(profile=profile, method="heuristic")


def test_ingest_new_candidate(store):
    out = store.ingest(extraction(name="Asha Rao", email="asha@example.com"), "resume one")
    assert out.matched_existing is False
    assert out.matched_on is None
    assert out.resume_version == 1
    assert out.duplicate_resume is False
    assert out.candidate_id and out.resume_id and out.extraction_id


def test_same_email_attaches_second_resume_version(store):
    first = store.ingest(extraction(email="asha@example.com"), "resume one")
    second = store.ingest(extraction(email="Asha@Example.com "), "resume two")
    assert second.candidate_id == first.candidate_id
    assert second.matched_existing is True
    assert second.matched_on == "email_hash"
    assert second.resume_version == 2


def test_phone_match_when_email_absent(store):
    first = store.ingest(extraction(email="asha@example.com", phone="+91 98765 43210"), "r1")
    second = store.ingest(extraction(phone="09876543210"), "r2")
    assert second.candidate_id == first.candidate_id
    assert second.matched_on == "phone_hash"


def test_email_match_takes_precedence_over_phone(store):
    store.ingest(extraction(email="a@example.com", phone="9876543210"), "ra")
    b = store.ingest(extraction(email="b@example.com"), "rb")
    hit = store.ingest(extraction(email="b@example.com", phone="9876543210"), "rc")
    assert hit.candidate_id == b.candidate_id
    assert hit.matched_on == "email_hash"


def test_no_contact_always_creates_new_candidate(store):
    a = store.ingest(extraction(name="Anon One"), "r1")
    b = store.ingest(extraction(name="Anon Two"), "r2")
    assert a.candidate_id != b.candidate_id


def test_identical_text_reuses_resume_but_records_new_extraction(store):
    first = store.ingest(extraction(email="asha@example.com"), "same text")
    again = store.ingest(extraction(email="asha@example.com"), "same text")
    assert again.duplicate_resume is True
    assert again.resume_id == first.resume_id
    assert again.resume_version == 1
    assert again.extraction_id != first.extraction_id


def test_missing_hash_backfilled_on_match(store):
    first = store.ingest(extraction(email="asha@example.com"), "r1")
    store.ingest(extraction(email="asha@example.com", phone="9876543210"), "r2")
    by_phone = store.ingest(extraction(phone="9876543210"), "r3")
    assert by_phone.candidate_id == first.candidate_id
