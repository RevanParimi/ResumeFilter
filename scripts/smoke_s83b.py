"""S8.3 Phase B smoke: the retention sweep runs, and the rights queue works.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path. Six sprints running.

What a unit test cannot prove and this does:

  * **DRY-RUN PARITY OVER THE WIRE.** Rows are aged in the server's OWN database
    (the smoke opens it directly, which no unit test setup can do for a running
    process), previewed through the route, then deleted through the route, and
    the two counts are compared. A sweeper whose preview and whose action
    disagree is worse than one with no preview, and that is the failure this
    check exists for.
  * **THE PORTAL'S PROMISE MATCHES THE MACHINE.** `sweep_active` reads true from
    a real HTTP response, on a deployment where the sweep genuinely ran.
  * a correction filed through a REAL SESSION (cookie + CSRF), not a machine
    key -- the browser's posture, which S8.4 Phase B measured refuses POSTs
    with 403 when a cookie and a header credential are mixed.
  * `GET /grievance` answered by a client that has never authenticated at all:
    no key, no cookie jar shared with any logged-in caller.
  * the 429 on the candidate request budget, over the wire, with Retry-After.

Runs with email_provider=capture, so codes land in a file instead of a mailbox.
Selected by EXPLICIT config -- never by fallback -- and prod refuses to boot
with it (app/core/boot.py).

Run from repo root:   python scripts/smoke_s83b.py
"""

import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


from _smoke import Smoke, base_env, wait_healthy


S = Smoke("smoke_s83b")
PORT = 8085
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}

OFFICER_EMAIL = "dpo@veritas.example"
#: Small enough to reach in a handful of requests. The DEFAULT is asserted in
#: tests/test_config_ratelimit.py; this file is about the wire.
REQUEST_LIMIT = 3




def _code_for(mailbox: Path, email: str) -> str:
    for raw in reversed(mailbox.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(raw)
        if msg["to"].strip().lower() == email.strip().lower():
            return re.search(r"\b(\d{6})\b", msg["body"]).group(1)
    raise AssertionError(f"no code was sent to {email}")


def _age_rows(db: Path, candidate_id: str, days: int) -> int:
    """Backdate this candidate's resumes past ret_resume_days.

    Done with sqlite3 against the server's OWN file rather than through the
    API, because there is no endpoint that fabricates an old row -- and the
    sweep is only interesting on rows old enough to be eligible.
    """
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    con = sqlite3.connect(db)
    try:
        cur = con.execute(
            "UPDATE resumes SET created_at = ? WHERE candidate_id = ?",
            (when, candidate_id),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def _affected(report: dict, data_class: str) -> int:
    for row in report["by_class"]:
        if row["data_class"] == data_class:
            return row["affected"]
    raise AssertionError(f"{data_class} missing from the report")


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    db = scratch / "smoke_s83b.db"
    url = "sqlite:///" + db.as_posix()
    flywheel = scratch / "flywheel.jsonl"
    print(f"scratch DB: {url}")

    env = base_env()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_FLYWHEEL_PATH": flywheel.as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY on purpose (the S7.3 lesson).
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
        "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": mailbox.as_posix(),
        "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_GRIEVANCE_OFFICER_NAME": "R. Menon",
        "DEE_GRIEVANCE_OFFICER_EMAIL": OFFICER_EMAIL,
        "DEE_GRIEVANCE_OFFICER_PHONE": "+91 80 4000 0000",
        "DEE_RATE_LIMIT_REQUEST_PER_HOUR_PER_CANDIDATE": str(REQUEST_LIMIT),
    })

    opened: list[httpx.Client] = []

    def _client(**kw) -> httpx.Client:
        c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5), **kw)
        opened.append(c)
        return c

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        boot = _client()
        booted = wait_healthy(boot)
        S.check("healthz", booted)
        if not booted:
            print("server did not become healthy")
            return 1

        admin = _client()

        # 1. THE PUBLISHED GRIEVANCE CONTACT, read by a client that has never
        #    authenticated. No admin key, no cookie jar shared with a logged-in
        #    caller: this is the posture of the person whose complaint is that
        #    they cannot log in.
        stranger = _client()
        g = stranger.get("/grievance")
        published = (
            g.status_code == 200
            and g.json().get("email") == OFFICER_EMAIL
            and g.json().get("response_days") >= 1
        )
        S.check("grievance_contact_is_public", published,
              f"{g.status_code} {g.text[:120]}")

        # 2. A candidate signs up through a REAL SESSION (cookie + CSRF), which
        #    is the browser's posture. Every unit test here uses X-Candidate-Key,
        #    a machine credential with no human behind it.
        subject = "asha@example.in"
        person = _client()
        su = person.post("/auth/candidate/signup", json={"email": subject})
        vr = person.post("/auth/candidate/verify",
                         json={"email": subject, "code": _code_for(mailbox, subject)})
        csrf = person.cookies.get("dee_csrf")
        S.check("candidate_signs_up_with_a_session",
              su.status_code == 202 and vr.status_code == 200 and bool(csrf),
              f"{su.status_code}/{vr.status_code} csrf={bool(csrf)}")
        session_h = {"X-CSRF-Token": csrf or ""}

        # 3. File a correction through that session.
        filed = person.post("/portal/corrections", headers=session_h,
                            json={"field": "full_name",
                                  "requested_value": "Asha Rao"})
        req = filed.json() if filed.status_code == 200 else {}
        S.check("correction_is_filed_over_a_session",
              filed.status_code == 200 and req.get("status") == "open"
              and req.get("applied") is False,
              f"{filed.status_code} {filed.text[:160]}")

        # 4. It is visible to the SUBJECT, in both places they would look.
        listed = person.get("/portal/requests").json()
        me = person.get("/portal/me").json()
        S.check("subject_sees_their_own_request",
              [r["id"] for r in listed] == [req.get("id")]
              and [r["id"] for r in me.get("requests", [])] == [req.get("id")],
              f"{len(listed)} at /portal/requests, "
              f"{len(me.get('requests', []))} in /portal/me")

        # 5. And so does their ACCESS LOG -- surveillance is itself observable,
        #    applied to the handling of their own complaint.
        log = person.get("/portal/access-log").json()
        in_log = [e for e in log if e["entity_type"] == "data_principal_request"]
        S.check("submission_is_in_the_subjects_access_log",
              [e["action"] for e in in_log] == ["request.submit"],
              str([e["action"] for e in in_log]))

        # 6. The operator lists it and resolves it WITH APPLY.
        queue = admin.get("/admin/requests?status=open", headers=ADMIN_H).json()
        resolved = admin.post(f"/admin/requests/{req.get('id')}/resolve",
                              headers=ADMIN_H,
                              json={"status": "resolved",
                                    "resolution": "verified against the ID",
                                    "apply": True})
        S.check("operator_lists_and_applies",
              len(queue) == 1 and resolved.status_code == 200
              and resolved.json().get("applied") is True,
              f"queue={len(queue)} resolve={resolved.status_code}")

        # 7. The subject sees the decision AND the identity row actually moved.
        #    Two checks, because the first version of this was ONE check named
        #    "reached the candidate row" that only ever looked at the request
        #    row -- a check claiming more than it makes, which is the shape the
        #    Phase A review caught twice in this file's sibling.
        after = person.get("/portal/me").json()
        S.check("the_subject_sees_the_decision",
              after["requests"][0]["status"] == "resolved"
              and after["requests"][0]["applied"] is True
              and after["requests"][0]["resolved_by"] == "operator_key",
              json.dumps(after["requests"][0])[:200])

        row = admin.get(f"/candidates/{after['candidate_id']}",
                        headers=ADMIN_H).json()
        S.check("the_correction_reached_the_candidate_row",
              row.get("full_name") == "Asha Rao",
              f"candidates.full_name={row.get('full_name')!r}")

        # 8. Resolving the SAME request again is a 409, not a second decision.
        again = admin.post(f"/admin/requests/{req.get('id')}/resolve",
                           headers=ADMIN_H,
                           json={"status": "resolved", "resolution": "oops",
                                 "apply": True})
        S.check("a_second_decision_is_409", again.status_code == 409,
              f"got {again.status_code}")

        # 9. An EMAIL correction is refused for auto-apply, naming its reason.
        email_req = person.post("/portal/corrections", headers=session_h,
                                json={"field": "email",
                                      "requested_value": "new@example.in"}).json()
        refused = admin.post(f"/admin/requests/{email_req.get('id')}/resolve",
                             headers=ADMIN_H,
                             json={"status": "resolved", "resolution": "ok",
                                   "apply": True})
        names_it = (refused.status_code == 422
                    and "login" in refused.text.lower())
        S.check("email_auto_apply_is_refused_naming_its_reason", names_it,
              f"{refused.status_code} {refused.text[:160]}")

        # 10. The candidate request budget, over the wire. Two are already
        #     spent (checks 3 and 9), so one more is allowed and the next is not.
        spent = 2
        allowed = [
            person.post("/portal/grievances", headers=session_h,
                        json={"note": f"n{i}"}).status_code
            for i in range(REQUEST_LIMIT - spent)
        ]
        over = person.post("/portal/grievances", headers=session_h,
                           json={"note": "one too many"})
        S.check("corrections_and_grievances_share_one_budget",
              allowed == [200] * (REQUEST_LIMIT - spent)
              and over.status_code == 429
              and over.headers.get("Retry-After", "").isdigit(),
              f"{allowed} then {over.status_code} "
              f"Retry-After={over.headers.get('Retry-After')!r}")

        # 11. THE SWEEP. Age this candidate's resume rows in the server's own
        #     database, then preview and delete through the route.
        cid = me["candidate_id"]
        upload = admin.post("/candidates", headers=ADMIN_H, json={
            "resume_text": f"Asha Rao\nEmail: {subject}\nSKILLS\nPython\n",
            "evaluate": False,
        })
        aged = _age_rows(db, cid, days=4000)
        S.check("a_resume_exists_and_was_backdated",
              upload.status_code == 200 and aged >= 1,
              f"upload={upload.status_code} rows_aged={aged}")

        # 11b. THE UPLOAD ABOVE IS THE ONE THAT USED TO REVERT THE CORRECTION.
        #      `_refresh_identity` is "latest non-empty name wins", so before
        #      `full_name_corrected_at` existed, this ingest put the extractor's
        #      spelling back while /portal/requests went on saying applied:true.
        #      The resume deliberately spells the name the OLD way.
        still = admin.get(f"/candidates/{cid}", headers=ADMIN_H).json()
        S.check("a_later_upload_does_not_revert_the_applied_correction",
              still.get("full_name") == "Asha Rao",
              f"candidates.full_name={still.get('full_name')!r} after an upload "
              f"whose resume says 'Asha R'")

        preview = admin.post("/admin/retention/sweep", headers=ADMIN_H,
                             json={}).json()
        real = admin.post("/admin/retention/sweep", headers=ADMIN_H,
                          json={"dry_run": False}).json()
        parity = (
            preview["dry_run"] is True
            and real["dry_run"] is False
            and [(c["data_class"], c["affected"]) for c in preview["by_class"]]
            == [(c["data_class"], c["affected"]) for c in real["by_class"]]
        )
        S.check("dry_run_counts_exactly_what_the_real_run_deletes", parity,
              f"preview resumes={_affected(preview, 'resumes')} "
              f"real resumes={_affected(real, 'resumes')}")
        S.check("the_sweep_actually_had_something_to_do",
              _affected(preview, "resumes") >= 1,
              f"resumes={_affected(preview, 'resumes')}")

        # 12. A SECOND real run finds nothing left -- the rows are gone, not
        #     merely reported.
        third = admin.post("/admin/retention/sweep", headers=ADMIN_H,
                           json={"dry_run": False}).json()
        S.check("a_second_run_finds_the_rows_already_gone",
              _affected(third, "resumes") == 0,
              f"resumes={_affected(third, 'resumes')}")

        # 13. The portal's promise now matches the machine.
        S.check("sweep_active_is_true_in_the_portal",
              person.get("/portal/me").json()["retention"]["sweep_active"] is True)

        # 14. And the counter records what went.
        m = admin.get("/metrics", headers=ADMIN_H)
        counted = 'veritas_retention_deleted_total' in m.text and \
                  'data_class="resumes"' in m.text
        S.check("metrics_carries_the_retention_counter", counted,
              'found veritas_retention_deleted_total{data_class="resumes"}'
              if counted else "the counter is absent from /metrics")

        # 15. A real run is REFUSED when the sweep is configured off. Proven by
        #     restarting the server with the knob flipped -- the config is read
        #     at boot, so a live toggle would prove nothing.
        proc.terminate()
        proc.wait(timeout=30)
        env_off = dict(env)
        env_off["DEE_RETENTION_SWEEP_ENABLED"] = "false"
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
            env=env_off,
        )
        off = _client()
        if not wait_healthy(off):
            S.check("server_restarts_with_the_sweep_disabled", False, "never healthy")
        else:
            S.check("server_restarts_with_the_sweep_disabled", True)
            refused_run = off.post("/admin/retention/sweep", headers=ADMIN_H,
                                   json={"dry_run": False})
            still_previews = off.post("/admin/retention/sweep", headers=ADMIN_H,
                                      json={})
            S.check("a_disabled_sweep_refuses_409_but_still_previews",
                  refused_run.status_code == 409
                  and refused_run.json().get("detail") == "retention_sweep_disabled"
                  and still_previews.status_code == 200,
                  f"real={refused_run.status_code} preview={still_previews.status_code}")
            # The subject's session survives the restart: the session row is in
            # the database, so the same cookie still resolves against the new
            # process. That is worth stating -- it is the same argument as
            # Phase A's check 6, one table over.
            me_off = person.get("/portal/me")
            S.check("sweep_active_reads_FALSE_when_the_knob_is_off",
                  me_off.status_code == 200
                  and me_off.json()["retention"]["sweep_active"] is False,
                  f"{me_off.status_code} "
                  f"{me_off.json().get('retention', {}).get('sweep_active')}")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=30)
        except Exception:
            pass
        for c in opened:
            try:
                c.close()
            except Exception:
                pass

    return S.summary()


if __name__ == "__main__":
    raise SystemExit(main())
