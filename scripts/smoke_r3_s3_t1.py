"""Versioned content rubric on migrated scratch HTTP/restart with fake providers.

SQLite by default; --postgres uses an explicitly disposable DEE_TEST_DB_URL.
Frozen synthetic question fixtures exercise the rubric, not representative quality.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, select, text, update
from datetime import datetime, timedelta, timezone

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from app.interview.scoring import SCORER_VERSION

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-interview-rubric-admin"
RUBRIC = json.loads((ROOT/"tests/fixtures/interview_rubric_v2.json").read_text(encoding="utf-8"))


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s3-t1-http-"))
    print(f"Synthetic interview evidence: {scratch}", flush=True)
    checks = Smoke("R3-S3 content rubric / atomic lifecycle / actor denials")
    mailbox = scratch/"mail.jsonl"
    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
            "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_LLM_MAX_RETRIES": "0", "DEE_GITHUB_TOKEN": "", "DEE_DB_MIGRATE_ON_BOOT": "true",
            "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "capture",
            "DEE_EMAIL_CAPTURE_PATH": str(mailbox), "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_SPEECH_PROVIDER": "local", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
            "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_VERIF_OTP_DEBUG_ECHO": "false",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "PGOPTIONS": pg_options, "NO_PROXY": "127.0.0.1,localhost",
            "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r3_s1_t2:create_smoke_app") + ["--factory"],
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(base, headers={"X-API-Key": ADMIN}) as admin:
                        assert wait_healthy(admin), "scratch app failed to start"
                        yield admin
                finally:
                    proc.terminate()
                    try: proc.wait(timeout=15)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)

        engine = create_engine(url, hide_parameters=True,
            connect_args={"options": pg_options} if pg_options else {})
        try:
            with client(base) as actor, client(base) as other, client(base) as org_actor:
                with server() as admin:
                    with engine.connect() as db:
                        checks.check("actual app migrated to current head", db.scalar(text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
                    ids = [require(admin.post("/candidates", json={"evaluate": False,
                        "resume_text": f"Synthetic Interview {i}\nEmail: interview-{i}@example.com\nEXPERIENCE\nEngineer at Acme, 2020 - 2024\nSKILLS\nPython, SQL, Spark"}))["candidate_id"] for i in range(2)]
                    for http, cid in zip((actor, other), ids):
                        http.headers["X-Candidate-Key"] = require(admin.post(f"/candidates/{cid}/auth-key"))["access_key"]
                    cid = ids[0]

                    def start(*, signals=None):
                        body = require(actor.post("/portal/interviews", json={}))
                        sid = body["session"]["id"]
                        questions = body["session"]["questions"][:3]
                        assert len(questions) == 3
                        # Explicit synthetic question fixtures, not a planner-quality claim.
                        for q in questions:
                            q.update(text=RUBRIC["question"], expected_signals=RUBRIC["signals"] if signals is None else signals)
                        with engine.begin() as db:
                            db.execute(update(InterviewSessionRow).where(InterviewSessionRow.id == sid).values(planned_questions=questions))
                        return sid, questions

                    def answer(sid, question, text_value):
                        return require(actor.post(f"/portal/interviews/{sid}/answers",
                            json={"question_id": question["id"], "text": text_value}))["session"]

                    sid, questions = start()
                    checks.check("foreign candidate cannot read, answer or finish owned session",
                        other.get(f"/portal/interviews/{sid}").status_code == 404
                        and other.post(f"/portal/interviews/{sid}/finish", json={}).status_code == 404
                        and other.post(f"/portal/interviews/{sid}/answers", json={"question_id": questions[0]["id"], "text": "private"}).status_code == 404)
                    checks.check("duplicate start and future question refuse without advancing",
                        actor.post("/portal/interviews", json={}).status_code == 409
                        and actor.post(f"/portal/interviews/{sid}/answers", json={"question_id": questions[-1]["id"], "text": "private"}).status_code == 409
                        and len(require(actor.get(f"/portal/interviews/{sid}"))["session"]["turns"]) == 0)
                    for q in questions:
                        bad = answer(sid, q, "I Python 123 retrieval " * 20)
                        checks.check("saved answer cannot be duplicated", actor.post(f"/portal/interviews/{sid}/answers",
                            json={"question_id": q["id"], "text": "private"}).status_code == 409)
                    checks.check("completed session has no next question or second finish",
                        require(actor.get(f"/portal/interviews/{sid}"))["next_question"] is None
                        and actor.post(f"/portal/interviews/{sid}/finish", json={}).status_code == 409)
                    checks.check("real HTTP repeated-keyword exploit has no strong band/confidence",
                        bad["assessment"]["band"] == "insufficient_signal" and bad["assessment"]["confidence"] == 0
                        and all(t["score"]["insufficient"] for t in bad["turns"]))
                    checks.check("new turn and assessment versions persist through HTTP",
                        bad["assessment"]["scorer_version"] == SCORER_VERSION
                        and all(t["score"]["scorer_version"] == SCORER_VERSION for t in bad["turns"]))

                    native_start = require(actor.post("/portal/interviews", json={}))
                    native_id, next_question = native_start["session"]["id"], native_start["next_question"]
                    while next_question is not None:
                        body = require(actor.post(f"/portal/interviews/{native_id}/answers", json={
                            "question_id": next_question["id"], "text": RUBRIC["cases"][6]["text"]}))
                        native, next_question = body["session"], body["next_question"]
                    checks.check("actual profile/domain plan refuses unrelated fluent content", native["assessment"]["band"] == "insufficient_signal"
                        and native["assessment"]["confidence"] == 0)

                    good_id, questions = start()
                    for q in questions:
                        good = answer(good_id, q, RUBRIC["cases"][0]["text"])
                    checks.check("concise reasoned HTTP answers remain usable/advisory",
                        good["assessment"]["band"] in ("solid", "deep") and good["assessment"]["confidence"] >= .5
                        and good["assessment"]["advisory"] and good["assessment"]["human_review_required"])
                    empty_id, questions = start(signals=[])
                    for q in questions:
                        empty = answer(empty_id, q, RUBRIC["cases"][6]["text"])
                    checks.check("absent yardstick cannot rescue unrelated HTTP content", empty["assessment"]["band"] == "insufficient_signal"
                        and all(t["score"]["dimensions"]["depth"] == .5 and "relevance_unconfirmed" in t["score"]["codes"] for t in empty["turns"]))
                    partial_id, questions = start()
                    answer(partial_id, questions[0], RUBRIC["cases"][1]["text"])
                    partial = require(actor.post(f"/portal/interviews/{partial_id}/finish", json={}))["session"]
                    evidence_id, questions = start()
                    for q, content in zip(questions, (RUBRIC["cases"][1]["text"], RUBRIC["cases"][6]["text"],
                            "I compared restored cut tokenizer regression." * 20)):
                        evidence = answer(evidence_id, q, content)
                    checks.check("unsupported/padded HTTP turns change progress without inflating evidence",
                        evidence["assessment"]["coverage"] == 1 and partial["assessment"]["coverage"] < 1
                        and evidence["assessment"]["confidence"] == partial["assessment"]["confidence"]
                        and evidence["assessment"]["dimensions"] == partial["assessment"]["dimensions"])
                    historical_id, questions = start()
                    first = answer(historical_id, questions[0], RUBRIC["cases"][1]["text"])
                    historical_turn_id = first["turns"][0]["id"]
                    require(actor.post(f"/portal/interviews/{historical_id}/finish", json={}))
                    legacy_score = {"dimensions": dict.fromkeys(("specificity", "ownership", "depth", "consistency"), 1.0), "insufficient": False, "codes": []}
                    legacy = {**good["assessment"], "session_id": historical_id, "scorer_version": "s73.1", "overall": 1.0, "band": "deep"}
                    with engine.begin() as db:
                        db.execute(update(InterviewSessionRow).where(InterviewSessionRow.id == historical_id).values(assessment=legacy, scorer_version="s73.1"))
                        db.execute(update(InterviewTurnRow).where(InterviewTurnRow.id == historical_turn_id).values(scores=legacy_score))
                    checks.check("historical completion reads its original values", require(actor.get(f"/portal/interviews/{historical_id}"))["session"]["assessment"] == legacy)

                    mixed_id, questions = start()
                    first = answer(mixed_id, questions[0], RUBRIC["cases"][1]["text"])
                    with engine.begin() as db:
                        db.execute(update(InterviewTurnRow).where(InterviewTurnRow.id == first["turns"][0]["id"]).values(scores=legacy_score))
                    for q in questions[1:]:
                        mixed = answer(mixed_id, q, RUBRIC["cases"][1]["text"])
                    checks.check("mixed versions persist safely without a confident blend", mixed["assessment"]["scorer_version"] == "mixed/unknown"
                        and mixed["assessment"]["band"] == "insufficient_signal" and mixed["assessment"]["dimensions"] == {} and mixed["assessment"]["confidence"] == 0)
                    checks.check("candidate summaries expose versions without raw answers", {s["scorer_version"] for s in require(actor.get("/portal/interviews"))["interviews"]} == {"s73.1", SCORER_VERSION, "mixed/unknown"})
                    org = require(admin.post("/ledger/orgs", json={"name": "Synthetic interview reader"}))
                    org_actor.headers["X-Org-Key"] = org["api_key"]
                    path = f"/interview/candidates/{cid}/assessments"
                    checks.check("org requires current interview consent", org_actor.get(path).status_code == 403)
                    grant = require(admin.post(f"/ledger/candidates/{cid}/consent", json={"purpose": "interview_read", "org_id": org["org"]["id"]}))
                    org_view = org_actor.get(path)
                    checks.check("org receives versioned summaries without transcript/turns", org_view.status_code == 200
                        and len(org_view.json()["assessments"]) == 8 and "transcript" not in org_view.text and "turns" not in org_view.text
                        and {a["scorer_version"] for a in org_view.json()["assessments"]} == {"s73.1", SCORER_VERSION, "mixed/unknown"})

                    expired = require(actor.post("/portal/interviews", json={}))
                    expired_id = expired["session"]["id"]
                    with engine.begin() as db:
                        db.execute(update(InterviewSessionRow).where(InterviewSessionRow.id == expired_id)
                            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
                    expired_view = require(actor.get(f"/portal/interviews/{expired_id}"))
                    checks.check("expiry refuses answer/finish and removes next question",
                        expired_view["session"]["status"] == "abandoned" and expired_view["next_question"] is None
                        and actor.post(f"/portal/interviews/{expired_id}/answers", json={
                            "question_id": expired["next_question"]["id"], "text": "private"}).status_code == 409
                        and actor.post(f"/portal/interviews/{expired_id}/finish", json={}).status_code == 409)
                    resumed = require(actor.post("/portal/interviews", json={}))
                    resume_id = resumed["session"]["id"]
                    resumed = require(actor.post(f"/portal/interviews/{resume_id}/answers", json={
                        "question_id": resumed["next_question"]["id"], "text": RUBRIC["cases"][0]["text"]}))

                with server() as admin:
                    checks.check("real restart resumes saved question and refuses stale answer",
                        require(actor.get(f"/portal/interviews/{resume_id}")) == resumed
                        and resumed["next_question"]["sequence"] == 2
                        and actor.post(f"/portal/interviews/{resume_id}/answers", json={
                            "question_id": resumed["session"]["turns"][0]["question_id"], "text": "private"}).status_code == 409)
                    resumed_done = require(actor.post(f"/portal/interviews/{resume_id}/finish", json={}))
                    checks.check("resumed early finish persists exact assessment and no next question",
                        resumed_done == require(actor.get(f"/portal/interviews/{resume_id}"))
                        and resumed_done["next_question"] is None
                        and resumed_done["session"]["assessment"]["questions_answered"] == 1)
                    checks.check("real restart preserves new evidence and historical assessment", require(actor.get(f"/portal/interviews/{good_id}"))["session"] == good
                        and require(actor.get(f"/portal/interviews/{historical_id}"))["session"]["assessment"] == legacy
                        and require(actor.get(f"/portal/interviews/{mixed_id}"))["session"] == mixed)
                    with engine.connect() as db:
                        checks.check("reads/restart never rewrite historical score JSON", db.execute(select(InterviewSessionRow.assessment).where(InterviewSessionRow.id == historical_id)).scalar_one() == legacy
                            and db.execute(select(InterviewTurnRow.scores).where(InterviewTurnRow.id == historical_turn_id)).scalar_one() == legacy_score)
                    require(admin.post(f"/ledger/consent/{grant['id']}/revoke"))
                    checks.check("revocation refuses org summaries after restart", org_actor.get(path).status_code == 403)
                    require(admin.delete(f"/candidates/{cid}"))
                    checks.check("erasure revokes candidate access and removes interview content", actor.get(f"/portal/interviews/{good_id}").status_code == 401)
                    with engine.connect() as db:
                        checks.check("erasure removes all owned sessions and turns", db.execute(select(InterviewSessionRow.id).where(InterviewSessionRow.candidate_id == cid)).all() == []
                            and db.execute(select(InterviewTurnRow.id)).all() == [])
                    checks.check("other candidate remains authorized", other.get("/portal/interviews").status_code == 200)
                logged = (scratch/"server.log").read_text(encoding="utf-8")
                checks.check("server logs omit submitted interview text", RUBRIC["cases"][0]["text"] not in logged and "I Python 123 retrieval" not in logged)
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
