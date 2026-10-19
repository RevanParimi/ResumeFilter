# INTERVIEWS.md — AI interview delivery (S7.3)

Peer of `VERIFICATION.md`. What `src/app/interview/` is, why it is shaped this way,
and which lines are load-bearing. Design record:
[historical design in Git](https://github.com/RevanParimi/ResumeFilter/blob/54804988f3ead83d727754e4361266a4322655c4/docs/superpowers/specs/2026-07-31-s73-ai-interview-delivery-design.md).

**Advisory, always.** An interview score never gates matching, ranking, search,
or a depth report. It is one more thing a human reads.

---

## 1. The interview asks the depth report's own probes

Veritas already generates *"questions a fake can't survive"*: `probe_generation`
writes `CoherenceVerdict.probes` for exactly the claims the depth pipeline could
not settle. Before S7.3 nobody ever asked them.

`questions.py` plans a session from three sources, in this order:

| Source | Where it comes from | Why in this position |
|---|---|---|
| `probe` | the candidate's latest `Report` — flagged claims first, then deferred, then the rest | the engine already decided these claims were unsettled |
| `profile` | deterministic templates over the candidate's own experience and skills | always available; needs no LLM and no report |
| `domain` | `DomainModel.interview_seed_questions()` | keeps domain knowledge in `src/app/domains/`, per the repo's standing rule |

A probe question carries the verdict's `missing_signals` as its
`expected_signals`. That is the load-bearing link to scoring: **the scorer knows
what a genuine answer must mention, per question, without an LLM.**

Below `interview_min_questions` the start is refused (422). Conducting an empty
interview and scoring the silence would be worse than saying there is nothing to
ask.

## 2. The three decisions this subsystem rests on

1. **The transcript is stored; the audio never is.** Audio is transcribed in
   memory, its sha256 kept, the bytes discarded. The transcript IS stored, on the
   resume precedent — it is first-party content the candidate produced in order
   to be evaluated. An advisory score whose basis nobody can read is worse for
   the candidate than the PII cost.
2. **Candidate-initiated, with consent-gated org read.** Starting your own
   interview is a first-party act needing no grant (the S6.4 principle). Orgs
   read under a **new `ConsentPurpose.INTERVIEW_READ`** — a new purpose rather
   than another widening of `VERIFICATION_READ`, whose dated redefinition window
   is closed (`LEDGER.md`).
3. **Real ASR API, deferred TTS.** The API accepts audio; questions are
   delivered as text. The browser offers typed and microphone answers;
   [R3-S3-T3](docs/delivery/EVIDENCE-R3.md#r3-s3-t3) owns capture/fallback evidence. OpenRouter serves no TTS and the local option is a GPU
   dependency the offline suite cannot exercise.

## 3. Structural DPDP

Interview writes serialize on the existing candidate row, with live status and
current question checked again after provider work and lock acquisition. The
last answer, saved advisory assessment and completion audit commit together;
early finish computes from the turns saved under that lock. Conflicting starts,
duplicate/stale answers, expired sessions and repeated finishes return 409.
Completed/expired detail responses have no next question. Reload reads saved
progress; after an uncertain network outcome, read before resubmitting. Provider
work happens before locking and may be spent on a losing concurrent request.
See [R3-S3-T2A](docs/delivery/EVIDENCE-R3.md#r3-s3-t2a) for lifecycle validation;
[T2B](docs/delivery/EVIDENCE-R3.md#r3-s3-t2b) validates the real text browser
start/list/resume/answer/finish flow, history and saved advisory/version/evidence
explanations. Conflicts or uncertain writes require a saved-state refresh before
another submission; no automatic answer replay. Derived abandoned reads are
labeled expired. Drafts clear on refresh/navigation/account loss.
[T3](docs/delivery/EVIDENCE-R3.md#r3-s3-t3) connects audio-only microphone capture with
explicit stop/discard/submit, typed fallback and device cleanup. ASR refusals
leave the question open; audio request rate limits still apply.
[R3-S3-Q](docs/delivery/EVIDENCE-R3.md#r3-s3-q) closes combined browser text/audio,
saved-state restart and consent-permitted employer summary acceptance. This
uses synthetic media/fake ASR; live codec support and assessment quality remain unproved.

- **No column on either table can hold audio.** The only audio field is
  `audio_digest` (`String(64)`). Asserted by `test_interview_models.py`, which
  also enforces that `transcript` is the *single* unbounded column — even
  `question_text` is `String(512)`, so a reviewer scanning for "where could bytes
  live" finds one answer.
- **The transcript never reaches an org.** `InterviewSummary` — the org-facing
  projection — has no transcript and no turns *as fields*. Structural absence
  beats a filter someone forgets.
- **Erasure needs no new path.** `interview_sessions` CASCADEs from `candidates`,
  `interview_turns` from `interview_sessions`. The existing hard-delete sweeps
  both (`test_interview_erasure.py`, plus the smoke's final check).
- **Retention** is surfaced as a portal window (`ret_interview_session_days`,
  1095). The mechanical sweep is still PI-8; `sweep_active` stays `False`.
- **Attempts are visible.** The org view lists every COMPLETED session and
  `attempts` is that count, so retakes cannot be hidden. An abandoned session is
  not an attempt at anything and stays in the portal only.

## 4. The speech seam (`src/app/services/speech.py`)

Shaped like `src/app/services/llm.py`: `SpeechClient` (ABC) · `OpenRouterSpeech`
(live, `asr_model`, OpenAI-wire `input_audio`) · `NullSpeech` (refuses) ·
`build_speech`.

**No key ⇒ an audio answer is refused 422 `speech_unavailable` and the interview
runs as a text interview.** That is the deterministic fallback, said out loud
rather than degraded silently. `SpeechFailed` (bad format, timeout, upstream
error) is also 422 — and in both cases **no turn is written**, so a retry is free
and a vendor outage never costs a candidate their answer.

The browser holds a stopped clip in memory until explicit submission or discard.
Submission transcribes and scores immediately using the existing endpoint; the
saved transcript can be inspected afterwards, not edited before scoring. Capture
is bounded to 5 MB/two minutes, with 20s permission/encoding and 5s stop deadlines.
Background timer delivery may be delayed; byte checks still precede upload, and
server settings may impose a lower cap. Navigation, page exit, refresh, mode/account
changes and unmount stop tracks and discard clips; late permission streams are
stopped when they resolve. Invalid MIME/base64/ambiguous channels refuse before
ASR, empty output saves no turn, and provider payloads stay out of HTTP/app logs.
Only transcript/digest metadata is persisted. Current validation uses fake ASR;
live codec compatibility and transcription quality are not newly established.

`speech_provider` accepts `openrouter | sarvam | local`; only `openrouter` is
implemented. The other two build `NullSpeech` **even with a key**, because a
declared-but-inert provider must answer the same way at every door (the S7.2
review lesson).

### Live verification (2026-08-01)

`OpenRouterSpeech` → `mistralai/voxtral-small-24b-2507`: request path, format
mapping and response parsing all **verified live** on the project key.

**Known hazard, found during that check:** the model was sent a 440 Hz tone
containing no speech and returned fluent, confident prose. **Voxtral hallucinates
on non-speech audio.** Consequences here are bounded — the candidate sees their
own transcript and can see it is wrong, scores are advisory, and a hallucinated
answer still has to cover the question's `expected_signals` to score well — but a
future ASR adapter should carry a no-speech/energy guard. Recorded as a
follow-up rather than fixed, because the mitigation belongs with a real audio
pipeline, not with a seam that has no audio to inspect.

## 5. Scoring (`scoring.py`)

New scores use **`s73.2`**, a bounded deterministic content rubric. The frozen
synthetic development examples are in
[`interview_rubric_v2.json`](tests/fixtures/interview_rubric_v2.json); they are
regressions, not held-out quality data or representative accuracy evidence.
Four axes remain **neutral when unknown (0.5) rather than zero**:

| Axis | Deterministic signal | Neutral when |
|---|---|---|
| `specificity` | distinct reported action/object clauses, saturating at three | no usable content produces an insufficient turn |
| `ownership` | a personal action is explicitly claimed in a substantive clause; pronoun frequency gives no extra credit | team/passive or unspecified individual contribution |
| `depth` | investigation, change and outcome/rationale stages in context; explicit signal paraphrases provide an anchor | absent yardstick or unconfirmed relevance |
| `consistency` | remains 0.5; profile-name overlap is not independent factual corroboration | no independent factual comparison is implemented |

That rule is the module's ethic: a scorer that treats *"we have no yardstick"* as
*"the answer was shallow"* punishes candidates for gaps in the question bank.
Bare tools, numerals, pronouns and copied question clauses earn no content
credit. Repeated clauses are deduplicated; decimal metrics are not sentence
boundaries, and coordinated action clauses receive credit like semicolon forms.
Question topics anchor relevance independently of the depth yardstick. A generic
profile template needs a specific contextual signal or two distinct procedural
cues; a universal verb such as "compared" alone is insufficient. Naming the
profile's employer/tool is not mandatory and never verifies factual consistency.
Two substantive clauses can make a concise answer usable below
`interview_min_answer_words`; a shorter single clause or an answer with no usable
content scores **nothing**, rather than scoring zero for ability.

`confidence = sum(eligible turn evidence_confidence) / questions planned`, capped
at 0.95: coverage times mean evidence, with zero contributions from ineligible
turns and no intermediate rounding. Two or more distinct substantive clauses
receive `min(0.95, 0.35 + 0.2 × distinct clauses)`; a single clause contributes
zero assessment evidence at any length. It may still have descriptive turn
dimensions, with `limited_content`. Repetition or filler crossing the word floor
does not create confidence. Unconfirmed relevance is disclosed and caps a turn's
descriptive evidence metadata at 0.4; that turn contributes zero to assessment
dimensions and confidence. Dimension means use only eligible turns.

An assessment with no relevant usable turn stays `INSUFFICIENT_SIGNAL`, even
with a zero configured confidence floor. Coverage is answered/planned, including
answers whose content is insufficient; adding unsupported turns changes this
progress count without increasing assessment score/confidence.

This is an explicit English action/object and reasoning heuristic with a small
paraphrase vocabulary, not general semantic understanding or factual verification.
Unrecognized phrasing may require human review; lexical recognition can also
over-credit plausible prose. Substantive negative outcomes are still legitimate
answer content. These limitations require the later empirical-quality gate;
neither scores nor synthetic fixtures prove fraud or representative effectiveness.

**`InterviewBand` is not `DepthBand`**, though they share members. A resume-depth
band and a live-interview band must never be silently interchangeable — the S7.2
"two ladders" lesson applied to two scores. Nothing fuses the interview into
`depth_score` or `fabrication_risk`; like S7.2's document findings it **stands
beside** them.

**The LLM is a nudge, never the grader.** `adjust_with_llm` (tier `scoring` →
`model_scoring`) may move a dimension by at most `interview_llm_max_delta`, can
never introduce one, can never rescue an insufficient answer, and can never
produce a band by itself. In v2 it cannot adjust unknown depth/ownership or
unverified consistency, nor change evidence confidence/version. No key, bad JSON,
nonfinite/out-of-range members or an exception leave the entire baseline standing.

New turns store `scorer_version` and `evidence_confidence` in existing score JSON;
new assessments use `s73.2`. Transcript-free candidate/org summaries now include
`scorer_version`. Completed historical assessments retain their original values
and versions; reads/restarts perform no rewrite. Wholly legacy active sessions
retain v1 aggregation over their saved scores/word counts. An active session
mixing legacy and v2 turns, or containing an unsupported version, completes as
`mixed/unknown` with empty dimensions, zero confidence and an insufficient band.
Legacy turn JSON is preserved. There is no working migration or automatic
rescoring, and no new interview UI behavior; browser wiring remains R3-S3-T2B.

## 6. Proxy signals (`proxy.py`) — and the no-biometrics decision

| Finding | Severity | Check |
|---|---|---|
| `identity_assurance_none` | soft | assurance level 0 |
| `identity_assurance_low` | info | level 1 (self-attested only) |
| `answer_rate_implausible` | soft | audio: words ÷ elapsed > `interview_max_words_per_second` |
| `typed_answer_rate_implausible` | soft | text: past `interview_max_typed_words_per_second` |
| `answer_style_ai_generated` | soft | S2.1's deterministic stylometry, ≥2 independent tells |
| `text_channel_only` | info | no audio turns — said out loud rather than hidden |

`elevated` requires **two** soft findings (the S2.4 AND-gate); the band stops at
`elevated` and no finding may be `hard`, because nothing here can *confirm* a
proxy.

**No voice biometrics — a decision, not an omission.** A voiceprint is biometric
data under DPDP; comparing sessions would mean storing a voice embedding, exactly
the artifact class S7.1 made structurally impossible, and would need its own
consent purpose and legal review. What ships is what the roadmap asked for: the
`IdentityAssurance` number, **stamped at session start** and never recomputed, so
verifying yourself afterwards cannot rewrite what a finished session was worth.

## 7. Session lifecycle

- One live session per candidate; a second start is **409** naming the live one.
  Concurrent sessions would make attempt counting and every timing signal
  meaningless.
- Every answer must name its `question_id`; a mismatch is **409**, so two racing
  clients cannot collapse into one turn.
- **Expiry is read-time.** The stored status stays `in_progress`;
  `effective_status` derives `abandoned` past `expires_at`. No scheduler exists,
  so a stored `abandoned` would be a lie nobody corrects (the S7.1 rule).
- Answering the last question completes the session; `finish` completes early
  with lower coverage and therefore lower confidence.
- **Cross-candidate isolation is structural**: every handler resolves
  `candidate_id` from the key. Another candidate's session is an
  indistinguishable 404.

**The assessment is stored** — the one deliberate departure from the read-time
roll-up rule. `IdentityAssurance` and `ClaimEvidence` depend on the clock and on
rows that arrive later, so storing them would store a lie; an assessment is a
closed fact about a finished session, and recomputing it would re-hit a paid
model and produce a different number on every read.

## 8. API

**Candidate plane (`X-Candidate-Key`)**

| Route | Notes |
|---|---|
| `POST /portal/interviews` | 422 when there is nothing to ask · 409 if one is live |
| `GET /portal/interviews` | summaries — no transcripts |
| `GET /portal/interviews/{id}` | full view **with** transcripts (their data) |
| `POST /portal/interviews/{id}/answers` | 409 wrong question/expired · 422 oversize, `speech_unavailable`, `speech_failed` · 400 no body or bad base64 |
| `POST /portal/interviews/{id}/finish` | complete early |

`GET /portal/me` gains `interviews` (summaries) and a retention window.

**Org plane (`X-Org-Key`)**

| Route | Notes |
|---|---|
| `GET /interview/candidates/{id}/assessments` | `INTERVIEW_READ`-gated; **every attempt audited allowed and denied** (`interview.query`). Bands, dimensions, proxy band, timestamps, `attempts`. Never a transcript. |

No admin-plane surface: nothing here needs an operator.

## 9. Audit

`interview.start` (actor: the candidate) and `interview.complete` (actor:
`system` — the platform scored it, not the candidate) land in the shared
`audit_log` and therefore in the candidate's own access log. **Individual turns
are not audited**: a turn is the candidate acting on their own session, inside a
session whose start they can already see, and a row per answer would flood the
very log that exists to make disclosure legible.

## 10. Config

All `interview_*` knobs plus `ret_interview_session_days`, `speech_timeout_seconds`
and `speech_max_retries` live in `config.yaml`. Band cut-points ARE knobs (the
`ai_*`/`fr_*`/`rep_*` precedent — a band is a presentation choice over a score).
The **scorer's internals are not**: `SPECIFICITY_TARGET` and
`SUBSTANCE_TARGET_WORDS` (legacy aggregation only) are module constants versioned by `SCORER_VERSION`,
because they define what the number means and a deploy that silently redefined
them would make two stored assessments incomparable.

## 11. Non-goals (S7.3)

- TTS / spoken question delivery — `tts_model` stays inert.
- Video, liveness, **voice biometrics** — §6.
- Org-invited, requisition-targeted interviews — needs an invite flow and a
  third-party-initiated DPDP basis.
- Fusing the interview into `depth_score` or `fabrication_risk` — it stands beside.
- Interview results as ledger records — the interview is platform-conducted
  first-party data, not an org's submitted record; putting it in the ledger would
  misdescribe who observed it.
- Disclosing transcripts to orgs — deliberately not v0.
- A retention sweeper (PI-8) · Hinglish/code-switch (deferred, English-first).

## 12. Follow-ups

1. Voice-consistency proxy detection — needs a consent purpose, a stored
   embedding, and legal review. The honest path to a *real* proxy signal.
2. A no-speech/energy guard on the ASR adapter (§4's hallucination hazard).
3. TTS question delivery, once a hosted Indian-English voice is on the account.
4. Org-invited interviews, once the invite basis is designed.
5. Interview scores as feature-store features, once PI-8's calibration harness
   can measure their predictive value against ledger outcomes.
6. Sarvam ASR for India data residency, when production DPDP posture makes it
   real (`MODELS.md`: a residency choice, not a capability one).
