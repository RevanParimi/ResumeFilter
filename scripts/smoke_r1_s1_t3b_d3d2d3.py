"""Combined erasure on migrated synthetic storage; HTTP, rollback and restart.

SQLite by default; --postgres uses an owned schema in disposable DEE_TEST_DB_URL.
Reuse the login scratch hooks and smoke harness. Never select working storage.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import tempfile

import httpx
from sqlalchemy import bindparam, create_engine, inspect, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_curation_input import export
from smoke_r1_s1_t3a_v1 import database
from smoke_r1_s1_t3b_d3d2c1 import GATE_APP as LOGIN_APP
from smoke_s82 import _code_for

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-combined-erasure-admin"
GATE_APP = LOGIN_APP + '''
@app.post('/_test/cleanup-mode')
async def cleanup_mode(mode: str):
    assert mode in ('failure', 'crash_before_commit', 'crash_after_commit')
    factory = app.state.services.candidates._session_factory
    engine = factory.kw['bind']
    if mode == 'crash_after_commit':
        event.listen(factory, 'after_commit', lambda *_: os._exit(77), once=True)
    else:
        def stop(conn, cursor, statement, params, context, executemany):
            if statement.lower().startswith('delete from candidates'):
                if mode == 'failure':
                    raise RuntimeError('synthetic cleanup failure')
                os._exit(76)
        event.listen(engine, 'after_cursor_execute', stop)
    return {'armed': True}
'''


def main():
    checks = Smoke("combined erasure HTTP/rollback/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-combined-erasure-"))
    print(f"Synthetic artifacts: {scratch}", flush=True)
    (scratch / "gate_app.py").write_text(GATE_APP, encoding="utf-8")
    mailbox = scratch / "mailbox.jsonl"
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
            "DEE_CANDIDATES_DB_URL": url, "DEE_ENV": "local",
            "DEE_API_AUTH_KEY": ADMIN, "DEE_DB_MIGRATE_ON_BOOT": "true",
            "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
            "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "DEE_SESSION_LAST_SEEN_WRITE_SECONDS": "86400",
            "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
            "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(scratch)]),
            "NO_PROXY": "127.0.0.1,localhost", "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        args = {"connect_args": {"options": pg_options}} if pg_options else {}
        engine = create_engine(url, hide_parameters=True, **args)
        candidate_tables = {"resumes", "extractions", "reports", "profile_sources",
            "resume_fingerprints", "ml_feature_vectors", "consent_grants", "audit_log",
            "auth_sessions", "candidate_credentials", "interview_sessions", "interview_records",
            "evaluation_events", "coding_round_results", "observed_offers", "verifications",
            "data_principal_requests", "batch_items"}

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port, target="gate_app:app"), env=env,
                    cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(base, headers={"X-API-Key": ADMIN}) as admin:
                        assert wait_healthy(admin), "scratch application startup failed"
                        yield admin, proc
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=10)

        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()

        def login(person, email):
            require(person.post("/auth/candidate/signup", json={"email": email}), 202)
            return require(person.post("/auth/candidate/verify", json={
                "email": email, "code": _code_for(mailbox, email)}))["csrf_token"]

        def queue(admin, subject):
            return require(admin.get(f"/screening/batches/{subject['batch']}/queue",
                headers=subject["org_headers"]))["rows"][0]

        def snapshot(subject):
            """Full retained rows, never printed; compare before/after rollback."""
            cid = subject["cid"]
            with engine.connect() as conn:
                tables = ("candidates", "resumes", "extractions", "reports", "profile_sources",
                          "resume_fingerprints", "ml_feature_vectors", "consent_grants",
                          "audit_log", "auth_sessions", "candidate_credentials", "interview_sessions",
                          "interview_records", "evaluation_events", "coding_round_results",
                          "observed_offers", "verifications", "data_principal_requests")
                result = {}
                for table in tables:
                    key = "id" if table == "candidates" else "candidate_id"
                    result[table] = conn.execute(text(
                        f"SELECT * FROM {table} WHERE {key}=:cid ORDER BY id"), {"cid": cid}).all()
                result["curation"] = conn.execute(text("SELECT o.* FROM curation_observations o "
                    "JOIN profile_sources p ON p.id=o.source_id WHERE p.candidate_id=:cid ORDER BY o.id"),
                    {"cid": cid}).all()
                result["turns"] = conn.execute(text("SELECT t.* FROM interview_turns t "
                    "JOIN interview_sessions s ON s.id=t.session_id WHERE s.candidate_id=:cid ORDER BY t.id"),
                    {"cid": cid}).all()
                result["outcomes"] = conn.execute(text("SELECT o.* FROM outcomes o "
                    "JOIN reports r ON r.id=o.report_id WHERE r.candidate_id=:cid ORDER BY o.id"),
                    {"cid": cid}).all()
                result["verification_challenges"] = conn.execute(text("SELECT h.* FROM verification_challenges h "
                    "JOIN verifications v ON v.id=h.verification_id WHERE v.candidate_id=:cid ORDER BY h.id"),
                    {"cid": cid}).all()
                result["challenges"] = conn.execute(text("SELECT * FROM login_challenges "
                    "WHERE email_hash=(SELECT email_hash FROM candidates WHERE id=:cid) ORDER BY id"),
                    {"cid": cid}).all()
                result["batch"] = conn.execute(text("SELECT * FROM batch_items WHERE id=:id"),
                    {"id": subject["item"]}).all()
                return result

        def gone(admin, subject):
            require(admin.get(f"/candidates/{subject['cid']}"), 404)
            require(admin.get(f"/report/{subject['report']}"), 404)
            require(admin.get(f"/candidates/{subject['cid']}/sources"), 404)
            require(subject["person"].get("/portal/me"), 401)
            state = snapshot(subject)
            assert all(not rows for table, rows in state.items() if table != "batch")
            with engine.connect() as conn:
                # Inspect saved child IDs directly: joins to erased parents alone
                # would hide an orphan if a cascade were accidentally removed.
                for table, ids in subject["owned_children"].items():
                    statement = text(f"SELECT count(*) FROM {table} WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True))
                    assert conn.scalar(statement, {"ids": ids}) == 0, table
                assert conn.scalar(text("SELECT count(*) FROM login_challenges WHERE email_hash=:hash"),
                    {"hash": subject["email_hash"]}) == 0
                assert conn.scalar(text("SELECT count(*) FROM login_issuances WHERE email_hash=:hash"),
                    {"hash": subject["email_hash"]}) == 0
                row = conn.execute(text("SELECT raw_text,text_sha256,candidate_id,resume_id,report_id,risk_score "
                    "FROM batch_items WHERE id=:id"), {"id": subject["item"]}).one()
                assert tuple(row) == ("", "", None, None, None, subject["completed_score"])
                assert conn.scalar(text("SELECT count(*) FROM screening_item_inputs WHERE id=:id"),
                    {"id": subject["item"]}) == 0
            row = queue(admin, subject)
            assert row["status"] == "done" and row["candidate_id"] is row["report_id"] is None
            retry = require(admin.post(f"/screening/batches/{subject['batch']}/retry",
                headers=subject["org_headers"]))
            assert retry["requeued"] == 0
            assert require(admin.post(f"/screening/batches/{subject['batch']}/process",
                headers=subject["org_headers"]))["processed"] == 0

        def erase(admin, subject, door):
            actor = subject["person"] if door == "portal" else admin
            path = "/portal/me" if door == "portal" else f"/candidates/{subject['cid']}"
            return actor.delete(path, headers={"X-CSRF-Token": subject["csrf"]})

        subjects = []
        try:
            with server() as (admin, _):
                checks.check("migrated app starts with disabled external providers", True)
                schema = inspect(engine)
                actual_candidate_tables = {table for table in schema.get_table_names()
                    if any(fk["referred_table"] == "candidates" for fk in schema.get_foreign_keys(table))}
                assert actual_candidate_tables == candidate_tables, actual_candidate_tables ^ candidate_tables
                orgs = [require(admin.post("/ledger/orgs", json={"name": f"Synthetic tenant {n}"}))
                        for n in range(2)]
                for index, name in enumerate(("PortalErase", "AdminErase", "KeeperOne", "KeeperTwo")):
                    email = name.lower() + "@example.in"
                    resume = (f"{name}\nEmail: {email}\nEXPERIENCE\nEngineer, Acme (2020 - Present)\n"
                              "SKILLS\nPython, Spark\nBuilt ingestion pipelines and measured latency.\n"
                              + " ".join(f"synthetic{i}" for i in range(90)))
                    org_headers = {"X-Org-Key": orgs[index % 2]["api_key"]}
                    batch = require(admin.post("/screening/batches", headers=org_headers, json={
                        "name": name, "domain": "genai", "items": [{"resume_text": resume}]}))["id"]
                    assert require(admin.post(f"/screening/batches/{batch}/process",
                        headers=org_headers))["processed"] == 1
                    row = require(admin.get(f"/screening/batches/{batch}/queue", headers=org_headers))["rows"][0]
                    cid = row["candidate_id"]
                    assert cid and row["report_id"]
                    person = client(base)
                    csrf = login(person, email)
                    assert require(person.get("/portal/me"))["candidate_id"] == cid
                    key = require(admin.post(f"/candidates/{cid}/auth-key"))["access_key"]
                    require(admin.post(f"/candidates/{cid}/sources/linkedin", json=export([
                        "Shared pending", "Private " + name, "Approval input"])))
                    require(admin.post(f"/ledger/candidates/{cid}/consent", json={"purpose": "ledger_read"}))
                    require(admin.post(f"/ledger/candidates/{cid}/consent", json={"purpose": "ledger_write"}))
                    now = datetime.now(timezone.utc).isoformat()
                    record = require(admin.post("/ledger/records", headers=org_headers, json={
                        "candidate_id": cid, "stage": "tech", "outcome": "advanced",
                        "interviewed_at": now, "summary": "Synthetic retained interview summary"}))
                    require(admin.post(f"/ledger/records/{record['id']}/events", headers=org_headers,
                        json={"event_type": "synthetic_note", "payload": {"note": "Synthetic retained event"}}))
                    require(admin.post("/ledger/coding-rounds", headers=org_headers, json={
                        "candidate_id": cid, "platform": "internal", "score": 70, "taken_at": now,
                        "assessment_name": "Synthetic assessment", "raw": {"note": "Synthetic coding detail"}}))
                    require(admin.post("/ledger/offers", headers=org_headers, json={
                        "candidate_id": cid, "role_family": "backend_engineer", "seniority": "senior",
                        "city_tier": "metro", "ctc_fixed": 2000000, "offered_at": now}))
                    require(admin.post(f"/report/{row['report_id']}/outcome", json={
                        "outcome": "inconclusive", "notes": "Synthetic retained outcome note"}))
                    require(person.post("/portal/verifications", headers={"X-CSRF-Token": csrf},
                        json={"method": "otp_email", "destination": email}))
                    require(person.post("/portal/grievances", headers={"X-CSRF-Token": csrf},
                        json={"note": "Synthetic retained grievance"}))
                    interview = require(person.post("/portal/interviews", json={}, headers={"X-CSRF-Token": csrf}))
                    sid = interview["session"]["id"]
                    require(person.post(f"/portal/interviews/{sid}/answers", headers={"X-CSRF-Token": csrf},
                        json={"question_id": interview["next_question"]["id"], "text":
                              "I measured latency before batching, compared results, and checked failures with the team."}))
                    finished = require(person.post(f"/portal/interviews/{sid}/finish", headers={"X-CSRF-Token": csrf}))
                    assert finished["session"]["assessment"]["human_review_required"]
                    # Seed every pending challenge scope through the reused synthetic hook.
                    require(admin.post("/_test/stale-redemption", params={"email": email, "plane": "candidate"}))
                    stale_code = _code_for(mailbox, email)
                    require(admin.post("/_test/scopes", params={"email": email}))
                    with engine.connect() as conn:
                        email_hash = conn.scalar(text("SELECT email_hash FROM candidates WHERE id=:cid"), {"cid": cid})
                        completed_score = conn.scalar(text("SELECT risk_score FROM batch_items WHERE id=:id"),
                            {"id": row["item_id"]})
                    subjects.append(dict(cid=cid, email=email, email_hash=email_hash, person=person,
                        csrf=csrf, key=key, resume=resume, resume_id=row["resume_id"], report=row["report_id"],
                        item=row["item_id"], batch=batch, org_headers=org_headers, stale_code=stale_code,
                        completed_score=completed_score))
                    require(admin.get(f"/screening/batches/{batch}/queue",
                        headers={"X-Org-Key": orgs[(index + 1) % 2]["api_key"]}), 404)
                materialized = require(admin.post("/features/materialize", json={}))
                assert materialized["materialized"] == 4
                receipt = require(admin.post("/curation/skills/resolve", json={"norm_key": "approval input",
                    "expected_revision": next(t["review_revision"] for t in require(admin.get("/curation/skills/unmapped"))["terms"] if t["norm_key"] == "approval input"),
                    "action": "map", "alias": "Explicit approved", "canonical": "python", "category": "language"}))
                assert receipt["alias"] == "Explicit approved" and "norm_key" not in receipt
                for subject in subjects:
                    state = snapshot(subject)
                    assert all(state.values()), [table for table, rows in state.items() if not rows]
                    subject["owned_children"] = {table: [row.id for row in state[key]]
                        for key, table in (("curation", "curation_observations"),
                            ("turns", "interview_turns"), ("outcomes", "outcomes"),
                            ("verification_challenges", "verification_challenges"))}
                checks.check("two tenants seed every candidate-owned SQL sink and child content; foreign queues refused", True)
                # Deleting one resume version leaves its independent report and candidate alive.
                survivor = subjects[-1]
                require(admin.delete(f"/candidates/{survivor['cid']}/resumes/{survivor['resume_id']}"))
                require(admin.get(f"/report/{survivor['report']}"))
                require(survivor["person"].get("/portal/me"))
                checks.check("resume-only deletion preserves independent report and portal lifetime", True)

            survivor_states = [snapshot(s) for s in subjects[2:]]
            for door, subject in zip(("portal", "admin"), subjects[:2]):
                baseline = snapshot(subject)
                with server() as (admin, _):
                    require(admin.post("/_test/cleanup-mode", params={"mode": "failure"}))
                    assert erase(admin, subject, door).status_code == 500
                    assert snapshot(subject) == baseline
                    checks.check(f"{door}: failed deletion rolls back candidate/cascades/challenges/screening", True)
                with server() as (admin, proc):
                    require(admin.post("/_test/cleanup-mode", params={"mode": "crash_before_commit"}))
                    try:
                        erase(admin, subject, door)
                    except httpx.TransportError:
                        pass
                    else:
                        raise AssertionError("crashed worker returned a response")
                    assert proc.wait(timeout=15) == 76
                    assert snapshot(subject) == baseline
                    checks.check(f"{door}: actual process death after DELETE rolls back complete state", True)
                with server() as (admin, _):
                    assert require(subject["person"].get("/portal/me"))["candidate_id"] == subject["cid"]
                    result = require(erase(admin, subject, door))
                    assert result == {"candidate_id": subject["cid"], "deleted": True, "reports_deleted": 1}
                    gone(admin, subject)
                    require(admin.get("/portal/me", headers={"X-Candidate-Key": subject["key"]}), 401)
                    refused = subject["person"].post("/auth/candidate/verify", json={
                        "email": subject["email"], "code": subject["stale_code"]})
                    assert refused.status_code == 400 and "set-cookie" not in refused.headers
                    retry = require(admin.post("/features/materialize", json={"candidate_ids": [subject["cid"]]}))
                    assert (retry["materialized"], retry["skipped"]) == (0, 1)
                    checks.check(f"{door}: retry erases target, old credentials/codes and stale work refuse", True)
                with server() as (admin, _):
                    gone(admin, subject)
                    assert [snapshot(s) for s in subjects[2:]] == survivor_states
                    for survivor in subjects[2:]:
                        require(survivor["person"].get("/portal/me"))
                        require(admin.get(f"/report/{survivor['report']}"))
                    terms = require(admin.get("/curation/skills/unmapped"))["terms"]
                    shared = next(t for t in terms if t["norm_key"] == "shared pending")
                    assert shared["occurrences"] == 3 - (door == "admin")
                    assert not any(t["norm_key"] == "private " + subject["email"].split("@")[0] for t in terms)
                    checks.check(f"{door}: restart preserves survivor rows and recomputes owned queue", True)

            with server() as (admin, proc):
                # A commit can survive an interrupted HTTP response; deletion retry is then a 404.
                require(admin.post("/_test/cleanup-mode", params={"mode": "crash_after_commit"}))
                try:
                    erase(admin, subjects[2], "admin")
                except httpx.TransportError:
                    pass
                else:
                    raise AssertionError("post-commit worker returned a response")
                assert proc.wait(timeout=15) == 77
            with server() as (admin, _):
                gone(admin, subjects[2])
                require(admin.delete(f"/candidates/{subjects[2]['cid']}"), 404)
                checks.check("committed erasure survives lost HTTP response; repeated deletion refuses", True)
                with engine.connect() as conn:
                    assert conn.scalar(text("SELECT count(*) FROM curation_aliases WHERE norm_key='explicit approved'")) == 1
                checks.check("explicit approved vocabulary survives contributor erasure and restart", True)
                # A fresh submission is permitted; old work cannot resurrect its original IDs.
                subject = subjects[0]
                new_csrf = login(subject["person"], subject["email"])
                fresh_id = require(subject["person"].get("/portal/me"))["candidate_id"]
                assert fresh_id != subject["cid"] and new_csrf
                fresh = require(admin.post("/screening/candidates", headers=subject["org_headers"],
                    json={"resume_text": subject["resume"], "evaluate": False}))
                assert fresh["candidate_id"] == fresh_id and fresh["resume_id"] != subject["resume_id"]
                signal = require(admin.post(f"/candidates/{fresh_id}/sources/linkedin", json=export(["Explicit approved"])))
                assert signal["skills"][0]["canonical"] == "python"
                checks.check("fresh signup/upload allowed; approved normalization reloads; original IDs stay absent", True)
                require(admin.get(f"/candidates/{subject['cid']}"), 404)
                assert snapshot(subjects[3]) == survivor_states[1]
            assert not (scratch / "flywheel.jsonl").exists()
            checks.check("production composition writes no unmanaged flywheel copy", True)
        finally:
            for subject in subjects:
                subject["person"].close()
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
