"""Job requisition store + role-conditioned match orchestrator (S5.1).

Shares the candidates/ledger session factory (organizations, candidates,
ml_feature_vectors, audit_log are one DB). CRUD is org-scoped: an org only sees
its own requisitions. run_match (Task 8) does the I/O the pure engine cannot and
audits every surfaced candidate as a match.surface disclosure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.candidates.normalize.skills import normalize_skill
from app.candidates.normalize.text import norm_key
from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.features import default_view, get_feature_registry
from app.features.store import FeatureStore, build_feature_store
from app.ledger.consent import as_utc
from app.ledger.models import AuditLogRow, OrganizationRow
from app.matching.match import compile_ranking, match as _match_engine
from app.matching.models import JobRequisitionRow
from app.matching.schema import (
    CompBand, JobRequisition, JobRequisitionInput, MatchResult, MatchWeights,
    RequisitionStatus,
)


def _canonicalize(skills: tuple[str, ...]) -> list[str]:
    """Map free-text skills to canonical taxonomy ids (unknown -> norm_key, so the
    ask is recorded verbatim-normalized even if no candidate can match it).
    De-duplicates, preserving first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for s in skills:
        m = normalize_skill(s)
        key = m.canonical if m else norm_key(s)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _to_contract(row: JobRequisitionRow) -> JobRequisition:
    return JobRequisition(
        id=row.id,
        org_id=row.org_id,
        title=row.title,
        status=RequisitionStatus(row.status),
        must_have_skills=tuple(row.must_have_skills or ()),
        nice_to_have_skills=tuple(row.nice_to_have_skills or ()),
        min_years_experience=row.min_years_experience,
        min_degree_level=row.min_degree_level,
        max_notice_days=row.max_notice_days,
        location_tiers=tuple(row.location_tiers) if row.location_tiers else None,
        remote=row.remote,
        min_skill_coverage=row.min_skill_coverage,
        comp_band=CompBand.model_validate(row.comp_band) if row.comp_band else None,
        weights=MatchWeights.model_validate(row.weights) if row.weights else None,
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
    )


def _apply_spec(row: JobRequisitionRow, spec: JobRequisitionInput) -> None:
    row.title = spec.title
    row.status = spec.status.value
    row.must_have_skills = _canonicalize(spec.must_have_skills)
    row.nice_to_have_skills = _canonicalize(spec.nice_to_have_skills)
    row.min_years_experience = spec.min_years_experience
    row.min_degree_level = spec.min_degree_level
    row.max_notice_days = spec.max_notice_days
    row.location_tiers = list(spec.location_tiers) if spec.location_tiers else None
    row.remote = spec.remote
    row.min_skill_coverage = spec.min_skill_coverage
    row.comp_band = spec.comp_band.model_dump() if spec.comp_band else None
    row.weights = spec.weights.model_dump(exclude_none=True) if spec.weights else None


class JobStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        candidate_store: Optional[CandidateStore] = None,
        feature_store: Optional[FeatureStore] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._candidates = candidate_store
        self._features = feature_store
        self._settings = settings or get_settings()

    def create_requisition(
        self, org_id: str, spec: JobRequisitionInput
    ) -> JobRequisition:
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            row = JobRequisitionRow(org_id=org_id)
            _apply_spec(row, spec)
            session.add(row)
            session.flush()
            session.add(AuditLogRow(
                actor_type="org", actor_id=org_id, action="requisition.create",
                entity_type="requisition", entity_id=row.id, candidate_id=None,
                details={"title": spec.title},
            ))
            session.commit()
            return _to_contract(row)

    def get_requisition(self, org_id: str, req_id: str) -> Optional[JobRequisition]:
        with self._session_factory() as session:
            row = session.get(JobRequisitionRow, req_id)
            if row is None or row.org_id != org_id:
                return None
            return _to_contract(row)

    def list_requisitions(self, org_id: str) -> list[JobRequisition]:
        with self._session_factory() as session:
            rows = session.execute(
                select(JobRequisitionRow)
                .where(JobRequisitionRow.org_id == org_id)
                .order_by(JobRequisitionRow.created_at, JobRequisitionRow.id)
            ).scalars().all()
            return [_to_contract(r) for r in rows]

    def update_requisition(
        self,
        org_id: str,
        req_id: str,
        *,
        status: Optional[RequisitionStatus] = None,
        spec: Optional[JobRequisitionInput] = None,
    ) -> Optional[JobRequisition]:
        with self._session_factory() as session:
            row = session.get(JobRequisitionRow, req_id)
            if row is None or row.org_id != org_id:
                return None
            if spec is not None:
                _apply_spec(row, spec)
            if status is not None:
                row.status = status.value
            session.add(AuditLogRow(
                actor_type="org", actor_id=org_id, action="requisition.update",
                entity_type="requisition", entity_id=row.id, candidate_id=None,
                details={"status": row.status},
            ))
            session.commit()
            return _to_contract(row)

    def run_match(
        self,
        org_id: str,
        req_id: str,
        *,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Optional[MatchResult]:
        """Role-conditioned match over the materialized pool. Returns None if the
        requisition is not owned by org_id. Reads vectors + point-in-time profiles
        at one as_of, ranks with the pure engine, and audits each RETURNED
        candidate as a match.surface disclosure (candidate-linked, CASCADE)."""
        req = self.get_requisition(org_id, req_id)
        if req is None:
            return None

        registry = get_feature_registry()
        view_name = self._settings.feat_default_view
        view_version = default_view(registry, settings=self._settings).version
        limit = limit or self._settings.match_default_limit

        cut = as_of or self._features.latest_as_of(view_name, view_version)
        pool = (
            self._features.vectors_for_view(view_name, view_version, as_of=cut)
            if cut is not None else []
        )
        vectors = [mv.vector for mv in pool]

        # Scalar feature specs the compiled ranking references (synthetic specs are
        # merged inside the engine); resolved from the registry.
        ranking = compile_ranking(req, self._settings)
        scalar = {t.feature for t in ranking.terms if not t.feature.startswith("match.")}
        specs_by_name = {n: registry.get(n).spec for n in scalar}

        profiles: dict = {}
        if cut is not None and self._candidates is not None:
            for v in vectors:
                p = self._candidates.profile_as_of(v.candidate_id, cut)
                if p is not None:
                    profiles[v.candidate_id] = p

        all_ranked = _match_engine(req, vectors, profiles, specs_by_name, self._settings)
        filtered_size = len(all_ranked)  # after the opt-in filter, before the limit
        ranked = all_ranked[:limit]

        # Disclosure audit: one match.surface row per RETURNED candidate.
        with self._session_factory() as session:
            for rank, mc in enumerate(ranked, start=1):
                session.add(AuditLogRow(
                    actor_type="org", actor_id=org_id, action="match.surface",
                    entity_type="requisition", entity_id=req_id,
                    candidate_id=mc.candidate_id,
                    details={"rank": rank, "score": mc.score},
                ))
            session.commit()

        return MatchResult(
            advisory=True, requisition_id=req_id, as_of=cut,
            view_name=view_name, view_version=view_version,
            pool_size=len(vectors), filtered_size=filtered_size,
            ranked=tuple(ranked),
        )


def build_job_store(settings: Optional[Settings] = None) -> JobStore:
    """Store on the shared candidates DB URL. Schema is Alembic's job."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    session_factory = make_session_factory(engine)
    return JobStore(
        session_factory,
        candidate_store=build_candidate_store(settings),
        feature_store=build_feature_store(settings),
        settings=settings,
    )
