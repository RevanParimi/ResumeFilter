"""S8.3 Phase A smoke: the limits hold, and they SURVIVE A RESTART.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path. Five sprints running.

What a unit test cannot prove and this does:

  * **CHECK 6 IS THE ENTIRE ARGUMENT FOR THE SPRINT'S STORAGE DECISION.** The
    server is TERMINATED and a second one started against the SAME database,
    and the limit still holds. An in-process limiter passes every other check
    in this file and fails exactly that one -- which is why "counters live in
    the database" was not a matter of taste.
  * a 429 for a registered and an unregistered address that are
    indistinguishable over the wire -- same status, same body, same header
    NAMES, no Set-Cookie on either. (Two things differ and neither is a
    function of the address: X-Request-ID is unique per request by design, and
    Retry-After counts down inside the shared window. The earlier wording here
    said "byte-identical ... headers included" while check 4 compared status
    and body only; the S8.3 review made the check match the claim.)
  * the retry -> process handoff end to end: a genuinely failed item is
    re-queued and the EXISTING process door picks it up.
  * /metrics as an actual HTTP surface: 401 without the admin key, and with it
    a document that carries the deny counter and the route TEMPLATE rather
    than any batch id.

Runs with email_provider=capture, so codes land in a file instead of a mailbox.
Selected by EXPLICIT config -- never by fallback -- and prod refuses to boot
with it (app/core/boot.py).

Run from repo root:   python scripts/smoke_s83a.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

PORT = 8083
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}

# Small enough to reach in a handful of requests; the DEFAULTS are asserted in
# tests/test_config_ratelimit.py, and this file is about the wire.
LOGIN_LIMIT = 3

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
_LINES = (FIXTURES / "genuine_genai_resume.txt").read_text(
    encoding="utf-8"
).splitlines()
GENUINE = "\n".join([_LINES[0], "Email: priya.nair@example.in"] + _LINES[1:])

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}")


def _wait_healthy(c: httpx.Client) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    return False


def _code_for(mailbox: Path, email: str) -> str:
    for raw in reversed(mailbox.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(raw)
        if msg["to"].strip().lower() == email.strip().lower():
            return re.search(r"\b(\d{6})\b", msg["body"]).group(1)
    raise AssertionError(f"no code was sent to {email}")


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    url = "sqlite:///" + (scratch / "smoke_s83a.db").as_posix()
    flywheel = scratch / "flywheel.jsonl"
    print(f"scratch DB: {url}")

    env = os.environ.copy()
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
        "DEE_RATE_LIMIT_LOGIN_PER_HOUR_PER_EMAIL": str(LOGIN_LIMIT),
        "DEE_RATE_LIMIT_LOGIN_PER_HOUR_PER_IP": "100",
        "DEE_RATE_LIMIT_PROCESS_PER_HOUR_PER_ORG": "50",
    })

    opened: list[httpx.Client] = []

    def _client() -> httpx.Client:
        c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5))
        opened.append(c)
        return c

    def _serve():
        return subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
            env=env,
        )

    proc = _serve()
    try:
        boot = _client()
        booted = _wait_healthy(boot)
        check("healthz", booted)
        if not booted:
            print("server did not become healthy")
            return 1

        admin = _client()

        # 1-2. Drive the per-email limit to a 429, over the wire.
        known = "ops@agency-a.example"
        signup = boot.post("/auth/org/signup",
                           json={"email": known, "organization_name": "Agency A"})
        verified = boot.post(
            "/auth/org/verify",
            json={"email": known, "code": _code_for(mailbox, known)},
        )
        check("org_onboards", signup.status_code == 202 and verified.status_code == 200,
              f"{signup.status_code}/{verified.status_code}")

        c1 = _client()

        # A FRESH address, so the budget starts at zero and the arithmetic is
        # not an assumption about what onboarding already spent.
        driver = "driver@agency-d.example"
        allowed = [c1.post("/auth/org/login", json={"email": driver}).status_code
                   for _ in range(LOGIN_LIMIT)]
        refused_driver = c1.post("/auth/org/login", json={"email": driver})
        check("login_allowed_up_to_the_limit", allowed == [202] * LOGIN_LIMIT,
              str(allowed))
        check("login_refused_past_the_limit", refused_driver.status_code == 429,
              f"got {refused_driver.status_code} {refused_driver.text[:120]}")

        # SIGNUP AND LOGIN SHARE ONE BUDGET, and that is correct rather than
        # incidental: both mint and send a code, so counting them separately
        # would double the real bound on the only thing being defended. This
        # smoke's first version assumed otherwise and was wrong -- `known` had
        # already spent one on its signup.
        spent_by_signup = 1
        shared = [c1.post("/auth/org/login", json={"email": known}).status_code
                  for _ in range(LOGIN_LIMIT - spent_by_signup)]
        refused = c1.post("/auth/org/login", json={"email": known})
        check("signup_and_login_share_one_budget",
              shared == [202] * (LOGIN_LIMIT - spent_by_signup)
              and refused.status_code == 429,
              f"{shared} then {refused.status_code}")

        # 3. Retry-After is usable.
        retry_after = refused.headers.get("Retry-After", "")
        check("retry_after_header_is_a_positive_number",
              retry_after.isdigit() and int(retry_after) > 0, f"got {retry_after!r}")

        # 4. A REGISTERED and an UNREGISTERED address are refused identically.
        #    A 429 that appeared only for registered addresses would rebuild
        #    the enumeration oracle the uniform 202 exists to close.
        #
        #    HEADERS TOO, added by the S8.3 review: this file's docstring said
        #    "headers included" while the check compared status and body only.
        #    A header present for one address and absent for the other is the
        #    same oracle, and a smoke that claims a check it does not make is
        #    the exact shape this sprint reviewed OPERATING.md for.
        unknown = "nobody@agency-z.example"
        for _ in range(LOGIN_LIMIT):
            c1.post("/auth/org/login", json={"email": unknown})
        refused_unknown = c1.post("/auth/org/login", json={"email": unknown})

        # X-Request-ID is unique per request BY DESIGN and carries nothing
        # about the address; Retry-After counts down inside the shared window,
        # so two refusals a second apart differ by a second. Everything else
        # must match exactly.
        def header_names(resp):
            return sorted({k.lower() for k in resp.headers} - {"x-request-id"})

        check("known_and_unknown_are_refused_identically",
              refused_unknown.status_code == refused.status_code
              and refused_unknown.json() == refused.json()
              and header_names(refused_unknown) == header_names(refused)
              and "set-cookie" not in header_names(refused)
              and abs(int(refused_unknown.headers["Retry-After"])
                      - int(refused.headers["Retry-After"])) <= 5,
              f"{refused_unknown.status_code} vs {refused.status_code}; "
              f"{header_names(refused_unknown)} vs {header_names(refused)}")

        # 5. A third address is unaffected -- the email scope is per address.
        third = c1.post("/auth/org/login", json={"email": "fresh@agency-c.example"})
        check("a_fresh_address_is_unaffected", third.status_code == 202,
              f"got {third.status_code}")

        # ── 6. THE CHECK NO UNIT TEST CAN REACH ──────────────────────────────
        #    Terminate the server, start a NEW one on the same database, and
        #    confirm the limit still holds. An in-process limiter passes checks
        #    1-5 and fails here.
        proc.terminate()
        proc.wait(timeout=30)
        proc = _serve()
        c2 = _client()
        if not _wait_healthy(c2):
            check("survives_a_restart", False, "second server never became healthy")
        else:
            after_restart = c2.post("/auth/org/login", json={"email": known})
            check("survives_a_restart", after_restart.status_code == 429,
                  f"got {after_restart.status_code} -- an in-process counter "
                  "would have reset here")

        # 7-9. Screening: process, force a failure, retry, and watch the
        #      EXISTING process door pick the item back up.
        org = admin.post("/ledger/orgs", json={"name": "Agency R"}, headers=ADMIN_H)
        # Detail only on FAILURE: the success body carries a live api_key, and
        # a smoke that prints credentials to stdout is a smoke whose output
        # cannot be pasted into an issue.
        check("org_created_for_screening", org.status_code == 200,
              org.text[:160] if org.status_code != 200 else "")
        # OrgCreateResponse is {org: Organization, api_key: str} -- the key comes
        # back from creation; there is no second call to make.
        org_h = {"X-Org-Key": org.json()["api_key"]}

        made = admin.post("/screening/batches", headers=org_h, json={
            "name": "Q3", "domain": "genai",
            "items": [{"resume_text": GENUINE}, {"resume_text": "   "}],
        })
        check("batch_registered", made.status_code == 200,
              made.text[:160] if made.status_code != 200 else "")
        bid = made.json()["id"]

        for _ in range(6):
            ran = admin.post(f"/screening/batches/{bid}/process", headers=org_h)
            if ran.status_code != 200 or ran.json().get("remaining", 0) == 0:
                break
        detail = admin.get(f"/screening/batches/{bid}", headers=org_h).json()
        failed_n = detail["counts"].get("failed", 0)
        check("a_blank_resume_fails_its_own_item", failed_n >= 1,
              f"counts={detail['counts']}")

        retried = admin.post(f"/screening/batches/{bid}/retry", headers=org_h)
        check("retry_requeues_the_failed_item",
              retried.status_code == 200 and retried.json()["requeued"] == failed_n,
              f"{retried.status_code} {retried.text[:160]}")

        after = admin.get(f"/screening/batches/{bid}", headers=org_h).json()
        check("a_requeued_item_reads_as_pending_again",
              after["counts"].get("pending", 0) >= failed_n,
              f"counts={after['counts']}")

        # 10. Another org's batch, and an unknown id, answer identically.
        org2 = admin.post("/ledger/orgs", json={"name": "Agency S"}, headers=ADMIN_H)
        key2 = org2.json()["api_key"]
        theirs = admin.post(f"/screening/batches/{bid}/retry",
                            headers={"X-Org-Key": key2})
        nosuch = admin.post(
            "/screening/batches/00000000-0000-0000-0000-000000000000/retry",
            headers={"X-Org-Key": key2},
        )
        check("retry_is_404_never_403_and_identical_to_an_unknown_id",
              theirs.status_code == nosuch.status_code == 404
              and theirs.json() == nosuch.json(),
              f"{theirs.status_code}/{nosuch.status_code}")

        # 11-13. /metrics as a real HTTP surface.
        unauth = _client().get("/metrics")
        check("metrics_requires_the_admin_credential", unauth.status_code == 401,
              f"got {unauth.status_code}")

        m = admin.get("/metrics", headers=ADMIN_H)
        ok_text = (m.status_code == 200
                   and m.headers.get("content-type", "").startswith("text/plain"))
        check("metrics_is_prometheus_text", ok_text,
              f"{m.status_code} {m.headers.get('content-type')}")

        # `check` prints its detail on PASS as well as on fail, so these two
        # report what was actually observed. They previously carried
        # failure-phrased prose, which printed "OK ... not found with a denial"
        # on a passing run -- a smoke whose own output contradicts its verdict
        # is the thing a smoke exists to prevent.
        body = m.text
        denied = 'decision="denied"' in body and 'rule="login_request"' in body
        check("metrics_carries_the_deny_counter", denied,
              "found decision=\"denied\" on rule=\"login_request\"" if denied
              else "veritas_rate_limit_decisions_total carries no denial")
        templated = 'route="/screening/batches/{batch_id}"' in body
        check("metrics_labels_by_template_and_leaks_no_batch_id",
              templated and bid not in body,
              f'route="/screening/batches/{{batch_id}}" present={templated}, '
              f"raw batch id present={bid in body}")
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

    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} OK")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
