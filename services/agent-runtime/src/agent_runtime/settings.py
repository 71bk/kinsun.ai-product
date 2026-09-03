import os
from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_RUNTIME_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
# Shared RAG settings live in the repository-root .env used by Core and ingestion.
REPOSITORY_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    MODEL_PROVIDER: str = "mock"
    MAX_AGENT_DECISIONS: int = 3
    MAX_TOOL_ROUNDS: int = 2
    MAX_TOTAL_TOOLS: int = 5
    MAX_REWRITE: int = 1
    DEFAULT_LANGUAGE: str = "zh-TW"
    API_VERSION: str = "1.0.0"
    AGENT_VERSION: str = "0.0.1"
    CORE_API_BASE_URL: AnyHttpUrl | None = None
    CORE_API_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)
    SERVICE_IDENTITY_ENABLED: bool = False
    SERVICE_IDENTITY_HMAC_SECRET: SecretStr | None = None
    SERVICE_IDENTITY_ISSUER: str = Field(default="kinsun-local", min_length=1, max_length=80)
    SERVICE_IDENTITY_TTL_SECONDS: int = Field(default=30, ge=1, le=60)
    # Durable replay protection. Required in production: a process-local store
    # cannot stop the same signed request being accepted by a second replica.
    SERVICE_IDENTITY_REPLAY_DATABASE_URL: SecretStr | None = None
    SERVICE_IDENTITY_REPLAY_STATEMENT_TIMEOUT_MS: int = Field(default=5_000, ge=500, le=30_000)
    RAG_MODE: str = "disabled"
    RAG_SEARCH_BACKEND: str = "postgresql"
    RAG_ALLOW_NEEDS_REVIEW_CITATIONS: bool = False
    RAG_STAGING_ALLOW_ALL_AUDIENCES: bool = False
    # Immutable runtime policy path and independently pinned digest must move together.
    RAG_SOURCE_FAMILY_POLICY_PATH: str | None = None
    RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256: str | None = None
    RAG_EMBEDDING_CONFIG_PATH: str = "config/rag/embedding-google.yaml"
    RAG_QUERY_EMBEDDING_CONFIG_PATH: str | None = "config/rag/embedding-google.yaml"
    RAG_OPENSEARCH_INDEX_CONFIG_PATH: str = "config/rag/opensearch-index-v1.json"
    RAG_HYBRID_NATURAL_CONFIG_PATH: str = "config/rag/hybrid-natural-language.json"
    RAG_HYBRID_LEGAL_CONFIG_PATH: str = "config/rag/hybrid-legal.json"
    RAG_DATABASE_URL: SecretStr | None = None
    RAG_POSTGRES_RELEASE_ID: str | None = None
    RAG_POSTGRES_EMBEDDING_PROFILE_ID: str | None = None
    RAG_POSTGRES_STATEMENT_TIMEOUT_MS: int = Field(default=10_000, ge=1_000, le=60_000)
    RAG_POSTGRES_POOL_MIN_SIZE: int = Field(default=1, ge=1, le=5)
    RAG_POSTGRES_POOL_MAX_SIZE: int = Field(default=5, ge=1, le=10)
    RAG_OPENSEARCH_SEARCH_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0.0, le=30.0)
    RAG_OPENSEARCH_MAX_CONCURRENCY: int = Field(default=4, ge=1, le=16)
    AWS_REGION: str | None = None
    BEDROCK_EMBEDDING_MODEL_ID: str | None = None
    BEDROCK_EMBEDDING_DIMENSION: int = 1024
    GEMINI_EMBEDDING_MODEL_ID: str | None = None
    GEMINI_EMBEDDING_DIMENSION: int = 1024
    GEMINI_EMBEDDING_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0.0, le=120.0)
    # No default: choosing a generation model is an owner/ADR decision, and a
    # silent fallback would make an unapproved model look sanctioned.
    BEDROCK_TEXT_MODEL_ID: str | None = None
    BEDROCK_TEXT_MAX_TOKENS: int = Field(default=512, gt=0, le=4096)
    BEDROCK_TEXT_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=1.0)
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL_ID: str | None = None
    GEMINI_MAX_TOKENS: int = Field(default=512, gt=0, le=4096)
    GEMINI_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=1.0)
    GEMINI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0.0, le=120.0)
    OPENAI_COMPATIBLE_BASE_URL: AnyHttpUrl | None = None
    OPENAI_COMPATIBLE_API_KEY: SecretStr | None = None
    OPENAI_COMPATIBLE_MODEL_ID: str | None = None
    OPENAI_COMPATIBLE_MAX_TOKENS: int = Field(default=512, gt=0, le=4096)
    OPENAI_COMPATIBLE_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=1.0)
    OPENAI_COMPATIBLE_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0.0, le=120.0)
    OPENSEARCH_HOST: str | None = None
    OPENSEARCH_INDEX: str | None = None
    OPENSEARCH_ALIAS: str | None = None

    model_config = SettingsConfigDict(
        # Both absolute so loading never depends on the working directory.
        # Later files win, so a service-local .env still overrides the shared one.
        env_file=(REPOSITORY_ENV_FILE, AGENT_RUNTIME_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    if os.getenv("APP_ENV", "").casefold() == "test":
        return Settings(_env_file=None)
    return Settings()
