"""S2.4 smoke: unified fabrication_risk visible over the real HTTP surface.

Boots uvicorn on a scratch, Alembic-migrated SQLite DB and checks the fused
band end to end: a farm near-duplicate upload lands moderate-or-elevated with a
resume_farm component; a genuine resume stays low; POST /evaluate fuses without
a farm component; depth outputs are never moved by fabrication signals.
Works with a live key (LLM extraction) and without one (deterministic floor).
Run from the repo root:
    python scripts/smoke_s24.py
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

from _smoke import Smoke, base_env

S = Smoke("smoke_s24")

FARM_A = Path("tests/fixtures/farm_genai_resume_a.txt")
FARM_B = Path("tests/fixtures/farm_genai_resume_b.txt")
GENUINE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8024
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"   # S8.1: the admin plane fails closed


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s24.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = base_env()
    env.update(
        {
            "DEE_API_AUTH_KEY": ADMIN,
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, headers={"X-API-Key": ADMIN}, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text_a = FARM_A.read_text(encoding="utf-8")
            text_b = FARM_B.read_text(encoding="utf-8")
            text_g = GENUINE.read_text(encoding="utf-8")

            first = c.post("/candidates", json={"resume_text": text_a, "domain": "genai"}).json()
            risk_a = (first.get("report") or {}).get("fabrication_risk") or {}
            S.check("upload A carries fabrication_risk", bool(risk_a), f"band={risk_a.get('band')}")

            second = c.post("/candidates", json={"resume_text": text_b, "domain": "genai"}).json()
            rep_b = second.get("report") or {}
            risk_b = rep_b.get("fabrication_risk") or {}
            comp_ids = [x.get("id") for x in risk_b.get("components", [])]
            S.check(
                "farm copy B fuses to moderate/elevated",
                risk_b.get("band") in ("moderate", "elevated"),
                f"band={risk_b.get('band')} score={risk_b.get('score')}",
            )
            S.check("farm copy B includes resume_farm component", "resume_farm" in comp_ids, str(comp_ids))
            S.check("assessment is advisory", risk_b.get("advisory") is True)
            S.check(
                "summary carries the fused advisory note",
                "Unified fabrication risk" in rep_b.get("summary", ""),
            )
            S.check(
                "report still advisory + human-review",
                rep_b.get("advisory") is True and rep_b.get("human_review_required") is True,
            )

            genuine = c.post("/candidates", json={"resume_text": text_g, "domain": "genai"}).json()
            risk_g = (genuine.get("report") or {}).get("fabrication_risk") or {}
            S.check(
                "genuine resume fuses low (or insufficient)",
                risk_g.get("band") in ("low", "insufficient_data"),
                f"band={risk_g.get('band')}",
            )

            adhoc = c.post("/evaluate", json={"resume_text": text_g, "domain": "genai"}).json()
            risk_e = adhoc.get("fabrication_risk") or {}
            ids_e = [x.get("id") for x in risk_e.get("components", [])]
            S.check("POST /evaluate carries fabrication_risk", bool(risk_e), f"band={risk_e.get('band')}")
            S.check("POST /evaluate has no resume_farm component", "resume_farm" not in ids_e, str(ids_e))
            S.check(
                "report still carries a depth band",
                (genuine.get("report") or {}).get("depth_band") is not None,
            )
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    return S.summary()


if __name__ == "__main__":
    raise SystemExit(main())
