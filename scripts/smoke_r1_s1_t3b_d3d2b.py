"""Migrated HTTP/restart checks for profile-source erasure.

The scratch server injects erasure on a separate database session immediately
during fetch/flush or after persistence/final read. Thread evidence is in pytest.
Supports SQLite and --postgres (fresh owned schema on DEE_TEST_DB_URL).
"""

from contextlib import contextmanager
import base64
import io
import zipfile
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-source-erasure-admin"
GATE_APP = '''
from sqlalchemy import delete, event
from app.main import app
from app.profile_sources import service as source_module
from app.profile_sources.models import ProfileSourceRow
from app.profile_sources.store import ProfileSourceStore
from app.services.github import GitHubClient, GitHubRepoRaw, GitHubUserRaw

armed = None
original_save = ProfileSourceStore.save_signal
original_guard = ProfileSourceStore.require_saved_signal
original_parse = source_module.parse_linkedin_export

def erase(candidate_id):
    assert app.state.services.portal.erase(candidate_id)['deleted']

def erase_during_fetch():
    global armed
    if armed and armed['mode'] == 'fetch':
        config, armed = armed, None
        erase(config['candidate_id'])

async def github(self, login):
    erase_during_fetch()
    return GitHubUserRaw(login=login, available=login != 'missing', repos=[
        GitHubRepoRaw(name='demo', language='SyntheticLang', languages={'SyntheticLang': 1000})])

def parse(*args):
    result = original_parse(*args)
    erase_during_fetch()
    return result

def save(self, candidate_id, signal):
    global armed
    config = None
    if armed and armed['candidate_id'] == candidate_id and armed['mode'] != 'after_read':
        config, armed = armed, None
    def erase_before_flush(*args):
        erase(candidate_id)
    if config and config['mode'] == 'flush':
        event.listen(self._session_factory, 'before_flush', erase_before_flush, once=True)
    try:
        row_id = original_save(self, candidate_id, signal)
    finally:
        if config and config['mode'] == 'flush':
            event.remove(self._session_factory, 'before_flush', erase_before_flush)
    if config and config['mode'] == 'commit':
        erase(candidate_id)
    elif config and config['mode'] == 'source_only':
        with self._session_factory() as session:
            session.execute(delete(ProfileSourceRow).where(ProfileSourceRow.id == row_id))
            session.commit()
    return row_id

def guard(self, candidate_id, row_id):
    global armed
    result = original_guard(self, candidate_id, row_id)
    if armed and armed['candidate_id'] == candidate_id and armed['mode'] == 'after_read':
        armed = None
        erase(candidate_id)
    return result

GitHubClient.gather_user_signal = github
source_module.parse_linkedin_export = parse
ProfileSourceStore.save_signal = save
ProfileSourceStore.require_saved_signal = guard

@app.post('/_test/arm')
async def arm(candidate_id: str, mode: str):
    global armed
    assert mode in ('fetch', 'flush', 'commit', 'source_only', 'after_read')
    armed = {'candidate_id': candidate_id, 'mode': mode}
    return {'armed': True}
'''


def main():
    checks = Smoke("profile-source erasure HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-source-erasure-"))
    print(f"Synthetic artifacts: {scratch}")
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
            "DEE_CANDIDATES_DB_URL": url, "DEE_ENV": "local",
            "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "null", "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
            "NO_PROXY": "127.0.0.1,localhost", "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        @contextmanager
        def server(gated):
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    uvicorn_argv(port, target="gate_app:app" if gated else "app.main:app"),
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
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

        def body(name):
            return {"resume_text": f"{name}\nEmail: {name.lower()}@example.com\nSKILLS\nPython\n", "evaluate": False}

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Skills.csv", "Name\nSyntheticLang\n")
        payloads = {"github": {"handle": "synthetic"},
                    "linkedin": {"export_b64": base64.b64encode(buffer.getvalue()).decode()}}
        erased, survivors = [], []
        with server(True) as http:
            checks.check("migrated app starts", True)
            keeper = require(http.post("/candidates", json=body("Keeper")))["candidate_id"]
            survivors.append(keeper)
            for kind in payloads:
                require(http.post(f"/candidates/{keeper}/sources/{kind}", json=payloads[kind]))
                for mode in ("fetch", "flush", "commit", "source_only"):
                    candidate_body = body(kind + mode)
                    cid = require(http.post("/candidates", json=candidate_body))["candidate_id"]
                    require(http.post("/_test/arm", params={"candidate_id": cid, "mode": mode}))
                    result = require(http.post(f"/candidates/{cid}/sources/{kind}", json=payloads[kind]), 404)
                    checks.check(f"{kind}/{mode}: safe erasure refusal", result == {
                        "detail": "source not found" if mode == "source_only" else "candidate not found"})
                    if mode == "source_only":
                        assert require(http.get(f"/candidates/{cid}/sources"))["sources"] == []
                    else:
                        erased.append(cid)
                        require(http.get(f"/candidates/{cid}"), 404)
                        fresh = require(http.post("/candidates", json=candidate_body))["candidate_id"]
                        assert fresh != cid
                        cid = fresh
                    survivors.append(cid)
                    signal = require(http.post(f"/candidates/{cid}/sources/{kind}", json=payloads[kind]))
                    checks.check(f"{kind}/{mode}: fresh ingestion remains permitted",
                                 signal["advisory"] and signal["method"] == ("api" if kind == "github" else "export"))
                cid = require(http.post("/candidates", json=body(kind + "Snapshot")))["candidate_id"]
                require(http.post("/_test/arm", params={"candidate_id": cid, "mode": "after_read"}))
                require(http.post(f"/candidates/{cid}/sources/{kind}", json=payloads[kind]))
                erased.append(cid)
                require(http.get(f"/candidates/{cid}"), 404)
                checks.check(f"{kind}: erasure after final read leaves a response snapshot", True)
            history = require(http.get(f"/candidates/{keeper}/sources"))["sources"]
            checks.check("unrelated candidate retains both source histories", len(history) == 2)
            unavailable = require(http.post(f"/candidates/{keeper}/sources/github", json={"handle": "missing"}))
            checks.check("unavailable provider remains advisory 200", unavailable["method"] == "unavailable")
            require(http.post(f"/candidates/{keeper}/sources/linkedin", json={"export_b64": "invalid!!!"}), 422)
            checks.check("malformed transport stays 422", True)
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic source agency"}))
            for kind in payloads:
                response = http.post(f"/candidates/{keeper}/sources/{kind}",
                                     headers={"X-API-Key": "invalid", "X-Org-Key": org["api_key"]}, json=payloads[kind])
                checks.check(f"{kind}: org key cannot authorize admin source write", response.status_code == 401)
            terms = require(http.get("/curation/skills/unmapped"))["terms"]
            term = next(t for t in terms if t["norm_key"] == "syntheticlang")
            checks.check("shared taxonomy observation survives erased ingests",
                         set(term["source_types"]) == {"github", "linkedin_export"} and term["occurrences"] > len(survivors))

        with server(False) as http:
            for cid in erased:
                require(http.get(f"/candidates/{cid}"), 404)
            checks.check("restart preserves candidate erasure", True)
            for cid in survivors:
                assert require(http.get(f"/candidates/{cid}/sources"))["sources"]
            checks.check("restart preserves surviving sources", True)
            terms_after = require(http.get("/curation/skills/unmapped"))["terms"]
            checks.check("restart preserves shared taxonomy queue", terms_after == terms)
            args = {"connect_args": {"options": pg_options}} if pg_options else {}
            engine = create_engine(url, hide_parameters=True, **args)
            try:
                with engine.connect() as connection:
                    owners = set(connection.scalars(text("SELECT candidate_id FROM profile_sources")))
                    checks.check("SQL contains source rows only for survivors", owners == set(survivors))
            finally:
                engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
