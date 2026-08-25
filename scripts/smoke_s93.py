"""S9.3 smoke: refusals are findable in a REAL server's logs.

What a unit test cannot prove and this does:
  * the handlers are installed in the app uvicorn actually serves, not only in
    one a fixture built;
  * the refusal line is JSON on stdout, as a log shipper would receive it --
    the unit tests assert on captured dicts, which is a different artifact and
    is exactly the distinction that let the OTP-leak guard read as green while
    checking an empty string;
  * `X-Request-ID` on the response is the SAME id as on the refusal line, so
    the correlation OPERATING.md §10d sells to an operator actually works;
  * a submitted secret does not reach the log through the 422 path.

Run from the repo root:   python scripts/smoke_s93.py
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

S = Smoke("smoke_s93")
PORT = 8093
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}
ROOT = Path(__file__).resolve().parent.parent
SECRET = "alice@example.in-SECRET-OTP-123456"


def main() -> int:
    # A plain mkdtemp, not a context manager: on Windows the just-terminated
    # uvicorn can still hold the sqlite file open, and auto-cleanup races that.
    scratch = Path(tempfile.mkdtemp(prefix="smoke_s93_"))
    url = f"sqlite:///{(scratch / 's93.db').as_posix()}"
    # DEE_API_AUTH_KEY, not DEE_ADMIN_API_KEY -- the first attempt used the
    # latter, every admin call 401'd, and half this smoke reported FAIL for a
    # reason that had nothing to do with logging.
    env = base_env(scratch, url, DEE_API_AUTH_KEY=ADMIN, DEE_LOG_JSON="true")

    # A FILE, never subprocess.PIPE: the server runs while we drive it, and a
    # full pipe buffer would deadlock the very process under test.
    logfile = scratch / "server.log"
    rid = ""
    with open(logfile, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            uvicorn_argv(PORT), env=env, cwd=str(ROOT), stdout=fh,
            stderr=subprocess.STDOUT, text=True,
        )
        try:
            with client(BASE, headers=ADMIN_H) as c:
                if not S.check("server_healthy", wait_healthy(c)):
                    return S.summary()

                r = c.get("/report/rep_does_not_exist")
                S.check("refusal_status_404", r.status_code == 404, f"HTTP {r.status_code}")
                S.check("body_still_has_detail", "detail" in r.json())
                rid = r.headers.get("X-Request-ID", "")
                S.check("response_carries_request_id", bool(rid))

                # Scanner noise -- must be labelled __unmatched__, not by path.
                c.get("/no/such/route/aaa")
                c.get("/no/such/route/bbb")

                # The 422 path, carrying a secret that must not be logged.
                v = c.post("/evaluate", json={"resume_text": {"nested": SECRET}})
                S.check("validation_status_422", v.status_code == 422, f"HTTP {v.status_code}")

                # Let the server flush stdout into the file.
                time.sleep(1.5)
        finally:
            proc.terminate()
            proc.wait(timeout=30)

    text = logfile.read_text(encoding="utf-8", errors="replace")
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                pass

    refusals = [line for line in lines if line.get("event") == "request_refused"]
    invalids = [line for line in lines if line.get("event") == "request_invalid"]

    S.check("json_lines_parsed", bool(lines), f"{len(lines)} parsed")
    S.check("refusal_line_emitted", bool(refusals), f"{len(refusals)} found")

    matched = [r for r in refusals if r.get("status") == 404 and r.get("route") != "__unmatched__"]
    S.check("matched_refusal_has_status", bool(matched))
    S.check(
        "matched_refusal_labelled_by_template",
        bool(matched) and "{" in matched[0].get("route", ""),
        matched[0].get("route", "") if matched else "none",
    )
    S.check("matched_refusal_has_reason", bool(matched) and bool(matched[0].get("reason")))
    S.check("matched_refusal_is_warning", bool(matched) and matched[0].get("level") == "warning")
    S.check(
        "request_id_correlates",
        any(r.get("request_id") == rid for r in refusals),
        f"caller got {rid or '(none)'}",
    )

    unmatched = [r for r in refusals if r.get("route") == "__unmatched__"]
    S.check("unmatched_collapses_to_one_label", len(unmatched) >= 2, f"{len(unmatched)} found")
    S.check(
        "unmatched_logs_at_info",
        bool(unmatched) and all(r.get("level") == "info" for r in unmatched),
    )
    S.check("raw_scanner_path_not_a_label", not any("aaa" in str(r.get("route", "")) for r in refusals))

    S.check("validation_line_emitted", bool(invalids), f"{len(invalids)} found")
    S.check("validation_names_the_field", bool(invalids) and bool(invalids[0].get("fields")))
    S.check("secret_not_in_logs", SECRET not in text)
    S.check("otp_fragment_not_in_logs", "SECRET-OTP" not in text)

    return S.summary()


if __name__ == "__main__":
    sys.exit(main())
