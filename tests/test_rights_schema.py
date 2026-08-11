"""DPDP rights: the pure types (S8.3 Phase B, spec §8)."""

from app.rights.schema import (
    AUTO_APPLIABLE_FIELDS,
    CorrectionField,
    RequestAlreadyResolved,
    RequestKind,
    RequestRefused,
    RequestStatus,
    ResolvedBy,
)


def test_only_full_name_is_auto_appliable():
    """email and phone are hashed into the dedup keys _resolve_candidate
    matches on, and email_hash is additionally the portal login credential.
    Changing either is an IDENTITY operation that can collide two candidate
    rows or move an account's login address -- not a data correction."""
    assert AUTO_APPLIABLE_FIELDS == frozenset({CorrectionField.FULL_NAME})


def test_the_four_correction_fields_are_named():
    assert {f.value for f in CorrectionField} == {
        "full_name", "email", "phone", "other"
    }


def test_status_and_applied_are_two_facts_so_status_has_only_three_members():
    """A four-member enum folding `applied` in would leave 'is an applied
    correction also resolved?' answerable two ways, and the subject's own view
    of their request is the last place to be vague about whether anything
    changed."""
    assert {s.value for s in RequestStatus} == {"open", "resolved", "rejected"}


def test_resolution_authorship_distinguishes_a_machine_key_from_a_person():
    """The S8.5 `recorded_by` argument, one table over: a null admin_user_id
    alone would conflate 'an operator using the shared key decided this' with
    'the admin who decided it has since been deleted'."""
    assert {r.value for r in ResolvedBy} == {"operator_key", "admin_user"}


def test_both_kinds_exist():
    assert {k.value for k in RequestKind} == {"correction", "grievance"}


def test_already_resolved_is_a_SUBCLASS_so_a_handler_can_tell_them_apart():
    """The HTTP layer answers 409 here and 422 for every other refusal, and
    choosing between them by matching on message text is a translation that
    breaks the first time somebody rewords a sentence."""
    assert issubclass(RequestAlreadyResolved, RequestRefused)
