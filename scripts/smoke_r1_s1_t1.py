"""Real HTTP/startup/restart proof that new evaluation text stays in SQL.

Run with .resume/Scripts/python.exe scripts/smoke_r1_s1_t1.py.
All state is synthetic, under .pytest_cache; provider calls are disabled.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import tempfile

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "r1-s1-t1-synthetic-admin"


def main() -> int:
    checks = Smoke("r1-s1-t1 retention")
    scratch_root = ROOT / ".pytest_cache"
    scratch_root.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="r1-s1-t1-", dir=scratch_root))
    db_url = "sqlite:///" + (scratch / "app.db").as_posix()
    legacy = scratch / "legacy.jsonl"
    legacy_content = b'{"claim_text":"synthetic legacy fixture"}\n'
    legacy.write_bytes(legacy_content)
    fresh = scratch / "new" / "flywheel.jsonl"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    # CWD is scratch, so Settings cannot read the developer's .env. Clear
    # inherited DEE_* too; explicitly restore the shared harness's safety pins.
    env = {k: v for k, v in base_env(scratch, db_url).items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
        "DEE_CANDIDATES_DB_URL": db_url,
        "DEE_ENV": "local",
        "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
        "DEE_EMAIL_PROVIDER": "null",
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_FLYWHEEL_PATH": str(fresh),
        "PYTHONPATH": str(ROOT / "src"),
        "NO_PROXY": "127.0.0.1,localhost",
    })

    def boot(log):
        return subprocess.Popen(
            uvicorn_argv(port), env=env, cwd=scratch,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def stop(proc):
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

    def require(response, status=200):
        if response.status_code != status:
            raise AssertionError(f"{response.request.method} {response.request.url.path}: {response.status_code}")
        return response.json()

    def upload(http, email):
        return require(http.post("/candidates", json={"resume_text": (
            f"Candidate\nEmail: {email}\nSkills: Python\n"
            "- Built production RAG at scale for support tickets.\n"
        )}))

    print(f"Synthetic artifacts: {scratch}")
    with (scratch / "server.log").open("w", encoding="utf-8") as log:
        proc = boot(log)
        try:
            with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
                if not checks.check("production app starts on migrated scratch storage", wait_healthy(http)):
                    return checks.summary()
                a, b = upload(http, "a@example.com"), upload(http, "b@example.com")
                for up in (a, b):
                    checks.check("evaluation has real verdicts", bool(up["report"]["verdicts"]))
                    require(http.post(f"/report/{up['report']['id']}/outcome", json={
                        "outcome": "candidate_clarified", "notes": "Synthetic private review note",
                    }))
                key = require(http.post(f"/candidates/{a['candidate_id']}/auth-key"))["access_key"]
                erased = require(http.delete("/portal/me", headers={"X-Candidate-Key": key}))
                checks.check("portal erase completed", erased["deleted"])
                checks.check("erased report is unavailable", http.get(f"/report/{a['report']['id']}").status_code == 404)
                checks.check("erased outcomes are unavailable", http.get(f"/report/{a['report']['id']}/outcomes").status_code == 404)
                checks.check("other report remains", http.get(f"/report/{b['report']['id']}").status_code == 200)
                checks.check("no unmanaged file/directory created", not fresh.parent.exists())
        finally:
            stop(proc)

        # Restart the actual app using the same SQL DB and an existing legacy
        # file path: new writes must neither append to nor clean up that file.
        env["DEE_FLYWHEEL_PATH"] = str(legacy)
        proc = boot(log)
        try:
            with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
                if not checks.check("app restarts", wait_healthy(http)):
                    return checks.summary()
                checks.check("erased report stays gone after restart", http.get(f"/report/{a['report']['id']}").status_code == 404)
                outcomes = require(http.get(f"/report/{b['report']['id']}/outcomes"))
                checks.check("other outcome survives restart",
                             len(outcomes["outcomes"]) == 1
                             and outcomes["outcomes"][0]["notes"] == "Synthetic private review note")
                require(http.post(f"/report/{b['report']['id']}/outcome", json={"outcome": "inconclusive"}))
                standalone = require(http.post("/evaluate", json={
                    "resume_text": "- Built production RAG for support tickets.",
                }))
                checks.check("standalone report has no guessed candidate", standalone["candidate_id"] is None)
                erased_b = require(http.delete(f"/candidates/{b['candidate_id']}"))
                checks.check("admin erase completed", erased_b["deleted"])
                checks.check("admin erasure removes outcomes", http.get(f"/report/{b['report']['id']}/outcomes").status_code == 404)
                checks.check("legacy bytes untouched by report/outcome writes", legacy.read_bytes() == legacy_content)
                checks.check("standalone stays explicitly owned by its report lifecycle", http.get(f"/report/{standalone['id']}").status_code == 200)
        finally:
            stop(proc)
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
