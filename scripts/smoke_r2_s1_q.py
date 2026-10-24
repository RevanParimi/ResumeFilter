"""R2-S1 combined acceptance: real migrated app, fake providers, scratch SQL."""

from contextlib import contextmanager
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

from app.candidates.schema import CandidateProfile
from app.core.config import Settings
from app.interview.scoring import score_turn

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r2_s1_t1 import ANSWER, ModelFake
from smoke_r2_s1_t3 import REPO, RESUMES, assessment, create_smoke_app as github_app, github_context

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-r2-integration-admin"
TABLES = ("candidates", "resumes", "extractions", "resume_fingerprints", "reports",
          "screening_batches", "batch_items", "screening_item_inputs")


def create_smoke_app():
    # T3's factory supplies the real GitHub client with MockTransport. T1's
    # existing fake then replaces only the model constructor before startup.
    import app.services as services
    app = github_app()
    services.build_llm = lambda settings: ModelFake(settings=settings)
    return app


def main():
    sys.path.insert(0, str(ROOT))
    from tests.pdf_helpers import adversarial_pdf, resume_pdf
    checks = Smoke("R2-S1 integrated input / provider / GitHub / ownership")
    scratch = Path(tempfile.mkdtemp(prefix="r2-s1-q-"))
    print(f"Synthetic artifacts: {scratch}")

    def set_modes(model="malformed", github="429"):
        (scratch / "provider-mode.txt").write_text(model, encoding="utf-8")
        (scratch / "github-mode.txt").write_text(github, encoding="utf-8")

    set_modes()
    url = "sqlite:///" + (scratch / "app.db").as_posix()
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
        "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
        "DEE_EMAIL_PROVIDER": "null", "DEE_SPEECH_PROVIDER": "local",
        "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_MAX_RESUME_CHARS": "2048",
        "DEE_MAX_PDF_B64_CHARS": "32000", "DEE_PDF_MAX_PAGES": "2",
        "DEE_PDF_MAX_DECODED_BYTES": "2048", "DEE_PDF_MAX_WORK_UNITS": "300",
        "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "R2_MODEL_SMOKE_DIR": str(scratch), "R2_GITHUB_SMOKE_DIR": str(scratch),
        "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    @contextmanager
    def server():
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r2_s1_q:create_smoke_app") + ["--factory"],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(f"http://127.0.0.1:{port}", connect=0.5, headers={"X-API-Key": ADMIN}) as http:
                    assert wait_healthy(http), "combined scratch app failed to start"
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

    def calls(name):
        path = scratch / name
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    engine = create_engine(url, hide_parameters=True)

    def counts():
        with engine.connect() as conn:
            return {table: conn.scalar(text(f"SELECT count(*) FROM {table}")) for table in TABLES}

    def check_context(label, report, warning):
        context = github_context(report)
        checks.check(label + " has neutral zero-weight GitHub context", bool(context) and all(
            e["polarity"] == "neutral" and e["weight"] == 0 for e in context))
        checks.check(label + " keeps diagnostics separate", any(e["ref"] == "github.unavailable"
                      for e in context) == warning)
        checks.check(label + " preserves advisory review", report["advisory"] and report["human_review_required"])
        checks.check(label + " excludes invalid provider fragments", "MODEL ONLY" not in json.dumps(report))

    try:
        with server() as http:
            with engine.connect() as conn:
                checks.check("real startup migrated scratch SQL to head", conn.scalar(
                    text("SELECT version_num FROM alembic_version")) == "0030_screening_ingest_facts")
            orgs = [require(http.post("/ledger/orgs", json={"name": "Synthetic Integrated " + name}))
                    for name in ("A", "B")]
            headers = [{"X-Org-Key": org["api_key"]} for org in orgs]
            paths = ("/evaluate", "/candidates", "/screening/candidates", "/screening/batches")
            cases = [
                ("empty", {"resume_text": " \t\n"}, "empty_resume"),
                ("corrupt", {"resume_pdf_b64": base64.b64encode(b"synthetic-private-invalid-pdf").decode()}, "pdf_parse_failed"),
                ("blank", {"resume_pdf_b64": resume_pdf("")}, "pdf_no_readable_text"),
                ("text-over", {"resume_text": "x" * 2049}, "resume_text exceeds max_resume_chars=2048"),
                ("encoded-over", {"resume_pdf_b64": "A" * 32001}, "resume_pdf_b64 exceeds max_pdf_b64_chars=32000"),
            ]
            cases += [(kind, {"resume_pdf_b64": adversarial_pdf(kind)}, "pdf_parse_failed")
                      for kind in ("pages", "expansion", "array", "form-cycle")]
            for path in paths:
                for label, payload, detail in cases:
                    before = counts(), calls("provider-calls.txt"), calls("github-calls.txt")
                    body = {"items": [{"resume_text": "Readable preceding item"}, payload]} if path.endswith("/batches") else payload
                    expected = "item 1: " + detail if path.endswith("/batches") else detail
                    response = http.post(path, headers=headers[0], json=body)
                    checks.check(path + " " + label + " refuses safely before providers/writes",
                        response.status_code == 422 and response.json() == {"detail": expected} and
                        (counts(), calls("provider-calls.txt"), calls("github-calls.txt")) == before)
            persisted = []
            for domain, resume in RESUMES.items():
                set_modes("abstain", "success")
                baseline = require(http.post("/evaluate", json={"resume_text": resume, "domain": domain}))
                for model, github in (("malformed", "429"), ("array", "404"), ("prose_array", "403"),
                                      ("nonfinite", "timeout"), ("transport", "transport"),
                                      ("malformed", "partial"), ("malformed", "success")):
                    set_modes(model, github)
                    for source, payload in (("text", {"resume_text": resume}),
                                            ("pdf", {"resume_pdf_b64": resume_pdf(resume)})):
                        label = domain + " " + source + " " + model + "/" + github
                        report = require(http.post("/evaluate", json={**payload, "domain": domain, "github_url": REPO}))
                        check_context(label, report, warning=github != "success")
                        checks.check(label + " equals no-GitHub deterministic assessment", assessment(report) == assessment(baseline))
                        checks.check(label + " persists corrected complete report", require(http.get(
                            f'/report/{report["id"]}')) == report)
                        persisted.append(report)
            set_modes("malformed", "429")
            linked_resume = RESUMES["genai"].replace("support chatbot.", "support chatbot. " + REPO)
            saved = require(http.post("/screening/candidates", headers=headers[0], json={"resume_text": linked_resume}))
            cid, rid = saved["candidate_id"], saved["report"]["id"]
            check_context("organization combined report", saved["report"], warning=True)
            detail = require(http.get(f"/candidates/{cid}"))
            checks.check("invalid profile reply falls back as a whole", saved["extraction_method"] == "heuristic"
                and detail["latest_profile"]["skills"] and "MODEL ONLY" not in json.dumps(detail))
            checks.check("commissioning org can read corrected report", require(http.get(
                f"/screening/reports/{rid}", headers=headers[0])) == saved["report"])
            require(http.get(f"/screening/reports/{rid}", headers=headers[1]), 404)
            checks.check("other org cannot read corrected report", True)
            sparse = require(http.post("/evaluate", json={"resume_text": "Python"}))
            checks.check("readable sparse input remains advisory insufficient data", sparse["advisory"] and
                sparse["human_review_required"] and sparse["fabrication_risk"]["band"] == "insufficient_data")

            # Different first-party claim links receive their own outcome even
            # when malformed extraction falls back and a shared link repeats.
            batch_resume = "Integrated Batch\nintegration-batch@example.com\nEXPERIENCE\n" + (
                f"- Built production RAG for support. {REPO}\n"
                "- Fine-tuned an open model for support. https://github.com/bob/project\n"
                f"- Built another production RAG service. {REPO}\n")
            bid = require(http.post("/screening/batches", headers=headers[0], json={
                "name": "Integrated synthetic batch", "items": [{"resume_text": batch_resume}]}))["id"]
            before = len(calls("github-calls.txt"))
            ran = require(http.post(f"/screening/batches/{bid}/process", headers=headers[0]))
            checks.check("batch completes with malformed model and GitHub outage", ran["processed"] == 1 and ran["remaining"] == 0)
            row = require(http.get(f"/screening/batches/{bid}/queue", headers=headers[0]))["rows"][0]
            batch_report = require(http.get(f'/screening/reports/{row["report_id"]}', headers=headers[0]))
            for verdict in batch_report["verdicts"]:
                context = [e for e in verdict["evidence"] if e["source"] == "github"]
                ref = "github.repository_metadata" if "bob/project" in verdict["claim_text"] else "github.unavailable"
                checks.check("fallback batch claim retains only its own neutral context", bool(context) and all(
                    e["ref"] == ref and e["polarity"] == "neutral" and e["weight"] == 0 for e in context))
            checks.check("repeat anchor cache is evaluation-local", calls("github-calls.txt")[before:].count(
                "/repos/alice/" + REPO.rsplit("/", 1)[-1]) == 1)
            require(http.get(f"/screening/batches/{bid}/queue", headers=headers[1]), 404)
            checks.check("other org cannot read integrated batch", True)

            key = require(http.post(f"/candidates/{cid}/auth-key"))["access_key"]
            candidate_headers = {"X-Candidate-Key": key}
            started = require(http.post("/portal/interviews", headers=candidate_headers, json={}))
            sid, question = started["session"]["id"], started["next_question"]
            expected_score = score_turn(transcript=ANSWER, expected_signals=question["expected_signals"],
                profile=CandidateProfile.model_validate(detail["latest_profile"]),
                settings=Settings(_env_file=None)).model_dump(mode="json")
            answered = require(http.post(f"/portal/interviews/{sid}/answers", headers=candidate_headers,
                json={"question_id": question["id"], "text": ANSWER}))
            score = answered["session"]["turns"][0]["score"]
            checks.check("malformed interview dimensions preserve entire deterministic score", score == expected_score)
            require(http.post(f"/portal/interviews/{sid}/finish", headers=candidate_headers, json={}))
            other = require(http.post("/candidates", json={
                "resume_text": "Other Integration Person\nother-integration@example.com\nSKILLS\nSQL", "evaluate": False}))
            other_key = require(http.post(f'/candidates/{other["candidate_id"]}/auth-key'))["access_key"]
            require(http.get(f"/portal/interviews/{sid}", headers={"X-Candidate-Key": other_key}), 404)
            checks.check("other candidate cannot read integrated interview", True)
            set_modes("valid", "success")
            valid = require(http.post("/evaluate", json={"resume_text": RESUMES["genai"], "github_url": REPO}))
            check_context("valid local model reply", valid, warning=False)
            checks.check("valid opinions retain confidence cap", any(e["source"] == "llm" and e["weight"] == 0.85
                for v in valid["verdicts"] for e in v["evidence"]))
            checks.check("all six model consumers were reached", set(calls("provider-calls.txt")) == {
                "claims", "profile", "plausibility", "style", "probes", "interview"})
            snapshot = counts()
        with server() as http:
            checks.check("actual restart preserves accepted rows", counts() == snapshot)
            checks.check("actual restart reads complete accepted reports", all(require(
                http.get(f'/report/{r["id"]}')) == r for r in persisted))
            checks.check("actual restart reads corrected org report", require(http.get(
                f"/screening/reports/{rid}", headers=headers[0])) == saved["report"])
            require(http.get(f"/screening/reports/{rid}", headers=headers[1]), 404)
            checks.check("actual restart preserves org denial", True)
            checks.check("actual restart reads completed batch", require(http.get(
                f"/screening/batches/{bid}", headers=headers[0]))["status"] == "complete")
            checks.check("actual restart retains rule interview score", require(http.get(
                f"/portal/interviews/{sid}", headers=candidate_headers))["session"]["turns"][0]["score"] == score)
        log = (scratch / "server.log").read_text(encoding="utf-8")
        checks.check("provider diagnostics omit private upstream text", all(marker not in log for marker in (
            "synthetic-provider-failure", "synthetic-upstream-private-detail", "synthetic-private-invalid-pdf")))
    finally:
        engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
