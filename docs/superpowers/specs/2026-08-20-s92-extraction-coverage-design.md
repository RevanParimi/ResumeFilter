# S9.2 — Extraction coverage (PI-9, sprint 2)

> **Status:** design approved 2026-08-20, spec written the same day.
> Baseline before any change: **1996 passing** (`pytest -q`, exit 0, 548.99s),
> `main` at `016f91f`, tree clean.

## 0. The question this sprint answers

S9.1 asked whether the advisory numbers predict what a human concluded. This
sprint asks the question underneath it:

> **Were those numbers computed from the resume, or from a hole where the
> resume used to be?**

Every signal veritas emits is derived from `CandidateProfile`. If the extractor
silently drops a section, every downstream check runs correctly over an empty
list and reports, honestly, that it had insufficient data. Nobody is lied to and
nobody can tell. That is the defect this sprint closes.

## 1. What was measured

Five resume shapes, run through `heuristic_profile()` on `main` at `016f91f`.
Not argued — executed:

| Shape | Result |
|---|---|
| `- Senior Data Engineer, Acme Analytics (2019 - Present)` — roles written as bullets | **exp=0** |
| the same resume with the bullets removed | exp=2 |
| the section header reads `CAREER HISTORY` instead of `EXPERIENCE` | **exp=0** |
| `Bachelor of Technology in Computer Science, VIT Vellore, 2015` | **edu=0** |
| `Programming Languages: Python, Java, Go` | skill named `"Programming Languages: Python"` |

Three of the five produce an **empty section from a resume that plainly has
one**. The fourth poisons skill matching and floods S6.3's curation queue with
category labels that will never map to anything.

The causes are each one line:

- `_experience` ([extractor.py:256](../../../src/app/candidates/extractor.py))
  skips every bulleted line, because under a role a bulleted line is a duty.
  Correct *within* an entry; wrong for the resume whose whole experience section
  is a bulleted list of roles.
- `_split_sections` ([extractor.py:98](../../../src/app/candidates/extractor.py))
  matches a header only when the stripped, lowercased, colon-trimmed line
  **equals** an alias. `CAREER HISTORY`, `EMPLOYMENT DETAILS`,
  `ORGANIZATIONAL EXPERIENCE` and `WORK EXPERIENCE (5 YEARS)` all miss, and
  their content stays in whatever section preceded them.
- `_DEGREE` ([extractor.py:47](../../../src/app/candidates/extractor.py)) knows
  `b.tech` and `mba` but not `bachelor`, `master`, `bba`, `b.a` or `m.a`, and
  `_education` requires a `_DEGREE` or `_GRADE` hit to open an entry at all.
- `_skills` splits on `[,;·|]` and never strips a leading `Category:` label.

## 2. Why this is PI-9 and not a bug fix

**`profile.experience` has six readers**, and every one of them degrades to
"nothing to check" on an empty list: `fabrication/cross_field.py`,
`features/definitions/candidate.py`, `interview/questions.py`,
`interview/scoring.py`, `verification/documents.py` and
`verification/moonlighting.py`. The fraud-screen wedge's entire pitch is those
checks.

**The system behaves correctly and that is the problem.**
`assess_cross_field` ([cross_field.py:363-387](../../../src/app/fabrication/cross_field.py))
gates every check on having enough dated entries and returns a bare
`CrossFieldAssessment()`, whose band defaults to `INSUFFICIENT_DATA`. Fusion
then *excludes* insufficient components rather than scoring them as zero risk
([risk.py:64,156](../../../src/app/fabrication/risk.py)). Both behaviours are
right. Their combination means a dropped experience section makes the headline
fabrication number **quieter**, not louder, and the report says
`insufficient_data` either way.

So the operator reading that report cannot distinguish:

- *this candidate has no work history* — a fresher, screen accordingly; from
- *the parser dropped the work history* — a senior hire, unscreened.

For a fraud screen those are opposite conclusions. Making the difference visible
is the deliverable.

**The one existing check cannot see any of this.** `_is_empty`
([extractor.py:552](../../../src/app/candidates/extractor.py)) is the only
"did extraction work?" test in the codebase, and it is an **all-of**: no name
AND no email AND no phone AND no education AND no experience AND no skills. A
profile with a name, an email and zero experience passes it untouched. It is a
floor against total failure, not a measure of coverage.

## 3. The instrument

New pure module `src/app/candidates/coverage.py` — no LLM, no network, no
database, no `app.` imports beyond schemas. It takes `(resume_text, profile)`
and reports where the text evidently states something the profile does not
carry.

### 3.1 The load-bearing rule: the instrument does not share the extractor's eyes

An instrument that detects evidence with the same code the extractor parses
with **cannot see that code's blind spot**. If coverage asked `_DEGREE` whether
the text mentions a degree, then the moment §5 widens `_DEGREE` the check stops
firing — and the moment it does *not*, the check agrees with the extractor that
there was nothing there. Either way it reports `complete` on the exact resume it
exists to catch.

So every coverage check derives its evidence **independently and more crudely**
than the extractor: broad word lists, "a line containing a four-digit year", "a
header-shaped line". Deliberately dumber, and never imported from
`extractor.py`.

The cost is false positives, and it is bounded by §3.3: a check fires only when
the profile has **nothing at all** for that field. A false positive therefore
says "we may have missed the education on a resume that has no education
entries" — an honest hedge, not a wrong claim.

### 3.2 The checks

| id | Evidence (independent of the extractor) | Fires when |
|---|---|---|
| `experience_not_extracted` | ≥1 line carrying a year range or a `Present`/`Current` end, outside an education-ish section, not itself degree-shaped | `profile.experience` is empty |
| `education_not_extracted` | ≥1 line carrying a broad degree word (`bachelor`, `master`, `diploma`, `b.*`, `m.*`, …) or a CGPA/percentage token | `profile.education` is empty |
| `skills_not_extracted` | a header-shaped line naming skills, followed by ≥1 non-empty line | `profile.skills` is empty |
| `contact_not_extracted` | an email- or phone-shaped token anywhere in the text | both `contact.email` and `contact.phone` are `None` |
| `section_unrecognized` | a header-shaped line matching no known alias, with content beneath it | always (informational) |

`section_unrecognized` carries the literal header text, bounded to
`coverage_max_header_chars`. It is the only gap that quotes the resume, and a
section header is not personal data — no other gap carries an excerpt, because
the report body is stored and a quoted line can hold an email or a salary
(S7.2's `claim_ref`, which stored 5031 characters including a UAN).

### 3.3 Total drops only

Every check fires on **empty**, never on "fewer than expected". Undercounting is
just as silent, but distinguishing "one role spanning two lines" from "two roles"
needs a ratio with a magic constant, and a false positive there accuses a
correct extraction. §9 records it as deliberately out of scope.

### 3.4 Bands, and the refusal

`CoverageBand`, mirroring `ConsistencyBand`'s vocabulary exactly:

| Band | Meaning |
|---|---|
| `insufficient_data` | the text is below `coverage_min_chars` — nothing can be said, and **no gaps are reported** |
| `complete` | checks ran, no gaps |
| `minor_gaps` | informational gaps only (`section_unrecognized`), every field populated |
| `major_gaps` | ≥1 field the text evidently describes is entirely absent from the profile |

`insufficient_data` is the default, as everywhere else in this codebase. A
refusal carries no gaps, in the S9.1 posture: a result that could not be taken
must not be readable as a result that came back clean.

## 4. Where it is computed — one place, both doors

Inside `extract_profile`, after `normalize_profile` and **before** contact
hashing, carried on `ExtractionResult` alongside `method` and `warnings`:

```
ExtractionResult(profile=..., method=..., warnings=[...], coverage=ExtractionCoverage(...))
```

This is the whole reason it goes there rather than in the heuristic path or in
the ingest core. **The LLM path drops things too**, and §2 showed `_is_empty`
waves a partial LLM profile straight through. This repo's signature defect —
found in S7.1, S7.2, S7.3, S8.4a and again in the S4.3 smoke — is a rule applied
at one entry point and not the other. Computing coverage at the single point
both paths already converge on closes that by construction rather than by
discipline.

A test asserts the two paths are measured by the same instrument: the same
resume text, extracted once heuristically and once through a fake LLM that
returns a profile missing the same section, must produce the same gap.

## 5. The fixes the instrument names

Each is TDD'd with the measured before/after from §1 as its test:

1. **Bulleted role lines.** If *every* dated line in an experience section is
   bulleted, they are roles, not duties. The disambiguation is principled rather
   than a special case: a duty list under a role always has an unbulleted dated
   line above it, so "all dated lines here are bulleted" means there is no role
   line for them to be duties of.
2. **Header matching.** Strip decoration and parenthetical suffixes before the
   alias lookup, and add the missing common aliases (`career history`,
   `employment details`, `organizational experience`, `professional summary`,
   `work summary`).
3. **Spelled-out degrees.** Widen `_DEGREE` to `bachelor`/`master`(`s`),
   `bba`, `b.a`, `m.a`, `bs`, `ms`.
4. **Labelled skill lines.** `Category: a, b, c` drops the label and keeps the
   values.

Fix 3 widens the extractor's degree regex; per §3.1 the coverage check must
**not** be re-pointed at it.

## 6. Surface

**`Report.extraction_coverage: Optional[ExtractionCoverage] = None`** — the
established pattern, `None` for every pre-S9.2 stored report exactly as
`ai_generation`, `cross_field` and `resume_farm` are `None` for reports written
before their sprints.

It reaches the report by the path `resume_farm` already uses, which is the
precedent for a signal computed outside the graph: `ingest.py` passes it to
`engine.evaluate(...)` → `EvaluationState.extraction_coverage` → the report node
copies it onto the `Report`.

**One sentence in the summary**, at `major_gaps` only, following the four
existing conditional sentences in `nodes/report.py`. It is the line an operator
actually reads, and it must say what happened without accusing the candidate:
the resume appears to state things the parser did not extract, so the absent
checks are absent for a reason about *us*.

**No projection change.** `redact_for_org` strips counterparty identity and
nothing else; extraction coverage describes the org's own uploaded document and
carries no other tenant's data, so it rides along in the existing deep copy. The
org sees it because the org should.

**No new route, no CLI, no UI.**

## 7. Data model

**No migration.** `ReportRow.body` is `JSON`
([reports/models.py:44](../../../src/app/reports/models.py)) and schema
evolution is Pydantic's job — the module docstring says so. No new table, no new
`ConsentPurpose`, no new erasure path: coverage is derived from a resume the
platform already holds and is stored inside a report that already cascades on
subject erasure.

New knobs in `config.yaml` under a `coverage_` prefix, mirrored on `Settings`:
`coverage_min_chars`, `coverage_max_header_chars`, `coverage_max_gaps`.

## 8. Testing

TDD, every test seen red first, fully offline.

1. **The five measured shapes from §1 become the first tests** — red on `main`,
   green after §5.
2. **A shape corpus.** One fixture per resume shape, asserting the coverage band
   *and* the extracted counts. A future extractor change that re-drops a shape
   fails here rather than in a smoke six months later.
3. **The instrument does not share the extractor's eyes** (§3.1): a test that
   fails if `coverage.py` imports the extractor's regexes, plus a case where the
   extractor is blind and coverage still fires.
4. **Both doors** (§4): heuristic and fake-LLM extraction of the same text
   produce the same gap.
5. **The refusal carries no gaps** — asserted on the type, not the values.
6. **No false positive on a genuine fresher**: a resume with education, skills
   and no work history at all reports `complete`, not `major_gaps`.
7. **Mutation pass** over the coverage predicates and the four fixed rules, in
   the S8.3/S9.1 pattern, with the harness **committed** — a count nobody can
   re-derive is a claim, not evidence.
8. **`smoke_s92`** — a live server, uploading each shape over HTTP and reading
   the coverage off the returned report, built on `scripts/_smoke.py`.

## 9. Non-goals

- **Undercounting** (§3.3).
- **Any change to a signal, threshold, band or weight.** Coverage is advisory
  and feeds nothing. It never changes `fabrication_risk`, `depth_score` or a
  verdict, and it is never a rejection signal.
- **An LLM in the coverage path.** It is the floor's own audit; it must work
  with no API key by construction.
- **The S9.1 tie-in.** Filtering the harness's population by extraction quality
  is a real confound and a later sprint's argument. SIGNALS.md gains one
  sentence naming it; no code.
- **Any UI.**
- **Rewriting the extractor.** Four named fixes, not an architecture.

## 10. Open questions

1. **Does `section_unrecognized` deserve a feedback loop?** It names header
   strings real customers actually use, which is exactly the input S6.3's
   curation queue was built for. Queueing them would turn the informational gap
   into an alias-learning loop. Left out of S9.2 because it needs a store, a
   route and a review surface — but it is the obvious S9.3.
2. **Should `major_gaps` appear on the screening queue read-model?** The queue
   deliberately carries scalars only and no Report. A coverage band is a scalar
   and arguably belongs there, since "this one didn't parse" is precisely the
   triage an operator wants before opening anything. Deferred: `batch_items`
   would need a column, which is a migration this sprint otherwise avoids.
3. **What is the right band for a resume that is genuinely unparseable** — a
   scanned image PDF whose text layer is 40 characters of noise? Today that is
   `insufficient_data`, which is correct and also indistinguishable from "very
   short resume". Revisit if it shows up in a real corpus.
