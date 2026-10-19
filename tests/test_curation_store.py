"""Legacy curation has read-only normalization compatibility after activation."""

from app.candidates.normalize.skills import SkillMatch
from app.curation.store import CurationStore
from tests.conftest import make_candidate_store
from tests.curation_helpers import legacy_term


def test_legacy_overlay_reads_only_resolved_vocabulary_and_preserves_storage():
    factory = make_candidate_store()._session_factory
    legacy_term(factory, "pending")
    legacy_term(factory, "ignored", status="ignored")
    legacy_term(factory, "approved", status="resolved", canonical="python", category="language")
    store = CurationStore(factory)
    assert store.load_owned_overlay() == {"approved": SkillMatch(canonical="python", category="language")}
    assert store.list_observations() == ([], None)
    assert store.purge_expired() == 0
    from app.curation.models import UnmappedTermRow
    from sqlalchemy import select
    with factory() as session:
        assert len(session.execute(select(UnmappedTermRow)).scalars().all()) == 3


def test_runtime_store_has_no_legacy_write_or_resolve_entry_points():
    assert not hasattr(CurationStore, "record_unmapped")
    assert not hasattr(CurationStore, "resolve")
    assert not hasattr(CurationStore, "list_terms")
    assert not hasattr(CurationStore, "get_term")
