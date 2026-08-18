"""S4.4 smoke: boot uvicorn on a migrated scratch DB, POST three fixture resumes,
then directly build the ledger (consent + interview records with controlled
timestamps), materialize core_v1 vectors at a fixed cut T, join labels via
build_training_set, and export a labeled training CSV. Proves: A (consented) gets
a post-cut HIRED label while its features stay point-in-time; B (consented) with
only a PRE-cut hired is right-censored (no leakage); C (unconsented) is withheld in
both features and label, with a `training.label` withheld audit. LLM-free.
Run from the repo root: python scripts/smoke_s44.py
"""

import importlib.util
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from app.candidates.store import build_candidate_store
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.export import ParquetUnavailable, export_training_csv, export_training_parquet
from app.features.materialize import materialize_candidate
from app.features.store import build_feature_store
from app.features.training import build_training_set
from app.ledger.schema import ConsentPurpose, InterviewOutcome, InterviewStage
from app.ledger.store import build_ledger_store
from app.reports.store import build_report_store

from _smoke import base_env, wait_healthy

PORT = 8044
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"

RESUMES = {
    "a": "A Dev\nEmail: a44@example.com\nEXPERIENCE\n- Engineer, Acme (2015 - Present)\nSKILLS\nPython\n",
    "b": "B Dev\nEmail: b44@example.com\nEXPERIENCE\n- Engineer, Acme (2016 - Present)\nSKILLS\nPython\n",
    "c": "C Dev\nEmail: c44@example.com\nEXPERIENCE\n- Engineer, Acme (2017 - Present)\nSKILLS\nPython\n",
}



def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s44.db").as_posix()
    reports = (scratch / "reports.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

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

    # Cut T = now (captured AFTER ingest), so ingest-stamped extractions
    # (created_at < now) predate it; consent granted before T; records straddle it.
    T = datetime.now(timezone.utc)
    G = T - timedelta(days=60)
    PRE = T - timedelta(days=30)
    POST = T + timedelta(days=30)

    org = ls.create_organization("Smoke Org")
    for tag in ("a", "b", "c"):
        ls.grant_consent(candidate_id=ids[tag], purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id, now=G)
    for tag in ("a", "b"):  # read consent -> materialization allowed; C withheld
        ls.grant_consent(candidate_id=ids[tag], purpose=ConsentPurpose.LEDGER_READ, org_id=org.id, now=G)

    # A: post-cut HIRED -> positive label; B: pre-cut HIRED -> censored (no leak);
    # C: post-cut HIRED but unconsented -> withheld.
    ls.submit_interview_record(org_id=org.id, candidate_id=ids["a"], stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)
    ls.submit_interview_record(org_id=org.id, candidate_id=ids["b"], stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=PRE)
    ls.submit_interview_record(org_id=org.id, candidate_id=ids["c"], stage=InterviewStage.HM,
                               outcome=InterviewOutcome.HIRED, interviewed_at=POST)

    mvs = []
    for tag in ("a", "b", "c"):
        mv = materialize_candidate(ids[tag], view=view, registry=reg, as_of=T,
                                   candidate_store=cs, report_store=rs, ledger_store=ls)
        fs.upsert_vector(mv)
        mvs.append(mv)

    examples = build_training_set(mvs, ledger_store=ls)
    label = {ex.vector.candidate_id: ex.label for ex in examples}

    csv_path = scratch / "train_core_v1.csv"
    export_training_csv(examples, view=view, path=str(csv_path))
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")

    pq_ok = True
    pq_path = scratch / "train_core_v1.parquet"
    if importlib.util.find_spec("pyarrow") is None:
        try:
            export_training_parquet(examples, view=view, registry=reg, path=str(pq_path))
            pq_ok = False  # should have raised
        except ParquetUnavailable:
            pq_ok = True
    else:
        export_training_parquet(examples, view=view, registry=reg, path=str(pq_path))
        pq_ok = pq_path.exists()

    a, b, c = label[ids["a"]], label[ids["b"]], label[ids["c"]]
    a_audit = [x for x in ls.audit_for_candidate(ids["a"]) if x.action == "training.label"]
    c_audit = [x for x in ls.audit_for_candidate(ids["c"]) if x.action == "training.label"]

    checks = {
        "A labeled positive (post-cut hired)": a.observed and a.hired is True and a.outcome == "hired",
        "A label lag is positive (~30d)": a.lag_days is not None and a.lag_days > 0,
        "A features point-in-time (pre-cut interview count = 0)":
            mvs[0].vector.values.get("ledger.interview_record_count") in (0, None),
        "B censored: pre-cut hired does NOT leak": (b.observed is False) and (b.hired is None),
        "C withheld in label": c.withheld is True and c.hired is None and c.observed is False,
        "C features consent-masked (ledger count null)":
            mvs[2].vector.values.get("ledger.interview_record_count") is None,
        "labeled CSV header ends with label columns":
            header[-7:] == ["label_hired", "label_outcome", "label_coding_best_percentile",
                            "label_event_at", "label_lag_days", "label_observed", "label_withheld"],
        "A join audited allowed": bool(a_audit) and a_audit[-1].details.get("allowed") is True,
        "C join audited withheld": bool(c_audit) and c_audit[-1].details.get("allowed") is False,
        "parquet guarded/written": pq_ok,
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if any(not ok for ok in checks.values()):
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
