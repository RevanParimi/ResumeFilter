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

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger import consent as consent_logic
from app.ledger.models import (
    AuditLogRow,
    ConsentGrantRow,
    EvaluationEventRow,
    InterviewRecordRow,
    OrganizationRow,
)
from app.ledger.schema import (
    AuditEntry,
    ConsentDecision,
    ConsentGrant,
    ConsentPurpose,
    EvaluationEvent,
    InterviewOutcome,
    InterviewRecord,
    InterviewStage,
    Organization,
)


class ConsentError(RuntimeError):
    """A write needed consent that is not currently active."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _org(row: OrganizationRow) -> Organization:
    return Organization(id=row.id, name=row.name, status=row.status,
                        created_at=consent_logic.as_utc(row.created_at))


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
        self, session_factory: sessionmaker, *, default_consent_ttl_days: int = 365
    ) -> None:
        self._session_factory = session_factory
        self._default_consent_ttl_days = default_consent_ttl_days

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
            dup = session.execute(
                select(OrganizationRow.id).where(OrganizationRow.name == name)
            ).first()
            if dup:
                raise ValueError(f"organization name already exists: {name!r}")
            row = OrganizationRow(name=name)
            session.add(row)
            session.flush()
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
        moment = now or _utcnow()
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
        moment = now or _utcnow()
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
            grants = self._grants_for(session, candidate_id, purpose)
        return consent_logic.check_consent(
            grants, org_id=org_id, purpose=purpose, at=moment
        )

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
        moment = now or _utcnow()
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


def build_ledger_store(settings: Optional[Settings] = None) -> LedgerStore:
    """Store on the shared candidates DB URL (one metadata root, one Alembic
    env). Schema is Alembic's job (`alembic upgrade head`), NOT the builder's."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return LedgerStore(
        make_session_factory(engine),
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
    )
