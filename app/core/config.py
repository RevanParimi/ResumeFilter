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
    model_reasoning: str = "qwen/qwen3.7-max"
    model_reasoning_hard: str = "qwen/qwen3.7-max"
    model_fast: str = "qwen/qwen3.6-flash"
    model_bulk: str = "qwen/qwen3.6-35b-a3b"
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 60.0
    # SDK-level retries with backoff; provider blips degrade to rules, not 500s.
    llm_max_retries: int = 2

    # --- GitHub (provenance) --------------------------------------------------
    github_token: SecretStr = Field(default=SecretStr(""))
    github_api_base: str = "https://api.github.com"

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

    # --- Report store (durable advisory reports + human outcomes) --------------
    report_db_path: str = "./data/reports.db"

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
    ledger_consent_default_ttl_days: int = 365

    # --- API hardening ----------------------------------------------------------
    # Input caps so a hostile/buggy client can't OOM the service (FR-11).
    max_resume_chars: int = 200_000
    max_pdf_b64_chars: int = 14_000_000  # ≈ 10 MB PDF once base64-decoded
    # Optional shared-secret gate (FR-15). SECRET → env/.env only, never YAML.
    # Empty (default) = auth disabled (local/dev). /healthz and / stay open.
    api_auth_key: SecretStr = Field(default=SecretStr(""))

    # --- Service --------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    env: Literal["local", "staging", "prod"] = "local"

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
        self, tier: Literal["reasoning", "reasoning_hard", "parsing", "bulk"]
    ) -> str:
        """Resolve a logical tier to a concrete, config-driven model id."""
        return {
            "reasoning": self.model_reasoning,
            "reasoning_hard": self.model_reasoning_hard,
            "parsing": self.model_fast,
            "bulk": self.model_bulk,
        }[tier]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call this everywhere instead of instantiating."""
    return Settings()
