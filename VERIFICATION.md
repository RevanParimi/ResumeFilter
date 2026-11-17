# Verification and contact assurance

Veritas records identity-verification outcomes and computes an advisory assurance
level at read time. The ladder does not change matching, ranking, depth scores,
claim verdicts or hiring decisions. The portal exposes the candidate's own records
and the "Verify a contact" flow.

| Level | Method | Current behavior |
|---|---|---|
| 0 | none | No current verification |
| 1 | `self_attested` | Candidate assertion |
| 2 | `otp_email`, `otp_phone` | Contact control; email uses the configured provider, phone delivery is unavailable by default |
| 3 | `manual_review` | Operator review recorded out of band |
| 4 | `government_id` | Declared and unimplemented; refused with 422 |

The employment-document intake and employer employment-evidence route were
removed. Existing `employment_claim` rows and their method enum values still
load; they do not raise identity assurance. No document intake remains.

## Routes and authorization

Candidate sessions or `X-Candidate-Key` resolve the subject; request parameters
cannot choose another candidate. Cookie writes require the shared CSRF check.

- `POST /portal/verifications`: start with `{method, destination?}`.
- `POST /portal/verifications/{id}/confirm`: confirm with `{code}`.
- `GET /portal/verifications`: the subject's records plus assurance.
- `GET /verification/candidates/{id}/assurance`: employer disclosure, requiring
  current `verification_read` consent. Allowed and denied reads are audited.
- `POST /candidates/{id}/verifications/manual-review`: operator-only outcome,
  optional note and evidence digest. Candidates cannot award themselves review.

First-party self-attestation and verification of one's own contact need no
consent grant. A third-party adapter would require `identity_verify`; the
unimplemented government-ID adapter remains refused even if consent exists.
`interview_read` is a separate purpose and is not unlocked by `verification_read`.
All existing consent-purpose values remain valid. See [LEDGER.md](LEDGER.md).

## Contact binding and storage

OTP destinations must match a contact hash already on the candidate's record;
knowing a candidate key cannot verify an unrelated mailbox or phone number.
The challenge stores a salted code digest and a destination hash, not a raw OTP
or raw destination. Wrong-attempt limits, expiry and resend cooldowns remain.
Email delivery honors the configured provider; unavailable delivery is refused.
The existing bounded contact-code pool and its refusal codes remain unchanged.

`verifications` stores outcomes, timestamps, method/subject metadata and an
optional evidence digest. `verification_challenges` holds short-lived challenge
state. The shipped flows retain no document image, biometric or raw audio.
Candidate erasure cascades both tables. Expiry is evaluated at read time so a
lapsed result stops contributing without waiting for a scheduler. The operator
retention sweep uses `ret_verification_days`; see [OPERATING.md](OPERATING.md).

## Settings

The current controls are `verif_otp_length` (6), `verif_otp_ttl_minutes` (10),
`verif_otp_max_attempts` (5), `verif_otp_resend_cooldown_seconds` (60),
`verif_outcome_ttl_days` (365), `ret_verification_days` (1095),
`contact_code_max_concurrent_requests` (2), `contact_code_wait_seconds` (20)
and `verif_otp_debug_echo` (false). Debug echo is honored only in local mode.
No government-ID provider, liveness, face matching or SMS provider is shipped.
