"""Prepare or generate the signed-scope Google artifact for PostgreSQL pgvector."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "core-api"))


from app.rag_embedding_importer import EmbeddingProfileBinding  # noqa: E402
from app.rag_projection_importer import (  # noqa: E402
    ProjectionImportError,
    load_projection_batch,
)

from rag_ingestion.embedding_provider import build_document_embedding_provider  # noqa: E402
from rag_ingestion.embedding_types import EmbeddingBatchError, EmbeddingError  # noqa: E402
from rag_ingestion.postgres_embedding_artifact import (  # noqa: E402
    generate_authorized_postgres_embedding_artifact,
)
from rag_ingestion.settings import SettingsError, load_settings  # noqa: E402
from rag_ingestion.staging_embedding_authorization import (  # noqa: E402
    StagingEmbeddingAuthorizationError,
    validate_staging_embedding_authorization,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="prepare or generate the fixed-hash Google artifact for pgvector"
    )
    parser.add_argument("command", choices=("prepare", "generate"))
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--candidate",
        type=Path,
        default=REPO_ROOT / "data" / "rag-v2" / "candidates" / "v002",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=(REPO_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.1.schema.json"),
    )
    parser.add_argument(
        "--authorization",
        type=Path,
        default=(REPO_ROOT / "data" / "rag-v2" / "human-review" / "acceptance" / "v002"),
    )
    parser.add_argument(
        "--embedding-config",
        type=Path,
        default=REPO_ROOT / "config" / "rag" / "embedding-google.yaml",
    )
    parser.add_argument(
        "--index-config",
        type=Path,
        default=REPO_ROOT / "config" / "rag" / "opensearch-index-v1.json",
    )
    parser.add_argument(
        "--staging-config",
        type=Path,
        default=REPO_ROOT / "config" / "rag" / "staging-filters.yaml",
    )
    parser.add_argument("--artifact-path", type=Path)
    parser.add_argument("--confirm-external-google-call", action="store_true")
    args = parser.parse_args(argv)

    embedder = None
    external_call_attempted = False
    try:
        repository_root = args.repository_root.resolve()
        authorization = validate_staging_embedding_authorization(
            repository_root,
            args.authorization.resolve(),
        )
        projection = load_projection_batch(
            args.candidate.resolve(),
            args.schema.resolve(),
            expected_source_count=authorization["source_count"],
            expected_chunk_count=authorization["chunk_count"],
        )
        settings = load_settings(
            embedding_config_path=args.embedding_config.resolve(),
            index_config_path=args.index_config.resolve(),
            staging_config_path=args.staging_config.resolve(),
            repository_root=repository_root,
        )
        settings.assert_staging_only_external_execution()
        profile = settings.require_embedding_profile()
        binding = EmbeddingProfileBinding(
            provider=profile.provider,
            model_id=profile.model_id,
            dimension=profile.dimension,
            document_task_type=profile.document_input_type,
            config_version=profile.config_version,
        )
        prepared = {
            "schema_version": "1.0.0",
            "status": "POSTGRES_EMBEDDING_PROFILE_READY",
            "release_id": projection.release_id,
            "candidate_sha256": projection.candidate_sha256,
            "allowlist_sha256": authorization["allowlist_sha256"],
            "embedding_profile_id": binding.profile_id,
            "embedding_provider": binding.provider,
            "embedding_model_id": binding.model_id,
            "embedding_dimension": binding.dimension,
            "document_task_type": binding.document_task_type,
            "config_version": binding.config_version,
            "source_count": projection.source_count,
            "chunk_count": projection.chunk_count,
            "external_access_performed": False,
            "database_write_performed": False,
            "retrieval_activation_status": "NOT_AUTHORIZED",
            "production_approved": False,
        }
        if args.command == "prepare":
            print(json.dumps(prepared, ensure_ascii=False, sort_keys=True))
            return 0
        expected_candidate_sha256 = os.getenv("RAG_POSTGRES_CANDIDATE_EXPECTED_SHA256", "")
        if expected_candidate_sha256 != projection.candidate_sha256:
            raise ProjectionImportError(
                "RAG_POSTGRES_CANDIDATE_EXPECTED_SHA256 must attest the exact candidate"
            )
        if not args.confirm_external_google_call:
            parser.error("generate requires --confirm-external-google-call")
        expected_profile_id = os.getenv("RAG_POSTGRES_EMBEDDING_PROFILE_EXPECTED_ID", "")
        if expected_profile_id != binding.profile_id:
            raise EmbeddingError(
                "RAG_POSTGRES_EMBEDDING_PROFILE_EXPECTED_ID must attest the exact profile"
            )

        artifact_path = (
            args.artifact_path.resolve()
            if args.artifact_path is not None
            else settings.embedding_artifact_path(repository_root)
        )
        embedder = build_document_embedding_provider(settings)
        external_call_attempted = True
        result = generate_authorized_postgres_embedding_artifact(
            authorization_status=authorization["authorization_status"],
            authorized_allowlist_sha256=authorization["allowlist_sha256"],
            provider=binding.provider,
            model_id=binding.model_id,
            dimension=binding.dimension,
            document_task_type=binding.document_task_type,
            config_version=binding.config_version,
            expected_chunk_count=projection.chunk_count,
            embedder=embedder,
            chunks=projection.chunks,
            artifact_path=artifact_path,
            repository_root=repository_root,
            rag_mode=settings.rag_mode,
            production_enabled=settings.rag_production_enabled,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        ProjectionImportError,
        SettingsError,
        StagingEmbeddingAuthorizationError,
        EmbeddingError,
    ) as exc:
        failure: dict[str, object] = {
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "external_access_status": (
                "MAY_HAVE_BEEN_ATTEMPTED" if external_call_attempted else "NOT_ATTEMPTED"
            ),
            "database_write_performed": False,
            "retrieval_activation_status": "NOT_AUTHORIZED",
            "production_approved": False,
        }
        if isinstance(exc, EmbeddingBatchError):
            failure["embedding_success_count"] = exc.success_count
            failure["embedding_failure_count"] = exc.failure_count
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        close = getattr(embedder, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    raise SystemExit(main())
