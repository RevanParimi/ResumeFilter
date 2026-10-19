"""Synthetic durable sources and historical rows for curation regressions."""

from datetime import datetime, timezone

from app.candidates.models import CandidateRow
from app.curation.models import UnmappedTermRow
from app.profile_sources.schema import ProfileSourceSignal, ProfileSourceType
from app.profile_sources.store import ProfileSourceStore


def saved_source(factory, *, kind=ProfileSourceType.GITHUB):
    with factory.begin() as session:
        candidate = CandidateRow(full_name="Synthetic contributor")
        session.add(candidate)
        session.flush()
        cid = candidate.id
    source = ProfileSourceStore(factory).save_signal(cid, ProfileSourceSignal(
        source_type=kind, identifier="synthetic", fetched_at=datetime.now(timezone.utc)))
    return cid, source


def legacy_term(factory, key="legacy", *, status="pending", **values):
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add(UnmappedTermRow(**(dict(norm_key=key, display_name="Legacy private text",
            source_types=["github"], occurrences=1, first_seen=now, last_seen=now,
            status=status, note="Legacy note", decided_by="Legacy supplied identity") | values)))
