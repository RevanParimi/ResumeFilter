from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.features.materialize import materialize_candidate
from app.main import create_app
from app.matching.schema import RequisitionStatus
from tests.conftest import ADMIN_HEADERS, set_extraction_created_at

AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _profile(name, email, skills):
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, SkillItem,
    )
    return CandidateProfile(
        full_name=ExtractedStr(value=name),
        contact=ContactInfo(email=ExtractedStr(value=email)),
        skills=[SkillItem(name=s, canonical=s) for s in skills],
    )


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        yield c


def _org_key(services, name="Acme"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_create_requires_org_key(services):
    with _client(services) as c:
        assert c.post("/jobs", json={"title": "BE", "must_have_skills": ["python"]}).status_code == 401


def test_crud_and_match_flow(services, settings):
    _, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    with _client(services) as c:
        # create
        r = c.post("/jobs", headers=hdr,
                   json={"title": "BE", "must_have_skills": ["React.js", "Postgres"]})
        assert r.status_code == 200
        req = r.json()
        assert set(req["must_have_skills"]) == {"react", "postgresql"}

        # get / list
        assert c.get(f"/jobs/{req['id']}", headers=hdr).status_code == 200
        assert len(c.get("/jobs", headers=hdr).json()) == 1
        assert c.get("/jobs/does-not-exist", headers=hdr).status_code == 404

        # patch (close)
        p = c.patch(f"/jobs/{req['id']}", headers=hdr, json={"status": "closed"})
        assert p.json()["status"] == RequisitionStatus.CLOSED.value

        # match with empty pool -> 200 with a reason (S8.4 Phase B). An empty
        # feature store is a SERVER-side state, and until this sprint there was
        # no HTTP route a caller could use to fix it -- a 422 blamed the client
        # for something only an operator could change.
        m0 = c.post(f"/jobs/{req['id']}/match", headers=hdr, json={"as_of": AS_OF.isoformat()})
        assert m0.status_code == 200
        assert m0.json()["pool_size"] == 0
        assert m0.json()["reason"] == "no_materialized_candidates"


def test_cross_org_match_404(services):
    _, key_a = _org_key(services, "A")
    org_b = services.ledger.create_organization("B")
    key_b = services.ledger.issue_api_key(org_b.id)
    with _client(services) as c:
        req = c.post("/jobs", headers={"X-Org-Key": key_a},
                     json={"title": "BE", "must_have_skills": ["python"]}).json()
        r = c.post(f"/jobs/{req['id']}/match", headers={"X-Org-Key": key_b},
                   json={"as_of": AS_OF.isoformat()})
        assert r.status_code == 404


def test_match_ranks_materialized_pool(services, settings):
    org_id, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    from app.candidates.schema import ExtractionResult
    from app.features import default_view, get_feature_registry
    registry = get_feature_registry()
    for name, email, skills in [
        ("Strong", "s@x.io", ["python", "django"]),
        ("Weak", "w@x.io", ["python"]),
    ]:
        saved = services.candidates.ingest(
            ExtractionResult(profile=_profile(name, email, skills), method="heuristic"),
            resume_text=email,
        )
        set_extraction_created_at(services.candidates, saved.candidate_id, AS_OF.replace(tzinfo=None))
        mv = materialize_candidate(
            saved.candidate_id, view=default_view(registry), registry=registry, as_of=AS_OF,
            candidate_store=services.candidates, report_store=services.report_store,
            ledger_store=services.ledger,
        )
        services.features.upsert_vector(mv)
    with _client(services) as c:
        req = c.post("/jobs", headers=hdr,
                     json={"title": "BE", "must_have_skills": ["python", "django"]}).json()
        m = c.post(f"/jobs/{req['id']}/match", headers=hdr, json={"as_of": AS_OF.isoformat()})
        assert m.status_code == 200
        body = m.json()
        assert body["advisory"] is True
        assert body["ranked"][0]["skill"]["coverage"] == 1.0
        assert body["pool_size"] == 2
