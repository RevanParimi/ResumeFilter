"""S1.1 smoke: run the profile extractor end-to-end on the fixture resumes.

Uses build_llm() — with no API key this exercises the deterministic floor
(NullLLM), with a key it exercises the live LLM path. Both must produce a
non-empty profile. Run from the repo root:  python scripts/smoke_s11.py
"""

import asyncio
import sys
from pathlib import Path

from app.candidates.extractor import extract_profile
from app.core.config import get_settings
from app.services.llm import build_llm

FIXTURES = Path("tests/fixtures")
RESUMES = (
    "full_profile_resume.txt",
    "genuine_genai_resume.txt",
    "fabricated_genai_resume.txt",
)


def main() -> int:
    settings = get_settings()
    llm = build_llm(settings)
    for name in RESUMES:
        text = (FIXTURES / name).read_text(encoding="utf-8")
        result = asyncio.run(extract_profile(text, llm=llm, settings=settings))
        p = result.profile
        print(f"\n=== {name} [{result.method}] warnings={result.warnings}")
        print(
            f"  name={p.full_name.value if p.full_name else None!r}"
            f" email_hash={(p.contact.email_hash or 'none')[:12]}"
            f" edu={len(p.education)} exp={len(p.experience)}"
            f" skills={len(p.skills)} projects={len(p.projects)}"
            f" certs={len(p.certifications)} links={len(p.links)}"
        )
        # Same emptiness contract as the extractor's LLM→heuristic fallback:
        # a profile that carries not even a name or contact point is a failure.
        if not (
            p.full_name or p.contact.email or p.contact.phone
            or p.experience or p.skills or p.links
        ):
            print(f"  FAIL: extractor produced an empty profile for {name}")
            return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
