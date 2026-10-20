"""Api route extraction regressions, grouped by behavior."""

import asyncio
from datetime import datetime, timedelta, timezone
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
from tests.test_ledger_api import _coding_payload, _ingest_candidate
from tests.test_dashboard_api import _candidate as dashboard_candidate, _materialize, AS_OF


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
