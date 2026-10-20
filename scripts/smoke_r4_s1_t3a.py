"""Auth/ledger/employer extraction: migrated HTTP, ownership and restart.

Uses captured mail and the existing fake-provider SQL app/graceful server loop.
No external mail/provider calls, working storage or existing demo restart.
"""

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from _smoke import Smoke, base_env, client, wait_healthy
from smoke_s82 import _code_for as latest_code
from smoke_r4_s1_t1a import serve


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-router-admin"


def main():
    checks = Smoke("R4-S1-T3A auth/session extraction HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t3a-"))
    print(f"Synthetic auth evidence: {scratch}", flush=True)
    stop, events, mailbox = scratch / "stop", scratch / "lifecycle.jsonl", scratch / "mail.jsonl"
    env = {key: value for key, value in base_env().items() if not key.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + (scratch / "app.db").as_posix(),
        "DEE_DB_MIGRATE_ON_BOOT": "true", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_SPEECH_PROVIDER": "local",
        "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_COOLDOWN_SECONDS": "0",
        "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "VERITAS_SQL_SMOKE_EVENTS": str(events),
        "VERITAS_SQL_SMOKE_FACTORY": "smoke_r4_s1_t1a:create_smoke_app",
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        stop.unlink(missing_ok=True)
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port), str(stop)],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base) as health:
                    assert wait_healthy(health), "scratch auth app failed to start"
                yield
            finally:
                stop.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("scratch auth app failed graceful shutdown")
                assert proc.returncode == 0, "scratch auth app failed during lifespan"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def login(http, plane, email, *, organization=None):
        body = {"email": email}
        if organization:
            body["organization_name"] = organization
        path = f"/auth/{plane}/" + ("signup" if organization or plane == "candidate" else "login")
        assert require(http.post(path, json=body), 202) == {"status": "accepted"}
        response = http.post(f"/auth/{plane}/verify", json={"email": email, "code": latest_code(mailbox, email)})
        session = require(response)
        cookies = response.headers.get_list("set-cookie")
        checks.check(f"{plane} verify preserves cookie posture", len(cookies) == 2
            and sum("HttpOnly" in value for value in cookies) == 1
            and all("SameSite=lax" in value and "Path=/" in value for value in cookies))
        assert session["principal"] == ("org" if plane == "org" else plane)
        return session["csrf_token"]

    with client(base, headers={"X-API-Key": ADMIN}) as control, client(base) as operator, \
            client(base) as org, client(base) as other_org, client(base) as candidate, client(base) as sibling:
        with server():
            require(control.post("/admin/users", json={"email": "router-admin@example.in", "label": "Synthetic router admin"}))
            admin_csrf = login(operator, "admin", "router-admin@example.in")
            org_csrf = login(org, "org", "router-org@example.in", organization="Synthetic Router A")
            other_csrf = login(other_org, "org", "router-other@example.in", organization="Synthetic Router B")
            candidate_csrf = login(candidate, "candidate", "router-candidate@example.in")
            sibling_csrf = login(sibling, "candidate", "router-candidate@example.in")
            who = [require(http.get("/auth/me")) for http in (operator, org, other_org, candidate)]
            checks.check("three planes resolve their own sessions", [row["kind"] for row in who] == ["admin", "org", "org", "candidate"])
            checks.check("anonymous and header-only callers cannot use session lifecycle", control.get("/auth/me").status_code == 401)
            for http, path, body in (
                (operator, "/ledger/orgs", {"name": "Denied without CSRF"}),
                (org, "/jobs", {"title": "Denied without CSRF", "must_have_skills": ["python"]}),
                (candidate, "/portal/consents", {"purpose": "ledger_read"}),
            ):
                checks.check(path + " retains session CSRF refusal", http.post(path, json=body).status_code == 403)
            other_id = who[2]["organization_id"]
            other_key = require(control.post(f"/ledger/orgs/{other_id}/api-key"))["api_key"]
            org.headers["X-Org-Key"] = other_key
            checks.check("cookie plus another employer key cannot bypass CSRF", org.post("/jobs", json={"title": "Denied", "must_have_skills": ["python"]}).status_code == 403)
            org.headers["X-CSRF-Token"] = org_csrf
            job = require(org.post("/jobs", json={"title": "Synthetic Router Engineer", "must_have_skills": ["python"]}))
            checks.check("session retains tenant precedence over header key", other_org.get(f"/jobs/{job['id']}").status_code == 404)
            candidate.headers["X-CSRF-Token"] = candidate_csrf
            checks.check("candidate cannot revoke an employer session", candidate.post(f"/auth/sessions/{who[1]['session_id']}/revoke").status_code == 404)
            sessions = require(candidate.get("/auth/sessions"))
            checks.check("same subject sees both own devices only", len(sessions) == 2 and all(row["id"] != who[1]["session_id"] for row in sessions))
            require(candidate.post(f"/auth/sessions/{who[3]['session_id']}/revoke"))
            checks.check("self revocation leaves sibling session usable", candidate.get("/auth/me").status_code == 401 and sibling.get("/portal/me").status_code == 200)
            unknown = require(control.post("/auth/org/login", json={"email": "router-unknown@example.in"}), 202)
            checks.check("unknown organization login remains uniform", unknown == {"status": "accepted"})
            invalid = control.post("/auth/admin/verify", json={"email": "missing@example.in", "code": "000000"})
            checks.check("invalid verification sets no cookies", invalid.status_code == 400 and "set-cookie" not in invalid.headers)

            # T3E reuses this migrated, captured-login, graceful-restart journey.
            operator.headers["X-CSRF-Token"] = admin_csrf
            other_org.headers["X-CSRF-Token"] = other_csrf
            subject = require(sibling.get("/portal/me"))["candidate_id"]
            ledger_path = f"/ledger/candidates/{subject}"
            org_id = who[1]["organization_id"]
            grants = {purpose: require(operator.post(ledger_path + "/consent", json={
                "purpose": purpose, "org_id": org_id})) for purpose in ("ledger_read", "ledger_write")}
            checks.check("admin cookie grants exact-purpose employer consent", all(
                require(operator.get(ledger_path + "/consent", params={"org_id": org_id, "purpose": purpose}))["grant_id"] == grant["id"]
                for purpose, grant in grants.items()))
            record_body = {"candidate_id": subject, "stage": "hm", "outcome": "hired",
                "interviewed_at": "2026-10-01T10:00:00Z", "summary": "Synthetic human assessment"}
            coding_body = {"candidate_id": subject, "platform": "hackerrank", "score": 80,
                "max_score": 100, "percentile": 88, "taken_at": "2026-10-01T10:00:00Z"}
            checks.check("ledger wrong-plane writes and unconsented employer refuse",
                operator.post("/ledger/records", json=record_body).status_code == 401
                and candidate.post("/ledger/records", json=record_body).status_code == 401
                and other_org.post("/ledger/records", json=record_body).status_code == 403
                and other_org.post("/ledger/coding-rounds", json=coding_body).status_code == 403)
            record = require(org.post("/ledger/records", json=record_body))
            coding = require(org.post("/ledger/coding-rounds", json=coding_body))
            event_path = f"/ledger/records/{record['id']}/events"
            event = require(org.post(event_path, json={"event_type": "human_reviewed", "payload": {"confirmed": True}}))
            checks.check("ledger writes use cookie tenant and original consent despite other key",
                record["org_id"] == coding["org_id"] == org_id
                and record["consent_id"] == coding["consent_id"] == grants["ledger_write"]["id"]
                and event["record_id"] == record["id"])
            checks.check("ledger event ownership hides other-tenant and missing records",
                other_org.post(event_path, json={"event_type": "refused"}).status_code == 404
                and other_org.post("/ledger/records/missing/events", json={"event_type": "refused"}).json() == {"detail": "record not found"})
            saved_ledger = {suffix: require(org.get(ledger_path + suffix)) for suffix in ("/records", "/coding-rounds")}
            reputation = require(org.get(ledger_path + "/reputation"))
            checks.check("ledger record coding and advisory reputation reads persist", saved_ledger["/records"] == [record]
                and saved_ledger["/coding-rounds"] == [coding] and reputation["advisory"] and reputation["total_observations"] == 2)
            checks.check("other employer cannot read any ledger section without consent", all(
                other_org.get(ledger_path + suffix).status_code == 403 for suffix in ("/records", "/coding-rounds", "/reputation")))
            org.headers.pop("X-CSRF-Token")
            checks.check("ledger cookie plus valid other key still requires CSRF", all(
                org.post(path, json=body).status_code == 403 for path, body in (
                    ("/ledger/records", record_body), ("/ledger/coding-rounds", coding_body), (event_path, {"event_type": "refused"}))))
            org.headers["X-CSRF-Token"] = org_csrf
            # T3F employer composition shares this existing restart harness.
            checks.check("employer match and board explain the empty feature pool",
                require(org.post(f"/jobs/{job['id']}/match", json={}))["reason"] == "no_materialized_candidates"
                and require(org.get(f"/jobs/{job['id']}/board"))["match"]["reason"] == "no_materialized_candidates")
            checks.check("employer job compensation and board hide other tenant", all(
                other_org.get(f"/jobs/{job['id']}" + suffix).status_code == 404 for suffix in ("", "/comp", "/board"))
                and other_org.patch(f"/jobs/{job['id']}", json={"status": "closed"}).status_code == 404
                and other_org.post(f"/jobs/{job['id']}/match", json={}).status_code == 404)
            employer_candidate = require(control.post("/candidates", json={"evaluate": False, "resume_text":
                "Synthetic Employer Candidate\nEmail: employer-flow@example.in\nEXPERIENCE\nEngineer at Example, 2020 - 2025\nSKILLS\nPython, Django"}))["candidate_id"]
            offer_body = {"candidate_id": employer_candidate, "role_family": "backend_engineer", "seniority": "senior",
                "city_tier": "metro", "ctc_fixed": 2000000, "offered_at": "2026-10-01T10:00:00Z"}
            checks.check("employer offers refuse missing consent", org.post("/ledger/offers", json=offer_body).status_code == 403)
            employer_write = require(operator.post(f"/ledger/candidates/{employer_candidate}/consent", json={"purpose": "ledger_write", "org_id": org_id}))
            employer_offer = require(org.post("/ledger/offers", json=offer_body))
            checks.check("employer offer is stamped with cookie tenant and grant", employer_offer["org_id"] == org_id
                and employer_offer["consent_id"] == employer_write["id"] and other_org.post("/ledger/offers", json=offer_body).status_code == 403)
            ad_hoc = require(org.post("/comp/estimate", json={"title": "Senior Backend Engineer", "years_experience": 7}))
            checks.check("ad hoc compensation remains advisory with null positioning", ad_hoc["advisory"] and ad_hoc["estimate"]["advisory"]
                and all(ad_hoc[field] is None for field in ("requisition_band", "position", "delta_pct")))
            updated_job = require(org.patch(f"/jobs/{job['id']}", json={"spec": {
                "title": "Synthetic Backend Role", "must_have_skills": ["Python"],
                "comp_band": {"ctc_min": 1500000, "ctc_max": 2500000}}}))
            materialized = require(control.post("/features/materialize", json={}))
            match_body = {"as_of": materialized["as_of"]}
            employer_match = require(org.post(f"/jobs/{job['id']}/match", json=match_body))
            employer_comp = require(org.get(f"/jobs/{job['id']}/comp"))
            employer_overview = require(org.get("/dashboard/overview"))
            employer_card = require(org.get(f"/candidates/{subject}/card"))
            checks.check("materialized employer board and overview return saved advisory data", employer_match["advisory"]
                and employer_match["ranked"][0]["candidate_id"] == employer_candidate
                and require(org.get(f"/jobs/{job['id']}/board"))["match"]["pool_size"] >= 1
                and employer_comp["advisory"] and employer_overview["total_requisitions"] == 1)
            checks.check("consented employer card exposes saved record coding and reputation", all(
                employer_card[section]["status"] == "available" for section in ("records", "coding_rounds", "reputation")))
        with server():
            checks.check("all planes and tenant data survive graceful restart", operator.get("/admin/users").status_code == 200
                and org.get(f"/jobs/{job['id']}").status_code == 200 and sibling.get("/portal/me").status_code == 200
                and other_org.get(f"/jobs/{job['id']}").status_code == 404)
            checks.check("ledger record and coding bodies survive graceful restart exactly", all(
                require(org.get(ledger_path + suffix)) == body for suffix, body in saved_ledger.items()))
            checks.check("restarted reputation stays advisory with both observations",
                (assessment := require(org.get(ledger_path + "/reputation")))["advisory"] and assessment["total_observations"] == 2)
            checks.check("restarted other employer still cannot append events", other_org.post(event_path, json={"event_type": "refused"}).status_code == 404)
            checks.check("employer job overview match and compensation survive restart",
                require(org.get(f"/jobs/{job['id']}")) == updated_job
                and require(org.get("/dashboard/overview")) == employer_overview
                and require(org.post(f"/jobs/{job['id']}/match", json=match_body)) == employer_match
                and require(org.get(f"/jobs/{job['id']}/comp")) == employer_comp)
            for purpose, grant in grants.items():
                require(operator.post(f"/ledger/consent/{grant['id']}/revoke"))
            checks.check("revoked persisted consent immediately denies reads and new writes", all(
                org.get(ledger_path + suffix).status_code == 403 for suffix in ("/records", "/coding-rounds", "/reputation"))
                and org.post("/ledger/records", json=record_body).status_code == 403
                and org.post("/ledger/coding-rounds", json=coding_body).status_code == 403)
            revoked_card = require(org.get(f"/candidates/{subject}/card"))
            require(operator.post(f"/ledger/consent/{employer_write['id']}/revoke"))
            checks.check("employer card and offer honor consent revocation after restart", all(
                revoked_card[section]["status"] == "consent_required" for section in ("records", "coding_rounds", "reputation"))
                and org.post("/ledger/offers", json=offer_body).status_code == 403)
            access_log = require(sibling.get("/portal/access-log"))
            checks.check("subject sees allowed and denied audited ledger queries", all(
                {row["allowed"] for row in access_log if row["action"] == action} == {True, False}
                for action in ("record.query", "coding_round.query", "reputation.query")))
            machine_org = require(operator.post("/ledger/orgs", json={"name": "Synthetic ledger key lifecycle"}))
            machine_id = machine_org["org"]["id"]
            with client(base, headers={"X-Org-Key": machine_org["api_key"]}) as machine:
                rotated = require(operator.post(f"/ledger/orgs/{machine_id}/api-key"))
                checks.check("ledger key rotation invalidates original credential", machine.get(ledger_path + "/records").status_code == 401)
                machine.headers["X-Org-Key"] = rotated["api_key"]
                checks.check("rotated credential resolves but consent remains required", machine.get(ledger_path + "/records").status_code == 403)
                require(operator.delete(f"/ledger/orgs/{machine_id}"))
                checks.check("organization offboarding invalidates rotated credential", machine.get(ledger_path + "/records").status_code == 401)
            for http, token in ((operator, admin_csrf), (org, org_csrf), (other_org, other_csrf), (sibling, sibling_csrf)):
                http.headers["X-CSRF-Token"] = token
                assert require(http.post("/auth/logout")) == {"logged_out": True}
                assert http.get("/auth/me").status_code == 401
            checks.check("logout clears all four sessions across planes", True)
        rows = [json.loads(line) for line in events.read_text().splitlines()]
        checks.check("two migrated lifespans close and detach owned SQL", sum(row["event"] == "stopped" for row in rows) == 2
            and sum(row["event"] == "disposed" for row in rows) == 2
            and all(row["revision"] == "0029_candidate_login_binding" for row in rows if row["event"] == "started"))
    return checks.summary()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
