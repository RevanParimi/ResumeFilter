"""Centralized configuration: YAML for tunables, env for secrets.

Non-sensitive config (model tiers, calibration thresholds, store locations) lives
in ``config.yaml`` so behavior changes without code changes and is reviewable in
git. Secrets (API keys, tokens) live ONLY in the environment / ``.env`` and are
never committed. Precedence (highest first):

    constructor args  >  environment (DEE_*)  >  .env  >  config.yaml  >  defaults

So env can always override a YAML value (handy per-deploy), and secrets never
need to appear in YAML. The YAML path is ``config.yaml`` by default; override it
with ``DEE_CONFIG_FILE`` (tests point this at a nonexistent path for pure defaults).

Usage:
    from app.core.config import get_settings
    settings = get_settings()        # cached singleton
    model = settings.model_reasoning
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Settings(BaseSettings):
    """Application settings, sourced from env / .env with the ``DEE_`` prefix."""

    model_config = SettingsConfigDict(
        env_prefix="DEE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add a YAML source UNDER env/.env. Missing file → contributes nothing."""
        yaml_path = os.environ.get("DEE_CONFIG_FILE", "config.yaml")
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_source,
            file_secret_settings,
        )

    # --- LLM provider: OpenRouter (OpenAI-wire-compatible) --------------------
    # OpenRouter fronts many model vendors behind one OpenAI-compatible API, so
    # the whole pipeline stays vendor-neutral and economical. Key is required for
    # live calls; empty is allowed so tests/offline scaffolding import without it.
    openrouter_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="OpenRouter API key (sk-or-...). Never hardcode in source.",
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional attribution headers OpenRouter uses for app rankings (both optional).
    openrouter_app_url: str = ""
    openrouter_app_title: str = "depth-eval-engine"

    # Tiered models. Domain/node code asks for a *tier*, never a literal model id.
    #   reasoning      → claim_extraction + plausibility
    #   reasoning_hard → override for the hardest plausibility reasoning
    #   parsing        → cheap structural work (maps to the FAST model)
    #   bulk           → high-volume text gen/classification (future flywheel
    #                    re-scoring/labeling). NOT embeddings — those use a
    #                    dedicated embedder, never a chat tier. Unused at M0.
    # Defaults mirror config.yaml (live OpenRouter pricing checked 2026-07-26):
    # deepseek-v3.2 ($0.269/$0.400 per M) is the default reasoning workhorse;
    # qwen3.7-max ($1.475/$4.425) is retained only as the hard-escalation tier.
    model_reasoning: str = "deepseek/deepseek-v3.2"
    model_reasoning_hard: str = "qwen/qwen3.7-max"
    model_fast: str = "qwen/qwen3.6-flash"
    model_bulk: str = "qwen/qwen3.6-35b-a3b"
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 60.0
    # SDK-level retries with backoff; provider blips degrade to rules, not 500s.
    llm_max_retries: int = 2

    # --- Future model slots (PI-7 interviews / PI-8 embeddings) ----------------
    # INERT until their sprint lands — declared now so model choices are
    # business-tunable config, not code (research + direction: MODELS.md).
    #   scoring        → decisive interview-scoring calls (S7.3); advisory +
    #                    human-reviewed, so the value tier is the right default
    #   speech_provider→ openrouter (existing account, cheapest dev path) |
    #                    sarvam (India-hosted DPDP residency, prod) | local (PI-8)
    #   asr/tts        → Indian-accented English first (Hinglish deferred)
    #   embedding/reranker → PI-8 semantic match + PI-5/8 search quality
    model_scoring: str = "deepseek/deepseek-v3.2"
    speech_provider: Literal["openrouter", "sarvam", "local"] = "openrouter"
    asr_model: str = "mistralai/voxtral-small-24b-2507"
    tts_model: str = "kokoro-82m"
    embedding_model: str = "qwen/qwen3-embedding-0.6b"
    reranker_model: str = "qwen/qwen3-reranker-0.6b"

    # --- GitHub (provenance) --------------------------------------------------
    github_token: SecretStr = Field(default=SecretStr(""))
    github_api_base: str = "https://api.github.com"

    # --- Profile sources (PI-6, S6.1): GitHub-as-signal ------------------------
    # A candidate-supplied GitHub handle is fetched (public data only) and turned
    # into an ADVISORY structured skill/activity signal. Limits bound rate-limit
    # exposure; forks are not authored signal.
    ps_github_repo_limit: int = Field(default=100, ge=1)
    ps_github_language_repos: int = Field(default=30, ge=0)
    ps_github_include_forks: bool = False

    # --- Profile sources (PI-6, S6.2): LinkedIn export parsing ------------------
    # The candidate uploads their own LinkedIn "Get a copy of your data" ZIP.
    # Pure parse (no network, no LLM). Self-reported Skills.csv entries are
    # low-confidence CLAIMS, bumped only when a position/headline corroborates.
    max_linkedin_b64_chars: int = 8_000_000  # reject oversize uploads (≈6 MB zip)
    ps_linkedin_skill_base_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    ps_linkedin_skill_corroborated_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    ps_linkedin_max_rows: int = Field(default=5_000, ge=1)  # per-CSV row cap

    # --- Normalization curation loop (PI-6, S6.3) ------------------------------
    # Human-in-the-loop taxonomy repair: unmapped skill terms surfaced by the
    # profile-source adapters queue for admin review; a resolution feeds a
    # deterministic normalize_skill overlay. No LLM. The queue is
    # candidate-agnostic (taxonomy-gap metadata — no candidate_id, no consent).
    cur_queue_default_limit: int = Field(default=200, ge=1)   # default + max rows returned
    cur_min_term_len: int = Field(default=2, ge=1)            # skip single-char noise
    cur_max_term_len: int = Field(default=64, ge=1)           # drop overlong junk

    # --- Candidate auth + DPDP portal (PI-6, S6.4) ----------------------------
    # First-party candidate auth (minted access key, mirrors ledger_api_key_bytes)
    # + retention POSTURE surfaced by the portal. These day-counts parametrize the
    # `retained_until` the portal shows; they do NOT enforce deletion — the
    # mechanical retention sweep is PI-8. Illustrative windows.
    candidate_access_key_bytes: int = Field(default=32, ge=16)
    ret_resume_days: int = Field(default=1095, ge=1)            # 3y
    ret_interview_record_days: int = Field(default=1825, ge=1)  # 5y
    ret_coding_round_days: int = Field(default=1825, ge=1)      # 5y
    ret_observed_offer_days: int = Field(default=1825, ge=1)    # 5y
    ret_profile_source_days: int = Field(default=1095, ge=1)    # 3y
    ret_audit_log_days: int = Field(default=2555, ge=1)         # 7y — longest

    # --- Identity verification (PI-7, S7.1) -----------------------------------
    # Deterministic, offline: OTP mechanics + how long an outcome stays fresh.
    # verif_otp_debug_echo is DOUBLE-GUARDED at the route: the code is echoed
    # only when env == "local" AND this is true. It exists so the sprint smoke
    # can drive the two-step flow over plain HTTP; production cannot echo.
    verif_otp_length: int = Field(default=6, ge=4, le=10)
    verif_otp_ttl_minutes: int = Field(default=10, ge=1)
    verif_otp_max_attempts: int = Field(default=5, ge=1)
    verif_otp_resend_cooldown_seconds: int = Field(default=60, ge=0)
    verif_outcome_ttl_days: int = Field(default=365, ge=1)
    verif_otp_debug_echo: bool = False
    ret_verification_days: int = Field(default=1095, ge=1)  # 3y, posture only

    # --- Document forensics (PI-7, S7.2) --------------------------------------
    # Deterministic and offline. The document itself is never stored; these
    # bound what will be parsed before anything is decoded.
    doc_max_b64_chars: int = Field(default=8_000_000, ge=1024)   # ~6MB decoded
    doc_max_pages: int = Field(default=20, ge=1)
    doc_metadata_skew_days: int = Field(default=1, ge=0)
    # Higher than xf_overlap_months_min on purpose: a three-month overlap is a
    # notice period, not a second job.
    moonlight_min_overlap_months: int = Field(default=12, ge=1)

    # --- AI interviews (PI-7, S7.3) -------------------------------------------
    # Band cut-points are knobs (the ai_*/fr_*/rep_* precedent -- a band is a
    # presentation choice over a score). The scorer's OWN internals are module
    # constants in scoring.py, versioned by SCORER_VERSION: a deploy that
    # silently redefined "specific" would make two stored assessments
    # incomparable.
    interview_max_questions: int = Field(default=8, ge=1)
    interview_min_questions: int = Field(default=3, ge=1)
    interview_session_ttl_minutes: int = Field(default=120, ge=1)
    interview_max_audio_b64_chars: int = Field(default=8_000_000, ge=1024)
    interview_max_answer_chars: int = Field(default=20_000, ge=64)
    interview_min_answer_words: int = Field(default=12, ge=1)
    interview_max_words_per_second: float = Field(default=4.0, gt=0.0)
    interview_max_typed_words_per_second: float = Field(default=8.0, gt=0.0)
    interview_llm_max_delta: float = Field(default=0.2, ge=0.0, le=0.5)
    interview_llm_excerpt_chars: int = Field(default=4000, ge=100)
    interview_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    interview_deep_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    interview_solid_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    interview_emerging_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    interview_weight_specificity: float = Field(default=1.0, ge=0.0)
    interview_weight_ownership: float = Field(default=1.0, ge=0.0)
    interview_weight_depth: float = Field(default=1.5, ge=0.0)
    interview_weight_consistency: float = Field(default=1.0, ge=0.0)
    ret_interview_session_days: int = Field(default=1095, ge=1)  # 3y, posture only
    speech_timeout_seconds: int = Field(default=60, ge=1)
    speech_max_retries: int = Field(default=2, ge=0)

    # --- Screening batches (PI-8, S8.4 Phase B) -------------------------------
    # Registration is a row insert, so the batch bound is a sanity limit rather
    # than a performance one. The per-call bound is the real cost control: each
    # item is a full nine-node graph run, and there is no worker -- the client
    # drives processing a few items at a time (spec §0.3).
    screening_max_batch_items: int = Field(default=500, ge=1)
    screening_max_items_per_call: int = Field(default=5, ge=1)
    # An item still 'processing' after this reads as pending again, so a batch
    # interrupted by a redeploy heals itself instead of wedging (spec §4.4).
    screening_claim_timeout_seconds: int = Field(default=900, ge=1)
    # Unprocessed item text. Swept since S8.3 Phase B, in CLEAR mode: the row
    # survives (an org's record of what it screened must outlive the text it
    # screened) and only `raw_text` is blanked. This is also what bounds the
    # in-place retry -- past this window a failed item's input is gone.
    ret_batch_item_days: int = Field(default=90, ge=1)

    # --- Retention sweep (PI-8, S8.3 Phase B) ---------------------------------
    # Both are SHORT windows on pseudonymous operational rows. A rate-limit
    # counter holds a salted hash of an email beside one of an IP: that is
    # personal data, not bookkeeping, and it has no value once its window has
    # closed. `login_state` is abandoned login challenges and sessions that
    # expired without a logout -- neither is ever consumed, so without a sweep
    # they live forever.
    ret_rate_limit_days: int = Field(default=7, ge=1)
    ret_login_state_days: int = Field(default=7, ge=1)
    # Bounds ONE invocation per class so the sweep cannot hold locks for
    # minutes on a large table. The report carries truncated=true rather than
    # pretending it finished; the operator (or the cron) simply runs it again.
    sweep_max_rows_per_class: int = Field(default=10_000, ge=1)
    # Flipped to True in S8.3 Phase B, because the job it was waiting for now
    # exists. This is what /portal/me reports as `sweep_active`, so it must
    # never be read from a literal again: the portal would keep telling every
    # data principal that no mechanical purge runs while the cron ran one.
    retention_sweep_enabled: bool = True

    # --- Rate limiting (PI-8, S8.3 Phase A) -----------------------------------
    # ONE limiter, DB-backed, called from the SERVICE layer (spec §3.1). The
    # defaults are the safe ones in both directions: limiting ON, and NO proxy
    # trusted -- X-Forwarded-For is attacker-controlled, so trusting it by
    # default would leave a limiter that looks installed and bounds nothing.
    # Prod REFUSES TO BOOT with rate_limit_enabled=False (app/core/boot.py).
    rate_limit_enabled: bool = True
    #: 0 = ignore X-Forwarded-For entirely and use the socket peer. Set to the
    #: number of proxies in front of the app (Railway: 1).
    rate_limit_trusted_proxy_hops: int = Field(default=0, ge=0)
    # Dual-scoped: per email AND per IP. Per-email alone lets an attacker spray
    # one guess across ten thousand addresses; per-IP alone lets a botnet grind
    # one address. Neither is a bound on its own (spec §2.3).
    rate_limit_login_per_hour_per_email: int = Field(default=20, ge=1)
    rate_limit_login_per_hour_per_ip: int = Field(default=100, ge=1)
    rate_limit_verify_per_hour_per_email: int = Field(default=30, ge=1)
    rate_limit_verify_per_hour_per_ip: int = Field(default=200, ge=1)
    # Spend. 400 calls x screening_max_items_per_call (5) = 2000 items/hour --
    # far above a human driving the UI, a hard ceiling on a runaway client
    # loop. Bounded per CALL is not bounded per CALLER.
    rate_limit_process_per_hour_per_org: int = Field(default=400, ge=1)
    rate_limit_asr_per_hour_per_candidate: int = Field(default=60, ge=1)
    # S8.3 Phase B. NOTE THE NAME: the spec's §10 sketch called this
    # rate_limit_grievance_per_hour_per_candidate, and it is deliberately
    # broader here. The candidate plane gained TWO new authenticated writes,
    # not one, and limiting the grievance while leaving the correction
    # unlimited is precisely the "a rule applied at one entry point and not the
    # other" defect this repo has shipped in S7.1, S7.2, S7.3 and S8.4 Phase B.
    # One rule, one shared budget, named for what it covers.
    rate_limit_request_per_hour_per_candidate: int = Field(default=10, ge=1)

    # --- Cursor pagination (PI-8, S8.4 Phase B) -------------------------------
    page_default_limit: int = Field(default=50, ge=1)
    page_max_limit: int = Field(default=200, ge=1)

    # --- Feature materialization (PI-8, S8.4 Phase B) -------------------------
    # Bound on the admin materialize route when it is called with no explicit
    # candidate list.
    materialize_max_candidates: int = Field(default=1000, ge=1)

    # --- Vector store (ChromaDB) ----------------------------------------------
    # Chroma's PersistentClient can hang (not raise) on some machines; startup
    # gives it this long, then degrades to the in-memory store (grounding is
    # best-effort). Set backend="memory" to skip Chroma entirely.
    vectorstore_backend: Literal["chroma", "memory"] = "chroma"
    vectorstore_init_timeout_seconds: float = 15.0
    chroma_persist_dir: str = "./.chroma"
    chroma_collection: str = "depth-eval-evidence"

    # --- Flywheel (training-data sink) ----------------------------------------
    flywheel_path: str = "./data/flywheel.jsonl"

    # --- Candidates (PI-1) ------------------------------------------------------
    # Salt for contact dedup hashes (email/phone). NOT a secret — it must stay
    # stable across deploys or identity resolution breaks; changing it orphans
    # every stored hash.
    contact_hash_salt: str = "veritas-dedup-v1"
    # SQLAlchemy URL for the candidate store (S1.2). SQLite file locally; the
    # Postgres migration is this one string plus `alembic upgrade head`.
    candidates_db_url: str = "sqlite:///./data/veritas.db"

    # --- Calibration (CONSERVATIVE: false positives are the existential risk) --
    # Flag a claim only when coherence is low AND we are confident enough to act.
    # When confidence is below the defer threshold we NEVER assert — we defer to a
    # human. These are advisory thresholds for an advisory system.
    flag_coherence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    flag_min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    defer_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # --- Fabrication defense (PI-2, S2.1): AI-generated-resume signals ---------
    # ADVISORY bands over stylistic tells. AI-assisted resume writing is common
    # and legitimate; these only pick the band shown to a human reviewer, and
    # LIKELY additionally requires >= 2 independent deterministic tells.
    ai_likely_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    ai_possible_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    ai_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    ai_llm_excerpt_chars: int = 6000

    # --- Fabrication defense (PI-2, S2.2): cross-field forensics ----------------
    # Deterministic date/structure checks over the extracted profile. ADVISORY:
    # findings are observations for a reviewer to probe, never a rejection
    # signal. Month thresholds are lower bounds computed with conservative
    # interval math (year-only dates shrink inward for overlaps).
    xf_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    xf_overlap_months_min: int = 3
    xf_gap_months_min: int = 12
    xf_edu_overlap_months_min: int = 12
    xf_senior_min_months: int = 24
    xf_lead_min_months: int = 48

    # --- Fabrication defense (PI-2, S2.3): resume-farm detection -----------------
    # Deterministic MinHash over contact-masked word shingles, compared across
    # candidates at ingest. ADVISORY: shared resume templates are common and
    # legitimate; matches are reviewer context, never a rejection signal.
    # Changing shingle_words/num_permutations changes the algo id — previously
    # stored fingerprints simply stop participating until re-fingerprinted.
    rf_shingle_words: int = 3
    rf_num_permutations: int = 128
    rf_min_shingles: int = 40
    rf_similar_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    rf_near_dup_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    rf_cluster_candidates_min: int = 3
    rf_max_matches: int = 10

    # --- Fabrication defense (PI-2, S2.4): unified fabrication risk -------------
    # Deterministic fusion of ai_generation + cross_field + resume_farm bands,
    # computed in the calibration stage. ADVISORY: never changes verdicts or
    # depth, never a rejection signal. ELEVATED additionally requires >= 2
    # components at their top band; fusion never asserts on a single subsystem.
    fr_moderate_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    fr_elevated_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    fr_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    fr_weight_ai: float = Field(default=1.0, ge=0.0)
    fr_weight_cross_field: float = Field(default=1.0, ge=0.0)
    fr_weight_farm: float = Field(default=1.0, ge=0.0)

    # --- Evaluation ledger (PI-3, S3.1): schema + DPDP consent model -----------
    # The ledger shares candidates_db_url (one metadata root, one Alembic env).
    # Grants created without an explicit expiry get this TTL — DPDP forbids
    # perpetual consent by construction. Purposes/stages are code constants.
    ledger_consent_default_ttl_days: int = Field(default=365, ge=1)
    # Byte length of generated org API keys (secrets.token_urlsafe). Floor keeps
    # keys high-entropy; the plaintext is returned once and only its hash stored.
    ledger_api_key_bytes: int = Field(default=32, ge=16)

    # --- Cross-company reputation (PI-3, S3.4) --------------------------------
    # Advisory Beta-Binomial aggregation of interview_records + coding_round
    # results, shrunk toward a neutral prior, recency-decayed, per-org
    # reliability weighted. Never auto-rejects; GUARDED (the only negative band)
    # and STRONG both require >= rep_corroboration_orgs distinct orgs.
    rep_prior_mean: float = Field(default=0.5, ge=0.0, le=1.0)
    rep_prior_strength: float = Field(default=4.0, gt=0.0)
    rep_recency_halflife_days: float = Field(default=365.0, gt=0.0)
    rep_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    rep_confidence_k: float = Field(default=4.0, gt=0.0)
    rep_confidence_cap: float = Field(default=0.90, ge=0.0, le=1.0)
    rep_corroboration_orgs: int = Field(default=2, ge=1)
    rep_strong_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    rep_favorable_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    rep_guarded_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    rep_interview_weight: float = Field(default=1.0, ge=0.0)
    rep_coding_weight: float = Field(default=1.0, ge=0.0)

    # --- ML feature store (PI-4, S4.1): feature registry -----------------------
    # Default FeatureView the materializer/smoke resolve (all seed features at
    # their latest version). Feature LOGIC is code-versioned, not config.
    feat_default_view: str = "core_v1"

    # --- ML feature store (PI-4, S4.3): talent search / ranking ---------------
    # Default page size for POST /talent/search when the caller omits `limit`.
    search_default_limit: int = Field(default=50, ge=1)

    # --- Demand side (PI-5, S5.1): job requisition + role-conditioned matching -
    # Advisory role-match ranking over the S4.2 pool. Weights are the default
    # RankingTerm weights; a requisition may override any of them. skill coverage
    # is the dominant term. match never auto-rejects.
    match_default_limit: int = Field(default=25, ge=1)
    match_skill_weight: float = Field(default=3.0, gt=0.0)
    match_years_weight: float = Field(default=1.0, gt=0.0)
    match_degree_weight: float = Field(default=1.0, gt=0.0)
    match_notice_weight: float = Field(default=1.0, gt=0.0)
    match_location_weight: float = Field(default=1.0, gt=0.0)
    match_nice_to_have_fraction: float = Field(default=0.3, ge=0.0, le=1.0)

    # --- Comp intelligence (PI-5, S5.2): advisory static bands + observed offers -
    # A curated static prior (bands.py) blended with consent-gated ledger-observed
    # offers (reputation.py-style shrinkage). Advisory only; no LLM.
    comp_currency_default: str = "INR"
    comp_min_observations: int = Field(default=5, ge=1)   # k-anonymity floor
    comp_recency_halflife_days: float = Field(default=365.0, gt=0.0)
    comp_prior_strength: float = Field(default=8.0, gt=0.0)   # static-prior pseudo-count
    comp_confidence_floor: float = Field(default=0.30, ge=0.0, le=1.0)
    comp_confidence_cap: float = Field(default=0.90, ge=0.0, le=1.0)
    comp_confidence_k: float = Field(default=4.0, gt=0.0)
    comp_mid_years: float = Field(default=2.0, ge=0.0)
    comp_senior_years: float = Field(default=5.0, ge=0.0)
    comp_lead_years: float = Field(default=9.0, ge=0.0)
    comp_benchmark_tolerance: float = Field(default=0.10, ge=0.0)
    comp_bands_path: str | None = None   # optional operator-supplied static table

    # --- DPDP rights (PI-8, S8.3 Phase B) -------------------------------------
    # A correction is a REVIEWED REQUEST, never a self-service edit (spec 0.3):
    # on a fraud screen, a subject write path onto the scored data is an edit
    # box over the evidence. Only full_name is ever auto-applied.
    # The same bound and the same reason as max_outcome_notes_chars (S8.5):
    # free text about a named person, typed into an unbounded Text column.
    max_request_note_chars: int = Field(default=2_000, ge=1)

    # --- Employer dashboard (PI-5, S5.3): read-only composition over jobs/comp/ledger.
    # Max ranked candidates returned per GET /jobs/{id}/board (passed as run_match limit).
    dash_board_top_n: int = Field(default=20, ge=1)

    # --- API hardening ----------------------------------------------------------
    # Input caps so a hostile/buggy client can't OOM the service (FR-11).
    max_resume_chars: int = 200_000
    max_pdf_b64_chars: int = 14_000_000  # ≈ 10 MB PDF once base64-decoded
    # Free text a human types beside a candidate's name, now on BOTH the
    # operator's and the customer's outcome route (S8.5). Unbounded is S7.2's
    # `claim_ref` finding one table over -- that one stored 5031 chars including
    # a salary and a UAN. A paragraph of reviewer reasoning fits; a pasted
    # document does not.
    max_outcome_notes_chars: int = Field(default=2_000, ge=1)
    # Shared-secret admin gate (FR-15). SECRET → env/.env only, never YAML.
    # Empty is NOT "auth disabled" — since S8.1 it is the MOST refusing state:
    # require_api_key 401s everything and verify_launch_config refuses to boot.
    # The default stays empty so a forgotten variable fails loudly, not openly.
    api_auth_key: SecretStr = Field(default=SecretStr(""))

    # --- Auth sessions + login (PI-8, S8.2) -----------------------------------
    # Opaque server-side sessions, NOT JWT (PI-8 decision 0.2): a JWT stays valid
    # after a candidate revokes consent or erases their account, which is a DPDP
    # correctness bug rather than a preference. An opaque row dies with a DELETE.
    session_ttl_minutes: int = Field(default=720, ge=1)
    session_idle_timeout_minutes: int = Field(default=120, ge=0)
    session_token_bytes: int = Field(default=32, ge=16)
    # last_seen_at feeds the idle timeout, but writing it on EVERY request turns
    # each authenticated GET into a row lock plus a WAL entry on the hottest path
    # in the system. The staleness this admits is bounded by this knob and is
    # two orders below the idle window, so it cannot change a timeout decision.
    session_last_seen_write_seconds: int = Field(default=60, ge=0)
    session_cookie_name: str = "dee_session"
    # SameSite=None is REQUIRED, not chosen: the UI is separately hosted, so every
    # request is cross-site and Lax would drop the cookie entirely. None mandates
    # Secure, which mandates HTTPS — so `false` is for localhost only, and prod
    # refuses to boot with it (app/core/boot.py).
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["none", "lax", "strict"] = "none"
    csrf_cookie_name: str = "dee_csrf"
    csrf_token_bytes: int = Field(default=32, ge=16)
    login_otp_length: int = Field(default=6, ge=4, le=10)
    login_otp_ttl_seconds: int = Field(default=600, ge=30)
    login_otp_max_attempts: int = Field(default=5, ge=1)
    login_otp_cooldown_seconds: int = Field(default=60, ge=0)
    # Fail-closed: no origin may call this API cross-site until one is named.
    # NEVER "*" — browsers forbid it with credentials anyway, and relying on that
    # as the guard leaves a defect waiting for someone to silence the error.
    cors_allowed_origins: list[str] = Field(default_factory=list)

    # --- Email seam (PI-8, S8.2) ----------------------------------------------
    # Shaped like llm.py / speech.py. "null" REFUSES (503 email_unavailable) so
    # nothing silently degrades. "capture" is reachable only by explicit config,
    # never by fallback, and prod refuses to boot with it.
    email_provider: Literal["null", "smtp", "capture"] = "null"
    email_from: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = Field(default=587, ge=1, le=65535)
    email_smtp_starttls: bool = True
    email_capture_path: str = ""   # where CaptureEmail writes; the smoke reads it
    email_smtp_user: SecretStr = Field(default=SecretStr(""))
    email_smtp_password: SecretStr = Field(default=SecretStr(""))

    # --- Service --------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    env: Literal["local", "staging", "prod"] = "local"
    # Run `alembic upgrade head` at startup (PI-8 blocker 1). This exists for the
    # operator who migrates as a separate deploy step -- NOT as a bypass: a False
    # boot against an empty DB fails loudly at the first query.
    db_migrate_on_boot: bool = True

    @field_validator("log_level")
    @classmethod
    def _upper_level(cls, v: str) -> str:
        return v.upper()

    # --- Convenience ----------------------------------------------------------
    @property
    def has_openrouter_key(self) -> bool:
        return bool(self.openrouter_api_key.get_secret_value())

    @property
    def has_github_token(self) -> bool:
        return bool(self.github_token.get_secret_value())

    def model_for_tier(
        self,
        tier: Literal["reasoning", "reasoning_hard", "parsing", "bulk", "scoring"],
    ) -> str:
        """Resolve a logical tier to a concrete, config-driven model id."""
        return {
            "reasoning": self.model_reasoning,
            "reasoning_hard": self.model_reasoning_hard,
            "parsing": self.model_fast,
            "bulk": self.model_bulk,
            # S7.3 interview scoring. Advisory, human-reviewed, and capped to a
            # +/- delta over the deterministic rubric, so the value tier is right.
            "scoring": self.model_scoring,
        }[tier]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call this everywhere instead of instantiating."""
    return Settings()
