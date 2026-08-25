"""Build an immutable fixed-hash staging document-embedding authorization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.staging_embedding_authorization import (  # noqa: E402
    StagingEmbeddingAuthorizationError,
    build_staging_embedding_authorization,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="build a fixed-hash owner authorization for staging document embedding"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--project-owner-id", required=True)
    parser.add_argument("--signed-at", required=True)
    parser.add_argument("--authorization-statement", required=True)
    parser.add_argument(
        "--confirm-staging-embedding-only",
        action="store_true",
        help="authorize fixed-hash staging document embedding without indexing or Production",
    )
    args = parser.parse_args(argv)
    if not args.confirm_staging_embedding_only:
        parser.error("--confirm-staging-embedding-only is required")
    repository_root = args.repository_root.resolve()
    output_root = (
        args.output_root.resolve()
        if args.output_root is not None
        else repository_root / "data" / "rag-v2" / "human-review" / "acceptance"
    )
    try:
        summary = build_staging_embedding_authorization(
            repository_root,
            output_root,
            project_owner_id=args.project_owner_id,
            signed_at=args.signed_at,
            authorization_statement=args.authorization_statement,
        )
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        StagingEmbeddingAuthorizationError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "failure_reason": str(exc),
                    "indexing_status": "NOT_AUTHORIZED",
                    "production_approved": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
