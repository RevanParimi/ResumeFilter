"""S4.2 smoke: materialize + persist + export feature vectors, consent-gated and
point-in-time. Boots uvicorn on a migrated scratch DB, POSTs two fixture resumes
(A consented for ledger_read with FUTURE-dated ledger rows; B no consent, no
rows), then opens the stores directly to materialize, persist, and export.
LLM-free. Run from the repo root: python scripts/smoke_s42.py
"""

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.candidates.store import build_candidate_store
from app.features import default_view, get_feature_registry
from app.features.export import ParquetUnavailable, export_view_csv, export_view_parquet
from app.features.materialize import materialize_candidate
from app.features.store import build_feature_store
from app.ledger.store import build_ledger_store
from app.services.report_store import build_report_store

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8042
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

# Ledger rows dated AFTER the `now` cut but INSIDE the consent grant's 365d TTL,
# so `later` still sees an active grant.
_NOW = datetime.now(timezone.utc)
ROWS_AT = (_NOW + timedelta(days=100)).isoformat()


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s42.db").as_posix()
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
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
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
            cidA = c.post("/candidates", json={"resume_text": text}, headers=admin_h).json()["candidate_id"]
            altB = ("Priya Nair\nBackend Engineer\nEmail: priya.noledger@example.com\n"
                    "Skills: Python, PostgreSQL\nExperience: Backend Engineer at Acme, 2021-2024\n")
            cidB = c.post("/candidates", json={"resume_text": altB}, headers=admin_h).json()["candidate_id"]

            org = c.post("/ledger/orgs", json={"name": "Org A"}, headers=admin_h).json()
            oid, okey = org["org"]["id"], org["api_key"]
            oh = {"X-Org-Key": okey}
            # A: write + read consent; two hired records + one coding round, FUTURE-dated
            for purpose in ("ledger_write", "ledger_read"):
                c.post(f"/ledger/candidates/{cidA}/consent",
                       json={"purpose": purpose, "org_id": oid}, headers=admin_h)
            for _ in range(2):
                c.post("/ledger/records",
                       json={"candidate_id": cidA, "stage": "hm", "outcome": "hired",
                             "interviewed_at": ROWS_AT}, headers=oh)
            c.post("/ledger/coding-rounds",
                   json={"candidate_id": cidA, "platform": "hackerrank", "score": 90.0,
                         "max_score": 100.0, "percentile": 92.0, "taken_at": ROWS_AT}, headers=oh)
    finally:
        proc.terminate()
        proc.wait(timeout=15)

    settings = Settings(_env_file=None, openrouter_api_key="",
                        candidates_db_url=url, report_db_path=reports, vectorstore_backend="memory")
    cs, ls, rs = build_candidate_store(settings), build_ledger_store(settings), build_report_store(settings)
    fs = build_feature_store(settings)
    reg = get_feature_registry()
    view = default_view(reg, settings=settings)

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=200)            # after the future rows, still inside the 365d grant

    mvA_now = materialize_candidate(cidA, view=view, registry=reg, as_of=now,
                                    candidate_store=cs, report_store=rs, ledger_store=ls)
    mvA_later = materialize_candidate(cidA, view=view, registry=reg, as_of=later,
                                      candidate_store=cs, report_store=rs, ledger_store=ls)
    mvB = materialize_candidate(cidB, view=view, registry=reg, as_of=now,
                                candidate_store=cs, report_store=rs, ledger_store=ls)

    fs.upsert_vector(mvA_now)
    fs.upsert_vector(mvB)

    csv_path = scratch / "features.csv"
    export_view_csv(fs.vectors_for_view(view.name, view.version, as_of=now), view=view, path=str(csv_path))
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")

    try:
        export_view_parquet([mvA_now], view=view, registry=reg, path=str(scratch / "features.parquet"))
        parquet_ok = True
    except ParquetUnavailable:
        parquet_ok = "skipped (pyarrow absent)"

    # Count BEFORE the DPDP erase below (which cascades A's vector away).
    persisted_count = len(fs.vectors_for_view(view.name, view.version, as_of=now))

    cs.delete_candidate(cidA)
    erased = fs.get_vector(cidA, view_name=view.name, view_version=view.version, as_of=now)

    checks = {
        "A consent allowed at now": mvA_now.consent_state["allowed"] is True,
        "A ledger count 0 at now (point-in-time; rows are future)":
            mvA_now.vector.values.get("ledger.interview_record_count") == 0,
        "A ledger count 2 later (future rows now visible)":
            mvA_later.vector.values.get("ledger.interview_record_count") == 2,
        "A best percentile 92 later":
            mvA_later.vector.values.get("ledger.best_coding_percentile") == 92.0,
        "B consent withheld": mvB.consent_state["allowed"] is False,
        "B consent feature masked to null":
            mvB.vector.values.get("ledger.interview_record_count") is None,
        "B first-party present": mvB.vector.values.get("candidate.num_skills") is not None,
        "persisted two vectors at now (pre-erase)": persisted_count == 2,
        "csv header wide + view order":
            header[:4] == ["candidate_id", "as_of", "view_name", "view_version"]
            and header[4:] == [n for n, _ in view.members],
        "parquet guarded": parquet_ok is True or isinstance(parquet_ok, str),
        "DPDP erase cascades vector": erased is None,
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    print(f"  parquet: {parquet_ok}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
