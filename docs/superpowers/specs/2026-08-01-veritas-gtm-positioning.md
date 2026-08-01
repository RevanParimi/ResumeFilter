# Veritas — Go-to-Market Positioning (decision record)

**Date:** 2026-08-01
**Status:** Decisions taken with the user. Binding on PI-8 planning.
**Supersedes nothing.** Companion to
`2026-08-01-veritas-gap-analysis-v2.md` — that document says what is *missing
technically*; this one says **what we sell, to whom, and in what order**.
**Read order:** `docs/ROADMAP.md` → gap-analysis v2 → this.

**Scope note:** this is a commercial positioning document, not an engineering
spec. It constrains PI-8's priorities and adds four blockers the technical audit
could not see (§8). It does not change any non-negotiable in
`CLAUDE.md`.

---

## 1. The question this answers

Asked by the user, 2026-08-01, after PI-7 closed:

> *"This is the product we're happy with so far. How do we get into the world of
> business the easy way — not a Steve Jobs first launch, but a path to capital
> revenue? Where would most IT companies use it? Which approach: (1) build a UI
> and full-stack app, advertise on LinkedIn, bring investors; (2) sell to
> LinkedIn / Naukri / Indeed; (3) sell direct to companies, hosted, via API?"*

Two framing corrections were made before answering, and both are load-bearing:

1. **The three options are not alternatives.** Options 2 and 3 both require a
   screen a non-engineer can evaluate. No corp-dev team and no delivery head
   assesses a repo or a Postman collection. "Build a UI" is therefore the shared
   cost of entry, not a competing strategy.
2. **The binding question is not *which channel* but *what single thing do we
   sell*.** Veritas is currently eight subsystems presented as one platform.
   Nobody buys "talent intelligence platform." They buy one painful thing.

## 2. Commercial inventory — what we are actually holding

Measured from the tree at `d9ce195` (numbers from gap-analysis v2 §1).

| Asset | Commercial read |
|---|---|
| Fabrication defense (PI-2) + document forensics (S7.2) | **The differentiated asset.** Works from one customer's own data. No incumbent occupies this funnel position. |
| DPDP consent model (PI-3, S3.1) | **Underrated.** Query-time enforcement + audit-of-every-touch is an RFP slide competitors cannot make. See §8.1. |
| Evaluation ledger / cross-company reputation (PI-3) | **Worst cold-start in the repo.** Worth zero to customer #1. See §4.2. |
| Candidate backbone + India normalization (PI-1, S1.4) | Table stakes. Commodity — Daxtra, RChilli, Affinda parse Indian resumes today. |
| Feature store + ranking (PI-4) | Internal machinery. Not a sellable unit; enables PI-9. |
| Matching / comp / dashboard (PI-5) | Me-too against every ATS. Expansion surface, not a wedge. |
| Identity verification ladder (S7.1) | Real, but govt-ID is inert; the ladder tops out at contact-control + operator review without a vendor. |
| AI interviews (S7.3) | Crowded category. Differentiated only by the probe idea (asks the depth report's *own* unsettled claims) — which is a genuinely good story, but a feature, not a wedge. |

**What we do not hold:** any real user, any real outcome, any validated number,
any UI, any deployment.

## 3. The two structural problems that govern every option

### 3.1 "Does it work?" currently has no answer

Gap-analysis v2 §2 is the central commercial fact, not merely a technical one:
**seven advisory numbers, none ever checked against a hiring outcome.** Every
serious buyer asks this in the second meeting. Today the honest answer is "the
architecture is conservative and advisory" — which is a process answer to an
efficacy question, and every experienced buyer hears the difference.

This gap blocks enterprise deals *and* investor conversations *and* any platform
sale. It is the highest-value thing to close, and §6 sequences GTM specifically
so that closing it is a side effect of the first customers rather than a project.

### 3.2 The most impressive subsystem has the worst cold-start

The cross-company evaluation ledger is the thing that makes veritas
Mercor-shaped, and it is worth **exactly nothing to the first customer**. It
needs N participating companies before it is worth anything to any of them.
Leading with it produces a demo that ends in "so what does it show me today?" —
answer: nothing.

This is a sequencing constraint, not a design flaw. The ledger is correct and
stays. It comes off the *pitch*.

## 4. DECISION 1 — the wedge

**We sell pre-screen fraud detection for Indian IT hiring.** Not the platform.

The sellable unit, drawn from existing subsystems:

| Capability | Ships from |
|---|---|
| AI-generated resume detection | S2.1 (`app/fabrication`, stylometry ⊕ capped LLM) |
| Timeline / cross-field contradiction forensics | S2.2 (deterministic, no LLM) |
| Resume-farm near-duplicate detection across the customer's own funnel | S2.3 (MinHash, `resume_fingerprints`) |
| Unified advisory `fabrication_risk` | S2.4 |
| Fake experience-letter / payslip forensics | S7.2 (`app/verification`, deterministic) |
| Dual-employment / moonlighting advisory | S7.2 (`moonlighting.py`) |
| Proxy-interview risk | S7.3 (`app/interview/proxy.py`) |

**Rationale — five reasons this slice and not another:**

1. **No cold start.** Produces value from one customer's own resumes on day one.
   Unlike the ledger (needs N orgs) or calibration (needs outcomes).
2. **Unoccupied funnel position.** Indian BGV incumbents — AuthBridge, IDfy,
   SpringVerify, OnGrid, First Advantage — verify *after* selection: slow,
   per-candidate, expensive, post-offer. Veritas screens *before*, cheaply, at
   the top of funnel, across everyone. That is a different product, not a
   cheaper version of theirs.
3. **The pain is board-level and named.** Dual employment became a CHRO agenda
   item after the 2022 moonlighting firings in Indian IT services. Fabricated
   experience letters sourced through "consultancies" are an open secret in
   Indian IT staffing.
4. **It is validatable retrospectively, in weeks.** "Here are the 40 we flagged
   out of your 500 — which had you already rejected?" That checks accuracy
   against data the customer *already has*, with no hiring cycle to wait out.
   This is the cheapest known path to closing §3.1.
5. **It demos on old resumes**, which is the user's stated constraint. Adversarial
   fixtures already exist in `tests/fixtures/`:
   `ai_generated_genai_resume.txt`, `fabricated_genai_resume.txt`,
   `inconsistent_genai_resume.txt`, `farm_genai_resume_a/b.txt`,
   `genuine_genai_resume.txt`.

**What this decision does NOT mean:** nothing is deleted, and PI-8 still hardens
the whole platform (§7). The narrowing is to the *pitch*, the demo, and the
first sales conversation. Everything else is the expansion story.

## 5. DECISION 2 — who we sell to, in order

**Not** TCS / Infosys / Wipro / HCL / Cognizant first. Those are 12–18 month
cycles gated on vendor empanelment, InfoSec questionnaires, MSA and procurement.
A solo vendor with no SOC 2 is filtered in week one, and a year is spent learning
nothing.

| # | Segment | Why first | What we get back |
|---|---|---|---|
| 1 | **Recruitment / staffing agencies, 50–500 people** | Feel fraud most acutely — a fake placement costs the fee, the client relationship, and often a replacement guarantee. One decision maker (founder / delivery head). Weeks-long cycle. High resume volume. | Real resumes **and** outcome labels (placed / rejected / dropped / client-flagged) — exactly PI-9's calibration input |
| 2 | **Mid-size IT services, 200–2 000 employees** | Real volume, real exposure, no in-house DS team to build it, a reachable budget holder | Volume, and the first referenceable logo |
| 3 | **BGV vendors as a channel, not a competitor** | They already hold the enterprise relationships and empanelment we lack. A white-labelled pre-screen layer feeding their existing pipeline is a far shorter path to enterprise logos than selling direct. | Enterprise distribution — **and the resolution to the EPFO/UAN blocker**, which S7.2 established is a vendor problem, not a legal one |

**Channel note (3) is strategically important**: the same partner that unblocks
enterprise distribution also unblocks the one verification method the ladder
cannot reach on its own. Those are the same conversation.

## 6. DECISION 3 — the sequence

```
Phase 0 — PI-8.  Launchable + demoable.
         Whole-platform hardening (§7) + a UI over the wedge path:
         batch resume upload -> ranked fraud-risk list with reasons ->
         drill into one candidate.  Deployed, Postgres, org self-signup.

Phase 1 — Design partners, NOT customers.
         3-5 firms from segment 1.  Free or near-free.  Price is
         (a) real resumes, (b) retrospective outcome labels.
         This is the ONLY thing that retires §3.1, and it is the
         precondition for every other option.
         Distribution: warm intros. The user's IBM network reaches
         segment 1 and 2 directly; cold outbound does not work here.

Phase 2 — Charge.  Direct (segments 1-2) + channel (segment 3).
         Entity: sole proprietorship + GST is sufficient to invoice
         B2B in India (§8.4).  Not a company in the venture sense.

Phase 3 — Only now: platform sale / investors become real
         conversations, because the walk-in is accuracy numbers and
         logos rather than a repository.

Phase 4 — PI-9 calibration harness fires on real data.
         Gap-analysis v2 §3.3 is unchanged and still true.
```

**Illustrative unit economics** — these are shape-checks by the author, *not*
market research, and must be re-derived before any pricing conversation:
at ₹20–50 per resume screened, a staffing firm processing 5 000 resumes/month is
₹1–2.5 L/month. Ten such customers is order-of ₹15 L/month. That is a
side-project-scale business reachable without funding, headcount, or leaving
employment — which matches the user's stated goal ("capital revenue, without
starting a company").

## 7. What this means for PI-8

**User's decision, 2026-08-01: PI-8 hardens the WHOLE platform**, all 63
endpoints and all three auth planes — not only the wedge path. This was chosen
over the recommended wedge-only cut with the trade-off stated.

**Why it is coherent with a narrow pitch:** the pitch narrows, the platform does
not. When a design partner asks "can you also verify employment / run the
interview / share signals across our group companies," the answer is a working
endpoint rather than a roadmap promise. For segment 1 and 2 buyers, expansion
questions arrive in the *first* meeting, not the fifth.

**The cost being accepted, stated plainly:** PI-8 is roughly double the
wedge-only scope; candidate self-registration (gap-analysis v2 §9 blocker 4) is
in scope though the wedge alone would not need it; and nothing is demoable until
late in the PI. The mitigation is to sequence the UI + wedge path early enough
within PI-8 that a demo exists before the PI closes.

**Priority ordering inside PI-8, derived from this document** (the sprint
breakdown itself belongs to PI-8's own brainstorm, not here):

1. Anything on the wedge demo path — it is what Phase 1 needs.
2. Blockers 1, 2, 3, 5, 7 (migrations-on-boot, Postgres, report-store rewrite,
   org self-onboard, rate limiting) — these make hosting a customer possible.
3. Blocker 6 (retention sweep) + the two DPDP statutory rights in §8.1 — these
   are RFP blockers, not polish.
4. Blocker 4 (candidate self-registration) and blocker 8 (observability).

## 8. Commercial blockers the technical audit could not see

These are **new**, and none appear in gap-analysis v2 §9.

### 8.1 DPDP is a differentiator, which reclassifies two deferred items

The consent architecture is not only a compliance cost — it is a competitive
asset in an Indian enterprise RFP, where DPDP readiness is currently a live
procurement question. "Consent is a first-class schema object, enforced at query
time, with every access audited, allowed or denied" is a claim most competitors
cannot make.

That cuts both ways. The two statutory rights deferred from S6.4 stop being
polish and become **RFP blockers**:

- **Correction / rectification** — a data principal can demand their data be fixed.
- **Grievance officer / DPO contact** — a reachable grievance mechanism.

Both are cheap now and expensive to retrofit under a customer's procurement
deadline. **Recommendation: PI-8 owns them**, for commercial reasons rather than
legal fear.

### 8.2 False-positive liability must live in the contract

The advisory-only, no-auto-reject, conservative-calibration posture is correct
and is a commercial asset — but today it exists only in code and docs. Flagging
a real candidate as fabrication-risk who then loses an offer is a defamation and
discrimination exposure in India.

**Required before the first paying customer:** terms of service that state
explicitly that output is advisory, that human review is mandatory, and that the
customer is the decision maker. The code already refuses to auto-reject; the
contract must say so too.

### 8.3 Employment IP conflict — RAISED, DECLINED BY THE USER 2026-08-01

The user is employed at IBM. IBM's IP-assignment and outside-activity clauses
are broad, and IBM has both an HR consulting practice and AI products, so a
talent-intelligence tool is plausibly "related to the employer's business."
The recommendation was to read the agreement and, if required, file for
outside-activity approval **before there is revenue**.

**The user declined, 2026-08-01**, on the grounds that IBM has lakhs of
employees, does not trace small side projects, and its people are occupied with
day-to-day work. **That is their call and it stands. Do not re-raise it**
unprompted.

**Residual risk, recorded once so the record is honest and not re-argued:** the
objection answers *"will IBM come looking?"*, which was not the failure mode.
IP-assignment operates at the moment of creation and surfaces when a
**counterparty** asks — investor legal diligence, acquirer IP review, or an
enterprise vendor questionnaire's "do you own this IP" line. **§6 Phase 3 is
explicitly platform sale and investors**, so the trigger sits on this document's
own plan, at the point of maximum leverage to lose. Detection by IBM is not
required for the risk to materialise.

**Practical consequence if it is never cleared:** Phases 0–2 (build, design
partners, direct invoicing) are largely unaffected in practice. Phase 3 is where
it bites. A future session reaching Phase 3 should surface this section then —
**that is a trigger, not a reminder to nag.**

### 8.4 Entity and invoicing

To invoice an Indian business B2B, a sole proprietorship + GST registration is
realistically the minimum. This is cheap and fast and is **not** "starting a
company" in the sense the user declined. It should not be a deterrent to Phase 2.

## 9. Rejected options — with reasoning

Recorded so a future session can disagree on the merits rather than re-derive.

### 9.1 REJECTED as a first move — sell to LinkedIn / Naukri / Indeed (user's option 2)

- **LinkedIn:** builds in-house, US-centric, India-specific hiring fraud is not
  on its roadmap.
- **Indeed:** has been reducing India-specific investment.
- **Naukri (Info Edge):** the only realistic one — Indian, feels resume fraud on
  its own platform, and genuinely acquisitive in this space (iimjobs/Hirist,
  DoSelect for assessments, Zwayam for recruitment automation).
- **Why it still fails today:** platforms buy traction, revenue and teams — not
  code. Pre-traction, we have no leverage; the realistic outcome is that the
  idea is absorbed and built in-house, because none of this is patentable and
  the hard part for them (distribution) is the part they already have.

**Verdict:** this is an *exit*, available after Phase 2 works. Not an entry.
Revisit at Phase 3.

### 9.2 REJECTED as stated — full-stack + LinkedIn advertising + investors (user's option 1)

- **The UI half is right** and is absorbed into Phase 0.
- **The GTM half is wrong.** Enterprise HR tech in India sells through
  relationships, referrals and channel partners — not LinkedIn advertising.
- **The investor half is premature.** No investor funds pre-revenue, pre-data HR
  tech from a solo side project in one of the most crowded categories in tech.
  Phase 3, with accuracy numbers and logos, is a different conversation.

### 9.3 ACCEPTED with correction — direct to companies (user's option 3)

Correct as the revenue path. Two corrections applied:

- **"IT companies" was too broad** — retargeted to staffing agencies first
  (§5), because they feel the pain most, decide fastest, and hold the outcome
  data.
- **"API" is the wrong framing.** Companies do not buy APIs; an HR team buys an
  outcome and engineering consumes the API afterwards. The API is a delivery
  mechanism, not the product.

### 9.4 REJECTED — lead with the evaluation ledger

The most architecturally impressive subsystem, and commercially the worst
opening move (§3.2). Stays built; comes off the pitch until multiple customers
exist. It becomes the retention and expansion story once segment 1 has depth.

## 10. Kill criteria — stated in advance

Recorded now, while it is cheap to be honest, so a future session is not
rationalising sunk cost:

- **If 5 design-partner conversations produce no one willing to hand over
  resumes for free**, the pain is not what this document assumes, and the wedge
  is wrong — not the sales approach.
- **If retrospective accuracy on real resumes is at or near chance**, §3.1 has
  been answered badly and the fabrication stack needs work before any GTM
  continues. This is the outcome PI-9 exists to measure, and the wedge is
  deliberately chosen so this answer arrives early and cheaply.
- **If false-positive rate is high enough that customers stop trusting the
  flags**, the conservative-by-construction posture (FABRICATION.md principle 2)
  has failed at its own stated goal, and that is a product problem, not a
  positioning one.

## 11. Open questions — not decided here

- **Pricing model** — per resume screened vs. per seat vs. flat monthly. Needs
  one real customer conversation; deciding it now would be fiction.
- **Hosting posture** — single shared instance vs. per-customer deployment.
  Interacts with multi-tenancy, which gap-analysis v2 §1 lists as deliberately
  deferred (YAGNI). Segment 1 may accept shared; segment 2 may not.
- **Deploy target** — Railway tooling is available in the working environment,
  which suggests a candidate. Confirm in PI-8's brainstorm; it collapses
  blockers 1–3 into concrete work.
- **Whether the demo UI is throwaway or the real front end** — a PI-8 scope
  question with a large cost delta.
