from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult, SkillItem,
)
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
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


def test_board_requires_org_key(services):
    with _client(services) as c:
        assert c.get("/jobs/x/board").status_code == 401


def test_board_404_cross_org_and_empty_pool_reason(services):
    _, key_a = _org_key(services, "A")
    org_b = services.ledger.create_organization("B")
    key_b = services.ledger.issue_api_key(org_b.id)
    with _client(services) as c:
        req = c.post("/jobs", headers={"X-Org-Key": key_a},
                     json={"title": "BE", "must_have_skills": ["python"]}).json()
        # cross-org -> 404
        assert c.get(f"/jobs/{req['id']}/board", headers={"X-Org-Key": key_b}).status_code == 404
        # owned but nothing materialized -> 200 with a reason (S8.4 Phase B):
        # an empty feature store is a server-side state, not a client error.
        board = c.get(f"/jobs/{req['id']}/board", headers={"X-Org-Key": key_a})
        assert board.status_code == 200
        assert board.json()["match"]["reason"] == "no_materialized_candidates"


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
        assert body["match"]["pool_size"] == 1
        assert body["match"]["ranked"][0]["candidate_id"]
