# S9.1 — Signal quality harness (PI-9, sprint 1)

> **Status:** design approved 2026-08-17, spec written the same day.
> Branch `s91-signal-quality`. Baseline before any change: **1854 passing**
> (`pytest -q`, exit 0, 318.91s), `main` at `9ac59b9`.

## 0. The question this sprint answers

Gap-analysis v2 §2 named **seven advisory numbers that have never been measured
against anything**. That is still the product's central risk: the entire value
proposition is that these numbers are worth reading, and no line of code in this
repo has ever asked whether any of them predicts a human's judgment.

This sprint builds the thing that asks.

## 1. The gate, and why the sprint proceeds anyway

**PI-9 was explicitly gated.** Gap-analysis v2 §5 (RESOLVED 2026-08-01) parked
the calibration harness on "real orgs submitting outcomes", with a warning worth
quoting because it is the objection this design has to survive:

> a harness measuring test fixtures would have been actively misleading.

That warning is correct and it is **not** an argument against building the
harness. It is an argument against a harness that will emit a number no matter
what it is fed. Those are different objects.

So S9.1 ships in this repo's established posture for a mechanism whose real
input does not exist yet — the same posture as S7.1's `government_id` method and
S7.2's EPFO adapter: **build the mechanism, and make the absence of real input a
refusal rather than a number.** A harness that structurally cannot report on an
insufficient sample is not misleading; it is the instrument that will be correct
on day one when real outcomes land, and honest every day before that.

The gate is therefore satisfied by construction rather than by waiting. §5 spells
out the three refusals that carry this claim.

## 2. Two prior framings this supersedes

Both were reasonable when written and both are wrong now. Recording why, so a
future session does not "restore" either.

### 2.1 §3.3's "metrics over the S4.2 × S4.4 join" — superseded

Gap-analysis v2 §3.3 scoped the harness as metrics over the existing
`ml_feature_vectors` × `build_label` join, and called it the cheapest
high-value sprint in the repo. The costing was right; the join is not.

`FeatureVector` is keyed `(candidate_id, as_of)` and `FeatureStore.get_vector`
matches `as_of` **exactly**. `outcomes` are keyed by `report_id`. Joining them
requires picking a vector "near" the report — a nearest-before rule, a tolerance
window, and a tie-break — every one of which is a place for leakage to enter
quietly.

**The Report body is the better predictor source, and not merely the cheaper
one.** The persisted `Report` already carries `depth_score`, `depth_band`,
`overall_confidence`, `fabrication_risk`, `ai_generation`, `cross_field` and
`resume_farm`, alongside its own `created_at`. What this harness needs to
calibrate is *the number a human was looking at when they recorded the
judgment* — and the report body is precisely that artifact, not a
reconstruction of it.

Consequences, all of them simplifications:

- the harness has **no feature-store dependency**;
- materialization is **not a prerequisite**, so the "no materialized
  candidates" condition that S8.4b had to turn into a 200 + reason never arises
  here at all;
- the join is **exact** — `outcome.report_id → report.id` — and needs no
  matching rule, so there is no window in which leakage can hide.

`ml_feature_vectors` remains PI-4's training-export concern, untouched.

### 2.2 "The ledger is the ground truth" — superseded by S8.5

`build_label` (S4.4) derives labels from `interview_records` and
`coding_round_results`. It is correct, pure, consent-gated, audited and
leakage-free, and it stays that way — this sprint does not edit it.

But the GTM doc §4.2 calls the ledger **"the worst cold-start in the repo —
worth zero to customer #1"** and keeps it off the pitch. A staffing agency
buying the fraud-screen wedge submits **nothing** to it. Meanwhile S8.5 shipped
an org-plane route that writes human judgments to `outcomes` — which is what
wedge customers actually produce, and which **nothing outside the API reads.**

A harness reading only the ledger would therefore still be empty *after* the
launch it was gated on. Hence the label seam in §4.

## 3. Package and dependencies

### 3.1 Name

**`src/app/signal_quality/`.** Both obvious names are already taken and neither
is being overloaded:

| Name | Already means |
|---|---|
| `app/core/calibration.py` | the conservative scoring gate (`aggregate_depth`, `classify`) — S2.4's fusion stage |
| `app/metrics/` | the Prometheus surface behind `GET /metrics` — S8.3 Phase A |

`signal_quality` states what is measured: whether an advisory signal has any
relationship to what a human concluded.

### 3.2 Modules

| Module | Holds | Depends on |
|---|---|---|
| `schema.py` | frozen result + refusal types | pydantic only |
| `metrics.py` | pure metric functions | **nothing** — stdlib |
| `labels.py` | the `LabelSource` seam + two implementations | stores |
| `service.py` | orchestration, the refusals, the report assembly | the above |

`metrics.py` importing nothing from `app/` is deliberate and is what makes every
number in §6 assertable against a hand-computed fixture.

### 3.3 No new dependency

`requirements.txt` has no numpy, scipy or scikit-learn (verified), and this
sprint adds none. Every metric is pure Python:

- **AUC** — rank-based Mann–Whitney U with **averaged ranks for ties**. Written
  out rather than imported, because a tie policy chosen silently by a library is
  exactly the kind of thing that makes a number look computed when it is
  arbitrary. Resume scores tie constantly (banded signals tie by design).
- **Brier** — mean squared error against the 0/1 label, on scores already
  constrained to `[0,1]` by their `Field(ge=0.0, le=1.0)`.
- **Calibration curve** — fixed-width bins, and **each bin carries its own
  `n`**. A bin's mean predicted-vs-observed gap is meaningless without it, and a
  chart that hides it is how a 2-sample bin gets read as a finding.
- **Lift by band** — positive rate per band against the overall base rate,
  grouped on the `*_band` categorical.

This also keeps the house rule intact: fully offline, deterministic, no API key.

## 4. The label seam — and why it carries semantics

```
LabelSource (Protocol)
├── OutcomesLabelSource   -> LabelKind.FRAUD   (default; reads `outcomes`)
└── LedgerLabelSource     -> LabelKind.HIRE    (wraps build_label, unedited)
```

### 4.1 The two label vocabularies are not interchangeable

`OutcomeLabel` is a **fraud** vocabulary — `VERIFIED_GENUINE`,
`VERIFIED_FABRICATED`, `CANDIDATE_CLARIFIED`, `INCONCLUSIVE`. The ledger's
`InterviewOutcome` is a **hiring** vocabulary — `HIRED`, `OFFER`, `ADVANCED`,
`REJECTED`, `NO_SHOW`, `WITHDRAWN`.

`fabrication.risk_score` predicts fabrication. `depth_score` predicts depth.
Scoring `depth_score` against `VERIFIED_FABRICATED` is not a weak measurement —
it is a **category error that would still produce a plausible-looking AUC.**
This repo has been bitten four times by a rule enforced at one door and
forgotten at a second; the fix each time was to make the wrong thing
unrepresentable rather than discouraged.

So: every signal declares the `LabelKind` it can be scored by, every
`LabelSource` declares the `LabelKind` it emits, and an incompatible pairing is
**refused**, never computed.

Naming every measured signal explicitly, because "the 12 registered features"
is ambiguous about the counts — several are structural tallies rather than
scores, and Brier is undefined on anything not constrained to `[0,1]`:

| Signal (from the Report body) | Kind | AUC | Brier | Lift | Available today |
|---|---|---|---|---|---|
| `fabrication_risk.score` | FRAUD | ✓ | ✓ | — | yes |
| `fabrication_risk.band` | FRAUD | — | — | ✓ | yes |
| `ai_generation.band` | FRAUD | — | — | ✓ | yes |
| `resume_farm.band` | FRAUD | — | — | ✓ | yes |
| `cross_field` major-finding count | FRAUD | ✓ | — | ✓ | yes |
| `depth_score` | HIRE | ✓ | ✓ | — | **no** |
| `depth_band` | HIRE | — | — | ✓ | **no** |
| `overall_confidence` | HIRE | ✓ | ✓ | — | **no** |

A signal declares its own metric set rather than the service computing four
numbers and leaving a reader to discover that one of them is nonsense. Ordinals
(`*_band`) get lift, not AUC-on-an-invented-encoding; unbounded counts get AUC
and lift but never Brier.

The remaining registered features — `depth.verdict_count`,
`flagged_claim_count`, `deferred_claim_count`, `coherent_claim_ratio`,
`candidate.*` — are **not measured here.** They are inputs and demographics, not
advisory numbers the product asks anyone to trust, and gap-analysis §2's list is
the one that defines this sprint's job.

Half the measured signals correctly report nothing on day one. That is the
design working, and §7's surface says so in words rather than leaving a reader
to infer it from an empty object.

### 4.2 Label mapping, stated explicitly

`OutcomeLabel → binary positive` for the FRAUD kind:

| Label | Maps to | Why |
|---|---|---|
| `VERIFIED_FABRICATED` | positive (1) | the event the fraud signals exist to predict |
| `VERIFIED_GENUINE` | negative (0) | a confirmed clean resume |
| `CANDIDATE_CLARIFIED` | **excluded** | the flag prompted a question and the answer resolved it; that is neither a confirmed fabrication nor a confirmed clean record, and forcing it either way manufactures a label a human declined to give |
| `INCONCLUSIVE` | **excluded** | says so on the tin |

Excluded rows are excluded from `n`, so the §5 sample refusal counts *real*
labels and not rows.

### 4.3 Operator self-labels are excluded by default

`OutcomeRow.recorded_by` exists because of this sprint. Its docstring, written
in S8.5, is a message left for PI-9:

> PI-9 must never train on our operator's self-labels believing a customer
> produced them; that is circular, and the derived answer would always look
> plausible.

`recorded_by=OPERATOR` rows are therefore excluded from the default run. They
remain reachable behind an explicit flag, because an operator label is still
real evidence when a reader knows that is what it is — the defect is the
conflation, not the row. The flag's value is echoed in the result, so a report
can never be read without knowing which population produced it.

Note this is *not* derivable from `org_id`: it SET NULLs on offboarding, so a
null org conflates "our operator wrote this" with "the customer who wrote this
has gone".

## 5. The three refusals

A refusal returns `sufficient=false`, a stable `reason` code and `n`. It carries
**no metric fields at all** — not zeros, not nulls in a result-shaped object.
The result types are separate models rather than one model with optional
fields, so "a refusal that still has an AUC attribute" is unrepresentable.

| # | Refuses when | Reason code | The failure it prevents |
|---|---|---|---|
| 1 | usable labels `< min_signal_quality_samples` | `insufficient_samples` | the gap analysis's exact objection — a harness reporting on fixtures |
| 2 | the positive class is degenerate (all-positive or all-negative) | `degenerate_class` | AUC is undefined here, and libraries variously return `0.5`, `nan`, or raise. `0.5` reads as "no signal" when the truth is "no measurement" |
| 3 | signal `LabelKind` ≠ source `LabelKind` | `label_kind_mismatch` | §4.1's category error |

`min_signal_quality_samples` is a `config.yaml` tunable. **No boot refusal is
added** — the existing eight guard configurations that produce a service which
looks healthy while being unsafe or unusable. This is advisory analysis tooling;
a ninth refusal here would be refusing to start over a report nobody has asked
for yet.

## 6. Leakage

One rule, the same one `build_label` already uses, applied at the only join
this harness has:

- `as_of := report.created_at`
- a label counts only when `recorded_at > as_of`, **strictly**

An outcome recorded at or before the report's creation cannot have been informed
by that report, and a row that fed the prediction must never become its label. A
test asserts the boundary case directly — a row exactly on `as_of` is excluded.

## 7. Surface

### 7.1 `GET /admin/signal-quality` — admin plane only

Never org-plane, for a reason worth stating: this report is **cross-tenant by
construction**, and an organisation must not be able to learn how well the fraud
screen performs against other organisations' candidates. There is no redacted
org-plane variant in this sprint and none is planned; the honest per-org version
is a different question ("how is the screen doing on *my* pipeline") with its own
sample-size problem, and inventing it here would ship a number computed from a
handful of rows.

Response states, per signal: the metrics, or the refusal and why. Plus the run's
own population — label source, kind, whether operator labels were included, `n`,
and the **observed** date range of the reports that contributed (min and max
`created_at`) — because a metric without its population is not interpretable.

That range is *reported*, not a filter: this sprint takes no date parameters.
A time-sliced view (has the signal drifted?) is a real question and a later
sprint's, and adding an unused parameter now would be a knob whose first real
use is untested.

### 7.2 `python -m app.signal_quality.report`

Mirrors `app/retention/sweep.py`'s entry point: an invocable thing, never a
daemon. There is still no worker anywhere in `app/`.

**It must exit cleanly on an unmigrated database.** S8.6 found the retention CLI
exiting 1 with a traceback in exactly that situation — the most likely first
thing a cron encounters — and the fix cost fifteen lines. Same treatment here
from the start: a distinct exit code and a sentence.

## 8. Data model

**No new table and no migration.** This sprint reads existing rows.

One addition to the `ReportStore` Protocol: a cross-report outcome reader, since
today's `outcomes(report_id)` and `outcomes_for_org(org_id, report_id)` are both
report-scoped. It is admin-plane only and returns rows joined to their report's
`id`, `created_at` and body signals.

There is exactly one implementation (`SqlReportStore`) and the tests exercise it
against real SQLite — no in-memory fake to drift out of sync, which retires the
"a fake that cannot enforce an invariant will hide it" trap for this sprint
before it can apply.

## 9. Testing

TDD, every test seen red first, fully offline.

1. **Hand-computed metric fixtures.** A 6-row AUC computable on paper, a Brier
   with a known answer, a calibration curve whose bin membership is obvious by
   inspection. `metrics.py` imports nothing from `app/`, so these are unit tests
   in the strict sense.
2. **The tie policy is pinned.** A fixture where several scores are equal, with
   the averaged-rank answer asserted — otherwise a future refactor to
   sort-based AUC changes results silently.
3. **Leakage.** An outcome recorded before its report never becomes a label; a
   row exactly on `as_of` is excluded.
4. **Each refusal fires and releases.** `n-1` refuses and `n` answers, for the
   sample threshold; all-positive and all-negative both refuse; a
   `depth.*` × FRAUD pairing refuses.
5. **A refusal carries no metrics** — asserted on the type, not on the values.
6. **Operator exclusion** is on by default, and the result echoes which
   population it used.
7. **Mutation pass** over `metrics.py` and the refusal predicates, in the S8.3
   pattern — the numbers here are the whole deliverable, so a test suite that
   survives mutating them is not testing them.
8. **`smoke_s91`** — a live server: seed reports and outcomes over HTTP, hit the
   admin route, observe a refusal below threshold and a real report above it,
   and run the CLI including against an unmigrated database.

## 10. Non-goals

- **The other five advisory numbers** — reputation (S3.4), match (S5.1), comp
  (S5.2), assurance (S7.1–7.2), interview band (S7.3). None is on the Report
  body; each needs its own point-in-time snapshot decision. A later PI-9 sprint,
  once this one proves the instrument reads true.
- **Any change to the signals themselves.** This sprint measures; it does not
  retune a threshold, a weight or a band boundary. Acting on a finding is the
  next sprint's argument, made with the finding in hand.
- **Training a model.** Measurement, not learning. The flywheel's
  delete-or-repurpose question (v2 §3.2) stays open and untouched.
- **An org-plane view** — §7.1.
- **Editing `build_label`.** It is correct; the seam wraps it.
- **Any UI.** The route and the CLI are the surface.

## 11. Open questions

1. **Bin count for the calibration curve.** Ten fixed-width bins is the
   conventional default, but with a small `n` most bins are empty and the two
   that are not carry everything. Proposal: fixed-width bins, each reporting its
   own `n`, and no smoothing — an empty bin shows as empty rather than
   interpolated. Revisit when a real distribution exists to look at.
2. **Whether `CANDIDATE_CLARIFIED` should stay excluded.** §4.2 excludes it, and
   that is the conservative call — but it is plausibly the most interesting
   label in the vocabulary, because it marks the cases where the screen *did*
   its job (raised a question that got answered) rather than cases where it was
   right or wrong. Excluding it may be discarding the wedge's actual success
   signal. Left excluded for now because forcing it to 0 or 1 manufactures a
   judgment a human declined to give; revisit when there are enough of them to
   look at as their own population.
