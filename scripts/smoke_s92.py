"""S9.2 smoke: coverage over the wire, on a live server.

What a unit test cannot prove and this does:
  * the four resume shapes survive a REAL upload through POST /candidates,
    not a direct heuristic_profile() call;
  * `extraction_coverage` is what an operator actually RECEIVES AS JSON, on
    both the embedded report and the ingest response;
  * a refusal serializes with NO gaps -- the sprint's claim, asserted on the
    body rather than on a Python object;
  * an evaluate=false bulk import still reports coverage, which is the whole
    reason it sits on the response as well as on the report.

Fixtures are read straight from tests/fixtures/shapes/*.txt (ruling R6) --
the same files tests/test_extractor_shape_corpus.py reads -- rather than
imported from that test module: smokes run as `python scripts/smoke_s92.py`
with sys.path[0] == scripts/, so importing tests/ is not an option, and
pasting a second copy of the shapes is the duplication scripts/_smoke.py
exists to end.

Run from the repo root:   python scripts/smoke_s92.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from _smoke import Smoke, base_env, client, uvicorn_argv, wait_healthy

S = Smoke("smoke_s92")
PORT = 8092
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
ADMIN_H = {"X-API-Key": ADMIN}
ROOT = Path(__file__).resolve().parent.parent
SHAPES_DIR = ROOT / "tests" / "fixtures" / "shapes"

SHAPES = {
    name: (SHAPES_DIR / f"{name}.txt").read_text(encoding="utf-8")
    for name in (
        "bulleted_roles",
        "career_history_header",
        "spelled_out_degrees",
        "labelled_skills",
    )
}


def main() -> int:
    # A plain mkdtemp, not a TemporaryDirectory context manager: on Windows the
    # just-terminated uvicorn subprocess can still hold the sqlite file open
    # for a moment after proc.wait() returns, and an auto-cleanup context
    # manager's rmtree races that and raises PermissionError. Every other
    # smoke (see scripts/smoke_s91.py) leaves the scratch dir for the OS to
    # reclaim rather than fighting that race.
    scratch = Path(tempfile.mkdtemp())
    url = f"sqlite:///{(scratch / 's92.db').as_posix()}"
    # coverage_min_chars defaults to 200; two of the four fixture shapes are
    # just under that (measured: labelled_skills 193, spelled_out_degrees
    # 195), same as tests/test_extractor_shape_corpus.py's min_chars=50.
    # Without lowering it here, those two would report insufficient_data
    # (a refusal) rather than complete, and "no_major_gap_after_the_fixes"
    # would pass trivially -- a check passing for the wrong reason.
    env = base_env(scratch, url, DEE_API_AUTH_KEY=ADMIN, DEE_COVERAGE_MIN_CHARS="50")
    proc = subprocess.Popen(uvicorn_argv(PORT), env=env, cwd=str(ROOT))
    try:
        with client(BASE, headers=ADMIN_H) as c:
            if not S.check("server_healthy", wait_healthy(c)):
                return S.summary()

            for name, text in SHAPES.items():
                r = c.post(
                    "/candidates", json={"resume_text": text, "domain": "genai"}
                )
                if not S.check(
                    f"{name}_uploaded", r.status_code == 200, f"HTTP {r.status_code}"
                ):
                    continue
                body = r.json()
                cov = (body.get("report") or {}).get("extraction_coverage")
                S.check(f"{name}_coverage_present", cov is not None)
                S.check(
                    f"{name}_no_major_gap_after_the_fixes",
                    cov is not None and cov["band"] != "major_gaps",
                    f"band={cov and cov['band']} gaps={cov and [g['id'] for g in cov['gaps']]}",
                )

            # A refusal, over the wire, serializing with NO metric-shaped fields.
            r = c.post(
                "/candidates",
                json={"resume_text": "Priya\npriya@example.com", "domain": "genai"},
            )
            cov = (r.json().get("report") or {}).get("extraction_coverage") or {}
            S.check(
                "short_document_refuses",
                cov.get("band") == "insufficient_data",
                f"band={cov.get('band')}",
            )
            S.check(
                "refusal_carries_no_gaps",
                cov.get("gaps") == [],
                f"gaps={cov.get('gaps')}",
            )

            # evaluate=false produces no report -- coverage must still arrive.
            r = c.post(
                "/candidates",
                json={
                    "resume_text": SHAPES["bulleted_roles"],
                    "domain": "genai",
                    "evaluate": False,
                },
            )
            body = r.json()
            S.check("bulk_import_has_no_report", body.get("report") is None)
            S.check(
                "bulk_import_still_reports_coverage",
                (body.get("extraction_coverage") or {}).get("band") is not None,
            )
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    return S.summary()


if __name__ == "__main__":
    sys.exit(main())
