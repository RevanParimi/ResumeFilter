"""Pure retention-posture helpers (S6.4). No I/O. The portal surfaces the policy
window per data class and a computed `retained_until` for the classes it
materializes; the mechanical purge is deferred to PI-8 (`sweep_active=False`)."""

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
    "interview_records": "ret_interview_record_days",
    "coding_rounds": "ret_coding_round_days",
    "observed_offers": "ret_observed_offer_days",
    "audit_log": "ret_audit_log_days",
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
    return RetentionPolicy(windows=windows, sweep_active=False)
