"""Authenticated evaluation/feedback/contact/restart on migrated scratch SQL.

SQLite by default; --postgres needs a disposable DEE_TEST_DB_URL. Uses the
existing fake-model/captured-email composition and never sends real messages.
"""
from contextlib import ExitStack, contextmanager
import base64
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, func, select, text
from app.candidates.models import CandidateRow

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from smoke_r3_s1_t2 import latest_code

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-r3-integration-admin"


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s1-q-http-"))
    print(f"Synthetic combined HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R3-S1 authenticated combined HTTP/restart")
    mailbox = scratch / "mail.jsonl"
    control = Path(str(mailbox) + ".control")
    codes = []
    emails = ["q-org-a@example.com", "q-org-b@example.com",
              "q-candidate-a@example.com", "q-candidate-b@example.com",
              "q-operator@example.com"]

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def login(actor, plane, email, *, signup=True, name=""):
        body = {"email": email}
        if name:
            body["organization_name"] = name
        require(actor.post(f"/auth/{plane}/{'signup' if signup else 'login'}", json=body), 202)
        messages = [json.loads(line) for line in mailbox.read_text(encoding="utf-8").splitlines()]
        msg = next(m for m in reversed(messages) if m["to"] == email)
        code = re.search(r"\b(\d{6})\b", msg["body"])[1]
        codes.append(code)
        verified = require(actor.post(f"/auth/{plane}/verify", json={"email": email, "code": code}))
        actor.headers["X-CSRF-Token"] = verified["csrf_token"]

    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
            "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_LLM_MAX_RETRIES": "0", "DEE_GITHUB_TOKEN": "",
            "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "capture",
            "DEE_EMAIL_CAPTURE_PATH": str(mailbox), "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_SPEECH_PROVIDER": "local", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
            "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_VERIF_OTP_DEBUG_ECHO": "false",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "PGOPTIONS": pg_options, "NO_PROXY": "127.0.0.1,localhost",
            "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r3_s1_t2:create_smoke_app") + ["--factory"],
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(base, headers={"X-API-Key": ADMIN}) as admin:
                        assert wait_healthy(admin), "scratch app failed to start"
                        yield admin
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

        with ExitStack() as actors:
            org_a, org_b, cand_a, cand_b, operator = [actors.enter_context(client(base)) for _ in range(5)]
            with server() as admin:
                engine = create_engine(url, hide_parameters=True,
                    connect_args={"options": pg_options} if pg_options else {})
                try:
                    with engine.connect() as conn:
                        checks.check("combined scratch composition migrated to head",
                            conn.scalar(text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
                finally:
                    engine.dispose()
                def candidate_count():
                    try:
                        with engine.connect() as conn:
                            return conn.scalar(select(func.count()).select_from(CandidateRow))
                    finally:
                        engine.dispose()
                login(org_a, "org", emails[0], name="Synthetic Q Agency A")
                login(org_b, "org", emails[1], name="Synthetic Q Agency B")
                login(cand_a, "candidate", emails[2])
                login(cand_b, "candidate", emails[3])
                require(admin.post("/admin/users", json={"email": emails[4], "label": "Synthetic Q Operator"}))
                login(operator, "admin", emails[4], signup=False)
                checks.check("captured login yields named cookie sessions in all three planes",
                    all(actor.cookies.get("dee_session") for actor in (org_a, org_b, cand_a, cand_b, operator)))
                before = candidate_count()
                require(org_a.post("/screening/candidates", json={"resume_text": "   "}), 422)
                checks.check("invalid input refuses before candidate persistence",
                    candidate_count() == before)
                resume = (ROOT / "tests/fixtures/style_polished_resume.txt").read_text(encoding="utf-8")
                csrf = org_a.headers.pop("X-CSRF-Token")
                try:
                    require(org_a.post("/screening/candidates", json={"resume_text": resume}), 403)
                finally:
                    org_a.headers["X-CSRF-Token"] = csrf
                checks.check("actual cookie upload requires CSRF and saves nothing on refusal",
                    candidate_count() == before)
                uploaded = require(org_a.post("/screening/candidates", json={"resume_text": resume, "domain": "data_eng"}))
                report = uploaded["report"]
                rid = report["id"]
                checks.check("org text intake returns actual persisted advisory v2 report",
                    require(org_a.get(f"/screening/reports/{rid}")) == report
                    and report["advisory"] and report["human_review_required"]
                    and report["fabrication_risk"]["scorer_version"] == 2)
                require(org_b.get(f"/screening/reports/{rid}"), 404)
                require(org_b.post(f"/screening/reports/{rid}/outcome", json={"outcome": "verified_genuine"}), 404)
                require(cand_a.get(f"/screening/reports/{rid}"), 401)
                checks.check("foreign organisation and candidate cannot read/write org report", True)
                recorded = require(org_a.post(f"/screening/reports/{rid}/outcome", json={"outcome": "verified_genuine"}))
                org_outcomes = require(org_a.get(f"/screening/reports/{rid}/outcomes"))["outcomes"]
                checks.check("human judgement persists on the correct org route",
                    len(org_outcomes) == 1 and org_outcomes[0]["outcome"] == "verified_genuine"
                    and org_outcomes[0]["recorded_by"] == "organization"
                    and recorded["report_id"] == rid)
                require(org_a.post("/screening/candidates", json={"resume_pdf_b64": base64.b64encode(b"%PDF-unreadable").decode()}), 422)
                # Reuse the actual minimal-PDF fixture generator used by Chrome.
                from check_ui_screening_browser import minimal_pdf
                pdf = minimal_pdf(resume.splitlines())
                pdf_report = require(org_a.post("/screening/candidates", json={
                    "resume_pdf_b64": base64.b64encode(pdf).decode(), "domain": "genai"}))["report"]
                checks.check("unreadable PDF refuses and valid PDF retry saves selected domain",
                    pdf_report["id"] != rid and pdf_report["domain"] == "genai")
                adhoc = require(operator.post("/evaluate", json={"resume_text": resume, "domain": "genai"}))
                require(operator.post(f'/report/{adhoc["id"]}/outcome', json={"outcome": "verified_genuine"}))
                adhoc_outcomes = require(operator.get(f'/report/{adhoc["id"]}/outcomes'))["outcomes"]
                checks.check("operator ad-hoc report and outcome persist without candidate",
                    adhoc["candidate_id"] is None and len(adhoc_outcomes) == 1
                    and adhoc_outcomes[0]["outcome"] == "verified_genuine"
                    and adhoc_outcomes[0]["recorded_by"] == "operator")
                require(cand_a.post("/evaluate", json={"resume_text": resume}), 401)
                checks.check("candidate plane cannot create an evaluation", True)
                control.write_text("failed", encoding="utf-8")
                failed = require(cand_a.post("/portal/verifications", json={"method": "otp_email", "destination": emails[2]}), 503)
                checks.check("combined delivery failure is safe and records no sent success",
                    failed == {"detail": "email_send_failed"}
                    and all(v["status"] == "failed" for v in require(cand_a.get("/portal/verifications"))["verifications"]))
                control.write_text("ok", encoding="utf-8")
                start = require(cand_a.post("/portal/verifications", json={"method": "otp_email", "destination": emails[2]}))
                vid = start["verification"]["id"]
                code = latest_code(mailbox, emails[2]); codes.append(code)
                checks.check("retry actually captures a code with no debug echo", start.get("debug_code") is None)
                require(cand_b.post(f"/portal/verifications/{vid}/confirm", json={"code": code}), 404)
                require(org_a.post("/portal/verifications", json={"method": "otp_email", "destination": emails[2]}), 401)
                checks.check("contact confirmation is candidate-owned and wrong plane refuses", True)
                completed = require(cand_a.post(f"/portal/verifications/{vid}/confirm", json={"code": code}))
                require(cand_a.post(f"/portal/verifications/{vid}/confirm", json={"code": code}), 400)
                checks.check("captured contact code verifies once", completed["status"] == "verified")

            with server() as admin:
                checks.check("restart retains both org reports and exact saved human judgement",
                    require(org_a.get(f"/screening/reports/{rid}")) == report
                    and require(org_a.get(f'/screening/reports/{pdf_report["id"]}')) == pdf_report
                    and require(org_a.get(f"/screening/reports/{rid}/outcomes"))["outcomes"] == org_outcomes)
                checks.check("restart retains operator report and exact judgement",
                    require(operator.get(f'/report/{adhoc["id"]}')) == adhoc
                    and require(operator.get(f'/report/{adhoc["id"]}/outcomes'))["outcomes"] == adhoc_outcomes)
                status = require(cand_a.get("/portal/verifications"))
                checks.check("restart retains contact outcome and advisory contact assurance",
                    completed in status["verifications"] and status["assurance"]["level"] == 2 and status["assurance"]["advisory"])
                require(cand_a.delete("/portal/me"))
                require(cand_a.get("/portal/verifications"), 401)
                require(cand_b.get("/portal/verifications"))
                require(org_a.get(f"/screening/reports/{rid}"))
                checks.check("contact erasure revokes old session and preserves unrelated actors/reports", True)
                require(org_a.post("/auth/logout"))
                require(org_a.post("/screening/candidates", json={"resume_text": resume}), 401)
                checks.check("expired org session cannot upload after logout", True)
            logged = (scratch / "server.log").read_text(encoding="utf-8")
            checks.check("combined app logs omit raw destinations and captured codes",
                all(value not in logged for value in [*emails, *codes]))
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
