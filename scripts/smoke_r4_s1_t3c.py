"""Candidate area: migrated scratch HTTP, shared employer intake and restart.

Reuses the fake-provider production SQL composition and graceful server loop.
No working data, external provider calls or existing demo restart.
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
from smoke_r4_s1_t1a import serve
from smoke_s62 import _export_b64
from smoke_s82 import _code_for


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-candidate-router-admin"
RESUME = "Synthetic Candidate Router\nEmail: candidate-router@example.in\n" + "\n".join(
    (ROOT / "tests/fixtures/genuine_genai_resume.txt").read_text(encoding="utf-8").splitlines()[1:]
)


def main():
    checks = Smoke("R4-S1-T3C candidate/source HTTP and graceful restart")
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t3c-"))
    print(f"Synthetic candidate evidence: {scratch}", flush=True)
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
                    assert wait_healthy(health), "scratch candidate app failed to start"
                yield
            finally:
                stop.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("scratch candidate app failed graceful shutdown")
                assert proc.returncode == 0, "scratch candidate app failed during lifespan"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def upload(http, text, **extra):
        return require(http.post("/candidates", json={"resume_text": text, "domain": "data_eng", **extra}))

    with client(base, headers={"X-API-Key": ADMIN}) as control, client(base) as operator, \
            client(base) as org_a, client(base) as org_b:
        with server():
            email = "candidate-router-admin@example.in"
            require(control.post("/admin/users", json={"email": email, "label": "Synthetic candidate reviewer"}))
            require(operator.post("/auth/admin/login", json={"email": email}), 202)
            session = require(operator.post("/auth/admin/verify", json={"email": email, "code": _code_for(mailbox, email)}))
            checks.check("operator cookie write refuses missing CSRF", operator.post("/candidates", json={"resume_text": RESUME}).status_code == 403)
            operator.headers["X-CSRF-Token"] = session["csrf_token"]
            for http, name in ((org_a, "A"), (org_b, "B")):
                org = require(control.post("/ledger/orgs", json={"name": "Candidate Router " + name}))
                http.headers["X-Org-Key"] = org["api_key"]
            checks.check("employer credential cannot use operator candidate area", org_a.get("/candidates/missing").status_code == 401
                and org_a.post("/candidates", json={"resume_text": RESUME}).status_code == 401)
            for body in ({}, {"resume_text": "   "}, {"resume_pdf_b64": "!!!"}, {"resume_text": RESUME, "domain": "missing"}):
                require(operator.post("/candidates", json=body), 422)
            checks.check("invalid intake refuses before persistence", True)
            first = upload(operator, RESUME)
            cid, rid = first["candidate_id"], first["report"]["id"]
            path = f"/candidates/{cid}"
            checks.check("operator intake keeps linked advisory report", first["resume_version"] == 1 and first["extraction_method"] == "heuristic"
                and first["report"]["candidate_id"] == cid and first["report"]["advisory"] and first["report"]["human_review_required"])
            duplicate = upload(operator, RESUME, evaluate=False)
            updated = upload(operator, RESUME + "\nAWS certification.", evaluate=False)
            checks.check("dedup and new versions use the same candidate", duplicate["duplicate_resume"] and duplicate["resume_id"] == first["resume_id"]
                and updated["candidate_id"] == cid and updated["resume_version"] == 2 and updated["report"] is None)
            other = upload(control, RESUME.replace("candidate-router@example.in", "candidate-other@example.in"), evaluate=False)
            checks.check("cross-candidate resume deletion refuses", operator.delete(path + f"/resumes/{other['resume_id']}").status_code == 404
                and require(control.get(f"/candidates/{other['candidate_id']}"))["resume_count"] == 1)
            require(operator.delete(path + f"/resumes/{updated['resume_id']}"))
            detail, resumes, reports = (require(operator.get(path + suffix)) for suffix in ("", "/resumes", "/reports"))
            checks.check("detail resume and report reads reflect one retained version", detail["resume_count"] == 1
                and detail["latest_profile"] is not None and len(resumes["resumes"]) == 1 and [row["id"] for row in reports] == [rid])
            invalid = require(operator.post(path + "/sources/github", json={"handle": "invalid handle!"}), 400)
            github = require(operator.post(path + "/sources/github", json={"handle": "octocat"}))
            checks.check("GitHub invalid handle refuses and fake public signal remains advisory", bool(invalid["detail"])
                and github["method"] == "api" and any(skill["canonical"] == "python" for skill in github["skills"]))
            linkedin = require(operator.post(path + "/sources/linkedin", json={"export_b64": _export_b64()}))
            checks.check("LinkedIn export and filtered history persist", linkedin["method"] == "export"
                and linkedin["activity"]["employers"] == ["Infosys", "TCS"]
                and require(operator.get(path + "/sources", params={"source_type": "linkedin_export"}))["sources"] == [linkedin])
            checks.check("invalid LinkedIn base64 preserves history", require(operator.post(path + "/sources/linkedin", json={"export_b64": "!!!"}), 422) == {"detail": "invalid_base64"}
                and len(require(operator.get(path + "/sources"))["sources"]) == 2)
            key = require(operator.post(path + "/auth-key"))["access_key"]
            with client(base, headers={"X-Candidate-Key": key}) as candidate:
                checks.check("issued candidate key resolves the retained subject", require(candidate.get("/portal/me"))["candidate_id"] == cid)

            owned = require(org_a.post("/screening/candidates", json={"resume_text": RESUME.replace("candidate-router@example.in", "candidate-employer@example.in"), "domain": "data_eng"}))
            employer_rid = owned["report"]["id"]
            checks.check("shared employer intake retains tenant ownership", org_b.get(f"/screening/reports/{employer_rid}").status_code == 404
                and require(org_a.get(f"/screening/reports/{employer_rid}"))["id"] == employer_rid)
            farms = (owned["resume_farm"], owned["report"]["resume_farm"])
            checks.check("both employer farm fields redact counterparty identity", all(farm and farm["matches"] for farm in farms)
                and all(match["candidate_id"] is None and match["resume_id"] is None for farm in farms for match in farm["matches"]))
            saved = {suffix: require(control.get(path + suffix)) for suffix in ("", "/resumes", "/reports", "/sources")}

        with server():
            checks.check("exact candidate resume report and source state survives restart", all(require(control.get(path + suffix)) == body for suffix, body in saved.items()))
            with client(base, headers={"X-Candidate-Key": key}) as candidate:
                checks.check("candidate credential survives restart", require(candidate.get("/portal/me"))["candidate_id"] == cid)
            deleted = require(control.delete(path))
            checks.check("operator erasure reports linked cleanup", deleted == {"candidate_id": cid, "deleted": True, "reports_deleted": 1})
            checks.check("erased candidate reads and writes refuse", all(control.get(path + suffix).status_code == 404 for suffix in ("", "/resumes", "/reports", "/sources"))
                and control.post(path + "/auth-key").status_code == 404
                and control.post(path + "/sources/github", json={"handle": "octocat"}).status_code == 404
                and control.post(path + "/sources/linkedin", json={"export_b64": _export_b64()}).status_code == 404
                and control.get(f"/report/{rid}").status_code == 404)
            with client(base, headers={"X-Candidate-Key": key}) as candidate:
                checks.check("erasure invalidates candidate key", candidate.get("/portal/me").status_code == 401)
            checks.check("unrelated candidate and employer report remain", require(control.get(f"/candidates/{other['candidate_id']}"))["resume_count"] == 1
                and require(org_a.get(f"/screening/reports/{employer_rid}"))["id"] == employer_rid)

    lifecycle = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    checks.check("both starts use migrated shared SQL and graceful cleanup", len([row for row in lifecycle if row["event"] == "started" and row["revision"] == "0029_candidate_login_binding" and row["one_factory"]]) == 2
        and sum(row["event"] == "disposed" for row in lifecycle) == 2
        and sum(row["event"] == "stopped" and row["detached"] for row in lifecycle) == 2)
    logs = (scratch / "server.log").read_text(encoding="utf-8")
    checks.check("app logs omit issued key and candidate mailbox", key not in logs and "candidate-router@example.in" not in logs)
    return checks.summary()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--serve":
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
