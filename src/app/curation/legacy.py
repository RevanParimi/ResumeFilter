"""Explicit offline disposition of unattributed legacy curation content."""

from datetime import datetime, timezone

from sqlalchemy import case, delete, func, insert, select, text

from app.candidates.normalize.skills import norm_key
from app.curation.models import CurationAliasRow, UnmappedTermRow
from app.curation.schema import CurationAction
from app.curation.service import CurationService
from app.curation.store import _bounded_text

MAX_SELECTION = 200
LEGACY = "legacy_unattributed"


class LegacyDispositionError(ValueError):
    """Fixed, raw-free operator errors; database errors must also be suppressed."""


def validate_selection(entries):
    """Strict bounded manifest; never reuse historical text as approval input."""
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_SELECTION:
        raise LegacyDispositionError("selection must contain 1 to 200 entries")
    result, ids, keys = [], set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise LegacyDispositionError("invalid selection entry")
        action = entry.get("action")
        required = {"id", "action"}
        if action in ("map", "create"):
            required |= {"alias", "canonical", "category"}
        elif action != "remove":
            raise LegacyDispositionError("invalid disposition action")
        if set(entry) != required or not _bounded_text(entry.get("id"), 36):
            raise LegacyDispositionError("invalid selection fields")
        if entry["id"] in ids:
            raise LegacyDispositionError("duplicate selected ID")
        ids.add(entry["id"])
        cleaned = dict(entry)
        if action != "remove":
            if not (_bounded_text(entry["alias"], 128)
                    and _bounded_text(entry["canonical"], 64)
                    and _bounded_text(entry["category"], 32)):
                raise LegacyDispositionError("invalid approved vocabulary")
            try:
                # Same canonical/category policy as the authenticated reviewer.
                CurationService._validate(CurationAction(action), entry["canonical"], entry["category"])
            except ValueError:
                raise LegacyDispositionError("invalid approved vocabulary") from None
            key = norm_key(entry["alias"])
            if not key or len(key) > 128 or key in keys:
                raise LegacyDispositionError("invalid or duplicate approved alias")
            keys.add(key)
            cleaned.update(alias=entry["alias"].strip(), norm_key=key)
        result.append(cleaned)
    return result


def inventory(conn):
    """One counts-only snapshot; unknown status values are never returned."""
    row = UnmappedTermRow.__table__
    statuses = ("pending", "ignored", "resolved")
    counts = conn.execute(select(func.count().label("total"), *[
        func.coalesce(func.sum(case((row.c.status == status, 1), else_=0)), 0).label(status)
        for status in statuses]).where(row.c.provenance == LEGACY)).mappings().one()
    result = dict(counts)
    result["other"] = result["total"] - sum(result[status] for status in statuses)
    return result


def dispose(conn, entries, *, apply=False):
    """Caller owns the transaction. Any error must roll back the whole batch.

    Apply serializes legacy writers on PG; SQLite's write transaction does so.
    Deleted IDs authorize approvals, so replay never creates another decision.
    No raw names/keys/notes/identities are loaded, copied or returned.
    """
    entries = validate_selection(entries)
    row, aliases = UnmappedTermRow.__table__, CurationAliasRow.__table__
    ids = [entry["id"] for entry in entries]
    if apply:
        if conn.dialect.name == "postgresql":
            conn.execute(text("LOCK TABLE unmapped_terms IN SHARE ROW EXCLUSIVE MODE"))
        elif conn.dialect.name == "sqlite":
            # Acquire the write reservation before reading the selected IDs.
            # A no-op UPDATE also works inside an existing caller transaction.
            conn.execute(row.update().where(row.c.id.in_(ids), row.c.provenance == LEGACY)
                         .values(provenance=LEGACY))
        else:
            raise LegacyDispositionError("unsupported database")
    found = dict(conn.execute(select(row.c.id, row.c.provenance)
                              .where(row.c.id.in_(ids))).all())
    if any(provenance != LEGACY for provenance in found.values()):
        raise LegacyDispositionError("selection includes nonlegacy rows")
    if apply:
        claimed = set(conn.scalars(delete(row).where(row.c.id.in_(ids), row.c.provenance == LEGACY)
                                   .returning(row.c.id)))
    else:
        claimed = set(found)
    approvals = [entry for entry in entries if entry["id"] in claimed and entry["action"] != "remove"]
    for entry in approvals:
        key = entry["norm_key"]
        if (conn.scalar(select(aliases.c.norm_key).where(aliases.c.norm_key == key)) is not None
                or conn.scalar(select(row.c.id).where(row.c.norm_key == key,
                    row.c.status == "resolved", row.c.id.not_in(claimed))) is not None):
            raise LegacyDispositionError("approved alias conflicts with retained vocabulary")
    if apply and approvals:
        conn.execute(insert(aliases), [dict(norm_key=entry["norm_key"], alias=entry["alias"],
            canonical=entry["canonical"], category=entry["category"], action=entry["action"],
            decided_at=datetime.now(timezone.utc), admin_user_id=None) for entry in approvals])
    return dict(selected=len(entries), matched=len(claimed), absent=len(entries) - len(claimed),
                removed=len(claimed), approved=len(approvals))
