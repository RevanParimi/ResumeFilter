"""Api route extraction regressions, grouped by behavior."""

import hashlib
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.main import create_app
from tests.conftest import make_services, ADMIN_HEADERS
from tests.test_auth_api import _code, capture_path, cfg
from tests.test_route_table_guard import _walk
from app.graph.build import EvaluationEngine
from tests.test_candidates_api import RESUME
from tests.test_profile_sources_api import _linkedin_b64
from app.reports.outcomes import build_outcome
from app.reports.schema import OutcomeLabel, OutcomeSource
from app.schemas.report import Report


# Api route extraction

CONTRACT = Path(__file__).parent / "fixtures/api_contract_r4_s1_t3.json"


def runtime_contract(app):
    def dependencies(node):
        return [
            {"call": sub.call.__name__, "dependencies": dependencies(sub)}
            for sub in node.dependencies
        ]

    routes = [
        {"path": route.path, "methods": sorted(route.methods), "name": route.name,
         "operation_id": route.operation_id, "status_code": route.status_code,
         "dependencies": dependencies(route.dependant),
         "inherited": sorted(call.__name__ for call in inherited)}
        for route, inherited in _walk(app.routes) if hasattr(route, "dependant")
    ]
    return {"openapi": app.openapi(), "ordered_routes": routes}


def contract_digest(contract):
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_product_extraction_preserves_full_openapi_and_ordered_auth_contract(services):
    expected = json.loads(CONTRACT.read_text(encoding="utf-8"))
    actual = runtime_contract(create_app(services))
    assert len(actual["ordered_routes"]) == expected["operations"]
    assert contract_digest(actual) == expected["sha256"]


def test_auth_router_runs_standalone_with_cookie_csrf_and_session_ownership(cfg, capture_path):
    from app.api.auth import auth_router
    from app.api.routes import auth_router as legacy_router

    assert legacy_router is auth_router
    services = make_services(cfg)
    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    with TestClient(app) as first, TestClient(app) as second:
        sessions = []
        for client, email in ((first, "router-first@example.in"), (second, "router-second@example.in")):
            accepted = client.post("/auth/candidate/signup", json={"email": email})
            assert accepted.status_code == 202 and accepted.json() == {"status": "accepted"}
            verified = client.post("/auth/candidate/verify", json={"email": email, "code": _code(capture_path)})
            assert verified.status_code == 200
            assert verified.json()["principal"] == "candidate"
            cookies = verified.headers.get_list("set-cookie")
            assert any(cfg.session_cookie_name + "=" in value and "HttpOnly" in value for value in cookies)
            assert any(cfg.csrf_cookie_name + "=" in value and "HttpOnly" not in value for value in cookies)
            me = client.get("/auth/me").json()
            listed = client.get("/auth/sessions")
            assert listed.status_code == 200
            assert [row["id"] for row in listed.json()] == [me["session_id"]]
            sessions.append((me["session_id"], verified.json()["csrf_token"]))
        own, csrf = sessions[0]
        other, _ = sessions[1]
        assert first.post(f"/auth/sessions/{own}/revoke").status_code == 403
        first.headers["X-CSRF-Token"] = csrf
        assert first.post(f"/auth/sessions/{other}/revoke").status_code == 404
        assert first.post(f"/auth/sessions/{own}/revoke").json() == {"session_id": own, "revoked": True}
        assert first.get("/auth/me").status_code == 401
        assert second.get("/auth/me").status_code == 200


# Operator report extraction

def test_standalone_operator_reports_preserve_refusals_provenance_and_erasure(services, genuine_resume):
    from app.api.reports import evaluation_router, report_router

    app = FastAPI()
    app.state.services = services
    app.state.engine = EvaluationEngine(services)
    app.include_router(evaluation_router)
    app.include_router(report_router)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/report/missing").status_code == 401
        client.headers.update(ADMIN_HEADERS)
        assert client.post("/evaluate", json={"resume_text": "   "}).status_code == 422
        assert client.post("/evaluate", json={"resume_text": genuine_resume, "domain": "missing"}).status_code == 422
        response = client.post("/evaluate", json={"resume_text": genuine_resume})
        assert response.status_code == 200
        report = response.json()
        assert report["advisory"] and report["human_review_required"]
        rid = report["id"]
        assert client.get(f"/report/{rid}").json() == report
        assert client.get(f"/report/{rid}/outcomes").json() == {"report_id": rid, "outcomes": []}
        for body in (
            {"outcome": "inconclusive", "claim_id": "unknown-claim"},
            {"outcome": "inconclusive", "notes": "x" * (services.settings.max_outcome_notes_chars + 1)},
        ):
            assert client.post(f"/report/{rid}/outcome", json=body).status_code == 422
            assert services.report_store.outcomes(rid) == []
        accepted = client.post(f"/report/{rid}/outcome", json={"outcome": "inconclusive", "notes": "Private operator judgment"})
        assert accepted.status_code == 200
        assert accepted.json()["report_id"] == rid
        assert accepted.json()["claim_id"] is None
        row = client.get(f"/report/{rid}/outcomes").json()["outcomes"][0]
        assert row["recorded_by"] == "operator" and row["org_id"] is None
        assert row["notes"] == "Private operator judgment"
        observed = [item for item in services.flywheel.records if item.get("record_type") == "outcome"]
        assert len(observed) == 1 and "notes" not in observed[0]
        assert services.report_store.delete(rid)
        assert services.report_store.outcomes(rid) == []
        assert client.get(f"/report/{rid}").status_code == 404
        assert client.get(f"/report/{rid}/outcomes").status_code == 404
        assert client.post(f"/report/{rid}/outcome", json={"outcome": "inconclusive"}).status_code == 404


# Candidate route extraction

def candidate_app(services):
    from app.api.auth import auth_router
    from app.api.candidates import router as candidate_router

    app = FastAPI()
    app.state.services = services
    app.state.engine = EvaluationEngine(services)
    app.include_router(auth_router)
    app.include_router(candidate_router)
    return app


def test_candidate_workflow_preserves_versions_sources_ownership_and_erasure(services):
    with TestClient(candidate_app(services), raise_server_exceptions=False) as client:
        assert client.post("/candidates", json={"resume_text": RESUME}).status_code == 401
        client.headers.update(ADMIN_HEADERS)
        for body in ({}, {"resume_text": "   "}, {"resume_pdf_b64": "!!!"},
                     {"resume_text": RESUME, "domain": "missing"}):
            assert client.post("/candidates", json=body).status_code == 422
        response = client.post("/candidates", json={"resume_text": RESUME})
        assert response.status_code == 200, response.text
        first = response.json()
        cid, rid = first["candidate_id"], first["report"]["id"]
        path = f"/candidates/{cid}"
        assert first["extraction_method"] == "heuristic"
        assert first["report"]["advisory"] and first["report"]["human_review_required"]
        duplicate = client.post("/candidates", json={"resume_text": RESUME, "evaluate": False}).json()
        assert duplicate["duplicate_resume"] and duplicate["resume_id"] == first["resume_id"]
        updated = client.post("/candidates", json={"resume_text": RESUME + "\nAWS certification.", "evaluate": False}).json()
        assert updated["candidate_id"] == cid and updated["resume_version"] == 2
        assert updated["report"] is None
        detail = client.get(path).json()
        assert detail["resume_count"] == 2 and detail["latest_profile"] is not None
        assert detail["email_hash"] != "asha.rao@example.com"
        assert detail["latest_profile"]["contact"]["email"]["value"] == "asha.rao@example.com"
        assert [row["version"] for row in client.get(path + "/resumes").json()["resumes"]] == [1, 2]
        assert [row["id"] for row in client.get(path + "/reports").json()] == [rid]

        other = client.post("/candidates", json={"resume_text": RESUME.replace("asha.rao@example.com", "other@example.com").replace("+91 98765 43210", "+91 91234 56789"), "evaluate": False}).json()
        assert other["candidate_id"] != cid
        refused = client.delete(path + f"/resumes/{other['resume_id']}")
        assert refused.status_code == 404 and refused.json()["detail"] == "resume not found for candidate"
        assert client.delete(path + f"/resumes/{updated['resume_id']}").json() == {"resume_id": updated["resume_id"], "deleted": True}
        assert client.get(path).json()["resume_count"] == 1

        assert client.post(path + "/sources/github", json={}).status_code == 400
        github = client.post(path + "/sources/github", json={"handle": "octocat"})
        assert github.status_code == 200 and github.json()["method"] == "api"
        assert any(skill["canonical"] == "python" for skill in github.json()["skills"])
        assert client.post(path + "/sources/linkedin", json={"export_b64": "!!!"}).json() == {"detail": "invalid_base64"}
        linkedin = client.post(path + "/sources/linkedin", json={"export_b64": _linkedin_b64()})
        assert linkedin.status_code == 200 and linkedin.json()["method"] == "export"
        assert len(client.get(path + "/sources").json()["sources"]) == 2
        assert client.get(path + "/sources", params={"source_type": "linkedin_export"}).json()["sources"] == [linkedin.json()]

        key = client.post(path + "/auth-key").json()["access_key"]
        assert services.candidates.authenticate_candidate(key) == cid
        deleted = client.delete(path)
        assert deleted.status_code == 200 and deleted.json() == {"candidate_id": cid, "deleted": True, "reports_deleted": 1}
        assert services.candidates.authenticate_candidate(key) is None
        assert services.report_store.get(rid) is None
        assert services.profile_sources._store.signals_for_candidate(cid) == []
        for suffix in ("", "/resumes", "/reports", "/sources"):
            assert client.get(path + suffix).status_code == 404
        assert client.post(path + "/auth-key").status_code == 404
        assert client.post(path + "/sources/github", json={"handle": "octocat"}).status_code == 404
        assert client.post(path + "/sources/linkedin", json={"export_b64": _linkedin_b64()}).status_code == 404
        assert client.delete(path).status_code == 404
        assert client.get(f"/candidates/{other['candidate_id']}").json()["resume_count"] == 1


def test_standalone_candidate_admin_cookie_requires_csrf_and_denies_org(cfg, capture_path):
    services = make_services(cfg)
    services.auth.create_admin_user(email_hash=services.auth.hash_email("candidate-router-admin@example.in"))
    with TestClient(candidate_app(services), raise_server_exceptions=False) as admin, \
            TestClient(candidate_app(services), raise_server_exceptions=False) as org:
        email = "candidate-router-admin@example.in"
        assert admin.post("/auth/admin/login", json={"email": email}).status_code == 202
        session = admin.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert session.status_code == 200
        body = {"resume_text": RESUME, "evaluate": False}
        assert admin.post("/candidates", json=body).status_code == 403
        admin.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        created = admin.post("/candidates", json=body)
        assert created.status_code == 200
        path = f"/candidates/{created.json()['candidate_id']}"
        assert admin.get(path).status_code == 200
        admin.headers.pop("X-CSRF-Token")
        assert admin.post(path + "/auth-key").status_code == 403
        assert admin.post(path + "/sources/github", json={"handle": "octocat"}).status_code == 403
        assert admin.delete(path).status_code == 403
        org_email = "candidate-router-org@example.in"
        assert org.post("/auth/org/signup", json={"email": org_email, "organization_name": "Synthetic candidate router org"}).status_code == 202
        verified = org.post("/auth/org/verify", json={"email": org_email, "code": _code(capture_path)})
        assert verified.status_code == 200
        org.headers["X-CSRF-Token"] = verified.json()["csrf_token"]
        assert org.get(path).status_code == 401
        assert org.post("/candidates", json=body).status_code == 401
        assert org.delete(path).status_code == 401


# Screening route extraction

def screening_app(services):
    from app.api.auth import auth_router
    from app.api.screening import org_router

    app = FastAPI()
    app.state.services = services
    app.state.engine = EvaluationEngine(services)
    app.include_router(auth_router)
    app.include_router(org_router)
    return app


def test_screening_workflow_preserves_tenancy_outcomes_and_batch_lifecycle(services, genuine_resume):
    organizations = [services.ledger.create_organization(name) for name in ("Router A", "Router B")]
    keys = [services.ledger.issue_api_key(org.id) for org in organizations]
    with TestClient(screening_app(services), raise_server_exceptions=False) as a, \
            TestClient(screening_app(services), raise_server_exceptions=False) as b:
        assert a.get("/screening/batches").status_code == 401
        a.headers["X-Org-Key"], b.headers["X-Org-Key"] = keys
        uploaded = a.post("/screening/candidates", json={"resume_text": genuine_resume})
        assert uploaded.status_code == 200, uploaded.text
        upload = uploaded.json()
        cid, rid = upload["candidate_id"], upload["report"]["id"]
        report_path = f"/screening/reports/{rid}"
        assert upload["report"]["advisory"] and upload["report"]["human_review_required"]
        assert a.get(report_path).json() == upload["report"]
        assert [row["id"] for row in a.get(f"/screening/candidates/{cid}/reports").json()] == [rid]
        assert b.get(f"/screening/candidates/{cid}/reports").json() == []
        services.report_store.add_outcome(build_outcome(Report.model_validate(upload["report"]),
            outcome=OutcomeLabel.INCONCLUSIVE, claim_id=None, notes="Private operator note", recorded_by=OutcomeSource.OPERATOR,
            max_notes_chars=services.settings.max_outcome_notes_chars))
        assert a.get(report_path + "/outcomes").json()["outcomes"] == []
        for body in ({"outcome": "inconclusive", "claim_id": "missing"},
                     {"outcome": "inconclusive", "notes": "x" * (services.settings.max_outcome_notes_chars + 1)}):
            assert a.post(report_path + "/outcome", json=body).status_code == 422
        assert a.post(report_path + "/outcome", json={"outcome": "candidate_clarified", "notes": "Human review"}).status_code == 200
        judgments = a.get(report_path + "/outcomes").json()["outcomes"]
        assert len(judgments) == 1 and judgments[0]["recorded_by"] == "organization"
        assert judgments[0]["org_id"] == organizations[0].id
        assert judgments[0]["recorded_by_org_user_id"] is None
        for suffix in ("", "/outcomes"):
            assert b.get(report_path + suffix).json() == b.get("/screening/reports/missing" + suffix).json() == {"detail": "report not found"}
            assert b.get(report_path + suffix).status_code == 404
        assert b.post(report_path + "/outcome", json={"outcome": "inconclusive"}).status_code == 404

        batch_body = {"name": "Router intake", "items": [{"resume_text": genuine_resume}, {"resume_text": genuine_resume + "\nUpdated availability."}]}
        refused = a.post("/screening/batches", json={"items": [batch_body["items"][0], {"resume_pdf_b64": "!!!"}]})
        assert refused.status_code == 422 and refused.json() == {"detail": "item 1: pdf_parse_failed"}
        assert a.get("/screening/batches").json()["batches"] == []
        registered = a.post("/screening/batches", json=batch_body)
        assert registered.status_code == 200, registered.text
        batch = registered.json()
        bid, path = batch["id"], f"/screening/batches/{batch['id']}"
        assert batch["counts"]["pending"] == 2 and batch["created_by_org_user_id"] is None
        assert [row["id"] for row in a.get("/screening/batches").json()["batches"]] == [bid]
        assert b.get("/screening/batches").json()["batches"] == []
        for suffix in ("", "/queue", "/summary"):
            response = b.get(path + suffix)
            assert response.status_code == 404 and response.json() == {"detail": "batch not found"}
        for suffix in ("/process", "/retry"):
            assert b.post(path + suffix).status_code == 404
        assert b.delete(path).status_code == 404
        for target in ("/screening/batches", path + "/queue"):
            assert a.get(target, params={"cursor": "!!!"}).status_code == 422
        result = a.post(path + "/process")
        assert result.status_code == 200, result.text
        assert result.json()["processed"] == 2 and result.json()["remaining"] == 0
        detail = a.get(path).json()
        assert detail["counts"]["done"] == 2 and detail["status"] == "complete"
        first_page = a.get(path + "/queue", params={"limit": 1}).json()
        assert len(first_page["rows"]) == 1 and first_page["next_cursor"]
        second_page = a.get(path + "/queue", params={"cursor": first_page["next_cursor"], "limit": 1}).json()
        rows = first_page["rows"] + second_page["rows"]
        assert len({row["item_id"] for row in rows}) == 2
        assert all(row["advisory"] and row["human_review_required"] and row["reason"] for row in rows)
        assert all("full_name" not in row and "matches" not in row["signals"] for row in rows)
        summary = a.get(path + "/summary").json()
        assert summary["n_screened"] == 2 and summary["advisory"] and summary["human_review_required"]
        assert a.post(path + "/retry").json() == {"batch_id": bid, "requeued": 0, "skipped": 0}
        assert a.delete(path).json() == {"batch_id": bid, "deleted": True}
        assert a.get(path).status_code == 404
        assert a.get("/screening/batches").json()["batches"] == []
        assert a.get(report_path).status_code == 200


def test_screening_cookie_csrf_and_human_provenance(cfg, capture_path, genuine_resume):
    services = make_services(cfg)
    with TestClient(screening_app(services), raise_server_exceptions=False) as client:
        email = "screening-router@example.in"
        assert client.post("/auth/org/signup", json={"email": email, "organization_name": "Router session"}).status_code == 202
        verified = client.post("/auth/org/verify", json={"email": email, "code": _code(capture_path)})
        assert verified.status_code == 200
        body = {"items": [{"resume_text": genuine_resume}]}
        assert client.post("/screening/batches", json=body).status_code == 403
        assert client.post("/screening/candidates", json={"resume_text": genuine_resume}).status_code == 403
        client.headers["X-CSRF-Token"] = verified.json()["csrf_token"]
        created = client.post("/screening/batches", json=body)
        assert created.status_code == 200, created.text
        bid = created.json()["id"]
        human = services.auth._store.org_user_by_email(services.auth.hash_email(email)).id
        assert human and created.json()["created_by_org_user_id"] == human
        assert client.post(f"/screening/batches/{bid}/process").status_code == 200
        rid = client.get(f"/screening/batches/{bid}/queue").json()["rows"][0]["report_id"]
        assert client.post(f"/screening/reports/{rid}/outcome", json={"outcome": "inconclusive"}).status_code == 200
        assert client.get(f"/screening/reports/{rid}/outcomes").json()["outcomes"][0]["recorded_by_org_user_id"] == human
        client.headers.pop("X-CSRF-Token")
        assert client.post(f"/screening/batches/{bid}/process").status_code == 403
        assert client.post(f"/screening/batches/{bid}/retry").status_code == 403
        assert client.delete(f"/screening/batches/{bid}").status_code == 403
        assert client.post(f"/screening/reports/{rid}/outcome", json={"outcome": "inconclusive"}).status_code == 403
