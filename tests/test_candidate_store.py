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


def test_get_candidate_summary(store):
    out = store.ingest(extraction(name="Asha Rao", email="asha@example.com"), "r1")
    store.ingest(extraction(name="Asha R. Rao", email="asha@example.com"), "r2")
    summary = store.get_candidate(out.candidate_id)
    assert summary is not None
    assert summary.full_name == "Asha R. Rao"  # latest resume's name wins
    assert summary.resume_count == 2
    assert summary.email_hash
    assert store.get_candidate("missing-id") is None


def test_latest_profile_comes_from_newest_resume_version(store):
    out = store.ingest(extraction(name="Asha Rao", email="asha@example.com"), "r1")
    store.ingest(extraction(name="Asha R. Rao", email="asha@example.com"), "r2")
    profile = store.latest_profile(out.candidate_id)
    assert profile is not None
    assert profile.full_name.value == "Asha R. Rao"
    assert store.latest_profile("missing-id") is None


def test_list_resumes_ordered_by_version(store):
    out = store.ingest(extraction(email="a@x.com"), "r1")
    store.ingest(extraction(email="a@x.com"), "r2")
    resumes = store.list_resumes(out.candidate_id)
    assert [r.version for r in resumes] == [1, 2]
    assert all(len(r.text_sha256) == 64 for r in resumes)


def test_delete_candidate_erases_everything(store):
    out = store.ingest(extraction(email="a@x.com"), "r1")
    assert store.delete_candidate(out.candidate_id) is True
    assert store.get_candidate(out.candidate_id) is None
    assert store.list_resumes(out.candidate_id) == []
    assert store.delete_candidate(out.candidate_id) is False


def test_delete_resume_keeps_candidate(store):
    out = store.ingest(extraction(email="a@x.com"), "r1")
    second = store.ingest(extraction(email="a@x.com"), "r2")
    assert store.delete_resume(second.resume_id) is True
    assert [r.version for r in store.list_resumes(out.candidate_id)] == [1]
    assert store.get_candidate(out.candidate_id) is not None
    assert store.delete_resume(second.resume_id) is False


def test_build_candidate_store_from_settings(settings):
    from app.candidates.store import build_candidate_store

    store = build_candidate_store(settings.model_copy(update={"candidates_db_url": "sqlite://"}))
    assert isinstance(store, CandidateStore)
