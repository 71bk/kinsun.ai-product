"""Plan developer knowledge smoke cases; --live runs bounded read-only diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/agent-runtime/src"))

from agent_runtime.rag.knowledge_evaluation import (  # noqa: E402
    CallCounts,
    CandidateRecorder,
    CountedEmbedding,
    CountedProvider,
    KnowledgeEvaluationError,
    evaluate_cases,
    load_cases,
    read_json,
    require,
)

DEFAULT_RELEASE = "rag-v2-v004-f3339ceae77c"


def _path(configured: str) -> Path:
    candidate = Path(configured)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _registry_profile(path: Path, profile_id: str) -> dict:
    registry = read_json(path)
    require(
        isinstance(registry, dict)
        and set(registry) == {"schema_version", "target_profile_id", "profiles"}
        and registry["schema_version"] == "knowledge-embedding-profiles-v1",
        "INVALID_PROFILE_REGISTRY",
    )
    require(isinstance(registry["profiles"], list), "INVALID_PROFILE_REGISTRY")
    names = {
        "profile_id",
        "provider",
        "model_id",
        "model_version",
        "document_task_type",
        "dimension",
        "config_version",
    }
    found = []
    for profile in registry["profiles"]:
        require(
            isinstance(profile, dict) and set(profile) == names,
            "INVALID_PROFILE_REGISTRY",
        )
        require(
            type(profile["dimension"]) is int
            and profile["dimension"] > 0
            and all(
                isinstance(profile[name], str) and bool(profile[name].strip())
                for name in names - {"dimension"}
            ),
            "INVALID_PROFILE_REGISTRY",
        )
        if profile["profile_id"] == profile_id:
            found.append(profile)
    require(len(found) == 1, "UNKNOWN_OR_AMBIGUOUS_PROFILE")
    return found[0]


def _generation_provider(settings):
    name = settings.MODEL_PROVIDER.strip().casefold()
    if name == "gemini":
        from agent_runtime.models.gemini_provider import GeminiModelProvider

        require(
            bool(settings.GEMINI_API_KEY and settings.GEMINI_MODEL_ID),
            "GENERATION_NOT_CONFIGURED",
        )
        return GeminiModelProvider(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            model_id=settings.GEMINI_MODEL_ID,
            max_tokens=settings.GEMINI_MAX_TOKENS,
            temperature=settings.GEMINI_TEMPERATURE,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        )
    if name == "openai-compatible":
        from agent_runtime.models.openai_compatible_provider import (
            OpenAICompatibleModelProvider,
        )

        require(
            bool(
                settings.OPENAI_COMPATIBLE_BASE_URL
                and settings.OPENAI_COMPATIBLE_MODEL_ID
            ),
            "GENERATION_NOT_CONFIGURED",
        )
        return OpenAICompatibleModelProvider(
            base_url=str(settings.OPENAI_COMPATIBLE_BASE_URL),
            model_id=settings.OPENAI_COMPATIBLE_MODEL_ID,
            api_key=settings.OPENAI_COMPATIBLE_API_KEY.get_secret_value()
            if settings.OPENAI_COMPATIBLE_API_KEY
            else None,
            max_tokens=settings.OPENAI_COMPATIBLE_MAX_TOKENS,
            temperature=settings.OPENAI_COMPATIBLE_TEMPERATURE,
            timeout_seconds=settings.OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
        )
    if name == "bedrock":
        from agent_runtime.models.bedrock_provider import build_bedrock_model_provider

        require(
            bool(settings.AWS_REGION and settings.BEDROCK_TEXT_MODEL_ID),
            "GENERATION_NOT_CONFIGURED",
        )
        return build_bedrock_model_provider(
            region=settings.AWS_REGION,
            model_id=settings.BEDROCK_TEXT_MODEL_ID,
            max_tokens=settings.BEDROCK_TEXT_MAX_TOKENS,
            temperature=settings.BEDROCK_TEXT_TEMPERATURE,
        )
    raise KnowledgeEvaluationError("REAL_GENERATION_PROVIDER_REQUIRED")


async def read_only_preflight(
    backend, *, release_id: str, profile: dict, expected_count: int
) -> dict:
    """Explicitly configure a read-only transaction before reading any source data."""
    from sqlalchemy import text

    from agent_runtime.rag.postgres_backend import configure_readonly_transaction

    async with backend._engine.connect() as connection:
        await configure_readonly_transaction(
            connection, backend._settings.statement_timeout_ms
        )
        readonly = await connection.execute(text("SHOW transaction_read_only"))
        require(readonly.scalar_one() == "on", "DATABASE_CONNECTION_NOT_READ_ONLY")
        default_readonly = await connection.execute(
            text("SHOW default_transaction_read_only")
        )
        default_readonly_on = default_readonly.scalar_one() == "on"
        result = await connection.execute(
            text("""
            SELECT release.release_id, release.chunk_count, release.release_status,
                   release.production_approved, profile.embedding_profile_id,
                   profile.provider, profile.model_id, profile.dimension,
                   profile.document_task_type, profile.config_version,
                   (SELECT count(*) FROM rag_public.chunk_projection AS projection
                    WHERE projection.release_id = release.release_id) AS projection_count,
                   (SELECT count(*) FROM rag_public.chunk_embedding AS embedding
                    WHERE embedding.release_id = release.release_id
                      AND embedding.embedding_profile_id = profile.embedding_profile_id)
                       AS vector_count,
                   (SELECT count(*) FROM rag_public.chunk_projection AS projection
                    JOIN rag_public.chunk_embedding AS embedding
                      ON embedding.release_id = projection.release_id
                     AND embedding.chunk_id = projection.chunk_id
                     AND embedding.embedding_text_sha256 = projection.embedding_text_sha256
                     AND embedding.embedding_profile_id = profile.embedding_profile_id
                    WHERE projection.release_id = release.release_id) AS matching_vector_count
            FROM rag_public.rag_release AS release
            JOIN rag_public.embedding_profile AS profile
              ON profile.embedding_profile_id = release.embedding_profile_id
            WHERE release.release_id = :release_id
              AND profile.embedding_profile_id = :profile_id
        """),
            {"release_id": release_id, "profile_id": profile["profile_id"]},
        )
        rows = result.mappings().all()
    require(len(rows) == 1, "RELEASE_PROFILE_NOT_FOUND")
    row = rows[0]
    require(
        row["production_approved"] is False
        and row["release_status"] == "STAGING_CANDIDATE",
        "STAGING_RELEASE_REQUIRED",
    )
    require(
        all(
            row[name] == expected_count
            for name in (
                "chunk_count",
                "projection_count",
                "vector_count",
                "matching_vector_count",
            )
        ),
        "RELEASE_VECTOR_COVERAGE_MISMATCH",
    )
    require(
        all(
            row[name] == profile[name]
            for name in (
                "provider",
                "model_id",
                "dimension",
                "document_task_type",
                "config_version",
            )
        ),
        "DATABASE_PROFILE_METADATA_MISMATCH",
    )
    return {
        "read_only_enforced": True,
        "read_only_enforcement": "EXPLICIT_TRANSACTION",
        "default_transaction_read_only_observed_on": default_readonly_on,
        "release_id": release_id,
        "projection_count": expected_count,
        "vector_count": expected_count,
        "profile": profile,
        "model_revision_verified_with_provider": False,
        "dataset": "EXISTING_V004_726"
        if release_id == DEFAULT_RELEASE
        else "EXPLICIT_EXISTING_RELEASE",
        "v007_658_dataset_tested": False,
    }


async def run_live(args, cases_version, cases):
    # Imports and environment/settings loading occur only after explicit --live.
    import yaml

    from agent_runtime.rag.evidence_service import EvidenceService
    from agent_runtime.rag.models import RagRuntimeSettings
    from agent_runtime.rag.retriever import build_retriever
    from agent_runtime.settings import Settings

    settings = Settings()
    require(
        settings.APP_ENV.strip().casefold() != "production"
        and settings.RAG_MODE.casefold() == "staging"
        and settings.RAG_SEARCH_BACKEND == "postgresql"
        and not settings.RAG_STAGING_ALLOW_ALL_AUDIENCES,
        "STAGING_READ_ONLY_CONFIGURATION_REQUIRED",
    )
    require(
        settings.MODEL_PROVIDER.strip().casefold()
        in {"gemini", "bedrock", "openai-compatible"},
        "REAL_GENERATION_PROVIDER_REQUIRED",
    )
    require(
        settings.RAG_POSTGRES_RELEASE_ID == args.release_id,
        "CONFIGURED_RELEASE_MISMATCH",
    )
    profile = _registry_profile(
        args.profile_registry, settings.RAG_POSTGRES_EMBEDDING_PROFILE_ID
    )
    config_path = _path(
        settings.RAG_QUERY_EMBEDDING_CONFIG_PATH or settings.RAG_EMBEDDING_CONFIG_PATH
    )
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    require(
        isinstance(document, dict) and isinstance(document.get("embedding"), dict),
        "INVALID_QUERY_EMBEDDING_CONFIG",
    )
    embedding = document["embedding"]
    require(
        document.get("schema_version") == profile["config_version"]
        and embedding.get("document_input_type") == profile["document_task_type"]
        and embedding.get("query_input_type") == "RETRIEVAL_QUERY"
        and embedding.get("truncate") == "NONE",
        "QUERY_PROFILE_CONFIG_MISMATCH",
    )
    # This copy changes neither environment files nor any running application.
    settings = settings.model_copy(update={"RAG_EVIDENCE_V3_ENABLED": True})
    names = (
        "AWS_REGION",
        "BEDROCK_EMBEDDING_MODEL_ID",
        "BEDROCK_EMBEDDING_DIMENSION",
        "GEMINI_EMBEDDING_MODEL_ID",
        "GEMINI_EMBEDDING_DIMENSION",
        "RAG_MODE",
        "RAG_SEARCH_BACKEND",
        "RAG_ALLOW_NEEDS_REVIEW_CITATIONS",
        "RAG_STAGING_ALLOW_ALL_AUDIENCES",
        "RAG_POSTGRES_RELEASE_ID",
        "RAG_POSTGRES_EMBEDDING_PROFILE_ID",
        "RAG_POSTGRES_STATEMENT_TIMEOUT_MS",
        "RAG_POSTGRES_POOL_MIN_SIZE",
        "RAG_POSTGRES_POOL_MAX_SIZE",
    )
    environment = {
        name: str(getattr(settings, name))
        for name in names
        if getattr(settings, name) is not None
    }
    runtime = RagRuntimeSettings.from_config_files(
        embedding_config_path=config_path,
        index_config_path=_path(settings.RAG_OPENSEARCH_INDEX_CONFIG_PATH),
        natural_profile_path=_path(settings.RAG_HYBRID_NATURAL_CONFIG_PATH),
        legal_profile_path=_path(settings.RAG_HYBRID_LEGAL_CONFIG_PATH),
        environ=environment,
        database_url=settings.RAG_DATABASE_URL,
    )
    require(
        runtime.embedding.provider == profile["provider"]
        and runtime.embedding.model_id == profile["model_id"]
        and runtime.embedding.dimension == profile["dimension"],
        "QUERY_PROFILE_METADATA_MISMATCH",
    )
    require(
        profile["model_version"] == profile["model_id"],
        "UNSUPPORTED_MODEL_REVISION_BINDING",
    )
    retriever = provider = None
    try:
        retriever = build_retriever(
            runtime,
            normalize_legal_queries=settings.RAG_QUERY_NORMALIZATION_ENABLED,
            google_api_key=settings.GEMINI_API_KEY.get_secret_value()
            if settings.GEMINI_API_KEY
            else None,
            google_timeout_seconds=settings.GEMINI_EMBEDDING_TIMEOUT_SECONDS,
        )
        async with asyncio.timeout(30):
            preflight = await read_only_preflight(
                retriever._search_backend,
                release_id=args.release_id,
                profile=profile,
                expected_count=args.expected_chunk_count,
            )
        counts = CallCounts()
        retriever._embedding_provider = CountedEmbedding(
            retriever._embedding_provider, counts
        )
        if not args.retrieval_only:
            provider = CountedProvider(_generation_provider(settings), counts)
        recorder = CandidateRecorder(retriever)
        service = EvidenceService(
            retriever=recorder,
            provider=provider,
            release_id=args.release_id,
            embedding_profile_id=profile["profile_id"],
        )
        report = await evaluate_cases(
            service,
            cases,
            cases_version=cases_version,
            counts=counts,
            recorder=recorder,
            retrieval_only=args.retrieval_only,
        )
        report["preflight"] = preflight
        report["generation_provider"] = settings.MODEL_PROVIDER
        report["generation_model_id"] = (
            provider.inner.model_id if provider is not None else None
        )
        report["generated_at"] = datetime.now(UTC).isoformat()
        report["process_local_v3_enabled"] = True
        return report
    finally:
        await asyncio.gather(
            *(
                resource.aclose()
                for resource in (provider, retriever)
                if resource is not None
            ),
            return_exceptions=True,
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "config/rag/knowledge-smoke-queries.json"
    )
    parser.add_argument("--case-id", nargs="+", action="extend", default=[])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--release-id", default=DEFAULT_RELEASE)
    parser.add_argument("--expected-chunk-count", type=int, default=726)
    parser.add_argument(
        "--profile-registry",
        type=Path,
        default=ROOT / "config/rag/knowledge-embedding-profiles.json",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".rag-work/knowledge-evaluation-v004.json"
    )
    args = parser.parse_args(argv)
    try:
        cases_version, cases = load_cases(args.cases, args.case_id)
        require(
            1 <= args.expected_chunk_count <= 100_000, "INVALID_EXPECTED_CHUNK_COUNT"
        )
        if not args.live:
            print(
                json.dumps(
                    {
                        "status": "OFFLINE_PLAN",
                        "cases_version": cases_version,
                        "case_ids": [case.id for case in cases],
                        "case_count": len(cases),
                        "release_id": args.release_id,
                        "expected_chunk_count": args.expected_chunk_count,
                        "query_embedding_calls": 0,
                        "generation_calls": 0,
                        "settings_loaded": False,
                        "report_written": False,
                    }
                )
            )
            return 0
        output = args.output.resolve()
        require(
            (ROOT / ".rag-work").resolve() in output.parents,
            "REPORT_MUST_BE_IN_IGNORED_WORK_DIRECTORY",
        )
        report = asyncio.run(run_live(args, cases_version, cases))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "COMPLETED",
                    **report["summary"],
                    "semantic_accuracy_verified": False,
                }
            )
        )
        return 1 if report["summary"]["statuses"].get("FAILED", 0) else 0
    except KnowledgeEvaluationError as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
        return 1
    except Exception as exc:
        failure = {
            "status": "FAILED",
            "error": "SMOKE_EXECUTION_FAILED",
            "exception_type": type(exc).__name__,
        }
        # Driver codes are safe operational metadata; never stringify exceptions.
        for candidate in (exc, getattr(exc, "orig", None), exc.__cause__):
            code = getattr(candidate, "sqlstate", None)
            if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code):
                failure["sqlstate"] = code
                break
        print(json.dumps(failure))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
