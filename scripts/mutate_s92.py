"""S9.2's mutation pass: deliberate one-line breaks that must all die.

The checks ARE the deliverable. A suite that survives mutating a refusal
direction or a severity is not testing them -- and a wrong coverage band still
returns a plausible-looking enum, which is the failure mode that hides longest.

Modelled on scripts/mutate_s91.py. Run from the repo root:
    python scripts/mutate_s92.py
Exit 0 means every mutant died. A SURVIVOR MEANS A TEST IS MISSING.

Two anchors below do NOT match the plan brief verbatim, because the code they
target moved under later rulings in this same sprint:

  * "fix4: skill category labels survive" -- Task 11's original one-line strip
    (`content = _SKILL_LABEL.sub("", content)`, called directly inside
    `_skills`) was replaced by ruling R15 with `_strip_skill_label()`, a
    helper that only strips when the line has exactly one colon and at least
    two comma-separated items follow it. The call site in `_skills` is now
    `content = _strip_skill_label(content)`; mutating it to `pass` reproduces
    the original mutant's intent (skip the strip entirely, so a category
    label survives) against the real line.
  * A new mutant, "R15: single-item colon-annotated skill loses its guard",
    targets the rule R15 itself ADDED (not moved): disabling the "at least
    two items after the colon" half inside `_strip_skill_label` so
    "C++: advanced" (one item, no comma) gets stripped anyway.

A new mutant for R10 (`_LIST_DELIMITERS` in `is_header_shaped`) is also added,
per the controller's instruction that both rulings added since the brief was
written need their own mutants.
"""

import pathlib, subprocess, sys

C = pathlib.Path("src/app/candidates/coverage.py")
E = pathlib.Path("src/app/candidates/extractor.py")

MUTANTS = [
 ("refusal: report COMPLETE instead of refusing on short text", C,
  "        return ExtractionCoverage()  # refusal", "        return ExtractionCoverage(band=CoverageBand.COMPLETE)  #"),
 ("refusal: min_chars boundary flips to >", C,
  "if len((text or \"\").strip()) < min_chars:", "if len((text or \"\").strip()) > min_chars:"),
 ("experience: fire even when entries exist", C,
  "if role_lines and not profile.experience:", "if role_lines:"),
 ("experience: academic lines count as roles", C,
  "and not looks_academic(line)", ""),
 ("experience: gap downgraded to MINOR", C,
  "            severity=GapSeverity.MAJOR,\n            field=\"experience\",",
  "            severity=GapSeverity.MINOR,\n            field=\"experience\","),
 ("education: fire even when entries exist", C,
  "if edu_lines and not profile.education:", "if edu_lines:"),
 ("contact: require BOTH to be missing becomes either", C,
  "profile.contact.email is None and profile.contact.phone is None",
  "profile.contact.email is None or profile.contact.phone is None"),
 ("band: MAJOR gaps read as MINOR", C,
  "        band = CoverageBand.MAJOR_GAPS", "        band = CoverageBand.MINOR_GAPS"),
 ("band: gaps present still reads COMPLETE", C,
  "    elif kept:\n        band = CoverageBand.MINOR_GAPS",
  "    elif False:\n        band = CoverageBand.MINOR_GAPS"),
 ("cap: truncated never reported", C,
  "    truncated = len(gaps) > max_gaps", "    truncated = False"),
 ("header quote: unbounded", C,
  "header=header.strip()[:max_header_chars],", "header=header.strip(),"),
 ("dated role: one year alone counts", C,
  "    return len(years) == 1 and bool(_PRESENT.search(line))", "    return len(years) == 1"),
 ("R10: delimited lists no longer rejected as headers", C,
  "    if any(ch in s for ch in _LIST_DELIMITERS):", "    if False:"),
 ("fix1: all-bulleted sections go back to being duties", E,
  "            if not all_dated_are_bullets:",
  "            if True:"),
 ("fix1: every bulleted section becomes roles", E,
  "    all_dated_are_bullets = bool(dated) and all(_BULLET.match(l) for _, l in dated)",
  "    all_dated_are_bullets = True"),
 ("fix2: header decoration no longer stripped", E,
  "            key = _header_key(line)",
  "            key = line.rstrip(\":\").strip().lower()"),
 ("fix4: skill category labels survive (re-anchored past R15's helper)", E,
  "        content = _strip_skill_label(content)", "        pass"),
 ("R15: a single-item colon-annotated skill loses its guard", E,
  "    if len(items) < 2:", "    if len(items) < 1:"),
]

SUITE = [
    "tests/test_extraction_coverage.py",
    "tests/test_extraction_coverage_independence.py",
    "tests/test_extraction_coverage_report.py",
    "tests/test_extractor_shape_corpus.py",
    "tests/test_candidate_extractor_heuristic.py",
]

# Byte-exact restore, and newline-agnostic matching. Python's ordinary
# text-mode read_text()/write_text() do universal-newline translation, which
# round-trips CRLF -> \n -> CRLF file-content-losslessly in principle, but
# measured on this machine it can still leave `git status` flagging a file
# dirty afterwards (git diff/hash-object agree there is no real change, so
# it is a line-ending bookkeeping artifact, not a content change -- but the
# harness's whole claim is that the tree comes back clean, so it must not
# happen). Fix: read raw BYTES once per mutant and always restore those exact
# bytes -- no encode/decode round-trip on the restore path at all. Matching
# is done against a CRLF-normalized copy of the text so the (LF-written)
# anchors in MUTANTS above match regardless of the file's real line endings;
# the mutated copy is re-CRLF'd before writing only if the file uses CRLF.
dead = survived = 0
for name, path, old, new in MUTANTS:
    original = path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    search = text.replace("\r\n", "\n") if crlf else text
    if old not in search:
        print(f"  ?? NOT APPLIED  {name}  (anchor missing in {path.name})")
        survived += 1
        continue
    mutated = search.replace(old, new, 1)
    if crlf:
        mutated = mutated.replace("\n", "\r\n")
    path.write_bytes(mutated.encode("utf-8"))
    try:
        rc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", *SUITE],
            capture_output=True, text=True,
        ).returncode
    finally:
        path.write_bytes(original)
    if rc == 0:
        print(f"  SURVIVED  {name}")
        survived += 1
    else:
        print(f"  dead      {name}")
        dead += 1

print(f"\n{dead}/{dead + survived} mutants dead")
sys.exit(0 if survived == 0 else 1)
