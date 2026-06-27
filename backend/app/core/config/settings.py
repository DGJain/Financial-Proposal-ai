"""Application settings.

Single, validated source of runtime configuration. The platform is **air-gapped
and internal-only** (PROJECT_CONTEXT.md · ARCHITECTURE_SUMMARY.md "Security
Constraints"); this module makes that constraint explicit and fail-closed: no
configuration path may enable external egress, and the model provider defaults to
the internal SLM in production.

Values are loaded from environment variables / a local `.env` file only — never
fetched from a remote configuration service.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Governs which model provider is permitted."""

    LOCAL = "local"
    PROTOTYPE = "prototype"
    PRODUCTION = "production"


class ModelProvider(StrEnum):
    """Enterprise-model provider behind the LLM Gateway.

    `CLAUDE` is permitted only outside production (prototype/eval); production
    must use the internal `SLM` so no request leaves the enterprise boundary.
    """

    CLAUDE = "claude"
    SLM = "slm"


def _nested_config(env_prefix: str) -> SettingsConfigDict:
    """Config for a nested settings group.

    Each group is instantiated via `default_factory`, so it must load the
    `.env` file itself — only the root `Settings` env_file config would
    otherwise apply, leaving prefixed fields like `dsn` unset (see `.env.example`).
    """
    return SettingsConfigDict(
        env_prefix=env_prefix,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class PostgresSettings(BaseSettings):
    model_config = _nested_config("POSTGRES_")

    dsn: PostgresDsn
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


class RedisSettings(BaseSettings):
    model_config = _nested_config("REDIS_")

    dsn: RedisDsn
    retrieval_cache_ttl_seconds: int = 300  # per-repo retrieval cache (ui-design §8)


class ChromaSettings(BaseSettings):
    model_config = _nested_config("CHROMA_")

    host: str = "localhost"
    port: int = 8000
    # Canonical collection names — ARCHITECTURE_SUMMARY.md is source of truth.
    collection_financial: str = "repo_financial"
    collection_proposals: str = "repo_proposals"
    collection_templates: str = "repo_templates"


class ObjectStorageSettings(BaseSettings):
    """S3-compatible (MinIO in-cluster). Endpoint must be an internal address."""

    model_config = _nested_config("OBJECT_STORAGE_")

    endpoint_url: str = "http://minio:9000"
    # Optional so local-dev (in-memory object store) needs no secrets; required
    # outside local, enforced by Settings._enforce_air_gap.
    access_key: str = ""
    secret_key: str = ""
    bucket_raw: str = "raw-originals"
    bucket_versioned: str = "versioned-originals"
    region: str = "us-east-1"


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_")

    provider: ModelProvider = ModelProvider.SLM
    # Internal serving endpoints (in-cluster, no egress).
    embedding_endpoint: str = "http://embedding-server.ai:8080"
    embedding_model_version: str = "local-embed-v1"  # first-class: pins collection comparability
    slm_endpoint: str = "http://slm-serving.ai:8080"
    # Prototype-only Claude access (ignored in production).
    claude_model: str = "claude-opus-4-8"
    claude_api_key: str | None = None
    request_timeout_seconds: int = 300  # generous: CPU-only cold model load + a section
    # DEV-ONLY escape hatch: in ``local`` substitute the real Claude gateway for the
    # EchoGateway so demos produce real prose. Requires ``claude_api_key`` and makes
    # an outbound call — never enable inside the air-gapped enterprise boundary;
    # production stays hard-locked to the internal SLM by ``_enforce_air_gap``.
    dev_use_claude: bool = False
    # DEV escape hatch (air-gap-safe): in ``local`` substitute a local Ollama model
    # for the EchoGateway. No API key, no egress (localhost only) — the realistic
    # stand-in for the production internal SLM. Preferred over ``dev_use_claude``.
    dev_use_local: bool = False
    local_endpoint: str = "http://localhost:11434"
    local_model: str = "qwen2.5:3b"
    # Cap per-section output for the local model so CPU-only generation stays fast
    # (the pipeline default is 1024). Keep the model resident between runs.
    local_max_output_tokens: int = 512
    local_keep_alive: str = "10m"


class Settings(BaseSettings):
    """Root settings aggregate."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment = Environment.LOCAL
    api_title: str = "Financial Proposal Platform API"
    api_version: str = "0.1.0"

    # Hard air-gap switch. Must remain True; retrieval/generation refuse to reach
    # any external network. Present as an explicit, auditable flag.
    air_gapped: bool = True

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)  # type: ignore[arg-type]
    redis: RedisSettings = Field(default_factory=RedisSettings)  # type: ignore[arg-type]
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    object_storage: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)  # type: ignore[arg-type]
    ai: AISettings = Field(default_factory=AISettings)

    @model_validator(mode="after")
    def _enforce_air_gap(self) -> Settings:
        """Fail-closed invariants for the air-gapped deployment."""
        if not self.air_gapped:
            raise ValueError(
                "air_gapped must be True — the platform must operate within the "
                "enterprise boundary (no external egress)."
            )
        if self.environment is Environment.PRODUCTION and self.ai.provider is not ModelProvider.SLM:
            raise ValueError(
                "Production must use the internal SLM provider; external model "
                "providers (e.g. Claude) are prohibited outside the enterprise boundary."
            )
        if self.environment is not Environment.LOCAL and not (
            self.object_storage.access_key and self.object_storage.secret_key
        ):
            raise ValueError(
                "Object-storage credentials are required outside local "
                "(OBJECT_STORAGE_ACCESS_KEY / OBJECT_STORAGE_SECRET_KEY)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (one validated instance per process)."""
    return Settings()
