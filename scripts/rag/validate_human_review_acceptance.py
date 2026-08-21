"""Validate the immutable project-owner human-review risk acceptance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.human_review_acceptance import (  # noqa: E402
    HumanReviewAcceptanceError,
    validate_human_review_acceptance,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="validate an immutable project-owner human-review risk acceptance"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--package",
        type=Path,
        default=(REPO_ROOT / "data" / "rag-v2" / "human-review" / "acceptance" / "v001"),
    )
    args = parser.parse_args(argv)
    try:
        summary = validate_human_review_acceptance(
            args.repository_root.resolve(),
            args.package.resolve(),
        )
    except (OSError, UnicodeDecodeError, ValueError, HumanReviewAcceptanceError) as exc:
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
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
