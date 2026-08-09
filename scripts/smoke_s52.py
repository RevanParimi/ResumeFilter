"""S5.2 smoke: boot uvicorn on a migrated scratch DB and exercise comp
intelligence over HTTP (LLM-free). Admin creates an org + X-Org-Key and
candidates; the org submits consent-gated observed offers and reads advisory
comp estimates + a requisition benchmark. Proves: static-only floor, the
observed blend once >= k offers exist (k-anonymity floor), requisition
benchmark below/at market, revocation dropping an offer from the aggregate, and
DPDP erasure tipping the aggregate back below k. Run from the repo root:
python scripts/smoke_s52.py
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

PORT = 8052
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
OFFERED_AT = datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat()


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def _make_candidate(c, admin_h, tag: str) -> str:
    text = f"{tag} Dev\nEmail: {tag}@example.com\nSKILLS\nPython\n"
    return c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()["candidate_id"]


def _grant_write(c, admin_h, cand_id, org_id) -> str:
    return c.post(
        f"/ledger/candidates/{cand_id}/consent", headers=admin_h,
        json={"purpose": "ledger_write", "org_id": org_id},
    ).json()["id"]


def _submit_offer(c, org_h, cand_id, *, role="backend_engineer", seniority="senior",
                  tier="metro", fixed=4_000_000.0):
    return c.post("/ledger/offers", headers=org_h, json={
        "candidate_id": cand_id, "role_family": role, "seniority": seniority,
        "city_tier": tier, "ctc_fixed": fixed, "offered_at": OFFERED_AT,
    })


def _estimate(c, org_h, title, years):
    # S8.4 Phase B: POST /comp/estimate answers a CompBenchmark WRAPPING the
    # estimate -- the same shape GET /jobs/{id}/comp has always returned.
    return c.post("/comp/estimate", headers=org_h,
                  json={"title": title, "years_experience": years}).json()["estimate"]


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s52.db").as_posix()
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
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

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
            org_key = c.post(f"/ledger/orgs/{org_id}/api-key", headers=admin_h).json()["api_key"]
            org_h = {"X-Org-Key": org_key}
            org2_id = c.post("/ledger/orgs", json={"name": "Beta"},
                             headers=admin_h).json()["org"]["id"]
            org2_key = c.post(f"/ledger/orgs/{org2_id}/api-key", headers=admin_h).json()["api_key"]

            # 1. Static-only estimate (no observed offers yet).
            static = _estimate(c, org_h, "Senior Backend Engineer", 7)
            checks["estimate advisory + static-only w/ no offers"] = (
                static["advisory"] is True and static["sources"] == ["static"]
            )
            checks["static band ordered p25<p50<p75"] = static["p25"] < static["p50"] < static["p75"]
            p50_static = static["p50"]

            # 2. Six backend/senior/metro offers; first proves the consent gate.
            backend = [_make_candidate(c, admin_h, f"be{i}") for i in range(6)]
            grants = {}
            pre_consent = _submit_offer(c, org_h, backend[0])
            checks["offer refused (403) before ledger_write consent"] = pre_consent.status_code == 403
            for i, cid in enumerate(backend):
                grants[cid] = _grant_write(c, admin_h, cid, org_id)
                r = _submit_offer(c, org_h, cid)
                if r.status_code != 200:
                    print(f"FAIL offer submit {i} -> {r.status_code} {r.text}")
                    return 1

            # 3. Blended estimate once >= k (5) offers exist.
            blended = _estimate(c, org_h, "Senior Backend Engineer", 7)
            checks["blend engages at >= k offers (sources static+observed)"] = (
                blended["sources"] == ["static", "observed"]
            )
            checks["n_observed reflects all 6 offers"] = blended["n_observed"] == 6
            checks["blended p50 pulled above static prior"] = blended["p50"] > p50_static
            checks["confidence rises above the static floor"] = blended["confidence"] > 0.30
            p50_blended = blended["p50"]

            # 4. Benchmark: a requisition band bracketing p50 reads "at market".
            req_at = c.post("/jobs", headers=org_h, json={
                "title": "Senior Backend Engineer", "must_have_skills": ["python"],
                "min_years_experience": 7, "location_tiers": ["metro"],
                "comp_band": {"ctc_min": p50_blended * 0.98, "ctc_max": p50_blended * 1.02},
            }).json()
            bench_at = c.get(f"/jobs/{req_at['id']}/comp", headers=org_h).json()
            checks["benchmark 'at' when band brackets p50"] = bench_at["position"] == "at"

            # 5. Benchmark: a low band reads "below".
            req_below = c.post("/jobs", headers=org_h, json={
                "title": "Senior Backend Engineer", "must_have_skills": ["python"],
                "min_years_experience": 7, "location_tiers": ["metro"],
                "comp_band": {"ctc_min": 800_000, "ctc_max": 900_000},
            }).json()
            bench_below = c.get(f"/jobs/{req_below['id']}/comp", headers=org_h).json()
            checks["benchmark 'below' for a low comp_band"] = (
                bench_below["position"] == "below" and bench_below["delta_pct"] < 0
            )

            # 6. A different role with < k offers stays static-only (k-anonymity).
            for i in range(2):
                cid = _make_candidate(c, admin_h, f"fe{i}")
                _grant_write(c, admin_h, cid, org_id)
                _submit_offer(c, org_h, cid, role="frontend_engineer")
            fe = _estimate(c, org_h, "Senior Frontend Engineer", 7)
            checks["different role with < k offers stays static-only"] = fe["sources"] == ["static"]

            # 7. Revocation drops one offer from the aggregate (6 -> 5, still blended).
            c.post(f"/ledger/consent/{grants[backend[0]]}/revoke", headers=admin_h)
            after_revoke = _estimate(c, org_h, "Senior Backend Engineer", 7)
            checks["revocation removes that offer (n_observed 6 -> 5)"] = (
                after_revoke["n_observed"] == 5 and after_revoke["sources"] == ["static", "observed"]
            )

            # 8. DPDP erasure drops another offer, tipping below k -> static-only.
            c.delete(f"/candidates/{backend[1]}", headers=admin_h)
            after_erase = _estimate(c, org_h, "Senior Backend Engineer", 7)
            checks["DPDP erase drops offer + tips below k (static-only)"] = (
                after_erase["sources"] == ["static"]
            )

            # 9. Cross-org benchmark is not visible.
            xorg = c.get(f"/jobs/{req_below['id']}/comp", headers={"X-Org-Key": org2_key})
            checks["cross-org benchmark -> 404"] = xorg.status_code == 404
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
