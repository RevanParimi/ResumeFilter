"""S5.1 smoke: boot uvicorn on a migrated scratch DB, create an org (admin) +
its X-Org-Key, POST three fixture resumes (distinct skills/experience), then
materialize + persist their core_v1 vectors directly. Re-boot and exercise the
org-plane demand side over HTTP: create a job requisition, POST
/jobs/{id}/match and assert a role-conditioned ranking (skill coverage drives
order, weak candidate still appears — advisory), a min_skill_coverage floor that
gates the pool, and DPDP erasure that drops a candidate + sweeps its
match.surface audit rows. LLM-free. Run from the repo root:
python scripts/smoke_s51.py
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

PORT = 8051
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

# Distinct emails (no identity merge). Skill coverage vs a [python, django] role:
# strong = both (1.0), weak = python only (0.5), other = java only (0.0).
RESUMES = {
    "strong": (
        "Strong Dev\nEmail: strong@example.com\n"
        "EXPERIENCE\n- Senior Engineer, Acme (2013 - Present)\n"
        "SKILLS\nPython, Django\nNotice period: 30 days\n"
    ),
    "weak": (
        "Weak Dev\nEmail: weak@example.com\n"
        "EXPERIENCE\n- Engineer, Acme (2019 - Present)\n"
        "SKILLS\nPython\nNotice period: 90 days\n"
    ),
    "other": (
        "Other Dev\nEmail: other@example.com\n"
        "EXPERIENCE\n- Engineer, Acme (2020 - Present)\n"
        "SKILLS\nJava\nNotice period: 60 days\n"
    ),
}


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
    url = "sqlite:///" + (scratch / "smoke_s51.db").as_posix()
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
    ids = {}
    org_key = None

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
            for tag, text in RESUMES.items():
                ids[tag] = c.post("/candidates", json={"resume_text": text},
                                  headers=admin_h).json()["candidate_id"]
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    settings = Settings(_env_file=None, openrouter_api_key="", candidates_db_url=url,
                        vectorstore_backend="memory")
    cs, ls, rs = build_candidate_store(settings), build_ledger_store(settings), build_report_store(settings)
    fs = build_feature_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)
    now = datetime.now(timezone.utc)

    # No consent granted -> reputation.* / ledger.* materialize masked; first-party OK.
    for cid in ids.values():
        mv = materialize_candidate(cid, view=view, registry=reg, as_of=now,
                                   candidate_store=cs, report_store=rs, ledger_store=ls)
        fs.upsert_vector(mv)

    org_h = {"X-Org-Key": org_key}
    as_of = now.isoformat()

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not _wait_healthy(c):
                print("FAIL server never became healthy (2nd boot)")
                return 1

            # Requisition A: role-conditioned match on skills + experience + notice.
            req_a = c.post("/jobs", headers=org_h, json={
                "title": "Backend Engineer",
                "must_have_skills": ["python", "django"],
                "min_years_experience": 2.0,
                "max_notice_days": 90,
            }).json()
            match_a = c.post(f"/jobs/{req_a['id']}/match", headers=org_h,
                             json={"as_of": as_of}).json()
            order = [m["candidate_id"] for m in match_a["ranked"]]
            by_id = {m["candidate_id"]: m for m in match_a["ranked"]}

            # Requisition B: opt-in min_skill_coverage floor gates the pool.
            req_b = c.post("/jobs", headers=org_h, json={
                "title": "BE (strict)",
                "must_have_skills": ["python", "django"],
                "min_skill_coverage": 0.75,
            }).json()
            match_b = c.post(f"/jobs/{req_b['id']}/match", headers=org_h,
                             json={"as_of": as_of}).json()

            # DPDP: erase the strong candidate, re-match A.
            c.delete(f"/candidates/{ids['strong']}", headers=admin_h)
            match_a2 = c.post(f"/jobs/{req_a['id']}/match", headers=org_h,
                              json={"as_of": as_of}).json()
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    # match.surface audit rows for the erased candidate must be swept (CASCADE).
    strong_audit = ls.audit_for_candidate(ids["strong"])

    checks = {
        "match advisory always true": match_a["advisory"] is True,
        "pool has all three": match_a["pool_size"] == 3,
        "ranked strong -> weak -> other (skill coverage drives order)":
            order == [ids["strong"], ids["weak"], ids["other"]],
        "strong full skill coverage": by_id[ids["strong"]]["skill"]["coverage"] == 1.0,
        "weak partial coverage, still ranked (advisory)":
            by_id[ids["weak"]]["skill"]["coverage"] == 0.5,
        "other zero coverage, still ranked (not auto-rejected)":
            by_id[ids["other"]]["skill"]["coverage"] == 0.0,
        "skill_coverage is a visible contribution":
            any(cn["feature"] == "match.skill_coverage"
                for cn in by_id[ids["strong"]]["contributions"]),
        "min_skill_coverage floor gates to strong only":
            [m["candidate_id"] for m in match_b["ranked"]] == [ids["strong"]],
        "DPDP: erased strong drops from the pool": match_a2["pool_size"] == 2,
        "DPDP: erased strong absent from ranking":
            ids["strong"] not in [m["candidate_id"] for m in match_a2["ranked"]],
        "DPDP: match.surface audit rows swept on erasure": strong_audit == [],
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
