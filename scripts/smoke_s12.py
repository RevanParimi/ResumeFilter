"""S1.2 smoke: migrate a scratch DB with Alembic, then run the real flow —
extract → ingest → dedup/versioning → latest_profile → DPDP delete.

With no API key this exercises the heuristic extractor; with a key, the LLM
path. Both must land in the store identically. Run from the repo root:
    python scripts/smoke_s12.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.services.llm import build_llm

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "smoke_s12.db"
    url = "sqlite:///" + db_path.as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    settings = get_settings()
    store = CandidateStore(make_session_factory(make_engine(url)))
    llm = build_llm(settings)

    text = FIXTURE.read_text(encoding="utf-8")
    result = asyncio.run(extract_profile(text, llm=llm, settings=settings))
    first = store.ingest(result, text)
    print(
        f"ingest #1 [{result.method}]: candidate={first.candidate_id[:8]}"
        f" v{first.resume_version} matched={first.matched_existing}"
    )

    second = store.ingest(result, text + "\n\nUpdate: AWS certification added.")
    print(
        f"ingest #2 (updated text): matched={second.matched_existing}"
        f" on={second.matched_on} v{second.resume_version}"
    )

    dup = store.ingest(result, text)
    print(f"ingest #3 (same text as #1): duplicate_resume={dup.duplicate_resume}")

    profile = store.latest_profile(first.candidate_id)
    resumes = store.list_resumes(first.candidate_id)
    deleted = store.delete_candidate(first.candidate_id)
    gone = store.get_candidate(first.candidate_id) is None

    checks = {
        "identity matched on re-ingest": second.matched_existing
        and second.matched_on == "email_hash",
        "second resume is version 2": second.resume_version == 2,
        "identical text deduplicated": dup.duplicate_resume and dup.resume_version == 1,
        "latest profile readable": profile is not None,
        "two resume versions listed": [r.version for r in resumes] == [1, 2],
        "DPDP delete erases candidate": deleted and gone,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if failed:
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
