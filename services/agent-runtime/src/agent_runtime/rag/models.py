from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"
ID_REGEX = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
LANGUAGE_REGEX = r"^[a-z]{2,3}(?:-[A-Za-z]{2})?$"

QueryProfile = Literal["natural_language", "legal"]
RetrievalStatus = Literal["SUCCESS", "NO_DATA", "FAILED"]
EmbeddingProviderName = Literal["bedrock", "google"]
SearchBackendName = Literal["opensearch", "postgresql"]


class RagBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, strict=True)


class RetrievalRequestV1(RagBaseModel):
    """Wire model matching the staging retrieval request contract."""

    schema_version: Literal["1.0.0"]
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    query: str = Field(min_length=1, max_length=2000)
    query_profile: QueryProfile
    top_k: Literal[5]
    audience: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=120)
    language: str = Field(default="zh-TW", pattern=LANGUAGE_REGEX)

    @field_validator("query")
    @classmethod
    def query_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        return value


class RetrievalRequestV2(RagBaseModel):
    """Wire request for governed V2 retrieval."""

    schema_version: Literal["2.0.0"]
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    query: str = Field(min_length=1, max_length=2000)
    query_profile: QueryProfile
    top_k: Literal[5]
    audience: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=120)
    language: str = Field(default="zh-TW", pattern=LANGUAGE_REGEX)

    @field_validator("query")
    @classmethod
    def query_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        return value


class RetrievalResultV1(RagBaseModel):
    """A chunk plus the citation fields the agent must preserve in its answer."""

    chunk_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=50000)
    score: float = Field(allow_inf_nan=False)
    document_name: str = Field(min_length=1, max_length=512)
    section: str = Field(min_length=1, max_length=512)
    # Null for sources that have no pagination, such as an official web page,
    # where source_locator carries the position instead. Both or neither: a
    # half-populated range is a data defect, not a citable location.
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_url: str = Field(min_length=1, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_absolute(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("source_url must be an absolute HTTP(S) URI")
        return value

    @model_validator(mode="after")
    def page_range_must_be_ordered(self) -> RetrievalResultV1:
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must both be set or both be null")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must be greater than or equal to page_start")
        return self


class RetrievalResultV2(RagBaseModel):
    """A governed chunk citation with no internal storage location."""

    chunk_id: str = Field(min_length=1, max_length=256)
    source_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=50000)
    score: float = Field(allow_inf_nan=False)
    artifact_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=512)
    publisher: str | None = Field(max_length=512)
    section: str = Field(min_length=1, max_length=1024)
    physical_page_start: int | None = Field(ge=1)
    physical_page_end: int | None = Field(ge=1)
    printed_page_start: int | None = Field(ge=1)
    printed_page_end: int | None = Field(ge=1)
    source_locator: str = Field(min_length=1, max_length=2048)
    direct_official_source_url: str | None = Field(max_length=4096)
    official_source_page_url: str | None = Field(max_length=4096)
    direct_source_url: str | None = Field(max_length=4096)
    source_page_url: str | None = Field(max_length=4096)
    is_official_source: bool
    source_version: str | None = Field(max_length=512)
    source_version_date: str | None = Field(max_length=512)
    version_published_at: str | None = Field(max_length=512)
    source_page_updated_at: str | None = Field(max_length=512)
    published_at: str | None = Field(max_length=512)
    last_verified_at: str | None = Field(max_length=512)
    review_status: Literal["needs_review", "verified"]
    production_approved: bool

    @property
    def document_name(self) -> str:
        """Compatibility display name for the shared citation renderer."""

        return self.title

    @property
    def page_start(self) -> int | None:
        return self.printed_page_start or self.physical_page_start

    @property
    def page_end(self) -> int | None:
        return self.printed_page_end or self.physical_page_end

    @property
    def source_url(self) -> str:
        value = (
            self.official_source_page_url or self.direct_official_source_url
            if self.is_official_source
            else self.source_page_url or self.direct_source_url
        )
        if value is None:
            raise ValueError("governed citation has no public source URL")
        return value

    @field_validator(
        "direct_official_source_url",
        "official_source_page_url",
        "direct_source_url",
        "source_page_url",
    )
    @classmethod
    def public_urls_must_be_absolute(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.hostname is None
                or any(character.isspace() for character in value)
            ):
                raise ValueError("citation URL must be an absolute HTTP(S) URI")
        return value

    @field_validator(
        "chunk_id",
        "source_id",
        "text",
        "artifact_version",
        "title",
        "section",
        "source_locator",
    )
    @classmethod
    def required_text_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required citation text must contain non-whitespace text")
        return value

    @field_validator(
        "publisher",
        "source_version",
        "source_version_date",
        "version_published_at",
        "source_page_updated_at",
        "published_at",
        "last_verified_at",
    )
    @classmethod
    def optional_evidence_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional citation evidence must be null or non-blank")
        return value

    @model_validator(mode="after")
    def governed_citation_must_be_complete(self) -> RetrievalResultV2:
        _validate_page_pair(
            self.physical_page_start,
            self.physical_page_end,
            "physical_page",
        )
        _validate_page_pair(
            self.printed_page_start,
            self.printed_page_end,
            "printed_page",
        )
        if self.direct_source_url is None and self.source_page_url is None:
            raise ValueError("a public direct or source-page URL is required")
        if self.is_official_source:
            if self.direct_official_source_url is None and self.official_source_page_url is None:
                raise ValueError("an official source requires an official public URL")
        elif (
            self.direct_official_source_url is not None or self.official_source_page_url is not None
        ):
            raise ValueError("non-official evidence cannot populate official URL fields")
        if self.production_approved and self.review_status != "verified":
            raise ValueError("production approval requires verified review status")
        return self


class RetrievalResponseV1(RagBaseModel):
    """Wire model matching the staging retrieval response contract."""

    schema_version: Literal["1.0.0"]
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    status: RetrievalStatus
    fallback_message: str | None = Field(max_length=1000)
    results: list[RetrievalResultV1] = Field(max_length=5)

    @model_validator(mode="after")
    def status_and_results_must_be_consistent(self) -> RetrievalResponseV1:
        if self.status == "SUCCESS":
            if self.fallback_message is not None:
                raise ValueError("successful retrieval cannot include a fallback message")
            if not 3 <= len(self.results) <= 5:
                raise ValueError("successful retrieval must provide three to five chunks")
        else:
            if not self.fallback_message or not self.fallback_message.strip():
                raise ValueError("non-success retrieval must include an explicit fallback message")
            if self.results:
                raise ValueError("fallback retrieval must not expose partial results to the agent")
        return self


class RetrievalResponseV2(RagBaseModel):
    """Governed retrieval response that fails closed without partial results."""

    schema_version: Literal["2.0.0"]
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    status: RetrievalStatus
    fallback_message: str | None = Field(max_length=1000)
    results: list[RetrievalResultV2] = Field(max_length=5)

    @model_validator(mode="after")
    def status_and_results_must_be_consistent(self) -> RetrievalResponseV2:
        if self.status == "SUCCESS":
            if self.fallback_message is not None:
                raise ValueError("successful retrieval cannot include a fallback message")
            if not 3 <= len(self.results) <= 5:
                raise ValueError("successful retrieval must provide three to five chunks")
        else:
            if not self.fallback_message or not self.fallback_message.strip():
                raise ValueError("non-success retrieval must include an explicit fallback message")
            if self.results:
                raise ValueError("fallback retrieval must not expose partial results to the agent")
        return self


class QueryEmbeddingSettings(RagBaseModel):
    """Provider-neutral query embedding settings without credentials."""

    provider: EmbeddingProviderName
    model_id: str = Field(min_length=1)
    region: str | None = Field(default=None, min_length=1)
    dimension: Literal[1024]

    @model_validator(mode="after")
    def bedrock_requires_region(self) -> QueryEmbeddingSettings:
        if self.provider == "bedrock" and self.region is None:
            raise ValueError("Bedrock embedding requires an AWS region")
        return self


class HybridProfileSettings(RagBaseModel):
    """Runtime subset of a configured OpenSearch search pipeline."""

    profile: QueryProfile
    search_pipeline: str = Field(min_length=1)
    bm25_weight: float = Field(ge=0.0, le=1.0)
    vector_weight: float = Field(ge=0.0, le=1.0)
    vector_min_score: float = Field(gt=0.0, le=1.0)
    top_k: Literal[5]
    agent_chunk_min: Literal[3]
    agent_chunk_max: Literal[5]

    @model_validator(mode="after")
    def weights_must_be_normalized(self) -> HybridProfileSettings:
        if abs((self.bm25_weight + self.vector_weight) - 1.0) > 1e-9:
            raise ValueError("hybrid weights must sum to 1")
        return self

    @classmethod
    def from_config(cls, values: Mapping[str, object]) -> HybridProfileSettings:
        """Select the runtime-safe subset from the full pipeline configuration file."""

        return cls.model_validate(
            {
                "profile": values.get("profile"),
                "search_pipeline": values.get("search_pipeline"),
                "bm25_weight": values.get("bm25_weight"),
                "vector_weight": values.get("vector_weight"),
                "vector_min_score": values.get("vector_min_score"),
                "top_k": values.get("top_k"),
                "agent_chunk_min": values.get("agent_chunk_min"),
                "agent_chunk_max": values.get("agent_chunk_max"),
            }
        )


class HybridSearchSettings(RagBaseModel):
    """Both approved search profiles and an optional legacy OpenSearch alias."""

    index_alias: str | None = Field(default=None, min_length=1)
    natural_language: HybridProfileSettings
    legal: HybridProfileSettings

    @model_validator(mode="after")
    def profile_slots_must_match(self) -> HybridSearchSettings:
        if self.natural_language.profile != "natural_language":
            raise ValueError("natural_language slot contains the wrong profile")
        if self.legal.profile != "legal":
            raise ValueError("legal slot contains the wrong profile")
        return self

    def for_profile(self, profile: QueryProfile) -> HybridProfileSettings:
        if profile == "legal":
            return self.legal
        return self.natural_language


class OpenSearchConnectionSettings(RagBaseModel):
    """AWS OpenSearch connection values resolved from configuration/environment."""

    host: str = Field(min_length=1)
    region: str = Field(min_length=1)
    index_name: str = Field(min_length=1)
    index_alias: str = Field(min_length=1)
    mode: Literal["staging"]

    @field_validator("index_name", "index_alias")
    @classmethod
    def index_targets_must_be_explicitly_staging(cls, value: str) -> str:
        normalized = value.casefold()
        if "staging" not in normalized or "production" in normalized or "prod" in normalized:
            raise ValueError("OpenSearch index and alias must be explicitly staging")
        return value


class PostgresSearchSettings(RagBaseModel):
    """Exact staging projection and bounded PostgreSQL connection settings."""

    database_url: SecretStr
    release_id: str = Field(min_length=1, max_length=160, pattern=ID_REGEX)
    embedding_profile_id: str = Field(min_length=1, max_length=160, pattern=ID_REGEX)
    statement_timeout_ms: int = Field(default=10_000, ge=1_000, le=60_000)
    pool_min_size: int = Field(default=1, ge=1, le=5)
    pool_max_size: int = Field(default=5, ge=1, le=10)
    mode: Literal["staging"]

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_async_postgresql(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("RAG_DATABASE_URL must use PostgreSQL with asyncpg")
        parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
        if (
            parsed.hostname is None
            or parsed.username is None
            or not parsed.path.strip("/")
            or parsed.fragment
        ):
            raise ValueError("RAG_DATABASE_URL is incomplete")
        return value

    @model_validator(mode="after")
    def pool_bounds_must_be_ordered(self) -> PostgresSearchSettings:
        if self.pool_max_size < self.pool_min_size:
            raise ValueError("PostgreSQL pool_max_size must be at least pool_min_size")
        return self


class RagRuntimeSettings(RagBaseModel):
    """Complete online retrieval settings with no provider values baked into code."""

    search_backend: SearchBackendName = "opensearch"
    embedding: QueryEmbeddingSettings
    opensearch: OpenSearchConnectionSettings | None = None
    postgres: PostgresSearchSettings | None = None
    hybrid: HybridSearchSettings
    allow_needs_review_citations: bool = False
    allow_all_audiences: bool = False

    @model_validator(mode="after")
    def exactly_one_search_backend_must_be_configured(self) -> RagRuntimeSettings:
        if self.search_backend == "opensearch":
            if self.opensearch is None or self.postgres is not None:
                raise ValueError("OpenSearch backend requires only OpenSearch settings")
            if self.hybrid.index_alias != self.opensearch.index_alias:
                raise ValueError("OpenSearch alias must match the hybrid settings")
        elif self.postgres is None or self.opensearch is not None:
            raise ValueError("PostgreSQL backend requires only PostgreSQL settings")
        backend_mode = self.postgres.mode if self.postgres is not None else self.opensearch.mode
        if self.allow_all_audiences and backend_mode != "staging":
            raise ValueError("all-audience retrieval is allowed only in staging")
        return self

    @classmethod
    def from_config_files(
        cls,
        *,
        embedding_config_path: str | Path,
        index_config_path: str | Path,
        natural_profile_path: str | Path,
        legal_profile_path: str | Path,
        environ: Mapping[str, str] | None = None,
        database_url: SecretStr | str | None = None,
    ) -> RagRuntimeSettings:
        """Load explicit paths and let named environment values override file values."""

        env = os.environ if environ is None else environ
        embedding_document = _read_yaml_mapping(embedding_config_path)
        natural_document = _read_json_mapping(natural_profile_path)
        legal_document = _read_json_mapping(legal_profile_path)

        embedding_values = _required_mapping(embedding_document, "embedding")
        search_backend = _as_nonempty_str(
            env.get("RAG_SEARCH_BACKEND", "opensearch"),
            "RAG_SEARCH_BACKEND",
        ).casefold()
        if search_backend not in {"opensearch", "postgresql"}:
            raise ValueError("RAG_SEARCH_BACKEND must be opensearch or postgresql")
        provider = _as_nonempty_str(
            embedding_values.get("provider"), "embedding provider"
        ).casefold()
        model_id = _resolve_config_value(embedding_values, "model_id", "model_id_env", env)
        region = (
            _resolve_config_value(embedding_values, "region", "region_env", env)
            if provider == "bedrock"
            else None
        )
        dimension = _resolve_config_value(
            embedding_values,
            "dimension",
            "dimension_env",
            env,
        )
        allow_needs_review_citations = _as_bool(
            env.get("RAG_ALLOW_NEEDS_REVIEW_CITATIONS", "false"),
            "RAG_ALLOW_NEEDS_REVIEW_CITATIONS",
        )
        allow_all_audiences = _as_bool(
            env.get("RAG_STAGING_ALLOW_ALL_AUDIENCES", "false"),
            "RAG_STAGING_ALLOW_ALL_AUDIENCES",
        )

        embedding = QueryEmbeddingSettings(
            provider=provider,
            model_id=_as_nonempty_str(model_id, "embedding model ID"),
            region=_as_nonempty_str(region, "AWS region") if region is not None else None,
            dimension=_as_int(dimension, "embedding dimension"),
        )
        natural = HybridProfileSettings.from_config(natural_document)
        legal = HybridProfileSettings.from_config(legal_document)
        opensearch: OpenSearchConnectionSettings | None = None
        postgres: PostgresSearchSettings | None = None
        index_alias: str | None = None
        if search_backend == "opensearch":
            index_document = _read_json_mapping(index_config_path)
            index_values = _required_mapping(index_document, "index")
            index_name = _resolve_config_value(index_values, "name", "name_env", env)
            index_alias = _resolve_config_value(index_values, "alias", "alias_env", env)
            opensearch = OpenSearchConnectionSettings(
                host=_required_env(env, "OPENSEARCH_HOST"),
                region=_required_env(env, "AWS_REGION"),
                index_name=_as_nonempty_str(index_name, "OpenSearch index name"),
                index_alias=_as_nonempty_str(index_alias, "OpenSearch index alias"),
                mode=env.get("RAG_MODE") or index_document.get("mode"),
            )
            index_alias = opensearch.index_alias
        else:
            raw_database_url = (
                database_url.get_secret_value()
                if isinstance(database_url, SecretStr)
                else database_url
            )
            if raw_database_url is None:
                raw_database_url = env.get("RAG_DATABASE_URL")
            postgres = PostgresSearchSettings(
                database_url=SecretStr(_as_nonempty_str(raw_database_url, "RAG_DATABASE_URL")),
                release_id=_required_env(env, "RAG_POSTGRES_RELEASE_ID"),
                embedding_profile_id=_required_env(
                    env,
                    "RAG_POSTGRES_EMBEDDING_PROFILE_ID",
                ),
                statement_timeout_ms=_as_int(
                    env.get("RAG_POSTGRES_STATEMENT_TIMEOUT_MS", "10000"),
                    "RAG_POSTGRES_STATEMENT_TIMEOUT_MS",
                ),
                pool_min_size=_as_int(
                    env.get("RAG_POSTGRES_POOL_MIN_SIZE", "1"),
                    "RAG_POSTGRES_POOL_MIN_SIZE",
                ),
                pool_max_size=_as_int(
                    env.get("RAG_POSTGRES_POOL_MAX_SIZE", "5"),
                    "RAG_POSTGRES_POOL_MAX_SIZE",
                ),
                mode=_required_env(env, "RAG_MODE"),
            )
        return cls(
            search_backend=search_backend,
            embedding=embedding,
            opensearch=opensearch,
            postgres=postgres,
            hybrid=HybridSearchSettings(
                index_alias=index_alias,
                natural_language=natural,
                legal=legal,
            ),
            allow_needs_review_citations=allow_needs_review_citations,
            allow_all_audiences=allow_all_audiences,
        )


class HybridSearchPlan(RagBaseModel):
    """Provider-neutral bounded search request; never carries executable DSL."""

    query: str = Field(min_length=1, max_length=2000)
    query_vector: list[float] = Field(min_length=1)
    profile: QueryProfile
    top_k: Literal[5]
    audience: str | None = Field(default=None, min_length=1, max_length=64)
    purpose: str | None = Field(default=None, min_length=1, max_length=64)
    governed_citations: bool
    allow_needs_review: bool
    allow_all_audiences: bool = False
    bm25_weight: float
    vector_weight: float
    min_score: float = Field(gt=0.0, le=1.0)


def _read_yaml_mapping(path: str | Path) -> Mapping[str, object]:
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load RAG YAML configuration: {path}") from exc
    if not isinstance(document, Mapping):
        raise ValueError(f"RAG YAML configuration must contain an object: {path}")
    return document


def _read_json_mapping(path: str | Path) -> Mapping[str, object]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load RAG JSON configuration: {path}") from exc
    if not isinstance(document, Mapping):
        raise ValueError(f"RAG JSON configuration must contain an object: {path}")
    return document


def _required_mapping(document: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"RAG configuration is missing object: {key}")
    return value


def _resolve_config_value(
    values: Mapping[str, object],
    value_key: str,
    env_key_key: str,
    environ: Mapping[str, str],
) -> object:
    env_key = values.get(env_key_key)
    if isinstance(env_key, str):
        env_value = environ.get(env_key)
        if env_value is not None and env_value.strip():
            return env_value.strip()
    value = values.get(value_key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"RAG configuration value is missing: {value_key}")
    return value


def _required_env(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if value is None or not value.strip():
        raise ValueError(f"required RAG environment value is missing: {key}")
    return value.strip()


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc


def _as_nonempty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _as_bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError(f"{label} must be true or false")


def _validate_page_pair(start: int | None, end: int | None, label: str) -> None:
    if (start is None) != (end is None):
        raise ValueError(f"{label}_start and {label}_end must both be set or both be null")
    if start is not None and end is not None and end < start:
        raise ValueError(f"{label}_end must be greater than or equal to {label}_start")
