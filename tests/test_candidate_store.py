"""Candidate store regressions, grouped by behavior."""

import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from sqlalchemy import event, func, select, text
from app.candidates import hashing
from app.candidates.schema import CandidateProfile, ExtractedStr, ExtractionResult
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from datetime import datetime, timezone
from app.candidates.extractor import heuristic_profile
from tests.conftest import make_candidate_store, set_extraction_created_at
from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.ledger.store import LedgerStore
from tests.test_candidate_login_binding_concurrency import blocked
from tests.test_report_erasure_concurrency import database  # noqa: F401


# Candidate store

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


@pytest.mark.parametrize("existing_email", [None, "victim@example.com"])
def test_unmatched_email_cannot_claim_candidate_through_phone(store, existing_email):
    victim = store.ingest(extraction(email=existing_email, phone="9876543210"), "victim")
    incoming = extraction(email="new@example.com", phone="9876543210")
    other = store.ingest(incoming, "other")
    assert other.candidate_id != victim.candidate_id
    assert store.get_candidate(victim.candidate_id).email_hash == (
        extraction(email=existing_email).profile.contact.email_hash
    )
    assert store.find_by_email_hash(incoming.profile.contact.email_hash) == other.candidate_id


def test_ambiguous_phone_does_not_choose_an_arbitrary_candidate(store):
    a = store.ingest(extraction(email="a@example.com", phone="9876543210"), "a")
    b = store.ingest(extraction(email="b@example.com", phone="9876543210"), "b")
    anonymous = store.ingest(extraction(phone="9876543210"), "unknown")
    assert anonymous.candidate_id not in {a.candidate_id, b.candidate_id}


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


@pytest.mark.parametrize("contact", ["email", "phone"])
@pytest.mark.parametrize("existing", [False, True], ids=["first-creation", "existing-subject"])
@pytest.mark.parametrize("upload", ["identical", "changed-text", "other-tenant"])
@pytest.mark.parametrize("rollback", [False, True], ids=["commit", "rollback"])
def test_competing_ingests_deduplicate_and_allocate_versions(
    database, monkeypatch, contact, existing, upload, rollback,
):
    engine, factory = database
    store = CandidateStore(factory)
    org_a = LedgerStore(factory).create_organization("Synthetic A").id
    org_b = LedgerStore(factory).create_organization("Synthetic B").id
    profile = extraction(**({"email": "ingest-race@example.com"} if contact == "email"
                            else {"phone": "9876543210"}))
    seed = store.ingest(profile, "seed", org_id=org_a) if existing else None
    first_factory, second_factory = make_session_factory(engine), make_session_factory(engine)
    first, second = CandidateStore(first_factory), CandidateStore(second_factory)
    ready, release, resolved = Event(), Event(), Event()
    pids, owner, lookups = [], [], []
    resolve = second._resolve_candidate

    def observe(session, incoming):
        result = resolve(session, incoming)
        lookups.append(result[0].id if result[0] else None)
        resolved.set()
        return result

    def hold(session, outcome):
        if engine.dialect.name == "postgresql":
            owner.append(session.connection().scalar(text("SELECT pg_backend_pid()")))
        ready.set()
        assert release.wait(20)
        if rollback:
            raise RuntimeError("synthetic ingest rollback")

    def started(session, transaction, connection):
        if engine.dialect.name == "postgresql":
            pids.append(connection.scalar(text("SELECT pg_backend_pid()")))

    monkeypatch.setattr(second, "_resolve_candidate", observe)
    event.listen(second_factory, "after_begin", started)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(first.ingest, profile, "same", org_id=org_a, before_commit=hold)
            try:
                assert ready.wait(20)
                two = pool.submit(second.ingest, profile,
                    "changed" if upload == "changed-text" else "same",
                    org_id=org_b if upload == "other-tenant" else org_a)
                assert resolved.wait(20)
                assert lookups[0] == (seed.candidate_id if seed else None)
                blocked(engine, two, owner[0] if owner else None, pids)
            finally:
                release.set()
            if rollback:
                with pytest.raises(RuntimeError, match="synthetic ingest rollback"):
                    one.result(timeout=20)
                saved = None
            else:
                saved = one.result(timeout=20)
            result = two.result(timeout=20)
    finally:
        event.remove(second_factory, "after_begin", started)

    if saved:
        assert result.candidate_id == saved.candidate_id
        assert result.duplicate_resume is (upload != "changed-text")
        assert (result.resume_id == saved.resume_id) is (upload == "identical")
        assert result.extraction_id != saved.extraction_id
    else:
        assert result.duplicate_resume is False
    if seed:
        assert result.candidate_id == seed.candidate_id
    assert result.matched_existing is (existing or not rollback)
    assert result.matched_on == (contact + "_hash" if result.matched_existing else None)
    count = int(existing) + 1 + int(not rollback and upload != "identical")
    assert result.resume_version == count
    with factory() as session:
        # The fixture's two unrelated subjects survive. No hidden split subject.
        assert session.scalar(select(func.count()).select_from(CandidateRow)) == 3
        resumes = session.scalars(select(ResumeRow).where(
            ResumeRow.candidate_id == result.candidate_id).order_by(ResumeRow.version)).all()
        assert [row.version for row in resumes] == list(range(1, count + 1))
        assert session.get(ResumeRow, result.resume_id).org_id == (
            org_b if upload == "other-tenant" else org_a)
        assert session.scalar(select(func.count()).select_from(ExtractionRow)) == (
            int(existing) + 1 + int(not rollback))
        assert session.get(CandidateRow, result.candidate_id).login_email_hash is None


def test_duplicate_asserted_emails_remain_distinct_and_unmodified(store):
    profile = extraction(email="ambiguous@example.com")
    with store._session_factory.begin() as session:
        session.add_all([CandidateRow(id=key, email_hash=profile.profile.contact.email_hash)
                         for key in ("one", "two")])
    first = store.ingest(profile, "same")
    second = store.ingest(profile, "same")
    assert len({"one", "two", first.candidate_id, second.candidate_id}) == 4
    assert not first.matched_existing and not second.matched_existing
    assert store.get_candidate("one").resume_count == 0
    assert store.get_candidate("two").resume_count == 0


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


# Candidate store asof

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark\nEmail: jane@example.com\n"


def _ingest(cs):
    return cs.ingest(
        ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
        resume_text=RESUME,
    ).candidate_id


def test_profile_as_of_none_before_first_extraction():
    cs = make_candidate_store()
    cid = _ingest(cs)
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert cs.profile_as_of(cid, datetime(2026, 1, 1, tzinfo=timezone.utc)) is None


def test_profile_as_of_returns_profile_after_extraction():
    cs = make_candidate_store()
    cid = _ingest(cs)
    set_extraction_created_at(cs, cid, datetime(2026, 5, 1, tzinfo=timezone.utc))
    prof = cs.profile_as_of(cid, datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert prof is not None
    assert prof.full_name  # heuristic pulled a name


def test_profile_as_of_unknown_candidate_is_none():
    cs = make_candidate_store()
    assert cs.profile_as_of("nope", datetime(2026, 6, 1, tzinfo=timezone.utc)) is None


# Candidate auth

def _new_candidate(store) -> str:
    with store._session_factory() as s:
        row = CandidateRow(full_name="Asha")
        s.add(row)
        s.commit()
        return row.id


@pytest.mark.parametrize('existing', [False, True], ids=['first-issue', 'rotation'])
def test_competing_key_issuance_serializes_one_credential_without_touching_profile(database, existing):
    from app.candidates.models import CandidateCredentialRow
    engine, factory = database
    store = CandidateStore(factory)
    if existing:
        store.issue_access_key('a')
    survivor = store.issue_access_key('b')
    with factory() as session:
        before = session.get(CandidateRow, 'a').updated_at
    ready, release, started = Event(), Event(), Event()
    owner, pids = [], []
    def pause(conn, cursor, statement, parameters, context, many):
        target = ('UPDATE CANDIDATE_CREDENTIALS' if existing else 'INSERT INTO CANDIDATE_CREDENTIALS')
        if statement.lstrip().upper().startswith(target) and not ready.is_set():
            if engine.dialect.name == 'postgresql':
                owner.append(conn.scalar(text('SELECT pg_backend_pid()')))
            ready.set()
            assert release.wait(15)
    def begin(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
        started.set()
    event.listen(engine, 'before_cursor_execute', pause)
    event.listen(factory, 'after_begin', begin)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(store.issue_access_key, 'a')
            try:
                assert ready.wait(8)
                started.clear()
                pids.clear()
                second = pool.submit(store.issue_access_key, 'a')
                assert started.wait(8)
                blocked(engine, second, owner[0] if owner else None, pids)
            finally:
                release.set()
            earlier, later = first.result(timeout=8), second.result(timeout=8)
        assert store.authenticate_candidate(earlier) is None
        assert store.authenticate_candidate(later) == 'a'
        assert store.authenticate_candidate(survivor) == 'b'
        with factory() as session:
            assert session.get(CandidateRow, 'a').updated_at == before
            assert session.scalar(select(func.count()).select_from(CandidateCredentialRow).where(CandidateCredentialRow.candidate_id == 'a')) == 1
    finally:
        release.set()
        event.remove(engine, 'before_cursor_execute', pause)
        event.remove(factory, 'after_begin', begin)


def test_issue_and_authenticate_roundtrip():
    store = make_candidate_store()
    cid = _new_candidate(store)
    key = store.issue_access_key(cid)
    assert isinstance(key, str) and key
    assert store.authenticate_candidate(key) == cid


@pytest.mark.parametrize('order', ['issue-first', 'erase-first'])
@pytest.mark.parametrize('existing', [False, True], ids=['first-issue', 'rotation'])
def test_candidate_key_issuance_and_erasure_have_one_order(database, order, existing):
    from app.candidates.models import CandidateCredentialRow
    engine, factory = database
    store = CandidateStore(factory)
    if existing:
        store.issue_access_key('a')
    survivor = store.issue_access_key('b')
    issuer_factory, eraser_factory = make_session_factory(engine), make_session_factory(engine)
    issuer, eraser = CandidateStore(issuer_factory), CandidateStore(eraser_factory)
    ready, release, started = Event(), Event(), Event()
    owner, pids = [], []
    def pause(session, *args):
        if engine.dialect.name == 'postgresql':
            owner.append(session.connection().scalar(text('SELECT pg_backend_pid()')))
        ready.set()
        assert release.wait(15)
    def begin(session, transaction, connection):
        if engine.dialect.name == 'postgresql':
            pids.append(connection.scalar(text('SELECT pg_backend_pid()')))
        started.set()
    first_factory = issuer_factory if order == 'issue-first' else eraser_factory
    second_factory = eraser_factory if order == 'issue-first' else issuer_factory
    event.listen(first_factory, 'after_flush', pause)
    event.listen(second_factory, 'after_begin', begin)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(issuer.issue_access_key if order == 'issue-first' else eraser.delete_candidate, 'a')
            try:
                assert ready.wait(8)
                second = pool.submit(eraser.delete_candidate if order == 'issue-first' else issuer.issue_access_key, 'a')
                assert started.wait(8)
                blocked(engine, second, owner[0] if owner else None, pids)
            finally:
                release.set()
            if order == 'issue-first':
                raw = first.result(timeout=8)
                assert second.result(timeout=8)
                assert store.authenticate_candidate(raw) is None
            else:
                assert first.result(timeout=8)
                with pytest.raises(LookupError):
                    second.result(timeout=8)
        assert store.get_candidate('a') is None
        assert store.authenticate_candidate(survivor) == 'b'
        with factory() as session:
            assert session.scalar(select(CandidateCredentialRow).where(CandidateCredentialRow.candidate_id == 'a')) is None
    finally:
        release.set()
        event.remove(first_factory, 'after_flush', pause)
        event.remove(second_factory, 'after_begin', begin)


@pytest.mark.parametrize('existing', [False, True], ids=['first-issue', 'rotation'])
def test_candidate_key_write_failure_rolls_back_credential(database, existing):
    from app.candidates.models import CandidateCredentialRow
    _, factory = database
    store = CandidateStore(factory)
    old = store.issue_access_key('a') if existing else None
    survivor = store.issue_access_key('b')
    def fail(session, *args):
        raise RuntimeError('synthetic key flush failure')
    event.listen(factory, 'after_flush', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic key flush failure'):
            store.issue_access_key('a')
    finally:
        event.remove(factory, 'after_flush', fail)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(CandidateCredentialRow).where(CandidateCredentialRow.candidate_id == 'a')) == int(existing)
    if old:
        assert store.authenticate_candidate(old) == 'a'
    assert store.authenticate_candidate(survivor) == 'b'
    assert store.authenticate_candidate(store.issue_access_key('a')) == 'a'


def test_authenticate_rejects_bad_and_empty_keys():
    store = make_candidate_store()
    cid = _new_candidate(store)
    store.issue_access_key(cid)
    assert store.authenticate_candidate("nope") is None
    assert store.authenticate_candidate("") is None
    assert store.authenticate_candidate("   ") is None


def test_issue_rotates_and_old_key_dies():
    store = make_candidate_store()
    cid = _new_candidate(store)
    k1 = store.issue_access_key(cid)
    k2 = store.issue_access_key(cid)
    assert k1 != k2
    assert store.authenticate_candidate(k1) is None   # rotated out
    assert store.authenticate_candidate(k2) == cid
    # still exactly one credential row (unique candidate_id upsert, not append)
    from app.candidates.models import CandidateCredentialRow
    from sqlalchemy import select, func
    with store._session_factory() as s:
        n = s.execute(
            select(func.count()).select_from(CandidateCredentialRow)
            .where(CandidateCredentialRow.candidate_id == cid)
        ).scalar()
    assert n == 1


def test_issue_unknown_candidate_raises():
    store = make_candidate_store()
    with pytest.raises(LookupError):
        store.issue_access_key("does-not-exist")


def test_credential_cascades_on_candidate_delete():
    store = make_candidate_store()
    cid = _new_candidate(store)
    key = store.issue_access_key(cid)
    assert store.delete_candidate(cid) is True
    assert store.authenticate_candidate(key) is None  # credential gone with candidate
