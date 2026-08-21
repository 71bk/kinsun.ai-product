"""Build the immutable pending-only RagChunkV2 human-review assignment package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.human_review_package import (  # noqa: E402
    HumanReviewPackageError,
    build_human_review_package,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="build an immutable pending-only RagChunkV2 human-review package"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    repository_root = args.repository_root.resolve()
    output_root = (
        args.output_root.resolve()
        if args.output_root is not None
        else repository_root / "data" / "rag-v2" / "human-review"
    )
    try:
        summary = build_human_review_package(repository_root, output_root)
    except (OSError, UnicodeDecodeError, ValueError, HumanReviewPackageError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "failure_reason": str(exc),
                    "review_completion_status": "NOT_COMPLETED",
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
