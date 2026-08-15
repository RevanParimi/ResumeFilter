"""Curation service (S6.3): capture unmapped terms, serve the review queue,
resolve a term, and refresh the deterministic normalize_skill overlay.

Validation is deterministic; no LLM. On resolve the in-memory overlay is
refreshed so the correction is live for the running process immediately.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.candidates.normalize.skills import (
    SKILL_CATEGORIES, canonical_ids, category_for_canonical, norm_key,
    set_curated_overlay,
)
from app.core.config import Settings, get_settings
from app.curation.schema import (
    CurationAction, CurationStatus, UnmappedPage, UnmappedTerm,
)
from app.curation.store import CurationStore, build_curation_store

_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CurationService:
    def __init__(self, *, store: CurationStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    # --- capture (called by profile-source ingestion) -------------------------
    def record_unmapped(self, name: str, *, source_type: str) -> None:
        key = norm_key(name or "")
        if not key:
            return
        if not (self._settings.cur_min_term_len <= len(key) <= self._settings.cur_max_term_len):
            return
        self._store.record_unmapped(
            key, name.strip(), source_type=source_type, now=datetime.now(timezone.utc)
        )

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
        terms, next_cursor = self._store.list_terms(status, limit, cursor=cursor)
        return UnmappedPage(terms=terms, next_cursor=next_cursor)

    # --- resolve --------------------------------------------------------------
    def resolve(
        self, norm_key_value: str, action: CurationAction, *,
        canonical: Optional[str] = None, category: Optional[str] = None,
        note: Optional[str] = None, decided_by: Optional[str] = None,
    ) -> UnmappedTerm:
        if self._store.get_term(norm_key_value) is None:
            raise LookupError(f"unmapped term {norm_key_value!r} not found")
        canonical, category = self._validate(action, canonical, category)
        term = self._store.resolve(
            norm_key_value, action=action, canonical=canonical, category=category,
            note=note, decided_by=decided_by, now=datetime.now(timezone.utc),
        )
        self.refresh_overlay()
        return term

    def _validate(
        self, action: CurationAction, canonical: Optional[str], category: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        if action == CurationAction.IGNORE:
            if canonical or category:
                raise ValueError("ignore takes no canonical/category")
            return None, None
        if action == CurationAction.MAP:
            if not canonical:
                raise ValueError("map requires a canonical")
            if canonical not in canonical_ids():
                raise ValueError(f"unknown canonical {canonical!r}")
            return canonical, category_for_canonical(canonical)  # category derived
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
        set_curated_overlay(self._store.load_overlay())


def build_curation_service(settings: Optional[Settings] = None) -> CurationService:
    settings = settings or get_settings()
    return CurationService(store=build_curation_store(settings), settings=settings)
