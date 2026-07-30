"""Candidate DPDP portal service (S6.4). Pure composition over CandidateStore +
LedgerStore + ReportStore + ProfileSourceService. Owns no tables/state. Every
method operates on ONE candidate_id (resolved from the caller's key upstream);
self-access needs no org consent. Reports surface as refs (no internals)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.ledger.consent import as_utc
from app.ledger.schema import ConsentGrant, ConsentPurpose
from app.ledger.store import LedgerStore
from app.portal.retention import build_retention_policy
from app.portal.schema import (
    AccessLogEntry, ConsentState, ConsentView, MyData, ReportRef,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortalService:
    def __init__(
        self,
        candidates: CandidateStore,
        ledger: LedgerStore,
        report_store,
        profile_sources,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self._candidates = candidates
        self._ledger = ledger
        self._report_store = report_store
        self._profile_sources = profile_sources
        self._settings = settings or get_settings()

    def my_data(self, candidate_id: str) -> MyData:
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")
        resumes = self._candidates.list_resumes(candidate_id)
        sources = self._profile_sources.list_sources(candidate_id)
        records = self._ledger.records_for_candidate(candidate_id)
        coding = self._ledger.coding_rounds_for_candidate(candidate_id)
        reports = [
            ReportRef(report_id=r.id, domain=r.domain, created_at=r.created_at)
            for r in self._report_store.for_candidate(candidate_id)
        ]
        oldest = {
            "resumes": min((r.created_at for r in resumes), default=None),
            "profile_sources": min((s.fetched_at for s in sources), default=None),
            "interview_records": min((r.created_at for r in records), default=None),
            "coding_rounds": min((c.created_at for c in coding), default=None),
        }
        return MyData(
            candidate_id=candidate_id,
            profile=self._candidates.latest_profile(candidate_id),
            resumes=resumes,
            sources=sources,
            interview_records=records,
            coding_rounds=coding,
            reports=reports,
            consents=self._ledger.consents_for_candidate(candidate_id),
            retention=build_retention_policy(oldest, self._settings),
        )

    def access_log(self, candidate_id: str) -> list[AccessLogEntry]:
        entries = self._ledger.audit_for_candidate(candidate_id)  # ascending
        names: dict[str, Optional[str]] = {}
        out: list[AccessLogEntry] = []
        for e in reversed(entries):  # newest first
            actor_name: Optional[str] = None
            if e.actor_type == "org" and e.actor_id:
                if e.actor_id not in names:
                    org = self._ledger.get_organization(e.actor_id)
                    names[e.actor_id] = org.name if org else None
                actor_name = names[e.actor_id]
            out.append(
                AccessLogEntry(
                    at=e.created_at,
                    actor_type=e.actor_type,
                    actor_id=e.actor_id,
                    actor_name=actor_name,
                    action=e.action,
                    allowed=e.details.get("allowed"),
                    entity_type=e.entity_type,
                )
            )
        return out

    def consents(self, candidate_id: str, *, now: Optional[datetime] = None) -> list[ConsentView]:
        moment = as_utc(now) if now else _utcnow()
        return [
            ConsentView(grant=g, state=self._state(g, moment))
            for g in self._ledger.consents_for_candidate(candidate_id)
        ]

    @staticmethod
    def _state(grant: ConsentGrant, now: datetime) -> ConsentState:
        if grant.revoked_at is not None:
            return ConsentState.REVOKED
        if as_utc(grant.expires_at) <= now:
            return ConsentState.EXPIRED
        return ConsentState.ACTIVE

    def grant(
        self,
        candidate_id: str,
        *,
        purpose: ConsentPurpose,
        org_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> ConsentGrant:
        return self._ledger.grant_consent(
            candidate_id=candidate_id, purpose=purpose, org_id=org_id, expires_at=expires_at
        )

    def revoke(self, candidate_id: str, consent_id: str) -> bool:
        grant = self._ledger.get_grant(consent_id)
        if grant is None or grant.candidate_id != candidate_id:
            # Same error whether missing or not-owned: a candidate can't probe
            # for another's grant ids.
            raise LookupError(f"unknown consent grant for candidate: {consent_id}")
        return self._ledger.revoke_consent(consent_id)


def build_portal_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
    report_store,
    profile_sources,
) -> PortalService:
    return PortalService(
        candidates, ledger, report_store, profile_sources,
        settings=settings or get_settings(),
    )
