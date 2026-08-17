"""Pure retention-posture helpers (S6.4, mechanised in S8.3 Phase B). No I/O.

The portal surfaces the policy window per data class and a computed
`retained_until` for the classes it materializes.

RETENTION_KNOBS is the SINGLE source of the retention promise: the portal prints
it, and since S8.3 Phase B `app/retention/plan.py` derives the sweeper's targets
from it. A sweeper carrying its own list of targets would let the two drift, and
the drift is silent in the worst direction -- the portal would keep promising a
window that nothing enforces.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.core.config import Settings
from app.ledger.consent import as_utc
from app.portal.schema import RetentionPolicy, RetentionWindow

# data_class -> Settings attribute holding its TTL in days.
RETENTION_KNOBS: dict[str, str] = {
    "resumes": "ret_resume_days",
    "profile_sources": "ret_profile_source_days",
    "verifications": "ret_verification_days",
    "interviews": "ret_interview_session_days",
    "interview_records": "ret_interview_record_days",
    "coding_rounds": "ret_coding_round_days",
    "observed_offers": "ret_observed_offer_days",
    "audit_log": "ret_audit_log_days",
    # S8.3 Phase B. DISCLOSED BECAUSE THEY ARE ENFORCED: a window we sweep and
    # do not print is the mirror image of the bug this sprint fixes. Each is
    # genuinely about the person reading it -- `batch_item_text` is a copy of
    # their own resume text, `rate_limit_counters` holds a salted hash of their
    # email beside one of their IP, `login_state` is their abandoned login
    # attempts and expired sessions.
    "batch_item_text": "ret_batch_item_days",
    "rate_limit_counters": "ret_rate_limit_days",
    "login_state": "ret_login_state_days",
}


def retained_until(oldest_at: datetime, ttl_days: int) -> datetime:
    """When the oldest item in a class ages out under the policy (aware UTC)."""
    return as_utc(oldest_at) + timedelta(days=ttl_days)


def build_retention_policy(
    oldest_by_class: dict[str, Optional[datetime]], settings: Settings
) -> RetentionPolicy:
    """Every class appears (ttl_days = the policy). `oldest_item_at` /
    `retained_until` are filled only where the caller supplied an oldest
    timestamp (classes the portal materializes); others stay policy-only."""
    windows: list[RetentionWindow] = []
    for data_class, attr in RETENTION_KNOBS.items():
        ttl = getattr(settings, attr)
        oldest = oldest_by_class.get(data_class)
        windows.append(
            RetentionWindow(
                data_class=data_class,
                ttl_days=ttl,
                oldest_item_at=oldest,
                retained_until=retained_until(oldest, ttl) if oldest else None,
            )
        )
    return RetentionPolicy(
        windows=windows, sweep_active=settings.retention_sweep_enabled
    )
