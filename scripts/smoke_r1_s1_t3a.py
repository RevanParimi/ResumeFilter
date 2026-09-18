"""HTTP evaluation/erase interleaving and restart on migrated scratch SQLite.

The scratch-only wrapper pauses the real evaluator with asyncio events. No
production route/store is replaced; external providers are disabled explicitly.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-r1-s1-t3a-admin"
GATE_APP = '''
import asyncio
from sqlalchemy import select
from app.candidates.models import CandidateRow
from app.graph.build import EvaluationEngine
from app.main import app

original = EvaluationEngine.evaluate
entered, released = asyncio.Event(), asyncio.Event()
armed = False
report_id = None

async def evaluate(self, **kwargs):
    global armed, report_id
    report = await original(self, **kwargs)
    if armed:
        armed = False
        report_id = report.id
        entered.set()
        await asyncio.wait_for(released.wait(), timeout=45)
    return report

EvaluationEngine.evaluate = evaluate

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
    with app.state.services.session_factory() as session:
        ids = list(session.scalars(select(CandidateRow.id)))
    return {"candidate_ids": ids, "report_id": report_id}

@app.post("/_test/release")
async def release():
    released.set()
    return {"released": True}
'''


def main():
    checks = Smoke("r1-s1-t3a erasure race")
    scratch_root = ROOT / ".pytest_cache"
    scratch_root.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="r1-s1-t3a-", dir=scratch_root))
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    db = scratch / "app.db"
    db_url = "sqlite:///" + db.as_posix()
    fresh = scratch / "flywheel.jsonl"
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
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    headers = {"X-API-Key": ADMIN}

    def boot(log, gated):
        argv = uvicorn_argv(port)
        if gated:
            argv[argv.index("app.main:app")] = "gate_app:app"
        return subprocess.Popen(argv, env=env, cwd=scratch, stdout=log,
                                stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def stop(proc):
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    def upload(email):
        with client(base, headers=headers) as http:
            return require(http.post("/candidates", json={"resume_text": (
                f"Candidate\nEmail: {email}\nSkills: Python\n"
                "- Built production RAG at scale for support tickets.\n"
            )}))

    print(f"Synthetic artifacts: {scratch}")
    with (scratch / "server.log").open("w", encoding="utf-8") as log:
        proc = boot(log, gated=True)
        try:
            with client(base, headers=headers) as http:
                if not checks.check("migrated app starts", wait_healthy(http)):
                    return checks.summary()
                b = upload("b@example.com")
                bid, brid = b["candidate_id"], b["report"]["id"]
                require(http.post(f"/report/{brid}/outcome", json={
                    "outcome": "inconclusive", "notes": "keep B synthetic note",
                }))
                # Exercise both real erasure entry points with fresh subjects.
                for door in ("portal", "admin"):
                    require(http.post("/_test/arm"))
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        pending = executor.submit(upload, f"{door}@example.com")
                        try:
                            waiting = require(http.get("/_test/entered"))
                            ids = set(waiting["candidate_ids"]) - {bid}
                            assert len(ids) == 1
                            aid = ids.pop()
                            if door == "portal":
                                key = require(http.post(f"/candidates/{aid}/auth-key"))["access_key"]
                                erased = require(http.delete("/portal/me", headers={"X-Candidate-Key": key}))
                            else:
                                erased = require(http.delete(f"/candidates/{aid}"))
                            checks.check(f"{door} erases while evaluation is paused", erased["deleted"])
                        finally:
                            require(http.post("/_test/release"))
                        cancelled = pending.result(timeout=45)
                    checks.check(f"{door} in-flight response cancels report", cancelled["report"] is None)
                    rid = waiting["report_id"]
                    checks.check(f"{door} rejected report unavailable", http.get(f"/report/{rid}").status_code == 404)
                    checks.check(f"{door} stale outcome refused", http.post(
                        f"/report/{rid}/outcome", json={"outcome": "inconclusive"}).status_code == 404)
                    checks.check(f"{door} repeat deletion returns 404",
                                 http.delete(f"/candidates/{aid}").status_code == 404)
                checks.check("no unmanaged flywheel file", not fresh.exists())
        finally:
            stop(proc)

        # Restart without the test wrapper, on the exact same migrated DB.
        proc = boot(log, gated=False)
        try:
            with client(base, headers=headers) as http:
                if not checks.check("unwrapped production app restarts", wait_healthy(http)):
                    return checks.summary()
                checks.check("B report survives restart", http.get(f"/report/{brid}").status_code == 200)
                outcomes = require(http.get(f"/report/{brid}/outcomes"))["outcomes"]
                checks.check("B outcome survives restart", len(outcomes) == 1 and
                             outcomes[0]["notes"] == "keep B synthetic note")
                with sqlite3.connect(db) as sql:
                    checks.check("only B candidate remains", sql.execute("SELECT id FROM candidates").fetchall() == [(bid,)])
                    checks.check("only B report remains", sql.execute("SELECT id FROM reports").fetchall() == [(brid,)])
                    checks.check("only B outcome remains", sql.execute("SELECT report_id FROM outcomes").fetchall() == [(brid,)])
        finally:
            stop(proc)
    logs = (scratch / "server.log").read_text(encoding="utf-8")
    checks.check("race logged without SQL payload", "write_race" in logs and "INSERT INTO reports" not in logs)
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
