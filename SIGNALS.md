# SIGNALS.md — does any of this predict anything?

Every advisory number veritas emits — a fabrication risk score, an AI-likelihood
band, a depth score — has until now been *asserted* to be useful. This is the
harness that asks whether it is, against what a human actually concluded.

**It is analysis only.** Nothing here changes a score, a band, a threshold or a
decision. It reads reports and outcomes and reports numbers. There is no path
from this module to anything a candidate experiences.

---

## 1. The one thing to understand first: it refuses

PI-9 was gated on real organisations submitting outcomes, on the explicit
grounds that *"a harness measuring test fixtures would have been actively
misleading."* That is an argument against a harness which emits a number no
matter what it is fed.

So this one cannot. There are three refusals, and a refused signal carries **no
metric fields at all** — not a null AUC, not a zero, nothing to misread:

| Refusal | When | Why it is not a number |
|---|---|---|
| `insufficient_samples` | fewer usable labels than `min_signal_quality_samples` | A proportion from nine rows has a confidence interval spanning most of [0,1] |
| `degenerate_class` | every label is positive, or every label is negative | AUC is undefined, and a lift baseline of zero is meaningless |
| `label_kind_mismatch` | the signal cannot be scored by this source's labels | See §2 — this is a category error, not a weak measurement |

`0.5` is a **real** AUC meaning "separates nothing". Emitting it for an
impossible measurement would conflate a measured null result with one that
could not be taken. That distinction is the whole design.

---

## 2. Two ground truths, and they do not cross

There are two vocabularies in this system and they answer different questions:

- **`OutcomeLabel`** — a *fraud* vocabulary. `verified_genuine`,
  `verified_fabricated`, `candidate_clarified`, `inconclusive`. Recorded by an
  organisation (or an operator) against a report.
- **`InterviewOutcome`** — a *hiring* vocabulary. `hired`, `offer`, `rejected`,
  and so on, from the PI-3 ledger.

Scoring `depth_score` against `VERIFIED_FABRICATED` is not a weak measurement.
It is a category error — and it would still produce a plausible-looking AUC,
which is exactly what makes it dangerous. So a source **declares** the kind it
emits, a signal **declares** the kind it can be scored by, and the service
refuses the pairing rather than computing it.

That refusal is checked **first**, before the sample floor. A depth signal on a
fraud source is not "nearly measurable, just short of samples" — it is not
measurable at all, and answering `insufficient_samples` would invite someone to
go and collect more of a label that can never score it.

### Labels we decline to binarise

`CANDIDATE_CLARIFIED` and `INCONCLUSIVE` are in neither the positive nor the
negative set. Forcing them to 0 or 1 manufactures a judgment a human explicitly
declined to give, and it inflates `n` while doing it. `CANDIDATE_CLARIFIED` may
well be the wedge's most interesting label; it deserves its own analysis, not a
coin flip.

### Whose judgment counts

Operator labels are **excluded by default**. Training on our own operators'
self-labels while believing a customer produced them is circular. Both the route
and the CLI can opt in explicitly (`?include_operator_labels=true`), and the
population block always states which way the run went.

---

## 3. The twelve signals

A signal declares its own metric set. The alternative — computing four numbers
for everything and letting the reader work out which are nonsense — puts a
Brier score on an unbounded count and an AUC on an ordinal that was cast to a
float to make it fit. Both look like measurements.

| Signal | Kind | Metrics |
|---|---|---|
| `fabrication_risk.score` | fraud | AUC, Brier |
| `fabrication_risk.band` | fraud | lift |
| `ai_generation.likelihood` | fraud | AUC, Brier |
| `ai_generation.band` | fraud | lift |
| `cross_field.score` | fraud | AUC, Brier |
| `cross_field.band` | fraud | lift |
| `cross_field.major_findings` | fraud | AUC, lift |
| `resume_farm.score` | fraud | AUC, Brier |
| `resume_farm.band` | fraud | lift |
| `depth_score` | hire | AUC, Brier |
| `depth_band` | hire | lift |
| `overall_confidence` | hire | AUC, Brier |

The rule: a `[0,1]` score gets AUC and Brier; a band ordinal gets lift only;
an unbounded count gets AUC and lift but never Brier.

### An absent assessment is `None`, never `0.0`

Pre-S2.x stored reports and ad-hoc `POST /evaluate` runs carry no fabrication
assessment. `0.0` on a risk score reads as a confident *"no risk"* rather than
*"never assessed"*, so those reports drop out of **that signal's** sample and
are counted in nothing.

Note the asymmetry: an assessment that *ran* and found nothing is a real `0.0`
and belongs in the sample. Only the missing assessment itself is `None`. The
population block stays honest either way — `labels_usable` counts every label,
even when an individual signal's `n` is smaller.

---

## 4. Why `depth.*` reports nothing today

The three `depth.*` signals are scored by *hiring* outcomes, which live in the
PI-3 ledger. The ledger needs N organisations before it holds anything, and the
GTM deliberately keeps it off the sales pitch — so a ledger-only harness would
still be empty *after* the launch PI-9 was gated on.

This is the honest day-one state, and it is why `outcomes` is the default
source: it is what the fraud-screen wedge actually collects.

**What would change it:** real organisations submitting interview records under
an active `ledger_read` grant. Until then `?source=ledger` returns a population
of zero and every fraud signal refuses with `label_kind_mismatch` — which is
the harness working, not failing.

### Consent is read, not assumed

The ledger source calls `materialization_consent(candidate_id,
at=report.created_at)` and passes the decision through. It is evaluated **at the
report's own moment**, not "now": a grant that began after the report was
written did not authorize reading that subject when the prediction was made.

This is the one place in PI-9 that touches consented data, and the plan's
original `consent_allowed=True` was a real bypass. Two tests fail if anyone
restores it.

---

## 5. Leakage

A label must never be a row that fed the prediction. Both sources apply the
same rule — **strictly after** the report's `created_at`, borrowed from S4.4's
`build_label` rather than reimplemented, so there is one strict-after rule and
not two that agree today.

One report yields **one** label: the earliest *qualifying* one. That is the
judgment closest to the prediction, and it is the only rule under which
recording a new outcome tomorrow cannot silently change a measurement taken
today. "Qualifying" matters — an excluded row (an operator's, a leaking one, or
a label we decline to binarise) never consumes the report's one slot.

Per-claim outcomes are excluded entirely. A per-claim judgment is about one
claim; every signal measured here is report-level, and scoring a whole-report
number against a single claim's verdict is the category error one column over.

---

## 6. The sample floor is a knob, and 30 is a convention

```yaml
min_signal_quality_samples: 30    # usable labels per signal, or it refuses
signal_quality_curve_bins: 10     # reliability-curve bins; empty bins report null
```

**30 is not derived.** It is roughly where a proportion's confidence interval
stops spanning most of [0,1], and it is a knob precisely because the right value
is an empirical question this repo has no data to answer yet. A literal would
have made it unanswerable.

An empty calibration bin reports `null`, not `0.0`. Zero is a real observed rate
meaning "none of these were positive"; empty means "nothing was predicted here".
Collapsing them draws a point on a chart where no data exists — so there is no
smoothing and no interpolation either.

---

## 7. Reading a report

```
GET /admin/signal-quality?source=outcomes&include_operator_labels=false
python -m app.signal_quality.report --source outcomes
```

**Admin plane, and there is no org-plane variant.** The report is cross-tenant
by construction: an organisation must not be able to learn how well the fraud
screen performs against other organisations' candidates. The honest per-org
version ("how is it doing on *my* pipeline") is a different question with its
own sample-size problem, and inventing it here would ship a number computed from
a handful of rows.

The CLI prints the report as the **last line of stdout**, as JSON. It shares
stdout with the structured log, so the stream is a sequence of JSON documents
rather than one. Against an unmigrated database it exits **3** with a sentence
on stderr and no traceback — S8.6 found the retention sweep answering that same
case with a forty-line stack, and a cron is the caller nobody is watching when
it goes wrong.

---

## 8. What is verified

- `15/15` mutants dead over the metrics and the refusals —
  `python scripts/mutate_s91.py`. The numbers are this sprint's whole
  deliverable, so a suite that survives mutating them is not testing them. The
  harness is committed, unlike S8.3's and S8.5's, because a count nobody can
  re-derive is a claim rather than evidence.
- `scripts/smoke_s91.py` — 15/15, the refusals asserted on the serialized body
  an operator actually receives, plus both CLI exit codes.

## 9. Deliberately not here

- **No boot refusal.** The eight that exist guard configurations producing a
  service that *looks* healthy while being unsafe or unusable. This is advisory
  analysis tooling; refusing to start over a report nobody has asked for yet
  would be a ninth that earns nothing.
- **No scheduler.** Same as the retention sweep: an invocable thing, never a
  daemon.
- **No thresholds, no alerts, no auto-tuning.** The harness measures. Acting on
  what it measures is a decision a human makes, and calibration stays
  conservative and advisory.
