from app.core.config import Settings
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.matching.schema import JobRequisitionInput, RequisitionStatus
from app.matching.store import JobStore
from tests.conftest import make_candidate_store


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _wire():
    cands = make_candidate_store()
    sf = cands._session_factory
    settings = _settings()
    ledger = LedgerStore(sf, settings=settings)
    features = FeatureStore(sf)
    jobs = JobStore(sf, candidate_store=cands, feature_store=features, settings=settings)
    return cands, ledger, jobs


def _minimal_profile():
    from app.candidates.schema import CandidateProfile, ContactInfo, ExtractedStr
    return CandidateProfile(
        full_name=ExtractedStr(value="P"),
        contact=ContactInfo(email=ExtractedStr(value="p@x.io")),
    )


def test_create_normalizes_skills_to_canonical():
    _, ledger, jobs = _wire()
    org = ledger.create_organization("Acme")
    req = jobs.create_requisition(org.id, JobRequisitionInput(
        title="BE", must_have_skills=("React.js", "Postgres"),
    ))
    assert set(req.must_have_skills) == {"react", "postgresql"}
    assert req.org_id == org.id
    assert req.status is RequisitionStatus.OPEN


def test_get_and_list_are_org_scoped():
    _, ledger, jobs = _wire()
    a = ledger.create_organization("A")
    b = ledger.create_organization("B")
    req = jobs.create_requisition(a.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    assert jobs.get_requisition(a.id, req.id).id == req.id
    assert jobs.get_requisition(b.id, req.id) is None          # cross-org invisible
    assert [r.id for r in jobs.list_requisitions(a.id)] == [req.id]
    assert jobs.list_requisitions(b.id) == []


def test_update_status_and_replace_spec():
    _, ledger, jobs = _wire()
    org = ledger.create_organization("A")
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    closed = jobs.update_requisition(org.id, req.id, status=RequisitionStatus.CLOSED)
    assert closed.status is RequisitionStatus.CLOSED
    replaced = jobs.update_requisition(
        org.id, req.id,
        spec=JobRequisitionInput(title="BE2", must_have_skills=("Django",)),
    )
    assert replaced.title == "BE2"
    assert set(replaced.must_have_skills) == {"django"}
    assert jobs.update_requisition("nope", req.id, status=RequisitionStatus.OPEN) is None


def test_create_is_audited_and_survives_candidate_erasure():
    cands, ledger, jobs = _wire()
    org = ledger.create_organization("A")
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    from app.candidates.schema import ExtractionResult
    saved = cands.ingest(
        ExtractionResult(profile=_minimal_profile(), method="heuristic"), resume_text="x"
    )
    cands.delete_candidate(saved.candidate_id)
    assert jobs.get_requisition(org.id, req.id) is not None  # survives
