"""S9.1 smoke: the signal-quality harness over the wire, refusals included.

What a unit test cannot prove and this does:

  * the route is REALLY admin-gated on a running server, not just in a
    TestClient whose dependency overrides came from a fixture;
  * the three refusals are what an operator actually RECEIVES AS JSON, and a
    refusal carries no metric fields -- the sprint's whole claim, asserted on
    the serialized body rather than on a Python object;
  * the CLI's exit codes are what a cron would read, including 3 against an
    unmigrated database with no traceback on stderr.

Written on scripts/_smoke.py, the shared harness, so the key pin and the
memory vectorstore come from one place. Run from the repo root:

    python scripts/smoke_s91.py
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.db import make_engine, make_session_factory
from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
from app.reports.store import SqlReportStore
from app.schemas.fabrication import FabricationRiskAssessment, FabricationRiskBand
from app.schemas.report import Report

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

S = Smoke("smoke_s91")

PORT = 8091
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}
ROOT = Path(__file__).resolve().parent.parent


def _sig(body, name):
    return next(s for s in body["signals"] if s["signal"] == name)


def _seed(store, n, *, positive, score, start):
    """Reports carrying a fabrication_risk assessment, each with one outcome.

    Written straight to the store rather than driven through POST /evaluate:
    sixty evaluations would make this smoke minutes long and would be measuring
    the graph, which is not what is under test here.
    """
    for i in range(n):
        at = start + timedelta(seconds=i)
        rep = Report(
            domain="genai", created_at=at,
            fabrication_risk=FabricationRiskAssessment(
                score=score, band=FabricationRiskBand.ELEVATED),
        )
        store.save(rep)
        store.add_outcome(OutcomeRecord(
            report_id=rep.id,
            outcome=(OutcomeLabel.VERIFIED_FABRICATED if positive
                     else OutcomeLabel.VERIFIED_GENUINE),
            recorded_by=OutcomeSource.ORGANIZATION,
            recorded_at=at + timedelta(days=1),
        ))


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s91.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = base_env(scratch, url, DEE_API_AUTH_KEY=ADMIN)
    store = SqlReportStore(make_session_factory(make_engine(url)))
    now = datetime.now(timezone.utc) - timedelta(days=30)

    proc = subprocess.Popen(uvicorn_argv(PORT), cwd=ROOT, env=env)
    try:
        with client(BASE, headers=ADMIN_H) as c, client(BASE) as anon:
            if not wait_healthy(c):
                print("FAIL server never became healthy")
                return 1
            S.check("healthz", True)

            code = anon.get("/admin/signal-quality").status_code
            S.check("route_is_admin_gated", code in (401, 403), detail=str(code))

            body = c.get("/admin/signal-quality").json()
            S.check("every_signal_is_reported", len(body["signals"]) == 12,
                    detail=f"{len(body['signals'])} signals")
            S.check("an_empty_database_refuses_everything",
                    all(s["sufficient"] is False for s in body["signals"]))

            # NOT all "insufficient_samples": the three depth.* signals cannot
            # be scored by a fraud source at ANY sample size, and answering
            # "insufficient" there would invite someone to go and collect more
            # of a label that can never score them.
            reasons = {s["reason"] for s in body["signals"]}
            S.check("the_empty_refusals_are_of_two_kinds",
                    reasons == {"insufficient_samples", "label_kind_mismatch"},
                    detail=str(sorted(reasons)))
            S.check("a_refusal_carries_no_metric_fields",
                    not ({"auc", "brier", "curve"}
                         & set(_sig(body, "fabrication_risk.score"))))

            _seed(store, 30, positive=True, score=0.9, start=now)
            body = c.get("/admin/signal-quality").json()
            reason = _sig(body, "fabrication_risk.score")["reason"]
            S.check("a_one_class_sample_refuses_as_degenerate",
                    reason == "degenerate_class", detail=reason)

            _seed(store, 30, positive=False, score=0.1, start=now + timedelta(days=1))
            body = c.get("/admin/signal-quality").json()
            fab = _sig(body, "fabrication_risk.score")
            S.check("a_real_sample_is_measured", fab["sufficient"] is True,
                    detail=f"n={fab.get('n')}")
            S.check("the_measurement_carries_an_auc_and_an_n",
                    fab.get("auc") == 1.0 and fab.get("n") == 60,
                    detail=f"auc={fab.get('auc')} n={fab.get('n')}")
            S.check("depth_signals_still_refuse_the_fraud_source",
                    all(_sig(body, s)["reason"] == "label_kind_mismatch"
                        for s in ("depth_score", "depth_band", "overall_confidence")))

            led = c.get("/admin/signal-quality?source=ledger").json()
            S.check("the_ledger_source_is_selectable",
                    led["population"]["label_kind"] == "hire",
                    detail=led["population"]["label_source"])
            S.check("fraud_signals_refuse_the_ledger_source",
                    _sig(led, "fabrication_risk.score")["reason"]
                    == "label_kind_mismatch")

            op = c.get("/admin/signal-quality?include_operator_labels=true").json()
            S.check("operator_labels_are_opt_in_over_the_wire",
                    op["population"]["include_operator_labels"] is True)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=30)
        except Exception:
            pass

    cli = subprocess.run([sys.executable, "-m", "app.signal_quality.report"],
                         cwd=ROOT, env=env, capture_output=True, text=True,
                         timeout=300)
    last = cli.stdout.strip().splitlines()[-1] if cli.stdout.strip() else ""
    parsed = False
    try:
        parsed = json.loads(last)["population"]["label_source"] == "outcomes"
    except Exception:
        parsed = False
    S.check("cli_exits_0_and_prints_the_report_as_the_last_stdout_line",
            cli.returncode == 0 and parsed, detail=f"exit={cli.returncode}")

    fresh = base_env(scratch,
                     "sqlite:///" + (scratch / "unmigrated.db").as_posix(),
                     DEE_API_AUTH_KEY=ADMIN)
    cli2 = subprocess.run([sys.executable, "-m", "app.signal_quality.report"],
                          cwd=ROOT, env=fresh, capture_output=True, text=True,
                          timeout=300)
    S.check("cli_refuses_an_unmigrated_database_with_exit_3_and_no_stack",
            cli2.returncode == 3
            and "not migrated" in cli2.stderr
            and "Traceback" not in cli2.stderr,
            detail=f"exit={cli2.returncode}")

    return S.summary()


if __name__ == "__main__":
    raise SystemExit(main())
