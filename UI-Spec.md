# Veritas UI — what is built, screen by screen

Single Design Component: `Veritas.dc.html`. Nothing is wired to the API yet —
every screen renders mock data shaped like the real response objects. Light and
dark themes throughout (CSS custom properties, one toggle in the top bar).

Legend for the endpoint column:
`✅` exists today · `🔜` UI.md says S8.4 · `—` no endpoint, UI-only state.

---

## 0. Shell

| Element | Behaviour |
|---|---|
| Left rail (212px) | Plane-aware. Org, Candidate and Operator each get a different nav set. Grouped headings, 15px masked Lucide glyphs, active item filled. |
| Rail footer | Org: live ingest meter (168/214). Candidate: rights summary. All: identity block + Sign out. Per-plane name/initial — a candidate never sees the agency's name or batch data. |
| Top bar | Screen title · search (org: candidates, operator: organisations, candidate: hidden) · theme toggle. Sticky. |
| Advisory strip | Renders **only** on risk surfaces: queue, report, summary, batches, roles. Deliberately absent from device lists, consents, erasure, curation. |
| Theme | Full DARK/LIGHT token maps. Band colours retuned per theme so they pass contrast on both grounds. |

---

## 1. Auth — 3 planes

**Screens:** Sign in → Enter code.

- Split layout: brand panel (animated CSS-3D wireframe globe, gradient ground,
  three proof stats) + form panel.
- Plane switcher is an underline tab row — Organisation / Candidate / Operator —
  each with a one-line description of what that plane can do.
- **Sign in / Create account** toggle on Organisation and Candidate only. Org
  signup additionally asks for organisation name (`{email, organization_name}`);
  candidate signup is `{email}` alone. Operator is login-only and says so —
  accounts are minted from the console via `POST /admin/users`.
- Email only. Copy states outright: no passwords, no SSO, no social login.
- Anti-enumeration copy: "If that address is registered, a code is on its way."
- Six-box OTP. Copy notes expired / wrong / too-many-attempts return one message.
- Verify routes by plane: org → queue, candidate → portal, operator → orgs.

| Maps to | |
|---|---|
| `POST /auth/{org,candidate,admin}/signup` · `/login` · `/verify` | ✅ |
| `GET /auth/me` on load | ✅ — **not yet called** |

**Not yet designed:** the `503 email_unavailable` state, the 403-CSRF state,
and the session-died-mid-session redirect.

---

## 2. Screening queue — the wedge

Batch header (name, upload time, one-line framing) + four band counters
(elevated / moderate / low / insufficient) + a bordered row list.

Each row: avatar, name, risk-band chip, role · city · domain, one-line reason,
loudest signal, numeric score, risk bar, confidence bar. Whole row is a button
(keyboard accessible, Enter/Space).

Six candidates cover every band including `insufficient_data`.

| Maps to | |
|---|---|
| fraud-screen read-model over a batch | 🔜 — S8.4 Phase B, `GET /screening/batches/{id}/queue` |
| cursor pagination | 🔜 — **no pagination UI yet**; S8.4 Phase B, one opaque cursor over `(created_at, id)` |

**Settled 2026-08-05 (UI.md §9):** the queue is scoped to **batches this
organisation uploaded**, so an org that has uploaded nothing gets an **empty
queue, not an error** — the resting state of every newly self-registered
customer, and the first screen they will ever see. The row's ingest-time signals
(`matched_existing`, `duplicate_resume`, `resume_farm`) come back into the
read-model here; UI-Spec item 9 recorded them being thrown away.

---

## 3. Candidate risk detail

- **Headline:** conic-gradient risk gauge (score arc), band chip, confidence bar
  captioned "read the score against it", depth band.
- **What drove it:** the three subsystems — resume farm, AI generation,
  cross-field — each with band, score, confidence and reasoning. Framed
  explicitly as *inputs to a fusion*, never four equal peers.
- **Claim by claim:** per verdict — status chip, claim type + coherence, the
  claim quoted, reasoning, **missing signals** (own tinted block), evidence
  split into `source · detail` rows, and probes in a highlighted card with a
  working copy-to-clipboard button.
- **Empty state:** zero-verdict candidates get "Nothing to reason about yet"
  with a per-candidate reason and a request-a-fuller-resume action. The outcome
  buttons are hidden in that case.
- **Outcome:** verified genuine / candidate clarified / verified fabricated /
  inconclusive.

| Maps to | |
|---|---|
| `GET /report/{id}` | ✅ (admin plane today) — S8.4 Phase A adds the org-plane equivalent, scoped to reports this org owns; another org's report is **404**, not 403 |
| `POST /report/{id}/outcome` | ✅ |

Resume-farm matches show similarity only — never whose resume matched.
**Settled 2026-08-05 (UI.md §9 Q4):** this is now permanent rather than pending
the tenancy call, and it is the *only* redaction — the org sees the full report,
`verdicts[]` / `missing_signals` / `probes[]` included. Server-side the redaction
is a single shared projection used by both this screen's endpoint and the batch
queue read-model, so it cannot hold on one path and lapse on the other.

---

## 4. Batch summary · 5. Upload · 6. Batches

- **Summary:** four big band counts with percentages, "top reasons a resume
  surfaced" bar list, no-accuracy-claim footnote. Numbers reconcile with the
  queue (168 screened, 46 pending).
- **Upload:** drop zone, batch name, domain segmented control (Data Engineering
  / GenAI — the two registered domains), live ingest progress with a link to
  partial results.
- **Batches:** per-org list with progress and elevated counts. Copy states the
  tenancy assumption: you see only what your organisation uploaded.
  **Confirmed 2026-08-05 — this is no longer an assumption but a decision**
  (UI.md §2.1); the copy stands as written.

| Maps to | |
|---|---|
| batch upload (500 files) | 🔜 — today `POST /candidates` is one at a time, admin-only. S8.4 Phase B adds an org-plane batch upload that **registers** items without evaluating them |
| batch as a stored object | 🔜 — nothing in the schema has it. S8.4 Phase B adds `screening_batches` + `batch_items` |
| live ingest progress | 🔜 — **poll `GET /screening/batches/{id}`; the client also drives the work** via a bounded `POST .../process`. There is no worker in `app/`, so "live progress" is the UI's loop, not a server push. Design for partial results — which this screen already does |
| `GET /domains` | ⚠️ **admin router — an org session gets 401.** The two domains (`data_eng`, `genai`) are correctly hard-coded in the UI today. |

---

## 7. Candidate DPDP portal (candidate plane)

| Screen | Contents |
|---|---|
| Overview | Counters (resume versions, report refs, active consents, access events) · profile with hashed contact fields · report **references only** · identity-assurance ladder incl. government-ID as declared-but-unimplemented · retention policy (3y resumes / 7y audit log) noted as *surfaced, not swept* |
| Who accessed it | Timestamp · org · purpose · allowed/refused. 5 most recent of 17. |
| Consents | Org · purpose · expiry · revoke. One revoked entry shown in its resting state. |
| Delete everything | Cascade spelled out, type-to-confirm, danger action. |

| Maps to | |
|---|---|
| `GET /portal/me` · `/access-log` · `/consents` · `POST /consents/{id}/revoke` · `DELETE /portal/me` | ✅ |

No candidate-facing risk score anywhere, per UI.md §4.D.

---

## 8. Signed-in devices (all planes)

User agent · session id · last seen · status · revoke. Current session cannot
revoke itself. Copy states the 12h / 2h-idle expiry.

`GET /auth/sessions` · `POST /auth/sessions/{id}/revoke` ✅

---

## 8b. Instant check (org plane) — `POST /evaluate` ✅ **BUILT**

Paste one resume → full `Report`, nothing persisted.

- Resume textarea + "attach a PDF instead" (noted as base64, parsed in memory).
- Domain picker (data_eng / genai).
- **GitHub URL and Portfolio URL fields** — `/evaluate` accepts these and
  `POST /candidates` does not; copy notes first-party links only, no scraping.
- Run walks the real nine graph nodes (ingest → ai_signals → cross_field →
  claim_extraction → provenance → plausibility → probe_generation → scoring →
  report), each with a state dot, the reasoning pass flagged as the slow one.
- Result is framed as **not saved** — leaving the page discards it; to keep a
  report, upload as a candidate instead.
- States honestly that **no resume-farm signal is available** on an ad-hoc run,
  because nothing was fingerprinted against the stored corpus.

## 8c. Interview runner (candidate plane) — `/portal/interviews*` ✅ **BUILT**

Five probes drawn from the candidate's own claims. Turn pips, per-turn scoring.

| Contract detail | How it surfaces |
|---|---|
| Channel `audio \| text` | Voice / type toggle; both scored identically |
| `SubmitAnswerRequest{question_id, text, audio_b64, mime}` | Recorder produces base64 + mime — no multipart upload UI |
| `422 speech_unavailable` | Calm inline notice, **not an error**: audio refused, interview continues in text, score unaffected. Driven by the `speechEnabled` prop |
| `SpeechFailed` must not cost a turn | Turn 3 on audio demonstrates it — question stays open, copy says the failure was ours and the retry is free |
| TTS deliberately absent | Question card states nothing is read aloud; no playback control exists |
| Audio transcribed then discarded | Footer states it, plus "the transcript is yours" |
| Org sees `InterviewSummary` only | Footer states an org receives a summary, never the transcript or turns |

**Still missing:** `transcript_truncated` inside `TurnScore.codes` has no
display, there is no post-interview transcript/review screen, and the org-side
`/interview/candidates/{id}/assessments` view does not exist.

## 9. Roles + 10. Comp (org plane)

- **Roles:** requisitions (title, location, domain, matched count, comp band,
  status in a *neutral* chip) then a role-conditioned shortlist showing match
  score and skill coverage **beside** the risk band, never fused. Includes a
  designed **403 "not shared with you"** block — closed section, rest of page
  loads, request-access affordance, notes the attempt is audited.
- **Comp:** blended band on a single scale — p25 / p50 / p75 with the median
  marker positioned from the same scale. Static prior vs observed offers vs
  blend weight, k-anonymity floor of 5 and prior strength k₀=8 stated.

| Maps to | |
|---|---|
| `GET/POST/PATCH /jobs` · `POST /jobs/{id}/match` · `GET /jobs/{id}/board` | ✅ |
| `GET /jobs/{id}/comp` · `POST /comp/estimate` | ✅ |

---

## 11. Operator console

Organisations (name, id, batches, joined, status) · Operator accounts (with the
warning that this plane can mint any candidate's access key, and that there is
no self-signup) · Curation queue (unmapped skill terms with counts and
map/reject actions).

`POST|GET|DELETE /admin/users` · `POST /ledger/orgs` · `GET /curation/skills/unmapped` ✅

---

# Backend surfaces with NO UI yet

This is the list to check against.

### Substantial — would each need real design work

1. ~~**AI interviews (S7.3)**~~ — **candidate-side runner BUILT**, see §8c.
   Remaining: transcript/review screen, `transcript_truncated` code display,
   and the org-side assessments view. Original notes kept below for reference.

   `/portal/interviews*` ✅. Audio-first, asks the
   depth report's own probes, transcribes and discards audio, deterministic
   scoring with an optional LLM nudge, proxy-risk from identity assurance held
   at session start. **Needs a genuinely different UI.** Confirmed contract
   details that shape it:
   - Channel is `audio | text`. Audio is submitted as
     `SubmitAnswerRequest{question_id, text, audio_b64, mime}` — **base64 + mime,
     not multipart**.
   - `422 speech_unavailable` is a **designed state, not an error**: with no key,
     audio is refused and the interview continues as text. Needs its own UI state.
   - `SpeechFailed` **must not cost a turn** — a retry has to be free so a vendor
     outage never costs a candidate their answer. That is a *distinct* retry
     affordance from the above.
   - **TTS is deliberately absent** — questions are text. Do not design audio
     playback.
   - Truncation surfaces as the code `transcript_truncated` inside
     `TurnScore.codes`, not as a top-level field.
   - The org sees `InterviewSummary` only — no transcript, no turns.
   Plus `/interview/candidates/{id}/assessments` (org side, consent-gated).
2. **Verification & identity assurance** — `POST /portal/verifications`,
   `/{id}/confirm`, contact-control OTP, document upload
   (`POST /portal/documents`, parsed in memory, never stored), operator manual
   review. Only the *outcome ladder* is shown today; none of the flows exist.
3. **Employment-claim forensics (S7.2)** — experience letters and payslips have
   their own claim ladder separate from identity assurance. Not surfaced at all.
4. **Profile sources** — GitHub and LinkedIn-export ingestion
   (`POST /candidates/{id}/sources/*`, `GET .../sources`). Advisory skill
   signals; nothing in the UI.
5. **Talent search / feature store** — `POST /talent/search`, ranked over
   materialised feature vectors. Admin-only today.
6. **Dashboard overview** — `GET /dashboard/overview` (requisition counts by
   status). The org plane has no home/dashboard screen at all.
7. **Candidate card** — `GET /candidates/{id}/card`. **Correction:** this is
   *not* substantial design work. Its three sections — reputation, coding_rounds,
   records — are all evaluation-ledger data, which is deliberately off the pitch.
   It carries no assurance, no claim evidence, no interviews, and is not the
   org's view of the fraud report. What to take from it is the
   **200-with-per-section-status pattern**, not the screen.

8. ~~`POST /evaluate`~~ — **BUILT**, see §8b.

9. **Ingest-response fraud signals thrown away.** `CandidateCreateResponse`
   already returns `matched_existing`, `matched_on`, `duplicate_resume`,
   `extraction_method` and `resume_farm` — the near-duplicate check runs at
   ingest so bulk works. The Upload screen designs a progress bar only. "This
   exact resume was uploaded before" and "this person is already on file,
   matched on email" are wedge facts available *before* any report opens.

10. **Org-side verification reads** — `GET /verification/candidates/{id}/assurance`
    and `.../claims`, both org-plane and consent-gated behind
    `verification_read`. These are the two org-facing surfaces of S7.2; item 2
    above covers only the candidate-side flows.

11. **Moonlighting / concurrent employment** — `ClaimEvidence.concurrent_employment`
    → `ConcurrentEmployment{periods, max_overlap_months, severity, advisory}`,
    threshold `moonlight_min_overlap_months = 12`. GTM names moonlighting as a
    wedge component and it appears nowhere in the UI.

12. **`POST /ledger/offers`** — the Comp screen renders observed-offer figures,
    but nothing submits an offer, so `n_observed` stays 0 and the blend is
    prior-only in practice. The display is designed; the input isn't.

13. **`POST /ledger/orgs/{id}/api-key`** — X-Org-Key is permanent and *is* the
    API product. No screen anywhere lets a customer obtain or rotate it.

14. **Operator consent administration** — `GET/POST /ledger/candidates/{id}/consent`,
    `POST /ledger/consent/{id}/revoke`. The candidate side is designed; the
    operator-side grievance/DPO path — an RFP blocker per GTM — is not.

15. **Operator candidate surfaces** — `GET /candidates/{id}` (CandidateDetail),
    `DELETE /candidates/{id}` (operator-initiated erasure, same
    `PortalService.erase()` path), `GET /candidates/{id}/reports` (report
    history per person). The console has orgs, operators and curation only.

16. **`POST /candidates/{id}/auth-key`** — the console warns that this plane can
    mint any candidate's key but designs no action for it.

17. **`DELETE /ledger/orgs/{id}`** (offboarding — a real ops need) and
    `POST /ledger/orgs/{id}/reliability` (ledger trust weighting — arguably
    off-pitch with the rest of the ledger).

### Smaller gaps

- Resume versions (`GET /candidates/{id}/resumes`) and per-resume erasure.
- `GET /report/{id}/outcomes` — recorded outcomes are written, never listed.
- Coding rounds (`/ledger/candidates/{id}/coding-rounds`) — consent-gated.
- Reputation — **deliberately excluded** (UI.md §8: ledger is off the pitch).
- `GET /healthz` / build + LLM-mode indicator for the operator console.
- Org signup flow (self-registration) — only login is designed.

### Deliberately NOT built (UI.md §8)

Evaluation-ledger screens · anything that auto-rejects, shortlists or hides ·
candidate-facing risk score · payments/payroll/contracts/sourcing · passwords,
SSO, social login · any accuracy badge.

---

# Known UI-side gaps

1. **No API wiring** — no base URL, no `credentials: "include"`, no
   `X-CSRF-Token`, no 401 redirect, no CSRF-403 vs consent-403 distinction.
2. **Search is decorative** — the top-bar field does not filter.
3. **Ingest progress is static** — UI.md wants partial results arriving over
   time, not a fixed 78%.
4. **No pagination** — a 500-resume queue needs the cursor UI that S8.4 adds.
5. **Error and loading states** are undesigned across the board.
