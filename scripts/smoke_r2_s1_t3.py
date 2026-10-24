"""GitHub polarity journey: real migrated app/HTTP, fake providers, scratch SQL."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

import httpx
from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from app.services.llm import LLMClient

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-github-polarity-admin"
PRIVATE = "synthetic-upstream-private-detail"
REPO = "https://github.com/alice/gpt-4-qlora-a100-eval-airflow-spark-kafka"
RESUMES = {
    "genai": "Synthetic Person\ngithub-polarity@example.com\nEXPERIENCE\n"
             "- Fine-tuned an open model for our support chatbot.\n"
             "- Built a retrieval augmented generation service for support.\nSKILLS\nPython, SQL\n",
    "data_eng": "Synthetic Data Person\ngithub-data@example.com\nEXPERIENCE\n"
                "- Built a daily ingestion pipeline for analytics.\n"
                "- Created a streaming service for analytics.\nSKILLS\nPython, SQL\n",
}


class ClaimFake(LLMClient):
    async def _araw(self, *, model, system, prompt, max_tokens):
        from tests.conftest import FakeLLM
        scratch = Path(os.environ["R2_GITHUB_SMOKE_DIR"])
        content = ""
        if (scratch / "claim-mode.txt").read_text(encoding="utf-8") == "generic" and "extracting atomic" in system:
            content = json.dumps({"claims": [{"text": "Owned a private project", "claim_type": "unknown"}]})
        return await FakeLLM({"": content}, settings=self.settings)._araw(
            model=model, system=system, prompt=prompt, max_tokens=max_tokens)


def create_smoke_app():
    import app.services as services
    from app.main import create_app
    from app.services.github import GitHubClient

    scratch = Path(os.environ["R2_GITHUB_SMOKE_DIR"])

    def handler(request):
        mode = (scratch / "github-mode.txt").read_text(encoding="utf-8")
        with (scratch / "github-calls.txt").open("a", encoding="utf-8") as calls:
            calls.write(request.url.path + "\n")
        # Bob's endpoint remains available while Alice's endpoint fails.
        if request.url.path.startswith("/repos/bob/"):
            mode = "success"
        component = request.url.path.rsplit("/", 1)[-1]
        if mode == "timeout":
            raise httpx.ReadTimeout(PRIVATE, request=request)
        if mode == "transport":
            raise httpx.ConnectError(PRIVATE, request=request)
        if mode.isdigit():
            return httpx.Response(int(mode), json={"message": PRIVATE})
        if mode == "json":
            return httpx.Response(200, text=PRIVATE)
        if mode == "shape":
            return httpx.Response(200, json=[PRIVATE])
        if mode == "partial" and component == "commits":
            return httpx.Response(429, json={"message": PRIVATE})
        if mode == "languages" and component == "languages":
            return httpx.Response(403, json={"message": PRIVATE})
        if component == "languages":
            return httpx.Response(200, json={"Python": 100})
        if component == "commits":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"language": "Python", "stargazers_count": 4})

    services.GitHubClient = lambda settings: GitHubClient(settings=settings, client=httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    services.build_llm = lambda settings: ClaimFake(settings=settings)
    return create_app()


def github_context(report):
    return [e for v in report["verdicts"] for e in v["evidence"] if e["source"] == "github"]


def assessment(report):
    # Compare the same claims; identifiers and display-only GitHub context vary.
    return {"depth": [report[k] for k in ("depth_score", "depth_band", "overall_confidence")],
            "verdicts": [{k: ([e for e in value if e["source"] != "github"] if k == "evidence" else value)
                          for k, value in v.items() if k != "claim_id"} for v in report["verdicts"]]}


def main():
    checks = Smoke("R2-S1-T3 GitHub neutral context / isolation / persistence")
    scratch = Path(tempfile.mkdtemp(prefix="r2-s1-t3-"))
    print(f"Synthetic artifacts: {scratch}")

    def set_mode(mode, claim_mode="rules"):
        (scratch / "github-mode.txt").write_text(mode, encoding="utf-8")
        (scratch / "claim-mode.txt").write_text(claim_mode, encoding="utf-8")

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    set_mode("success")
    url = "sqlite:///" + (scratch / "app.db").as_posix()
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
        "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
        "DEE_EMAIL_PROVIDER": "null", "DEE_SPEECH_PROVIDER": "local",
        "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "R2_GITHUB_SMOKE_DIR": str(scratch),
        "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    @contextmanager
    def server():
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r2_s1_t3:create_smoke_app") + ["--factory"],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
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

    def check_context(label, report, unavailable=False):
        context = github_context(report)
        checks.check(label + " shows neutral zero-weight context", bool(context) and all(
            e["polarity"] == "neutral" and e["weight"] == 0 for e in context))
        checks.check(label + " preserves advisory review", report["advisory"] and report["human_review_required"])
        checks.check(label + " diagnostics omit upstream details", PRIVATE not in json.dumps(report))
        if unavailable:
            checks.check(label + " explicitly reports unavailable fetch", any(
                e["ref"] == "github.unavailable" for e in context))

    engine = create_engine(url, hide_parameters=True)
    try:
        with server() as http:
            with engine.connect() as conn:
                checks.check("actual scratch startup migrated to head", conn.scalar(
                    text("SELECT version_num FROM alembic_version")) == "0030_screening_ingest_facts")
            for domain, resume in RESUMES.items():
                baseline = require(http.post("/evaluate", json={"resume_text": resume, "domain": domain}))
                checks.check(domain + " baseline has rule assessments", bool(baseline["verdicts"]) and any(
                    e["source"] == "rule" for v in baseline["verdicts"] for e in v["evidence"]))
                for mode in ("success", "403", "404", "429", "503", "timeout", "transport", "json", "shape", "partial", "languages"):
                    set_mode(mode)
                    report = require(http.post("/evaluate", json={
                        "resume_text": resume, "domain": domain, "github_url": REPO}))
                    label = domain + " " + mode
                    check_context(label, report, unavailable=mode != "success")
                    checks.check(label + " leaves claim assessment unchanged", assessment(report) == assessment(baseline))
                    checks.check(label + " persisted context equals response", require(
                        http.get(f'/report/{report["id"]}')) == report)
            set_mode("404", "generic")
            generic = require(http.post("/evaluate", json={"resume_text": RESUMES["genai"], "github_url": REPO}))
            checks.check("outage alone cannot assess a generic claim", len(generic["verdicts"]) == 1 and
                generic["verdicts"][0]["claim_type"] == "unknown" and
                generic["verdicts"][0]["status"] == "unverified" and generic["verdicts"][0]["confidence"] == 0)
            set_mode("success", "generic")
            generic = require(http.post("/evaluate", json={"resume_text": RESUMES["genai"], "github_url": REPO}))
            checks.check("visible metadata alone cannot assess a generic claim", len(generic["verdicts"]) == 1 and
                generic["verdicts"][0]["status"] == "unverified" and generic["verdicts"][0]["confidence"] == 0)

            set_mode("404")
            orgs = [require(http.post("/ledger/orgs", json={"name": "Synthetic GitHub " + name}))
                    for name in ("A", "B")]
            headers = [{"X-Org-Key": org["api_key"]} for org in orgs]
            # Screening's heuristic extractor discovers links on claim lines;
            # a standalone profile link is not a candidate-level API argument.
            screening_resume = RESUMES["genai"].replace(
                "support chatbot.", "support chatbot. " + REPO)
            saved = require(http.post("/screening/candidates", headers=headers[0],
                                     json={"resume_text": screening_resume}))
            rid = saved["report"]["id"]
            check_context("org screening 404", saved["report"], unavailable=True)
            checks.check("commissioning org reads its corrected report", require(http.get(
                f"/screening/reports/{rid}", headers=headers[0])) == saved["report"])
            require(http.get(f"/screening/reports/{rid}", headers=headers[1]), 404)
            checks.check("other org cannot read corrected report", True)

            # Different linked claims in one batch result must keep their own
            # fetch outcomes. Repeat Alice links use only evaluation-local cache.
            batch_resume = "Batch Synthetic\ngithub-batch@example.com\nEXPERIENCE\n" + (
                f"- Built a retrieval augmented generation service. {REPO}\n"
                "- Fine-tuned an open model for support. https://github.com/bob/project\n"
                f"- Built another retrieval augmented generation service. {REPO}\n")
            bid = require(http.post("/screening/batches", headers=headers[0], json={
                "name": "Synthetic GitHub context", "items": [{"resume_text": batch_resume}]}))["id"]
            calls_before = len((scratch / "github-calls.txt").read_text(encoding="utf-8").splitlines())
            ran = require(http.post(f"/screening/batches/{bid}/process", headers=headers[0]))
            checks.check("batch processing completes with partial availability", ran["processed"] == 1 and ran["remaining"] == 0)
            rows = require(http.get(f"/screening/batches/{bid}/queue", headers=headers[0]))["rows"]
            batch_report = require(http.get(f'/screening/reports/{rows[0]["report_id"]}', headers=headers[0]))
            for verdict in batch_report["verdicts"]:
                context = [e for e in verdict["evidence"] if e["source"] == "github"]
                wanted = "github.repository_metadata" if "bob/project" in verdict["claim_text"] else "github.unavailable"
                checks.check("linked batch claim retains own fetch outcome", bool(context) and all(
                    e["ref"] == wanted and e["polarity"] == "neutral" and e["weight"] == 0 for e in context))
            calls = (scratch / "github-calls.txt").read_text(encoding="utf-8").splitlines()[calls_before:]
            checks.check("repeat linked repo fetch cached within evaluation", calls.count("/repos/alice/" + REPO.rsplit("/", 1)[-1]) == 1)
            require(http.get(f"/screening/batches/{bid}/queue", headers=headers[1]), 404)
            checks.check("other org cannot read batch queue", True)
        with server() as http:
            checks.check("corrected org report survives actual app restart", require(
                http.get(f"/screening/reports/{rid}", headers=headers[0])) == saved["report"])
            require(http.get(f"/screening/reports/{rid}", headers=headers[1]), 404)
            checks.check("restart preserves org isolation", True)
            checks.check("batch report context survives restart", require(http.get(
                f'/screening/reports/{batch_report["id"]}', headers=headers[0])) == batch_report)
        checks.check("provider details absent from server logs", PRIVATE not in (scratch / "server.log").read_text(encoding="utf-8"))
    finally:
        engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
