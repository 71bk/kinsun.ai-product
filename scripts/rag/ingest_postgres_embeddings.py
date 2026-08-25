"""Validate, import, or verify the signed-scope pgvector embedding artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "core-api"))

from app.database_url import to_psycopg_conninfo  # noqa: E402
from app.rag_embedding_importer import (  # noqa: E402
    EmbeddingImportError,
    import_embeddings,
    load_embedding_import_batch,
    validated_artifact_receipt,
    verify_embeddings,
)
from app.rag_projection_importer import (  # noqa: E402
    ProjectionImportError,
    load_projection_batch,
)

from rag_ingestion.settings import default_embedding_artifact_path  # noqa: E402
from rag_ingestion.staging_embedding_authorization import (  # noqa: E402
    StagingEmbeddingAuthorizationError,
    validate_staging_embedding_authorization,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="validate or transactionally import pgvector document embeddings"
    )
    parser.add_argument("command", choices=("validate", "import", "verify"))
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
        "--artifact",
        type=Path,
        default=default_embedding_artifact_path(),
    )
    parser.add_argument("--confirm-staging-write", action="store_true")
    args = parser.parse_args(argv)

    database_write_attempted = False
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
        expected_candidate_sha256 = os.getenv("RAG_POSTGRES_CANDIDATE_EXPECTED_SHA256", "")
        if expected_candidate_sha256 != projection.candidate_sha256:
            raise ProjectionImportError(
                "RAG_POSTGRES_CANDIDATE_EXPECTED_SHA256 must attest the exact candidate"
            )
        expected_artifact_sha256 = os.getenv("RAG_EMBEDDING_ARTIFACT_EXPECTED_SHA256", "")
        expected_profile_id = os.getenv(
            "RAG_POSTGRES_EMBEDDING_PROFILE_EXPECTED_ID",
            "",
        )
        batch = load_embedding_import_batch(
            args.artifact.resolve(),
            repository_root=repository_root,
            projection=projection,
            expected_artifact_sha256=expected_artifact_sha256,
            expected_allowlist_sha256=authorization["allowlist_sha256"],
            expected_profile_id=expected_profile_id,
        )
        if args.command == "validate":
            print(
                json.dumps(
                    validated_artifact_receipt(batch),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        if os.getenv("APP_ENV", "development").casefold() == "production":
            raise EmbeddingImportError("PostgreSQL embedding import is staging-only")
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise EmbeddingImportError("DATABASE_URL is required")
        if args.command == "import" and not args.confirm_staging_write:
            parser.error("import requires --confirm-staging-write")
        with psycopg.connect(to_psycopg_conninfo(database_url)) as connection:
            if args.command == "import":
                database_write_attempted = True
                payload = import_embeddings(connection, batch).to_dict()
            else:
                payload = verify_embeddings(connection, batch)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        psycopg.Error,
        ProjectionImportError,
        EmbeddingImportError,
        StagingEmbeddingAuthorizationError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "database_write_attempted": database_write_attempted,
                    "retrieval_activation_status": "NOT_AUTHORIZED",
                    "production_approved": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
