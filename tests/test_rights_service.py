"""RightsService (S8.3 Phase B): request, review, decide, record, disclose.

Every fixture here builds the REAL limiter and the REAL stores over one
in-memory engine. A permissive stand-in limiter would let the rate-limit tests
pass while the service ran unbounded, which is Phase A's lesson exactly: a fake
that cannot enforce an invariant will hide it.
"""

from datetime import datetime, timezone

import pytest

from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.store import LedgerStore
from app.ratelimit.service import RateLimited, build_rate_limiter
from app.rights.schema import (
    CorrectionField, RequestAlreadyResolved, RequestKind, RequestRefused,
    RequestStatus, ResolvedBy,
)
from app.rights.service import RightsService
from app.rights.store import RightsStore

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


@pytest.fixture
def wired(settings):
    """One engine, every store on it, and the real limiter."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    candidates = CandidateStore(factory)
    ledger = LedgerStore(factory)
    service = RightsService(
        RightsStore(factory),
        candidates,
        ledger,
        limiter=build_rate_limiter(settings, factory),
        settings=settings,
    )
    return service, candidates, ledger


@pytest.fixture
def rights(wired):
    return wired[0]


@pytest.fixture
def candidates(wired):
    return wired[1]


@pytest.fixture
def ledger(wired):
    return wired[2]


@pytest.fixture
def candidate_id(candidates):
    from app.candidates.models import CandidateRow

    with candidates._session_factory() as s:
        row = CandidateRow(full_name="Asha R")
        s.add(row)
        s.commit()
        return row.id


def _correction(rights, candidate_id, **over):
    kwargs = dict(
        kind=RequestKind.CORRECTION, field=CorrectionField.FULL_NAME,
        requested_value="Asha Rao", note="", now=NOW,
    )
    kwargs.update(over)
    return rights.submit(candidate_id, **kwargs)


def _grievance(rights, candidate_id, note="nobody answered"):
    return rights.submit(candidate_id, kind=RequestKind.GRIEVANCE, field=None,
                         requested_value="", note=note, now=NOW)


# ── submission ───────────────────────────────────────────────────────────────


def test_a_correction_requires_a_requested_value(rights, candidate_id):
    with pytest.raises(RequestRefused):
        _correction(rights, candidate_id, requested_value="   ")


def test_a_correction_requires_a_field(rights, candidate_id):
    with pytest.raises(RequestRefused):
        _correction(rights, candidate_id, field=None)


def test_the_field_other_requires_a_note(rights, candidate_id):
    """`other` can never be auto-applied, so the note IS the request -- without
    it an operator has a row naming a field nobody can act on."""
    with pytest.raises(RequestRefused):
        _correction(rights, candidate_id, field=CorrectionField.OTHER,
                    requested_value="x", note="")


def test_a_grievance_requires_a_note_and_carries_no_field(rights, candidate_id):
    with pytest.raises(RequestRefused):
        _grievance(rights, candidate_id, note="")
    view = _grievance(rights, candidate_id)
    assert view.field is None
    assert view.kind is RequestKind.GRIEVANCE


def test_the_note_is_bounded_by_max_request_note_chars(rights, candidate_id, settings):
    """The S8.5 outcome-notes argument one table over: free text typed by a
    person about their own record, into an unbounded Text column."""
    with pytest.raises(RequestRefused):
        _grievance(rights, candidate_id,
                   note="x" * (settings.max_request_note_chars + 1))


def test_the_requested_value_is_bounded_too(rights, candidate_id, settings):
    with pytest.raises(RequestRefused):
        _correction(rights, candidate_id,
                    requested_value="x" * (settings.max_request_note_chars + 1))


def test_the_submission_captures_the_CURRENT_value_at_request_time(
    rights, candidate_id, candidates
):
    """What the operator reviews is the pair the SUBJECT saw, not whatever the
    row says by the time somebody gets to it."""
    view = _correction(rights, candidate_id)
    assert view.current_value == "Asha R"
    candidates.apply_correction(candidate_id, full_name="Someone Else")
    assert rights.for_candidate(candidate_id)[0].current_value == "Asha R"


def test_an_email_correction_records_NO_current_value(rights, candidate_id):
    """We hold email_hash, never the address. Echoing a blank is honest; making
    one up, or reflecting the requested value back as 'current', would put a
    fabricated fact in front of the operator deciding."""
    view = _correction(rights, candidate_id, field=CorrectionField.EMAIL,
                       requested_value="new@example.com")
    assert view.current_value == ""


def test_a_submission_is_audited_onto_the_SUBJECTS_own_log(rights, candidate_id,
                                                           ledger):
    """S3.1's rule -- surveillance is itself observable -- applied to the
    handling of the subject's own complaint, which is where it matters most."""
    _grievance(rights, candidate_id)
    entries = ledger.audit_for_candidate(candidate_id)
    assert [e.entity_type for e in entries] == ["data_principal_request"]
    assert entries[0].action == "request.submit"


# ── resolution ───────────────────────────────────────────────────────────────


def test_resolving_a_full_name_correction_with_apply_writes_the_candidate_row(
    rights, candidate_id, candidates
):
    view = _correction(rights, candidate_id)
    out = rights.resolve(view.id, status=RequestStatus.RESOLVED,
                         resolution="verified against the payslip", apply=True,
                         resolved_by=ResolvedBy.OPERATOR_KEY, admin_user_id=None,
                         now=NOW)
    assert out.applied is True
    assert out.status is RequestStatus.RESOLVED
    assert candidates.get_candidate(candidate_id).full_name == "Asha Rao"


def test_an_email_correction_is_REFUSED_for_auto_apply_naming_its_reason(
    rights, candidate_id
):
    """Not 'not implemented': email_hash is the dedup key AND the portal login
    credential, so changing it is an identity operation that can collide two
    candidate rows or move an account's login address."""
    view = _correction(rights, candidate_id, field=CorrectionField.EMAIL,
                       requested_value="new@example.com")
    with pytest.raises(RequestRefused) as exc:
        rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="ok",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)
    assert "email" in str(exc.value)
    assert "login" in str(exc.value).lower()


def test_a_phone_correction_is_refused_for_auto_apply_too(rights, candidate_id):
    view = _correction(rights, candidate_id, field=CorrectionField.PHONE,
                       requested_value="+91 99999 99999")
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="ok",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_an_email_correction_can_still_be_RESOLVED_without_apply(rights, candidate_id):
    """The mechanism is complete for all four fields. Auto-apply is a
    convenience for the one field where it is safe, not the mechanism itself."""
    view = _correction(rights, candidate_id, field=CorrectionField.EMAIL,
                       requested_value="new@example.com")
    out = rights.resolve(view.id, status=RequestStatus.RESOLVED,
                         resolution="changed by hand after an ID check",
                         apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                         admin_user_id=None, now=NOW)
    assert out.status is RequestStatus.RESOLVED
    assert out.applied is False


def test_applying_a_grievance_is_refused(rights, candidate_id):
    view = _grievance(rights, candidate_id)
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="sorry",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_applying_a_REJECTED_request_is_refused(rights, candidate_id):
    """A rejection that writes the value is a contradiction the subject would
    read as an approval."""
    view = _correction(rights, candidate_id)
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, status=RequestStatus.REJECTED, resolution="no",
                       apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_a_rejection_records_the_reason_and_leaves_the_row_alone(
    rights, candidate_id, candidates
):
    view = _correction(rights, candidate_id, requested_value="Someone Else")
    out = rights.resolve(view.id, status=RequestStatus.REJECTED,
                         resolution="the name does not match the submitted ID",
                         apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                         admin_user_id=None, now=NOW)
    assert out.status is RequestStatus.REJECTED
    assert out.applied is False
    assert out.resolution
    assert candidates.get_candidate(candidate_id).full_name == "Asha R"


def test_a_rejection_may_NOT_be_silent(rights, candidate_id):
    """DPDP's mechanism is request-review-decide-RECORD-disclose. A refusal
    with no written reason is a decision the subject cannot act on, which is
    the one thing a grievance process must never be."""
    view = _correction(rights, candidate_id)
    with pytest.raises(RequestRefused):
        rights.resolve(view.id, status=RequestStatus.REJECTED, resolution="   ",
                       apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_resolving_twice_is_RequestAlreadyResolved(rights, candidate_id):
    view = _grievance(rights, candidate_id)
    kwargs = dict(status=RequestStatus.RESOLVED, resolution="done", apply=False,
                  resolved_by=ResolvedBy.OPERATOR_KEY, admin_user_id=None, now=NOW)
    rights.resolve(view.id, **kwargs)
    with pytest.raises(RequestAlreadyResolved):
        rights.resolve(view.id, **kwargs)


def test_resolving_an_unknown_request_raises_LookupError(rights):
    with pytest.raises(LookupError):
        rights.resolve("nope", status=RequestStatus.RESOLVED, resolution="x",
                       apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)


def test_a_resolution_is_audited_onto_the_subjects_log_too(rights, candidate_id,
                                                           ledger):
    view = _grievance(rights, candidate_id)
    rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="called them",
                   apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                   admin_user_id=None, now=NOW)
    actions = [
        e.action for e in ledger.audit_for_candidate(candidate_id)
        if e.entity_type == "data_principal_request"
    ]
    assert actions == ["request.submit", "request.resolve"]


def test_an_APPLIED_correction_NEVER_touches_an_extraction(
    rights, candidate_id, candidates
):
    """THE LOAD-BEARING RULE OF THIS PHASE. An extractions row records what a
    DOCUMENT said. The subject of a correction is exactly the person with an
    incentive to edit a claim that got flagged, so the evidence is immutable
    and only the candidate's own identity column moves."""
    from app.candidates.models import ExtractionRow, ResumeRow
    from app.candidates.schema import CandidateProfile, ExtractedStr

    profile = CandidateProfile(full_name=ExtractedStr(value="Asha R"))
    with candidates._session_factory() as s:
        resume = ResumeRow(candidate_id=candidate_id, version=1, raw_text="x",
                           text_sha256="a" * 64)
        s.add(resume)
        s.flush()
        s.add(ExtractionRow(
            resume_id=resume.id, candidate_id=candidate_id, method="heuristic",
            profile=profile.model_dump(mode="json"), warnings=[],
        ))
        s.commit()

    before = candidates.latest_profile(candidate_id)
    view = _correction(rights, candidate_id)
    rights.resolve(view.id, status=RequestStatus.RESOLVED, resolution="ok",
                   apply=True, resolved_by=ResolvedBy.OPERATOR_KEY,
                   admin_user_id=None, now=NOW)
    assert candidates.latest_profile(candidate_id) == before
    assert candidates.get_candidate(candidate_id).full_name == "Asha Rao"


# ── the bound ────────────────────────────────────────────────────────────────


def test_submitting_is_rate_limited_per_candidate(rights, candidate_id, settings):
    limit = settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        _grievance(rights, candidate_id, note=f"n{i}")
    with pytest.raises(RateLimited):
        _grievance(rights, candidate_id, note="over")


def test_a_CORRECTION_spends_the_SAME_budget_as_a_grievance(rights, candidate_id,
                                                            settings):
    """One rule over both candidate-plane writes. Limiting one of two sibling
    doors is this repo's signature defect, and the spec's grievance-only sketch
    would have left the correction unbounded."""
    limit = settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        _correction(rights, candidate_id, requested_value=f"Name {i}")
    with pytest.raises(RateLimited):
        _grievance(rights, candidate_id, note="over")


def test_the_limit_is_charged_BEFORE_the_row_is_written(rights, candidate_id,
                                                        settings):
    """A bound that runs after the work it bounds is the S8.4 Phase B finding
    (4) shape. Here it would leave the refused request stored."""
    limit = settings.rate_limit_request_per_hour_per_candidate
    for i in range(limit):
        _grievance(rights, candidate_id, note=f"n{i}")
    with pytest.raises(RateLimited):
        _grievance(rights, candidate_id, note="over")
    assert len(rights.for_candidate(candidate_id)) == limit


def test_an_INVALID_submission_still_spends_the_budget(rights, candidate_id,
                                                       settings):
    """The limiter is charged BEFORE validation, and this is the trade-off
    written down rather than discovered.

    A typo costs one of ten complaints an hour, which is the smaller harm. The
    alternative -- validate first, charge only the valid -- leaves an endpoint
    a stuck client can hammer FOREVER at zero cost by sending a body that never
    passes validation, which is exactly the surface the limiter exists for.
    Bounding only the successful call is not bounding the caller.
    """
    limit = settings.rate_limit_request_per_hour_per_candidate
    for _ in range(limit):
        with pytest.raises(RequestRefused):
            _grievance(rights, candidate_id, note="")
    with pytest.raises(RateLimited):
        _grievance(rights, candidate_id, note="a perfectly valid complaint")


def test_resolving_is_NOT_rate_limited(rights, candidate_id, settings):
    """The bound is on the door a stuck CLIENT loops on. An operator clearing
    a backlog of a hundred complaints is the behaviour we want."""
    views = [
        _grievance(rights, candidate_id, note=f"n{i}")
        for i in range(settings.rate_limit_request_per_hour_per_candidate)
    ]
    for v in views:
        rights.resolve(v.id, status=RequestStatus.RESOLVED, resolution="done",
                       apply=False, resolved_by=ResolvedBy.OPERATOR_KEY,
                       admin_user_id=None, now=NOW)
    assert all(v.status is RequestStatus.RESOLVED
               for v in rights.for_candidate(candidate_id))
