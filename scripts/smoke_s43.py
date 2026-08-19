"""S4.3 smoke: boot uvicorn on a migrated scratch DB, POST three fixture resumes
(none consented), materialize + persist their core_v1 vectors directly, then
exercise POST /talent/search over HTTP: a ranking with visible contributions, a
filter that narrows the pool, and proof the consent-withheld candidates are ranked
(reduced coverage) not penalized to the bottom. LLM-free. Run from the repo root:
python scripts/smoke_s43.py
"""

import subprocess
import sys
import tempfile
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

from _smoke import base_env, wait_healthy

PORT = 8043
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

# Three resumes with distinct emails (no identity merge) and different experience.
#
# THE ROLE LINES CARRY NO BULLET, and that is load-bearing rather than style.
# `extractor._experience` skips any line matching `_BULLET` -- under a bullet
# a dated line is a DUTY, not a role -- so the bulleted form yielded ZERO
# experience entries and `candidate.years_experience` came back None for all
# three. Until the S8.6 review that was invisible: this file inherited a real
# DEE_OPENROUTER_API_KEY, the LLM extractor read the bullets fine, and the
# docstring above said LLM-free about a run that was billing a vendor.
#
# Measured on the deterministic path: 2013 -> ~13.6 yrs, 2019 -> ~7.6, 2023
# -> ~3.6, so the `>= 6` filter narrows to exactly the two seniors and the
# ranking has a real numeric to order by. With the key pinned and the bullets
# still in place, FOUR of the eight checks below failed and the other four
# were passing on insertion order over three None-valued candidates.
RESUMES = {
    "sr": ("Sr Dev\nEmail: sr@example.com\nEXPERIENCE\nEngineer, Acme (2013 - Present)\nSKILLS\nPython\n"),
    "mid": ("Mid Dev\nEmail: mid@example.com\nEXPERIENCE\nEngineer, Acme (2019 - Present)\nSKILLS\nPython\n"),
    "jr": ("Jr Dev\nEmail: jr@example.com\nEXPERIENCE\nEngineer, Acme (2023 - Present)\nSKILLS\nPython\n"),
}



def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s43.db").as_posix()
    reports = (scratch / "reports.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    # base_env() pins DEE_OPENROUTER_API_KEY empty -- what the docstring above
    # has always claimed and what this file did not enforce until S8.6.
    env = base_env()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": reports,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
    })
    admin_h = {"X-API-Key": ADMIN}
    ids = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not wait_healthy(c):
                print("FAIL server never became healthy")
                return 1
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

    # No consent granted for anyone -> reputation.* / ledger.* materialize masked.
    for cid in ids.values():
        mv = materialize_candidate(cid, view=view, registry=reg, as_of=now,
                                   candidate_store=cs, report_store=rs, ledger_store=ls)
        fs.upsert_vector(mv)

    # Re-boot uvicorn against the now-populated DB and search over HTTP.
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            if not wait_healthy(c):
                print("FAIL server never became healthy (2nd boot)")
                return 1

            ranking = {"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]}
            ranked = c.post("/talent/search", json={"ranking": ranking}, headers=admin_h).json()
            order = [r["candidate_id"] for r in ranked["ranked"]]

            filt = c.post("/talent/search", json={
                "filters": [{"feature": "candidate.years_experience", "op": "gte", "value": 6}],
                "ranking": ranking,
            }, headers=admin_h).json()

            # A ranking that WOULD reward reputation: consent-withheld candidates
            # must still be ranked (reputation dropped), not pushed to the bottom.
            rep_ranking = {"terms": [
                {"feature": "candidate.years_experience", "weight": 0.5},
                {"feature": "reputation.score", "weight": 0.5},
            ]}
            rep = c.post("/talent/search", json={"ranking": rep_ranking}, headers=admin_h).json()
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    checks = {
        "advisory always true": ranked["advisory"] is True,
        "pool has all three": ranked["pool_size"] == 3,
        "ranked senior -> mid -> junior": order == [ids["sr"], ids["mid"], ids["jr"]],
        "top has a contribution": bool(ranked["ranked"][0]["contributions"]),
        "filter narrows to the two most experienced": filt["filtered_size"] == 2,
        "consent-withheld still ranked (reputation dropped)": len(rep["ranked"]) == 3,
        "withheld reputation reduces coverage, not membership":
            all(r["coverage"] < 1.0 and "reputation.score" in r["missing"]
                for r in rep["ranked"]),
        "withheld senior still ranks first on present terms":
            rep["ranked"][0]["candidate_id"] == ids["sr"],
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
