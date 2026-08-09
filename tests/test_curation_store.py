from datetime import datetime, timedelta, timezone

from app.candidates.normalize.skills import SkillMatch
from app.curation.schema import CurationAction, CurationStatus
from app.curation.store import CurationStore
from tests.conftest import make_candidate_store

T0 = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _store() -> CurationStore:
    cs = make_candidate_store()  # in-memory engine; create_all built unmapped_terms
    return CurationStore(cs._session_factory)


def test_record_inserts_then_bumps_and_unions_sources():
    st = _store()
    st.record_unmapped("cobol", "COBOL", source_type="linkedin_export", now=T0)
    st.record_unmapped("cobol", "Cobol", source_type="github", now=T0 + timedelta(days=1))
    term = st.get_term("cobol")
    assert term.occurrences == 2
    assert set(term.source_types) == {"linkedin_export", "github"}
    assert term.display_name == "Cobol"          # refreshed to most recent
    assert term.last_seen == T0 + timedelta(days=1)
    assert term.status == CurationStatus.PENDING


def test_resolved_term_is_not_requeued_or_recounted():
    st = _store()
    st.record_unmapped("cobol", "COBOL", source_type="linkedin_export", now=T0)
    st.resolve("cobol", action=CurationAction.CREATE, canonical="cobol",
               category="language", note=None, decided_by="ops", now=T0)
    st.record_unmapped("cobol", "COBOL", source_type="github", now=T0 + timedelta(days=2))
    term = st.get_term("cobol")
    assert term.status == CurationStatus.RESOLVED
    assert term.occurrences == 1                  # not bumped
    assert term.source_types == ["linkedin_export"]  # not unioned


def test_list_orders_by_occurrences_then_recency_and_filters_status():
    st = _store()
    st.record_unmapped("aterm", "Aterm", source_type="github", now=T0)
    st.record_unmapped("bterm", "Bterm", source_type="github", now=T0)
    st.record_unmapped("bterm", "Bterm", source_type="github", now=T0 + timedelta(days=1))
    pending, _ = st.list_terms(CurationStatus.PENDING, limit=10)
    assert [t.norm_key for t in pending] == ["bterm", "aterm"]  # bterm has 2 occ
    st.resolve("aterm", action=CurationAction.IGNORE, canonical=None, category=None,
               note=None, decided_by=None, now=T0)
    assert [t.norm_key for t in st.list_terms(CurationStatus.PENDING, limit=10)[0]] == ["bterm"]
    assert [t.norm_key for t in st.list_terms(CurationStatus.IGNORED, limit=10)[0]] == ["aterm"]
    assert len(st.list_terms(None, limit=10)[0]) == 2  # no filter


def test_resolve_unknown_raises():
    st = _store()
    try:
        st.resolve("ghost", action=CurationAction.IGNORE, canonical=None, category=None,
                   note=None, decided_by=None, now=T0)
        assert False, "expected LookupError"
    except LookupError:
        pass


def test_ignore_stores_no_canonical_and_load_overlay_skips_it():
    st = _store()
    st.record_unmapped("team player", "Team Player", source_type="linkedin_export", now=T0)
    st.record_unmapped("cobol", "COBOL", source_type="linkedin_export", now=T0)
    st.resolve("team player", action=CurationAction.IGNORE, canonical=None, category=None,
               note=None, decided_by=None, now=T0)
    st.resolve("cobol", action=CurationAction.CREATE, canonical="cobol", category="language",
               note=None, decided_by=None, now=T0)
    overlay = st.load_overlay()
    assert overlay == {"cobol": SkillMatch(canonical="cobol", category="language")}
