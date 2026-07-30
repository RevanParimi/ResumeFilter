from datetime import datetime, timezone

from app.portal.schema import (
    AccessLogEntry, ConsentState, ConsentView, MyData, ReportRef,
    RetentionPolicy, RetentionWindow,
)
from app.ledger.schema import ConsentGrant, ConsentPurpose


def test_retention_window_and_policy_shapes():
    w = RetentionWindow(data_class="resumes", ttl_days=1095,
                        oldest_item_at=None, retained_until=None)
    p = RetentionPolicy(windows=[w])
    assert p.sweep_active is False           # honest: posture only, no purge
    assert p.windows[0].data_class == "resumes"


def test_report_ref_is_existence_only():
    r = ReportRef(report_id="rep_1", domain="genai",
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    # No verdicts / fabrication fields on the ref.
    assert set(r.model_dump().keys()) == {"report_id", "domain", "created_at"}


def test_consent_view_wraps_grant_and_state():
    g = ConsentGrant(id="c1", candidate_id="cand1", purpose=ConsentPurpose.LEDGER_READ,
                     granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                     expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    v = ConsentView(grant=g, state=ConsentState.ACTIVE)
    assert v.grant.id == "c1" and v.state == "active"


def test_my_data_defaults_are_empty_collections():
    md = MyData(candidate_id="cand1", retention=RetentionPolicy(windows=[]))
    assert md.resumes == [] and md.interview_records == [] and md.reports == []
    assert md.profile is None
