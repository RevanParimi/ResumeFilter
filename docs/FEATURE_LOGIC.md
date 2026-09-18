# Feature logic and current limits

Reviewed against local source on 2026-09-07. Numbers below are code defaults;
configuration can override them. This document describes implemented behavior.
Proposed changes are explicitly marked and tracked in [PROGRESS.md](PROGRESS.md).

## Resume input

The API accepts `resume_text` or `resume_pdf_b64`. The batch browser input accepts
PDF, TXT and Markdown (`.md`); TXT/Markdown are read as plain text. PDFs use pypdf
text extraction. There is no DOC/DOCX parser, image input or OCR for scanned PDFs.
The current malformed/empty PDF refusal gap is tracked as F07.

Sources: `src/app/api/routes.py`, `src/app/graph/nodes/ingest.py`,
`frontend/Veritas.dc.html` (file admission/reading).

## Writing-style signals

`src/app/fabrication/ai_text.py` measures four patterns:

- Template phrases: at least 60 words, at least three phrase hits; phrases
  include "results-driven", "proven track record", "spearheaded", "leveraged".
- Uniform bullets: at least six bullets, length coefficient of variation below
  0.22, and at least 85% beginning with a word ending in `ed`.
- Metric saturation: at least six bullets and at least 70% containing a percent
  or `x` metric; percentages divisible by five increase the signal.
- Symmetry: at least three groups of bullets, each with the same count of at
  least three bullets.

The deterministic score averages all detectors with enough input, including
zero for detectors that did not fire. Confidence increases with coverage:
`min(0.9, 0.30 + 0.15 * evaluated_detector_count)`. This is a heuristic coverage
score, not a measured probability of AI authorship. An optional LLM style
assessment is fused with it in `src/app/graph/nodes/ai_signals.py`.

**Yes, a truthful resume polished with AI can trigger these rules.** A human
using a resume template can too. The code observes patterns in the final text;
it has no evidence of who wrote it or whether the underlying experience is true.

Proposed F08: present these as optional writing-style observations and remove
their contribution to factual fabrication risk. This change is not implemented
in the foundations batch. Setting `fr_weight_ai=0` alone is insufficient: the
current fusion still includes that component in maximum-risk and coverage logic.

## Timeline checks

`src/app/fabrication/cross_field.py` compares dates within the extracted profile:

- Overlapping primary employment lasting at least three months.
- Gaps between primary roles of at least 12 months (minor context).
- Primary employment overlapping a bachelor's degree by at least 12 months.
- Senior/lead titles with less than 24/48 months of visible career span, subject
  to sufficient history and uncertainty guards.

Part-time/internship/freelance roles are treated differently from primary roles.
Year-only dates use conservative interval bounds to avoid inventing overlap.
These checks do not contact employers or verify actual attendance. Legitimate
work during study, simultaneous work and career breaks need candidate context.

## Near duplication

`src/app/fabrication/similarity.py` normalizes text, removes
contact-like strings/URLs, and forms overlapping three-word groups (shingles).
It needs at least 40 unique shingles and uses 128 MinHash values to estimate
Jaccard similarity against stored fingerprints belonging to other candidates.

Defaults: similarity at least 0.60 yields a match; at least 0.80, or similarity
to at least three distinct candidates, yields the near-duplicate band. This is
comparison against this application's stored corpus, not an internet search.
Shared templates, common phrasing and normalization can affect the result.
Similarity is a reason to examine overlapping content, not proof of plagiarism
or of a coordinated resume-writing operation.

## Combined advisory risk

`src/app/fabrication/risk.py` currently combines all three subsystems:

| Component | Low / middle / high band values |
|---|---|
| AI-style likelihood | 0.10 / 0.45 / 0.75 |
| Timeline consistency issues | 0.10 / 0.40 / 0.75 |
| Resume duplication | 0.10 / 0.45 / 0.80 |

Each usable component's weight is its configured weight times its confidence.
Missing/insufficient components are omitted. Then:

```text
risk = 0.70 * weighted_mean(component_values) + 0.30 * max(component_values)
confidence = min(0.90, 0.30 + 0.15 * usable_component_count)
```

Default confidence floor is 0.50, so one component alone gives insufficient
data. Moderate requires risk >= 0.30 and either one high-band component or two
non-low components. Elevated requires risk >= 0.60 and two high-band components.

This means "review these observations together", not "this person is X% likely
to be dishonest". It does not change depth scores/verdicts or automatically
reject candidates. F08 will separate style because AI polishing is legitimate.

## Employer screening outcomes

`src/app/reports/schema.py` and `outcomes.py` define a human feedback record:
`verified_genuine`, `verified_fabricated`, `candidate_clarified`, `inconclusive`.
It can apply to a report or one claim and records notes, actor/provenance and
time. Employer access is scoped to the organization's screening reports.

The outcome preserves the reviewer's resolution and supplies feedback for
signal-quality analysis. It does not rerun the report, automatically retrain
models, or mean the person was hired/rejected. Only qualifying genuine/fabricated
labels supply binary signal-quality ground truth; clarification/inconclusive
are excluded. Hiring-stage outcomes belong to the separate interview ledger.

R1-S1-T1 retention update: reports/outcomes remain in SQL, including reviewer
notes. The production observer no longer writes JSONL copies of claims, probes,
signals or outcomes. Candidate deletion reaches their SQL reports/outcomes;
standalone reports retain their separate report lifecycle. Existing JSONL files
are untouched and require the upcoming legacy-cleanup task.

## Authentication: CSRF and rate limiting

CSRF means Cross-Site Request Forgery: another site attempts to make a logged-in
browser send an authenticated change request. The browser automatically sends
session cookies, so cookie authentication alone is insufficient.

The UI reads `dee_csrf` and echoes it as `X-CSRF-Token` for write requests.
The authentication guard compares the nonempty cookie and header using
`hmac.compare_digest`; mismatches receive 403. This supplements SameSite cookie
controls. API-key requests use a different authentication path.
Sources: `src/app/auth/csrf.py`, `src/app/api/routes.py`, `frontend/api.js`.

Rate limiting counts requests within time windows using SQL-backed counters.
Keys depend on the operation: email/IP for login, organization for screening,
candidate for transcription/corrections. When a configured budget is exhausted,
the API returns 429 with retry guidance. OTP wrong-attempt limits and resend
cooldowns are additional controls. They reduce automated guessing, spam and
provider-cost abuse. F04 addresses the separately identified concurrent OTP
consumption/attempt-update defect; existing limits do not fix that race.

## Talent reputation

`src/app/ledger/reputation.py` aggregates consented cross-company interview
records and coding results. It does not infer reputation from resume style.

| Interview outcome | Value |
|---|---:|
| Hired | 1.00 |
| Offer | 0.90 |
| Advanced | 0.65 |
| Rejected | 0.15 |
| No-show | 0.10 |
| Withdrawn | Excluded |

Coding uses percentile/100, otherwise score/max_score. Unnormalizable coding
scores are excluded. Each observation has weight:

```text
weight = type_weight * organization_reliability * 0.5 ** (age_days / 365)
reputation = (2 + sum(weight * value)) / (4 + sum(weight))
confidence = min(0.90, round(sum(weight) / (sum(weight) + 4), 2))
```

These are defaults: neutral prior 0.5 with strength four, one-year half-life,
and default organization/type weights of one. Sparse evidence stays close to
neutral. One recent hired outcome gives score 0.60 and confidence 0.20, therefore
`insufficient_data`, not a strong reputation.

Confidence must reach 0.50 to assign a substantive band. Strong >= 0.75 and
guarded <= 0.35 require at least two organizations; favorable >= 0.60, otherwise
mixed. A rejection may reflect job fit or process issues, so these numerical
choices require validation and must remain advisory. Current-consent handling
for cached derived vectors is an outstanding F06 issue.

## Assessment, interviews and ML

`src/app/interview/questions.py` builds a question plan at session creation:
report follow-up probes first (flagged/deferred claims prioritized, up to two
probes per claim), then profile-based employment/skill questions and domain
seed questions. The backend supports one live session per candidate.

The candidate starts through `/portal/interviews` and submits the current
question's answer to `/portal/interviews/{id}/answers`. Answers may be text or
base64 audio. A configured speech provider transcribes audio; an unavailable
provider refuses transcription. Raw audio is not retained as a video archive.
The backend stores transcript/turn records and advances through the plan.

`src/app/interview/scoring.py` calculates specificity, ownership, depth and
consistency through deterministic signals, with an optional bounded LLM
adjustment. Session completion aggregates turns. The audit showed repetitive
keyword-filled nonsense can max these scores: F11 must repair and validate this
rubric before relying on it for assessment.

There is no camera/video session, streaming conversational interview, or
answer-adaptive follow-up loop in this implementation. The existing feature
store, ranking, label/export and experiment infrastructure does not establish
that a trained, validated interview model exists.

Video is a proposed feature requiring a candidate UI, session transport,
speech input/output, interruption/reconnection handling, and explicit recording
retention/consent behavior. Score answer content, not facial appearance,
expressions or inferred emotion. Conversational video is the working
recommendation; the user has not yet answered the optional format question.

## Foundations changes completed in this batch

- An unmatched email no longer merges into another profile through phone
  matching. Ambiguous phone-only matches create a separate profile. Existing
  email matches and unique phone-only matches still work. Existing persisted
  identity mistakes need a separate reviewed repair; this is not proof that
  arbitrary resume contact data belongs to the uploader.
- GitHub evidence now stays with the selected claim/candidate repo inside one
  evaluation. Removed shared vector-store add/query from provenance. The wider
  vector-store service remains wired pending F12/F13 cleanup. GitHub fetch-error
  polarity is a separate remaining evidence-quality issue.
- Materialization uses one snapshot timestamp per run and returns it. Search
  and matching read the latest eligible vector per candidate, retaining others
  after a partial refresh. Historical cutoffs exclude later vectors; exact-cut
  exports keep their existing semantics.

See [PROGRESS.md](PROGRESS.md) for test results and the next implementation batch.
