# S7.3 — AI interview delivery v0 (design)

**Date:** 2026-07-31
**Sprint:** PI-7 · S7.3 (the last sprint in PI-7, and the largest build in it)
**Status:** design approved (three forks decided with the user, §0) — plan next
**Reads:** `docs/ROADMAP.md` · `docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md` §5C
· `VERIFICATION.md` §§3, 11 · `MODELS.md` · `FLOW.md`
**Precedents it follows:** S7.1 (adapter seam refuses by default; read-time roll-ups;
structural DPDP) · S7.2 (a second producer on an existing spine; `details` is codes, not
content) · S2.1 (deterministic signal ⊕ *capped* LLM) · S6.4 (first-party self-service
needs no grant)

---

## 0. The three decisions this design rests on

Decided with the user before writing (each had a real alternative):

1. **The transcript is stored; the audio never is.** Audio is transcribed in memory, its
   sha256 kept, the bytes discarded — voice is biometric-adjacent, so it stays *structurally*
   unstorable (no column can hold it). The transcript text **is** stored, on the resume
   precedent: it is first-party content the candidate deliberately produced to be evaluated.
   Rejected: scores-and-codes-only. An advisory score whose basis nobody can read is worse
   for the candidate than the PII cost — "advisory + human-reviewed" is empty if the human
   has nothing to review, and a scoring bug would be undebuggable after the fact.
2. **Candidate-initiated, with consent-gated org read.** The candidate starts an interview
   themselves from the portal (S6.4: acting on your own data is a data-principal right, not
   a disclosure). Orgs read assessments under a **new `ConsentPurpose.INTERVIEW_READ`** —
   a new purpose rather than another widening of `VERIFICATION_READ`, whose redefinition
   window the ROADMAP records as **closed**.
3. **Real ASR, deferred TTS.** A speech seam mirroring the LLM seam, with a live
   OpenRouter ASR adapter. Candidates answer **by audio**; questions are delivered as
   **text**. OpenRouter has no TTS and `kokoro-82m` is a local GPU dependency neither the
   offline suite nor the key-less smoke could exercise, and question delivery is cosmetic —
   the signal is in the answer. Rejected: shipping the ASR seam declared-but-inert, which
   would be the same false claim S7.1's review caught in `government_id`.

## 1. What this sprint is, in one paragraph

Veritas already generates *"questions a fake can't survive"*: `probe_generation` writes
`CoherenceVerdict.probes` for exactly the claims the depth pipeline could not verify.
Today nobody ever asks them. **S7.3 asks them** — audio-first, English, advisory — and
scores whether the answers close the gaps the report identified. That framing is the whole
design: this is not a generic interview product bolted onto the repo, it is the depth
engine's own unanswered questions, delivered and scored, with proxy-detection hooks reading
the S7.1 identity number.

```
resume ─▶ extraction ─▶ claims ─▶ verdicts ─▶ probes ─┐
                                                      ▼
                              S7.3  interview session (probes asked out loud)
                                                      │
                              answers (audio ─ASR─▶ transcript | typed text)
                                                      ▼
                          deterministic rubric ⊕ capped LLM ─▶ InterviewAssessment
                          IdentityAssurance + behaviour     ─▶ ProxyRisk
```

## 2. Package shape

A new pure-ish package `app/interview/` — peer of `app/verification/` and `app/portal/` —
plus one new service seam.

| Module | Contents | Purity |
|---|---|---|
| `app/interview/schema.py` | contracts + taxonomies (code constants, never config) | pure |
| ↳ | `InterviewStatus` · `QuestionSource` · `AnswerChannel` · `InterviewBand` · `ProxyBand` · `InterviewQuestion` · `InterviewTurn` · `TurnScore` · `ProxyFinding` · `ProxyRisk` · `InterviewAssessment` · `InterviewSession` · `InterviewSummary` | |
| `app/interview/questions.py` | `build_question_plan` — probes ▸ profile templates ▸ domain seeds | pure |
| `app/interview/scoring.py` | deterministic rubric per turn; aggregation to an assessment | pure, clock-free |
| `app/interview/proxy.py` | `assess_proxy_risk` over assurance + behaviour | pure, clock-injected |
| `app/interview/models.py` | `InterviewSessionRow`, `InterviewTurnRow` | ORM |
| `app/interview/store.py` | `InterviewStore` — CRUD + candidate-scoped reads | I/O |
| `app/interview/service.py` | `InterviewService` — the state machine, consent, audit | I/O |
| `app/services/speech.py` | `SpeechClient` ABC · `OpenRouterSpeech` · `NullSpeech` · `build_speech` | I/O |

`Services` gains `speech: SpeechClient` and `interview: InterviewService`, both wired in
`build_default_services` (function-local imports, the established cycle-safe pattern).
`InterviewService` composes `CandidateStore` + `LedgerStore` + `ReportStore` +
`VerificationService` + `LLMClient` + `SpeechClient`. It owns exactly two tables.

**Layering rule:** `app/interview/` may import `app/verification/` (it reads the assurance
number); `app/verification/` must never import `app/interview/`. Asserted by a test, the
way the ledger↔comp direction was in S5.2.

## 3. The question plan (`questions.py`)

```python
def build_question_plan(
    *, profile: CandidateProfile, report: Optional[Report],
    domain: DomainModel, limit: int, minimum: int,
) -> list[InterviewQuestion]
```

Pure, deterministic, stable order (tests depend on it). Three sources, in priority order:

| Source | Where it comes from | Why first/second/third |
|---|---|---|
| `PROBE` | the candidate's latest depth `Report`: verdicts for `flagged_claim_ids`, then `deferred_claim_ids`, then any verdict carrying probes | highest value — the engine already decided these claims were unsettled |
| `PROFILE` | deterministic templates over the candidate's own experience/skills | always available; needs no LLM and no report |
| `DOMAIN` | new optional `DomainModel.interview_seed_questions() -> list[str]`, base returns `[]` | keeps domain knowledge in `app/domains/` per CLAUDE.md, without forcing every domain to implement it |

A probe question carries the **`expected_signals`** of the claim it came from (the verdict's
`missing_signals`). This is the load-bearing link to scoring: the scorer knows what a
genuine answer would have to mention, per question, without an LLM.

Profile templates are code constants with slots, e.g.
`"You list {skill} at {employer}. Describe a specific problem you solved with it — what broke, and how did you find the cause?"`
Their `expected_signals` are the slot values plus generic depth markers (failure, trade-off,
latency, cost, rollback).

Dedup by normalized question text; cap at `interview_max_questions`. If the plan cannot
reach `interview_min_questions` — a candidate with no profile at all — starting an interview
is **422**, not an empty session. There is nothing to ask, and an assessment built on
nothing is precisely the false-confidence failure the whole codebase is arranged against.

## 4. The speech seam (`app/services/speech.py`)

Mirrors `app/services/llm.py` exactly, because that seam has survived six PIs.

```python
class Transcript(BaseModel):
    text: str
    duration_seconds: Optional[float] = None
    model: Optional[str] = None

class SpeechClient(ABC):
    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript: ...

class OpenRouterSpeech(SpeechClient):   # settings.asr_model, OpenAI-wire input_audio
class NullSpeech(SpeechClient):         # no key -> raises SpeechUnavailable

def build_speech(settings) -> SpeechClient   # key + provider == "openrouter" -> live, else Null
```

`speech_provider` is already a `Literal["openrouter", "sarvam", "local"]` in `Settings`.
v0 implements **`openrouter` only**; `sarvam` and `local` build a `NullSpeech` and are
declared-inert — inertness that reads the same at every door, per the S7.2 review lesson.

**The deterministic fallback is the honest one:** with no key (or a non-openrouter
provider), an *audio* answer is refused **422 `speech_unavailable`** and the candidate is
told to answer in text. The interview still runs end to end, still scores, still produces an
assessment — it is a text interview. Nothing silently degrades to a worse number; the
channel is recorded per turn and the proxy signal says so (§6). ASR failure mid-session
(network, timeout) is the same 422 with reason `speech_failed`: the turn is **not** recorded,
so a retry is free and no answer is ever lost to a vendor outage.

`speech_timeout_seconds` (60) and `speech_max_retries` (2) mirror the LLM knobs.

## 5. Scoring (`scoring.py`)

**Per turn, deterministic, four dimensions in 0..1:**

| Dimension | Deterministic signal |
|---|---|
| `specificity` | density of concrete tokens — numerals, versions, named tools (matched against the S1.4 skill taxonomy), proper nouns. Saturating, so a wall of jargon does not win |
| `ownership` | first-person singular agency ("I built", "I traced") vs plural/passive ("we had", "it was decided"). Ratio-based, saturating |
| `depth` | coverage of the question's `expected_signals` — how much of what a genuine answer must contain actually appeared |
| `consistency` | employers/skills named in the answer that also appear on the profile. **Neutral (0.5) when unknown** — never punished, because a candidate naming a client or a tool we never taxonomised is normal |

Answers under `interview_min_answer_words` are marked `insufficient_answer`: they count
against coverage but contribute to no dimension mean. Silence cannot score.

**Neutral-when-unknown is a rule, not a special case.** A question with no
`expected_signals` (a `DOMAIN` seed opener) scores `depth` at 0.5 rather than 0 — the same
treatment `consistency` gets for an unrecognised employer. Absence of a yardstick is not
evidence of shallowness, and a scorer that confuses the two would punish candidates for the
question bank's gaps.

**Aggregate → `InterviewAssessment`:** weighted mean over dimensions (`interview_weight_*`
knobs, `depth` dominant), plus a `confidence` from coverage (`answered / planned`) and
answer substance. Below `interview_min_confidence` the band is `INSUFFICIENT_SIGNAL` and the
assessment asserts nothing — the S2.x/S3.4/S5.2 stance, unchanged.

`InterviewBand` is its **own** StrEnum (`insufficient_signal | superficial | emerging |
solid | deep`) with the same members as `DepthBand`, deliberately **not** the same type. A
resume-depth band and a live-interview band must never be silently interchangeable or fused;
this is the S7.2 "two ladders, one table" lesson applied to two scores. Nothing in v0 fuses
the interview into `depth_score` or `fabrication_risk` — like S7.2's document findings, it
**stands beside** them.

**Optional capped LLM pass.** A new `"scoring"` tier resolves `model_scoring`
(`model_for_tier` and `llm.Tier` both gain it). Per turn, the LLM sees the question, the
expected signals and the transcript (capped at `interview_llm_excerpt_chars`) and returns
per-dimension adjustments. Fusion is the S2.1 pattern: **the LLM may move a dimension by at
most `interview_llm_max_delta` (0.2) and can never alone produce a band.** `NullLLM` returns
`{}` → deterministic scores stand. A malformed or absent response is not an error.

`scorer_version` is stamped on every stored assessment, so a future scoring change is
visible in the data instead of silently rewriting history.

## 6. Proxy signals (`proxy.py`) — assurance + behaviour, never biometrics

```python
def assess_proxy_risk(*, assurance: IdentityAssurance, turns: list[InterviewTurn],
                      now: datetime, settings) -> ProxyRisk
```

| Finding | Severity | Check |
|---|---|---|
| `identity_assurance_none` | soft | assurance level 0 — nothing at all ties this session to a person |
| `identity_assurance_low` | info | level 1 (self-attested only) |
| `answer_rate_implausible` | soft | audio turn: words ÷ elapsed > `interview_max_words_per_second` (4.0; human speech ≈ 2.5) — a read-aloud script or a pasted transcript |
| `typed_answer_rate_implausible` | soft | text turn: > `interview_max_typed_words_per_second` (8.0) — paste, not typing |
| `answer_style_ai_generated` | soft | S2.1's `ai_text.assess_deterministic` over the concatenated transcript lands in its top band |
| `text_channel_only` | info | no audio turns — proxy is inherently less assessable, said out loud rather than hidden |

Band: `low | moderate | elevated`; **`elevated` requires ≥2 soft findings** (the S2.4
AND-gate, so one noisy signal cannot brand anyone). It stops at `elevated` — there is no
"confirmed", because none of these findings can confirm anything.

**No voice biometrics in v0, and this is a decision, not an omission.** A voiceprint is
biometric data under DPDP; comparing sessions would require storing a voice embedding —
exactly the artifact class S7.1 made structurally unstorable — and would need its own consent
purpose and its own legal review. The roadmap asked for "proxy-detection hooks reading
`IdentityAssurance`", and that is precisely and only what ships: the assurance level is
stamped **at session start** (`assurance_level_at_start`), never recomputed, so a candidate
cannot verify themselves afterwards and rewrite what the session was worth.

## 7. DPDP posture

- **Audio is structurally unstorable.** Neither table has a column able to hold audio; the
  only audio field is `audio_digest` (sha256, `String(64)`). Asserted by a test in both the
  schema and the models, the way S7.1/S7.2 assert theirs.
- **The transcript is stored** (§0.1) and is candidate-visible in the portal. It is **not**
  disclosed to orgs in v0 — an org sees bands, dimensions, proxy band, attempt count and
  timestamps, never the candidate's words. Same deferred-disclosure shape as S6.4's
  `ReportRef` decision, recorded here so the next session does not re-litigate it.
- **One new `ConsentPurpose`: `INTERVIEW_READ`.** Query-time enforced, **every attempt
  audited allowed *and* denied** (action `interview.query`), mirroring
  `query_records_for_org` and S7.2's `claim.query`.
- **Erasure needs no new path.** `interview_sessions` CASCADEs from `candidates`,
  `interview_turns` CASCADEs from `interview_sessions`. The existing hard-delete sweeps
  both; proven by a test and by the smoke's final check.
- **Retention posture** surfaced in the portal as a new `RetentionWindow`
  (`ret_interview_session_days`, 1095). The mechanical sweep remains PI-8 — unchanged, and
  still honestly reported as `sweep_active=False`.
- **Attempts are never hidden.** The org-facing view lists **every completed session**, and
  `attempts` is exactly that count — so a candidate cannot retake until lucky and disclose
  only the best run. Abandoned sessions are not disclosed to orgs (an interrupted session is
  not an attempt at anything) but do appear in the candidate's own portal.

## 8. Data model + migration `0015_ai_interviews`

**`interview_sessions`** — candidate CASCADE, indexed on `candidate_id` and `status`:

| Column | Type | Note |
|---|---|---|
| `id` | String(36) PK | |
| `candidate_id` | FK candidates.id **CASCADE** | |
| `domain` | String(32) | which `DomainModel` framed the questions |
| `report_id` | String(36) nullable | provenance of the probes. **Not** a FK — reports live in a separate SQLite DB (`report_db_path`); same reasoning as `VerificationRow.consent_id` |
| `status` | String(16) indexed | `in_progress \| completed \| abandoned` |
| `assurance_level_at_start` | Integer | the S7.1 hook, point-in-time |
| `planned_questions` | JSON | the ordered plan, so it is stable across requests |
| `assessment` | JSON nullable | see below |
| `scorer_version` | String(16) nullable | |
| `started_at` / `completed_at` / `expires_at` / `created_at` | DateTime(tz) | |

**`interview_turns`** — session CASCADE, indexed on `session_id`:
`id`, `session_id`, `sequence`, `question_id`, `question_text` (Text), `question_source`
(String(24)), `expected_signals` (JSON), `channel` (String(8)), `transcript` (Text),
`audio_digest` (String(64) nullable), `audio_duration_seconds` (Float nullable),
`word_count` (Integer), `scores` (JSON), `asked_at`, `answered_at`, `created_at`.

**Why the assessment is stored when `IdentityAssurance` and `ClaimEvidence` are not.** Those
roll-ups depend on the clock (expiry) and on rows that may arrive later, so storing them
would store a lie that nobody corrects. An interview assessment is a **closed fact about a
finished session** — its inputs cannot change — and recomputing it would re-hit a paid model
and produce a different number each read. It is computed once at completion, stamped with
`scorer_version`, and stored. The spec states this explicitly because it is the first
deliberate departure from the read-time-roll-up rule, and a reviewer should see it argued
rather than assume it was forgotten.

Drift / index / FK-ondelete / nullability guards are extended to both tables (the S7.1
nullability guard caught a real migration/ORM disagreement — it earns its keep).

## 9. Session state machine

- `POST /portal/interviews` → body `{"domain": "genai"}` (the repo's existing default-string
  convention, not a new config knob). Builds the plan, stamps assurance, status
  `in_progress`, `expires_at = now + interview_session_ttl_minutes` (120). Returns the
  session + first question.
- **One live session per candidate.** Starting a second while an unexpired `in_progress`
  session exists is **409** with the live session's id. Concurrent sessions would make both
  attempt counting and the timing-based proxy signals meaningless, and "resume the one you
  started" is the behaviour a candidate expects anyway.
- Each answer must name its `question_id`. A mismatch with the current question is **409**,
  never a silent re-answer — two racing clients must not collapse into one turn.
- Answering the last planned question completes the session and computes the assessment.
  `POST .../finish` completes early; the assessment is computed over what was answered and
  its confidence falls with coverage.
- **Expiry is read-time**, never a stored lie (S7.1's rule): the stored `status` stays
  `in_progress`, and an `effective_status` computed against the injected clock reads
  `abandoned` past `expires_at`. Such a session refuses new answers (409) and — if any turn
  was answered — still exposes an assessment marked incomplete. No sweeper is invented;
  PI-8 still owns that.
- **Cross-candidate isolation is structural**: every candidate-plane handler resolves
  `candidate_id` from the key, never from a path or body parameter. Another candidate's
  session is an indistinguishable 404.

## 10. API

**Candidate plane (`X-Candidate-Key`)**

| Route | Behaviour |
|---|---|
| `POST /portal/interviews` | start; 422 when there is nothing to ask |
| `GET /portal/interviews` | list of `InterviewSummary` |
| `GET /portal/interviews/{id}` | session + next question + turns (**with** transcripts — their data) |
| `POST /portal/interviews/{id}/answers` | `{question_id, text? \| audio_b64?, mime?}` → scored turn + next question or completion. 409 wrong question / expired · 422 oversize, empty, or `speech_unavailable` |
| `POST /portal/interviews/{id}/finish` | complete early → assessment |

`MyData` gains `interviews: list[InterviewSummary]` and a retention window.

**Org plane (`X-Org-Key`)**

| Route | Behaviour |
|---|---|
| `GET /interview/candidates/{id}/assessments` | `INTERVIEW_READ`-gated, audited allowed **and** denied. Bands, dimensions, proxy band, attempt count, timestamps. **No transcripts, no question-level answers.** |

No admin-plane surface. Nothing here needs an operator.

## 11. Config (`interview_*`, plus two speech knobs)

```
interview_max_questions: 8          interview_min_questions: 3
interview_session_ttl_minutes: 120  interview_min_answer_words: 12
interview_max_audio_b64_chars: 8000000   interview_max_answer_chars: 20000
interview_max_words_per_second: 4.0      interview_max_typed_words_per_second: 8.0
interview_llm_max_delta: 0.2             interview_llm_excerpt_chars: 4000
interview_min_confidence: 0.5
interview_weight_specificity: 1.0        interview_weight_ownership: 1.0
interview_weight_depth: 1.5              interview_weight_consistency: 1.0
ret_interview_session_days: 1095
speech_timeout_seconds: 60               speech_max_retries: 2
```

`model_scoring`, `speech_provider`, `asr_model` already exist and stop being inert.
`tts_model` stays inert and is documented as such. **Severities and bands are code
constants, not knobs** — the S7.2 stance: a deploy-time switch that silently reclassifies
`soft` → `hard` is exactly what that stance exists to prevent.

## 12. Testing and smoke

Fully offline: `FakeSpeech` (canned transcript) joins `conftest.py` beside the existing
`FakeLLM`; the default fixture services use `NullSpeech` + `NullLLM`, so the suite proves
the no-key path by default and the fakes are opt-in per test. New tests cover schema, plan building (ordering, dedup, caps, the 422 floor),
each scoring dimension and the aggregation, each proxy finding and both band gates, the
`interview → verification` import direction, migration guards + the no-audio-column
structural test, store, the service state machine (expiry, 409s, isolation), both API planes,
`MyData`, config, and erasure.

**`scripts/smoke_s73.py`** (uvicorn, key-less, no network): candidate + key → no interviews
→ start → first question present → **audio answer 422 `speech_unavailable`** → text answers
score and advance → wrong `question_id` 409 → oversize answer 422 → session completes with
an advisory assessment (band + confidence + `advisory: true`) → proxy risk shows
`identity_assurance_none`, band ≤ `elevated` → candidate self-attests (S7.1) → a **new**
session stamps assurance 1, proving the hook reads the live number → org read 403 → grant
`interview_read` → 200 → **no transcript anywhere in the org payload** → revoke → 403 →
`/portal/me` shows interviews + the retention window → access log shows `interview.query`
with the org name resolved → `DELETE /portal/me` → org read 404.

A **live** ASR check is run manually once with the real key (one audio turn through
`OpenRouterSpeech`) and its result recorded in `MODELS.md`'s verification log — the same
treatment `deepseek-v3.2` and `voxtral` got on 2026-07-26. It is not part of the offline
suite or the smoke.

## 13. Non-goals (S7.3)

- **TTS / spoken question delivery** — decided in §0.3; `tts_model` stays inert.
- **Video, liveness, voice biometrics** — §6. Needs a consent purpose, a stored embedding,
  and a legal review; none of it is v0.
- **Org-invited interviews against a requisition** — needs an invite/acceptance flow and a
  third-party-initiated DPDP basis. The candidate-initiated flow is the whole of v0.
- **Fusing the interview into `depth_score` or `fabrication_risk`** — it stands beside them,
  the S7.2 posture.
- **Interview results as ledger records or feature-store features** — the interview is
  platform-conducted first-party data, not an org's submitted record; folding it into the
  ledger would misdescribe who observed it.
- **Coding/live-code interviews** — a standing non-goal (gap analysis §5C), unchanged.
- **A retention sweeper** — PI-8, unchanged.
- **Hinglish / code-switch** — deferred by the 2026-07-26 decision; English-first.

## 14. Follow-ups this sprint deliberately leaves open

1. Voice-consistency proxy detection (needs a new consent purpose + a stored embedding +
   legal review) — the honest path to a *real* proxy signal.
2. TTS question delivery once a hosted Indian-English voice exists on the account, or a
   local GPU is in scope (PI-8).
3. Org-invited, requisition-targeted interviews (the Mercor flow) once the invite basis is
   designed.
4. Interview scores as feature-store features, once their predictive value is measurable
   against ledger outcomes (PI-8's calibration harness).
5. Disclosing transcripts to orgs under an explicit, separate consent — deliberately not v0.
6. Sarvam ASR for India data-residency, when production DPDP posture makes it real
   (`MODELS.md`: it is a residency choice, not a capability one).
