"""S8.4 Phase B smoke: the screening surface over real HTTP, key-less.

Boots uvicorn on a migrated scratch DB and drives the whole sprint the way a
customer does: register a batch without evaluating anything, process it in
bounded calls, watch derived progress, read the ranked queue and the roll-up,
page with a cursor, prove cross-org 404s on every route, delete, and confirm
the materialization route un-breaks the board.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path, and S8.4 Phase A
then found FIVE more smokes doing the same thing.

The checks this sprint exists to protect:
  * registration_is_evaluation_free -- 500 resumes cannot be evaluated inside
    one request (there is no worker anywhere in app/), so upload must only
    insert rows. A regression here is a request that times out in production.
  * a_failed_item_does_not_stop_the_batch -- a batch of 500 with one corrupt
    file has to finish.
  * queue_row_carries_no_match_identities -- THE structural guarantee. The
    queue read-model is built from batch_items ALONE, so no Report (a
    cross-corpus object) is ever on the org-plane read path. Asserted on a
    batch whose report genuinely HAS farm matches, seeded from another
    organisation -- the exact shape that leaked in Phase A.
  * cross_org_404_matches_absence -- another org's batch answers byte for byte
    like a batch that never existed. A 403, or a body differing by one byte,
    confirms it exists.
  * a_stolen_cursor_reaches_nothing -- a cursor is a sort POSITION, not a
    capability.

Runs with email_provider=capture, so codes land in a file. Selected by EXPLICIT
config, never by fallback; prod refuses to boot with it (app/core/boot.py).

Run from repo root:   python scripts/smoke_s84b.py
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

PORT = 8086
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

_GENUINE_LINES = (
    (FIXTURES / "genuine_genai_resume.txt").read_text(encoding="utf-8").splitlines()
)


def _resume(email: str, note: str = "") -> str:
    """The genuine fixture with a contact block spliced in after the header.

    After the first line rather than before it, so heuristic extraction's
    name parsing (which reads line one) is unaffected.
    """
    lines = [_GENUINE_LINES[0], f"Email: {email}"] + _GENUINE_LINES[1:]
    if note:
        lines += ["", note]
    return "\n".join(lines)


FARM_A = (FIXTURES / "farm_genai_resume_a.txt").read_text(encoding="utf-8")
FARM_B = (FIXTURES / "farm_genai_resume_b.txt").read_text(encoding="utf-8")

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
    """The newest code addressed to THIS recipient -- deliberately not "the last
    line", which silently hands one person's code to another client."""
    for raw in reversed(mailbox.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(raw)
        if msg["to"].strip().lower() == email.strip().lower():
            return re.search(r"\b(\d{6})\b", msg["body"]).group(1)
    raise AssertionError(f"no code was sent to {email}")


def _drain(c: httpx.Client, key: dict, batch_id: str, cap: int = 40) -> dict:
    """Process until nothing remains. Bounded so a bug cannot spin forever."""
    last: dict = {}
    for _ in range(cap):
        r = c.post(f"/screening/batches/{batch_id}/process", headers=key)
        if r.status_code != 200:
            return {"error": r.text}
        last = r.json()
        if not last["remaining"]:
            break
    return last


def run_checks(c: httpx.Client, mailbox: Path) -> None:
    # ── 1. Two organisations, each with its own key ─────────────────────────
    def onboard(email: str, name: str) -> tuple[str, dict]:
        """Sign up in a THROWAWAY cookie jar, then hand back only the key.

        The session cookie must not survive into the rest of this smoke. CSRF
        keys on how the principal was established, not on which header was
        sent (S8.2), so a client holding a session cookie is CSRF-checked even
        when it also presents X-Org-Key -- and every subsequent POST here would
        answer 403. That is the rule working; this is the machine client, and a
        machine client has no cookies.
        """
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as jar:
            r = jar.post("/auth/org/signup",
                         json={"email": email, "organization_name": name})
            if r.status_code != 202:
                return "", {}
            v = jar.post("/auth/org/verify",
                         json={"email": email, "code": _code_for(mailbox, email)})
            org_id = v.json()["organization_id"]
        key = c.post(f"/ledger/orgs/{org_id}/api-key", headers=ADMIN_H).json()["api_key"]
        return org_id, {"X-Org-Key": key}

    org_a, key_a = onboard("ops@agency-a.example", "Agency A")
    org_b, key_b = onboard("ops@agency-b.example", "Agency B")
    check("two_orgs_with_their_own_keys", bool(org_a and org_b and key_a != key_b))

    # ── 2. Registration is evaluation-free ──────────────────────────────────
    before = len(c.get("/candidates", headers=ADMIN_H).json())
    reg = c.post("/screening/batches", headers=key_a, json={
        "name": "Q3 intake", "domain": "genai",
        "items": [
            {"resume_text": _resume("priya.nair@example.in")},
            {"resume_text": _resume("arjun.rao@example.in", "Note: second candidate.")},
            {"resume_text": "   "},  # the failing item -- check 5
        ],
    })
    batch = reg.json()
    if reg.status_code != 200:
        check("registration_is_evaluation_free", False, f"{reg.status_code} {reg.text[:200]}")
        return
    after = len(c.get("/candidates", headers=ADMIN_H).json())
    check("registration_is_evaluation_free",
          reg.status_code == 200 and batch["counts"]["pending"] == 3
          and batch["status"] == "pending" and after == before,
          f"candidates {before} -> {after}")
    bid = batch["id"]

    # ── 3. Processing is bounded ────────────────────────────────────────────
    first = c.post(f"/screening/batches/{bid}/process", headers=key_a).json()
    check("processing_is_bounded_and_resumable",
          first["processed"] + first["failed"] <= 5 and first["remaining"] >= 0,
          f"processed={first['processed']} failed={first['failed']} "
          f"remaining={first['remaining']}")
    final = _drain(c, key_a, bid)

    # ── 4. Progress is derived, not stored ──────────────────────────────────
    detail = c.get(f"/screening/batches/{bid}", headers=key_a).json()
    check("derived_progress_reaches_a_terminal_status",
          detail["counts"]["pending"] == 0 and detail["counts"]["processing"] == 0
          and detail["status"] == "partial",
          f"counts={detail['counts']} status={detail['status']}")

    # ── 5. A failed item does not stop the batch ────────────────────────────
    rows = c.get(f"/screening/batches/{bid}/queue", headers=key_a).json()["rows"]
    failed = [r for r in rows if r["status"] == "failed"]
    done = [r for r in rows if r["status"] == "done"]
    check("a_failed_item_does_not_stop_the_batch",
          len(failed) == 1 and failed[0]["error"] == "empty_resume" and len(done) == 2,
          f"done={len(done)} failed={len(failed)} err={failed[0]['error'] if failed else None}")

    # ── 6. The queue is ranked, and every row explains itself ───────────────
    scores = [r["risk_score"] if r["risk_score"] is not None else -1.0 for r in rows]
    check("queue_is_ranked_riskiest_first_with_reasons",
          scores == sorted(scores, reverse=True) and all(r["reason"] for r in rows),
          f"scores={scores}")

    # ── 7. The farm signal is present and identity-free ─────────────────────
    # Org B seeds a near-duplicate FIRST, so org A's screening has something to
    # find -- exactly the cross-tenant shape that leaked in Phase A.
    seeded = c.post("/screening/batches", headers=key_b, json={
        "name": "theirs", "domain": "genai",
        "items": [{"resume_text": FARM_A}],
    }).json()
    _drain(c, key_b, seeded["id"])
    mine = c.post("/screening/batches", headers=key_a, json={
        "name": "mine", "domain": "genai",
        "items": [{"resume_text": FARM_B}],
    }).json()
    _drain(c, key_a, mine["id"])
    farm_page = c.get(f"/screening/batches/{mine['id']}/queue", headers=key_a)
    farm_row = farm_page.json()["rows"][0]
    check("queue_row_carries_no_match_identities",
          "matches" not in farm_page.text
          and farm_row["signals"] is not None
          and farm_row["signals"]["farm_corpus_size"] >= 1,
          f"corpus_size={farm_row['signals']['farm_corpus_size']} "
          f"farm_band={farm_row['signals']['farm_band']}")

    # ── 8. The summary is counts only ───────────────────────────────────────
    summary = c.get(f"/screening/batches/{bid}/summary", headers=key_a)
    body = summary.text
    leaks = [k for k in ("candidate_id", "resume_id", "report_id", "reasoning")
             if k in body]
    check("summary_is_counts_only",
          summary.status_code == 200 and not leaks
          and summary.json()["n_screened"] == 2,
          f"leaked={leaks}")

    # ── 9. Cursor paging covers every row exactly once ──────────────────────
    p1 = c.get(f"/screening/batches/{bid}/queue?limit=2", headers=key_a).json()
    p2 = c.get(f"/screening/batches/{bid}/queue?cursor={p1['next_cursor']}",
               headers=key_a).json()
    ids = [r["item_id"] for r in p1["rows"] + p2["rows"]]
    check("cursor_paging_covers_every_row_once",
          bool(p1["next_cursor"]) and len(ids) == len(set(ids)) == 3,
          f"ids={len(ids)} unique={len(set(ids))}")

    # ── 10. Cross-org 404 on every batch route, matching absence ────────────
    absent = "00000000-0000-0000-0000-000000000000"
    mismatched = []
    for method, theirs, missing in (
        ("get", f"/screening/batches/{bid}", f"/screening/batches/{absent}"),
        ("get", f"/screening/batches/{bid}/queue", f"/screening/batches/{absent}/queue"),
        ("get", f"/screening/batches/{bid}/summary", f"/screening/batches/{absent}/summary"),
        ("post", f"/screening/batches/{bid}/process", f"/screening/batches/{absent}/process"),
        ("delete", f"/screening/batches/{bid}", f"/screening/batches/{absent}"),
    ):
        got = getattr(c, method)(theirs, headers=key_b)
        gone = getattr(c, method)(missing, headers=key_b)
        if got.status_code != 404 or got.text != gone.text:
            mismatched.append(f"{method.upper()} {theirs} -> {got.status_code}")
    check("cross_org_404_matches_absence", not mismatched, str(mismatched))

    # ── 11. A stolen cursor reaches none of the minting org's rows ──────────
    # NOT "returns nothing": org B has a batch of its own by this point, and a
    # page containing B's OWN work is correct. A cursor is a sort POSITION, so
    # replaying it merely positions inside B's own list. The property that
    # matters -- and the only one a leak would break -- is that none of A's
    # batches appear.
    a_ids = {b["id"] for b in c.get("/screening/batches", headers=key_a).json()["batches"]}
    stolen = c.get("/screening/batches?limit=1", headers=key_a).json()["next_cursor"]
    replayed = c.get(f"/screening/batches?cursor={stolen}", headers=key_b).json()
    b_ids = {b["id"] for b in replayed["batches"]}
    check("a_stolen_cursor_reaches_none_of_the_other_orgs_rows",
          bool(stolen) and not (a_ids & b_ids) and len(a_ids) >= 2,
          f"A owns {len(a_ids)}, B saw {sorted(b_ids)} with A's cursor")

    # ── 12. Delete really deletes ───────────────────────────────────────────
    gone = c.delete(f"/screening/batches/{bid}", headers=key_a)
    after_delete = c.get(f"/screening/batches/{bid}", headers=key_a)
    check("delete_removes_the_batch",
          gone.status_code == 200 and gone.json()["deleted"] is True
          and after_delete.status_code == 404)

    # ── 13. Materialization un-breaks the board ─────────────────────────────
    req_id = c.post("/jobs", headers=key_a, json={
        "title": "Senior Engineer", "must_have_skills": ["python"],
    }).json()["id"]
    pre = c.get(f"/jobs/{req_id}/board", headers=key_a).json()
    run = c.post("/features/materialize", headers=ADMIN_H, json={})
    post = c.get(f"/jobs/{req_id}/board", headers=key_a).json()
    check("materialization_un_breaks_the_board",
          pre["match"]["reason"] == "no_materialized_candidates"
          and run.status_code == 200 and run.json()["materialized"] >= 1
          and post["match"]["pool_size"] >= 1
          and post["match"]["reason"] is None,
          f"pre={pre['match']['reason']} materialized={run.json().get('materialized')} "
          f"pool_after={post['match']['pool_size']}")

    # ── 14. Comp answers one shape from both endpoints ──────────────────────
    est = c.post("/comp/estimate", headers=key_a, json={
        "title": "Senior Backend Engineer", "years_experience": 7,
    }).json()
    check("comp_estimate_returns_a_benchmark",
          "estimate" in est and est["requisition_band"] is None
          and est["position"] is None and est["delta_pct"] is None)

    # ── 15. A case-variant organisation name is refused at signup ───────────
    dup = c.post("/auth/org/signup",
                 json={"email": "someone@agency-a.example",
                       "organization_name": "AGENCY A"})
    check("a_case_variant_org_name_is_409_at_signup",
          dup.status_code == 409 and dup.json()["detail"] == "organization_name_taken",
          f"{dup.status_code} {dup.text[:60]}")


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    url = "sqlite:///" + (scratch / "smoke_s84b.db").as_posix()
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
        # MUST be memory: a persistent Chroma client hangs on this machine, and
        # a smoke that hangs is a smoke nobody runs.
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Pinned EMPTY on purpose: this smoke claims the no-key path works end
        # to end, and a developer with a real key in .env would otherwise ship
        # live billed calls from a test run (the S7.3 lesson, and the five
        # smokes Phase A found doing it).
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
        # Capture email, and cookies a plain-HTTP client will actually keep.
        "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": mailbox.as_posix(),
        "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax",
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not _wait_healthy(c):
                print("server never became healthy")
                return 1
            check("healthz", True)
            run_checks(c, mailbox)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} OK")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
