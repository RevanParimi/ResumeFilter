"""D2a: real migrated scratch HTTP/restart; synthetic providers, no live data."""

import base64
from contextlib import contextmanager
import csv
import io
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-curation-input-admin"
GATE_APP = '''
from app.main import app
from app.curation.store import CurationStore
from app.services.github import GitHubClient, GitHubRepoRaw, GitHubUserRaw

async def github(self, login):
    names = ['COBOL', 'LongSkill' + '!' * 5000, '\\tControlSkill',
             ' ' * 124 + 'PaddingSkill', 'SyntheticPrivateSkill']
    return GitHubUserRaw(login=login, available=True,
        repos=[GitHubRepoRaw(name='demo', languages={name: 100 for name in names})])

original_record = CurationStore.record_observation
def record(self, name, **kwargs):
    if name == 'SyntheticPrivateSkill':
        raise RuntimeError('SyntheticPrivateSkill PRIVATE_DATABASE_ERROR')
    return original_record(self, name, **kwargs)

GitHubClient.gather_user_signal = github
CurationStore.record_observation = record
'''


def export(names):
    rows = io.StringIO(newline="")
    writer = csv.writer(rows)
    writer.writerow(["Name"])
    writer.writerows([name] for name in names)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("Skills.csv", rows.getvalue())
    return {"export_b64": base64.b64encode(buf.getvalue()).decode()}


def main():
    checks = Smoke("curation raw input HTTP/restart")
    scratch = Path(tempfile.mkdtemp(prefix="curation-input-"))
    print(f"Synthetic artifacts: {scratch}")
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + (scratch / "app.db").as_posix(),
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_DB_MIGRATE_ON_BOOT": "true",
        "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "null",
        "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
        "NO_PROXY": "127.0.0.1,localhost",
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

    def require(response):
        assert response.status_code == 200, (response.request.url.path, response.status_code)
        return response.json()

    with server(True) as http:
        ids = []
        saved_signals = {}
        for name in ("First", "Second"):
            ids.append(require(http.post("/candidates", json={"resume_text":
                f"{name}\nEmail: {name.lower()}@example.com\nSKILLS\nPython\n",
                "evaluate": False}))["candidate_id"])
        checks.check("migrated startup and two candidates", len(set(ids)) == 2)
        for cid, kind in zip(ids, ("linkedin", "github")):
            body = export(["COBOL" + "!" * 123, "LongSkill" + "!" * 5000,
                           "\tControlSkill", " " * 124 + "PaddingSkill", "SyntheticPrivateSkill"])
            signal = require(http.post(f"/candidates/{cid}/sources/{kind}",
                                       json=body if kind == "linkedin" else {"handle": "dev"}))
            saved_signals[cid] = signal
            checks.check(f"{kind}: ingestion survives refusals and capture failure",
                         any(s["name"] == "SyntheticPrivateSkill" for s in signal["skills"]))
            queued = require(http.get("/curation/skills/unmapped"))["terms"]
            checks.check(f"{kind}: only bounded valid term queued",
                         len(queued) == 1 and queued[0]["norm_key"] == "cobol")
        checks.check("queue remains admin-only", http.get("/curation/skills/unmapped",
                     headers={"X-API-Key": ""}).status_code == 401)
        resolved = require(http.post("/curation/skills/resolve", json={
            "expected_revision": queued[0]["review_revision"],
            "norm_key": "cobol", "action": "create", "alias": "COBOL", "canonical": "cobol", "category": "language"}))
        checks.check("valid vocabulary still resolves", resolved["canonical"] == "cobol")

    owned_lifecycle = "--owned-lifecycle" in sys.argv
    owned_storage = "--owned-storage" in sys.argv or owned_lifecycle
    if owned_storage:
        # Historical schema/store modes still seed synthetic extra observations.
        # Automatic capture and review above now use the owned lifecycle.
        with sqlite3.connect(scratch / "app.db") as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("INSERT INTO curation_observations "
                "(id, source_id, norm_key, display_name, created_at) "
                "SELECT id, id, 'synthetic raw', 'Synthetic raw ' || candidate_id, "
                "datetime('now') FROM profile_sources")
            db.execute("INSERT INTO curation_aliases "
                "(norm_key, alias, canonical, category, action, decided_at) VALUES "
                "('approved synthetic', 'Approved synthetic', 'approved_synthetic', "
                "'language', 'create', '2026-09-28 00:00:00+00:00')")
            checks.check("owned schema seeded against two saved sources",
                         db.execute("SELECT count(*) FROM curation_observations").fetchone()[0] == 2)

    if owned_lifecycle:
        # Direct store exercise while the real HTTP app is stopped.
        sys.path.insert(0, str(ROOT / "src"))
        import app.services  # register the complete ORM metadata
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select, update
        from app.core.db import make_engine, make_session_factory
        from app.curation.models import CurationObservationRow
        from app.curation.schema import CurationAction
        from app.curation.store import CurationStore
        from app.profile_sources.models import ProfileSourceRow

        engine = make_engine(env["DEE_CANDIDATES_DB_URL"])
        store = CurationStore(make_session_factory(engine))
        with engine.connect() as conn:
            source_ids = dict(conn.execute(select(ProfileSourceRow.candidate_id, ProfileSourceRow.id)).all())
        for cid in ids:
            assert store.record_observation("Review COBOL", source_id=source_ids[cid])
        checks.check("owned store aggregates two durable contributors",
                     store.get_observation("review cobol").occurrences == 2)
        store.resolve_observations("review cobol", action=CurationAction.CREATE,
            alias="Reviewed COBOL", canonical="cobol", category="language")
        checks.check("promotion deletes raw and approves only explicit alias",
                     store.get_observation("review cobol") is None
                     and store.load_owned_overlay()["reviewed cobol"].canonical == "cobol")
        store.record_observation("Expired synthetic", source_id=source_ids[ids[1]])
        with engine.begin() as conn:
            conn.execute(update(CurationObservationRow).where(
                CurationObservationRow.norm_key == "expired synthetic").values(
                created_at=datetime.now(timezone.utc) - timedelta(days=31)))
        checks.check("expiry hidden before physical purge",
                     store.get_observation("expired synthetic") is None)
        # Keep the schema-only seed live regardless of the date of this run.
        with engine.begin() as conn:
            conn.execute(update(CurationObservationRow).where(
                CurationObservationRow.norm_key == "synthetic raw").values(
                created_at=datetime.now(timezone.utc)))
        checks.check("explicit purge removes expired observation", store.purge_expired() == 1)
        engine.dispose()

    with server(False) as http:
        queued = require(http.get("/curation/skills/unmapped"))["terms"]
        checks.check("restart retains only valid vocabulary", (len(queued) == 1 and queued[0]["norm_key"] == "synthetic raw") if owned_storage else queued == [])
        for cid in ids:
            stored = require(http.get(f"/candidates/{cid}/sources"))
            checks.check("source evidence survives restart",
                         stored["candidate_id"] == cid and stored["sources"] == [saved_signals[cid]])
        signal = require(http.post(f"/candidates/{ids[0]}/sources/linkedin", json=export(["COBOL"])))
        checks.check("approved normalization survives restart", signal["skills"][0]["canonical"] == "cobol")

        if owned_storage:
            with sqlite3.connect(scratch / "app.db") as db:
                checks.check("owned observations survive process restart",
                             db.execute("SELECT count(*) FROM curation_observations").fetchone()[0] == 2)
            erased = require(http.delete(f"/candidates/{ids[0]}"))
            checks.check("HTTP candidate erasure succeeds", erased["deleted"])
            with sqlite3.connect(scratch / "app.db") as db:
                checks.check("HTTP erasure leaves only survivor raw form",
                    db.execute("SELECT display_name FROM curation_observations").fetchall()
                    == [("Synthetic raw " + ids[1],)])
                checks.check("HTTP erasure preserves approved vocabulary and legacy classification",
                    db.execute("SELECT alias FROM curation_aliases ORDER BY alias").fetchall()
                    == ([("Approved synthetic",), ("COBOL",), ("Reviewed COBOL",)] if owned_lifecycle
                        else [("Approved synthetic",), ("COBOL",)])
                    and db.execute("SELECT provenance FROM unmapped_terms").fetchall() == [])

            if owned_lifecycle:
                engine = make_engine(env["DEE_CANDIDATES_DB_URL"])
                store = CurationStore(make_session_factory(engine))
                term = store.get_observation("synthetic raw")
                checks.check("owned snapshot after HTTP erasure has only survivor",
                    term.occurrences == 1 and term.display_name == "Synthetic raw " + ids[1]
                    and term.source_types == ["github"])
                checks.check("approved alias survives restart and erasure",
                    store.load_owned_overlay()["reviewed cobol"].canonical == "cobol")
                store.resolve_observations("synthetic raw", action=CurationAction.IGNORE)
                checks.check("ignore removes remaining raw observations", store.list_observations() == ([], None))
                engine.dispose()

    output = (scratch / "server.log").read_text(encoding="utf-8")
    checks.check("capture failure observable", "unmapped_skill_capture_failed" in output)
    checks.check("capture log omits private input and exception", all(
        private not in output for private in ("SyntheticPrivateSkill", "PRIVATE_DATABASE_ERROR", "Traceback")))
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
