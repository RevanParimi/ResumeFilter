"""Feature materialization/search/board/restart on migrated disposable storage.

Default: scratch SQLite. --postgres uses DEE_TEST_DB_URL with a fresh owned
schema, and drops only that schema. All providers are disabled.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy


ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-feature-timestamp-admin"
RANKING = {"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]}


@contextmanager
def database(scratch):
    if "--postgres" not in sys.argv:
        yield "sqlite:///" + (scratch / "app.db").as_posix(), ""
        return
    # URL options override PGOPTIONS; discard them so the app cannot escape
    # the scratch schema selected below through an inherited search_path.
    url = make_url(os.environ["DEE_TEST_DB_URL"]).difference_update_query(["options"])
    assert url.get_backend_name() == "postgresql"
    schema = "r1_feature_smoke_" + uuid.uuid4().hex
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield (url.render_as_string(hide_password=False),
               f"-csearch_path={schema} -ctimezone=Asia/Calcutta")
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def main():
    checks = Smoke("feature timestamp HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-feature-smoke-"))
    print(f"Synthetic artifacts: {scratch}")
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
            "PYTHONPATH": str(ROOT / "src"), "NO_PROXY": "127.0.0.1,localhost",
            "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    uvicorn_argv(port), env=env, cwd=scratch, stdout=log,
                    stderr=subprocess.STDOUT,
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

        with server() as http:
            checks.check("migrated app starts", True)
            org = require(http.post("/ledger/orgs", json={"name": "Synthetic feature agency"}))
            org_headers = {"X-Org-Key": org["api_key"]}
            ids = []
            for name, year in [("Senior", 2013), ("Junior", 2023)]:
                saved = require(http.post("/candidates", json={"resume_text": (
                    f"{name}\nEmail: {name.lower()}@example.com\nEXPERIENCE\n"
                    f"Engineer, Acme ({year} - Present)\nSKILLS\nPython\n"
                )}))
                ids.append(saved["candidate_id"])
            job = require(http.post("/jobs", headers=org_headers, json={
                "title": "Engineer", "must_have_skills": ["python"],
            }))
            first = require(http.post("/features/materialize", json={}))
            checks.check("batch materializes both candidates", first["materialized"] == 2)
            refreshed = require(http.post("/features/materialize", json={"candidate_ids": ids[:1]}))
            checks.check("partial refresh materializes one", refreshed["materialized"] == 1)
            ranked = require(http.post("/talent/search", json={"ranking": RANKING}))
            checks.check("newest cut retains both candidates", ranked["pool_size"] == 2)
            checks.check("advisory ranking keeps senior first",
                         ranked["advisory"] and [r["candidate_id"] for r in ranked["ranked"]] == ids)
            checks.check("returned newest instant matches materialization",
                         datetime.fromisoformat(ranked["as_of"]) == datetime.fromisoformat(refreshed["as_of"]))
            cutoff = datetime.fromisoformat(first["as_of"])
            offset_cut = cutoff.astimezone(timezone(timedelta(hours=5, minutes=30)))
            historical = require(http.post("/talent/search", json={
                "ranking": RANKING, "as_of": offset_cut.isoformat(),
            }))
            checks.check("offset historical cut preserves pool", historical["pool_size"] == 2)
            before = require(http.post("/talent/search", json={
                "ranking": RANKING, "as_of": (cutoff - timedelta(microseconds=1)).isoformat(),
            }))
            checks.check("earlier cut excludes future snapshots", before["pool_size"] == 0)
            board = require(http.get(f"/jobs/{job['id']}/board", headers=org_headers))
            checks.check("board sees materialized pool", board["match"]["pool_size"] == 2)
            require(http.post("/talent/search", json={"ranking": RANKING, "filters": [{
                "feature": "candidate.years_experience", "op": "gte", "value": "invalid",
            }]}), 400)
            checks.check("malformed numeric filter returns 400", True)
            require(http.delete(f"/candidates/{ids[0]}"))
            retried = require(http.post("/features/materialize", json={
                "candidate_ids": ids, "as_of": first["as_of"],
            }))
            checks.check("same-cut retry skips erased subject and updates survivor",
                         retried["materialized"] == 1 and retried["skipped"] == 1)
            refused = require(http.post("/features/materialize", json={
                "candidate_ids": ids[:1],
            }))
            checks.check("new-cut retry cannot recreate erased vector",
                         refused["materialized"] == 0 and refused["skipped"] == 1)
        with server() as http:
            ranked = require(http.post("/talent/search", json={"ranking": RANKING}))
            checks.check("restart preserves only unerased candidate",
                         ranked["pool_size"] == 1 and
                         [r["candidate_id"] for r in ranked["ranked"]] == ids[1:])
            board = require(http.get(f"/jobs/{job['id']}/board", headers=org_headers))
            checks.check("board agrees after restart", board["match"]["pool_size"] == 1)
            retried = require(http.post("/features/materialize", json={"candidate_ids": ids}))
            checks.check("restart preserves skipped-subject accounting",
                         retried["materialized"] == 1 and retried["skipped"] == 1)
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
