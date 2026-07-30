from datetime import datetime, timezone

from app.curation.schema import CurationAction, CurationStatus, UnmappedTerm


def test_status_and_action_values():
    assert [s.value for s in CurationStatus] == ["pending", "resolved", "ignored"]
    assert [a.value for a in CurationAction] == ["map", "create", "ignore"]


def test_unmapped_term_defaults_pending_no_resolution():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    t = UnmappedTerm(
        norm_key="cobol", display_name="COBOL", source_types=["linkedin_export"],
        first_seen=now, last_seen=now,
    )
    assert t.status == CurationStatus.PENDING
    assert t.occurrences == 1
    assert t.action is None and t.canonical is None and t.category is None


def test_unmapped_term_carries_resolution():
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    t = UnmappedTerm(
        norm_key="cobol", display_name="COBOL", first_seen=now, last_seen=now,
        status=CurationStatus.RESOLVED, action=CurationAction.CREATE,
        canonical="cobol", category="language", decided_by="ops", decided_at=now,
    )
    assert t.action == CurationAction.CREATE and t.canonical == "cobol"
