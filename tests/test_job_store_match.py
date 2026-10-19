from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.features import default_view
from app.features.materialize import MaterializedVector, materialize_candidate
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


@pytest.mark.parametrize("denial", ["foreign_org", "revoked", "expired", "wrong_purpose"])
@pytest.mark.parametrize("filter_gated", [False, True])
def test_direct_match_authorizes_gated_ranking_for_asking_org(monkeypatch, denial, filter_gated):
    # Shipped requisitions rank first-party terms only. Extend the real pure
    # compiler in this probe so the direct-store authorization boundary is
    # observable through scores, contributions and filters, not a spy on inputs.
    import importlib
    engine = importlib.import_module("app.matching.match")
    from app.features.ranking_schema import FeatureFilter, FilterOp, RankingSpec, RankingTerm
    from app.ledger.schema import ConsentPurpose

    original_ranking = engine.compile_ranking
    def ranking(req, settings):
        base = original_ranking(req, settings)
        return RankingSpec(terms=(*base.terms, RankingTerm(feature="reputation.score", weight=1.0)))
    monkeypatch.setattr(engine, "compile_ranking", ranking)
    monkeypatch.setattr("app.matching.store.compile_ranking", ranking)
    if filter_gated:
        monkeypatch.setattr(engine, "compile_filters", lambda req: [
            FeatureFilter(feature="reputation.score", op=FilterOp.GTE, value=0.1),
        ])

    cands, ledger, features, jobs, settings = _wire()
    a = ledger.create_organization("Asking A")
    b = ledger.create_organization("Other B")
    denied = _seed_candidate(cands, features, ledger, "Denied", "denied@x.io", ("python",))
    allowed = _seed_candidate(cands, features, ledger, "Allowed", "allowed@x.io", ("python",))
    current = AS_OF + timedelta(days=1)
    monkeypatch.setattr("app.features.serving._utcnow", lambda: current)
    for cid, org, value in [(denied, b if denial == "foreign_org" else a, 0.99), (allowed, a, 0.2)]:
        grant = ledger.grant_consent(
            candidate_id=cid, org_id=org.id,
            purpose=ConsentPurpose.VERIFICATION_READ if cid == denied and denial == "wrong_purpose"
                    else ConsentPurpose.LEDGER_READ,
            now=AS_OF, expires_at=current if cid == denied and denial == "expired"
                    else current + timedelta(days=7),
        )
        if cid == denied and denial == "revoked":
            ledger.revoke_consent(grant.id, now=current)
        raw = features.get_vector(cid, view_name="core_v1",
            view_version=default_view(settings=settings).version, as_of=AS_OF)
        values = {**raw.vector.values, "reputation.score": value}
        features.upsert_vector(MaterializedVector(raw.vector.model_copy(update={"values": values}),
                                                  {"allowed": True}, raw.materialized_at))
    req = jobs.create_requisition(a.id, JobRequisitionInput(title="BE", must_have_skills=("python",)))
    result = jobs.run_match(a.id, req.id, as_of=AS_OF)
    rows = {r.candidate_id: r for r in result.ranked}
    assert result.pool_size == 2
    assert rows[allowed].contributions[-1].feature == "reputation.score"
    assert rows[allowed].contributions[-1].raw == 0.2
    if filter_gated:
        assert result.filtered_size == 1 and set(rows) == {allowed}
    else:
        assert set(rows) == {denied, allowed}
        assert rows[denied].score == 1.0  # present skill term; withheld term drops
        assert [c.feature for c in rows[denied].contributions] == ["match.skill_coverage"]
        assert rows[denied].missing == ("reputation.score",)
    assert features.get_vector(denied, view_name="core_v1", view_version=default_view(settings=settings).version,
                               as_of=AS_OF).vector.values["reputation.score"] == 0.99
