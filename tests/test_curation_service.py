import pytest

from app.candidates.normalize.skills import clear_curated_overlay, normalize_skill
from app.curation.schema import CurationAction, CurationStatus
from app.curation.service import CurationService
from app.curation.store import CurationStore
from tests.conftest import make_candidate_store
from tests.curation_helpers import saved_source


def _svc(settings) -> tuple[CurationService, str]:
    cs = make_candidate_store()
    return CurationService(store=CurationStore(cs._session_factory), settings=settings), saved_source(cs._session_factory)[1]


def teardown_function():
    clear_curated_overlay()


def test_record_applies_length_guards(settings):
    svc, source = _svc(settings)  # cur_min_term_len=2, cur_max_term_len=64
    svc.record_unmapped("x", source_id=source)             # too short
    svc.record_unmapped("a" * 65, source_id=source)        # too long
    svc.record_unmapped("   ", source_id=source)           # empty norm_key
    svc.record_unmapped("COBOL", source_id=source)
    keys = [t.norm_key for t in svc.list_unmapped(CurationStatus.PENDING).terms]
    assert keys == ["cobol"]


def test_list_limit_clamped_to_config(settings):
    # use a small cap to prove the limit is actually enforced
    small = settings.model_copy(update={"cur_queue_default_limit": 3})
    svc, source = _svc(small)
    for i in range(5):
        svc.record_unmapped(f"term{i}", source_id=source)
    assert len(svc.list_unmapped(limit=10_000).terms) == 3   # clamped to cap (3), not 5
    assert len(svc.list_unmapped(limit=2).terms) == 2        # explicit smaller limit honored
    assert len(svc.list_unmapped().terms) == 3               # default is the cap


def test_resolve_create_makes_normalize_skill_resolve(settings):
    svc, source = _svc(settings)
    svc.record_unmapped("COBOL", source_id=source)
    assert normalize_skill("COBOL") is None
    term = svc.resolve("cobol", CurationAction.CREATE, alias="COBOL", canonical="cobol", category="language")
    assert term.action == CurationAction.CREATE
    assert normalize_skill("COBOL").canonical == "cobol"   # overlay refreshed live


def test_resolve_map_to_existing_canonical(settings):
    svc, source = _svc(settings)
    svc.record_unmapped("PyTorch Lightning", source_id=source)
    term = svc.resolve("pytorch lightning", CurationAction.MAP, alias="PyTorch Lightning", canonical="pytorch", category="ml")
    assert term.canonical == "pytorch" and term.category == "ml"
    assert normalize_skill("PyTorch Lightning").canonical == "pytorch"


def test_resolve_validation_matrix(settings):
    svc, source = _svc(settings)
    for k in ("t1", "t2", "t3", "t4", "t5"):
        svc.record_unmapped(k, source_id=source)
    with pytest.raises(ValueError):  # map to unknown canonical
        svc.resolve("t1", CurationAction.MAP, alias="Approved term", canonical="not_a_real_skill", category="language")
    with pytest.raises(ValueError):  # map with no canonical
        svc.resolve("t2", CurationAction.MAP)
    with pytest.raises(ValueError):  # create bad category
        svc.resolve("t3", CurationAction.CREATE, canonical="cobol", category="nope")
    with pytest.raises(ValueError):  # create canonical that already exists
        svc.resolve("t4", CurationAction.CREATE, canonical="python", category="language")
    with pytest.raises(ValueError):  # ignore with a canonical is contradictory
        svc.resolve("t5", CurationAction.IGNORE, canonical="python")
    with pytest.raises(ValueError):
        svc.resolve("t1", CurationAction.MAP, alias="Approved term", canonical="python", category="ml")
    assert len(svc.list_unmapped().terms) == 5


def test_resolve_missing_valid_request_is_not_found(settings):
    svc, source = _svc(settings)
    with pytest.raises(LookupError):
        svc.resolve("ghost", CurationAction.IGNORE)



def test_create_bad_id_shape_rejected(settings):
    svc, source = _svc(settings)
    svc.record_unmapped("Some Skill", source_id=source)
    with pytest.raises(ValueError):  # not snake_case
        svc.resolve("some skill", CurationAction.CREATE, canonical="Not Snake", category="language")


def test_guarded_service_conflict_preserves_raw_and_overlay(settings):
    from app.curation.store import StaleReviewError

    svc, source = _svc(settings)
    svc.record_unmapped("Review raw", source_id=source)
    snapshot, = svc.list_unmapped().terms
    svc.record_unmapped("Review raw", source_id=source)
    with pytest.raises(StaleReviewError, match="review snapshot changed"):
        svc.resolve("review raw", CurationAction.MAP, alias="Approved revision",
            canonical="python", category="language", expected_revision=snapshot.review_revision)
    assert svc.list_unmapped().terms[0].occurrences == 2
    assert normalize_skill("Approved revision") is None
    fresh, = svc.list_unmapped().terms
    svc.resolve("review raw", CurationAction.MAP, alias="Approved revision",
        canonical="python", category="language", expected_revision=fresh.review_revision)
    assert normalize_skill("Approved revision").canonical == "python"
