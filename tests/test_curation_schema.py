from datetime import datetime, timezone

from app.curation.schema import CurationAction, CurationDecision, CurationStatus, UnmappedTerm


def test_status_and_action_values():
    assert [s.value for s in CurationStatus] == ["pending", "resolved", "ignored"]
    assert [a.value for a in CurationAction] == ["map", "create", "ignore"]


def test_unmapped_term_defaults_pending_no_resolution():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    t = UnmappedTerm(
        norm_key="cobol", display_name="COBOL", source_types=["linkedin_export"],
        first_seen=now, last_seen=now,
        review_revision="0" * 64,
    )
    assert t.status == CurationStatus.PENDING
    assert t.occurrences == 1
    assert "note" not in t.model_dump() and "decided_by" not in t.model_dump()


def test_decision_receipt_contains_approved_vocabulary_only():
    from dataclasses import asdict
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    receipt = CurationDecision(CurationAction.CREATE, "Approved COBOL", "cobol", "language", now, None)
    assert set(asdict(receipt)) == {"action", "alias", "canonical", "category", "decided_at", "admin_user_id"}
