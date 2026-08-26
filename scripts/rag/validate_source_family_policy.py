"""Validate the RAG v003 source-family policy preflight and candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.source_family_policy import (  # noqa: E402
    SourceFamilyPolicyError,
    validate_source_family_policy,
    validate_source_family_policy_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate governed source-family policy artifacts")
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        root = args.repository_root.resolve()
        preflight = validate_source_family_policy_preflight(root)
        policy = validate_source_family_policy(root)
    except (OSError, UnicodeDecodeError, ValueError, SourceFamilyPolicyError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "failure_reason": str(exc),
                    "external_sync": "NOT_AUTHORIZED",
                    "production_approved": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "preflight": preflight,
                "policy": policy,
                "external_sync": "NOT_AUTHORIZED",
                "production_approved": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
