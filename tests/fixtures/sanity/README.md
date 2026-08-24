# Sanity fixtures — the data each advisory signal actually needs

Every number in this file was MEASURED against the running pipeline
(`POST /candidates`), not read off the source. Re-measure before trusting it if
the extractor or the thresholds move.

## Why this directory exists

`tests/fixtures/genuine_genai_resume.txt` — the fixture most smokes reach for —
yields **0 experience, 0 education, 0 skills** under the heuristic extractor. It
was written for the depth/claim pipeline, so it is a header plus four undated
achievement bullets and nothing else. Sanity-testing extraction, cross-field or
fabrication against it measures the empty path and reports `insufficient_data`
everywhere. These files exist so a sanity run exercises the populated path.

## What each signal requires

| Signal | Requirement (measured) | Where the gate lives |
|---|---|---|
| `contact.email` | a line containing `x@y.tld` | `extractor.py:47` `_EMAIL` |
| `contact.phone` | **Indian format only** — `+91 98765 43210`, i.e. a leading digit 6-9 then 4+5 digits. A US-style number does NOT match | `extractor.py:48` `_PHONE` |
| `profile.experience` | a recognised section header (`Work Experience`, `Employment`, `Career History`, …) **plus** an UNBULLETED role line carrying a date range — two date points, or one plus `Present` | `sections.py:13`, `extractor.py:308`, `dates.py:64` |
| `profile.education` | a line matching `_DEGREE` — `B.Tech`, `M.Tech`, `B.E`, `MCA`, `MBA`, `Bachelors`… (note: `BS`/`MS` are deliberately NOT in the pattern — S9.2 ruling R14, they match `MS Office`) | `extractor.py:50` |
| `profile.skills` | a `Skills` / `Technical Skills` / `Technologies` header over a comma-separated list | `sections.py:29` |
| `cross_field` | needs DATED experience entries. With none it returns `insufficient_data` — honestly, but it means the check never ran | `nodes/cross_field.py:29` |
| `ai_generation` | **≥60 words AND ≥6 bullets**, and ≥3 job entries for the structural check. Below any of these: `insufficient_text` | `fabrication/ai_text.py:36-38` |
| `resume_farm` | ≥40 three-word shingles after contact-masking, ≥0.60 Jaccard for `similar` / ≥0.80 for `near_duplicate` — **and the compared resumes must belong to DIFFERENT candidates** | `config.py:339-343`, `screening/ingest.py:121` |
| `fabrication_risk` | fuses whichever of the three above produced a signal; with none it is `insufficient_data` | `fabrication/risk.py:148` |

## THE TRAP that costs an afternoon

Resume-farm clones must differ in **BOTH email and phone**. Identity resolution
dedups on email+phone hash, so clones sharing a phone number resolve to ONE
candidate — and the farm check excludes a candidate's own resumes
(`ingest.py:132 exclude_candidate_id`). Measured: four clones differing only in
name and email produced `farm=unique, matches=0` on every one. The same four
with distinct phones produced `near_duplicate` with 1, 2 and 3 matches.

## The files, and what each one is for

| File | Measured result |
|---|---|
| `senior_complete.txt` | 2 experience · **2 education** · 6 skills · coverage `complete` · cross_field `consistent` · fabrication `low` (2 components). The happy path. |
| `fresher.txt` | **2 education** · 5 skills · 0 experience · coverage `complete` · cross_field `insufficient_data` · depth `insufficient_signal`. Proves an education-only resume is not a parse failure. |
| `ai_signals_three_roles.txt` | 3 roles · 9 bullets · 187 words. The only fixture that clears the AI gates: `ai_generation` = **`possible`** on `template_phrases`, `uniform_bullets`, `symmetric_structure`, and fabrication fuses **all three** components. |
| `farm_clone_{1,2,3}_*.txt` | Near-duplicates of `senior_complete.txt` with distinct identities. Upload all four in order: farm goes `unique` → `near_duplicate` (1) → (2) → (3) and fabrication rises to `moderate`. |

## Order matters for the farm cohort

```
POST /candidates  senior_complete.txt      -> farm unique          fabrication low
POST /candidates  farm_clone_1_meera.txt   -> farm near_duplicate  fabrication moderate
POST /candidates  farm_clone_2_vikram.txt  -> farm near_duplicate (2 matches)
POST /candidates  farm_clone_3_ananya.txt  -> farm near_duplicate (3 matches)
```

## An extraction artifact to expect, not to debug

Both resumes carrying a `CGPA: 8.6/10` line extract **2** education entries, not
1: the degree line opens one and the CGPA line opens a second with
`degree=None, institution=None`. Coverage still reports `complete` (its check
fires on EMPTY, never on "more than expected" — spec §3.3), so this is cosmetic
in the advisory numbers but it will look wrong on a profile screen. Put the
grade on the degree line itself to get a single entry.

## Instrument bug found while measuring these — FIXED

`coverage.looks_academic` matched `_DEGREE_WORDS` as SUBSTRINGS, and `b.com`
lives inside **`github.com`**. Any resume carrying a GitHub link counted as
degree-bearing and raised a false `education_not_extracted` whenever education
was genuinely absent — in a tech-hiring product, most resumes. It is what made
`genuine_genai_resume.txt` report `major_gaps` on a resume with no degree line
at all; it now reports `complete`.

Fixed on branch `s92-fix-degree-false-positive`: word-boundary matching, an
explicit link/email strip, and a required dot on the two-letter abbreviations
(an optional one would match the English words "be" and "ma"). Pinned by
`test_a_url_is_never_a_degree_bearing_line`, its English-word sibling, and the
`github_link_no_education` row of the shape matrix. 3/3 mutants dead.

STILL OPEN, same bug class, different module: the EXTRACTOR's own `_DEGREE`
spells this `b\.?e`, which matches the bare word "be". A line in an education
section reading "This programme will be announced later" becomes an education
entry whose degree is that whole sentence. Narrower than the coverage bug (it
only fires inside a recognised education section) but real, and not fixed here
— changing the extractor changes what gets EXTRACTED, not just what gets
flagged.
