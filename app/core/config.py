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

    # --- Calibration (CONSERVATIVE: false positives are the existential risk) --
    # Flag a claim only when coherence is low AND we are confident enough to act.
    # When confidence is below the defer threshold we NEVER assert — we defer to a
    # human. These are advisory thresholds for an advisory system.
    flag_coherence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    flag_min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    defer_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

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
