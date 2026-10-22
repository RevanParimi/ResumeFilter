"""Microphone API on migrated scratch SQLite/PostgreSQL with fake ASR.

No real ASR/email/GitHub calls. Fake provider logs metadata only, never audio.
Browser device/codec mechanics are exercised separately by the Chrome journey.
--combined adds typed continuation and repeated-keyword acceptance for R3-S3-Q;
--postgres uses an explicitly disposable DEE_TEST_DB_URL.
"""
import asyncio
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import sys

from sqlalchemy import create_engine, select, text

from _smoke import Smoke, base_env, client, wait_healthy
from smoke_r4_s1_t1a import serve
from app.services.speech import SpeechClient, SpeechFailed, SpeechUnavailable, Transcript
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ANSWER = "I compared the baseline and restored the parser because tokenization changed. I measured the result using a regression sample."


class ControlledSpeech(SpeechClient):
    @property
    def control(self):
        return Path(self.settings.email_capture_path + ".speech-control")

    def event(self, event, **metadata):
        with Path(str(self.control) + ".jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"event": event, **metadata}) + "\n")

    async def atranscribe(self, *, audio_b64, mime):
        self.event("start", mime=mime, chars=len(audio_b64),
            digest=hashlib.sha256(base64.b64decode(audio_b64)).hexdigest())
        mode = self.control.read_text() if self.control.exists() else "ok"
        for _ in range(200):
            if mode != "delay": break
            await asyncio.sleep(.05)
            mode = self.control.read_text()
        if mode == "unavailable":
            self.event("unavailable"); raise SpeechUnavailable("synthetic-private-provider-secret")
        if mode in {"failed", "delay"}:
            self.event("failed"); raise SpeechFailed("synthetic-private-provider-secret")
        self.event("complete")
        return Transcript(text="" if mode == "empty" else ANSWER * 400 if mode == "long" else ANSWER, duration_seconds=None, model="synthetic-asr")


def create_smoke_app():
    import app.services as services
    from smoke_r3_s1_t2 import create_smoke_app as base_app
    services.build_speech = lambda settings: ControlledSpeech(settings)
    return base_app()


def main():
    checks = Smoke("R3-S3-T3 audio HTTP/refusal/restart/privacy")
    scratch = Path(tempfile.mkdtemp(prefix="r3-s3-t3-http-"))
    print(f"Synthetic audio evidence: {scratch}", flush=True)
    with database(scratch) as (url, pg_options):
        return run(scratch, url, pg_options, checks, combined="--combined" in sys.argv)


def run(scratch, url, pg_options, checks, *, combined):
    mailbox = scratch/"mail.jsonl"
    stop = scratch/"stop"
    control = Path(str(mailbox) + ".speech-control")
    env = {k:v for k,v in base_env().items() if not k.startswith("DEE_")}
    env.update({"DEE_CONFIG_FILE":str(scratch/"no-config.yaml"), "DEE_ENV":"local", "DEE_CANDIDATES_DB_URL":url,
        "DEE_DB_MIGRATE_ON_BOOT":"true", "DEE_API_AUTH_KEY":"synthetic-audio-admin",
        "DEE_OPENROUTER_API_KEY":"", "DEE_GITHUB_TOKEN":"", "DEE_GITHUB_API_BASE":"http://127.0.0.1:9",
        "DEE_LLM_MAX_RETRIES":"0", "DEE_EMAIL_PROVIDER":"capture", "DEE_EMAIL_CAPTURE_PATH":str(mailbox),
        "DEE_SPEECH_PROVIDER":"local", "DEE_INTERVIEW_MAX_AUDIO_B64_CHARS":"250000",
        "DEE_FLYWHEEL_PATH":str(scratch/"flywheel.jsonl"), "DEE_VECTORSTORE_BACKEND":"memory",
        "DEE_LOGIN_OTP_DEBUG_ECHO":"false", "DEE_VERIF_OTP_DEBUG_ECHO":"false", "DEE_LOGIN_OTP_STATIC_CODE":"",
        "DEE_SESSION_COOKIE_SECURE":"false", "DEE_SESSION_COOKIE_SAMESITE":"lax", "NO_PROXY":"localhost,127.0.0.1",
        "PGOPTIONS":pg_options, "VERITAS_SQL_SMOKE_FACTORY":"smoke_r3_s3_t3:create_smoke_app",
        "PYTHONPATH":os.pathsep.join(str(p) for p in (ROOT/"src", ROOT/"scripts", ROOT))})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        stop.unlink(missing_ok=True)
        with (scratch/"server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", str(port), str(stop)],
                env=env,cwd=scratch,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base,headers={"X-API-Key":"synthetic-audio-admin"}) as admin:
                    assert wait_healthy(admin); yield admin
            finally:
                stop.write_text("stop", encoding="utf-8")
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait(timeout=10)
                    raise AssertionError("interview scratch app failed graceful shutdown")
                assert proc.returncode == 0, "interview scratch lifespan failed"
                checks.check("interview scratch lifespan shuts down gracefully", True)

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path,response.status_code)
        return response.json()
    def count():
        path = Path(str(control)+".jsonl")
        return sum(json.loads(line)["event"] == "start" for line in path.read_text().splitlines()) if path.exists() else 0
    b64 = base64.b64encode(b"synthetic-audio-sentinel-not-a-live-codec-test").decode()
    with client(base) as actor, client(base) as other, client(base) as org_reader:
        with server() as admin:
            engine = create_engine(url, hide_parameters=True, connect_args={"options":pg_options} if pg_options else {})
            try:
                with engine.connect() as db:
                    checks.check("scratch app migrated to current head", db.scalar(text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
            finally:
                engine.dispose()
            ids = []
            for n,http in enumerate((actor,other)):
                cid = require(admin.post("/candidates",json={"evaluate":False,"resume_text":
                    f"Synthetic Audio {n}\nEmail: audio-{n}@example.com\nEXPERIENCE\nEngineer at Acme, 2020 - 2024\nSKILLS\nPython, SQL, Spark"}))["candidate_id"]
                http.headers["X-Candidate-Key"] = require(admin.post(f"/candidates/{cid}/auth-key"))["access_key"]
                ids.append(cid)
            body = require(actor.post("/portal/interviews",json={}))
            sid, qid = body["session"]["id"],body["next_question"]["id"]
            route = f"/portal/interviews/{sid}/answers"
            payload = {"question_id":qid,"audio_b64":b64,"mime":"audio/webm;codecs=opus"}
            checks.check("other candidate cannot read or submit audio to owned interview", other.get(f"/portal/interviews/{sid}").status_code==404
                and other.post(route,json=payload).status_code==404 and count()==0)
            for invalid,status in [({**payload,"mime":"application/pdf"},422),({**payload,"audio_b64":"%%%"},400),
                    ({**payload,"text":"ambiguous"},400),({**payload,"audio_b64":"A"*250001},422)]:
                before = count(); require(actor.post(route,json=invalid),status)
                current = require(actor.get(f"/portal/interviews/{sid}"))
                checks.check("invalid MIME/base64/exclusive channel/size refuses before ASR", count()==before
                    and current["session"]["turns"]==[] and current["next_question"]["id"]==qid)
            for mode in ("failed","unavailable","empty"):
                control.write_text(mode)
                response = actor.post(route,json=payload)
                require(response,422)
                current = require(actor.get(f"/portal/interviews/{sid}"))
                checks.check("fake ASR refusal keeps question and hides provider detail: "+mode,
                    "synthetic-private" not in response.text and not current["session"]["turns"] and current["next_question"]["id"]==qid)
            if combined:
                typed = require(actor.post(route,json={"question_id":qid,"text":ANSWER}))
                qid = typed["next_question"]["id"]
                payload["question_id"] = qid
                checks.check("combined typed answer saves before microphone continuation", typed["session"]["turns"][0]["channel"] == "text")
            control.write_text("ok")
            saved = require(actor.post(route,json=payload))
            turn = saved["session"]["turns"][-1]
            checks.check("browser MIME accepted; saved transcript/digest, no raw audio", turn["channel"]=="audio"
                and turn["transcript"]==ANSWER and turn["audio_digest"]==hashlib.sha256(base64.b64decode(b64)).hexdigest()
                and b64 not in json.dumps(saved) and "audio_b64" not in turn)
            require(actor.post(route,json=payload),409)
            checks.check("duplicate audio refuses without another ASR call", count()==4)
            q2 = saved["next_question"]["id"]
            control.write_text("long")
            long = require(actor.post(route,json={**payload,"question_id":q2}))["session"]["turns"][-1]
            checks.check("overlong ASR is bounded with saved truncation disclosure", len(long["transcript"])==20000 and "transcript_truncated" in long["score"]["codes"])
            done = require(actor.post(f"/portal/interviews/{sid}/finish",json={}))["session"]
            checks.check("audio completion is saved advisory content scoring", done["assessment"]["advisory"]
                and done["assessment"]["human_review_required"] and done["assessment"]["scorer_version"]=="s73.2")
            if combined:
                repeated = require(actor.post("/portal/interviews",json={}))
                repeated_id = repeated["session"]["id"]
                while repeated["next_question"] is not None:
                    repeated = require(actor.post(f"/portal/interviews/{repeated_id}/answers",json={
                        "question_id":repeated["next_question"]["id"], "text":"I Python 123 retrieval " * 20}))
                checks.check("combined native repeated-keyword session cannot earn a strong band", repeated["session"]["assessment"]["band"] == "insufficient_signal"
                    and repeated["session"]["assessment"]["confidence"] == 0)
            org = require(admin.post("/ledger/orgs",json={"name":"Synthetic Audio Reader"}))
            org_reader.headers["X-Org-Key"] = org["api_key"]
            org_path = f"/interview/candidates/{ids[0]}/assessments"
            checks.check("audio summary requires current org consent", org_reader.get(org_path).status_code==403)
            grant = require(admin.post(f"/ledger/candidates/{ids[0]}/consent",json={"purpose":"interview_read","org_id":org["org"]["id"]}))
            summary = org_reader.get(org_path)
            checks.check("consented audio summary exposes neither transcript, turns nor raw audio", summary.status_code==200
                and len(summary.json()["assessments"])==(2 if combined else 1) and all(value not in summary.text for value in (ANSWER,b64,"transcript","turns","audio_digest")))
        with server() as admin:
            after = require(actor.get(f"/portal/interviews/{sid}"))
            checks.check("restart preserves exact saved turns and assessment", after["session"]["turns"]==done["turns"] and after["session"]["assessment"]==done["assessment"])
            if combined:
                checks.check("restart preserves both text and audio channels", [t["channel"] for t in after["session"]["turns"]] == ["text", "audio", "audio"])
            require(admin.post(f"/ledger/consent/{grant['id']}/revoke"))
            checks.check("revoked consent refuses saved audio summary after restart", org_reader.get(org_path).status_code==403)
            require(actor.delete("/portal/me"))
            checks.check("erasure revokes audio subject; survivor stays authorized", actor.get(f"/portal/interviews/{sid}").status_code==401
                and other.get("/portal/interviews").status_code==200)
            engine = create_engine(url, hide_parameters=True, connect_args={"options":pg_options} if pg_options else {})
            try:
                with engine.connect() as db:
                    checks.check("erasure removes saved mixed-channel sessions and turns", not db.execute(select(InterviewSessionRow.id).where(InterviewSessionRow.candidate_id==ids[0])).all()
                        and not db.execute(select(InterviewTurnRow.id)).all())
            finally:
                engine.dispose()
        logs = (scratch/"server.log").read_text(encoding="utf-8")
        checks.check("app logs omit raw audio, transcript and private provider error", all(v not in logs for v in (b64,ANSWER,"synthetic-private-provider-secret")))
    return checks.summary()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        asyncio.run(serve(int(sys.argv[2]), Path(sys.argv[3])))
    else:
        raise SystemExit(main())
