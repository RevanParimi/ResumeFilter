"""Api route extraction regressions, grouped by behavior."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import pytest
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
from tests.test_ledger_api import _coding_payload, _ingest_candidate
from tests.test_dashboard_api import _candidate as dashboard_candidate, _materialize, AS_OF
from tests.test_talent_search_api import _seed as seed_search_vector, _AS_OF as SEARCH_CUT


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


# Ledger route extraction

def ledger_app(services):
    from app.api.auth import auth_router
    from app.api.ledger import router, org_router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(router)
    app.include_router(org_router)
    return app


def test_ledger_workflow_preserves_key_lifecycle_consent_ownership_and_audits(services):
    cid = asyncio.run(_ingest_candidate(services))
    record_body = {"candidate_id": cid, "stage": "hm", "outcome": "hired",
                   "interviewed_at": "2026-10-01T10:00:00+00:00", "summary": "Human assessment"}
    coding_body = _coding_payload(cid)
    root = f"/ledger/candidates/{cid}"
    with TestClient(ledger_app(services), raise_server_exceptions=False) as control, \
            TestClient(ledger_app(services), raise_server_exceptions=False) as a, \
            TestClient(ledger_app(services), raise_server_exceptions=False) as b:
        assert control.get("/ledger/orgs").status_code == 401
        control.headers.update(ADMIN_HEADERS)
        created = []
        for name, actor in (("Ledger A", a), ("Ledger B", b)):
            response = control.post("/ledger/orgs", json={"name": name})
            assert response.status_code == 200, response.text
            created.append(response.json())
            actor.headers["X-Org-Key"] = response.json()["api_key"]
        oid = created[0]["org"]["id"]
        assert control.post("/ledger/orgs", json={"name": "Ledger A"}).status_code == 409
        assert control.get("/ledger/orgs").json() == [item["org"] for item in created]
        assert a.get("/ledger/orgs").status_code == 401
        assert control.post("/ledger/records", json=record_body).status_code == 401
        org_path = f"/ledger/orgs/{oid}"
        assert control.post(org_path + "/reliability", json={"weight": -1}).status_code == 422
        assert control.post(org_path + "/reliability", json={"weight": 1.75}).json()["reliability_weight"] == 1.75
        for suffix in ("records", "coding-rounds", "reputation"):
            assert a.get(root + "/" + suffix).status_code == 403
        for target, body in (("/ledger/records", record_body), ("/ledger/coding-rounds", coding_body)):
            assert a.post(target, json=body).status_code == 403
            assert a.post(target, json={**body, "candidate_id": "missing"}).status_code == 404
        grants = {}
        for purpose in ("ledger_read", "ledger_write"):
            response = control.post(root + "/consent", json={"purpose": purpose, "org_id": oid})
            assert response.status_code == 200
            grants[purpose] = response.json()["id"]
            assert control.get(root + "/consent", params={"org_id": oid, "purpose": purpose}).json() == {
                "allowed": True, "reason": f"active grant {grants[purpose]} covers purpose '{purpose}'", "grant_id": grants[purpose]}
        record = a.post("/ledger/records", json=record_body)
        assert record.status_code == 200, record.text
        row = record.json()
        assert row["org_id"] == oid and row["consent_id"] == grants["ledger_write"]
        event_path = f"/ledger/records/{row['id']}/events"
        event_body = {"event_type": "reviewed", "payload": {"decision": "human"}}
        event = a.post(event_path, json=event_body)
        assert event.status_code == 200 and event.json()["record_id"] == row["id"]
        assert event.json()["payload"] == event_body["payload"]
        refused = b.post(event_path, json=event_body)
        missing = b.post("/ledger/records/missing/events", json=event_body)
        assert refused.status_code == missing.status_code == 404
        assert refused.json() == missing.json() == {"detail": "record not found"}
        assert len(services.ledger.events_for_record(row["id"])) == 1
        assert a.post("/ledger/coding-rounds", json={**coding_body, "percentile": 101}).status_code == 422
        coding = a.post("/ledger/coding-rounds", json=coding_body)
        assert coding.status_code == 200, coding.text
        assert coding.json()["consent_id"] == grants["ledger_write"]
        assert a.get(root + "/records").json() == [row]
        assert a.get(root + "/coding-rounds").json() == [coding.json()]
        reputation = a.get(root + "/reputation")
        assert reputation.status_code == 200
        assert reputation.json()["advisory"] and reputation.json()["total_observations"] == 2
        for suffix in ("records", "coding-rounds", "reputation"):
            assert b.get(root + "/" + suffix).status_code == 403
            assert a.get("/ledger/candidates/missing/" + suffix).status_code == 404
        assert b.post("/ledger/records", json=record_body).status_code == 403
        # Reads are cross-company when the subject explicitly grants that org.
        read_b = control.post(root + "/consent", json={"purpose": "ledger_read", "org_id": created[1]["org"]["id"]}).json()
        assert b.get(root + "/records").json() == [row]
        assert control.post(f"/ledger/consent/{read_b['id']}/revoke").json()["revoked"]
        for purpose, grant_id in grants.items():
            path = f"/ledger/consent/{grant_id}/revoke"
            assert control.post(path).json() == {"consent_id": grant_id, "revoked": True}
            assert control.post(path).json()["revoked"] is False
            assert not control.get(root + "/consent", params={"org_id": oid, "purpose": purpose}).json()["allowed"]
        for purpose in ("ledger_read", "ledger_write"):
            assert control.post(root + "/consent", json={"purpose": purpose, "org_id": oid,
                "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}).status_code == 200
        for suffix in ("records", "coding-rounds", "reputation"):
            assert a.get(root + "/" + suffix).status_code == 403
        assert a.post("/ledger/records", json=record_body).status_code == 403
        assert a.post("/ledger/coding-rounds", json=coding_body).status_code == 403
        audits = services.ledger.audit_for_candidate(cid)
        for action in ("record.query", "coding_round.query", "reputation.query"):
            assert {item.details["allowed"] for item in audits if item.action == action} == {True, False}
        rotated = control.post(org_path + "/api-key")
        assert rotated.status_code == 200 and rotated.json()["api_key"] != created[0]["api_key"]
        assert a.get(root + "/records").status_code == 401
        a.headers["X-Org-Key"] = rotated.json()["api_key"]
        assert a.get(root + "/records").status_code == 403
        assert control.delete(org_path).json() == {"org_id": oid, "deleted": True}
        assert a.get(root + "/records").status_code == 401
        assert control.delete(org_path).status_code == 404
        assert control.post(org_path + "/api-key").status_code == 404
        assert control.post(org_path + "/reliability", json={"weight": 1}).status_code == 404
        assert control.post("/ledger/candidates/missing/consent", json={"purpose": "ledger_read"}).status_code == 404


def test_ledger_admin_and_org_cookies_preserve_csrf_and_auth_planes(cfg, capture_path):
    services = make_services(cfg)
    cid = asyncio.run(_ingest_candidate(services))
    email = "ledger-router-admin@example.in"
    services.auth.create_admin_user(email_hash=services.auth.hash_email(email))
    with TestClient(ledger_app(services), raise_server_exceptions=False) as admin, \
            TestClient(ledger_app(services), raise_server_exceptions=False) as org:
        assert admin.post("/auth/admin/login", json={"email": email}).status_code == 202
        verified = admin.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert verified.status_code == 200
        admin_csrf = verified.json()["csrf_token"]
        admin.headers["X-CSRF-Token"] = admin_csrf
        created = admin.post("/ledger/orgs", json={"name": "Cookie ledger admin"}).json()
        oid = created["org"]["id"]
        consent_path = f"/ledger/candidates/{cid}/consent"
        grant = admin.post(consent_path, json={"purpose": "ledger_write"}).json()
        admin.headers.pop("X-CSRF-Token")
        # A valid header alongside the cookie must not bypass CSRF.
        admin.headers.update(ADMIN_HEADERS)
        for method, path, body in (
            ("POST", "/ledger/orgs", {"name": "Refused"}),
            ("POST", f"/ledger/orgs/{oid}/api-key", None),
            ("DELETE", f"/ledger/orgs/{oid}", None),
            ("POST", f"/ledger/orgs/{oid}/reliability", {"weight": 0}),
            ("POST", consent_path, {"purpose": "ledger_read"}),
            ("POST", f"/ledger/consent/{grant['id']}/revoke", None),
        ):
            assert admin.request(method, path, json=body).status_code == 403
        assert len(admin.get("/ledger/orgs").json()) == 1
        assert services.ledger.get_grant(grant["id"]).revoked_at is None
        admin.headers.pop("X-API-Key")
        admin.headers["X-CSRF-Token"] = admin_csrf
        org_email = "ledger-router-org@example.in"
        assert org.post("/auth/org/signup", json={"email": org_email, "organization_name": "Cookie ledger org"}).status_code == 202
        verified = org.post("/auth/org/verify", json={"email": org_email, "code": _code(capture_path)})
        assert verified.status_code == 200
        org.headers["X-CSRF-Token"] = verified.json()["csrf_token"]
        body = {"candidate_id": cid, "stage": "screen", "outcome": "advanced", "interviewed_at": "2026-10-01T10:00:00Z"}
        record = org.post("/ledger/records", json=body)
        assert record.status_code == 200
        event_path = f"/ledger/records/{record.json()['id']}/events"
        writes = [("/ledger/records", body), (event_path, {"event_type": "reviewed"}),
                  ("/ledger/coding-rounds", _coding_payload(cid))]
        for path, payload in writes[1:]:
            assert org.post(path, json=payload).status_code == 200
        assert org.get("/ledger/orgs").status_code == 401
        assert org.post(consent_path, json={"purpose": "ledger_read"}).status_code == 401
        assert admin.post("/ledger/records", json=body).status_code == 401
        org.headers.pop("X-CSRF-Token")
        org.headers["X-Org-Key"] = created["api_key"]
        for path, payload in writes:
            assert org.post(path, json=payload).status_code == 403
        assert len(services.ledger.records_for_candidate(cid)) == 1
        assert len(services.ledger.coding_rounds_for_candidate(cid)) == 1
        assert len(services.ledger.events_for_record(record.json()["id"])) == 1


# Employer jobs, compensation and dashboard extraction

def employer_app(services):
    from app.api.auth import auth_router
    from app.api.employer import org_router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(org_router)
    return app


def test_employer_workflow_preserves_tenancy_ranking_compensation_and_consent(services):
    cid = dashboard_candidate(services, skills=("python", "django"))
    organizations = [services.ledger.create_organization(name) for name in ("Employer A", "Employer B")]
    keys = [services.ledger.issue_api_key(org.id) for org in organizations]
    spec = {"title": "Senior Backend Engineer", "must_have_skills": ["Python", "Django"],
            "min_years_experience": 5, "comp_band": {"ctc_min": 1500000, "ctc_max": 2500000}}
    offer = {"candidate_id": cid, "role_family": "backend_engineer", "seniority": "senior",
             "city_tier": "metro", "ctc_fixed": 2000000, "offered_at": datetime.now(timezone.utc).isoformat()}
    with TestClient(employer_app(services), raise_server_exceptions=False) as a, \
            TestClient(employer_app(services), raise_server_exceptions=False) as b:
        assert a.get("/jobs").status_code == 401
        a.headers["X-Org-Key"], b.headers["X-Org-Key"] = keys
        assert a.post("/jobs", json={"title": "Invalid"}).status_code == 422
        created = a.post("/jobs", json=spec)
        assert created.status_code == 200, created.text
        job = created.json()
        jid, path = job["id"], f"/jobs/{job['id']}"
        assert job["org_id"] == organizations[0].id and job["must_have_skills"] == ["python", "django"]
        assert a.get(path).json() == job
        assert a.get("/jobs").json() == [job] and b.get("/jobs").json() == []
        for suffix in ("", "/comp", "/board"):
            denied, missing = b.get(path + suffix), b.get("/jobs/missing" + suffix)
            assert denied.status_code == missing.status_code == 404
            assert denied.json() == missing.json() == {"detail": "requisition not found"}
        assert b.patch(path, json={"status": "closed"}).status_code == 404
        assert b.post(path + "/match", json={}).status_code == 404
        for response in (a.post(path + "/match", json={}), a.get(path + "/board")):
            assert response.status_code == 200
            match = response.json().get("match", response.json())
            assert match["advisory"] and match["pool_size"] == 0
            assert match["reason"] == "no_materialized_candidates"
        assert a.post(path + "/match", json={"limit": 0}).status_code == 422
        assert a.post("/comp/estimate", json={"role_family": "astronaut"}).status_code == 400
        estimate = a.post("/comp/estimate", json={"title": spec["title"], "years_experience": 5})
        assert estimate.status_code == 200
        value = estimate.json()
        assert value["advisory"] and value["estimate"]["advisory"]
        assert value["estimate"]["sources"] == ["static"]
        assert all(value[field] is None for field in ("requisition_band", "position", "delta_pct"))
        benchmark = a.get(path + "/comp")
        assert benchmark.status_code == 200 and benchmark.json()["advisory"]
        assert benchmark.json()["requisition_band"] == spec["comp_band"] | {"currency": "INR", "variable_max": None, "notes": None}
        card_path = f"/candidates/{cid}/card"
        sections = ("records", "coding_rounds", "reputation")
        assert a.get("/candidates/missing/card").status_code == 404
        assert all(a.get(card_path).json()[section]["status"] == "consent_required" for section in sections)
        assert a.post("/ledger/offers", json=offer).status_code == 403
        assert a.post("/ledger/offers", json={**offer, "city_tier": "moon"}).status_code == 400
        assert a.post("/ledger/offers", json={**offer, "ctc_fixed": -1}).status_code == 422
        assert a.post("/ledger/offers", json={**offer, "candidate_id": "missing"}).status_code == 404
        read = services.ledger.grant_consent(candidate_id=cid, purpose="ledger_read", org_id=organizations[0].id)
        write = services.ledger.grant_consent(candidate_id=cid, purpose="ledger_write", org_id=organizations[0].id)
        assert all(a.get(card_path).json()[section]["status"] == "no_data" for section in sections)
        submitted = a.post("/ledger/offers", json=offer)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["org_id"] == organizations[0].id and submitted.json()["consent_id"] == write.id
        assert b.post("/ledger/offers", json=offer).status_code == 403
        _materialize(services, cid)
        matched = a.post(path + "/match", json={"as_of": AS_OF.isoformat()})
        assert matched.status_code == 200, matched.text
        assert matched.json()["advisory"] and matched.json()["pool_size"] == 1
        assert matched.json()["ranked"][0]["candidate_id"] == cid
        assert matched.json()["ranked"][0]["skill"]["coverage"] == 1
        board = a.get(path + "/board")
        assert board.status_code == 200
        assert board.json()["advisory"] and board.json()["comp"]["advisory"]
        assert board.json()["match"]["ranked"][0]["candidate_id"] == cid
        assert a.patch(path, json={"status": "closed"}).json()["status"] == "closed"
        updated = a.patch(path, json={"spec": {**spec, "title": "Revised Backend Engineer"}})
        assert updated.status_code == 200 and updated.json()["title"] == "Revised Backend Engineer"
        assert a.get("/dashboard/overview").json()["total_requisitions"] == 1
        assert b.get("/dashboard/overview").json()["total_requisitions"] == 0
        services.ledger.revoke_consent(read.id)
        services.ledger.revoke_consent(write.id)
        assert all(a.get(card_path).json()[section]["status"] == "consent_required" for section in sections)
        assert a.post("/ledger/offers", json=offer).status_code == 403


def test_employer_cookie_requires_csrf_and_retains_tenant_precedence(cfg, capture_path):
    services = make_services(cfg)
    cid = dashboard_candidate(services)
    other = services.ledger.create_organization("Employer header tenant")
    key = services.ledger.issue_api_key(other.id)
    with TestClient(employer_app(services), raise_server_exceptions=False) as actor:
        email = "employer-router@example.in"
        assert actor.post("/auth/org/signup", json={"email": email, "organization_name": "Employer cookie tenant"}).status_code == 202
        verified = actor.post("/auth/org/verify", json={"email": email, "code": _code(capture_path)})
        assert verified.status_code == 200
        actor.headers["X-Org-Key"] = key
        spec = {"title": "Cookie engineer", "must_have_skills": ["python"]}
        assert actor.post("/jobs", json=spec).status_code == 403
        csrf = verified.json()["csrf_token"]
        actor.headers["X-CSRF-Token"] = csrf
        created = actor.post("/jobs", json=spec)
        assert created.status_code == 200
        job = created.json()
        oid, path = job["org_id"], f"/jobs/{job['id']}"
        assert oid != other.id
        services.ledger.grant_consent(candidate_id=cid, purpose="ledger_write", org_id=oid)
        writes = [("POST", "/jobs", spec), ("PATCH", path, {"status": "closed"}),
                  ("POST", path + "/match", {}), ("POST", "/comp/estimate", {"title": "Engineer"}),
                  ("POST", "/ledger/offers", {"candidate_id": cid, "role_family": "backend_engineer",
                    "seniority": "senior", "city_tier": "metro", "ctc_fixed": 1000000,
                    "offered_at": datetime.now(timezone.utc).isoformat()})]
        actor.headers.pop("X-CSRF-Token")
        for method, target, body in writes:
            assert actor.request(method, target, json=body).status_code == 403
        assert actor.get(path).json()["status"] == "open"
        assert len(actor.get("/jobs").json()) == 1
        actor.headers["X-CSRF-Token"] = csrf
        for method, target, body in writes[1:]:
            assert actor.request(method, target, json=body).status_code == 200
        with TestClient(employer_app(services), headers={"X-Org-Key": key}) as machine, \
                TestClient(employer_app(services), headers=ADMIN_HEADERS) as admin:
            assert machine.get(path).status_code == 404
            assert machine.get("/jobs").json() == []
            assert admin.get("/dashboard/overview").status_code == 401
            assert admin.post("/jobs", json=spec).status_code == 401


# Feature materialization and talent search extraction


def feature_app(services):
    from app.api.auth import auth_router
    from app.api.features import router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(router)
    return app


def test_feature_workflow_preserves_cuts_partial_refresh_errors_and_erasure(services):
    ids = [dashboard_candidate(services, name=name, email=name + "@example.in", skills=skills)
           for name, skills in (("FeatureOne", ("python",)), ("FeatureTwo", ("python", "sql")))]
    ranking = {"terms": [{"feature": "candidate.num_skills", "weight": 1}]}
    with TestClient(feature_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as client:
        empty = client.post("/talent/search", json={"ranking": ranking})
        assert empty.status_code == 200
        assert empty.json()["advisory"] and empty.json()["pool_size"] == 0
        assert empty.json()["as_of"] is None and empty.json()["ranked"] == []
        for path, body, status in (
            ("/features/materialize", {"view_name": "unknown-view"}, 422),
            ("/features/materialize", {"as_of": "bad-time"}, 422),
            ("/talent/search", {"ranking": {"terms": []}}, 422),
            ("/talent/search", {"ranking": ranking, "limit": 0}, 422),
            ("/talent/search", {"ranking": {"terms": [{"feature": "unknown.feature", "weight": 1}]}}, 400),
            ("/talent/search", {"ranking": ranking, "filters": [{"feature": "unknown.feature", "op": "exists"}]}, 400),
        ):
            assert client.post(path, json=body).status_code == status
        first = client.post("/features/materialize", json={})
        assert first.status_code == 200, first.text
        cut = first.json()
        assert cut["materialized"] == 2 and cut["skipped"] == 0
        assert cut["view_name"] == services.settings.feat_default_view and cut["as_of"]
        body = {"ranking": ranking, "as_of": cut["as_of"], "view_name": cut["view_name"],
                "view_version": cut["view_version"]}
        historical = client.post("/talent/search", json=body).json()
        assert historical["advisory"] and historical["pool_size"] == historical["filtered_size"] == 2
        assert [row["candidate_id"] for row in historical["ranked"]] == ids[::-1]
        assert historical["ranked"][0]["contributions"][0]["raw"] == 2
        refreshed = client.post("/features/materialize", json={"candidate_ids": [ids[0], "missing"]})
        assert refreshed.status_code == 200
        assert refreshed.json()["materialized"] == refreshed.json()["skipped"] == 1
        latest = client.post("/talent/search", json={"ranking": ranking, "limit": 1}).json()
        assert latest["pool_size"] == 2 and latest["ranked"][0]["candidate_id"] == ids[1]
        assert len(latest["ranked"]) == 1
        assert client.post("/talent/search", json=body).json() == historical
        assert client.post("/talent/search", json={**body, "as_of": SEARCH_CUT.isoformat()}).json()["pool_size"] == 0
        malformed = client.post("/talent/search", json={"ranking": ranking, "filters": [
            {"feature": "candidate.num_skills", "op": "gt", "value": "many"}]})
        assert malformed.status_code == 400
        services.portal.erase(ids[0])
        retry = client.post("/features/materialize", json={"candidate_ids": ids, "as_of": cut["as_of"]})
        assert retry.status_code == 200
        assert retry.json()["materialized"] == retry.json()["skipped"] == 1
        assert [row["candidate_id"] for row in client.post("/talent/search", json=body).json()["ranked"]] == ids[1:]


def test_feature_search_masks_revoked_historical_values_and_refuses_consent_failure(services, monkeypatch):
    ids = [asyncio.run(seed_search_vector(services, name, {
        "candidate.years_experience": years, "reputation.score": reputation}))
        for name, years, reputation in (("feature-a", 8, .9), ("feature-b", 2, .2))]
    orgs = [services.ledger.create_organization(name) for name in ("Feature A", "Feature B")]
    grants = [services.ledger.grant_consent(candidate_id=cid, org_id=org.id,
        purpose="ledger_read", now=SEARCH_CUT) for cid, org in zip(ids, orgs)]
    body = {"as_of": SEARCH_CUT.isoformat(), "ranking": {"terms": [
        {"feature": name, "weight": 1} for name in ("candidate.years_experience", "reputation.score")]}}
    with TestClient(feature_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as client:
        allowed = client.post("/talent/search", json=body)
        assert allowed.status_code == 200
        assert {row["candidate_id"] for row in allowed.json()["ranked"]} == set(ids)
        assert all(row["coverage"] == 1 for row in allowed.json()["ranked"])
        assert services.ledger.revoke_consent(grants[0].id)
        masked = {row["candidate_id"]: row for row in client.post("/talent/search", json=body).json()["ranked"]}
        assert masked[ids[0]]["coverage"] == .5 and masked[ids[1]]["coverage"] == 1
        assert masked[ids[0]]["missing"] == ["reputation.score"]
        assert [term["feature"] for term in masked[ids[0]]["contributions"]] == ["candidate.years_experience"]
        filtered = client.post("/talent/search", json={**body, "filters": [{"feature": "reputation.score", "op": "exists"}]})
        assert [row["candidate_id"] for row in filtered.json()["ranked"]] == ids[1:]
        stored = services.features.get_vector(ids[0], view_name="core_v1", view_version=allowed.json()["view_version"], as_of=SEARCH_CUT)
        assert stored.consent_state["allowed"] and stored.vector.values["reputation.score"] == .9
        def unavailable(_):
            raise RuntimeError("synthetic feature consent store failure")
        monkeypatch.setattr(services.ledger, "consents_for_candidate", unavailable)
        refused = client.post("/talent/search", json=body)
        assert refused.status_code == 500
        assert "ranked" not in refused.text and "synthetic feature consent store failure" not in refused.text


def test_feature_routes_preserve_admin_cookie_csrf_and_other_plane_refusals(cfg, capture_path):
    services = make_services(cfg)
    email = "feature-admin@example.in"
    services.auth.create_admin_user(email_hash=services.auth.hash_email(email))
    org = services.ledger.create_organization("Feature machine employer")
    org_key = services.ledger.issue_api_key(org.id)
    writes = (("/features/materialize", {}), ("/talent/search", {"ranking": {"terms": [
        {"feature": "candidate.num_skills", "weight": 1}]}}))
    with TestClient(feature_app(services), raise_server_exceptions=False) as admin, \
            TestClient(feature_app(services), raise_server_exceptions=False) as other:
        for path, body in writes:
            assert other.post(path, json=body).status_code == 401
            assert other.post(path, json=body, headers={"X-Org-Key": org_key}).status_code == 401
            assert other.post(path, json=body, headers=ADMIN_HEADERS).status_code == 200
        assert admin.post("/auth/admin/login", json={"email": email}).status_code == 202
        verified = admin.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert verified.status_code == 200
        admin.headers.update(ADMIN_HEADERS)
        for path, body in writes:
            assert admin.post(path, json=body).status_code == 403
            assert admin.post(path, json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
        admin.headers.pop("X-API-Key")
        admin.headers["X-CSRF-Token"] = verified.json()["csrf_token"]
        for path, body in writes:
            assert admin.post(path, json=body).status_code == 200
        for plane in ("org", "candidate"):
            other.cookies.clear()
            login = {"email": f"feature-{plane}@example.in"}
            if plane == "org":
                login["organization_name"] = "Feature cookie employer"
            assert other.post(f"/auth/{plane}/signup", json=login).status_code == 202
            verified = other.post(f"/auth/{plane}/verify", json={"email": login["email"], "code": _code(capture_path)})
            assert verified.status_code == 200
            for path, body in writes:
                assert other.post(path, json=body, headers={"X-CSRF-Token": verified.json()["csrf_token"]}).status_code == 401


# Candidate portal and data-principal requests extraction


def portal_app(services):
    from app.api.auth import auth_router
    from app.api.portal import candidate_router, router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(candidate_router)
    app.include_router(router)
    return app


def test_portal_workflow_preserves_subject_consent_review_audit_and_erasure(services):
    from app.ledger.store import ConsentError

    ids = [dashboard_candidate(services, name=name, email=name + "@example.in")
           for name in ("PortalOne", "PortalTwo")]
    keys = [services.candidates.issue_access_key(cid) for cid in ids]
    org = services.ledger.create_organization("Portal disclosure employer")
    with TestClient(portal_app(services), headers={"X-Candidate-Key": keys[0]}, raise_server_exceptions=False) as one, \
            TestClient(portal_app(services), headers={"X-Candidate-Key": keys[1]}, raise_server_exceptions=False) as two, \
            TestClient(portal_app(services), headers=ADMIN_HEADERS, raise_server_exceptions=False) as admin:
        assert one.get("/portal/me", params={"candidate_id": ids[1]}).json()["candidate_id"] == ids[0]
        assert admin.get("/portal/me").status_code == 401
        assert one.get("/admin/requests").status_code == 401
        grant = one.post("/portal/consents", json={"candidate_id": ids[1], "purpose": "ledger_read", "org_id": org.id})
        assert grant.status_code == 200 and grant.json()["candidate_id"] == ids[0]
        gid = grant.json()["id"]
        assert one.get("/portal/consents").json()[0]["state"] == "active"
        assert two.get("/portal/consents").json() == []
        assert one.post("/portal/consents", json={"purpose": "ledger_read", "org_id": "missing"}).status_code == 404
        assert one.post("/portal/consents", json={"purpose": "unknown"}).status_code == 422
        foreign, absent = [two.post(f"/portal/consents/{value}/revoke") for value in (gid, "missing")]
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json() == {"detail": "consent grant not found"}
        assert services.ledger.query_records_for_org(org_id=org.id, candidate_id=ids[0]) == []
        assert one.post(f"/portal/consents/{gid}/revoke").json() == {"consent_id": gid, "revoked": True}
        assert one.get("/portal/consents").json()[0]["state"] == "revoked"
        with pytest.raises(ConsentError):
            services.ledger.query_records_for_org(org_id=org.id, candidate_id=ids[0])
        queries = [row for row in one.get("/portal/access-log").json() if row["action"] == "record.query"]
        assert {row["allowed"] for row in queries} == {True, False}
        assert all(row["actor_name"] == org.name for row in queries)
        original = services.candidates.latest_profile(ids[0]).model_dump(mode="json")
        correction = one.post("/portal/corrections", json={"field": "full_name", "requested_value": "Reviewed Name"})
        assert correction.status_code == 200 and correction.json()["status"] == "open" and not correction.json()["applied"]
        grievance = two.post("/portal/grievances", json={"note": "Other subject's private complaint"})
        assert grievance.status_code == 200
        rid = correction.json()["id"]
        assert [row["id"] for row in one.get("/portal/requests", params={"candidate_id": ids[1]}).json()] == [rid]
        assert one.get("/portal/me").json()["requests"] == [correction.json()]
        assert {row["id"] for row in admin.get("/admin/requests").json()} == {rid, grievance.json()["id"]}
        assert len(admin.get("/admin/requests", params={"status": "open", "limit": 1}).json()) == 1
        for query in ({"limit": -1}, {"limit": 0}, {"status": "unknown"}):
            assert admin.get("/admin/requests", params=query).status_code == 422
        path = f"/admin/requests/{rid}/resolve"
        assert one.post(path, json={"status": "resolved", "resolution": "Denied"}).status_code == 401
        assert admin.post(path, json={"status": "rejected", "resolution": " "}).status_code == 422
        decided = admin.post(path, json={"status": "resolved", "resolution": "Human review recorded"})
        assert decided.status_code == 200 and not decided.json()["applied"]
        assert decided.json()["resolved_by"] == "operator_key"
        assert services.candidates.get_candidate(ids[0]).full_name == "PortalOne"
        assert admin.post(path, json={"status": "resolved", "resolution": "Again"}).status_code == 409
        assert admin.post("/admin/requests/missing/resolve", json={"status": "resolved", "resolution": "Unknown"}).status_code == 404
        second = one.post("/portal/corrections", json={"field": "full_name", "requested_value": "Reviewed Name"}).json()
        applied = admin.post(f"/admin/requests/{second['id']}/resolve", json={
            "status": "resolved", "resolution": "Explicitly reviewed", "apply": True})
        assert applied.status_code == 200 and applied.json()["applied"]
        assert services.candidates.get_candidate(ids[0]).full_name == "Reviewed Name"
        assert services.candidates.latest_profile(ids[0]).model_dump(mode="json") == original
        request_audit = [row["action"] for row in one.get("/portal/access-log").json()
                         if row["entity_type"] == "data_principal_request"]
        assert request_audit.count("request.submit") == request_audit.count("request.resolve") == 2
        erased = one.delete("/portal/me")
        assert erased.status_code == 200 and erased.json()["candidate_id"] == ids[0] and erased.json()["deleted"]
        assert one.get("/portal/me").status_code == 401 and one.get("/portal/requests").status_code == 401
        assert two.get("/portal/me").json()["candidate_id"] == ids[1]
        assert admin.get("/admin/requests").json() == [grievance.json()]


def test_portal_request_budget_and_erasure_errors_preserve_http_contract(settings, monkeypatch):
    services = make_services(settings.model_copy(update={"rate_limit_request_per_hour_per_candidate": 2}))
    cid = dashboard_candidate(services)
    key = services.candidates.issue_access_key(cid)
    with TestClient(portal_app(services), headers={"X-Candidate-Key": key}, raise_server_exceptions=False) as actor:
        assert actor.post("/portal/grievances", json={"note": " "}).status_code == 422
        assert actor.post("/portal/grievances", json={"note": "Valid request"}).status_code == 200
        refused = actor.post("/portal/corrections", json={"field": "full_name", "requested_value": "Name"})
        assert refused.status_code == 429 and refused.json() == {"detail": "rate_limited"}
        assert int(refused.headers["Retry-After"]) > 0
        from app.portal.service import PortalSubjectErasedError
        def erased(*args, **kwargs):
            raise PortalSubjectErasedError()
        for method, path in (("my_data", "/portal/me"), ("access_log", "/portal/access-log"), ("consents", "/portal/consents")):
            monkeypatch.setattr(services.portal, method, erased)
            assert actor.get(path).status_code == 404


def test_portal_cookie_precedence_csrf_named_review_and_erasure(cfg, capture_path):
    services = make_services(cfg)
    email = "portal-reviewer@example.in"
    services.auth.create_admin_user(email_hash=services.auth.hash_email(email))
    with TestClient(portal_app(services), raise_server_exceptions=False) as one, \
            TestClient(portal_app(services), raise_server_exceptions=False) as two, \
            TestClient(portal_app(services), raise_server_exceptions=False) as admin:
        subjects, tokens = [], []
        for actor, address in ((one, "portal-one@example.in"), (two, "portal-two@example.in")):
            assert actor.post("/auth/candidate/signup", json={"email": address}).status_code == 202
            verified = actor.post("/auth/candidate/verify", json={"email": address, "code": _code(capture_path)})
            assert verified.status_code == 200
            tokens.append(verified.json()["csrf_token"])
            subjects.append(actor.get("/portal/me").json()["candidate_id"])
        keys = [services.candidates.issue_access_key(cid) for cid in subjects]
        one.headers["X-Candidate-Key"] = keys[1]
        assert one.get("/portal/me").json()["candidate_id"] == subjects[0]
        writes = (("POST", "/portal/consents", {"purpose": "ledger_read"}),
                  ("POST", "/portal/corrections", {"field": "full_name", "requested_value": "Reviewed"}),
                  ("POST", "/portal/grievances", {"note": "Review me"}), ("DELETE", "/portal/me", None))
        for method, path, body in writes:
            assert one.request(method, path, json=body).status_code == 403
        one.headers["X-CSRF-Token"] = tokens[0]
        grant = one.post("/portal/consents", json={"purpose": "ledger_read"})
        assert grant.status_code == 200 and grant.json()["candidate_id"] == subjects[0]
        one.headers.pop("X-CSRF-Token")
        assert one.post(f"/portal/consents/{grant.json()['id']}/revoke").status_code == 403
        one.headers["X-CSRF-Token"] = tokens[0]
        assert one.post(f"/portal/consents/{grant.json()['id']}/revoke").status_code == 200
        submitted = one.post("/portal/grievances", json={"note": "Named review"}).json()
        assert admin.post("/auth/admin/login", json={"email": email}).status_code == 202
        verified = admin.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert verified.status_code == 200
        path = f"/admin/requests/{submitted['id']}/resolve"
        admin.headers.update(ADMIN_HEADERS)
        assert admin.post(path, json={"status": "resolved", "resolution": "Reviewed"}).status_code == 403
        admin.headers.pop("X-API-Key")
        admin.headers["X-CSRF-Token"] = verified.json()["csrf_token"]
        resolved = admin.post(path, json={"status": "resolved", "resolution": "Named human decision"})
        assert resolved.status_code == 200 and resolved.json()["resolved_by"] == "admin_user"
        assert "admin_user_id" not in resolved.text and email not in resolved.text
        assert one.get("/portal/requests").json() == [resolved.json()]
        one.headers.pop("X-Candidate-Key")
        assert one.delete("/portal/me").json()["deleted"]
        assert one.get("/portal/me").status_code == 401
        assert admin.get("/portal/me", headers={"X-Candidate-Key": keys[0]}).status_code == 401
        assert two.get("/portal/me").json()["candidate_id"] == subjects[1]


# Verification, documents and employer assurance extraction


def verification_app(services):
    from app.api.auth import auth_router
    from app.api.verification import candidate_router, org_router, router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(candidate_router)
    app.include_router(org_router)
    app.include_router(router)
    return app


def test_verification_otp_preserves_ownership_delivery_and_single_use(cfg, capture_path):
    from tests.test_verification_claim_api import _candidate

    services = make_services(cfg)
    cid, key = _candidate(services, email="verify-one@example.in")
    other_id, other_key = _candidate(services, email="verify-two@example.in")
    with TestClient(verification_app(services), raise_server_exceptions=False) as one, \
            TestClient(verification_app(services), raise_server_exceptions=False) as two:
        one.headers["X-Candidate-Key"] = key
        two.headers["X-Candidate-Key"] = other_key
        assert one.get("/portal/verifications", headers={"X-Candidate-Key": "bad"}).status_code == 401
        for method, status in (("manual_review", 403), ("experience_letter", 403),
                               ("payslip", 403), ("government_id", 422), ("epfo_employment", 422)):
            assert one.post("/portal/verifications", json={"method": method}).status_code == status
        assert one.post("/portal/verifications", json={"method": "otp_phone", "destination": "+919876543210"}).status_code == 400
        assert one.post("/portal/verifications", json={"method": "otp_email", "destination": "wrong@example.in"}).status_code == 400
        body = {"method": "otp_email", "destination": "verify-one@example.in", "candidate_id": other_id}
        started = one.post("/portal/verifications", json=body)
        assert started.status_code == 200 and started.json().get("debug_code") is None
        row = started.json()["verification"]
        assert row["candidate_id"] == cid and row["status"] == "pending"
        code = _code(capture_path)
        assert one.post("/portal/verifications", json=body).status_code == 429
        path = f"/portal/verifications/{row['id']}/confirm"
        foreign = two.post(path, json={"code": code})
        absent = two.post("/portal/verifications/missing/confirm", json={"code": code})
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json() == {"detail": "verification not found"}
        wrong = "000000" if code != "000000" else "111111"
        assert one.post(path, json={"code": wrong}).status_code == 400
        confirmed = one.post(path, json={"code": code})
        assert confirmed.status_code == 200 and confirmed.json()["status"] == "verified"
        assert one.post(path, json={"code": code}).status_code == 400
        listed = one.get("/portal/verifications").json()
        assert [row for row in listed["verifications"] if row["status"] == "verified"] == [confirmed.json()]
        assert listed["assurance"]["level"] == 2 and listed["assurance"]["advisory"]
        assert listed["claims"]["strength"] == 0
        assert two.get("/portal/verifications").json()["verifications"] == []


def test_verification_documents_manual_review_consent_audit_and_erasure(services):
    from app.ledger.schema import ConsentPurpose
    from tests.test_verification_claim_api import _b64, _candidate

    cid, key = _candidate(services, email="document-one@example.in")
    other_id, other_key = _candidate(services, email="document-two@example.in")
    orgs = [services.ledger.create_organization(name) for name in ("Verification employer", "Other employer")]
    org_keys = [services.ledger.issue_api_key(org.id) for org in orgs]
    with TestClient(verification_app(services), raise_server_exceptions=False) as client:
        own = {"X-Candidate-Key": key}
        org = {"X-Org-Key": org_keys[0]}
        document = {"doc_type": "experience_letter", "content_b64": _b64(), "claim_ref": other_id}
        review = f"/candidates/{cid}/verifications/manual-review"
        assert client.post("/portal/documents", json=document, headers=org).status_code == 401
        for change, status in (({"content_b64": "!!!"}, 400), ({"doc_type": "unknown"}, 422),
                               ({"claim_ref": "x" * 129}, 422)):
            assert client.post("/portal/documents", json={**document, **change}, headers=own).status_code == status
        assert client.get("/portal/verifications", headers=own).json()["verifications"] == []
        submitted = client.post("/portal/documents", json=document, headers=own)
        assert submitted.status_code == 200
        body = submitted.json()
        assert body["verification"]["candidate_id"] == cid
        assert body["verification"]["subject"] == "employment_claim" and body["claims"]["strength"] == 2
        assert "ACME TECHNOLOGIES" not in submitted.text and "hr@acme.com" not in submitted.text
        assert client.get("/portal/verifications", headers=own).json()["assurance"]["level"] == 0
        assert client.get("/portal/verifications", headers={"X-Candidate-Key": other_key}).json()["verifications"] == []
        for headers in ({}, own, org):
            assert client.post(review, json={"outcome": "verified"}, headers=headers).status_code == 401
        assert client.post(review, json={"outcome": "unknown"}, headers=ADMIN_HEADERS).status_code == 422
        assert client.post("/candidates/missing/verifications/manual-review", json={"outcome": "verified"}, headers=ADMIN_HEADERS).status_code == 404
        reviewed = client.post(review, json={"outcome": "verified", "note": "Private human review", "evidence_digest": "a" * 64}, headers=ADMIN_HEADERS)
        assert reviewed.status_code == 200 and reviewed.json()["assurance_level"] == 3
        assert client.get("/portal/verifications", headers=own).json()["claims"]["strength"] == 2
        for suffix, field, value in (("assurance", "level", 3), ("claims", "strength", 2)):
            path = f"/verification/candidates/{cid}/{suffix}"
            assert client.get(path, headers=own).status_code == 401
            assert client.get(path, headers=org).status_code == 403
            grant = services.ledger.grant_consent(candidate_id=cid, org_id=orgs[0].id, purpose=ConsentPurpose.VERIFICATION_READ)
            allowed = client.get(path, headers=org)
            assert allowed.status_code == 200 and allowed.json()[field] == value and allowed.json()["advisory"]
            for secret in ("evidence_digest", "destination_hash", "claim_ref", "Private human review", "a" * 64, other_id):
                assert secret not in allowed.text
            assert client.get(path, headers={"X-Org-Key": org_keys[1]}).status_code == 403
            services.ledger.revoke_consent(grant.id)
            assert client.get(path, headers=org).status_code == 403
            assert client.get(f"/verification/candidates/missing/{suffix}", headers=org).status_code == 404
        audit = services.portal.access_log(cid)
        for action in ("verification.query", "claim.query"):
            assert {row.allowed for row in audit if row.action == action} == {True, False}
        services.portal.erase(cid)
        assert client.get("/portal/verifications", headers=own).status_code == 401
        for suffix in ("assurance", "claims"):
            assert client.get(f"/verification/candidates/{cid}/{suffix}", headers=org).status_code == 404
        assert client.get("/portal/verifications", headers={"X-Candidate-Key": other_key}).status_code == 200


def test_verification_cookie_precedence_csrf_and_manual_review(cfg, capture_path):
    from tests.test_verification_claim_api import _b64, _candidate

    services = make_services(cfg)
    cid, _ = _candidate(services, email="verify-cookie@example.in")
    other_id, other_key = _candidate(services, email="verify-foreign@example.in")
    email = "verify-operator@example.in"
    services.auth.create_admin_user(email_hash=services.auth.hash_email(email))
    with TestClient(verification_app(services), raise_server_exceptions=False) as candidate, \
            TestClient(verification_app(services), raise_server_exceptions=False) as admin:
        assert candidate.post("/auth/candidate/login", json={"email": "verify-cookie@example.in"}).status_code == 202
        logged = candidate.post("/auth/candidate/verify", json={"email": "verify-cookie@example.in", "code": _code(capture_path)})
        assert logged.status_code == 200
        candidate.headers["X-Candidate-Key"] = other_key
        assert candidate.get("/portal/verifications").json()["assurance"]["candidate_id"] == cid
        writes = (("/portal/verifications", {"method": "self_attested"}),
                  ("/portal/documents", {"doc_type": "experience_letter", "content_b64": _b64(), "claim_ref": other_id}))
        for path, body in writes:
            assert candidate.post(path, json=body).status_code == 403
            result = candidate.post(path, json=body, headers={"X-CSRF-Token": logged.json()["csrf_token"]})
            assert result.status_code == 200 and result.json()["verification"]["candidate_id"] == cid
        candidate.headers["X-CSRF-Token"] = logged.json()["csrf_token"]
        started = candidate.post("/portal/verifications", json={"method": "otp_email", "destination": "verify-cookie@example.in"})
        assert started.status_code == 200
        path = f"/portal/verifications/{started.json()['verification']['id']}/confirm"
        code = _code(capture_path)
        candidate.headers.pop("X-CSRF-Token")
        assert candidate.post(path, json={"code": code}).status_code == 403
        assert candidate.post(path, json={"code": code}, headers={"X-CSRF-Token": logged.json()["csrf_token"]}).json()["status"] == "verified"
        assert admin.post("/auth/admin/login", json={"email": email}).status_code == 202
        logged = admin.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert logged.status_code == 200
        admin.headers.update(ADMIN_HEADERS)
        path = f"/candidates/{cid}/verifications/manual-review"
        assert admin.post(path, json={"outcome": "verified"}).status_code == 403
        admin.headers.pop("X-API-Key")
        assert admin.post(path, json={"outcome": "verified"}, headers={"X-CSRF-Token": logged.json()["csrf_token"]}).json()["assurance_level"] == 3


# Candidate interviews and employer assessment summaries extraction


def interview_app(services):
    from app.api.auth import auth_router
    from app.api.interviews import candidate_router, org_router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(candidate_router)
    app.include_router(org_router)
    return app


def test_interview_workflow_preserves_ownership_budget_scores_privacy_and_consent(settings):
    from app.ledger.schema import ConsentPurpose
    from tests.conftest import FakeSpeech
    from tests.test_interview_api import ANSWER, AUDIO_B64, _candidate

    # Three malformed audio submissions consume budget before parsing, then one
    # valid transcription is allowed. Typed answers never consume that budget.
    tuned = settings.model_copy(update={"rate_limit_asr_per_hour_per_candidate": 4})
    speech = FakeSpeech(text=ANSWER, settings=tuned)
    services = make_services(tuned, speech=speech)
    cid, key = _candidate(services, "Interview One")
    other_id, other_key = _candidate(services, "Interview Two")
    orgs = [services.ledger.create_organization(name) for name in ("Interview employer", "Other employer")]
    org_keys = [services.ledger.issue_api_key(org.id) for org in orgs]
    with TestClient(interview_app(services), raise_server_exceptions=False) as actor, \
            TestClient(interview_app(services), raise_server_exceptions=False) as other:
        assert actor.get("/portal/interviews").status_code == 401
        actor.headers["X-Candidate-Key"] = key
        other.headers["X-Candidate-Key"] = other_key
        assert actor.post("/portal/interviews", json={"domain": "missing"}).status_code == 422
        started = actor.post("/portal/interviews", json={"candidate_id": other_id})
        assert started.status_code == 200 and started.json()["session"]["candidate_id"] == cid
        body = started.json()
        sid, qid = body["session"]["id"], body["next_question"]["id"]
        base = f"/portal/interviews/{sid}"
        assert actor.post("/portal/interviews", json={}).status_code == 409
        for method, suffix, payload in (("GET", "", None), ("POST", "/answers", {"question_id": qid, "text": ANSWER}),
                                        ("POST", "/finish", {})):
            foreign = other.request(method, base + suffix, json=payload)
            absent = other.request(method, "/portal/interviews/missing" + suffix, json=payload)
            assert foreign.status_code == absent.status_code == 404
            assert foreign.json() == absent.json() == {"detail": "interview not found"}
        for payload, status in (({"question_id": "wrong", "text": ANSWER}, 409),
                                ({"question_id": qid}, 400),
                                ({"question_id": qid, "audio_b64": "%%%", "mime": "audio/wav"}, 400),
                                ({"question_id": qid, "audio_b64": AUDIO_B64, "mime": "application/pdf"}, 422),
                                ({"question_id": qid, "text": ANSWER, "audio_b64": AUDIO_B64}, 400)):
            assert actor.post(base + "/answers", json=payload).status_code == status
        assert speech.calls == [] and actor.get(base).json() == body
        typed = actor.post(base + "/answers", json={"question_id": qid, "text": ANSWER})
        assert typed.status_code == 200 and typed.json()["session"]["turns"][0]["channel"] == "text"
        assert speech.calls == []
        qid = typed.json()["next_question"]["id"]
        audio = actor.post(base + "/answers", json={"question_id": qid, "audio_b64": AUDIO_B64, "mime": "audio/webm;codecs=opus"})
        assert audio.status_code == 200 and len(speech.calls) == 1
        saved = audio.json()
        assert [row["channel"] for row in saved["session"]["turns"]] == ["text", "audio"]
        assert saved["session"]["turns"][-1]["transcript"] == ANSWER
        assert AUDIO_B64 not in audio.text and saved["session"]["turns"][-1]["audio_digest"]
        assert actor.post(base + "/answers", json={"question_id": qid, "audio_b64": AUDIO_B64}).status_code == 409
        qid = saved["next_question"]["id"]
        refused = actor.post(base + "/answers", json={"question_id": qid, "audio_b64": AUDIO_B64})
        assert refused.status_code == 429 and refused.json() == {"detail": "rate_limited"}
        assert int(refused.headers["Retry-After"]) > 0 and len(speech.calls) == 1
        assert actor.get(base).json() == saved
        fallback = actor.post(base + "/answers", json={"question_id": qid, "text": ANSWER})
        assert fallback.status_code == 200 and len(speech.calls) == 1
        done = actor.post(base + "/finish", json={})
        assert done.status_code == 200 and done.json()["next_question"] is None
        assessment = done.json()["session"]["assessment"]
        assert assessment["scorer_version"] == "s73.2" and assessment["advisory"] and assessment["human_review_required"]
        assert actor.post(base + "/finish", json={}).status_code == 409
        assert actor.get(base).json() == done.json()
        listed = actor.get("/portal/interviews")
        assert [row["id"] for row in listed.json()["interviews"]] == [sid]
        assert ANSWER not in listed.text and "transcript" not in listed.text and "audio_digest" not in listed.text
        assert other.get("/portal/interviews").json() == {"interviews": []}
        path = f"/interview/candidates/{cid}/assessments"
        assert actor.get(path).status_code == 401
        org = {"X-Org-Key": org_keys[0]}
        assert other.get(path, headers=org).status_code == 403
        services.ledger.grant_consent(candidate_id=cid, org_id=orgs[0].id, purpose=ConsentPurpose.VERIFICATION_READ)
        assert other.get(path, headers=org).status_code == 403
        grant = services.ledger.grant_consent(candidate_id=cid, org_id=orgs[0].id, purpose=ConsentPurpose.INTERVIEW_READ)
        allowed = other.get(path, headers=org)
        assert allowed.status_code == 200 and allowed.json()["attempts"] == 1
        summary = allowed.json()["assessments"][0]
        assert all(summary[field] == assessment[field] for field in ("band", "overall", "dimensions", "confidence", "scorer_version", "questions_planned", "questions_answered", "advisory"))
        assert all(secret not in allowed.text for secret in (ANSWER, AUDIO_B64, "transcript", '"turns"', "audio_digest"))
        assert other.get(path, headers={"X-Org-Key": org_keys[1]}).status_code == 403
        services.ledger.revoke_consent(grant.id)
        assert other.get(path, headers=org).status_code == 403
        audit = [row for row in services.portal.access_log(cid) if row.action == "interview.query"]
        assert {row.allowed for row in audit} == {True, False}
        services.portal.erase(cid)
        assert actor.get(base).status_code == 401
        assert other.get(path, headers=org).status_code == 404
        assert other.get("/portal/interviews").status_code == 200


@pytest.mark.parametrize("failure,detail", [
    ("unavailable", "speech_unavailable: answer this question in text"),
    ("failed", "speech_failed: no answer saved; record again or answer in text"),
])
def test_interview_asr_refusal_keeps_question_and_allows_typed_recovery(settings, failure, detail):
    from app.services.speech import SpeechFailed, SpeechUnavailable
    from tests.conftest import FakeSpeech
    from tests.test_interview_api import ANSWER, AUDIO_B64, _candidate

    error = SpeechUnavailable if failure == "unavailable" else SpeechFailed
    speech = FakeSpeech(fail=error("private-provider-error"), settings=settings)
    services = make_services(settings, speech=speech)
    _, key = _candidate(services)
    with TestClient(interview_app(services), headers={"X-Candidate-Key": key}) as actor:
        started = actor.post("/portal/interviews", json={}).json()
        path = f"/portal/interviews/{started['session']['id']}"
        qid = started["next_question"]["id"]
        refused = actor.post(path + "/answers", json={"question_id": qid, "audio_b64": AUDIO_B64})
        assert refused.status_code == 422 and refused.json() == {"detail": detail}
        assert actor.get(path).json() == started
        assert actor.post(path + "/answers", json={"question_id": qid, "text": ANSWER}).status_code == 200
        assert len(speech.calls) == 1


def test_interview_cookie_ownership_csrf_and_employer_key_precedence(cfg, capture_path):
    from app.ledger.schema import ConsentPurpose
    from tests.test_interview_api import ANSWER
    from tests.test_verification_claim_api import _candidate

    services = make_services(cfg)
    cid, _ = _candidate(services, email="interview-cookie@example.in")
    other_id, other_key = _candidate(services, email="interview-foreign@example.in")
    with TestClient(interview_app(services), raise_server_exceptions=False) as actor, \
            TestClient(interview_app(services), raise_server_exceptions=False) as employer:
        address = "interview-cookie@example.in"
        assert actor.post("/auth/candidate/login", json={"email": address}).status_code == 202
        verified = actor.post("/auth/candidate/verify", json={"email": address, "code": _code(capture_path)})
        assert verified.status_code == 200
        token = verified.json()["csrf_token"]
        actor.headers["X-Candidate-Key"] = other_key
        assert actor.post("/portal/interviews", json={}).status_code == 403
        started = actor.post("/portal/interviews", json={"candidate_id": other_id}, headers={"X-CSRF-Token": token})
        assert started.status_code == 200 and started.json()["session"]["candidate_id"] == cid
        path = f"/portal/interviews/{started.json()['session']['id']}"
        answer = {"question_id": started.json()["next_question"]["id"], "text": ANSWER}
        for suffix, payload in (("/answers", answer), ("/finish", {})):
            assert actor.post(path + suffix, json=payload).status_code == 403
        assert actor.post(path + "/answers", json=answer, headers={"X-CSRF-Token": token}).status_code == 200
        assert actor.post(path + "/finish", json={}, headers={"X-CSRF-Token": token}).status_code == 200
        login = {"email": "interview-employer@example.in", "organization_name": "Interview cookie employer"}
        assert employer.post("/auth/org/signup", json=login).status_code == 202
        assert employer.post("/auth/org/verify", json={"email": login["email"], "code": _code(capture_path)}).status_code == 200
        org_id = employer.get("/auth/me").json()["organization_id"]
        other_org = services.ledger.create_organization("Foreign interview employer")
        foreign_key = services.ledger.issue_api_key(other_org.id)
        employer.headers["X-Org-Key"] = foreign_key
        services.ledger.grant_consent(candidate_id=cid, org_id=org_id, purpose=ConsentPurpose.INTERVIEW_READ)
        response = employer.get(f"/interview/candidates/{cid}/assessments")
        assert response.status_code == 200 and response.json()["attempts"] == 1
        assert employer.post("/portal/interviews", json={}).status_code == 401
        employer.cookies.clear()
        assert employer.get(f"/interview/candidates/{cid}/assessments").status_code == 403


# Curation extraction


def curation_app(services):
    from app.api.auth import auth_router
    from app.api.curation import router

    app = FastAPI()
    app.state.services = services
    app.include_router(auth_router)
    app.include_router(router)
    return app


def test_curation_queue_preserves_pagination_status_bounds_and_surviving_sources(settings):
    from tests.curation_helpers import saved_source

    services = make_services(settings.model_copy(update={"cur_queue_default_limit": 2}))
    first, source = saved_source(services.session_factory)
    _, other = saved_source(services.session_factory)
    for name in ("Alpha raw", "Beta raw", "Gamma raw"):
        services.curation.record_unmapped(name, source_id=source)
    services.curation.record_unmapped("Alpha raw", source_id=other)
    with TestClient(curation_app(services), headers=ADMIN_HEADERS) as client:
        page = client.get("/curation/skills/unmapped", params={"limit": 999, "status": "pending"})
        assert page.status_code == 200
        body = page.json()
        assert len(body["terms"]) == 2 and body["next_cursor"]
        assert body["terms"][0]["norm_key"] == "alpha raw" and body["terms"][0]["occurrences"] == 2
        following = client.get("/curation/skills/unmapped", params={"cursor": body["next_cursor"]})
        assert following.status_code == 200 and following.json()["next_cursor"] is None
        terms = body["terms"] + following.json()["terms"]
        assert len({t["norm_key"] for t in terms}) == len(terms) == 3
        assert all(len(t["review_revision"]) == 64 for t in terms)
        assert all(secret not in page.text + following.text for secret in (first, source, other, "candidate_id", "source_id"))
        assert len(client.get("/curation/skills/unmapped?limit=0").json()["terms"]) == 1
        for status in ("resolved", "ignored"):
            assert client.get("/curation/skills/unmapped", params={"status": status}).json() == {"terms": [], "next_cursor": None}
        for query in ({"cursor": "!!!"}, {"status": "unknown"}, {"limit": "bad"}):
            assert client.get("/curation/skills/unmapped", params=query).status_code == 422
        services.portal.erase(first)
        survivor, = client.get("/curation/skills/unmapped").json()["terms"]
        assert survivor["norm_key"] == "alpha raw" and survivor["occurrences"] == 1
        assert survivor["review_revision"] != terms[0]["review_revision"]


def test_curation_decisions_preserve_validation_conflicts_receipts_and_overlay(services):
    from app.candidates.normalize.skills import normalize_skill
    from tests.curation_helpers import saved_source

    _, source = saved_source(services.session_factory)
    for name in ("Map raw", "Create raw", "Ignore raw"):
        services.curation.record_unmapped(name, source_id=source)
    with TestClient(curation_app(services), headers=ADMIN_HEADERS) as client:
        before = client.get("/curation/skills/unmapped").json()
        snapshots = {t["norm_key"]: t for t in before["terms"]}
        body = dict(norm_key="map raw", action="map", alias="Approved extracted",
                    canonical="python", category="language", expected_revision=snapshots["map raw"]["review_revision"])
        for change in ({"expected_revision": None}, {"expected_revision": "x" * 64},
                       {"canonical": "unknown"}, {"category": "data"}, {"alias": None},
                       {"admin_user_id": "supplied-identity"}, {"note": "private-note"}):
            assert client.post("/curation/skills/resolve", json=body | change).status_code == 422
            assert client.get("/curation/skills/unmapped").json() == before
        missing = {k: v for k, v in body.items() if k != "expected_revision"}
        assert client.post("/curation/skills/resolve", json=missing).status_code == 422
        mapped = client.post("/curation/skills/resolve", json=body)
        assert mapped.status_code == 200
        assert mapped.json() == dict(action="map", alias="Approved extracted", canonical="python",
            category="language", decided_at=mapped.json()["decided_at"], admin_user_id=None)
        assert "map raw" not in mapped.text and normalize_skill("Approved extracted").canonical == "python"
        assert normalize_skill("Map raw") is None
        conflict = client.post("/curation/skills/resolve", json=body | {"norm_key": "create raw",
            "expected_revision": snapshots["create raw"]["review_revision"]})
        assert conflict.status_code == 409 and conflict.json() == {"detail": "approved alias already exists"}
        assert snapshots["create raw"] in client.get("/curation/skills/unmapped").json()["terms"]
        created = client.post("/curation/skills/resolve", json=body | {"norm_key": "create raw", "action": "create",
            "alias": "Approved new extracted", "canonical": "extracted_skill", "category": "data",
            "expected_revision": snapshots["create raw"]["review_revision"]})
        assert created.status_code == 200 and normalize_skill("Approved new extracted").canonical == "extracted_skill"
        ignore = dict(norm_key="ignore raw", action="ignore", expected_revision=snapshots["ignore raw"]["review_revision"])
        assert client.post("/curation/skills/resolve", json=ignore).status_code == 200
        services.curation.record_unmapped("Ignore raw", source_id=source)
        fresh = client.get("/curation/skills/unmapped").json()
        stale = client.post("/curation/skills/resolve", json=ignore)
        assert stale.status_code == 409 and stale.json() == {"detail": "review snapshot changed; refresh before deciding"}
        assert client.get("/curation/skills/unmapped").json() == fresh
        ignored = client.post("/curation/skills/resolve", json=ignore | {"expected_revision": fresh["terms"][0]["review_revision"]})
        assert ignored.status_code == 200 and ignored.json()["alias"] is None
        absent = client.post("/curation/skills/resolve", json=ignore)
        assert absent.status_code == 404 and absent.json() == {"detail": "term not found"}
        assert client.get("/curation/skills/unmapped").json() == {"terms": [], "next_cursor": None}


def test_curation_operator_auth_cookie_csrf_identity_and_revocation(cfg, capture_path):
    from tests.curation_helpers import saved_source

    services = make_services(cfg)
    _, source = saved_source(services.session_factory)
    services.curation.record_unmapped("Operator raw", source_id=source)
    email = "extracted-reviewer@example.in"
    operator = services.auth.create_admin_user(email_hash=services.auth.hash_email(email))
    org = services.ledger.create_organization("Curation employer")
    org_key = services.ledger.issue_api_key(org.id)
    candidate_id, _ = saved_source(services.session_factory)
    candidate_key = services.candidates.issue_access_key(candidate_id)
    with TestClient(curation_app(services), raise_server_exceptions=False) as client:
        body = dict(norm_key="operator raw", action="map", alias="Approved operator",
                    canonical="python", category="language", expected_revision="0" * 64)
        for headers in ({}, {"X-Org-Key": org_key}, {"X-Candidate-Key": candidate_key}, {"X-API-Key": "invalid"}):
            assert client.get("/curation/skills/unmapped", headers=headers).status_code == 401
            assert client.post("/curation/skills/resolve", json=body, headers=headers).status_code == 401
        before = client.get("/curation/skills/unmapped", headers=ADMIN_HEADERS).json()
        body["expected_revision"] = before["terms"][0]["review_revision"]
        assert client.post("/auth/admin/login", json={"email": email}).status_code == 202
        login = client.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert login.status_code == 200
        # Even a valid machine key cannot bypass session CSRF or replace its actor.
        client.headers.update(ADMIN_HEADERS)
        assert client.get("/curation/skills/unmapped").json() == before
        for token in (None, "wrong"):
            headers = {} if token is None else {"X-CSRF-Token": token}
            assert client.post("/curation/skills/resolve", json=body, headers=headers).status_code == 403
            assert client.get("/curation/skills/unmapped").json() == before
        approved = client.post("/curation/skills/resolve", json=body, headers={"X-CSRF-Token": login.json()["csrf_token"]})
        assert approved.status_code == 200 and approved.json()["admin_user_id"] == operator.id
        client.headers.pop("X-API-Key")
        assert services.auth.delete_admin_user(operator.id)
        assert client.get("/curation/skills/unmapped").status_code == 401
        assert client.post("/curation/skills/resolve", json=body).status_code == 401


# Operator operations extraction


def operator_app(services):
    from app.api.auth import auth_router
    from app.api.operator import metrics_router, retention_router, router

    app = FastAPI()
    app.state.services = services
    for segment in (auth_router, metrics_router, retention_router, router):
        app.include_router(segment)
    return app


def test_operator_accounts_preserve_planes_cookie_csrf_and_target_session_revocation(cfg, capture_path):
    from tests.curation_helpers import saved_source

    services = make_services(cfg)
    org = services.ledger.create_organization("Operator isolation")
    org_key = services.ledger.issue_api_key(org.id)
    cid, _ = saved_source(services.session_factory)
    candidate_key = services.candidates.issue_access_key(cid)
    reads = ("/admin/users", "/metrics", "/admin/signal-quality")
    with TestClient(operator_app(services), raise_server_exceptions=False) as root, \
            TestClient(operator_app(services)) as actor, TestClient(operator_app(services)) as other:
        for headers in ({}, {"X-API-Key": "invalid"}, {"X-Org-Key": org_key}, {"X-Candidate-Key": candidate_key}):
            assert all(root.get(path, headers=headers).status_code == 401 for path in reads)
            assert root.post("/admin/users", json={"email": "denied@example.in"}, headers=headers).status_code == 401
            assert root.delete("/admin/users/missing", headers=headers).status_code == 401
            assert root.post("/admin/retention/sweep", json={}, headers=headers).status_code == 401
        root.headers.update(ADMIN_HEADERS)
        email = "operator-extracted@example.in"
        created = root.post("/admin/users", json={"email": email, "label": "Extracted operator"})
        assert created.status_code == 200 and email not in created.text
        account = created.json()
        assert account["email_hash"] == services.auth.hash_email(email) and account["label"] == "Extracted operator"
        duplicate = root.post("/admin/users", json={"email": email.upper()})
        assert duplicate.status_code == 409 and duplicate.json() == {"detail": "operator already exists"}
        assert root.post("/admin/users", json={}).status_code == 422
        missing = root.delete("/admin/users/missing")
        assert missing.status_code == 404 and missing.json() == {"detail": "operator not found"}

        def sign_in(client, address):
            assert client.post("/auth/admin/login", json={"email": address}).status_code == 202
            login = client.post("/auth/admin/verify", json={"email": address, "code": _code(capture_path)})
            assert login.status_code == 200
            return login.json()["csrf_token"]

        csrf = sign_in(actor, email)
        sign_in(other, email)
        assert actor.get("/auth/me").json()["session_id"] != other.get("/auth/me").json()["session_id"]
        # A cookie retains precedence even alongside a valid machine credential.
        actor.headers.update(ADMIN_HEADERS)
        assert all(actor.get(path).status_code == 200 for path in reads)
        before = root.get("/admin/users").json()
        for token in (None, "wrong"):
            headers = {} if token is None else {"X-CSRF-Token": token}
            assert actor.post("/admin/users", json={"email": "survivor@example.in"}, headers=headers).status_code == 403
            assert actor.delete(f"/admin/users/{account['id']}", headers=headers).status_code == 403
            assert actor.post("/admin/retention/sweep", json={}, headers=headers).status_code == 403
            assert root.get("/admin/users").json() == before
        actor.headers["X-CSRF-Token"] = csrf
        survivor = actor.post("/admin/users", json={"email": "survivor@example.in"}).json()
        assert actor.post("/admin/retention/sweep", json={}).json()["dry_run"] is True
        with TestClient(operator_app(services)) as retained:
            sign_in(retained, "survivor@example.in")
            deleted = actor.delete(f"/admin/users/{account['id']}")
            assert deleted.status_code == 200 and deleted.json() == {"admin_user_id": account["id"], "deleted": True}
            actor.headers.pop("X-API-Key")
            for client in (actor, other):
                assert client.get("/auth/me").status_code == 401
                assert all(client.get(path).status_code == 401 for path in reads)
                assert client.post("/admin/retention/sweep", json={}).status_code == 401
            assert retained.get("/admin/users").json() == [survivor]
        assert root.get("/admin/users").json() == [survivor]


def test_operator_retention_preserves_safe_preview_refusal_cap_and_metrics(services):
    from sqlalchemy import select
    from app.candidates.models import CandidateRow, ResumeRow
    from tests.test_retention_api import ALL_CLASSES

    now = datetime.now(timezone.utc)
    with services.session_factory() as session:
        candidate = CandidateRow(full_name="Retention fixture")
        session.add(candidate)
        session.flush()
        rows = [ResumeRow(candidate_id=candidate.id, version=i + 1,
            raw_text="private retention fixture", text_sha256=str(i) * 64,
            created_at=now - timedelta(days=age)) for i, age in enumerate((2000, 2000, 1))]
        session.add_all(rows)
        session.flush()
        expired, recent = {r.id for r in rows[:2]}, rows[2].id
        session.commit()

    def remaining():
        with services.session_factory() as session:
            return set(session.scalars(select(ResumeRow.id)))

    services.settings.retention_sweep_enabled = False
    services.settings.sweep_max_rows_per_class = 1
    with TestClient(operator_app(services), headers=ADMIN_HEADERS) as client:
        preview = client.post("/admin/retention/sweep", json={})
        assert preview.status_code == 200 and preview.json()["dry_run"] is True
        body = preview.json()
        assert {r["data_class"] for r in body["by_class"]} == ALL_CLASSES and body["truncated"] is True
        resume = next(r for r in body["by_class"] if r["data_class"] == "resumes")
        assert resume["affected"] == 1 and resume["truncated"] is True
        assert remaining() == expired | {recent}
        refused = client.post("/admin/retention/sweep", json={"dry_run": False})
        assert refused.status_code == 409 and refused.json() == {"detail": "retention_sweep_disabled"}
        assert client.post("/admin/retention/sweep", json={"dry_run": "invalid"}).status_code == 422
        assert remaining() == expired | {recent}
        services.settings.retention_sweep_enabled = True
        applied = client.post("/admin/retention/sweep", json={"dry_run": False})
        assert applied.status_code == 200 and applied.json()["dry_run"] is False
        applied_resume = next(r for r in applied.json()["by_class"] if r["data_class"] == "resumes")
        assert applied_resume == resume
        assert len(remaining() & expired) == 1 and recent in remaining()
        assert client.post("/admin/retention/sweep", json={"dry_run": False}).status_code == 200
        assert remaining() == {recent}
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert metrics.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
        assert 'veritas_retention_deleted_total{data_class="resumes"} 2' in metrics.text
        assert all(value not in metrics.text for value in (*expired, recent, "private retention fixture"))


def test_operator_signal_quality_preserves_label_opt_in_floor_refusals_and_privacy(services):
    from tests.test_signal_quality_labels import _saved, _judge

    services.settings.min_signal_quality_samples = 3
    store = services.report_store
    genuine, fabricated, inconclusive = [_saved(store) for _ in range(3)]
    _judge(store, genuine, OutcomeLabel.VERIFIED_GENUINE)
    _judge(store, fabricated, OutcomeLabel.VERIFIED_FABRICATED, source=OutcomeSource.OPERATOR)
    _judge(store, inconclusive, OutcomeLabel.INCONCLUSIVE)
    with TestClient(operator_app(services), headers=ADMIN_HEADERS) as client:
        response = client.get("/admin/signal-quality")
        assert response.status_code == 200
        default = response.json()
        assert default["population"]["label_source"] == "outcomes"
        assert default["population"]["label_kind"] == "fraud"
        assert default["population"]["include_operator_labels"] is False
        assert default["population"]["labels_usable"] == 1
        opted = client.get("/admin/signal-quality?include_operator_labels=true").json()
        assert opted["population"]["include_operator_labels"] is True and opted["population"]["labels_usable"] == 2
        for body in (default, opted):
            assert len(body["signals"]) == 12 and all(not s["sufficient"] for s in body["signals"])
            fraud = next(s for s in body["signals"] if s["signal"] == "fabrication_risk.score")
            assert fraud["reason"] == "insufficient_samples" and fraud["detail"].endswith("need 3")
            assert set(fraud) == {"signal", "sufficient", "reason", "n", "detail"}
        ledger = client.get("/admin/signal-quality?source=ledger").json()
        assert ledger["population"]["label_source"] == "ledger" and ledger["population"]["label_kind"] == "hire"
        fraud = next(s for s in ledger["signals"] if s["signal"] == "fabrication_risk.score")
        assert fraud["reason"] == "label_kind_mismatch" and "auc" not in fraud
        assert client.get("/admin/signal-quality?source=unknown").status_code == 422
        assert client.get("/admin/signal-quality?include_operator_labels=invalid").status_code == 422
        assert all(report.id not in response.text for report in (genuine, fabricated, inconclusive))


# Public surface and final composition


def public_surface_app(services):
    from app.api.auth import auth_router
    from app.api.public import domain_router, public_router, service_router

    app = FastAPI()
    app.state.services = services
    for segment in (domain_router, public_router, auth_router, service_router):
        app.include_router(segment)
    return app


@pytest.mark.parametrize("mode", ["null", "live"])
def test_public_surface_preserves_lightweight_health_contact_and_effective_mode(services, mode, monkeypatch):
    from types import SimpleNamespace
    from app import __version__
    from app.services.llm import NullLLM
    from tests.conftest import FakeLLM

    services.settings.grievance_officer_name = "Synthetic Officer"
    services.settings.grievance_officer_email = "public-officer@example.in"
    services.settings.grievance_officer_phone = "+91 80 4000 0000"
    services.settings.grievance_response_days = 21
    llm = NullLLM(services.settings) if mode == "null" else FakeLLM(settings=services.settings)
    async def refuse_provider_call(**kwargs):
        raise AssertionError("public reads must not invoke a model")
    monkeypatch.setattr(llm, "_araw", refuse_provider_call)
    app = public_surface_app(services)
    # No auth or stores are available; the composed app also records HTTP metrics.
    app.state.services = SimpleNamespace(settings=services.settings, llm=llm, metrics=services.metrics)
    client = TestClient(app)
    for headers in ({}, {"X-API-Key": "invalid", "X-Org-Key": "invalid", "X-Candidate-Key": "invalid"}):
        health = client.get("/healthz", headers=headers)
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "version": __version__,
            "env": services.settings.env, "llm_mode": mode, "domains": ["data_eng", "genai"]}
        contact = client.get("/grievance", headers=headers)
        assert contact.status_code == 200
        assert contact.json() == {"name": "Synthetic Officer", "email": "public-officer@example.in",
            "phone": "+91 80 4000 0000", "response_days": 21}
        service = client.get("/", headers=headers)
        assert service.status_code == 200
        assert set(service.json()) == {"service", "advisory", "human_review_required", "endpoints"}
        assert service.json()["service"] == "depth-eval-engine"
        assert service.json()["advisory"] is service.json()["human_review_required"] is True


def test_public_domains_preserve_admin_key_session_and_other_plane_refusals(cfg, capture_path):
    from tests.curation_helpers import saved_source

    services = make_services(cfg)
    org = services.ledger.create_organization("Public metadata denial")
    org_key = services.ledger.issue_api_key(org.id)
    cid, _ = saved_source(services.session_factory)
    candidate_key = services.candidates.issue_access_key(cid)
    email = "domain-operator@example.in"
    services.auth.create_admin_user(email_hash=services.auth.hash_email(email))
    with TestClient(public_surface_app(services)) as client:
        for headers in ({}, {"X-API-Key": "invalid"}, {"X-Org-Key": org_key}, {"X-Candidate-Key": candidate_key}):
            refused = client.get("/domains", headers=headers)
            assert refused.status_code == 401
            assert refused.json() == {"detail": "invalid or missing admin credential"}
        expected = client.get("/domains", headers=ADMIN_HEADERS)
        assert expected.status_code == 200
        assert [row["key"] for row in expected.json()] == ["data_eng", "genai"]
        assert all(set(row) == {"key", "display_name", "claim_types"}
            and row["display_name"] and row["claim_types"] for row in expected.json())
        assert client.post("/auth/admin/login", json={"email": email}).status_code == 202
        verified = client.post("/auth/admin/verify", json={"email": email, "code": _code(capture_path)})
        assert verified.status_code == 200
        # Safe reads require no CSRF; invalid machine credentials cannot mask a session.
        assert client.get("/domains", headers={"X-API-Key": "invalid"}).json() == expected.json()
        client.headers["X-CSRF-Token"] = verified.json()["csrf_token"]
        assert client.post("/auth/logout").status_code == 200
        assert client.get("/domains").status_code == 401


def test_public_service_discovery_follows_requesting_app_and_later_routes(services):
    first, second = public_surface_app(services), public_surface_app(services)

    @first.get("/later-surface")
    async def later_surface():
        return {"available": True}

    with TestClient(first) as client, TestClient(second) as other:
        listed = client.get("/").json()["endpoints"]
        assert "GET /later-surface" in listed
        assert "GET /later-surface" not in other.get("/").json()["endpoints"]
        assert client.get("/later-surface").json() == {"available": True}
        assert all(entry in listed for entry in ("GET /healthz", "GET /grievance", "GET /domains"))
        assert listed == sorted(set(listed), key=lambda e: (e.split(" ", 1)[1], e))
        assert not any(entry.startswith(("HEAD ", "OPTIONS ")) or entry.split(" ", 1)[1]
            in {"/", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"} or "/ui" in entry for entry in listed)
