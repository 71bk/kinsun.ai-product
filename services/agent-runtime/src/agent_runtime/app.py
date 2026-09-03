import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agent_runtime.api.agent_runs import router as agent_runs_router
from agent_runtime.api.error_handlers import register_exception_handlers
from agent_runtime.api.health import router as health_router
from agent_runtime.api.rag_retrievals import router as rag_retrievals_router
from agent_runtime.middleware.correlation import CorrelationIdMiddleware
from agent_runtime.models.bedrock_provider import build_bedrock_model_provider
from agent_runtime.models.gemini_provider import GeminiModelProvider
from agent_runtime.models.mock_provider import MockModelProvider
from agent_runtime.models.openai_compatible_provider import OpenAICompatibleModelProvider
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.orchestrator import AgentOrchestrator
from agent_runtime.rag.models import RagRuntimeSettings
from agent_runtime.rag.retriever import build_retriever, close_retriever
from agent_runtime.rag.runtime_policy import load_source_family_runtime_policy
from agent_runtime.security.replay_store import InMemoryReplayStore, ReplayStore
from agent_runtime.security.replay_store_postgres import (
    PostgresReplayStore,
    build_replay_engine,
)
from agent_runtime.security.service_identity import ServiceCredentialVerifier
from agent_runtime.settings import Settings, get_settings

logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

# Providers that actually reach a governed model. "mock" is deliberately absent:
# it answers from fixed rules, and a deployment doing that while the operator
# believes a model is grounded in the knowledge base is the failure this
# allowlist exists to stop.
PRODUCTION_APPROVED_MODEL_PROVIDERS = frozenset({"bedrock", "gemini", "openai-compatible"})

# RAG_MODE values this service may serve under APP_ENV=production. Empty on
# purpose, not by oversight: "disabled" builds no retriever at all, and
# "staging" binds the retriever to a release whose chunks carry
# production_approved=false. Promoting a corpus is an owner decision plus a
# signed allowlist, so the approved value arrives with that release, not before.
PRODUCTION_APPROVED_RAG_MODES: frozenset[str] = frozenset()


def build_provider() -> ModelProvider:
    settings = get_settings()
    provider_key = settings.MODEL_PROVIDER.strip().casefold().replace("_", "-")
    if provider_key == "mock":
        return MockModelProvider()
    if provider_key == "bedrock":
        # Fail at startup rather than degrade to the mock: a companion that
        # silently answers from rules while the operator believes a real model
        # is grounded in the knowledge base is worse than one that will not start.
        if not settings.AWS_REGION or not settings.BEDROCK_TEXT_MODEL_ID:
            raise ValueError("MODEL_PROVIDER=bedrock requires AWS_REGION and BEDROCK_TEXT_MODEL_ID")
        return build_bedrock_model_provider(
            region=settings.AWS_REGION,
            model_id=settings.BEDROCK_TEXT_MODEL_ID,
            max_tokens=settings.BEDROCK_TEXT_MAX_TOKENS,
            temperature=settings.BEDROCK_TEXT_TEMPERATURE,
        )
    if provider_key == "gemini":
        if not settings.GEMINI_API_KEY or not settings.GEMINI_MODEL_ID:
            raise ValueError("MODEL_PROVIDER=gemini requires GEMINI_API_KEY and GEMINI_MODEL_ID")
        return GeminiModelProvider(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            model_id=settings.GEMINI_MODEL_ID,
            max_tokens=settings.GEMINI_MAX_TOKENS,
            temperature=settings.GEMINI_TEMPERATURE,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        )
    if provider_key == "openai-compatible":
        if not settings.OPENAI_COMPATIBLE_BASE_URL or not settings.OPENAI_COMPATIBLE_MODEL_ID:
            raise ValueError(
                "MODEL_PROVIDER=openai-compatible requires "
                "OPENAI_COMPATIBLE_BASE_URL and OPENAI_COMPATIBLE_MODEL_ID"
            )
        api_key = (
            settings.OPENAI_COMPATIBLE_API_KEY.get_secret_value()
            if settings.OPENAI_COMPATIBLE_API_KEY
            else None
        )
        return OpenAICompatibleModelProvider(
            base_url=str(settings.OPENAI_COMPATIBLE_BASE_URL),
            model_id=settings.OPENAI_COMPATIBLE_MODEL_ID,
            api_key=api_key,
            max_tokens=settings.OPENAI_COMPATIBLE_MAX_TOKENS,
            temperature=settings.OPENAI_COMPATIBLE_TEMPERATURE,
            timeout_seconds=settings.OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
        )
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.MODEL_PROVIDER}")


def build_configured_rag_retriever():
    """Build staging-only adapters, or leave retrieval explicitly unavailable."""

    settings = get_settings()
    if settings.RAG_MODE.casefold() != "staging":
        return None
    try:
        provider_environment = {
            key: str(value)
            for key, value in {
                "AWS_REGION": settings.AWS_REGION,
                "BEDROCK_EMBEDDING_MODEL_ID": settings.BEDROCK_EMBEDDING_MODEL_ID,
                "BEDROCK_EMBEDDING_DIMENSION": settings.BEDROCK_EMBEDDING_DIMENSION,
                "GEMINI_EMBEDDING_MODEL_ID": settings.GEMINI_EMBEDDING_MODEL_ID,
                "GEMINI_EMBEDDING_DIMENSION": settings.GEMINI_EMBEDDING_DIMENSION,
                "OPENSEARCH_HOST": settings.OPENSEARCH_HOST,
                "OPENSEARCH_INDEX": settings.OPENSEARCH_INDEX,
                "OPENSEARCH_ALIAS": settings.OPENSEARCH_ALIAS,
                "RAG_OPENSEARCH_SEARCH_TIMEOUT_SECONDS": (
                    settings.RAG_OPENSEARCH_SEARCH_TIMEOUT_SECONDS
                ),
                "RAG_OPENSEARCH_MAX_CONCURRENCY": settings.RAG_OPENSEARCH_MAX_CONCURRENCY,
                "RAG_MODE": settings.RAG_MODE,
                "RAG_SEARCH_BACKEND": settings.RAG_SEARCH_BACKEND,
                "RAG_ALLOW_NEEDS_REVIEW_CITATIONS": settings.RAG_ALLOW_NEEDS_REVIEW_CITATIONS,
                "RAG_STAGING_ALLOW_ALL_AUDIENCES": (settings.RAG_STAGING_ALLOW_ALL_AUDIENCES),
                "RAG_POSTGRES_RELEASE_ID": settings.RAG_POSTGRES_RELEASE_ID,
                "RAG_POSTGRES_EMBEDDING_PROFILE_ID": (settings.RAG_POSTGRES_EMBEDDING_PROFILE_ID),
                "RAG_POSTGRES_STATEMENT_TIMEOUT_MS": (settings.RAG_POSTGRES_STATEMENT_TIMEOUT_MS),
                "RAG_POSTGRES_POOL_MIN_SIZE": settings.RAG_POSTGRES_POOL_MIN_SIZE,
                "RAG_POSTGRES_POOL_MAX_SIZE": settings.RAG_POSTGRES_POOL_MAX_SIZE,
            }.items()
            if value is not None and str(value).strip()
        }
        rag_settings = RagRuntimeSettings.from_config_files(
            embedding_config_path=_resolve_config_path(
                settings.RAG_QUERY_EMBEDDING_CONFIG_PATH or settings.RAG_EMBEDDING_CONFIG_PATH
            ),
            index_config_path=_resolve_config_path(settings.RAG_OPENSEARCH_INDEX_CONFIG_PATH),
            natural_profile_path=_resolve_config_path(settings.RAG_HYBRID_NATURAL_CONFIG_PATH),
            legal_profile_path=_resolve_config_path(settings.RAG_HYBRID_LEGAL_CONFIG_PATH),
            environ=provider_environment,
            database_url=settings.RAG_DATABASE_URL,
        )
        google_api_key = (
            settings.GEMINI_API_KEY.get_secret_value()
            if rag_settings.embedding.provider == "google" and settings.GEMINI_API_KEY
            else None
        )
        if rag_settings.allow_all_audiences:
            logger.warning("staging_rag_all_audiences_enabled")
        policy_path = settings.RAG_SOURCE_FAMILY_POLICY_PATH
        policy_sha256 = settings.RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256
        if (policy_path is None) != (policy_sha256 is None):
            raise ValueError("source-family runtime policy path and SHA-256 are both required")
        source_family_policy = None
        if policy_path is not None and policy_sha256 is not None:
            if rag_settings.allow_all_audiences:
                raise ValueError(
                    "source-family runtime policy cannot use the legacy audience override"
                )
            source_family_policy = load_source_family_runtime_policy(
                _resolve_config_path(policy_path),
                expected_sha256=policy_sha256,
            )
            logger.info(
                "staging_rag_source_family_policy_loaded",
                extra={
                    "runtime_policy_version": (
                        source_family_policy.document.runtime_policy_version
                    ),
                    "candidate_count": len(source_family_policy.candidate_chunk_ids),
                },
            )
        return build_retriever(
            rag_settings,
            google_api_key=google_api_key,
            google_timeout_seconds=settings.GEMINI_EMBEDDING_TIMEOUT_SECONDS,
            source_family_policy=source_family_policy,
        )
    except Exception as exc:
        # Never include provider messages: they can contain endpoint/account details.
        logger.warning(
            "staging_rag_unavailable",
            extra={"exception_type": type(exc).__name__},
        )
        return None


def _resolve_config_path(configured_path: str) -> Path:
    """Resolve an environment-provided path from cwd or the repository root."""

    path = Path(configured_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate
    return (REPOSITORY_ROOT / path).resolve()


def validate_production_configuration(settings: Settings) -> None:
    """Refuse a production start that would only look like a working runtime.

    Local, test and staging keep every default: they may run the mock provider
    with retrieval switched off, and nothing about those profiles claims
    otherwise. Production is where the same defaults become invisible — the
    service starts, answers, and reports healthy while the replies are synthetic
    and no governed retrieval ever ran. Every violation is collected so one
    failed start shows the operator the whole gap instead of one value per
    restart, and no configured value is echoed back into the message.
    """

    if settings.APP_ENV.strip().casefold() != "production":
        return

    reasons: list[str] = []
    provider_key = settings.MODEL_PROVIDER.strip().casefold().replace("_", "-")
    if provider_key not in PRODUCTION_APPROVED_MODEL_PROVIDERS:
        approved = ", ".join(sorted(PRODUCTION_APPROVED_MODEL_PROVIDERS))
        reasons.append(
            f"MODEL_PROVIDER must be one of: {approved} "
            "(the mock provider returns scripted text, not a model reply)"
        )
    if settings.RAG_MODE.strip().casefold() not in PRODUCTION_APPROVED_RAG_MODES:
        reasons.append(
            "RAG_MODE has no production-approved value yet: 'disabled' runs with no "
            "governed retrieval, and 'staging' retrieves from a release whose chunks "
            "are production_approved=false"
        )
    if settings.RAG_ALLOW_NEEDS_REVIEW_CITATIONS:
        reasons.append(
            "RAG_ALLOW_NEEDS_REVIEW_CITATIONS must be false: needs-review chunks have "
            "not passed human review"
        )
    if settings.RAG_STAGING_ALLOW_ALL_AUDIENCES:
        reasons.append(
            "RAG_STAGING_ALLOW_ALL_AUDIENCES must be false: it serves a role content "
            "whose source metadata does not list that role"
        )
    if reasons:
        raise ValueError("APP_ENV=production rejected this configuration: " + "; ".join(reasons))


def build_service_identity_replay_store(settings: Settings) -> ReplayStore:
    """Return a durable claim store, or fail closed where replicas can exist.

    Local and test profiles keep the in-memory store so the suite needs no
    database. Production must not: two replicas each holding their own
    dictionary would both accept the same signed request.
    """

    configured_url = settings.SERVICE_IDENTITY_REPLAY_DATABASE_URL
    if configured_url is not None and configured_url.get_secret_value().strip():
        return PostgresReplayStore(
            build_replay_engine(
                configured_url.get_secret_value().strip(),
                statement_timeout_ms=settings.SERVICE_IDENTITY_REPLAY_STATEMENT_TIMEOUT_MS,
            )
        )
    if settings.APP_ENV.strip().casefold() == "production":
        raise ValueError(
            "SERVICE_IDENTITY_REPLAY_DATABASE_URL is required when APP_ENV=production: "
            "process-local replay protection cannot span replicas"
        )
    return InMemoryReplayStore()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        yield
    finally:
        await close_retriever(app.state.rag_retriever)
        await app.state.provider.aclose()
        await app.state.service_identity_replay_store.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    validate_production_configuration(settings)
    if not settings.SERVICE_IDENTITY_ENABLED:
        raise ValueError("SERVICE_IDENTITY_ENABLED=true is required for Agent Runtime")
    if not settings.SERVICE_IDENTITY_HMAC_SECRET:
        raise ValueError("SERVICE_IDENTITY_HMAC_SECRET is required for Agent Runtime")
    app = FastAPI(
        title="Eldercare Agent Runtime",
        version=settings.API_VERSION,
        lifespan=_lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(agent_runs_router)
    app.include_router(rag_retrievals_router)
    app.state.provider = build_provider()
    app.state.orchestrator = AgentOrchestrator(
        provider=app.state.provider,
        max_steps=settings.MAX_AGENT_DECISIONS,
        agent_version=settings.AGENT_VERSION,
        max_tool_rounds=settings.MAX_TOOL_ROUNDS,
        max_total_tools=settings.MAX_TOTAL_TOOLS,
    )
    app.state.rag_retriever = build_configured_rag_retriever()
    app.state.service_identity_replay_store = build_service_identity_replay_store(settings)
    app.state.service_identity_verifier = ServiceCredentialVerifier(
        secret=settings.SERVICE_IDENTITY_HMAC_SECRET.get_secret_value(),
        issuer=settings.SERVICE_IDENTITY_ISSUER,
        expected_subject="core-api",
        audience="agent-runtime",
        replay_store=app.state.service_identity_replay_store,
        max_ttl_seconds=settings.SERVICE_IDENTITY_TTL_SECONDS,
    )
    return app


app = create_app()
