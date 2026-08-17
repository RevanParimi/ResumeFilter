# Veritas UI — build plan (multi-session)

Source of truth: `depth-eval-resume-engine/UI.md` (83 routes, tagged ✅/🔜/🚫).
Design systems attached: Modernist, Broadsheet, Organic (in `_ds/`).

## Decisions taken
- Scope: everything incl. admin console. Buyer-first, recruiter-usable.
- Tenancy: **"my queue"** — an org sees only batches it uploaded. Resume-farm
  matches show *that* a near-duplicate exists + similarity, never whose.
- Batch is a **real object** (name, status, counts) + a flat all-candidates view.
- Org sees the **full** Report: fabrication_risk headline, 3 subsystems as
  inputs, claim-level verdicts, evidence, probes.
- Advisory framing: persistent banner **and** per-score confidence treatment.
- Clickable prototype + configurable API base URL (Settings → API).
- Mock data: Indian IT staffing, GenAI + Data Engineering domains.

## Visual direction — SETTLED
Broadsheet was rejected ("reads like a PDF"). Current direction: dark cinematic
SaaS — deep teal→indigo brand panel, CSS-3D wireframe globe, cyan→violet gradient
accents, Space Grotesk / Manrope / JetBrains Mono, LinkedIn-tight density
(13px body, 8-10px radii, 30px avatars).
Full light + dark theming via CSS custom properties on the root wrapper
(DARK / LIGHT token maps in the logic class) — every surface reads var(--*).
Previous version kept at `docs/ui/Veritas v1 (Broadsheet).dc.html`. It moved out
of `frontend/` in the S8.6 review: that directory is served to the public
internet at `/ui`, so a rejected design was downloadable by anyone. The mount
now refuses anything outside `app.main.UI_ASSETS`, but a design archive has no
business in a runtime asset directory either way.

## Phase 1 — shell + wedge  ✅ DONE
1. App shell: nav, org switcher, advisory banner, session/API state.
2. Login / OTP verify — org, candidate, admin planes. 202 anti-enumeration copy,
   single `invalid_code` message, 503 `email_unavailable`, 403 CSRF state.
3. Batch upload + async ingest progress (partial results, not a blocking spinner).
4. Screening queue — ranked risk list, band · score · confidence · reason · loudest signal.
5. Candidate risk detail — the Report (headline + components + verdicts + probes + evidence).
6. Batch summary roll-up (screenshot-able).

## Phase 2 — compliance + org plane
7. ✅ Candidate DPDP portal: overview, access log, consents, erasure.
8. ✅ Signed-in devices / sessions.
9. ✅ Roles & requisitions + role-conditioned shortlist.
10. ✅ Comp intelligence (prior/observed blend, k-anonymity floor).

## Phase 3 — operator + states
11. ✅ Operator console (organisations, operator accounts, curation queue).
12. ✅ insufficient-signal empty state · ✅ 403 "not shared with you" (Roles).
    Remaining: a 403 pass on the candidate card's per-section statuses.
13. API wiring: base-URL setting, `credentials: "include"`, `X-CSRF-Token`,
    401 → login, 403 → CSRF vs consent distinction.

## Never build (UI.md §8)
Evaluation ledger screens · auto-reject/shortlist/hide · candidate-facing risk
score · payments/payroll/sourcing · passwords/SSO · any accuracy badge.
