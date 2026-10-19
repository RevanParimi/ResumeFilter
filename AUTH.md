# AUTH.md — identity & access (S8.2)

Peer of `LEDGER.md`, `PORTAL.md`, `VERIFICATION.md`, `INTERVIEWS.md`.
Design record: [historical design in Git](https://github.com/RevanParimi/ResumeFilter/blob/54804988f3ead83d727754e4361266a4322655c4/docs/superpowers/specs/2026-08-02-s82-identity-access-design.md).

Before S8.2 every principal was a long-lived header key an operator minted by
hand. A browser could obtain none of them, and no human identity sat behind any
of them. S8.2 adds the second, human way in — **email-OTP login issuing an
opaque, revocable, server-side session in an httpOnly cookie** — on all three
planes, plus self-onboarding for orgs and candidates.

---

## 1. Two modes per plane, permanently

| Plane | Machine credential | Human credential | Principal |
|---|---|---|---|
| admin | `X-API-Key` (shared secret) | operator session | `admin_users` row, or *none* for the shared key |
| org | `X-Org-Key` | org-user session | `org_users` row → its organization |
| candidate | `X-Candidate-Key` | candidate session | `candidates` row |

**Browsers get cookies, machines get keys.** `X-Org-Key` is not legacy — the
long-lived key *is* the API product. Both modes are first-class and stay.

The difference is load-bearing for audit: a `Principal` established by the
shared admin key carries `admin_user_id = None`, so "an operator did it" and
"the shared secret did it" are distinguishable. That is the whole reason
operator accounts exist (S7.1's review caught one audit misattribution).

## 2. One resolver per plane — and the guard that keeps it that way

Sessions add a **second entry point to every plane**, and a rule applied at one
entry point and not the other has shipped as a real defect in S7.1, S7.2 and
S7.3. The structural answer:

```
require_api_key ─┐
require_org ─────┼──▶ AuthService.resolve(kind, session_token, header_key)
require_candidate┘         └── session cookie first, then the plane's header key

require_any_principal ──▶ AuthService.resolve_any(session_token)   # session ONLY
```

The three original dependencies keep their **names and return types**
(`org_id: str`, `candidate_id: str`), so all 63 endpoints gained session mode
with **zero handler edits** and every pre-existing authorization test passes
unmodified *through the new path*.

`tests/test_route_table_guard.py` walks the live FastAPI route table and asserts
every non-public route establishes its principal through one of those four. It
fails for a route that does not exist yet, which hand-written session twins
cannot do. **Widening `PUBLIC_PATHS` is the reviewable act.**

> **Adding a route?** Depend on one of the four resolvers. If your route is
> genuinely pre-authentication (a new login surface), add its path to
> `PUBLIC_PATHS` in `src/app/api/dependencies.py` — deliberately, in a diff someone reads.
> `tests/test_api_auth_gate.py` imports that same set, so the two never drift.

Authentication/session handlers and their wire models live in `src/app/api/auth.py`.
Product handlers share the resolvers in `api/dependencies.py`; existing imports
from `api/routes.py` retain the same resolver and allowlist identities.

## 3. Sessions

`auth_sessions` carries **three nullable FKs** — `candidate_id`, `org_user_id`,
`admin_user_id` — each `ON DELETE CASCADE`, plus a CHECK that exactly one is
non-null. Not a polymorphic `subject_type`+`subject_id`: a polymorphic id
**cannot carry a foreign key**, so erasure would stop cascading.

- The plaintext token is returned **once**; only its sha256 is stored.
- **Expiry is computed at read time**, absolute *and* idle — the S7.1
  `effective_status` precedent. No scheduler exists, so a stored `expired` would
  be a lie nothing corrects.
- `last_seen_at` is written at most once per `session_last_seen_write_seconds`
  (default 60). The naive version is a row lock and a WAL entry on every
  authenticated GET.
- `ip_hash`, never a raw IP.

## 4. Transport: cookie + CSRF

| Cookie | httpOnly | Why |
|---|---|---|
| `dee_session` | **yes** | XSS must not be able to read the session token |
| `dee_csrf` | **no** | the browser client has to read it to echo `X-CSRF-Token` |

`Secure` + `SameSite=Lax` in any deployed environment (S8.6). The UI is served
by this API at `/ui`, so requests are same-origin and `None` is no longer
required; `none` stays a permitted value for a separately-hosted UI. **`Secure`
is required either way** — the cookie crosses the public internet — so `false`
is for localhost only and **prod refuses to boot with it**.

**CSRF is kept even though Lax already blocks cross-site POST.** Lax is a
browser-side control, and the server must not make the client's correctness its
only defence. `tests/test_cookie_posture.py` pins that reasoning, because "Lax
makes CSRF redundant" is exactly the argument that would delete this layer.

**The CSRF exemption keys on `Principal.via`, never on "was a header present".**
Otherwise a browser carrying a session cookie plus an attacker-supplied
`X-Org-Key` skips CSRF entirely. `resolve()` prefers the session when both
arrive, so the stronger requirement wins. Enforcement lives *inside* the
resolvers (`_accept`), not as a sibling dependency — FastAPI runs router-level
dependencies before route-level ones, so a separate `Depends(require_csrf)` on
`org_router` would have run before the principal existed and skipped every
check.

## 5. Login: email OTP, no passwords

Pure mechanics are **reused** from `src/app/verification/otp.py`; the table is not.
`login_challenges` is scoped to **`email_hash` + `purpose` + `plane`** — a limit
scoped to a row the flow re-mints limits nothing (S7.1's own review finding),
and one address can legitimately be both a candidate and an org user.

Rows are **deleted on consume or supersession**: short-TTL secret material is
hygiene, not a retention policy.

### One live challenge per address, per plane

`_scope_purpose` files candidate-plane signup and login under **one** scope. A
second live challenge for the same address is not merely untidy — it was an
**unauthenticated login lockout**: `verify_code` checked signup first, so a
correct login code was evaluated against the wrong hash and refused until the
shadowing challenge expired, and anyone could trigger it against any candidate.
Found in whole-branch review, reproduced, and fixed twice over: the scope is
collapsed so the state cannot arise, and `verify_code` evaluates **every** live
challenge before refusing so it cannot arise on another plane either.

### No account enumeration

Signup and login always answer `202`, and every invalid-code failure answers one
`400 invalid_code` — distinguishing expired from wrong from exhausted tells a
brute-forcer which assumption was right. Cooldown refusals are also `202`.

**On the candidate plane, signup and login are the same act and both always
send.** A `candidates` row is *not* an account: most were created by an org
uploading a resume, about someone who has never touched this system. Treating
"a record exists" as "has an account" made the claim below unreachable in
exactly the case it exists for. Uniformity is also a stronger anti-enumeration
property than silence — same status, same body, same email, either way.

The org plane keeps the distinction, because an `org_users` row *is* an account.

## 6. The claim — the sprint's sharpest edge

After exact mailbox OTP redemption, candidate login first resolves the unique
`login_email_hash` proved previously. Resume `email_hash`/`phone_hash` values are
asserted hints and cannot move that binding or change a session's subject.
The first proof timestamp remains unchanged on subsequent logins.

An address with no binding may claim one uniquely matching, unbound candidate
hint, or create a bare candidate if no hint matches. Duplicated hints refuse
with `409 candidate_identity_ambiguous`; a hint pointing at an already bound
candidate refuses with `409 candidate_identity_conflict`. Neither refusal spends
the correct code, creates a session or replaces an existing cookie. Requests
still return the same `202`; invalid proofs still return `400 invalid_code`.
There is no automatic contact change, alias or profile merge operation.

This release explicitly refuses login changes, aliases and profile merges;
there is no apply endpoint or supported manual-SQL procedure. A new mailbox's
OTP alone cannot authorize moving an old subject, its history, keys or consents.
`candidate_id` supplied at login is ignored. A supported future change would
need proof of the existing principal and both relevant mailboxes, collision and
consent review, audit and session invalidation; those checks are not implemented.
Contact corrections may be submitted and reviewed through the existing rights
routes. `apply=true` refuses with 422, leaving the request open; an operator may
record the refusal with `apply=false`. That decision changes no identity fields
and never clears `login_binding_review_required`.

Uploads dedup only against one compatible asserted email hint. Duplicate hints
or a hint inconsistent with its proved mailbox create a separate submission.
An email upload never falls back to phone; phone-only matching excludes proved
and legacy-review subjects. Their top-level contact hints are frozen to uploads,
while extraction JSON retains the document's contact claims. These rules do not
verify document truth or authorship; unique-email dedup remains advisory. A match
whose contact/proof state changes before its write rolls back and returns
`422 candidate_contact_changed`; a fresh upload may resolve again. Duplicate
cardinality is a read snapshot, not a global lock across new submissions.

`scripts/inventory_candidate_contacts.py --database <explicit SQLite file>`
reports aggregate hints/proof/review counts read-only, with no repair mode or
configuration loading. Missing proof columns are reported as unknown. The actual
working-file inventory and preservation evidence are owned by
[R1-S2-T4B](docs/delivery/EVIDENCE-R1.md#r1-s2-t4b); it authorizes no cleanup or migration.

Migration `0029_candidate_login_binding` never infers historical ownership from
resume hints. It marks candidates with any existing candidate session (including
expired/revoked sessions) or session-create audit `login_binding_review_required`; the flag survives
session purge. New binding refuses `409 candidate_identity_review_required`
until explicit review. Existing sessions and candidate keys retain their subjects.
Historical sessions whose rows and audits were both purged cannot be recovered.
Downgrade removes the new proof/review metadata; it preserves older candidate,
session and key rows and must not be used as an ownership recovery procedure.
Only migrated disposable stores were exercised for this change.

Redemption locks and reloads the exact challenge, then rechecks its current
attempt budget and expiry in the consuming DELETE. Production samples time
after address/challenge lock waits; explicit injected clocks remain deterministic.
A stale preflight cannot redeem an exhausted or expired code. Refusal remains
the generic `400 invalid_code` and mints no session or mailbox binding.

Challenge consumption, binding, the session-create audit and session creation
share one transaction and the existing address lock. Erasure clears both proved
and asserted addresses, except an asserted hint at another candidate's proved
mailbox, whose challenges must survive. Proof fields are private to persistence;
the portal continues to return its existing candidate/assurance contracts.

Why: records built from org-uploaded resumes would otherwise be unreachable by
their own subject, which makes the portal's DPDP access, correction and erasure
rights theoretical for every candidate in the system — which is all of them. A
completed OTP proves control of the mailbox, which is exactly what S7.1's L2
`otp_email` assurance already means here.

**The risk, stated rather than buried:** whoever controls that mailbox gets the
candidate's data. Same trust boundary as every OTP login on the internet, but
the blast radius here is a full depth report.

**Signing up grants no identity assurance.** Logging in is not being verified;
fusing them would repeat S7.2's two-ladders mistake.

## 7. DPDP

- **No new `ConsentPurpose`** — authentication is not a disclosure.
- `MyData.sessions` lets a candidate see and revoke their own devices.
- Candidate session create/revoke are audited into the shared `audit_log`, so
  they appear in `GET /portal/access-log`. Org-user and operator events have no
  candidate subject and are structured-logged only (see §9).
- **Erasure**: both portal and admin routes call `PortalService.erase()`, which
  delegates to `CandidateStore.delete_candidate()`. Candidate sessions and other
  candidate-linked rows cascade. `login_challenges` and `login_issuances` have no
  FK (signup can precede a principal), so the candidate store explicitly deletes
  every plane/purpose for the stored email hash in the **same transaction**.
  Failed or interrupted erasure rolls back the cleanup; a retry can complete it.
  Other addresses and organization/admin principals and sessions survive.
  A send reserves an expiring token before provider I/O and activates a challenge
  only if that exact token survives. Short transaction locks order reservation,
  activation and erasure; no lock spans delivery. Cancelled sends return generic
  202 without debug echo. Provider failures preserve any previous valid code.
  Fresh signup remains permitted; already-sent mail cannot be recalled.
  Redemption uses the same address lock: exact code consumption, principal
  creation/resolution, session and candidate audit commit together. Erasure
  first refuses stale verification; redemption first allows erasure to cascade
  its candidate session. Failure before commit restores the challenge and leaves
  no partial signup/session. A cookie delivered after later erasure cannot
  resolve the erased candidate; response delivery itself is outside the lock.

## 8. Email seam

`src/app/services/email.py`, shaped like `llm.py`/`speech.py`:

- **`NullEmail` refuses** → `503 email_unavailable`. Nothing silently degrades.
- **`CaptureEmail` writes JSON lines** to `email_capture_path`, selected only by
  explicit config, **never by fallback**. Prod refuses to boot with it.
- `EmailClient.available` is probed **before any account lookup**, so a broken
  provider refuses identically for addresses that exist and ones that do not.
  Without that, "503 for a real user, 202 for a stranger" is an enumeration
  oracle that appears only when email is misconfigured.

This also gives S7.1's L2 contact-control rung its first real delivery path — it
had been tested but undeliverable since 2026-07-31.

## 9. Known gaps

- **NO RATE LIMITING.** The OTP surface is unthrottled beyond per-challenge
  attempt caps and cooldowns. This is S8.3's, and it is acceptable *only*
  because the deploy moved to the end of PI-8, so nothing is publicly reachable
  in the window. **If that sequencing changes, rate limiting must come forward
  with it.** Related: on the candidate plane any address can be mailed a code,
  which is a mail-bombing vector until the limiter lands.
- **Org-user and operator auth events are not in `audit_log`** — that table is
  candidate-scoped by design. Widening it is a recorded follow-up.
- **No org-user invites.** `org_users.role` (`owner`/`member`) ships so adding
  them needs no migration, but the endpoints do not. **When they land, fix
  `org_user_by_email` first:** uniqueness on `org_users` is per-organization, so
  one address may legitimately hold logins at two firms, and that lookup can
  then only return one of them. It is ordered by `created_at` today so the
  choice is at least deterministic, but the real answer is for the caller to
  name the organization. No current code path can create that state.
- **Org signup fails on a duplicate organization name** (unique constraint).
  Surfaced as `400 invalid_code`, which is a poor message for a real user.
