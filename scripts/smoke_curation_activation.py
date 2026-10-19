"""Activated curation on migrated scratch storage, HTTP/restart and optional Chrome.

No live providers or working storage. --browser adds real reviewer actions.
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_curation_input import export

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-activation-admin"
GATE_APP = '''
from app.main import app
from app.curation.store import CurationStore
from app.profile_sources.store import ProfileSourceStore
from app.candidates.store import CandidateStore
from app.services.github import GitHubClient, GitHubRepoRaw, GitHubUserRaw

async def github(self, login):
    names = ['Shared raw', 'SyntheticPrivateSkill', 'LongSkill' + '!' * 5000]
    return GitHubUserRaw(login=login, available=True,
        repos=[GitHubRepoRaw(name='demo', languages={name: 100 for name in names})])

original_record = CurationStore.record_observation
def record(self, name, **kwargs):
    if name == 'SyntheticPrivateSkill':
        raise RuntimeError('SyntheticPrivateSkill PRIVATE_DATABASE_ERROR')
    return original_record(self, name, **kwargs)

original_save = ProfileSourceStore.save_signal
def save(self, candidate_id, signal):
    if signal.identifier == 'refused':
        CandidateStore(self._session_factory).delete_candidate(candidate_id)
    return original_save(self, candidate_id, signal)

GitHubClient.gather_user_signal = github
CurationStore.record_observation = record
ProfileSourceStore.save_signal = save
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main(browser=False, legacy_disposition=False):
    checks = Smoke("owned curation activation HTTP/restart" + ("/browser" if browser else ""))
    scratch = Path(tempfile.mkdtemp(prefix="curation-activation-"))
    dbpath = scratch / "app.db"
    print(f"Synthetic artifacts: {scratch}", flush=True)
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + dbpath.as_posix(),
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_DB_MIGRATE_ON_BOOT": "true",
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": str(scratch / "mail.jsonl"),
        "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch), str(ROOT / "scripts")]),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(uvicorn_argv(port, target="gate_app:app"), env=env, cwd=scratch,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base, headers={"X-API-Key": ADMIN}) as http:
                    assert wait_healthy(http), "scratch application startup failed"
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
        return require(http.post("/candidates", json={"resume_text":
            f"{name}\nEmail: {name.lower()}@example.com\nSKILLS\nPython\n",
            "evaluate": False}))["candidate_id"]

    def raw_count():
        with sqlite3.connect(dbpath) as db:
            return db.execute("SELECT count(*) FROM curation_observations").fetchone()[0]

    with server() as http:
        first, second = candidate(http, "First"), candidate(http, "Second")
        require(http.post(f"/candidates/{first}/sources/linkedin", json=export(["Shared raw!"])))
        require(http.post(f"/candidates/{second}/sources/github", json={"handle": "dev"}))
        terms = require(http.get("/curation/skills/unmapped"))["terms"]
        checks.check("two saved contributors share one survivor snapshot", len(terms) == 1
            and terms[0]["occurrences"] == 2 and set(terms[0]["source_types"]) == {"github", "linkedin_export"})
        require(http.delete(f"/candidates/{second}"))
        term, = require(http.get("/curation/skills/unmapped"))["terms"]
        checks.check("erasure drops erased display/count/source type", term["display_name"] == "Shared raw!"
            and term["occurrences"] == 1 and term["source_types"] == ["linkedin_export"])
        refused = candidate(http, "Refused")
        require(http.post(f"/candidates/{refused}/sources/github", json={"handle": "refused"}), 404)
        checks.check("refused source does not contribute", raw_count() == 1)
        require(http.post("/curation/skills/resolve", json={"norm_key": "shared raw", "action": "map",
            "expected_revision": term["review_revision"],
            "canonical": "python", "category": "language"}), 422)
        approved = require(http.post("/curation/skills/resolve", json={"norm_key": "shared raw", "action": "map",
            "expected_revision": term["review_revision"],
            "alias": "Approved shared", "canonical": "python", "category": "language"}))
        checks.check("promotion receipt retains only explicit vocabulary", approved["alias"] == "Approved shared"
            and "norm_key" not in approved and approved["admin_user_id"] is None and raw_count() == 0)
        require(http.post(f"/candidates/{first}/sources/linkedin", json=export(["Shared raw!"])))
        fresh, = require(http.get("/curation/skills/unmapped"))["terms"]
        require(http.post("/curation/skills/resolve", json={"norm_key": "shared raw", "action": "ignore",
            "expected_revision": fresh["review_revision"]}))
        require(http.post(f"/candidates/{first}/sources/linkedin", json=export(["Shared raw!"])))
        checks.check("ignore deletes raw and later input reappears", raw_count() == 1)
        checks.check("unauthorized reviewer refused", http.get("/curation/skills/unmapped",
            headers={"X-API-Key": ""}).status_code == 401)
        require(http.post("/admin/users", json={"email": "reviewer@example.com"}))

    # Seed synthetic legacy and expired rows while the server is stopped.
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(dbpath) as db:
        source = db.execute("SELECT id FROM profile_sources WHERE candidate_id=? LIMIT 1", (first,)).fetchone()[0]
        db.execute("INSERT INTO curation_observations VALUES (?,?,?,?,?)",
                   ("startup-expired", source, "expired raw", "Expired raw", old))
        db.execute("INSERT INTO unmapped_terms (id,norm_key,display_name,source_types,occurrences,"
            "first_seen,last_seen,status,canonical,category,note,decided_by,created_at) "
            "VALUES (?,?,?,'[]',1,?,?,'resolved','python','language',?,?,?)",
            ("legacy", "legacy approved", "Legacy private display", now, now, "Legacy note", "Supplied name", now))
    with server() as http:
        checks.check("startup physically purges expired observations", raw_count() == 1)
        terms = require(http.get("/curation/skills/unmapped"))["terms"]
        checks.check("restart hides legacy and preserves live queue", [t["norm_key"] for t in terms] == ["shared raw"])
        signal = require(http.post(f"/candidates/{first}/sources/linkedin", json=export(["Approved shared", "Legacy approved"])))
        checks.check("restart reloads new and compatible legacy normalization", all(s["canonical"] == "python" for s in signal["skills"]))
        with sqlite3.connect(dbpath) as db:
            db.execute("INSERT INTO curation_observations VALUES (?,?,?,?,?)",
                       ("daily-expired", source, "daily raw", "Daily raw", old))
        checks.check("expired physical row is hidden before maintenance", len(require(http.get("/curation/skills/unmapped"))["terms"]) == 1
            and raw_count() == 2)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/purge_curation.py")], env=env,
            cwd=scratch, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        checks.check("daily command physically purges only expired owned input", result.returncode == 0
            and "removed: 1" in result.stdout and raw_count() == 1)
        if browser:
            from check_ui_curation_browser import run_browser
            asyncio.run(run_browser(base, scratch, dbpath, http, first, checks))
        else:
            require(http.delete(f"/candidates/{first}"))
            checks.check("last contributor erasure deletes remaining queue", raw_count() == 0)
        with sqlite3.connect(dbpath) as db:
            checks.check("maintenance preserves approved vocabulary and legacy content",
                db.execute("SELECT count(*) FROM curation_aliases").fetchone()[0] >= 1
                and db.execute("SELECT display_name,note,decided_by FROM unmapped_terms").fetchall()
                == [("Legacy private display", "Legacy note", "Supplied name")])
    if browser:
        with server() as http:
            checks.check("browser decisions survive subsequent real app restart", require(http.get("/curation/skills/unmapped"))["terms"] == []
                and raw_count() == 0)
            fresh = candidate(http, "Restartbrowser")
            signal = require(http.post(f"/candidates/{fresh}/sources/linkedin", json=export(
                ["Approved browser", "Approved browser skill", "Approved fresh browser", "Approved late browser"])))
            checks.check("restart reloads vocabulary approved through actual Chrome", [s["canonical"] for s in signal["skills"]]
                == ["python", "browser_skill", "python", "python"])
    if legacy_disposition:
        legacy_journey(checks, dbpath, scratch, env, server, candidate, require)
    output = (scratch / "server.log").read_text(encoding="utf-8")
    checks.check("capture failures observable without private terms or exceptions",
        "unmapped_skill_capture_failed" in output and all(v not in output
            for v in ("SyntheticPrivateSkill", "PRIVATE_DATABASE_ERROR", "Traceback")))
    return checks.summary()


def legacy_journey(checks, dbpath, scratch, env, server, candidate, require):
    """Explicit disposition, abrupt process death, retry and application reload."""
    script = ROOT / "scripts/dispose_legacy_curation.py"
    manifest = scratch / "disposition.json"
    selection = [dict(id="legacy", action="map", alias="Reviewed legacy",
                      canonical="python", category="language"), dict(id="to-remove", action="remove")]
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(dbpath) as db:
        for rid, key in (("to-remove", "private pending"), ("retained", "retained legacy")):
            db.execute("INSERT INTO unmapped_terms (id,norm_key,display_name,source_types,occurrences,"
                "first_seen,last_seen,status,canonical,category,note,decided_by,created_at) "
                "VALUES (?,?,?,'[]',1,?,?,'resolved','python','language',?,?,?)",
                (rid, key, "PRIVATE synthetic display", now, now, "PRIVATE note", "PRIVATE name", now))
    manifest.write_text(json.dumps(selection), encoding="utf-8")

    def cli(apply=False):
        return subprocess.run([sys.executable, str(script), "--database", str(dbpath),
            "--selection", str(manifest), *(["--apply"] if apply else [])],
            env=env, cwd=scratch, capture_output=True, text=True, timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    before = dbpath.read_bytes()
    preview = cli()
    checks.check("legacy dry-run gives only counts and does not write", preview.returncode == 0
        and json.loads(preview.stdout)["disposition"]["matched"] == 2
        and all(value not in preview.stdout + preview.stderr for value in
                ("PRIVATE", "Legacy private display", "Supplied name", "Reviewed legacy"))
        and dbpath.read_bytes() == before)
    # Pause after DELETE/INSERT, before commit; kill the real command process.
    marker = scratch / "transaction-ready"
    crash_code = '''
import importlib.util, pathlib, sys, time
spec = importlib.util.spec_from_file_location('disposition', sys.argv[1])
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
original = tool.dispose
def pause(conn, entries, **kwargs):
    result = original(conn, entries, **kwargs)
    pathlib.Path(sys.argv[2]).write_text('ready')
    time.sleep(60)
    return result
tool.dispose = pause
raise SystemExit(tool.main(sys.argv[3:]))
'''
    proc = subprocess.Popen([sys.executable, "-c", crash_code, str(script), str(marker),
        "--database", str(dbpath), "--selection", str(manifest), "--apply"], env=env, cwd=scratch,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not marker.exists() and proc.poll() is None:
            time.sleep(0.05)
        reached = marker.exists()
    finally:
        proc.terminate()
        proc.wait(timeout=15)
    with sqlite3.connect(dbpath) as db:
        ids = {r[0] for r in db.execute("SELECT id FROM unmapped_terms")}
        count = db.execute("SELECT count(*) FROM curation_aliases WHERE norm_key='reviewed legacy'").fetchone()[0]
    checks.check("process death before commit rolls back deletion and approval", reached
        and ids == {"legacy", "to-remove", "retained"} and count == 0)
    manifest.write_text(json.dumps([dict(selection[0], alias="Approved shared"), selection[1]]), encoding="utf-8")
    conflict = cli(True)
    with sqlite3.connect(dbpath) as db:
        preserved = db.execute("SELECT count(*) FROM unmapped_terms").fetchone()[0] == 3
    checks.check("CLI alias conflict rolls back the entire selection without disclosure",
        conflict.returncode == 2 and conflict.stdout == "" and preserved
        and all(value not in conflict.stderr for value in ("PRIVATE", "Approved shared", "Traceback")))
    manifest.write_text(json.dumps(selection), encoding="utf-8")
    applied, replay = cli(True), cli(True)
    checks.check("explicit cleanup and lost-response replay are bounded", applied.returncode == replay.returncode == 0
        and json.loads(applied.stdout)["disposition"]["removed"] == 2
        and json.loads(replay.stdout)["disposition"]["absent"] == 2)
    with server() as http:
        fresh = candidate(http, "LegacyJourney")
        signal = require(http.post(f"/candidates/{fresh}/sources/linkedin",
            json=export(["Reviewed legacy", "Retained legacy", "Legacy approved"])))
        skills = {s["name"]: s for s in signal["skills"]}
        checks.check("app restart loads approved and retained aliases and drops removed legacy key",
            skills["Reviewed legacy"]["canonical"] == skills["Retained legacy"]["canonical"] == "python"
            and skills["Legacy approved"]["canonical"] is None)
        terms = require(http.get("/curation/skills/unmapped"))["terms"]
        checks.check("remaining historical raw text stays hidden from ordinary queue", len(terms) == 1
            and terms[0]["norm_key"] == "legacy approved" and "PRIVATE" not in str(terms))
        require(http.delete(f"/candidates/{fresh}"))
        checks.check("fresh source erasure still removes new observations", require(http.get(
            "/curation/skills/unmapped"))["terms"] == [])
    with sqlite3.connect(dbpath) as db:
        checks.check("unselected history and approved vocabulary survive restart and erasure",
            db.execute("SELECT id,display_name,note,decided_by FROM unmapped_terms").fetchall()
            == [("retained", "PRIVATE synthetic display", "PRIVATE note", "PRIVATE name")]
            and db.execute("SELECT alias FROM curation_aliases WHERE norm_key='reviewed legacy'").fetchone()
            == ("Reviewed legacy",))


if __name__ == "__main__":
    raise SystemExit(main(browser="--browser" in sys.argv,
                          legacy_disposition="--legacy-disposition" in sys.argv))
