"""Migrated HTTP setup, subprocess training/export races, and restart checks.

Synthetic providers and disposable SQLite or --postgres storage only. There is
no production training HTTP route; the worker calls the real library builder.
"""

from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from sqlalchemy import event, select

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from smoke_r1_s1_t3a_v1 import database

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-training-erasure-admin"
BOUNDARIES = ("absent", "before_flush", "after_commit", "later_example", "no_audit", "no_audit_after_read")


def worker(scratch):
    from app.candidates.store import CandidateStore
    from app.core.db import make_engine, make_session_factory
    from app.features import default_view, get_feature_registry
    from app.features.export import export_training_csv, export_training_parquet, ParquetUnavailable
    from app.features.materialize import materialize_candidate
    from app.features.models import FeatureVectorRow
    from app.features.store import FeatureStore
    from app.features.training import build_training_set
    from app.ledger.models import AuditLogRow
    from app.ledger.store import LedgerStore
    from app.reports.store import SqlReportStore

    engine = make_engine(os.environ["DEE_CANDIDATES_DB_URL"])
    factory = make_session_factory(engine)
    candidates, ledger = CandidateStore(factory), LedgerStore(factory)
    features, reports = FeatureStore(factory), SqlReportStore(factory)
    registry = get_feature_registry()
    view = default_view(registry)
    now = datetime.now(timezone.utc)
    org = ledger.create_organization("Synthetic training agency")
    cases = json.loads((scratch / "cases.json").read_text())
    checks = Smoke("training erasure worker")
    kept = set()
    try:
        for index, case in enumerate(cases):
            cid, bid, allowed, boundary = (case[k] for k in ("erased", "kept", "allowed", "boundary"))
            kept.add(bid)
            vectors = []
            for subject in (cid, bid):
                ledger.grant_consent(candidate_id=subject, purpose="ledger_write", org_id=org.id,
                                     now=now - timedelta(days=1))
                if allowed:
                    ledger.grant_consent(candidate_id=subject, purpose="ledger_read", org_id=org.id,
                                         now=now - timedelta(days=1))
                ledger.submit_interview_record(org_id=org.id, candidate_id=subject,
                    stage="hm", outcome="hired", interviewed_at=now + timedelta(days=1))
                mv = materialize_candidate(subject, view=view, registry=registry, as_of=now,
                    candidate_store=candidates, report_store=reports, ledger_store=ledger)
                assert mv is not None
                assert features.upsert_vector(mv)
                vectors.append(mv)
            training = LedgerStore(make_session_factory(engine))
            audit = not boundary.startswith("no_audit")

            def erase(*_):
                assert candidates.delete_candidate(cid)

            initial = vectors
            if boundary in ("absent", "no_audit"):
                erase()
            elif boundary in ("before_flush", "after_commit"):
                event.listen(training._session_factory, boundary, erase, once=True)
            elif boundary == "later_example":
                original = training.audit_training_label

                def erase_earlier(subject, **kwargs):
                    if subject == bid and candidates.get_candidate(cid) is not None:
                        erase()
                    return original(subject, **kwargs)
                training.audit_training_label = erase_earlier
            elif allowed:
                original = training.coding_rounds_for_candidate

                def read_then_erase(subject):
                    rows = original(subject)
                    if subject == cid and candidates.get_candidate(cid) is not None:
                        erase()
                    return rows
                training.coding_rounds_for_candidate = read_then_erase
            else:
                def stream():
                    yield vectors[0]
                    erase()
                    yield vectors[1]
                initial = stream()
            examples = build_training_set(initial, ledger_store=training, audit=audit)
            assert [ex.vector.candidate_id for ex in examples] == [bid]
            assert examples[0].label.hired is (True if allowed else None)
            assert examples[0].label.withheld is (not allowed)
            assert build_training_set(vectors, ledger_store=training, audit=audit) == examples
            assert ledger.audit_for_candidate(cid) == []
            joins = [a for a in ledger.audit_for_candidate(bid) if a.action == "training.label"]
            assert bool(joins) is audit
            path = scratch / f"training-{index}.csv"
            export_training_csv(examples, view=view, path=str(path))
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            assert [row["candidate_id"] for row in rows] == [bid]
            assert rows[0]["label_withheld"] == str(not allowed)
            parquet = scratch / f"training-{index}.parquet"
            try:
                export_training_parquet(examples, view=view, registry=registry, path=str(parquet))
            except ParquetUnavailable:
                assert not parquet.exists()
            else:
                import pyarrow.parquet as pq
                assert pq.read_table(parquet).column("candidate_id").to_pylist() == [bid]
            checks.check(f"{allowed}/{boundary}: omitted, survivor label, retry, export and audit", True)
        with factory() as session:
            assert set(session.scalars(select(FeatureVectorRow.candidate_id))) == kept
            owners = set(session.scalars(select(AuditLogRow.candidate_id).where(
                AuditLogRow.candidate_id.is_not(None))))
            assert owners == kept
        checks.check("only surviving subjects retain vectors/audits", True)
    finally:
        engine.dispose()
    return checks.summary()


def main():
    checks = Smoke("training erasure HTTP/subprocess/restart")
    scratch = Path(tempfile.mkdtemp(prefix="r1-training-audit-"))
    print(f"Synthetic artifacts: {scratch}")
    with database(scratch) as (url, pg_options):
        env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
        env.update({
            "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"),
            "DEE_CANDIDATES_DB_URL": url, "DEE_ENV": "local",
            "DEE_API_AUTH_KEY": ADMIN, "DEE_OPENROUTER_API_KEY": "",
            "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
            "DEE_EMAIL_PROVIDER": "null", "DEE_VECTORSTORE_BACKEND": "memory",
            "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
            "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
            "PYTHONPATH": str(ROOT / "src"), "NO_PROXY": "127.0.0.1,localhost",
            "PGOPTIONS": pg_options,
        })
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        @contextmanager
        def server():
            with (scratch / "server.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(uvicorn_argv(port), env=env, cwd=scratch,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    with client(f"http://127.0.0.1:{port}", headers={"X-API-Key": ADMIN}) as http:
                        assert wait_healthy(http), "scratch app failed to start"
                        yield http
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

        cases = []
        with server() as http:
            checks.check("migrated application starts", True)
            for allowed in (False, True):
                for boundary in BOUNDARIES:
                    case = {"allowed": allowed, "boundary": boundary}
                    for role in ("erased", "kept"):
                        name = f"Subject{allowed}{boundary}{role}"
                        response = http.post("/candidates", json={"resume_text":
                            f"{name}\nEmail: {name.lower()}@example.com\nSkills: Python", "evaluate": False})
                        assert response.status_code == 200
                        case[role] = response.json()["candidate_id"]
                    cases.append(case)
            (scratch / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            with (scratch / "worker.log").open("w", encoding="utf-8") as log:
                proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(scratch)],
                    cwd=scratch, env=env, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            assert proc.returncode == 0, "training worker failed"
            checks.check("all 12 worker erasure/export scenarios passed", True)
        with server() as http:
            for case in cases:
                assert http.get(f"/candidates/{case['erased']}").status_code == 404
                assert http.get(f"/candidates/{case['kept']}").status_code == 200
            checks.check("restart preserves 12 erasures and 12 survivors", True)
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(worker(Path(sys.argv[2])) if "--worker" in sys.argv else main())
