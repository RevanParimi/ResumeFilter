"""Curation service (S6.3): capture unmapped terms, serve the review queue,
resolve a term, and refresh the deterministic normalize_skill overlay.

Validation is deterministic; no LLM. On resolve the in-memory overlay is
refreshed so the correction is live for the running process immediately.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.candidates.normalize.skills import (
    SKILL_CATEGORIES, canonical_ids, category_for_canonical, norm_key,
    set_curated_overlay,
)
from app.core.config import Settings, get_settings
from app.curation.schema import (
    CurationAction, CurationDecision, CurationStatus, UnmappedPage,
)
from app.curation.store import CurationStore, build_curation_store

_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class AliasConflictError(ValueError):
    def __init__(self) -> None:
        super().__init__("approved alias already exists")


def reviewable_raw_term(name: str) -> bool:
    """Bound curation input before trimming; this is not a PII detector."""
    return (isinstance(name, str) and len(name) <= 128
            and not any(unicodedata.category(char) == "Cc" for char in name))


class CurationService:
    def __init__(self, *, store: CurationStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    # --- capture (called by profile-source ingestion) -------------------------
    def record_unmapped(self, name: str, *, source_id: str) -> None:
        if not reviewable_raw_term(name):
            return
        key = norm_key(name or "")
        if not key:
            return
        if not (self._settings.cur_min_term_len <= len(key) <= self._settings.cur_max_term_len):
            return
        self._store.record_observation(name, source_id=source_id)

    # --- review ---------------------------------------------------------------
    def list_unmapped(
        self,
        status: Optional[CurationStatus] = None,
        limit: Optional[int] = None,
        *,
        cursor: Optional[str] = None,
    ) -> UnmappedPage:
        cap = self._settings.cur_queue_default_limit
        limit = cap if limit is None else max(1, min(limit, cap))
        terms, next_cursor = self._store.list_observations(limit, cursor=cursor)
        if status not in (None, CurationStatus.PENDING):
            terms, next_cursor = [], None
        return UnmappedPage(terms=terms, next_cursor=next_cursor)

    # --- resolve --------------------------------------------------------------
    def resolve(
        self, norm_key_value: str, action: CurationAction, *,
        alias: Optional[str] = None, canonical: Optional[str] = None,
        category: Optional[str] = None, admin_user_id: Optional[str] = None,
        expected_revision: Optional[str] = None,
    ) -> CurationDecision:
        canonical, category = self._validate(action, canonical, category)
        try:
            term = self._store.resolve_observations(
                norm_key_value, action=action, alias=alias, canonical=canonical,
                category=category, admin_user_id=admin_user_id,
                expected_revision=expected_revision,
            )
        except IntegrityError as exc:
            is_unique = (getattr(exc.orig, "sqlstate", None) == "23505"
                         or getattr(exc.orig, "pgcode", None) == "23505"
                         or getattr(exc.orig, "sqlite_errorcode", None) in (1555, 2067))
            if is_unique:
                raise AliasConflictError() from None
            raise
        self.refresh_overlay()
        return term

    @staticmethod
    def _validate(
        action: CurationAction, canonical: Optional[str], category: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        if action == CurationAction.IGNORE:
            if canonical or category:
                raise ValueError("ignore takes no canonical/category")
            return None, None
        if action == CurationAction.MAP:
            if not canonical or not category:
                raise ValueError("map requires canonical and category")
            if canonical not in canonical_ids():
                raise ValueError(f"unknown canonical {canonical!r}")
            if category != category_for_canonical(canonical):
                raise ValueError("category does not match canonical")
            return canonical, category
        if action == CurationAction.CREATE:
            if not canonical or not _CANONICAL_ID_RE.fullmatch(canonical):
                raise ValueError("create requires a snake_case canonical id")
            if canonical in canonical_ids():
                raise ValueError(f"canonical {canonical!r} already exists (use map)")
            if not category or category not in SKILL_CATEGORIES:
                raise ValueError(f"create requires a category in {sorted(SKILL_CATEGORIES)}")
            return canonical, category
        raise ValueError(f"unknown action {action!r}")

    def refresh_overlay(self) -> None:
        set_curated_overlay(self._store.load_owned_overlay())

    def purge_expired(self) -> int:
        return self._store.purge_expired()


def build_curation_service(settings: Optional[Settings] = None, *, session_factory=None) -> CurationService:
    settings = settings or get_settings()
    return CurationService(
        store=build_curation_store(settings, session_factory=session_factory), settings=settings,
    )
