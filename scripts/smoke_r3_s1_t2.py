"""Captured contact email/refusal/retry/restart on migrated scratch storage.

Default SQLite; --postgres requires an explicitly configured disposable database.
Never sends real email/SMS. The control file changes only this synthetic provider.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, select, update

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database
from app.core.db import make_session_factory
from app.services.email import CaptureEmail, EmailSendFailed, NullEmail
from app.verification.models import VerificationChallengeRow

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-contact-delivery-admin"


class ControlledCaptureEmail(CaptureEmail):
    """Capture/failure controls are local evidence, never a production provider."""
    @property
    def mode(self):
        path = Path(self.settings.email_capture_path + ".control")
        return path.read_text(encoding="utf-8") if path.exists() else "ok"

    @property
    def available(self):
        return self.mode != "unavailable"

    def send(self, *, to, subject, body):
        if subject == "Verify your Veritas contact" and self.mode == "failed":
            raise EmailSendFailed("synthetic provider refusal")
        super().send(to=to, subject=subject, body=body)
        if subject == "Verify your Veritas contact" and self.mode == "partial":
            raise EmailSendFailed("synthetic ambiguous provider acknowledgment")


def create_smoke_app():
    import app.services as services
    from smoke_r2_s2_t1 import create_smoke_app as fake_engine_app
    services.build_email = lambda settings: (ControlledCaptureEmail(settings)
        if settings.email_provider == "capture" else NullEmail(settings))
    return fake_engine_app()


def latest_code(mailbox, destination):
    messages = [json.loads(line) for line in mailbox.read_text(encoding="utf-8").splitlines()]
    msg = next(m for m in reversed(messages) if m["to"] == destination and m["subject"] == "Verify your Veritas contact")
    return re.search(r"\b(\d{6})\b", msg["body"])[1]


def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-contact-delivery-"))
    print(f"Synthetic HTTP evidence: {scratch}", flush=True)
    checks = Smoke("R3-S1-T2 contact delivery HTTP/restart")
    mailbox = scratch / "mail.jsonl"
    control = Path(str(mailbox) + ".control")
    codes = []
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
            "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "capture", "DEE_EMAIL_CAPTURE_PATH": str(mailbox),
            "DEE_VECTORSTORE_BACKEND": "memory", "DEE_SPEECH_PROVIDER": "local",
            "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
            "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
            "PGOPTIONS": pg_options, "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r3_s1_t2:create_smoke_app") + ["--factory"],
                    env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
                        assert wait_healthy(http), "scratch app failed to start"
                        yield http
                finally:
                    proc.terminate()
                    try: proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait(timeout=10)

        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()

        engine = create_engine(url, hide_parameters=True,
            connect_args={"options": pg_options} if pg_options else {})
        factory = make_session_factory(engine)
        def mutate(vid, **values):
            with factory.begin() as session:
                session.execute(update(VerificationChallengeRow).where(
                    VerificationChallengeRow.verification_id == vid).values(**values))
        def challenges():
            with factory() as session: return len(session.scalars(select(VerificationChallengeRow)).all())

        email = "http-contact@example.com"
        other_email = "http-other@example.com"
        try:
            with server() as http:
                candidates = [require(http.post("/candidates", json={"evaluate": False, "resume_text":
                    f"Synthetic Contact\nEmail: {address}\nPhone: +919876543210\nSkills: Python SQL"}))["candidate_id"]
                    for address in (email, other_email)]
                headers = [{"X-Candidate-Key": require(http.post(f"/candidates/{cid}/auth-key"))["access_key"]} for cid in candidates]
                a, b = headers
                def start(method="otp_email", destination=email, status=200):
                    return require(http.post("/portal/verifications", headers=a,
                        json={"method": method, "destination": destination}), status)
                def confirm(vid, value, headers=a, status=200):
                    return require(http.post(f"/portal/verifications/{vid}/confirm", headers=headers, json={"code": value}), status)
                def rows(): return require(http.get("/portal/verifications", headers=a))["verifications"]

                checks.check("migrated app and two candidate actors start", True)
                checks.check("wrong destination refuses before delivery", start(destination=other_email, status=400)["detail"])
                checks.check("phone delivery is explicitly unavailable", start("otp_phone", "+919876543210", 503) == {"detail": "phone_unavailable"})
                first = start()["verification"]; first_code = latest_code(mailbox, email); codes.append(first_code)
                checks.check("actual email capture supplies code without plaintext echo", bool(first_code) and first["status"] == "pending")
                checks.check("cooldown refuses a second send", "recently" in start(status=429)["detail"])
                before = challenges()
                control.write_text("unavailable", encoding="utf-8")
                checks.check("unavailable email refuses without new secret", start(status=503) == {"detail": "email_unavailable"} and challenges() == before)
                control.write_text("partial", encoding="utf-8")
                mutate(first["id"], last_sent_at=datetime.now(timezone.utc)-timedelta(seconds=61))
                checks.check("provider acknowledgment failure is not sent success", start(status=503) == {"detail": "email_send_failed"})
                partial_code = latest_code(mailbox, email); codes.append(partial_code)
                failed = next(v for v in reversed(rows()) if v["status"] == "failed")
                checks.check("provider-rejected captured code cannot confirm", confirm(failed["id"], partial_code, status=400)["detail"])
                checks.check("failure rollback retains exactly the previous active secret", challenges() == before)
                checks.check("foreign confirmation remains indistinguishable 404", confirm(first["id"], first_code, headers=b, status=404) == {"detail": "verification not found"})
                checks.check("previous code still confirms after failed resend", confirm(first["id"], first_code)["status"] == "verified")
                checks.check("confirmation is single use", confirm(first["id"], first_code, status=400)["detail"])
                control.write_text("failed", encoding="utf-8")
                checks.check("unsent request fails with safe response", start(status=503) == {"detail": "email_send_failed"} and challenges() == 0)
                control.write_text("ok", encoding="utf-8")
                retry = start()["verification"]; retry_code = latest_code(mailbox, email); codes.append(retry_code)
                mutate(retry["id"], expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
                checks.check("expired delivered code is refused", confirm(retry["id"], retry_code, status=400)["detail"] == "challenge expired")
                exhausted = start()["verification"]; exhausted_code = latest_code(mailbox, email); codes.append(exhausted_code)
                mutate(exhausted["id"], attempts=5)
                checks.check("exhausted correct code is refused", confirm(exhausted["id"], exhausted_code, status=400)["detail"] == "too many attempts")
                final = start(); final_code = latest_code(mailbox, email); codes.append(final_code)
                checks.check("successful API never exposes raw code", final.get("debug_code") is None)
                completed = confirm(final["verification"]["id"], final_code)

            with server() as http:
                saved = require(http.get("/portal/verifications", headers=a))
                checks.check("restart preserves actual outcome and advisory contact assurance", any(v == completed for v in saved["verifications"]) and saved["assurance"]["level"] == 2 and saved["assurance"]["advisory"])
                require(http.delete("/portal/me", headers=a))
                checks.check("erasure refuses the old candidate and preserves the second", http.get("/portal/verifications", headers=a).status_code == 401 and http.get("/portal/verifications", headers=b).status_code == 200)
                checks.check("erasure leaves no candidate challenge secrets", challenges() == 0)
            logged = (scratch / "server.log").read_text(encoding="utf-8")
            checks.check("actual rendered server logs omit destinations and codes", all(value not in logged for value in [email, other_email, *codes]))
        finally:
            engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
