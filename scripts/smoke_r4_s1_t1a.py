"""Production SQL composition/HTTP/graceful restart on migrated scratch stores.

External providers are fake. --postgres owns an isolated disposable test schema.
The child uses uvicorn's normal shutdown, not Windows TerminateProcess, so SQL
disposal events are actual lifespan evidence. No provider-client cleanup claim.
"""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

from sqlalchemy import event, text

from _smoke import Smoke, base_env, client, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-shared-sql-admin"
RANKING = {"terms": [{"feature": "candidate.num_skills", "weight": 1},
    {"feature": "reputation.score", "weight": 1}]}


def create_smoke_app():
    from smoke_r2_s2_t1 import create_smoke_app as fake_app
    app = fake_app()  # Existing fake clients; actual default SQL composition.
    original = app.router.lifespan_context
    path = Path(os.environ["VERITAS_SQL_SMOKE_EVENTS"])
    def record(kind, **data):
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"event": kind, **data}) + "\n")
    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            svc = app.state.services
            stores = [svc.candidates, svc.ledger, svc.report_store, svc.features, svc.jobs,
                svc.profile_sources._store, svc.curation._store, svc.auth._store,
                svc.verification._store, svc.interview._store, svc.screening._store, svc.rights._store]
            stores.extend(getattr(svc, name)._limiter._store for name in ("auth", "interview", "screening", "rights"))
            engine = svc.session_factory.kw["bind"]
            event.listen(engine, "engine_disposed", lambda engine: record("disposed"))
            event.listen(engine, "close", lambda connection, row: record("connection_closed"))
            with svc.session_factory() as session:
                revision = session.scalar(text("SELECT version_num FROM alembic_version"))
            record("started", one_factory=all(s._session_factory is svc.session_factory for s in stores),
                reused=svc.dashboard._jobs is svc.jobs and svc.dashboard._comp is svc.comp
                and svc.comp._ledger is svc.ledger and svc.jobs._features is svc.features
                and svc.jobs._candidates is svc.candidates, revision=revision)
            yield
        record("stopped", detached=app.state.services is None and app.state.engine is None)
    app.router.lifespan_context = lifespan
    return app


async def serve(port, stop):
    import importlib
    import uvicorn
    factory = create_smoke_app
    if target := os.environ.get("VERITAS_SQL_SMOKE_FACTORY"):
        module, name = target.split(":", 1)
        factory = getattr(importlib.import_module(module), name)
    server = uvicorn.Server(uvicorn.Config(factory(), host="127.0.0.1", port=port, log_level="warning"))
    async def watch():
        while not stop.exists(): await asyncio.sleep(.05)
        server.should_exit = True
    watcher = asyncio.create_task(watch())
    try: await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def main(*, provider_checks=False, composition_checks=False):
    checks = Smoke("R4-S1-Q combined production composition / graceful restart" if composition_checks
                   else "R4-S1-T1B owned providers / HTTP / graceful restart" if provider_checks
                   else "R4-S1-T1A shared production SQL / HTTP / graceful restart")
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t1a-"))
    print(f"Synthetic SQL lifecycle evidence: {scratch}", flush=True)
    stop, events = scratch/"stop", scratch/"lifecycle.jsonl"
    with database(scratch) as (url, pg_options):
        env = {k:v for k,v in base_env().items() if not k.startswith("DEE_")}
        env.update({"DEE_CONFIG_FILE":str(scratch/"no-config.yaml"), "DEE_ENV":"local",
            "DEE_CANDIDATES_DB_URL":url, "DEE_DB_MIGRATE_ON_BOOT":"true", "DEE_API_AUTH_KEY":ADMIN,
            "DEE_OPENROUTER_API_KEY":"", "DEE_LLM_MAX_RETRIES":"0", "DEE_GITHUB_TOKEN":"",
            "DEE_GITHUB_API_BASE":"http://127.0.0.1:9", "DEE_EMAIL_PROVIDER":"capture",
            "DEE_EMAIL_CAPTURE_PATH":str(scratch/"mail.jsonl"), "DEE_VECTORSTORE_BACKEND":"memory",
            "DEE_FLYWHEEL_PATH":str(scratch/"flywheel.jsonl"), "DEE_LOGIN_OTP_DEBUG_ECHO":"false",
            "DEE_LOGIN_OTP_STATIC_CODE":"", "DEE_VERIF_OTP_DEBUG_ECHO":"false",
            "DEE_SESSION_COOKIE_SECURE":"false", "DEE_SESSION_COOKIE_SAMESITE":"lax",
            "PGOPTIONS":pg_options, "NO_PROXY":"127.0.0.1,localhost",
            "VERITAS_SQL_SMOKE_EVENTS":str(events),
            "PYTHONPATH":os.pathsep.join(str(p) for p in (ROOT/"src", ROOT/"scripts", ROOT))})
        if provider_checks:
            env["VERITAS_SQL_SMOKE_FACTORY"] = "smoke_r4_s1_t1b:create_smoke_app"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0)); port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        @contextmanager
        def server():
            stop.unlink(missing_ok=True)
            with (scratch/"server.log").open("a",encoding="utf-8") as log:
                proc = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--serve",str(port),str(stop)],
                    cwd=scratch, env=env, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(base,headers={"X-API-Key":ADMIN}) as admin:
                        assert wait_healthy(admin), "owned app failed to start"
                        yield admin
                finally:
                    stop.write_text("stop",encoding="utf-8")
                    try: proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        proc.terminate(); proc.wait(timeout=10)
                        raise AssertionError("owned app failed graceful SQL shutdown")
                    assert proc.returncode == 0, "owned app failed during lifespan"
        def require(response,status=200):
            assert response.status_code == status, (response.request.url.path,response.status_code)
            return response.json()
        def surface():
            with client(base) as public:
                schema = require(public.get("/openapi.json"))
                expected = json.loads((ROOT/"tests/fixtures/api_contract_r4_s1_t3.json").read_text())
                operations = sum(method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
                    for methods in schema["paths"].values() for method in methods)
                checks.check("production HTTP publishes the complete API operation surface", operations==expected["operations"])
                page = public.get("/ui/")
                assert page.status_code == 200
                checks.check("production HTTP serves the actual extracted entry document",
                    page.content==(ROOT/"frontend/Veritas.dc.html").read_bytes())
                scripts = re.findall(r'<script\s+src="(\./[^"]+)"', page.text)
                assert len(scripts) >= 8, "extracted screen scripts missing from entry document"
                for source in scripts:
                    response = public.get("/ui/" + source.removeprefix("./"))
                    checks.check("production HTTP serves " + source, response.status_code==200
                        and "javascript" in response.headers.get("content-type", "")
                        and response.content==(ROOT/"frontend"/source.removeprefix("./")).read_bytes())
                checks.check("production HTTP refuses anonymous access to protected planes",
                    all(public.get(path).status_code==401 for path in
                        ("/portal/me", "/admin/users", "/ledger/orgs", "/curation/skills/unmapped"))
                    and public.post("/talent/search", json={"ranking":RANKING}).status_code==401)
                checks.check("production HTTP refuses private and retired UI assets",
                    all(public.get("/ui/"+name).status_code==404 for name in
                        (".env", "config.yaml", "src/app/main.py", "design-system.js")))
                return schema
        def search(admin,cut):
            return require(admin.post("/talent/search",json={"as_of":cut,"ranking":RANKING,
                "filters":[{"feature":"reputation.score","op":"exists"}]}))
        def exercise_providers(admin, actor):
            report = require(admin.post("/evaluate", json={"resume_text":document,
                "domain":"data_eng", "github_url":"https://github.com/synthetic/repo"}))
            body = require(actor.post("/portal/interviews", json={"domain":"data_eng"}))
            sid = body["session"]["id"]
            answer = require(actor.post(f"/portal/interviews/{sid}/answers", json={
                "question_id":body["next_question"]["id"], "audio_b64":"AAAA", "mime":"audio/wav"}))
            done = require(actor.post(f"/portal/interviews/{sid}/finish", json={}))["session"]
            checks.check("owned provider wrappers serve real evaluation and audio routes", report["advisory"]
                and answer["session"]["turns"][0]["channel"]=="audio" and done["assessment"]["human_review_required"])
        with client(base) as actor, client(base) as survivor, client(base) as org_a, client(base) as org_b:
            with server() as admin:
                if composition_checks: initial_schema = surface()
                orgs = [require(admin.post("/ledger/orgs",json={"name":"Shared SQL " + name})) for name in ("A","B")]
                for http,org in zip((org_a,org_b),orgs): http.headers["X-Org-Key"] = org["api_key"]
                document = "Synthetic SQL Candidate\nEmail: shared-sql@example.com\nEXPERIENCE\nEngineer at Acme, 2020 - 2024\nSKILLS\nPython, SQL, Spark"
                report = require(admin.post("/evaluate",json={"resume_text":document,"domain":"data_eng"}))
                checks.check("production evaluation remains advisory with deterministic fake model", report["advisory"] and report["human_review_required"])
                upload = require(org_a.post("/screening/candidates",json={"resume_text":document,"domain":"data_eng"}))
                cid, saved_report = upload["candidate_id"], upload["report"]
                rid = saved_report["id"]
                other = require(admin.post("/candidates",json={"evaluate":False,"resume_text":"Synthetic Survivor\nEmail: sql-survivor@example.com\nSKILLS\nPython, SQL"}))["candidate_id"]
                for http,subject in ((actor,cid),(survivor,other)):
                    http.headers["X-Candidate-Key"] = require(admin.post(f"/candidates/{subject}/auth-key"))["access_key"]
                checks.check("shared composition preserves both portal subjects", require(actor.get("/portal/me"))["candidate_id"]==cid
                    and require(survivor.get("/portal/me"))["candidate_id"]==other and cid!=other)
                if provider_checks: exercise_providers(admin, actor)
                checks.check("report ownership remains scoped across the shared pool", require(org_a.get(f"/screening/reports/{rid}"))==saved_report
                    and org_b.get(f"/screening/reports/{rid}").status_code==404)
                oid = orgs[0]["org"]["id"]
                require(admin.post(f"/ledger/candidates/{cid}/consent",json={"purpose":"ledger_write","org_id":oid}))
                grant = require(actor.post("/portal/consents",json={"purpose":"ledger_read","org_id":oid}))
                require(org_a.post("/ledger/records",json={"candidate_id":cid,"stage":"hm","outcome":"hired",
                    "interviewed_at":(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}))
                batch = require(admin.post("/features/materialize",json={}))
                cut = batch["as_of"]
                checks.check("materialization and consent-gated search see shared saved data", batch["materialized"]==2 and search(admin,cut)["filtered_size"]==1)
                job = require(org_a.post("/jobs",json={"title":"Shared SQL Engineer","must_have_skills":["python"]}))
                checks.check("job service works and refuses another employer", org_a.post(f"/jobs/{job['id']}/match",json={}).status_code==200
                    and org_b.post(f"/jobs/{job['id']}/match",json={}).status_code==404)
            rows = [json.loads(line) for line in events.read_text().splitlines()]
            checks.check("first real shutdown disposes one owned pool and its DBAPI connection", sum(r["event"]=="disposed" for r in rows)==1
                and any(r["event"]=="connection_closed" for r in rows) and rows[-1]=={"event":"stopped","detached":True})
            with server() as admin:
                if composition_checks:
                    checks.check("graceful restart preserves the complete HTTP OpenAPI document", surface()==initial_schema)
                checks.check("graceful process restart preserves report, portal and search", require(org_a.get(f"/screening/reports/{rid}"))==saved_report
                    and require(actor.get("/portal/me"))["candidate_id"]==cid and search(admin,cut)["filtered_size"]==1)
                if provider_checks: exercise_providers(admin, actor)
                require(actor.post(f"/portal/consents/{grant['id']}/revoke"))
                checks.check("current consent revocation still masks historical search", search(admin,cut)["filtered_size"]==0)
                require(actor.delete("/portal/me"))
                checks.check("erasure revokes subject and report without affecting survivor", actor.get("/portal/me").status_code==401
                    and org_a.get(f"/screening/reports/{rid}").status_code==404
                    and require(survivor.get("/portal/me"))["candidate_id"]==other)
            rows = [json.loads(line) for line in events.read_text().splitlines()]
            starts = [r for r in rows if r["event"]=="started"]
            checks.check("each migrated production lifespan shares factory and store/service instances", len(starts)==2
                and all(r["one_factory"] and r["reused"] and r["revision"]=="0029_candidate_login_binding" for r in starts))
            checks.check("both graceful lifespans dispose and detach owned SQL resources", sum(r["event"]=="disposed" for r in rows)==2
                and sum(r["event"]=="stopped" and r["detached"] for r in rows)==2)
            if provider_checks:
                spans, span = [], []
                for row in rows:
                    span.append(row)
                    if row["event"] == "stopped": spans.append(span); span = []
                checks.check("each graceful lifespan closes every opened owned HTTP transport exactly once", len(spans)==2
                    and all(sorted(r["provider"] for r in part if r["event"]=="provider_opened")==["github","llm","speech"]
                        and sorted(r["provider"] for r in part if r["event"]=="provider_closed" and r["closed"])==["github","llm","speech"]
                        for part in spans))
            if composition_checks:
                provenance = [r for r in rows if r["event"]=="provenance_runtime"]
                checks.check("both owned-provider lifespans avoid Chroma under default and retired settings",
                    [r["mode"] for r in provenance]==["default", "legacy"]
                    and all(r["chroma_import_attempts"]==r["vector_threads"]==0 for r in provenance))
            logs = (scratch/"server.log").read_text(encoding="utf-8",errors="replace")
            checks.check("lifecycle/app logs omit resume text and candidate keys", document not in logs
                and actor.headers["X-Candidate-Key"] not in logs and survivor.headers["X-Candidate-Key"] not in logs)
    return checks.summary()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        asyncio.run(serve(int(sys.argv[2]),Path(sys.argv[3])))
    else: raise SystemExit(main())
