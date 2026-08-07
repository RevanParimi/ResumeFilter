"""S5.3 smoke: boot uvicorn on a migrated scratch DB, create two orgs (admin) +
their X-Org-Keys, POST one candidate, create a job requisition, and assert
GET /jobs/{id}/board -> 422 before the pool is materialized (empty pool).
Re-boot, materialize the candidate's core_v1 vector directly (as smoke_s51.py
does), and exercise the employer dashboard over HTTP (LLM-free): the pipeline
overview, the lean board (200, non-empty pool, advisory comp), the drill-in
card's per-section consent degradation (consent_required -> no_data on grant
-> consent_required on revoke), a cross-org board 404, and an unknown-candidate
card 404. Run from the repo root:
python scripts/smoke_s53.py
"""

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.candidates.store import build_candidate_store
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.store import build_feature_store
from app.ledger.store import build_ledger_store
from app.reports.store import build_report_store

PORT = 8053
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

RESUME = (
    "Strong Dev\nEmail: strong@example.com\n"
    "EXPERIENCE\n- Senior Engineer, Acme (2013 - Present)\n"
    "SKILLS\nPython, Django\nNotice period: 30 days\n"
)


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s53.db").as_posix()
    reports = (scratch / "reports.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": reports,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        # Key-less BY CONSTRUCTION: this repo's .env carries a real key,
        # so without this a bare run makes live BILLED calls from a smoke
        # that claims to prove the no-key path (S7.3 recorded this trap).
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}
    state: dict[str, str] = {}

    # ── Boot 1: admin plane setup + pre-materialization 422 ─────────────────
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not _wait_healthy(c):
                print("FAIL server never became healthy")
                return 1

            org_id = c.post("/ledger/orgs", json={"name": "Acme"},
                            headers=admin_h).json()["org"]["id"]
            org_key = c.post(f"/ledger/orgs/{org_id}/api-key",
                             headers=admin_h).json()["api_key"]
            org2_id = c.post("/ledger/orgs", json={"name": "Beta"},
                             headers=admin_h).json()["org"]["id"]
            org2_key = c.post(f"/ledger/orgs/{org2_id}/api-key",
                              headers=admin_h).json()["api_key"]

            cand_id = c.post("/candidates", json={"resume_text": RESUME},
                             headers=admin_h).json()["candidate_id"]

            org_h = {"X-Org-Key": org_key}
            req = c.post("/jobs", headers=org_h, json={
                "title": "Backend Engineer",
                "must_have_skills": ["python", "django"],
                "comp_band": {"ctc_min": 1_500_000, "ctc_max": 2_000_000},
            }).json()
            req_id = req["id"]

            pre_board = c.get(f"/jobs/{req_id}/board", headers=org_h)
            checks["board -> 422 before materialization (empty pool)"] = (
                pre_board.status_code == 422
            )

            state.update(org_id=org_id, org_key=org_key, org2_key=org2_key,
                        cand_id=cand_id, req_id=req_id)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    # ── In-process: materialize the candidate's core_v1 vector directly ────
    settings = Settings(_env_file=None, openrouter_api_key="", candidates_db_url=url,
                        vectorstore_backend="memory")
    cs = build_candidate_store(settings)
    ls = build_ledger_store(settings)
    rs = build_report_store(settings)
    fs = build_feature_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)
    now = datetime.now(timezone.utc)

    mv = materialize_candidate(state["cand_id"], view=view, registry=reg, as_of=now,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    fs.upsert_vector(mv)

    # ── Boot 2: dashboard endpoints over HTTP ───────────────────────────────
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not _wait_healthy(c):
                print("FAIL server never became healthy (2nd boot)")
                return 1

            org_h = {"X-Org-Key": state["org_key"]}
            org2_h = {"X-Org-Key": state["org2_key"]}
            req_id = state["req_id"]
            cand_id = state["cand_id"]

            # 1. Overview: one open requisition.
            overview = c.get("/dashboard/overview", headers=org_h).json()
            checks["overview total_requisitions == 1"] = overview["total_requisitions"] == 1
            checks["overview by_status == {open: 1}"] = overview["by_status"] == {"open": 1}

            # 2. Board: now materialized -> 200, non-empty pool, advisory comp.
            board = c.get(f"/jobs/{req_id}/board", headers=org_h)
            checks["board -> 200 after materialization"] = board.status_code == 200
            board_body = board.json()
            checks["board match.pool_size >= 1"] = board_body["match"]["pool_size"] >= 1
            checks["board comp.advisory is True"] = board_body["comp"]["advisory"] is True

            # 3. Card without consent: 200, all sections consent_required.
            card0 = c.get(f"/candidates/{cand_id}/card", headers=org_h)
            checks["card -> 200 without consent"] = card0.status_code == 200
            body0 = card0.json()
            checks["card reputation consent_required (no grant)"] = (
                body0["reputation"]["status"] == "consent_required"
            )
            checks["card coding_rounds consent_required (no grant)"] = (
                body0["coding_rounds"]["status"] == "consent_required"
            )
            checks["card records consent_required (no grant)"] = (
                body0["records"]["status"] == "consent_required"
            )

            # 4. Grant ledger_read for the org -> sections resolve to no_data
            #    (consent present, nothing submitted yet).
            grant_id = c.post(
                f"/ledger/candidates/{cand_id}/consent", headers=admin_h,
                json={"purpose": "ledger_read", "org_id": state["org_id"]},
            ).json()["id"]

            card1 = c.get(f"/candidates/{cand_id}/card", headers=org_h).json()
            checks["card reputation no_data after grant"] = (
                card1["reputation"]["status"] == "no_data"
            )
            checks["card coding_rounds no_data after grant"] = (
                card1["coding_rounds"]["status"] == "no_data"
            )
            checks["card records no_data after grant"] = (
                card1["records"]["status"] == "no_data"
            )

            # 5. Revoke -> all sections back to consent_required (symmetric with
            #    the post-grant check: revocation must gate every section).
            c.post(f"/ledger/consent/{grant_id}/revoke", headers=admin_h)
            card2 = c.get(f"/candidates/{cand_id}/card", headers=org_h).json()
            checks["card reputation consent_required after revoke"] = (
                card2["reputation"]["status"] == "consent_required"
            )
            checks["card coding_rounds consent_required after revoke"] = (
                card2["coding_rounds"]["status"] == "consent_required"
            )
            checks["card records consent_required after revoke"] = (
                card2["records"]["status"] == "consent_required"
            )

            # 6. Cross-org board -> 404 (second org never owned this req).
            xorg_board = c.get(f"/jobs/{req_id}/board", headers=org2_h)
            checks["cross-org board -> 404"] = xorg_board.status_code == 404

            # 7. Unknown candidate card -> 404.
            unknown = c.get("/candidates/does-not-exist/card", headers=org_h)
            checks["unknown candidate card -> 404"] = unknown.status_code == 404
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
