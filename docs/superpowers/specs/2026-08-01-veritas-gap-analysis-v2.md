# Veritas — Gap Analysis v2 (post-PI-7 re-audit)

**Date:** 2026-08-01
**Status:** Planning reference. **Supersedes**
`2026-07-26-veritas-vision-gap-analysis.md`, which was written when S3.4 was the
next sprint and is now four PIs stale in its "what exists today" section.
**Audience:** any future session shaping PI-8 or beyond. Read `docs/ROADMAP.md`
first; read this second.
**What v1 got right and this keeps:** the vision (§2 there, unchanged), the
capability map (§4 there, unchanged), the non-negotiables (§7 there, unchanged),
and the PI-5→PI-6→PI-7 sequencing, which was executed as designed.
**What this corrects:** the asset inventory, three claims about PI-8 that turn
out to be wrong, and the gaps PI-5..PI-7 *created* that v1 could not have known
about.

---

## 1. What exists today — measured, not remembered (2026-08-01)

Every number below was counted from the tree at `5e73216`, not recalled.

| | |
|---|---|
| App code | 19 packages, ~18 100 lines |
| Main database | **20 tables**, 15 Alembic migrations, SQLAlchemy, SQLite (Postgres-shaped) |
| Second database | **2 tables** (`reports`, `outcomes`) — raw `sqlite3`, self-creating schema, **outside Alembic** (see §3.1) |
| HTTP surface | **63 endpoints**: 27 admin (`X-API-Key`) · 20 org (`X-Org-Key`) · 15 candidate (`X-Candidate-Key`) · 1 public |
| Tests | 169 files, **1175 tests**, fully offline |
| Smokes | 26 scripted uvicorn runs, one per sprint |
| Config | 140 knobs in `Settings` |
| LLM call sites | 6 (extraction · ai_signals · claim_extraction · plausibility · probe_generation · interview scoring) |
| ASR call sites | 1 (interview answers) |
| Domains registered | 2 (`genai`, `data_eng`) |

**Subsystem status:**

| Subsystem | State | Honest note |
|---|---|---|
| Depth-eval pipeline (`app/graph`, `app/domains`) | **Live** | Claim → probe → verdict → report. Advisory. Deterministic fallback throughout. |
| Candidate backbone (`app/candidates`) | **Live** (PI-1) | Extraction w/ confidence + provenance; versioned store; hashed-contact identity resolution; hard-delete paths. |
| India normalization | **Live** (S1.4) | Static tables + an S6.3 curation overlay. No auto-learning. |
| Fabrication defense (`app/fabrication`) | **Live** (PI-2) | AI-text, cross-field, MinHash farm detection, fused `fabrication_risk`. |
| Evaluation ledger (`app/ledger`) | **Live** (PI-3) | Orgs, org keys, purpose-scoped revocable consent, interview records, coding rounds, reputation, audit-of-every-touch. |
| Feature store + ranking (`app/features`) | **Live** (PI-4) | Registry → point-in-time materialization → search/ranking → **training export with leakage-free labels**. |
| Demand side (`app/matching`, `app/comp`, `app/dashboard`) | **Live** (PI-5) | Requisitions + role-conditioned match, comp bands + observed offers, read-only board/card. |
| Candidate side (`app/profile_sources`, `app/curation`, `app/portal`) | **Live** (PI-6) | GitHub + LinkedIn export as signals, curation loop, candidate auth + DPDP portal. |
| Verification (`app/verification`) | **Live** (S7.1–7.2) | Assurance ladder + employment-claim ladder, document forensics. Govt-ID and EPFO declared-inert. |
| AI interviews (`app/interview`) | **Live** (S7.3) | Probe-driven, deterministic scoring, live ASR seam, proxy signals. |
| Vector store | **Fake** | `HashingEmbedding` = md5 token hashing. Not semantic. Unchanged since M0. |
| Flywheel | **Write-only** | 6 write sites, **0 readers** — see §3.2. |
| Observability | **structlog only** | No metrics, no tracing, no error aggregation. |
| Multi-tenancy | Single-tenant | Deliberate (YAGNI). |
| Rate limiting | **None, anywhere** | 63 endpoints, no limiter. |

## 2. The headline finding

**Veritas now produces seven advisory numbers, and not one of them has ever
been checked against reality.**

| Number | Since | Validated against an outcome? |
|---|---|---|
| `depth_score` / `depth_band` | M0 | ✗ |
| `fabrication_risk` | S2.4 | ✗ |
| `resume_farm` / `ai_generation` / `cross_field` | PI-2 | ✗ |
| reputation | S3.4 | ✗ |
| match score | S5.1 | ✗ |
| comp estimate | S5.2 | ✗ |
| `IdentityAssurance` / `ClaimStrength` | S7.1–7.2 | ✗ (definitional, not predictive) |
| interview band + proxy risk | S7.3 | ✗ |

Every one is conservatively calibrated, advisory, and human-reviewed — which is
the right posture and is *not* a substitute for knowing whether any of them
correlates with a hire. The product's entire value proposition is that these
numbers are worth reading.

This finding originally argued for opening PI-8 on the calibration harness (§5),
and §3.3 shows it would also be the *cheapest* sprint — which was not obvious
before this audit.

**That argument lost, on 2026-08-01, to a fact the audit could not supply.**
There is no pilot org and none close, so there are no real outcomes to measure;
the harness would compute metrics over test fixtures. The seven unvalidated
numbers remain the product's central risk — but the way to retire that risk is
to get real orgs submitting outcomes, which is **PI-8 = launch readiness (§9)**.
Calibration becomes **PI-9**, and §3.3 will still be true when it arrives.

## 3. Three corrections to v1's PI-8 assumptions

### 3.1 "Postgres migration — low risk by design" is **half true**

v1 called this low-risk because the schema is PG-shaped. That holds for the
**main** database: 20 tables, real FKs, UUID-string PKs, JSON columns, 15
Alembic migrations, and a `make_engine` that already branches on dialect. A
connection-string change plus a CI matrix genuinely covers it. Six migrations
use `batch_alter_table`, which is a SQLite accommodation that degrades to
ordinary `ALTER` on PG — not a blocker.

**But `app/services/report_store.py` is a second database that speaks raw
`sqlite3`** (212 lines, stdlib driver, `CREATE TABLE IF NOT EXISTS` at
construction, no Alembic, no SQLAlchemy). It holds `reports` and — importantly —
**`outcomes`, the human-recorded outcome records**. For PG that is a *rewrite*,
not a connection string.

Two mitigations, both real: it sits behind a `ReportStore` `Protocol` with an
`InMemoryReportStore` already used by every test, so the rewrite is bounded and
testable; and only 6 modules consume it. Call it a day of work, not a week — but
it must appear in S8.1's scope, because today it is invisible in the plan.

### 3.2 The flywheel is not "unconsumed" — it is **redundant**

v1 said flywheel records are "written, never consumed" and put consumption in
PI-8. Still literally true: 6 `flywheel.log(...)` sites, zero readers. But S4.4
changed what that means. `app/features/training.py::build_label` derives
point-in-time-correct, leakage-free labels **from the ledger** —
`interview_records` and `coding_round_results` — and never touches the flywheel
JSONL.

So the label pipeline the flywheel was built to feed **already exists and uses a
better source** (consented, audited, revocable, relational). The open question
is no longer "when do we consume the flywheel" but **"delete it or repurpose
it"**. That is a decision for PI-8's brainstorm, and either answer is defensible:
the JSONL captures per-claim reasoning that the ledger does not, which could
matter for training a *model*, as opposed to measuring calibration.

### 3.3 The calibration harness is much closer than v1 assumed

v1 scoped S8.2 as "offline eval harness over ledger outcomes", implying a
build from scratch. In fact PI-4 already shipped two of its three parts:

- **Features at `as_of=T`** — `ml_feature_vectors`, point-in-time correct (S4.2).
- **Leakage-free labels strictly after T** — `build_label`, pure and tested,
  with a `_withheld_label()` path when consent does not permit (S4.4).
- **Missing: the comparison itself** — do the advisory numbers predict the
  label? That is metrics (AUC, Brier, calibration curves, lift by band) over a
  join that already runs.

This is the finding that most changes PI-8's shape: **the highest-value sprint
is also the smallest.**

## 4. New gaps that PI-5..PI-7 created (v1 could not have known these)

| Gap | Why it matters | Landing zone |
|---|---|---|
| **Seven unvalidated advisory numbers** (§2) | the product's core claim is untested | **PI-8, first sprint** |
| **No rate limiting on 63 endpoints** | a stolen candidate key can drive unbounded ASR spend (S7.3 review); a stolen org key can drive unbounded queries | PI-8 (with observability — you cannot limit what you cannot measure) |
| **Candidate registration is admin-minted** | `POST /candidates/{id}/auth-key` is the only way to get a key; there is no self-registration, password, or session | PI-8 or PI-9 — blocks any real candidate pilot |
| **ASR quality unverified on Indian-accented English** | S7.3's whole premise; the live check proved the *seam*, not the hearing | Needs an audio corpus. Blocks trusting interview scores in production |
| **voxtral hallucinates on non-speech audio** | a silent/garbled recording yields confident fabricated text | S7.3 follow-up: a no-speech guard on the adapter |
| **Retention sweep still absent** | `RetentionPolicy.sweep_active=False` everywhere; DPDP purpose-limitation is asserted but not enforced | PI-8 — deferred since S6.4 and now the oldest outstanding compliance gap |
| **`docs/superpowers/plans/` and specs are the only design record** | 26 smokes, no single end-to-end story | Optional: one composite smoke |

## 5. Revised PI-8 proposal

v1 proposed S8.1 Postgres → S8.2 calibration → S8.3 observability. **This audit
argues for reordering**, with the reasoning made explicit so a future session can
disagree on the merits:

```
PI-8  SCALE & LEARNING  (revised 2026-08-01)
 ├ S8.1  CALIBRATION HARNESS  (was S8.2)
 │       Metrics over the EXISTING S4.2 features x S4.4 labels join:
 │       AUC / Brier / calibration curves / lift-by-band for each advisory
 │       number. Answers "does any of this work", needs no new infra, and
 │       tells PI-9 which signals deserve investment. Also decides the
 │       flywheel's fate (section 3.2).
 ├ S8.2  POSTGRES CUTOVER + REPORT-STORE REWRITE  (was S8.1)
 │       Connection string + CI matrix for the main DB; a real rewrite for
 │       app/services/report_store.py (section 3.1). Do it AFTER S8.1 so the
 │       harness is not blocked on infra, and because S8.1 may reveal the
 │       report store should be folded into the main DB rather than ported.
 ├ S8.3  OBSERVABILITY + RATE LIMITING
 │       Metrics/tracing, plus the limiter the S7.3 review flagged. Paired
 │       because a limit you cannot observe is a guess.
 └ S8.4  REAL EMBEDDINGS + ANN  (was inside S8.1)
         Replaces HashingEmbedding; upgrades farm detection from single-DB
         MinHash. Split out because it is the one piece with a genuine
         infra dependency (a model + a vector store) and the least urgency.
```

**Why calibration first, stated as an argument rather than a preference:** it is
the only sprint whose output changes what the *other* sprints are worth. If
`fabrication_risk` turns out to be uncorrelated with hiring outcomes, then
scaling it to Postgres, adding ANN to it, and tracing it are all investments in
something that does not work. The reverse is not true: nothing about calibration
requires Postgres, real embeddings, or metrics.

**The honest counter-argument** (a future session should weigh it): calibration
needs *data*, and the ledger currently holds only whatever test and smoke runs
put there. With no real pilot orgs submitting outcomes, S8.1 may produce a
harness with nothing to measure — in which case it is scaffolding built ahead of
demand, and the Postgres/observability work that makes a pilot *possible* should
come first. **Resolving this is the first question of PI-8's brainstorm**, and it
turns on a fact this audit cannot supply: whether a real pilot org exists or is
close.

### ⚠ RESOLVED 2026-08-01 — the counter-argument won; §5's order is SUPERSEDED

**Asked and answered by the user on 2026-08-01:** there is **no pilot org today
and none close**, and the goal for veritas is **"real companies, eventually — I
want it launchable."**

That settles it against the reorder proposed above. A calibration harness cannot
measure anything until orgs are live submitting outcomes, and getting orgs live
is precisely what "launchable" means. So:

- **PI-8 becomes LAUNCH READINESS**, not scale-and-learning. Its question is
  *"what stops a real company onboarding without the operator hand-holding the
  database?"* — see §9 for the measured blocker list.
- **The calibration harness moves to PI-9**, gated on PI-8 succeeding. It stays
  cheap (§3.3 is unchanged and still true) and it becomes valuable the moment
  real outcomes exist. Nothing is lost by waiting; a harness measuring test
  fixtures would have been actively misleading.

§5's sprint list above is kept as the dated record of the pre-answer reasoning.
**Do not plan from it** — plan from §9.

## 6. Non-negotiables — unchanged, and now tested three times over

v1 §7 stands verbatim. PI-7 stress-tested all five and none bent: advisory-only
(seven numbers, zero auto-rejects), consent-before-signal (three new purposes,
each argued), deterministic fallback (the whole no-key interview path), TDD +
offline + smoke-per-sprint (1175 tests, 26 smokes), erasure-cascades-everything
(S7.3 needed no new erasure path at all).

**One addition earned by PI-7**, which every future sprint should adopt:

> **Hunt the one-entry-point gate.** All three PI-7 branch reviews found the
> same defect class — a rule enforced at one entry point and not the other
> (S7.1's `start()`, S7.2's `claim_ref` and identity route, S7.3's audio path).
> Put gates on the *service*, not the route, and enumerate every writer of a
> table and every caller of a service method before believing a guarantee.
> A second, related shape: **a stored row later code cannot parse must degrade,
> never raise on a read path** — twice now that pattern would have permanently
> bricked a candidate's own DPDP access.

## 7. Knowledge gaps — status

| v1 §8 item | Status |
|---|---|
| DPDP Consent Manager maturity + DigiLocker terms | **Still open.** Untouched; govt-ID stays inert. |
| Speech models for Indian-accented English | **Partly closed.** Model chosen and live-verified (voxtral). **Quality on accented English still unverified** — no audio corpus exists. |
| EPFO/UAN legality | **CLOSED** (S7.2). Lawful via authorized BGV aggregators; the blocker is the vendor, not the law. |
| Third-party assessment webhook formats | **Still open.** No partner has appeared. |
| License-clean comp-band sources | **Still open.** S5.2 ships an illustrative seed table. |
| **NEW:** does a real pilot org exist? | **Open, and it now gates PI-8's ordering** (§5). |

## 8. Immediate next action

**Brainstorm PI-8's shape** from §9's blocker list (NOT from §5, which the
2026-08-01 answer superseded). Nothing in this document overrides the ROADMAP's
"Next action"; when they disagree, the ROADMAP wins.

## 9. PI-8 = LAUNCH READINESS — the measured blocker list

Every row verified against the tree at `cd5e5c9`, not assumed. The question each
answers: *what stops a real company onboarding without the operator hand-holding
the database?*

| # | Blocker | Evidence in the tree | Rough shape |
|---|---|---|---|
| 1 | **Migrations never run automatically** | `alembic upgrade head` appears in neither `Dockerfile` nor `app/main.py`; a fresh container boots against no schema | small — a boot step or entrypoint |
| 2 | **SQLite is single-process** | `candidates_db_url: sqlite:///./data/veritas.db`; concurrent uvicorn workers contend on write locks | the Postgres cutover |
| 3 | **Report store blocks Postgres** | `app/services/report_store.py` — 212 lines of raw `sqlite3`, self-creating schema, outside Alembic, and it holds the human `outcomes` | rewrite behind the existing `ReportStore` Protocol (§3.1) |
| 4 | **Candidates cannot self-register** | `POST /candidates/{id}/auth-key` is admin-plane only; every candidate key is minted by hand | real registration: signup, session, recovery |
| 5 | **Orgs cannot self-onboard** | `POST /ledger/orgs` requires the shared `X-API-Key` | org signup + key self-service |
| 6 | **Retention declared, not enforced** | `RetentionPolicy.sweep_active=False` everywhere; deferred since S6.4 | the sweep job — now a real DPDP gap, not a nicety |
| 7 | **No rate limiting anywhere** | 63 endpoints, no limiter; the S7.3 review flagged unbounded ASR spend from a stolen candidate key | a limiter, paired with #8 |
| 8 | **No metrics, tracing or alerting** | `app/core/logging.py` is structlog only | you cannot operate for customers blind |

**The biggest open scope question, deliberately NOT decided here:** *is API-only
launchable?* The stance since M1 has been API-first, and PI-5's "thin employer
dashboard" (S5.3) shipped as **JSON read-models, not a UI**. Indian employers
will expect a screen. Whether PI-8 includes a real front end — and if so how
thin — is the largest call in the PI and deserves its own conversation at the
top of the brainstorm, because it could double the PI's size.
