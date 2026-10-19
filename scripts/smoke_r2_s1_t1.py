"""Model-boundary HTTP journey; real app, existing FakeLLM, scratch SQL.

Provider override is confined to this smoke factory. No external vendor calls,
browser, live-provider compatibility or quality claims.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.interview.scoring import score_turn
from app.services.llm import LLMClient

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-model-boundary-admin"
RESUME = """Synthetic Person
model-boundary@example.com
EXPERIENCE
ML Engineer, Acme (2021 - Present)
- Fine-tuned GPT-4 to dramatically improve accuracy for our chatbot.
- Built production RAG at scale serving millions of users.
SKILLS
Python, PyTorch, SQL
"""
ANSWER = ("I rebuilt the ingestion service at Acme myself using Python and PyTorch. "
          "I measured p99 latency from 900 ms to 220 ms on a held-out test set. "
          "I rolled back the tokenizer change after tracing the nightly job failure.")


class ModelFake(LLMClient):
    """Scripted text replies use the normal shared JSON parser in the child app."""

    async def _araw(self, *, model, system, prompt, max_tokens):
        from tests.conftest import FakeLLM
        scratch = Path(os.environ["R2_MODEL_SMOKE_DIR"])
        mode = (scratch / "provider-mode.txt").read_text(encoding="utf-8")
        if "precise resume parser" in system:
            kind, payload = "profile", {"full_name": {"value": "MODEL ONLY", "confidence": 0.9},
                                       "skills": [{"confidence": 0.9}]}
        elif "extracting atomic" in system:
            kind, payload = "claims", {"claims": [{"text": "MODEL ONLY"}, {}]}
        elif "forensic writing" in system:
            kind, payload = "style", {"likelihood": "0.99", "confidence": 0.9,
                                     "reasoning": "MODEL ONLY", "indicators": None}
        elif '\"probes\"' in prompt:
            kind, payload = "probes", {"probes": ["MODEL ONLY", {}]}
        elif "grading ONE answer" in system:
            kind, payload = "interview", {"dimensions": {"depth": 0.9, "ownership": "0.9"}}
        else:
            kind, payload = "plausibility", {"coherence": 0.99, "confidence": 0.99,
                "reasoning": "MODEL ONLY", "expected_signals": None, "missing_signals": []}
        with (scratch / "provider-calls.txt").open("a", encoding="utf-8") as calls:
            calls.write(kind + "\n")
        if mode == "transport":
            raise RuntimeError("synthetic-provider-failure")
        if mode == "abstain":
            content = ""
        elif mode == "array":
            content = '[{"coherence": 0.99}]'
        elif mode == "prose_array":
            content = 'Here is the reply: ' + json.dumps([{
                "coherence": 0.99, "confidence": 0.99, "reasoning": "MODEL ONLY",
                "expected_signals": [], "missing_signals": [],
            }])
        elif mode == "nonfinite":
            content = '{"coherence": NaN, "confidence": Infinity}'
        elif mode == "valid":
            if kind == "plausibility":
                payload = {"coherence": 0.9, "confidence": 0.99, "reasoning": "Valid local opinion",
                           "expected_signals": [], "missing_signals": []}
            elif kind == "style":
                payload = {"likelihood": 0.2, "confidence": 0.99, "reasoning": "Valid local style",
                           "indicators": ["varied wording"]}
            else:
                payload = {}
            content = json.dumps(payload)
        else:
            content = json.dumps(payload)
        fake = FakeLLM({"": content}, settings=self.settings)
        return await fake._araw(model=model, system=system, prompt=prompt, max_tokens=max_tokens)


def create_smoke_app():
    # Override only the provider constructor in this isolated test process.
    # create_app(None) still follows the real startup/migration/store composition.
    import app.services as services
    from app.main import create_app
    services.build_llm = lambda settings: ModelFake(settings=settings)
    return create_app()


def project(report):
    return {**{k: report[k] for k in ("domain", "candidate_context", "depth_score", "depth_band",
                "overall_confidence", "advisory", "human_review_required", "summary", "ai_generation")},
            "verdicts": [{k: v for k, v in row.items() if k != "claim_id"}
                         for row in report["verdicts"]],
            "flagged": len(report["flagged_claim_ids"]), "deferred": len(report["deferred_claim_ids"])}


def main():
    checks = Smoke("R2-S1-T1 model fallback HTTP/persistence/interview")
    scratch = Path(tempfile.mkdtemp(prefix="r2-s1-t1-"))
    print(f"Synthetic artifacts: {scratch}")
    def set_mode(mode):
        (scratch / "provider-mode.txt").write_text(mode, encoding="utf-8")

    set_mode("abstain")
    url = "sqlite:///" + (scratch / "app.db").as_posix()
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "R2_MODEL_SMOKE_DIR": str(scratch),
        "DEE_LLM_MAX_RETRIES": "0", "DEE_GITHUB_TOKEN": "",
        "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "null",
        "DEE_SPEECH_PROVIDER": "local", "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "PYTHONPATH": os.pathsep.join(str(path) for path in (ROOT / "src", ROOT / "scripts", ROOT)), "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r2_s1_t1:create_smoke_app") + ["--factory"], env=env, cwd=scratch,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base, connect=0.5, headers={"X-API-Key": ADMIN}) as http:
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

    engine = create_engine(url, hide_parameters=True)
    try:
        with server() as http:
            with engine.connect() as conn:
                checks.check("actual scratch app migrated to head", conn.scalar(
                    text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
            baseline = require(http.post("/evaluate", json={"resume_text": RESUME}))
            checks.check("abstaining provider has deterministic claims/probes",
                         bool(baseline["verdicts"]) and any(v["probes"] for v in baseline["verdicts"]))
            for mode in ("malformed", "array", "prose_array", "nonfinite", "transport"):
                set_mode(mode)
                actual = require(http.post("/evaluate", json={"resume_text": RESUME}))
                checks.check(f"{mode} evaluation equals deterministic baseline", project(actual) == project(baseline))
                saved = require(http.get(f'/report/{actual["id"]}'))
                checks.check(f"{mode} report persisted without LLM evidence",
                    saved == actual and all(e["source"] != "llm"
                        for v in actual["verdicts"] for e in v["evidence"]))
            set_mode("malformed")
            orgs = [require(http.post("/ledger/orgs", json={"name": f"Synthetic Model {name}"}))
                    for name in ("A", "B")]
            headers = [{"X-Org-Key": org["api_key"]} for org in orgs]
            saved = require(http.post("/screening/candidates", json={"resume_text": RESUME}, headers=headers[0]))
            cid, rid = saved["candidate_id"], saved["report"]["id"]
            detail = require(http.get(f"/candidates/{cid}"))
            checks.check("malformed profile uses whole heuristic result",
                saved["extraction_method"] == "heuristic" and detail["latest_profile"]["skills"]
                and "MODEL ONLY" not in json.dumps(detail))
            checks.check("commissioning org reads saved fallback report",
                require(http.get(f"/screening/reports/{rid}", headers=headers[0])) == saved["report"])
            require(http.get(f"/screening/reports/{rid}", headers=headers[1]), 404)
            checks.check("other org cannot read fallback report", True)
            key = require(http.post(f"/candidates/{cid}/auth-key"))["access_key"]
            candidate_headers = {"X-Candidate-Key": key}
            started = require(http.post("/portal/interviews", json={}, headers=candidate_headers))
            sid, question = started["session"]["id"], started["next_question"]
            # Settings for the pure baseline are read from the exact child pins.
            prior = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                settings = Settings(_env_file=None)
            finally:
                os.environ.clear()
                os.environ.update(prior)
            expected = score_turn(transcript=ANSWER, expected_signals=question["expected_signals"],
                profile=CandidateProfile.model_validate(detail["latest_profile"]), settings=settings)
            answered = require(http.post(f"/portal/interviews/{sid}/answers", headers=candidate_headers,
                json={"question_id": question["id"], "text": ANSWER}))
            checks.check("mixed invalid interview dimensions retain entire rule score",
                answered["session"]["turns"][0]["score"] == expected.model_dump(mode="json"))
            require(http.post(f"/portal/interviews/{sid}/finish", headers=candidate_headers, json={}))
            require(http.get(f"/portal/interviews/{sid}", headers={"X-Candidate-Key": "wrong"}), 401)
            checks.check("interview still requires candidate authentication", True)
            second = require(http.post("/candidates", json={"resume_text":
                "Second Synthetic\nsecond-model@example.com\nSKILLS\nPython, SQL\n", "evaluate": False}))
            second_key = require(http.post(f'/candidates/{second["candidate_id"]}/auth-key'))["access_key"]
            require(http.get(f"/portal/interviews/{sid}", headers={"X-Candidate-Key": second_key}), 404)
            checks.check("other candidate cannot read fallback interview", True)
            set_mode("valid")
            valid = require(http.post("/evaluate", json={"resume_text": RESUME}))
            checks.check("valid opinions still contribute capped LLM evidence/style",
                any(e["source"] == "llm" and e["weight"] == 0.85
                    for v in valid["verdicts"] for e in v["evidence"])
                and any(s["source"] == "llm" for s in valid["ai_generation"]["signals"]))
            checks.check("all six actual provider consumers reached", set((scratch / "provider-calls.txt").read_text(encoding="utf-8").splitlines()) == {
                "claims", "profile", "plausibility", "style", "probes", "interview"})
        set_mode("malformed")
        with server() as http:
            checks.check("fallback report survives actual app restart",
                require(http.get(f"/report/{rid}")) == saved["report"])
            body = require(http.get(f"/portal/interviews/{sid}", headers=candidate_headers))
            checks.check("rule interview score survives restart",
                body["session"]["turns"][0]["score"] == expected.model_dump(mode="json"))
        log = (scratch / "server.log").read_text(encoding="utf-8")
        checks.check("provider failure details absent from app logs", "synthetic-provider-failure" not in log)
    finally:
        engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
