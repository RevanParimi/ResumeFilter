"""Resume section headers the extractor recognizes (S1.1), as data.

MOVED OUT OF extractor.py in S9.2 so app/candidates/coverage.py can ask what is
recognized WITHOUT importing the extractor. Spec §3.1 forbids coverage from
sharing the extractor's detection LOGIC; a declaration is not logic (plan
ruling R1), and this file deliberately contains no functions.
"""

from __future__ import annotations

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": ("education", "academics", "academic background", "qualifications"),
    "experience": (
        "experience", "work experience", "professional experience",
        "employment", "employment history", "work history",
    ),
    "skills": ("skills", "technical skills", "core skills", "skill set", "technologies"),
    "projects": ("projects", "personal projects", "key projects", "academic projects"),
    "certifications": (
        "certifications", "certificates", "licenses",
        "licenses & certifications", "courses & certifications",
    ),
}
