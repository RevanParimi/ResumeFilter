"""The screening UI's contract with the API, driven the way a BROWSER drives it.

`frontend/` has no CI and no test runner (PI-8 decision 0.1), so the wiring is
verified by driving the real API over real HTTP in the browser's own posture:
a cross-origin `Origin` header, a session COOKIE rather than `X-Org-Key`, and
`X-CSRF-Token` on every unsafe method. That posture is the point --
`smoke_s84b.py` deliberately uses a machine credential in a throwaway cookie
jar, because a client holding BOTH a cookie and an org key is CSRF-checked and
every POST answers 403 (S8.2: CSRF keys on how the principal was established,
not on which header arrived). The UI is the other client, and nothing else
exercises it.

Every check is named for what a regression would break ON SCREEN. Three earn
their place beyond "the route still answers":

  * a_corrupt_pdf_names_an_item_index -- the UI translates `item 37:` back into
    the file's name, because "item 37" is meaningless to somebody looking at
    400 filenames. It parses that prefix with a regex, so this asserts the
    REGEX ITSELF against the live message. If the wording moves, the screen
    silently stops naming files and this goes red first.
  * a_queue_row_carries_no_persons_name -- the queue screen tells the user, in
    prose, that rows hold no names by design. That sentence has to be TRUE:
    this searches the raw page for a name that is definitely in the resume.
  * an_outcome_is_unreachable_from_an_org_session -- the report screen dropped
    four buttons on the claim that this route is admin-plane. A claim a screen
    makes about the API is a claim worth pinning.

Key-less by construction: DEE_OPENROUTER_API_KEY is pinned empty, for the same
reason every smoke pins it (S7.3, and the five smokes S8.4 Phase A caught
making live billed calls).

Run from repo root:   python scripts/check_ui_screening_contract.py
"""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

PORT = 8095
BASE = f"http://127.0.0.1:{PORT}"
UI_ORIGIN = "http://localhost:5173"
ADMIN = "ui-contract-admin-key"

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
GENUINE = (FIXTURES / "genuine_genai_resume.txt").read_text(encoding="utf-8")

# The exact regex frontend/Veritas.dc.html uses in `_nameIndex`. Kept here as a
# literal so the two cannot drift apart quietly.
UI_ITEM_INDEX_RE = re.compile(r"^item (\d+):\s*(.*)$")

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}")


def _resume(name: str, email: str) -> str:
    lines = GENUINE.splitlines()
    return "\n".join([name, f"Email: {email}"] + lines[1:])


def minimal_pdf_b64(lines: list[str]) -> str:
    """A hand-built one-page PDF carrying real extractable text.

    pypdf can WRITE a blank page but not text, and the point here is to prove
    the browser's `readAsDataURL` -> `resume_pdf_b64` path decodes to something
    the extractor can actually work with.
    """
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")

    content = (
        "BT /F1 11 Tf 40 780 Td 14 TL\n"
        + "\n".join(f"({esc(line)}) Tj T*" for line in lines)
        + "\nET"
    ).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += (
        b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref).encode() + b"\n%%EOF\n"
    )
    return base64.b64encode(bytes(out)).decode()


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


class Browser:
    """One tab. Holds the cookie jar and echoes the CSRF cookie like api.js.

    Deliberately mirrors `frontend/api.js`: `credentials:"include"` on every
    call (httpx keeps the jar), and `X-CSRF-Token` read from the cookie AT CALL
    TIME rather than cached from login -- a re-login rotates it.
    """

    def __init__(self) -> None:
        self.c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(300, connect=5))

    def _headers(self, unsafe: bool, csrf: bool = True) -> dict:
        h = {"Origin": UI_ORIGIN}
        if unsafe and csrf:
            token = self.c.cookies.get("dee_csrf")
            if token:
                h["X-CSRF-Token"] = token
        return h

    def get(self, path: str) -> httpx.Response:
        return self.c.get(path, headers=self._headers(False))

    def post(self, path: str, body=None, csrf: bool = True) -> httpx.Response:
        return self.c.post(path, json=body if body is not None else {},
                           headers=self._headers(True, csrf))

    def delete(self, path: str, csrf: bool = True) -> httpx.Response:
        return self.c.delete(path, headers=self._headers(True, csrf))

    def close(self) -> None:
        self.c.close()


def run_checks(mailbox: Path) -> None:
    b = Browser()

    # ── 1. The preflight the browser sends before any POST ──────────────────
    pre = b.c.options("/screening/batches", headers={
        "Origin": UI_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrf-token",
    })
    check("preflight_allows_the_ui_origin",
          pre.status_code in (200, 204)
          and pre.headers.get("access-control-allow-origin") == UI_ORIGIN
          and pre.headers.get("access-control-allow-credentials") == "true",
          f"{pre.status_code} allow-origin={pre.headers.get('access-control-allow-origin')}")

    # ── 2. Signup -> verify, the UI's whole login ───────────────────────────
    email = "delivery@sampoorna.example"
    signup = b.post("/auth/org/signup", {"email": email, "organization_name": "Sampoorna Staffing"})
    verified = b.post("/auth/org/verify", {"email": email, "code": _code_for(mailbox, email)})
    check("signup_and_verify_set_both_cookies",
          signup.status_code == 202 and verified.status_code == 200
          and bool(b.c.cookies.get("dee_session")) and bool(b.c.cookies.get("dee_csrf")),
          f"signup={signup.status_code} verify={verified.status_code}")

    me = b.get("/auth/me")
    check("auth_me_on_the_cookie_alone",
          me.status_code == 200 and me.json()["kind"] == "org",
          f"{me.status_code} {me.text[:80]}")

    # ── 3. The first screen a new customer ever sees ────────────────────────
    empty = b.get("/screening/batches")
    check("a_new_org_sees_an_empty_batch_page_not_an_error",
          empty.status_code == 200 and empty.json()["batches"] == []
          and empty.json()["next_cursor"] is None,
          f"{empty.status_code} {empty.text[:80]}")

    # ── 4. CSRF is real on the browser path ─────────────────────────────────
    naked = b.post("/screening/batches",
                   {"name": "no csrf", "domain": "genai",
                    "items": [{"resume_text": _resume("Test", "t@example.in")}]},
                   csrf=False)
    check("a_post_without_the_csrf_header_is_403",
          naked.status_code == 403 and "csrf" in naked.text.lower(),
          f"{naked.status_code} {naked.text[:90]}")

    # ── 5. Registration takes both item shapes and evaluates nothing ────────
    pdf_item = minimal_pdf_b64([
        "Kavya Iyer", "Email: kavya.iyer@example.in", "Senior Data Engineer, Pune",
        "Built Airflow ingest for a 400-table warehouse.",
    ])
    # SEVEN items, over `screening_max_items_per_call` (5) on purpose. A batch
    # that fits in one call cannot prove the loop loops -- the first draft used
    # four and the "bounded and terminates" check passed after a single call,
    # which is this repo's recurring shape: a check that inspects less than it
    # appears to.
    others = ["Meera Sundaram", "Vikram Joshi", "Ananya Bose"]
    reg = b.post("/screening/batches", {
        "name": "Wipro DE — August intake", "domain": "genai",
        "items": [
            {"resume_text": _resume("Priya Nandakumar", "priya.n@example.in")},
            {"resume_text": _resume("Arjun Rao", "arjun.rao@example.in")},
            {"resume_pdf_b64": pdf_item},
            {"resume_text": "   "},          # fails at PROCESSING, not registration
        ] + [
            {"resume_text": _resume(n, n.split()[0].lower() + "@example.in")}
            for n in others
        ],
    })
    ok_reg = reg.status_code == 200
    batch = reg.json() if ok_reg else {}
    check("register_accepts_text_and_pdf_and_evaluates_nothing",
          ok_reg and batch["counts"]["pending"] == 7 and batch["counts"]["done"] == 0
          and batch["status"] == "pending",
          f"{reg.status_code} {reg.text[:120] if not ok_reg else batch['counts']}")
    if not ok_reg:
        return
    bid = batch["id"]

    # ── 6. The driver: bounded calls until `remaining` is 0 ─────────────────
    calls, guard = [], 0
    while guard < 40:
        guard += 1
        res = b.post(f"/screening/batches/{bid}/process")
        if res.status_code != 200:
            calls.append({"error": f"{res.status_code} {res.text[:80]}"})
            break
        got = res.json()
        calls.append(got)
        if not got["remaining"]:
            break
    bounded = all("error" not in c and c["processed"] + c["failed"] <= 5 for c in calls)
    check("the_process_loop_is_bounded_and_terminates",
          bounded and len(calls) >= 2 and calls[0]["remaining"] > 0
          and calls[-1].get("remaining") == 0,
          f"{len(calls)} calls, remaining per call="
          f"{[c.get('remaining') for c in calls]}")

    detail = b.get(f"/screening/batches/{bid}").json()
    check("derived_progress_is_terminal_after_the_loop",
          detail["counts"]["pending"] == 0 and detail["counts"]["processing"] == 0
          and detail["status"] == "partial",
          f"counts={detail['counts']} status={detail['status']}")

    # ── 7. The queue the screen renders ─────────────────────────────────────
    qres = b.get(f"/screening/batches/{bid}/queue")
    rows = qres.json()["rows"]
    scores = [r["risk_score"] if r["risk_score"] is not None else -1.0 for r in rows]
    check("queue_rows_are_ranked_and_each_carries_a_reason",
          scores == sorted(scores, reverse=True) and all(r["reason"] for r in rows),
          f"scores={scores}")

    # The screen SAYS, in prose, that rows hold no names. Prove the sentence.
    raw_queue = qres.text
    leaked = [n for n in ("Priya Nandakumar", "Kavya Iyer", "Arjun Rao",
                          "priya.n@example.in", "kavya.iyer@example.in")
              if n in raw_queue]
    check("a_queue_row_carries_no_persons_name", not leaked, f"leaked={leaked}")

    failed = [r for r in rows if r["status"] == "failed"]
    check("a_failed_row_carries_a_code_not_a_verdict",
          len(failed) == 1 and failed[0]["error"] == "empty_resume"
          and failed[0]["risk_score"] is None
          and failed[0]["reason"].startswith("could not be screened"),
          f"{[ (r['status'], r['error']) for r in rows ]}")

    # ── 8. The summary, which is the page a customer screenshots ────────────
    sres = b.get(f"/screening/batches/{bid}/summary")
    summary = sres.json()
    known = {"ai_generation", "cross_field", "resume_farm"}
    check("summary_signal_ids_are_the_three_the_ui_can_label",
          sres.status_code == 200
          and {s["signal"] for s in summary["top_signals"]} <= known
          and summary["n_screened"] == sum(summary["by_risk_band"].values()),
          f"signals={[s['signal'] for s in summary['top_signals']]} "
          f"n_screened={summary['n_screened']} bands={summary['by_risk_band']}")
    check("the_summary_carries_no_names_or_ids_beyond_its_own_batch",
          not any(n in sres.text for n in ("Priya", "Kavya", "Arjun", "can_", "rep_"))
          and summary["batch_id"] == bid,
          "counts and enum members only")

    # ── 9. Paging, exactly as the "Load more" button does it ────────────────
    p1 = b.get(f"/screening/batches/{bid}/queue?limit=2").json()
    p2 = b.get(f"/screening/batches/{bid}/queue?limit=2&cursor={p1['next_cursor']}").json()
    ids1 = {r["item_id"] for r in p1["rows"]}
    ids2 = {r["item_id"] for r in p2["rows"]}
    check("cursor_paging_returns_disjoint_pages",
          len(p1["rows"]) == 2 and bool(p1["next_cursor"]) and ids2 and not (ids1 & ids2),
          f"page1={len(ids1)} page2={len(ids2)} overlap={ids1 & ids2}")

    # A cursor is opaque, so anything a client hand-builds is a bug on the
    # client's side and must be a 422 rather than a 500. Note what is NOT here:
    # base64 of `[1, "x"]` is a perfectly VALID cursor (a float-ish score and a
    # row id) and positions inside the caller's own batch -- the first draft of
    # this check asserted 422 on it and was measuring its own assumption. The
    # forgeries below are the ones the decoder can actually tell apart.
    def _b64(payload) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(payload).encode()).decode().rstrip("=")

    forgeries = {
        "not base64 at all": "%%%not-base64%%%",
        "base64 of non-JSON": base64.urlsafe_b64encode(b"hello").decode().rstrip("="),
        "wrong arity": _b64([1]),
        "score is a string": _b64(["high", "x"]),
        "id is a number": _b64([0.5, 7]),
    }
    got = {
        label: b.get(f"/screening/batches/{bid}/queue?cursor={value}").status_code
        for label, value in forgeries.items()
    }
    check("every_forged_cursor_shape_is_422_not_500",
          set(got.values()) == {422}, f"{got}")

    # ── 10. The report drill-in ─────────────────────────────────────────────
    drillable = [r for r in rows if r["report_id"]]
    rep = b.get(f"/screening/reports/{drillable[0]['report_id']}")
    body = rep.json()
    fab = body.get("fabrication_risk") or {}
    check("report_drill_in_returns_the_full_report",
          rep.status_code == 200 and "verdicts" in body and "components" in fab
          and body["advisory"] is True and body["human_review_required"] is True,
          f"{rep.status_code} verdicts={len(body.get('verdicts', []))} "
          f"components={len(fab.get('components', []))}")

    farm = body.get("resume_farm") or {}
    matches = farm.get("matches", [])
    check("farm_matches_keep_similarity_and_lose_identity",
          all(m["candidate_id"] is None and m["resume_id"] is None
              and m["similarity"] is not None for m in matches),
          f"{len(matches)} matches, ids present: "
          f"{[m for m in matches if m['candidate_id'] or m['resume_id']]}")

    # ── 11. The refusals the upload screen renders ──────────────────────────
    corrupt = b.post("/screening/batches", {
        "name": "corrupt", "domain": "genai",
        "items": [
            {"resume_text": _resume("Fine", "fine@example.in")},
            {"resume_pdf_b64": base64.b64encode(b"this is not a pdf").decode()},
        ],
    })
    parsed = UI_ITEM_INDEX_RE.match(str(corrupt.json().get("detail", "")))
    check("a_corrupt_pdf_names_an_item_index_the_ui_can_translate",
          corrupt.status_code == 422 and parsed is not None and parsed.group(1) == "1",
          f"{corrupt.status_code} detail={corrupt.json().get('detail')!r}")

    still_empty = b.get("/screening/batches").json()["batches"]
    check("a_refused_registration_leaves_nothing_behind",
          all(x["name"] != "corrupt" for x in still_empty),
          f"{[x['name'] for x in still_empty]}")

    over = b.post("/screening/batches", {
        "name": "too big", "domain": "genai",
        "items": [{"resume_text": "x"} for _ in range(501)],
    })
    cap_msg = str(over.json().get("detail", ""))
    check("an_over_cap_batch_names_the_cap_the_ui_shows_verbatim",
          over.status_code == 422 and re.search(r"\b\d+\b", cap_msg) is not None
          and "at most" in cap_msg,
          f"{over.status_code} {cap_msg!r}")

    # ── 12. The batch list, whose FIRST row the UI auto-selects ─────────────
    second = b.post("/screening/batches", {
        "name": "later batch", "domain": "genai",
        "items": [{"resume_text": _resume("Meera S", "meera@example.in")}],
    })
    listing = b.get("/screening/batches").json()["batches"]
    check("the_batch_list_is_newest_first",
          second.status_code == 200 and listing[0]["id"] == second.json()["id"],
          f"first={listing[0]['name']!r} of {[x['name'] for x in listing]}")

    # ── 13. Another organisation's batch is absent, not forbidden ───────────
    other = Browser()
    other_email = "ops@rival.example"
    other.post("/auth/org/signup", {"email": other_email, "organization_name": "Rival Staffing"})
    other.post("/auth/org/verify", {"email": other_email, "code": _code_for(mailbox, other_email)})
    theirs = other.get(f"/screening/batches/{bid}")
    theirs_q = other.get(f"/screening/batches/{bid}/queue")
    absent = other.get("/screening/batches/bat_doesnotexist")
    check("another_orgs_batch_is_404_byte_for_byte_like_absence",
          theirs.status_code == 404 and theirs_q.status_code == 404
          and theirs.text == absent.text,
          f"{theirs.status_code}/{theirs_q.status_code} body_matches={theirs.text == absent.text}")
    other.close()

    # ── 14. The claim the report screen makes about outcomes ────────────────
    outcome = b.post(f"/report/{drillable[0]['report_id']}/outcome",
                     {"outcome": "verified_genuine"})
    check("an_outcome_is_unreachable_from_an_org_session",
          outcome.status_code == 401,
          f"{outcome.status_code} {outcome.text[:80]}")

    # ── 15. Delete: the DPDP path, and it needs CSRF like everything else ───
    no_csrf = b.delete(f"/screening/batches/{bid}", csrf=False)
    gone = b.delete(f"/screening/batches/{bid}")
    after = b.get(f"/screening/batches/{bid}")
    check("delete_needs_csrf_and_then_really_deletes",
          no_csrf.status_code == 403 and gone.status_code == 200
          and gone.json()["deleted"] is True and after.status_code == 404,
          f"no_csrf={no_csrf.status_code} delete={gone.status_code} after={after.status_code}")

    b.close()


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    url = "sqlite:///" + (scratch / "ui_contract.db").as_posix()
    print(f"scratch DB: {url}")

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        # A persistent Chroma client hangs on this machine, and a check that
        # hangs is a check nobody runs.
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY: this asserts the key-less path, and a real key in .env
        # would otherwise ship live billed calls from a verification run.
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
        "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": mailbox.as_posix(),
        # The three settings that default to broken-for-a-browser. All local;
        # prod refuses to boot with any of them (app/core/boot.py).
        "DEE_CORS_ALLOWED_ORIGINS": json.dumps([UI_ORIGIN]),
        "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax",
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not _wait_healthy(c):
                print("server never became healthy")
                return 1
        check("healthz", True)
        run_checks(mailbox)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} OK")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
