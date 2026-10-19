"""Source-owned raw observations and explicit approved vocabulary.

Legacy resolved aliases remain read-only normalization compatibility.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Optional
import unicodedata
import uuid

from sqlalchemy import and_, delete, exists, func, insert, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.candidates.normalize.skills import SkillMatch, norm_key
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.curation.models import CurationAliasRow, CurationObservationRow, UnmappedTermRow
from app.curation.schema import CurationAction, CurationDecision, CurationStatus, UnmappedTerm
from app.profile_sources.models import ProfileSourceRow


REVIEW_LIFETIME = timedelta(days=30)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_text(value: str | None, maximum: int) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= maximum
            and bool(value.strip())
            and not any(unicodedata.category(char) == "Cc" for char in value))


def _as_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class StaleReviewError(ValueError):
    def __init__(self) -> None:
        super().__init__("review snapshot changed; refresh before deciding")


def _review_revision(key: str, observations) -> str:
    """Hash exact snapshot identity/content without returning contributor IDs.

    Canonical UTC timestamps work for SQLite's naive values and PostgreSQL's
    timezone-aware values. UUID identities distinguish identical replacements.
    This is a precondition, not authentication or a persisted raw-data receipt.
    """
    members = sorted((row["id"], row["source_id"],
                      _as_utc(row["created_at"]).isoformat(timespec="microseconds"),
                      row["observed_display"]) for row in observations)
    return hashlib.sha256(json.dumps([key, members], separators=(",", ":")).encode()).hexdigest()


class CurationStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def record_observation(self, name: str, *, source_id: str) -> bool:
        """Append against a durable source; never refresh an earlier lifetime.

        The service must still apply configured key bounds and skip known static
        vocabulary. This persistence boundary bounds raw input independently.
        """
        if not _bounded_text(name, 128):
            return False
        key = norm_key(name)
        if not key or len(key) > 128:
            return False
        row = CurationObservationRow
        with self._session_factory() as session:
            statement = insert(row).from_select(
                ["id", "source_id", "norm_key", "display_name", "created_at"],
                select(literal(str(uuid.uuid4())), ProfileSourceRow.id,
                       literal(key), literal(name.strip()), literal(_utcnow()))
                .where(ProfileSourceRow.id == source_id,
                       ~exists(select(CurationAliasRow.norm_key)
                               .where(CurationAliasRow.norm_key == key))),
            ).returning(row.id)
            try:
                captured = session.execute(statement).scalar_one_or_none() is not None
                session.commit()
                return captured
            except IntegrityError as exc:
                session.rollback()
                is_fk = (getattr(exc.orig, "sqlstate", None) == "23503"
                         or getattr(exc.orig, "pgcode", None) == "23503"
                         or getattr(exc.orig, "sqlite_errorcode", None) == 787)
                if is_fk and session.get(ProfileSourceRow, source_id) is None:
                    return False
                raise

    def list_observations(
        self, limit: int = 200, *, cursor: str | None = None,
        key: str | None = None,
    ) -> tuple[list[UnmappedTerm], str | None]:
        """One statement snapshot for counts, representative and source types.

        Erasure/expiry after the statement snapshot can still race delivery.
        Paging order is mutable when observations arrive, expire or are erased.
        """
        from app.screening.pagination import decode_cursor, encode_cursor, iso_datetime

        if limit < 1:
            raise ValueError("limit must be >= 1")
        row = CurationObservationRow
        active_query = select(
            row.id, row.source_id, row.norm_key, row.display_name, row.created_at,
            ProfileSourceRow.source_type,
        ).join(ProfileSourceRow, ProfileSourceRow.id == row.source_id).where(
            row.created_at > _utcnow() - REVIEW_LIFETIME)
        if key is not None:
            active_query = active_query.where(row.norm_key == key)
        active = active_query.cte("active_observations")
        ranked = select(
            active.c.norm_key, active.c.display_name,
            func.count().over(partition_by=active.c.norm_key).label("occurrences"),
            func.min(active.c.created_at).over(partition_by=active.c.norm_key).label("first_seen"),
            func.max(active.c.created_at).over(partition_by=active.c.norm_key).label("last_seen"),
            func.row_number().over(partition_by=active.c.norm_key,
                order_by=(active.c.created_at.desc(), active.c.id.desc())).label("position"),
        ).cte("ranked_observations")
        q = select(ranked).where(ranked.c.position == 1)
        if cursor is not None:
            occ, seen, last_key = decode_cursor(cursor, arity=3, types=(int, str, str))
            cut = _as_utc(iso_datetime(seen))
            q = q.where(or_(ranked.c.occurrences < occ,
                and_(ranked.c.occurrences == occ, or_(ranked.c.last_seen < cut,
                    and_(ranked.c.last_seen == cut, ranked.c.norm_key > last_key)))))
        page = q.order_by(ranked.c.occurrences.desc(), ranked.c.last_seen.desc(),
                          ranked.c.norm_key).limit(limit + 1).cte("observation_page")
        # One statement snapshot supplies both visible aggregates and revision
        # members; a separate read could attach a newer revision to old text.
        statement = select(page, active.c.id, active.c.source_id, active.c.created_at,
                           active.c.display_name.label("observed_display"),
                           active.c.source_type).join(
            active, active.c.norm_key == page.c.norm_key).order_by(
                page.c.occurrences.desc(), page.c.last_seen.desc(), page.c.norm_key,
                active.c.id)
        with self._session_factory() as session:
            rows = session.execute(statement).mappings().all()
        grouped: dict[str, list] = {}
        for item in rows:
            grouped.setdefault(item["norm_key"], []).append(item)
        result = []
        for norm, members in grouped.items():
            item = members[0]
            result.append(UnmappedTerm(norm_key=norm, display_name=item["display_name"],
                occurrences=item["occurrences"], first_seen=_as_utc(item["first_seen"]),
                last_seen=_as_utc(item["last_seen"]),
                source_types=sorted({row["source_type"] for row in members}),
                review_revision=_review_revision(norm, members)))
        more = len(result) > limit
        result = result[:limit]
        next_cursor = (encode_cursor((result[-1].occurrences, result[-1].last_seen,
                                      result[-1].norm_key)) if more else None)
        return result, next_cursor

    def get_observation(self, key: str) -> UnmappedTerm | None:
        terms, _ = self.list_observations(limit=1, key=key)
        return terms[0] if terms else None

    def resolve_observations(
        self, key: str, *, action: CurationAction, alias: str | None = None,
        canonical: str | None = None, category: str | None = None,
        admin_user_id: str | None = None,
        expected_revision: str | None = None,
    ) -> CurationDecision:
        """Claim raw rows by DELETE, then approve in the same transaction.

        DELETE serializes competing decisions without a pre-read race. Recheck
        the clock after waiting for row locks. Only returned live observations
        authorize approval. New concurrent captures may form a later queue item.
        Duplicate approved aliases fail explicitly; raw deletion rolls back.
        A supplied revision binds the decision to the exact live claimed rows.
        Revision conflicts raise within the transaction, restoring all claims.
        """
        action = CurationAction(action)
        if expected_revision is not None and (not isinstance(expected_revision, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_revision)):
            raise ValueError("invalid review revision")
        if action == CurationAction.IGNORE:
            if any(value is not None for value in (alias, canonical, category)):
                raise ValueError("ignore takes no approved vocabulary")
        elif not (_bounded_text(alias, 128) and norm_key(alias)
                  and len(norm_key(alias)) <= 128 and _bounded_text(canonical, 64)
                  and _bounded_text(category, 32)):
            raise ValueError("promotion requires bounded alias, canonical and category")
        with self._session_factory.begin() as session:
            claimed = session.execute(delete(CurationObservationRow).where(
                CurationObservationRow.norm_key == key).returning(
                    CurationObservationRow.id, CurationObservationRow.source_id,
                    CurationObservationRow.created_at,
                    CurationObservationRow.display_name.label("observed_display"))).mappings().all()
            now = _utcnow()
            live = [row for row in claimed if _as_utc(row["created_at"]) > now - REVIEW_LIFETIME]
            if live and expected_revision is not None and _review_revision(key, live) != expected_revision:
                raise StaleReviewError()
            if live and action != CurationAction.IGNORE:
                alias = alias.strip()
                canonical, category = canonical.strip(), category.strip()
                session.add(CurationAliasRow(norm_key=norm_key(alias), alias=alias,
                    canonical=canonical, category=category, action=action.value,
                    decided_at=now, admin_user_id=admin_user_id))
        if not live:
            # Expired rows claimed above are physically removed even on refusal.
            raise LookupError("term not found")
        return CurationDecision(action, alias, canonical, category, now, admin_user_id)

    def purge_expired(self) -> int:
        """Physical purge; caller owns startup/daily scheduling and failure reporting."""
        with self._session_factory.begin() as session:
            result = session.execute(delete(CurationObservationRow).where(
                CurationObservationRow.created_at <= _utcnow() - REVIEW_LIFETIME))
            return result.rowcount

    def load_owned_overlay(self) -> dict[str, SkillMatch]:
        """Approved aliases override compatible legacy resolved mappings only."""
        overlay = self.load_overlay()
        with self._session_factory() as session:
            rows = session.execute(select(CurationAliasRow)).scalars().all()
            overlay.update({r.norm_key: SkillMatch(canonical=r.canonical, category=r.category)
                            for r in rows})
        return overlay

    def load_overlay(self) -> dict[str, SkillMatch]:
        with self._session_factory() as session:
            rows = session.execute(
                select(UnmappedTermRow.norm_key, UnmappedTermRow.canonical,
                       UnmappedTermRow.category).where(
                    UnmappedTermRow.status == CurationStatus.RESOLVED.value
                )
            ).all()
            overlay: dict[str, SkillMatch] = {}
            for r in rows:
                if r.canonical and r.category:
                    overlay[r.norm_key] = SkillMatch(canonical=r.canonical, category=r.category)
            return overlay


def build_curation_store(
    settings: Optional[Settings] = None, *, session_factory: Optional[sessionmaker] = None,
) -> CurationStore:
    settings = settings or get_settings()
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings.candidates_db_url))
    return CurationStore(session_factory)
