"""Shared resume refusal and readable-input journey on migrated scratch HTTP."""

from contextlib import contextmanager
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-resume-boundary-admin"
TABLES = ("candidates", "resumes", "extractions", "resume_fingerprints", "reports",
          "screening_batches", "batch_items", "screening_item_inputs")


def main(*, parser_limits=False):
    # Reuse the actual synthetic PDF builder, including compressed/image streams.
    sys.path.insert(0, str(ROOT))
    from tests.pdf_helpers import adversarial_pdf, resume_pdf
    task = "r2-s1-t2b" if parser_limits else "r2-s1-t2a"
    checks = Smoke(task + " input acceptance HTTP/persistence")
    scratch = Path(tempfile.mkdtemp(prefix=task + "-"))
    print(f"Synthetic artifacts: {scratch}")
    url = "sqlite:///" + (scratch / "app.db").as_posix()
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
        "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
        "DEE_EMAIL_PROVIDER": "null", "DEE_SPEECH_PROVIDER": "local",
        "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_MAX_RESUME_CHARS": "64",
        "DEE_MAX_PDF_B64_CHARS": "4000", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "PYTHONPATH": str(ROOT / "src"), "NO_PROXY": "127.0.0.1,localhost",
    })
    if parser_limits:
        env.update(DEE_PDF_MAX_PAGES="2", DEE_PDF_MAX_DECODED_BYTES="1024",
                   DEE_PDF_MAX_WORK_UNITS="300", DEE_DOC_MAX_PAGES="1")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    @contextmanager
    def server():
        with (scratch / "server.log").open("a", encoding="utf8") as log:
            proc = subprocess.Popen(uvicorn_argv(port), env=env, cwd=scratch,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(f"http://127.0.0.1:{port}", connect=0.5,
                            headers={"X-API-Key": ADMIN}) as http:
                    assert wait_healthy(http), "scratch startup failed"
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

    engine = create_engine(url, hide_parameters=True)
    def counts():
        with engine.connect() as conn:
            return {table: conn.scalar(text(f"SELECT count(*) FROM {table}")) for table in TABLES}

    def batch(payload):
        return {"items": [{"resume_text": "Readable preceding item"}, payload]}

    try:
        with server() as http:
            with engine.connect() as conn:
                checks.check("actual startup migrated scratch to head", conn.scalar(
                    text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
            orgs = [require(http.post("/ledger/orgs", json={"name": f"Synthetic Input {name}"}))
                    for name in ("A", "B")]
            headers = [{"X-Org-Key": org["api_key"]} for org in orgs]
            paths = ("/evaluate", "/candidates", "/screening/candidates", "/screening/batches")
            valid = resume_pdf()
            cases = [
                ("whitespace", {"resume_text": " \t\r\n\u2003"}, "empty_resume"),
                ("corrupt", {"resume_pdf_b64": base64.b64encode(b"private-not-pdf").decode()}, "pdf_parse_failed"),
                ("truncated", {"resume_pdf_b64": base64.b64encode(base64.b64decode(valid)[:100]).decode()}, "pdf_parse_failed"),
                ("base64-junk", {"resume_pdf_b64": valid[:20] + "!" + valid[20:]}, "pdf_parse_failed"),
                ("encrypted", {"resume_pdf_b64": resume_pdf(encrypted=True)}, "pdf_parse_failed"),
                ("blank", {"resume_pdf_b64": resume_pdf("")}, "pdf_no_readable_text"),
                ("image-only", {"resume_pdf_b64": resume_pdf(image_only=True)}, "pdf_no_readable_text"),
                ("pdf-whitespace", {"resume_pdf_b64": resume_pdf(" " * 10)}, "pdf_no_readable_text"),
                ("decoded-text-over", {"resume_pdf_b64": resume_pdf("x" * 65)}, "resume_text exceeds max_resume_chars=64"),
                ("raw-text-over", {"resume_text": "x" * 65}, "resume_text exceeds max_resume_chars=64"),
                ("encoded-pdf-over", {"resume_pdf_b64": "A" * 4001}, "resume_pdf_b64 exceeds max_pdf_b64_chars=4000"),
            ]
            if parser_limits:
                cases += [(kind, {"resume_pdf_b64": adversarial_pdf(kind)}, "pdf_parse_failed")
                          for kind in ("pages", "expansion", "array", "form-cycle")]
            for path in paths:
                for label, payload, reason in cases:
                    before = counts()
                    body = batch(payload) if path.endswith("/batches") else payload
                    expected = "item 1: " + reason if path.endswith("/batches") else reason
                    response = http.post(path, json=body, headers=headers[0])
                    checks.check(f"{path} {label}: safe refusal without writes",
                        response.status_code == 422 and response.json() == {"detail": expected}
                        and counts() == before)
            reports, batches = [], []
            for path in paths:
                for label, payload in (
                    ("txt", {"resume_text": "Python"}),
                    ("markdown", {"resume_text": "# Skills\nPython"}),
                    ("pdf", {"resume_pdf_b64": resume_pdf("Python")}),
                    ("text-exact", {"resume_text": "x" * 64}),
                    ("decoded-exact", {"resume_pdf_b64": resume_pdf("x" * 64)}),
                ):
                    body = {"items": [payload]} if path.endswith("/batches") else payload
                    saved = require(http.post(path, json=body, headers=headers[0]))
                    if path.endswith("/batches"):
                        batches.append(saved["id"])
                        require(http.post(f'/screening/batches/{saved["id"]}/process', headers=headers[0]))
                        row = require(http.get(f'/screening/batches/{saved["id"]}/queue', headers=headers[0]))["rows"][0]
                        checks.check(f"{path} {label}: readable input completed", row["status"] == "done" and row["advisory"])
                    else:
                        report = saved if path == "/evaluate" else saved["report"]
                        reports.append(report)
                        checks.check(f"{path} {label}: saved advisory insufficient-signal report",
                            report["advisory"] and report["human_review_required"]
                            and report["fabrication_risk"]["band"] == "insufficient_data"
                            and require(http.get(f'/report/{report["id"]}')) == report)
                        if path == "/screening/candidates":
                            own = http.get(f'/screening/reports/{report["id"]}', headers=headers[0])
                            foreign = http.get(f'/screening/reports/{report["id"]}', headers=headers[1])
                            checks.check(f"{label}: org report ownership preserved", own.status_code == 200 and foreign.status_code == 404)
            checks.check("other org cannot read batch", http.get(
                f"/screening/batches/{batches[0]}", headers=headers[1]).status_code == 404)
            if parser_limits:
                # Candidate keys select the actor; no document row is written on
                # page/expansion/work refusal. Other candidate's list stays empty.
                candidate_ids = [require(http.post('/candidates', json={
                    'resume_text': f'Synthetic PDF Actor {i}', 'evaluate': False}))['candidate_id']
                    for i in range(2)]
                candidate_headers = [{'X-Candidate-Key': require(http.post(
                    f'/candidates/{cid}/auth-key'))['access_key']} for cid in candidate_ids]
                def document_counts():
                    with engine.connect() as conn:
                        return tuple(conn.scalar(text(f'SELECT count(*) FROM {table}'))
                            for table in ('verifications', 'verification_challenges', 'audit_log'))
                for kind in ('pages', 'expansion', 'array', 'form-cycle'):
                    before = document_counts()
                    response = http.post('/portal/documents', headers=candidate_headers[0], json={
                        'doc_type': 'experience_letter', 'content_b64': adversarial_pdf(kind)})
                    checks.check(f'verification {kind}: safe refusal without rows',
                        response.status_code == 400 and response.json() == {
                            'detail': 'document could not be read as a PDF'} and document_counts() == before)
                saved = require(http.post('/portal/documents', headers=candidate_headers[0], json={
                    'doc_type': 'experience_letter', 'content_b64': resume_pdf('Python')}))
                mine = require(http.get('/portal/verifications', headers=candidate_headers[0]))
                foreign = require(http.get('/portal/verifications', headers=candidate_headers[1]))
                checks.check('verification valid PDF: advisory claim evidence, identity untouched',
                    saved['claims']['advisory'] and mine['assurance']['level'] == 0)
                checks.check('verification actor isolation', len(mine['verifications']) == 1
                    and foreign['verifications'] == [])
            snapshot = counts()
        with server() as http:
            checks.check("actual restart retains only valid intake rows", counts() == snapshot)
            checks.check("actual restart reads saved reports", all(
                require(http.get(f'/report/{report["id"]}')) == report for report in reports))
            checks.check("actual restart reads completed batch", require(http.get(
                f"/screening/batches/{batches[0]}", headers=headers[0]))["status"] == "complete")
            if parser_limits:
                checks.check('actual restart reads valid document only', len(require(http.get(
                    '/portal/verifications', headers=candidate_headers[0]))['verifications']) == 1)
        if parser_limits:
            # A very short deadline exercises real app worker timeout refusal;
            # the separate controlled-child regression proves an entered stall.
            env['DEE_PDF_PARSE_TIMEOUT_SECONDS'] = '0.001'
            with server() as http:
                before = counts()
                response = http.post('/evaluate', json={'resume_pdf_b64': resume_pdf('Python')})
                checks.check('actual HTTP worker deadline refuses without intake rows',
                    response.status_code == 422 and response.json() == {'detail': 'pdf_parse_failed'}
                    and counts() == before)
                checks.check('server remains healthy after worker timeout', http.get('/healthz').status_code == 200)
    finally:
        engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
