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
from agent_runtime.rag.retriever import build_retriever
from agent_runtime.security.service_identity import ServiceCredentialVerifier
from agent_runtime.settings import get_settings

logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


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
                "OPENSEARCH_HOST": settings.OPENSEARCH_HOST,
                "OPENSEARCH_INDEX": settings.OPENSEARCH_INDEX,
                "OPENSEARCH_ALIAS": settings.OPENSEARCH_ALIAS,
                "RAG_MODE": settings.RAG_MODE,
            }.items()
            if value is not None and str(value).strip()
        }
        rag_settings = RagRuntimeSettings.from_config_files(
            embedding_config_path=_resolve_config_path(settings.RAG_EMBEDDING_CONFIG_PATH),
            index_config_path=_resolve_config_path(settings.RAG_OPENSEARCH_INDEX_CONFIG_PATH),
            natural_profile_path=_resolve_config_path(settings.RAG_HYBRID_NATURAL_CONFIG_PATH),
            legal_profile_path=_resolve_config_path(settings.RAG_HYBRID_LEGAL_CONFIG_PATH),
            environ=provider_environment,
        )
        return build_retriever(rag_settings)
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        yield
    finally:
        await app.state.provider.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
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
    app.state.service_identity_verifier = ServiceCredentialVerifier(
        secret=settings.SERVICE_IDENTITY_HMAC_SECRET.get_secret_value(),
        issuer=settings.SERVICE_IDENTITY_ISSUER,
        expected_subject="core-api",
        audience="agent-runtime",
        max_ttl_seconds=settings.SERVICE_IDENTITY_TTL_SECONDS,
    )
    return app


app = create_app()
