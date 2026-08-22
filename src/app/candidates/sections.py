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
        "career history", "employment details", "organizational experience",
        "organisational experience", "work summary",
        # NOT "professional summary" (S9.2 ruling R13, deliberate): in the
        # overwhelming majority of resumes a "Professional Summary" section is
        # prose near the top, not employment history -- and _experience opens
        # an entry for any line in the recognized section carrying a date
        # range, so a summary sentence mentioning "2015 - 2023" would
        # manufacture a fabricated job with no employer. Missing a role is a
        # bounded, honest gap (and the coverage instrument built in S9.2
        # Tasks 4-5 reports it as experience_not_extracted); inventing one is
        # not, and this sprint exists to stop the extractor being silently
        # wrong. Do not add it back.
    ),
    "skills": ("skills", "technical skills", "core skills", "skill set", "technologies"),
    "projects": ("projects", "personal projects", "key projects", "academic projects"),
    "certifications": (
        "certifications", "certificates", "licenses",
        "licenses & certifications", "courses & certifications",
    ),
}
