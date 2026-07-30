import pytest

from app.candidates.normalize.skills import clear_curated_overlay, normalize_skill
from app.curation.schema import CurationAction, CurationStatus
from app.curation.service import CurationService
from app.curation.store import CurationStore
from tests.conftest import make_candidate_store


def _svc(settings) -> CurationService:
    cs = make_candidate_store()
    return CurationService(store=CurationStore(cs._session_factory), settings=settings)


def teardown_function():
    clear_curated_overlay()


def test_record_applies_length_guards(settings):
    svc = _svc(settings)  # cur_min_term_len=2, cur_max_term_len=64
    svc.record_unmapped("x", source_type="github")             # too short
    svc.record_unmapped("a" * 65, source_type="github")        # too long
    svc.record_unmapped("   ", source_type="github")           # empty norm_key
    svc.record_unmapped("COBOL", source_type="linkedin_export")
    keys = [t.norm_key for t in svc.list_unmapped(CurationStatus.PENDING)]
    assert keys == ["cobol"]


def test_list_limit_clamped_to_config(settings):
    svc = _svc(settings)
    for i in range(5):
        svc.record_unmapped(f"term{i}", source_type="github")
    assert len(svc.list_unmapped(limit=2)) == 2
    assert len(svc.list_unmapped(limit=10_000)) == 5  # clamped to cur_queue_default_limit


def test_resolve_create_makes_normalize_skill_resolve(settings):
    svc = _svc(settings)
    svc.record_unmapped("COBOL", source_type="linkedin_export")
    assert normalize_skill("COBOL") is None
    term = svc.resolve("cobol", CurationAction.CREATE, canonical="cobol", category="language")
    assert term.status == CurationStatus.RESOLVED
    assert normalize_skill("COBOL").canonical == "cobol"   # overlay refreshed live


def test_resolve_map_to_existing_canonical(settings):
    svc = _svc(settings)
    svc.record_unmapped("PyTorch Lightning", source_type="github")
    term = svc.resolve("pytorch lightning", CurationAction.MAP, canonical="pytorch")
    assert term.canonical == "pytorch" and term.category == "ml"  # category derived
    assert normalize_skill("PyTorch Lightning").canonical == "pytorch"


def test_resolve_validation_matrix(settings):
    svc = _svc(settings)
    for k in ("t1", "t2", "t3", "t4", "t5"):
        svc.record_unmapped(k, source_type="github")
    with pytest.raises(ValueError):  # map to unknown canonical
        svc.resolve("t1", CurationAction.MAP, canonical="not_a_real_skill")
    with pytest.raises(ValueError):  # map with no canonical
        svc.resolve("t2", CurationAction.MAP)
    with pytest.raises(ValueError):  # create bad category
        svc.resolve("t3", CurationAction.CREATE, canonical="cobol", category="nope")
    with pytest.raises(ValueError):  # create canonical that already exists
        svc.resolve("t4", CurationAction.CREATE, canonical="python", category="language")
    with pytest.raises(ValueError):  # ignore with a canonical is contradictory
        svc.resolve("t5", CurationAction.IGNORE, canonical="python")


def test_resolve_unknown_term_raises_lookup(settings):
    svc = _svc(settings)
    with pytest.raises(LookupError):
        svc.resolve("ghost", CurationAction.IGNORE)


def test_create_bad_id_shape_rejected(settings):
    svc = _svc(settings)
    svc.record_unmapped("Some Skill", source_type="github")
    with pytest.raises(ValueError):  # not snake_case
        svc.resolve("some skill", CurationAction.CREATE, canonical="Not Snake", category="language")
