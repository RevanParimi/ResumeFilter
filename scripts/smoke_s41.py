"""S4.1 smoke: feature registry over real candidate + depth + ledger data.

Boots uvicorn on a migrated scratch DB, POSTs a fixture resume (real extraction
+ auto depth-eval + persisted report), submits consented interview + coding
rows, then opens the stores DIRECTLY and computes the core_v1 feature vector.
Also computes for a candidate with NO ledger data. LLM-free (heuristic
extraction, no API key). Run from the repo root:
    python scripts/smoke_s41.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.candidates.store import build_candidate_store
from app.features import default_view, get_feature_registry
from app.features.context import build_context
from app.ledger.store import build_ledger_store
from app.reports.store import build_report_store

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8041
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
AT = "2026-07-24T10:00:00+00:00"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s41.db").as_posix()
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
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    admin_h = {"X-API-Key": ADMIN}
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text = FIXTURE.read_text(encoding="utf-8")
            cand = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()
            cid = cand["candidate_id"]
            method = cand["extraction_method"]
            # a second candidate with NO ledger data — must be a DISTINCT identity
            # (a different email, else email-hash identity resolution merges it
            # into the first candidate).
            alt = ("Priya Nair\nBackend Engineer\n"
                   "Email: priya.nair.noledger@example.com\n"
                   "Skills: Python, PostgreSQL\n"
                   "Experience: Backend Engineer at Acme, 2021-2024\n")
            cand2 = c.post("/candidates", json={"resume_text": alt}, headers=admin_h).json()
            cid2 = cand2["candidate_id"]

            org = c.post("/ledger/orgs", json={"name": "Org A"}, headers=admin_h).json()
            oid, okey = org["org"]["id"], org["api_key"]
            oh = {"X-Org-Key": okey}
            c.post(f"/ledger/candidates/{cid}/consent",
                   json={"purpose": "ledger_write", "org_id": oid}, headers=admin_h)
            for _ in range(2):
                c.post("/ledger/records",
                       json={"candidate_id": cid, "stage": "hm",
                             "outcome": "hired", "interviewed_at": AT}, headers=oh)
            c.post("/ledger/coding-rounds",
                   json={"candidate_id": cid, "platform": "hackerrank",
                         "score": 90.0, "max_score": 100.0, "percentile": 92.0,
                         "taken_at": AT}, headers=oh)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    # --- direct feature computation against the same scratch DBs ---------------
    settings = Settings(
        _env_file=None, openrouter_api_key="",
        candidates_db_url=url, vectorstore_backend="memory",
    )
    cs = build_candidate_store(settings)
    ls = build_ledger_store(settings)
    rs = build_report_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)

    ctx = build_context(cid, candidate_store=cs, report_store=rs, ledger_store=ls)
    fv = reg.compute_view(view, ctx)
    ctx2 = build_context(cid2, candidate_store=cs, report_store=rs, ledger_store=ls)
    fv2 = reg.compute_view(view, ctx2)

    print(f"candidate [{method}]: {cid[:8]}  features={len(fv.values)}")
    print(f"  years_experience   = {fv.values.get('candidate.years_experience')}")
    print(f"  depth_score        = {fv.values.get('depth.depth_score')}")
    print(f"  fabrication.risk   = {fv.values.get('fabrication.risk_band')}")
    print(f"  interview_records  = {fv.values.get('ledger.interview_record_count')}")
    print(f"  reputation.band    = {fv.values.get('reputation.band')}")
    print(f"  reputation.score   = {fv.values.get('reputation.score')}")

    checks = {
        "registry has >= 25 features": len(reg.names()) >= 25,
        "view covers every feature": {n for n, _ in view.members} == set(reg.names()),
        "profile feature present": fv.values.get("candidate.num_skills") is not None,
        "depth feature present": fv.values.get("depth.depth_score") is not None,
        "consent-gated ledger count = 2": fv.values.get("ledger.interview_record_count") == 2,
        "best coding percentile = 92": fv.values.get("ledger.best_coding_percentile") == 92.0,
        "reputation computed (score in range)": 0.0 <= (fv.values.get("reputation.score") or -1) <= 1.0,
        "no-ledger candidate counts 0": fv2.values.get("ledger.interview_record_count") == 0,
        "no-ledger percentile missing": "ledger.best_coding_percentile" in fv2.missing,
        "no-ledger reputation insufficient": fv2.values.get("reputation.band") == "insufficient_data",
    }
    failed = [name for name, v in checks.items() if not v]
    for name, v in checks.items():
        print(f"  {'OK  ' if v else 'FAIL'} {name}")
    if failed:
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
