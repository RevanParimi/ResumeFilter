"""Factual-risk v2: actual migrated HTTP/restart, fake providers, scratch SQL.

Plain/polished truthful fixtures use the same dates, atomic claim and comparison
corpus. Only descriptive style differs. Real extraction, fingerprints, scoring,
report persistence and materialization remain in the app composition.
"""

from contextlib import contextmanager
from copy import deepcopy
import csv
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy
from app.services.llm import LLMClient

ROOT = Path(__file__).resolve().parents[1]
ADMIN = "synthetic-style-fusion-admin"


class ClaimFake(LLMClient):
    async def _araw(self, *, model, system, prompt, max_tokens):
        from tests.conftest import FakeLLM
        content = ""
        if "extracting atomic" in system:
            content = json.dumps({"claims": [{
                "text": "Built a daily ingestion pipeline for finance reporting.", "claim_type": "unknown"
            }]})
        return await FakeLLM({"": content}, settings=self.settings)._araw(
            model=model, system=system, prompt=prompt, max_tokens=max_tokens)


def create_smoke_app():
    import app.services as services
    from app.main import create_app
    from tests.conftest import FakeGitHub

    services.build_llm = lambda settings: ClaimFake(settings=settings)
    services.GitHubClient = lambda settings: FakeGitHub()
    return create_app()


def main():
    from app.core.db import make_session_factory
    from app.features import default_view, get_feature_registry
    from app.features.export import export_view_csv
    from app.features.materialize import materialize_candidate
    from app.features.store import FeatureStore
    from app.candidates.store import CandidateStore
    from app.ledger.store import LedgerStore
    from app.reports.models import ReportRow
    from app.reports.schema import OutcomeLabel, OutcomeRecord, OutcomeSource
    from app.reports.store import SqlReportStore

    checks = Smoke("R2-S2-T1 style exclusion / historical semantics / persistence")
    scratch = Path(tempfile.mkdtemp(prefix="r2-s2-t1-"))
    print(f"Synthetic artifacts: {scratch}")
    texts = {name: (ROOT / "tests/fixtures" / f"style_{name}_resume.txt").read_text(encoding="utf-8")
             for name in ("plain", "polished")}
    url = "sqlite:///" + (scratch / "app.db").as_posix()
    env = {k: v for k, v in base_env().items() if not k.startswith("DEE_")}
    env.update({
        "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_CANDIDATES_DB_URL": url,
        "DEE_ENV": "local", "DEE_API_AUTH_KEY": ADMIN,
        "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
        "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
        "DEE_EMAIL_PROVIDER": "null", "DEE_SPEECH_PROVIDER": "local",
        "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
        "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_FLYWHEEL_PATH": str(scratch / "flywheel.jsonl"),
        "DEE_FR_WEIGHT_AI": "0",  # high style must disappear even from maximum/coverage
        "PYTHONPATH": os.pathsep.join(str(p) for p in (ROOT / "src", ROOT / "scripts", ROOT)),
        "NO_PROXY": "127.0.0.1,localhost",
    })
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

    @contextmanager
    def server():
        with (scratch / "server.log").open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(uvicorn_argv(port, target="smoke_r2_s2_t1:create_smoke_app") + ["--factory"],
                env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                with client(base, connect=0.5, headers={"X-API-Key": ADMIN}) as http:
                    assert wait_healthy(http), "scratch app failed to start"
                    yield http
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)

    def with_email(body, address):
        return body.replace("Synthetic Taylor", "Synthetic Taylor\nEmail: " + address)

    def check_pair(label, pair, expected):
        plain, polished = pair
        checks.check(label + " changes descriptive style", polished["ai_generation"]["band"] == "likely" and
                     plain["ai_generation"]["likelihood"] < polished["ai_generation"]["likelihood"])
        risks = [r["fabrication_risk"] for r in pair]
        checks.check(label + " retains identical factual risk", risks[0] == risks[1])
        checks.check(label + " has expected v2 factual band", risks[0]["band"] == expected and
            all(r["scorer_version"] == 2 and all(c["id"] != "ai_generation" for c in r["components"]) for r in risks))
        checks.check(label + " preserves depth and advisory review", all(
            plain[k] == polished[k] for k in ("depth_score", "depth_band", "overall_confidence")) and
            all(r["advisory"] and r["human_review_required"] for r in pair))
        checks.check(label + " preserves fixed claim assessments", [
            {k: v[k] for k in ("claim_text", "claim_type", "status", "coherence_score", "confidence")}
            for v in plain["verdicts"]
        ] == [{k: v[k] for k in ("claim_text", "claim_type", "status", "coherence_score", "confidence")}
              for v in polished["verdicts"]])
        checks.check(label + " retains fixed factual component inputs", [
            (c["id"], c["band"], c["confidence"], c["flagged"], c["weight"]) for c in risks[0]["components"]
        ] == [(c["id"], c["band"], c["confidence"], c["flagged"], c["weight"]) for c in risks[1]["components"]])

    engine = create_engine(url, hide_parameters=True)
    factory = make_session_factory(engine)
    cs, rs, ls, fs = CandidateStore(factory), SqlReportStore(factory), LedgerStore(factory), FeatureStore(factory)
    reg = get_feature_registry()
    view = default_view(reg, settings=SimpleNamespace(feat_default_view="core_v1"))
    saved = {}
    try:
        with server() as http:
            with engine.connect() as conn:
                checks.check("actual scratch startup migrated to head", conn.scalar(
                    text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
            for domain in ("genai", "data_eng"):
                pair = [require(http.post("/evaluate", json={"resume_text": body, "domain": domain}))
                        for body in texts.values()]
                check_pair(domain + " ad-hoc", pair, "insufficient_data")
                checks.check(domain + " style cannot fill missing duplication coverage",
                             all(len(r["fabrication_risk"]["components"]) == 1 and
                                 r["fabrication_risk"]["confidence"] == 0.45 for r in pair))

            orgs = [require(http.post("/ledger/orgs", json={"name": "Synthetic Style " + name}))
                    for name in ("A", "B")]
            headers = [{"X-Org-Key": org["api_key"]} for org in orgs]
            unrelated = "Synthetic Botanical\nEmail: botanical@example.com\n" + " ".join(
                f"botanical{i} specimen{i} catalog{i} archive{i}" for i in range(60))
            require(http.post("/candidates", json={"resume_text": unrelated, "evaluate": False}))

            def screening_pair(label, bodies, expected):
                uploads = [require(http.post("/screening/candidates", headers=headers[0], json={
                    "resume_text": with_email(body, "style-pair@example.com"), "domain": "data_eng"}))
                    for body in bodies]
                reports = [item["report"] for item in uploads]
                check_pair(label, reports, expected)
                checks.check(label + " reupload excludes same subject from corpus",
                             uploads[0]["candidate_id"] == uploads[1]["candidate_id"])
                for report in reports:
                    rid = report["id"]
                    checks.check(label + " owner reads persisted result", require(http.get(
                        f"/screening/reports/{rid}", headers=headers[0])) == report)
                    require(http.get(f"/screening/reports/{rid}", headers=headers[1]), 404)
                    saved[rid] = report
                checks.check(label + " other org denied", True)
                return uploads

            low = screening_pair("clean timeline/unique corpus", list(texts.values()), "low")
            # Two versions of one different candidate make each paired upload
            # find its exact equivalent, with the same corpus and confidence.
            for body in texts.values():
                require(http.post("/candidates", json={
                    "resume_text": with_email(body, "reference@example.com"), "evaluate": False}))
            moderate = screening_pair("real near duplication", list(texts.values()), "moderate")
            checks.check("actual fingerprints detect near duplication", all(
                item["report"]["resume_farm"]["band"] == "near_duplicate" and
                item["report"]["resume_farm"]["score"] == 1.0 for item in moderate))
            overlaps = [body.replace("Jan 2019 - Dec 2021", "Jan 2021 - Dec 2023") for body in texts.values()]
            for body in overlaps:
                require(http.post("/candidates", json={
                    "resume_text": with_email(body, "reference@example.com"), "evaluate": False}))
            elevated = screening_pair("timeline overlap and duplication", overlaps, "elevated")
            checks.check("actual timeline overlap remains visible", all(any(
                f["id"] == "timeline_overlap" and f["severity"] == "major"
                for f in item["report"]["cross_field"]["findings"]) for item in elevated))

            historical = require(http.post("/candidates", json={
                "resume_text": "Historical Synthetic\nSkills: Python", "domain": "data_eng"}))
            hrid, hcid = historical["report"]["id"], historical["candidate_id"]
            with factory() as session:
                row = session.get(ReportRow, hrid)
                historical_body = deepcopy(row.body)
                historical_body["fabrication_risk"] = {
                    "score": 0.75, "confidence": 0.60, "band": "moderate", "advisory": True,
                    "reasoning": "Synthetic historical style-inclusive assessment; keep original interpretation.",
                    "components": [{"id": "ai_generation", "band": "likely", "risk": 0.75,
                                    "confidence": 0.8, "weight": 0.8, "flagged": True}],
                }
                row.body = historical_body
                session.commit()
            old_response = require(http.get(f"/report/{hrid}"))
            checks.check("historical HTTP read preserves score and style-inclusive version",
                         old_response["fabrication_risk"] == {**historical_body["fabrication_risk"], "scorer_version": 1})
            saved[hrid] = old_response
            for rid in (hrid, elevated[-1]["report"]["id"]):
                report = rs.get(rid)
                from datetime import timedelta
                rs.add_outcome(OutcomeRecord(report_id=rid, outcome=OutcomeLabel.INCONCLUSIVE,
                    recorded_by=OutcomeSource.ORGANIZATION, recorded_at=report.created_at + timedelta(days=1)))
                rs.add_outcome(OutcomeRecord(report_id=rid, outcome=OutcomeLabel.VERIFIED_GENUINE,
                    recorded_by=OutcomeSource.ORGANIZATION, recorded_at=report.created_at + timedelta(days=2)))
            quality = require(http.get("/admin/signal-quality"))
            checks.check("HTTP measurement keeps population but excludes historical risk sample",
                         quality["population"]["labels_usable"] == 2 and all(
                item["n"] == 1 and not item["sufficient"] for item in quality["signals"]
                if item["signal"] in ("fabrication_risk.score", "fabrication_risk.band")))

            legacy = replace(view, version=1, members=tuple(
                (name, 1 if name in ("fabrication.risk_score", "fabrication.risk_band") else version)
                for name, version in view.members))
            cut = datetime.now(timezone.utc)
            historical_vector = materialize_candidate(hcid, view=legacy, registry=reg, as_of=cut,
                candidate_store=cs, report_store=rs, ledger_store=ls)
            fs.upsert_vector(historical_vector)
            run = require(http.post("/features/materialize", json={}))
            checks.check("HTTP materializes new view version", run["view_version"] == 2)
            current = fs.latest_vectors_for_view(view.name, view.version,
                                                 as_of=datetime.fromisoformat(run["as_of"]))
            current_by_id = {item.vector.candidate_id: item for item in current}
            checks.check("new materialization refuses historical risk semantics",
                         current_by_id[hcid].vector.values["fabrication.risk_score"] is None and
                         current_by_id[hcid].vector.values["fabrication.risk_band"] is None)
            pair_id = low[0]["candidate_id"]
            checks.check("new materialization carries current factual score", current_by_id[pair_id].vector.values[
                "fabrication.risk_score"] == elevated[-1]["report"]["fabrication_risk"]["score"])
            for label, bundle, rows in (("historical", legacy, [historical_vector]), ("current", view, current)):
                path = scratch / (label + ".csv")
                export_view_csv(rows, view=bundle, registry=reg, ledger_store=ls, path=str(path))
                with path.open(newline="", encoding="utf-8") as handle:
                    exported = {row["candidate_id"]: row for row in csv.DictReader(handle)}
                checks.check(label + " CSV preserves separate interpretation",
                             exported[hcid]["fabrication.risk_score"] == ("0.75" if bundle.version == 1 else "") and
                             exported[hcid]["view_version"] == str(bundle.version))
            ranking = {"terms": [{"feature": "fabrication.risk_score", "weight": 1.0}]}
            checks.check("default search selects current view", require(http.post(
                "/talent/search", json={"ranking": ranking}))["view_version"] == 2)
            checks.check("explicit historical search remains available", require(http.post(
                "/talent/search", json={"ranking": ranking, "view_version": 1}))["view_version"] == 1)
            require(http.post("/features/materialize", headers={"X-API-Key": "wrong", **headers[1]}, json={}), 401)
            checks.check("org cannot materialize platform features", True)
        with server() as http:
            for rid, report in saved.items():
                path = f"/report/{rid}" if rid == hrid else f"/screening/reports/{rid}"
                kwargs = {} if rid == hrid else {"headers": headers[0]}
                checks.check("report semantics survive actual restart", require(http.get(path, **kwargs)) == report)
            require(http.get(f'/screening/reports/{elevated[0]["report"]["id"]}', headers=headers[1]), 404)
            checks.check("restart preserves tenant denial", True)
            checks.check("historical feature vector survives unchanged", fs.get_vector(
                hcid, view_name=legacy.name, view_version=1, as_of=cut) == historical_vector)
            with factory() as session:
                checks.check("historical report body is never rewritten", session.get(ReportRow, hrid).body == historical_body)
    finally:
        engine.dispose()
    return checks.summary()


if __name__ == "__main__":
    raise SystemExit(main())
