"""Ledger store — organizations, consent lifecycle, audit trail (S3.1).

Every mutation writes its audit row inside the same transaction: an action
that committed is an action that was audited, atomically. Consent decisions
delegate to the pure ``app.ledger.consent`` module; the store only loads the
candidate's grant rows and converts them to contracts.

Actor model (S3.1, pre-auth): consent mutations are attributed to the
candidate (the DPDP data principal), record submissions to the org, and
org management to "system". Org-scoped API keys arrive in S3.2.

DPDP: erasure is NOT this store's job — every candidate-linked ledger row
cascades away when ``CandidateStore.delete_candidate`` deletes the candidate
(proven in tests). ``delete_organization`` is the org-side delete path.

Row-to-contract converters run every timestamp through ``consent.as_utc``:
a row built and returned within the same flush (before commit re-reads it)
carries the Python-side aware datetime, but a row fetched fresh from SQLite
comes back naive (see ``app.ledger.consent`` for why) — without normalizing,
two contracts for the same row would compare unequal depending on which
session produced them.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger import consent as consent_logic
from app.ledger.models import (
    AuditLogRow,
    CodingRoundResultRow,
    ConsentGrantRow,
    EvaluationEventRow,
    InterviewRecordRow,
    ObservedOfferRow,
    OrganizationRow,
)
from app.ledger.reputation import assess_reputation
from app.ledger.schema import (
    AuditEntry,
    CodingPlatform,
    CodingRoundResult,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    ObservedOffer,
    ObservedOfferPoint,
    Organization,
    ReputationAssessment,
)


class ConsentError(RuntimeError):
    """A write needed consent that is not currently active."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _org(row: OrganizationRow) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        status=row.status,
        reliability_weight=(
            row.reliability_weight if row.reliability_weight is not None else 1.0
        ),
        created_at=consent_logic.as_utc(row.created_at),
    )


def _grant(row: ConsentGrantRow) -> ConsentGrant:
    return ConsentGrant(
        id=row.id,
        candidate_id=row.candidate_id,
        org_id=row.org_id,
        purpose=ConsentPurpose(row.purpose),
        granted_at=consent_logic.as_utc(row.granted_at),
        expires_at=consent_logic.as_utc(row.expires_at),
        revoked_at=consent_logic.as_utc(row.revoked_at) if row.revoked_at else None,
    )


def _record(row: InterviewRecordRow) -> InterviewRecord:
    return InterviewRecord(
        id=row.id,
        org_id=row.org_id,
        candidate_id=row.candidate_id,
        consent_id=row.consent_id,
        stage=InterviewStage(row.stage),
        outcome=InterviewOutcome(row.outcome),
        interviewed_at=consent_logic.as_utc(row.interviewed_at),
        summary=row.summary,
        created_at=consent_logic.as_utc(row.created_at),
    )


def _event(row: EvaluationEventRow) -> EvaluationEvent:
    return EvaluationEvent(
        id=row.id,
        record_id=row.record_id,
        candidate_id=row.candidate_id,
        event_type=row.event_type,
        payload=dict(row.payload or {}),
        created_at=consent_logic.as_utc(row.created_at),
    )


def _coding_round(row: CodingRoundResultRow) -> CodingRoundResult:
    return CodingRoundResult(
        id=row.id,
        org_id=row.org_id,
        candidate_id=row.candidate_id,
        consent_id=row.consent_id,
        platform=CodingPlatform(row.platform),
        platform_name=row.platform_name,
        assessment_name=row.assessment_name,
        score=row.score,
        max_score=row.max_score,
        percentile=row.percentile,
        problem_tags=list(row.problem_tags or []),
        taken_at=consent_logic.as_utc(row.taken_at),
        raw=dict(row.raw or {}),
        created_at=consent_logic.as_utc(row.created_at),
    )


def _observed_offer(row: ObservedOfferRow) -> ObservedOffer:
    return ObservedOffer(
        id=row.id, org_id=row.org_id, candidate_id=row.candidate_id,
        consent_id=row.consent_id, role_family=row.role_family,
        seniority=row.seniority, city_tier=row.city_tier,
        ctc_fixed=row.ctc_fixed, ctc_variable=row.ctc_variable, currency=row.currency,
        offered_at=consent_logic.as_utc(row.offered_at),
        created_at=consent_logic.as_utc(row.created_at),
    )


def _audit_entry(row: AuditLogRow) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        candidate_id=row.candidate_id,
        details=dict(row.details or {}),
        created_at=consent_logic.as_utc(row.created_at),
    )


class LedgerStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        default_consent_ttl_days: int = 365,
        api_key_bytes: int = 32,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._default_consent_ttl_days = default_consent_ttl_days
        self._api_key_bytes = api_key_bytes
        self._settings = settings

    # -- audit ----------------------------------------------------------------

    @staticmethod
    def _audit(
        session: Session,
        *,
        actor_type: str,
        actor_id: Optional[str],
        action: str,
        entity_type: str,
        entity_id: str,
        candidate_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        session.add(
            AuditLogRow(
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                candidate_id=candidate_id,
                details=details or {},
            )
        )

    def audit_for_candidate(self, candidate_id: str) -> list[AuditEntry]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(AuditLogRow)
                    .where(AuditLogRow.candidate_id == candidate_id)
                    .order_by(AuditLogRow.created_at, AuditLogRow.id)
                )
                .scalars()
                .all()
            )
            return [_audit_entry(r) for r in rows]

    # -- organizations --------------------------------------------------------

    def create_organization(self, name: str) -> Organization:
        with self._session_factory() as session:
            row = OrganizationRow(name=name)
            session.add(row)
            try:
                session.flush()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError(f"organization name already exists: {name!r}") from exc
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.create",
                entity_type="organization",
                entity_id=row.id,
                details={"name": name},
            )
            session.commit()
            return _org(row)

    def get_organization(self, org_id: str) -> Optional[Organization]:
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            return _org(row) if row else None

    def list_organizations(self) -> list[Organization]:
        with self._session_factory() as session:
            rows = (
                session.execute(select(OrganizationRow).order_by(OrganizationRow.created_at))
                .scalars()
                .all()
            )
            return [_org(r) for r in rows]

    def delete_organization(self, org_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            if row is None:
                return False
            session.delete(row)
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.delete",
                entity_type="organization",
                entity_id=org_id,
            )
            session.commit()
            return True

    def issue_api_key(self, org_id: str) -> str:
        """Generate + store (hashed) a fresh API key, returning the plaintext
        ONCE. Overwrites any previous key — this is also key rotation."""
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            if row is None:
                raise LookupError(f"unknown organization: {org_id}")
            raw = secrets.token_urlsafe(self._api_key_bytes)
            row.api_key_hash = _hash_api_key(raw)
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.issue_key",
                entity_type="organization",
                entity_id=org_id,
            )
            session.commit()
            return raw

    def authenticate_org(self, api_key: str) -> Optional[str]:
        """org_id for the active org holding this key, else None. Suspended
        orgs never authenticate; empty/whitespace keys never match."""
        api_key = (api_key or "").strip()
        if not api_key:
            return None
        digest = _hash_api_key(api_key)
        with self._session_factory() as session:
            row = session.execute(
                select(OrganizationRow).where(
                    OrganizationRow.api_key_hash == digest,
                    OrganizationRow.status == "active",
                )
            ).scalar_one_or_none()
            return row.id if row else None

    def set_org_reliability(self, org_id: str, weight: float) -> Organization:
        """Admin: set an org's reliability multiplier for S3.4 reputation.
        weight >= 0 (0 mutes the org's evidence); audited as org.set_reliability."""
        if weight < 0:
            raise ValueError(f"reliability weight must be >= 0, got {weight}")
        with self._session_factory() as session:
            row = session.get(OrganizationRow, org_id)
            if row is None:
                raise LookupError(f"unknown organization: {org_id}")
            row.reliability_weight = float(weight)
            self._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="org.set_reliability",
                entity_type="organization",
                entity_id=org_id,
                details={"reliability_weight": float(weight)},
            )
            session.commit()
            return _org(row)

    # -- consent lifecycle ----------------------------------------------------

    def grant_consent(
        self,
        *,
        candidate_id: str,
        purpose: ConsentPurpose | str,
        org_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> ConsentGrant:
        purpose = ConsentPurpose(purpose)
        # SQLite drops tzinfo at write, storing wall-clock fields; coerce every
        # caller-supplied datetime to real UTC first so a naive readback lands
        # at the correct instant (store-internal `_utcnow()` is already UTC).
        moment = consent_logic.as_utc(now) if now else _utcnow()
        expires_at = consent_logic.as_utc(expires_at) if expires_at else None
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            if org_id is not None and session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            expires = expires_at or moment + timedelta(days=self._default_consent_ttl_days)
            row = ConsentGrantRow(
                candidate_id=candidate_id,
                org_id=org_id,
                purpose=purpose.value,
                granted_at=moment,
                expires_at=expires,
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="candidate",
                actor_id=candidate_id,
                action="consent.grant",
                entity_type="consent_grant",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "purpose": purpose.value,
                    "org_id": org_id,
                    "expires_at": expires.isoformat(),
                },
            )
            session.commit()
            return _grant(row)

    def revoke_consent(self, consent_id: str, *, now: Optional[datetime] = None) -> bool:
        """True only when this call newly revoked the grant."""
        moment = consent_logic.as_utc(now) if now else _utcnow()
        with self._session_factory() as session:
            row = session.get(ConsentGrantRow, consent_id)
            if row is None or row.revoked_at is not None:
                return False
            row.revoked_at = moment
            self._audit(
                session,
                actor_type="candidate",
                actor_id=row.candidate_id,
                action="consent.revoke",
                entity_type="consent_grant",
                entity_id=row.id,
                candidate_id=row.candidate_id,
            )
            session.commit()
            return True

    def _grants_for(
        self, session: Session, candidate_id: str, purpose: ConsentPurpose
    ) -> list[ConsentGrant]:
        rows = (
            session.execute(
                select(ConsentGrantRow).where(
                    ConsentGrantRow.candidate_id == candidate_id,
                    ConsentGrantRow.purpose == purpose.value,
                )
            )
            .scalars()
            .all()
        )
        return [_grant(r) for r in rows]

    def consent_status(
        self,
        candidate_id: str,
        *,
        org_id: str,
        purpose: ConsentPurpose | str,
        at: Optional[datetime] = None,
    ) -> ConsentDecision:
        purpose = ConsentPurpose(purpose)
        moment = at or _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            grants = self._grants_for(session, candidate_id, purpose)
        return consent_logic.check_consent(
            grants, org_id=org_id, purpose=purpose, at=moment
        )

    def consents_for_candidate(self, candidate_id: str) -> list[ConsentGrant]:
        """All grants for a candidate — active, revoked, and expired — ordered by
        grant time. A raw candidate-own read (the candidate's own consent ledger);
        no consent gate. Powers the S6.4 portal `/portal/consents` view."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ConsentGrantRow)
                    .where(ConsentGrantRow.candidate_id == candidate_id)
                    .order_by(ConsentGrantRow.granted_at, ConsentGrantRow.id)
                ).scalars().all()
            )
            return [_grant(r) for r in rows]

    def get_grant(self, consent_id: str) -> Optional[ConsentGrant]:
        """One grant by id, or None. Used by the S6.4 portal to enforce ownership
        before a first-party revoke."""
        with self._session_factory() as session:
            row = session.get(ConsentGrantRow, consent_id)
            return _grant(row) if row else None

    # -- interview records + events (consent-gated writes) --------------------

    def submit_interview_record(
        self,
        *,
        org_id: str,
        candidate_id: str,
        stage: InterviewStage | str,
        outcome: InterviewOutcome | str,
        interviewed_at: datetime,
        summary: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> InterviewRecord:
        """Write-time DPDP gate: refuses without an active ledger_write grant."""
        stage = InterviewStage(stage)
        outcome = InterviewOutcome(outcome)
        moment = consent_logic.as_utc(now) if now else _utcnow()
        interviewed_at = consent_logic.as_utc(interviewed_at)
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_WRITE)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_WRITE, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)
            row = InterviewRecordRow(
                org_id=org_id,
                candidate_id=candidate_id,
                consent_id=decision.grant_id,
                stage=stage.value,
                outcome=outcome.value,
                interviewed_at=interviewed_at,
                summary=summary,
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="record.submit",
                entity_type="interview_record",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "stage": stage.value,
                    "outcome": outcome.value,
                    "consent_id": decision.grant_id,
                },
            )
            session.commit()
            return _record(row)

    def append_event(
        self,
        record_id: str,
        *,
        event_type: str,
        payload: Optional[dict] = None,
    ) -> EvaluationEvent:
        with self._session_factory() as session:
            record = session.get(InterviewRecordRow, record_id)
            if record is None:
                raise LookupError(f"unknown interview record: {record_id}")
            row = EvaluationEventRow(
                record_id=record.id,
                candidate_id=record.candidate_id,
                event_type=event_type,
                payload=payload or {},
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="org",
                actor_id=record.org_id,
                action="event.append",
                entity_type="evaluation_event",
                entity_id=row.id,
                candidate_id=record.candidate_id,
                details={"record_id": record.id, "event_type": event_type},
            )
            session.commit()
            return _event(row)

    def records_for_candidate(self, candidate_id: str) -> list[InterviewRecord]:
        """Raw store read — query-time ledger_read enforcement is S3.2 (API)."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(InterviewRecordRow)
                    .where(InterviewRecordRow.candidate_id == candidate_id)
                    .order_by(InterviewRecordRow.created_at, InterviewRecordRow.id)
                )
                .scalars()
                .all()
            )
            return [_record(r) for r in rows]

    def get_record(self, record_id: str) -> Optional[InterviewRecord]:
        with self._session_factory() as session:
            row = session.get(InterviewRecordRow, record_id)
            return _record(row) if row else None

    def query_records_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
    ) -> list[InterviewRecord]:
        """Query-time DPDP gate: an org may read a candidate's records only under
        an active ledger_read grant. Every read attempt — allowed or denied — is
        audited in the same transaction (surveillance is itself observable)."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_READ)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_READ, at=moment
            )
            if not decision.allowed:
                self._audit(
                    session,
                    actor_type="org",
                    actor_id=org_id,
                    action="record.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "ledger_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)
            rows = (
                session.execute(
                    select(InterviewRecordRow)
                    .where(InterviewRecordRow.candidate_id == candidate_id)
                    .order_by(InterviewRecordRow.created_at, InterviewRecordRow.id)
                )
                .scalars()
                .all()
            )
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="record.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "record_count": len(rows),
                },
            )
            session.commit()
            return [_record(r) for r in rows]

    def events_for_record(self, record_id: str) -> list[EvaluationEvent]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(EvaluationEventRow)
                    .where(EvaluationEventRow.record_id == record_id)
                    .order_by(EvaluationEventRow.created_at, EvaluationEventRow.id)
                )
                .scalars()
                .all()
            )
            return [_event(r) for r in rows]

    # -- coding-round results (S3.3, consent-gated like interview records) -----

    def submit_coding_round(
        self,
        *,
        org_id: str,
        candidate_id: str,
        platform: CodingPlatform | str,
        score: float,
        taken_at: datetime,
        assessment_name: Optional[str] = None,
        platform_name: Optional[str] = None,
        max_score: Optional[float] = None,
        percentile: Optional[float] = None,
        problem_tags: Optional[list[str]] = None,
        raw: Optional[dict] = None,
        now: Optional[datetime] = None,
    ) -> CodingRoundResult:
        """Write-time DPDP gate: refuses without an active ledger_write grant."""
        platform = CodingPlatform(platform)
        moment = consent_logic.as_utc(now) if now else _utcnow()
        taken_at = consent_logic.as_utc(taken_at)
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_WRITE)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_WRITE, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)
            row = CodingRoundResultRow(
                org_id=org_id,
                candidate_id=candidate_id,
                consent_id=decision.grant_id,
                platform=platform.value,
                platform_name=platform_name,
                assessment_name=assessment_name,
                score=score,
                max_score=max_score,
                percentile=percentile,
                problem_tags=list(problem_tags or []),
                taken_at=taken_at,
                raw=dict(raw or {}),
            )
            session.add(row)
            session.flush()
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="coding_round.submit",
                entity_type="coding_round_result",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "platform": platform.value,
                    "score": score,
                    "consent_id": decision.grant_id,
                },
            )
            session.commit()
            return _coding_round(row)

    def coding_rounds_for_candidate(self, candidate_id: str) -> list[CodingRoundResult]:
        """Raw store read — query-time ledger_read enforcement is the API's job."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(CodingRoundResultRow)
                    .where(CodingRoundResultRow.candidate_id == candidate_id)
                    .order_by(CodingRoundResultRow.created_at, CodingRoundResultRow.id)
                )
                .scalars()
                .all()
            )
            return [_coding_round(r) for r in rows]

    def query_coding_rounds_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
    ) -> list[CodingRoundResult]:
        """Query-time DPDP gate mirroring records: an org may read a candidate's
        coding rounds only under an active ledger_read grant. Every attempt —
        allowed or denied — is audited in the same transaction."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_READ)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_READ, at=moment
            )
            if not decision.allowed:
                self._audit(
                    session,
                    actor_type="org",
                    actor_id=org_id,
                    action="coding_round.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "ledger_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)
            rows = (
                session.execute(
                    select(CodingRoundResultRow)
                    .where(CodingRoundResultRow.candidate_id == candidate_id)
                    .order_by(CodingRoundResultRow.created_at, CodingRoundResultRow.id)
                )
                .scalars()
                .all()
            )
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="coding_round.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "result_count": len(rows),
                },
            )
            session.commit()
            return [_coding_round(r) for r in rows]

    # -- observed offers (S5.2, consent-gated like interview records) -----------

    def submit_observed_offer(
        self,
        *,
        org_id: str,
        candidate_id: str,
        role_family: str,
        seniority: str,
        city_tier: str,
        ctc_fixed: float,
        ctc_variable: Optional[float] = None,
        currency: str = "INR",
        offered_at: datetime,
        now: Optional[datetime] = None,
    ) -> ObservedOffer:
        """Write-time DPDP gate: refuses without an active ledger_write grant.
        role_family/seniority/city_tier are validated at the API boundary."""
        moment = consent_logic.as_utc(now) if now else _utcnow()
        offered_at = consent_logic.as_utc(offered_at)
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_WRITE)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_WRITE, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)
            row = ObservedOfferRow(
                org_id=org_id, candidate_id=candidate_id, consent_id=decision.grant_id,
                role_family=role_family, seniority=seniority, city_tier=city_tier,
                ctc_fixed=ctc_fixed, ctc_variable=ctc_variable, currency=currency,
                offered_at=offered_at,
            )
            session.add(row)
            session.flush()
            self._audit(
                session, actor_type="org", actor_id=org_id, action="offer.submit",
                entity_type="observed_offer", entity_id=row.id, candidate_id=candidate_id,
                details={
                    "role_family": role_family, "seniority": seniority,
                    "city_tier": city_tier, "ctc_fixed": ctc_fixed,
                    "consent_id": decision.grant_id,
                },
            )
            session.commit()
            return _observed_offer(row)

    def observed_offers_for_comp(
        self,
        *,
        requesting_org_id: str,
        role_family: str,
        seniority: str,
        city_tier: str,
        at: Optional[datetime] = None,
    ) -> list[ObservedOfferPoint]:
        """Cross-candidate comp aggregation read (S5.2). Returns DE-IDENTIFIED
        points (total_ctc + offered_at only) for offers matching the role signal
        whose stamped ledger_write grant is still active at `at` -- so a
        candidate's revocation/expiry removes their offer. Audits comp.aggregate
        (candidate_id=None: the aggregate is about a role, not a person). The
        k-anonymity floor is applied by the comp engine, not here."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ObservedOfferRow).where(
                        ObservedOfferRow.role_family == role_family,
                        ObservedOfferRow.seniority == seniority,
                        ObservedOfferRow.city_tier == city_tier,
                    )
                ).scalars().all()
            )
            points: list[ObservedOfferPoint] = []
            for r in rows:
                grant_row = session.get(ConsentGrantRow, r.consent_id)
                if grant_row is None:
                    continue
                if consent_logic.is_grant_active(
                    _grant(grant_row), org_id=r.org_id,
                    purpose=ConsentPurpose.LEDGER_WRITE, at=moment,
                ):
                    points.append(ObservedOfferPoint(
                        total_ctc=r.ctc_fixed + (r.ctc_variable or 0.0),
                        offered_at=consent_logic.as_utc(r.offered_at),
                    ))
            self._audit(
                session, actor_type="org", actor_id=requesting_org_id,
                action="comp.aggregate", entity_type="role_signal",
                entity_id=f"{role_family}:{seniority}:{city_tier}", candidate_id=None,
                details={
                    "matched": len(rows), "active": len(points),
                    "excluded": len(rows) - len(points),
                },
            )
            session.commit()
            return points

    # -- cross-company reputation (S3.4, derived ledger_read-gated read) --------

    def reputation_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
    ) -> ReputationAssessment:
        """Advisory cross-company reputation, ledger_read-gated. Reads the
        candidate's interview records + coding rounds, aggregates them (Bayesian
        shrinkage + recency decay + per-org reliability), and audits every
        attempt — allowed or denied — as reputation.query in the same
        transaction. Never a rejection signal."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_READ)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.LEDGER_READ, at=moment
            )
            if not decision.allowed:
                self._audit(
                    session,
                    actor_type="org",
                    actor_id=org_id,
                    action="reputation.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "ledger_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)

            record_rows = (
                session.execute(
                    select(InterviewRecordRow)
                    .where(InterviewRecordRow.candidate_id == candidate_id)
                    .order_by(InterviewRecordRow.created_at, InterviewRecordRow.id)
                ).scalars().all()
            )
            coding_rows = (
                session.execute(
                    select(CodingRoundResultRow)
                    .where(CodingRoundResultRow.candidate_id == candidate_id)
                    .order_by(CodingRoundResultRow.created_at, CodingRoundResultRow.id)
                ).scalars().all()
            )
            records = [_record(r) for r in record_rows]
            coding = [_coding_round(r) for r in coding_rows]

            org_ids = {r.org_id for r in records} | {c.org_id for c in coding}
            reliability_by_org: dict[str, float] = {}
            for oid in org_ids:
                o = session.get(OrganizationRow, oid)
                reliability_by_org[oid] = (
                    o.reliability_weight if o and o.reliability_weight is not None else 1.0
                )

            assessment = assess_reputation(
                records, coding, now=moment,
                reliability_by_org=reliability_by_org, settings=self._settings,
            )
            self._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="reputation.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "band": assessment.band.value,
                    "total_observations": assessment.total_observations,
                    "distinct_orgs": assessment.distinct_orgs,
                },
            )
            session.commit()
            return assessment

    # -- feature materialization consent (S4.2, platform-internal gate) ---------

    def materialization_consent(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> ConsentDecision:
        """Platform-internal materialization gate (S4.2): may the platform include
        this candidate's consent-tagged (ledger/reputation) features in the ML
        feature table at `at`? Basis = any active ledger_read grant (org-agnostic).
        Audits `feature.materialize` (allowed AND withheld) in the same
        transaction. Returns the decision — withheld does NOT raise (the caller
        still writes a valid row with those features nulled)."""
        moment = consent_logic.as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._grants_for(session, candidate_id, ConsentPurpose.LEDGER_READ)
            decision = consent_logic.has_any_active(
                grants, purpose=ConsentPurpose.LEDGER_READ, at=moment
            )
            details = {"allowed": decision.allowed, "purpose": "ledger_read"}
            if decision.allowed:
                details["consent_id"] = decision.grant_id
            self._audit(
                session,
                actor_type="system",
                actor_id="platform",
                action="feature.materialize",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details=details,
            )
            session.commit()
            return decision

    def audit_training_label(
        self, candidate_id: str, *, allowed: bool, as_of: datetime
    ) -> None:
        """S4.4 training-set export: audit that the platform used (allowed) or
        withheld (not allowed) this candidate's consent-gated outcomes as a
        training label. Audit-only — it records the S4.2 materialization decision
        reused at export time (single source of truth), does not recompute
        consent, and never raises. The candidate-linked row CASCADEs on erasure."""
        with self._session_factory() as session:
            self._audit(
                session,
                actor_type="system",
                actor_id="platform",
                action="training.label",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": allowed,
                    "as_of": consent_logic.as_utc(as_of).isoformat(),
                },
            )
            session.commit()


    def audit_request_event(
        self,
        candidate_id: str,
        *,
        request_id: str,
        action: str,
        actor_type: str,
        actor_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """S8.3 Phase B: a DPDP correction/grievance request changed state.

        Named rather than a general `audit(...)` door, matching
        `audit_training_label` above: every audit writer in this store says what
        it is recording, so `_audit` stays private and no caller can invent an
        entity_type the candidate's own access log has never seen.

        The candidate_id is what puts this on the SUBJECT's access log --
        S3.1's rule that surveillance is itself observable, applied to the
        handling of their own complaint, which is where it matters most.
        """
        with self._session_factory() as session:
            self._audit(
                session,
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                entity_type="data_principal_request",
                entity_id=request_id,
                candidate_id=candidate_id,
                details=details or {},
            )
            session.commit()


def build_ledger_store(settings: Optional[Settings] = None) -> LedgerStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job (`alembic upgrade head`), NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return LedgerStore(
        make_session_factory(engine),
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        api_key_bytes=getattr(settings, "ledger_api_key_bytes", 32),
        settings=settings,
    )
