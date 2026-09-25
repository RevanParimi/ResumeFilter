"""Real HTTP interview/erasure interleaving and restart on scratch SQLite.

Only the scratch application's answer-resolution boundary is paused. Production
stores/routes run normally, with external providers disabled.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-interview-erasure-admin"
ANSWER = "I built the Python ingestion pipeline and reduced latency with batching."
GATE_APP = '''
import asyncio
from app.interview.service import InterviewService
from app.main import app

original = InterviewService._resolve_answer
entered, released = asyncio.Event(), asyncio.Event()
armed = False

async def resolve(self, **kwargs):
    global armed
    result = await original(self, **kwargs)
    if armed:
        armed = False
        entered.set()
        await asyncio.wait_for(released.wait(), timeout=45)
    return result

InterviewService._resolve_answer = resolve

@app.post("/_test/arm")
async def arm():
    global armed
    entered.clear()
    released.clear()
    armed = True
    return {"armed": True}

@app.get("/_test/entered")
async def wait_entered():
    await asyncio.wait_for(entered.wait(), timeout=45)
    return {"entered": True}

@app.post("/_test/release")
async def release():
    released.set()
    return {"released": True}
'''


def main():
    checks = Smoke("interview erasure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-interview-erasure-"))
    print(f"Synthetic artifacts: {scratch}")
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    db = scratch / "app.db"
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + db.as_posix(), "DEE_ENV": "local",
        "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
        "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
        "DEE_EMAIL_PROVIDER": "null", "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server(gated):
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(
                uvicorn_argv(port, target="gate_app:app" if gated else "app.main:app"),
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                with client(base, headers={"X-API-Key": ADMIN}) as http:
                    assert wait_healthy(http), "scratch app failed to start"
                    yield http
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def candidate(http, name):
        saved = require(http.post("/candidates", json={"resume_text": (
            f"{name}\nEmail: {name.lower()}@example.com\nEXPERIENCE\n"
            "Engineer, Acme (2020 - Present)\nSKILLS\nPython, Spark\n"
            "Built ingestion pipelines, measured latency and shipped batching.\n"
        )}))
        cid = saved["candidate_id"]
        key = require(http.post(f"/candidates/{cid}/auth-key"))["access_key"]
        return cid, {"X-Candidate-Key": key}

    def answer(path, headers, question):
        with client(base) as http:
            return http.post(path, headers=headers,
                             json={"question_id": question["id"], "text": ANSWER})

    erased_ids = []
    with server(True) as http:
        checks.check("migrated application starts", True)
        bid, bheaders = candidate(http, "Kept")
        b = require(http.post("/portal/interviews", json={}, headers=bheaders))
        bsid = b["session"]["id"]
        require(answer(f"/portal/interviews/{bsid}/answers", bheaders, b["next_question"]))
        finished = require(http.post(f"/portal/interviews/{bsid}/finish", headers=bheaders))
        checks.check("other candidate completes advisory interview",
                     finished["session"]["status"] == "completed" and
                     finished["session"]["assessment"]["human_review_required"])
        for door in ("portal", "admin"):
            cid, headers = candidate(http, door)
            erased_ids.append(cid)
            a = require(http.post("/portal/interviews", json={}, headers=headers))
            sid = a["session"]["id"]
            path = f"/portal/interviews/{sid}/answers"
            require(http.post("/_test/arm"))
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(answer, path, headers, a["next_question"])
                try:
                    require(http.get("/_test/entered"))
                    erased = require(http.delete("/portal/me", headers=headers) if door == "portal"
                                     else http.delete(f"/candidates/{cid}"))
                    checks.check(f"{door} erasure completes while answer is paused", erased["deleted"])
                finally:
                    require(http.post("/_test/release"))
                response = pending.result(timeout=45)
            checks.check(f"{door} stale answer returns defined 404", response.status_code == 404)
            checks.check(f"{door} refusal excludes transcript", ANSWER not in response.text)
            checks.check(f"{door} erased credential cannot retry",
                         answer(path, headers, a["next_question"]).status_code == 401)
    with server(False) as http:
        kept = require(http.get(f"/portal/interviews/{bsid}", headers=bheaders))["session"]
        checks.check("restart preserves other candidate's completed transcript",
                     kept["status"] == "completed" and kept["turns"][0]["transcript"] == ANSWER)
        with sqlite3.connect(db) as conn:
            sessions = conn.execute("SELECT id, candidate_id FROM interview_sessions").fetchall()
            checks.check("restart retains only the other interview", sessions == [(bsid, bid)])
            checks.check("no erased turns remain", conn.execute(
                "SELECT DISTINCT session_id FROM interview_turns").fetchall() == [(bsid,)])
            for cid in erased_ids:
                checks.check("erased subject has no audit rows", conn.execute(
                    "SELECT count(*) FROM audit_log WHERE candidate_id = ?", (cid,)).fetchone()[0] == 0)
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
