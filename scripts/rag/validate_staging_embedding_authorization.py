"""Validate the immutable fixed-hash staging embedding authorization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.staging_embedding_authorization import (  # noqa: E402
    StagingEmbeddingAuthorizationError,
    validate_staging_embedding_authorization,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="validate the fixed-hash staging document-embedding authorization"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--package",
        type=Path,
        default=(REPO_ROOT / "data" / "rag-v2" / "human-review" / "acceptance" / "v002"),
    )
    args = parser.parse_args(argv)
    try:
        summary = validate_staging_embedding_authorization(
            args.repository_root.resolve(),
            args.package.resolve(),
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
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
