from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult, SkillItem,
)
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.ledger.schema import ConsentPurpose
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, set_extraction_created_at

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)
AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS) as c:
        yield c


def _org_key(services, name="Acme"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _candidate(services, name="Ann", email="ann@x.io", skills=("python",)):
    saved = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value=name),
                contact=ContactInfo(email=ExtractedStr(value=email)),
                skills=[SkillItem(name=s, canonical=s) for s in skills],
            ),
            method="heuristic",
        ),
        resume_text=email,
    )
    return saved.candidate_id


def _materialize(services, candidate_id):
    registry = get_feature_registry()
    set_extraction_created_at(services.candidates, candidate_id, AS_OF.replace(tzinfo=None))
    mv = materialize_candidate(
        candidate_id, view=default_view(registry), registry=registry, as_of=AS_OF,
        candidate_store=services.candidates, report_store=services.report_store,
        ledger_store=services.ledger,
    )
    services.features.upsert_vector(mv)


def test_all_dashboard_routes_require_org_key(services):
    with _client(services) as c:
        assert c.get("/dashboard/overview").status_code == 401
        assert c.get("/jobs/x/board").status_code == 401
        assert c.get("/candidates/x/card").status_code == 401


def test_overview_endpoint(services):
    _, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    with _client(services) as c:
        c.post("/jobs", headers=hdr, json={"title": "BE", "must_have_skills": ["python"]})
        r = c.get("/dashboard/overview", headers=hdr)
        assert r.status_code == 200
        body = r.json()
        assert body["total_requisitions"] == 1
        assert body["by_status"] == {"open": 1}
        assert body["advisory"] is True


def test_board_404_cross_org_and_422_empty_pool(services):
    _, key_a = _org_key(services, "A")
    org_b = services.ledger.create_organization("B")
    key_b = services.ledger.issue_api_key(org_b.id)
    with _client(services) as c:
        req = c.post("/jobs", headers={"X-Org-Key": key_a},
                     json={"title": "BE", "must_have_skills": ["python"]}).json()
        # cross-org -> 404
        assert c.get(f"/jobs/{req['id']}/board", headers={"X-Org-Key": key_b}).status_code == 404
        # owned but nothing materialized -> 422
        assert c.get(f"/jobs/{req['id']}/board", headers={"X-Org-Key": key_a}).status_code == 422


def test_board_200_with_materialized_pool(services):
    org_id, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    _materialize(services, _candidate(services, "Strong", "s@x.io", ("python", "django")))
    with _client(services) as c:
        req = c.post("/jobs", headers=hdr,
                     json={"title": "BE", "must_have_skills": ["python", "django"],
                           "comp_band": {"ctc_min": 800000, "ctc_max": 900000}}).json()
        r = c.get(f"/jobs/{req['id']}/board", headers=hdr)
        assert r.status_code == 200
        body = r.json()
        assert body["requisition"]["id"] == req["id"]
        assert body["comp"]["advisory"] is True
        assert body["match"]["pool_size"] == 1
        assert body["match"]["ranked"][0]["candidate_id"]


def test_card_consent_flow(services):
    org_id, key = _org_key(services)
    hdr = {"X-Org-Key": key}
    cand_id = _candidate(services)
    with _client(services) as c:
        # unknown candidate -> 404
        assert c.get("/candidates/nope/card", headers=hdr).status_code == 404
        # known candidate, no grant -> 200, all sections consent_required
        r0 = c.get(f"/candidates/{cand_id}/card", headers=hdr)
        assert r0.status_code == 200
        b0 = r0.json()
        assert b0["reputation"]["status"] == "consent_required"
        assert b0["records"]["status"] == "consent_required"
        # grant read -> sections resolve (no data submitted -> no_data)
        services.ledger.grant_consent(
            candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_READ, org_id=org_id,
            expires_at=NOW + timedelta(days=90))
        b1 = c.get(f"/candidates/{cand_id}/card", headers=hdr).json()
        assert b1["records"]["status"] == "no_data"
        assert b1["coding_rounds"]["status"] == "no_data"
