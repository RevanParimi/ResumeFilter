"""S8.6 smoke: the production shape, proven as far as a machine with no Docker
and no Postgres can prove it.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path. Six sprints running.

What a unit test cannot prove and this does:

  * **THE EIGHT REFUSALS ARE PROCESS EXITS.** Unit tests prove
    `verify_launch_config` raises. Only starting the real process proves the
    raise is not caught, logged and swallowed somewhere between `create_app`
    and uvicorn's worker -- which is the only way a refusal actually protects a
    deployment.
  * **THE REFUSALS RUN BEFORE ANY DATABASE SOCKET OPENS.** Check 1. Without it,
    a green refusal suite is equally consistent with "the config is wrong in a
    way that exits early", which is the vacuous-guard shape this repo keeps
    finding.
  * **SMTPEmail DELIVERS.** It is selected by config no test selects, because
    selecting it means opening a socket. `app/services/email.py`'s own
    docstring says S7.1's L2 assurance "has NEVER delivered an OTP to a human";
    it had not delivered to anything. A local SMTP sink gives it one, and a
    candidate signup runs end to end: composed, accepted by a server, read back
    out of the delivered message, verified, session established.
  * the UI served BY THIS API, same origin, with no credential.
  * `GET /` advertising a DERIVED endpoints list over the wire.
  * the retention CLI -- the door a Railway cron will call -- against the
    running server's own database.

Run from repo root:   python scripts/smoke_s86.py
"""

import contextlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx


from _smoke import (
    Smoke, base_env, boot_until_exit, client, uvicorn_argv, wait_healthy,
)


S = Smoke("smoke_s86")
ROOT = Path(__file__).resolve().parents[1]

#: Distinct from every other smoke's port so two can run at once.
REFUSAL_PORT = 8092
PORT = 8093
SMTP_PORT = 8094
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-s86-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}




def _prod_env(**over: str) -> dict:
    """A prod-shaped environment that satisfies ALL EIGHT refusals.

    The Postgres URL points at nothing on purpose. Refusal 2 tests
    `candidates_db_url.startswith("sqlite")` -- a STRING -- and
    `verify_launch_config` runs in the lifespan BEFORE `upgrade_to_head`. So a
    syntactically valid URL satisfies refusal 2 and the process still exits on
    the refusal under test, never having opened a socket. That ordering is
    load-bearing for this whole section, so check 1 asserts it directly.
    """
    prod = {
        "DEE_ENV": "prod",
        "DEE_API_AUTH_KEY": ADMIN,
        "DEE_SESSION_COOKIE_SECURE": "true",
        "DEE_CORS_ALLOWED_ORIGINS": "[]",
        "DEE_EMAIL_PROVIDER": "smtp",
        "DEE_EMAIL_SMTP_HOST": "127.0.0.1",
        "DEE_RATE_LIMIT_ENABLED": "true",
        "DEE_GRIEVANCE_OFFICER_EMAIL": "dpo@example.com",
    }
    # merged, not `**prod, **over`: a caller overriding one of these -- which
    # is the whole point of the REFUSALS table -- is a duplicate keyword and a
    # TypeError, not an override.
    prod.update(over)
    return base_env(None, "postgresql+psycopg://u:p@127.0.0.1:1/nope", **prod)


#: One variable flipped per case. A config with TWO faults that exits proves
#: only that it exits. Each needle is a string from the SPECIFIC refusal, so a
#: process that died for any other reason does not pass.
REFUSALS = [
    ("api_auth_key",       {"DEE_API_AUTH_KEY": ""},                      "DEE_API_AUTH_KEY"),
    ("prod_on_sqlite",     {"DEE_CANDIDATES_DB_URL": "sqlite:///./x.db"}, "DEE_CANDIDATES_DB_URL"),
    ("insecure_cookie",    {"DEE_SESSION_COOKIE_SECURE": "false"},        "session_cookie_secure"),
    ("wildcard_cors",      {"DEE_CORS_ALLOWED_ORIGINS": '["*"]'},         "cors_allowed_origins"),
    ("capture_email",      {"DEE_EMAIL_PROVIDER": "capture",
                            "DEE_EMAIL_CAPTURE_PATH": "./data/x.jsonl"},  "email_provider=capture"),
    ("rate_limit_off",     {"DEE_RATE_LIMIT_ENABLED": "false"},           "rate_limit_enabled"),
    ("no_grievance_email", {"DEE_GRIEVANCE_OFFICER_EMAIL": ""},           "grievance_officer_email"),
    ("no_email_provider",  {"DEE_EMAIL_PROVIDER": "null"},                "no working email provider"),
]


def _run_refusal_checks() -> None:
    # CHECK 1. The refusals run BEFORE anything opens a database socket, and a
    # CORRECT prod config therefore gets PAST all eight and reaches the
    # database. Without this, a green refusal suite below is equally consistent
    # with "this config is wrong in a way that exits early".
    #
    # ASSERTED POSITIVELY, and that is the whole point of the check. The first
    # version was `code != 0 and "LaunchConfigError" not in out`, which passed
    # -- and passed for the WRONG REASON. Measured: against a dead Postgres the
    # process does not fail, it HANGS in the lifespan (psycopg's connect has no
    # timeout), so `code != 0` was satisfied only because the harness killed it
    # at the deadline. A check whose evidence is "we shot it and it did not
    # complain" would have passed just as happily against a process that booted
    # cleanly and served traffic. So it now requires uvicorn's own
    # "Waiting for application startup" marker -- proof the lifespan RAN, which
    # is where verify_launch_config lives -- and a timeout is the expected
    # outcome rather than an accident.
    code, out = boot_until_exit(uvicorn_argv(REFUSAL_PORT), _prod_env(), timeout=30.0, cwd=ROOT)
    S.check("refusals_run_before_any_db_connection",
          "Waiting for application startup" in out
          and "LaunchConfigError" not in out
          and code != 0,
          detail=f"exit={code} (-1 = hung on the dead DB, which is the point)")

    for name, override, needle in REFUSALS:
        code, out = boot_until_exit(uvicorn_argv(REFUSAL_PORT), _prod_env(**override), cwd=ROOT)
        S.check(f"refusal_{name}_exits_the_process",
              code != 0 and needle.lower() in out.lower(),
              detail=f"exit={code}")


# ── part 2: a local SMTP sink, and SMTPEmail's first delivery ────────────────


class _SMTPSink(threading.Thread):
    """Enough of RFC 5321 to accept one message and remember it.

    aiosmtpd would do this in four lines and is NOT in requirements.txt; adding
    a package to PRODUCTION requirements to support a smoke is the wrong trade.

    No AUTH and no STARTTLS, and neither is laziness: SMTPEmail calls
    smtp.login() only when email_smtp_user is non-empty (app/services/email.py),
    so the smoke leaves it empty and sets DEE_EMAIL_SMTP_STARTTLS=false.
    Offering capabilities nothing exercises would be untested code in a test.
    """

    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        self.messages: list[str] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", port))
        self._sock.listen(8)

    def run(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                try:
                    self._serve(conn)
                except OSError:
                    pass

    def _serve(self, conn: socket.socket) -> None:
        f = conn.makefile("rwb")
        f.write(b"220 localhost smoke-sink\r\n")
        f.flush()
        body: list[bytes] = []
        in_data = False
        while True:
            line = f.readline()
            if not line:
                return
            if in_data:
                if line.strip() == b".":
                    self.messages.append(b"".join(body).decode("utf-8", "replace"))
                    body, in_data = [], False
                    f.write(b"250 OK\r\n")
                    f.flush()
                else:
                    body.append(line)
                continue
            cmd = line.strip().upper()
            if cmd.startswith((b"EHLO", b"HELO")):
                f.write(b"250 localhost\r\n")
            elif cmd.startswith(b"DATA"):
                in_data = True
                f.write(b"354 go ahead\r\n")
            elif cmd.startswith(b"QUIT"):
                f.write(b"221 bye\r\n")
                f.flush()
                return
            else:
                f.write(b"250 OK\r\n")
            f.flush()

    def stop(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def main() -> int:
    _run_refusal_checks()

    scratch = Path(tempfile.mkdtemp())
    db = scratch / "smoke_s86.db"
    url = "sqlite:///" + db.as_posix()
    print(f"scratch DB: {url}")

    # SAID OUT LOUD, because a smoke that silently proves less than its name
    # implies is the overclaiming check Phase B caught. The serving phase
    # cannot be env=prod: prod refuses SQLite (refusal 2) and this machine has
    # no Postgres. env=prod on Postgres is covered by CI's `postgres` job and
    # the image by CI's `image` job -- neither of which has ever run.
    print("\nNOTE: the serving phase runs at DEE_ENV=staging, not prod. prod "
          "refuses SQLite (refusal 2) and this machine has no Postgres. Every "
          "OTHER prod value is set. See DEPLOY.md section 0.\n")

    sink = _SMTPSink(SMTP_PORT)
    sink.start()

    env = _prod_env(
        DEE_ENV="staging",
        DEE_CANDIDATES_DB_URL=url,
        DEE_FLYWHEEL_PATH=(scratch / "flywheel.jsonl").as_posix(),
        # Plain HTTP to localhost, so a Secure cookie would never be stored.
        # This is the ONE prod value the serving phase cannot keep.
        DEE_SESSION_COOKIE_SECURE="false",
        DEE_SESSION_COOKIE_SAMESITE="lax",
        DEE_EMAIL_PROVIDER="smtp",
        DEE_EMAIL_SMTP_HOST="127.0.0.1",
        DEE_EMAIL_SMTP_PORT=str(SMTP_PORT),
        DEE_EMAIL_SMTP_STARTTLS="false",
        DEE_EMAIL_SMTP_USER="",
        DEE_EMAIL_FROM="veritas@example.com",
    )

    stack = contextlib.ExitStack()

    def _client(**kw) -> httpx.Client:
        """Closed by the ExitStack, not by a hand-rolled list and a bare
        `except Exception: pass` -- which swallowed exactly the close errors
        worth seeing."""
        return stack.enter_context(client(BASE, **kw))

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env,
    )
    try:
        api = _client(headers=ADMIN_H)
        booted = wait_healthy(api)
        S.check("healthz", booted)
        if not booted:
            print("server did not become healthy")
            return 1

        # A COMPLETE login over a REAL SMTP conversation.
        email = "delivery.test@example.in"
        r = api.post("/auth/candidate/signup", json={"email": email})
        S.check("signup_accepted", r.status_code == 202, detail=str(r.status_code))

        for _ in range(60):
            if sink.messages:
                break
            time.sleep(0.25)
        S.check("smtp_sink_received_a_message", bool(sink.messages),
              detail=f"{len(sink.messages)} message(s)")

        delivered = sink.messages[-1] if sink.messages else ""
        code_match = re.search(r"\b(\d{6})\b", delivered)
        S.check("the_delivered_message_contains_a_usable_code",
              code_match is not None)
        # The envelope is part of the delivery, not decoration: a message that
        # arrives addressed to nobody is not a delivered login code.
        S.check("the_delivered_message_is_addressed_to_the_signup",
              email in delivered and "veritas@example.com" in delivered)

        if code_match is not None:
            person = _client()
            r = person.post("/auth/candidate/verify",
                            json={"email": email, "code": code_match.group(1)})
            S.check("verify_with_the_delivered_code_establishes_a_session",
                  r.status_code == 200 and "dee_session" in r.cookies,
                  detail=str(r.status_code))

        # ── part 3: the UI, the derived root list, metrics, the CLI ──────────

        # The UI is served BY THE API, same origin -- the posture that ships.
        r = api.get("/ui/api.js")
        S.check("the_ui_is_served_same_origin",
              r.status_code == 200 and "veritas" in r.text[:400].lower(),
              detail=str(r.status_code))

        # It must not require a credential: a login page behind a login is
        # unreachable by the person who needs it.
        anon = _client()
        S.check("the_ui_needs_no_credential",
              anon.get("/ui/api.js").status_code == 200)

        # api.js must carry the same-origin DEFAULT into the container, not
        # just into the repo. Task 5 has no pytest coverage at all.
        S.check("the_served_api_js_defaults_to_its_own_origin",
              'var DEFAULT_BASE = "";' in r.text,
              detail="localhost default would break a deployed UI")

        # GET / no longer advertises a hand-maintained list (S8.6 section 6).
        listed = " ".join(api.get("/").json()["endpoints"])
        S.check("root_advertises_the_screening_surface", "/screening/batches" in listed)
        S.check("root_advertises_metrics", "/metrics" in listed)
        S.check("root_advertises_the_phase_b_rights_routes",
              "/portal/grievances" in listed and "/admin/requests" in listed)
        S.check("root_does_not_advertise_the_static_mount", "/ui" not in listed)

        # /metrics is admin-gated and labels by route TEMPLATE.
        m = api.get("/metrics")
        S.check("metrics_responds", m.status_code == 200, detail=str(m.status_code))
        S.check("metrics_labels_by_route_template",
              "veritas_http_requests_total" in m.text)

        # The retention CLI -- the door the Railway cron calls -- against the
        # SERVER'S OWN database, which the web process migrated on boot.
        cli = subprocess.run(
            [sys.executable, "-m", "app.retention.sweep"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
        )
        S.check("retention_cli_previews_cleanly", cli.returncode == 0,
              detail=cli.stderr[-200:])
        if cli.returncode == 0:
            report = json.loads(cli.stdout.strip().splitlines()[-1])
            S.check("retention_report_is_the_last_line_and_is_a_dry_run",
                  report.get("dry_run") is True)

        # And the refusal that keeps a cron log readable: a database nothing
        # has migrated exits 3 with a sentence, not a traceback.
        fresh = dict(env)
        fresh["DEE_CANDIDATES_DB_URL"] = (
            "sqlite:///" + (scratch / "never_migrated.db").as_posix()
        )
        cold = subprocess.run(
            [sys.executable, "-m", "app.retention.sweep", "--apply"],
            cwd=ROOT, env=fresh, capture_output=True, text=True, timeout=300,
        )
        S.check("retention_cli_refuses_an_unmigrated_database",
              cold.returncode == 3 and "Traceback" not in cold.stderr,
              detail=f"exit={cold.returncode}")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=30)
        except Exception:
            pass
        sink.stop()
        stack.close()

    return S.summary()


if __name__ == "__main__":
    raise SystemExit(main())
