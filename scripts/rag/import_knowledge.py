"""Review complete local candidate/vector inputs; no DB import or activation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))

from app.rag_knowledge_embedding_importer import load_knowledge_embedding_batch  # noqa: E402
from app.rag_knowledge_importer import load_knowledge_batch  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / ".rag-work/knowledge-v008"
    )
    parser.add_argument(
        "--cache", type=Path, default=ROOT / ".rag-work/cache/v008-complete-cache.json"
    )
    parser.add_argument(
        "--profile-registry",
        type=Path,
        default=ROOT / "config/rag/knowledge-embedding-profiles.json",
    )
    parser.add_argument("--expected-release-id")
    parser.add_argument("--expected-candidate-sha256")
    parser.add_argument("--expected-cache-sha256")
    args = parser.parse_args(argv)
    try:
        projection = load_knowledge_batch(args.dataset)
        if (
            args.expected_release_id is not None
            and args.expected_release_id != projection.release_id
        ):
            raise ValueError("release binding mismatch")
        if (
            args.expected_candidate_sha256 is not None
            and args.expected_candidate_sha256 != projection.candidate_sha256
        ):
            raise ValueError("candidate binding mismatch")
        embeddings = load_knowledge_embedding_batch(
            args.cache,
            projection=projection,
            profile_registry_path=args.profile_registry,
            expected_cache_sha256=args.expected_cache_sha256,
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "mode": "DRY_RUN",
                    "release_id": projection.release_id,
                    "candidate_sha256": projection.candidate_sha256,
                    "cache_sha256": embeddings.artifact_sha256,
                    "source_count": projection.source_count,
                    "chunk_count": projection.chunk_count,
                    "validated_vector_count": len(embeddings.records),
                    "embedding_profile_id": embeddings.profile.profile_id,
                    "embedding_provider": embeddings.profile.provider,
                    "embedding_model_id": embeddings.profile.model_id,
                    "embedding_dimension": embeddings.profile.dimension,
                    "document_task_type": embeddings.profile.document_task_type,
                    "config_version": embeddings.profile.config_version,
                    "legacy_allowlist_used": False,
                    "database_write_performed": False,
                    "activation_performed": False,
                    "import_flag_available": False,
                    "production_approved": False,
                },
                allow_nan=False,
            )
        )
        return 0
    except Exception as exc:
        # Never expose content, credentials, exception messages or local paths.
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
