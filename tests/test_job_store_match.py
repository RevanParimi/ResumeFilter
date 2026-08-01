from datetime import datetime, timezone

from app.core.config import Settings
from app.features.materialize import materialize_candidate
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.matching.schema import JobRequisitionInput
from app.matching.store import JobStore
from tests.conftest import make_candidate_store, set_extraction_created_at

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def _profile(name, email, skills, tier=None):
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, SkillItem,
    )
    return CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(email=ExtractedStr(value=email), location_tier=tier),
        skills=[SkillItem(name=s, canonical=s) for s in skills],
    )


def _wire():
    cands = make_candidate_store()
    sf = cands._session_factory
    s = _settings()
    ledger = LedgerStore(sf, settings=s)
    features = FeatureStore(sf)
    jobs = JobStore(sf, candidate_store=cands, feature_store=features, settings=s)
    return cands, ledger, features, jobs, s


def _seed_candidate(cands, features, ledger, name, email, skills, tier=None):
    from app.candidates.schema import ExtractionResult
    from app.features import default_view, get_feature_registry
    from app.reports.store import SqlReportStore
    saved = cands.ingest(
        ExtractionResult(profile=_profile(name, email, skills, tier), method="heuristic"),
        resume_text=email,
    )
    cid = saved.candidate_id
    set_extraction_created_at(cands, cid, AS_OF.replace(tzinfo=None))
    registry = get_feature_registry()
    mv = materialize_candidate(
        cid, view=default_view(registry), registry=registry, as_of=AS_OF,
        candidate_store=cands, report_store=SqlReportStore(cands._session_factory), ledger_store=ledger,
    )
    features.upsert_vector(mv)
    return cid


def test_run_match_ranks_by_skill_coverage_and_audits_disclosure():
    cands, ledger, features, jobs, s = _wire()
    org = ledger.create_organization("Acme")
    strong = _seed_candidate(cands, features, ledger, "Strong", "strong@x.io", ("python", "django"))
    weak = _seed_candidate(cands, features, ledger, "Weak", "weak@x.io", ("python",))
    req = jobs.create_requisition(org.id, JobRequisitionInput(
        title="BE", must_have_skills=("python", "django"),
    ))
    result = jobs.run_match(org.id, req.id, as_of=AS_OF)
    assert result.advisory is True
    assert [m.candidate_id for m in result.ranked] == [strong, weak]
    assert result.pool_size == 2
    strong_audit = [a for a in ledger.audit_for_candidate(strong) if a.action == "match.surface"]
    assert len(strong_audit) == 1
    assert strong_audit[0].actor_id == org.id


def test_run_match_cross_org_returns_none():
    cands, ledger, features, jobs, s = _wire()
    a = ledger.create_organization("A")
    b = ledger.create_organization("B")
    req = jobs.create_requisition(a.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    assert jobs.run_match(b.id, req.id, as_of=AS_OF) is None


def test_run_match_empty_pool_reports_zero():
    cands, ledger, features, jobs, s = _wire()
    org = ledger.create_organization("A")
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    result = jobs.run_match(org.id, req.id, as_of=AS_OF)  # nothing materialized
    assert result.pool_size == 0
    assert result.ranked == ()


def test_dpdp_erasure_sweeps_match_surface_audit():
    cands, ledger, features, jobs, s = _wire()
    org = ledger.create_organization("A")
    cid = _seed_candidate(cands, features, ledger, "C", "c@x.io", ("python",))
    req = jobs.create_requisition(org.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    jobs.run_match(org.id, req.id, as_of=AS_OF)
    assert [a for a in ledger.audit_for_candidate(cid) if a.action == "match.surface"]
    cands.delete_candidate(cid)
    assert ledger.audit_for_candidate(cid) == []  # candidate-linked rows CASCADE
