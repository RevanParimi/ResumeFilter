"""S2.1 smoke: AI-generation signals visible over the real HTTP surface.

Boots uvicorn on a scratch environment, POSTs the AI-drafted adversarial
fixture and the genuine fixture to /evaluate, and verifies the report carries
an advisory ai_generation assessment: the AI fixture lands in possible/likely
with >=2 explained deterministic tells, the genuine resume never reaches
"likely", and the advisory/human-review mandates hold. Works with a live key
(LLM stylometry fused in) and without one (deterministic floor). Run from the
repo root:
    python scripts/smoke_s21.py
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

AI_FIXTURE = Path("tests/fixtures/ai_generated_genai_resume.txt")
GENUINE_FIXTURE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8021
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s21.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
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
        # Generous read timeout: the AI fixture yields many claims, and a live
        # run pays one reasoning call per claim in plausibility + probes.
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            ai_rep = c.post(
                "/evaluate",
                json={
                    "resume_text": AI_FIXTURE.read_text(encoding="utf-8"),
                    "domain": "genai",
                },
            ).json()
            print(f"POST /evaluate (AI fixture): report={ai_rep.get('id', '?')}")
            gen_rep = c.post(
                "/evaluate",
                json={
                    "resume_text": GENUINE_FIXTURE.read_text(encoding="utf-8"),
                    "domain": "genai",
                },
            ).json()
            print(f"POST /evaluate (genuine fixture): report={gen_rep.get('id', '?')}")

        ai = ai_rep.get("ai_generation") or {}
        gen = gen_rep.get("ai_generation") or {}
        ai_det = [
            s for s in ai.get("signals", []) if s.get("source") == "deterministic"
        ]
        checks = {
            "AI fixture: assessment present": bool(ai),
            "AI fixture: band possible/likely": ai.get("band") in {"possible", "likely"},
            "AI fixture: >=2 deterministic tells, all explained": len(ai_det) >= 2
            and all(s.get("detail") for s in ai_det),
            "AI fixture: summary carries the advisory note": "never a rejection signal"
            in ai_rep.get("summary", ""),
            "genuine fixture: never LIKELY": gen.get("band") != "likely",
            "mandates hold (advisory + human review)": ai_rep.get("advisory") is True
            and ai_rep.get("human_review_required") is True,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
