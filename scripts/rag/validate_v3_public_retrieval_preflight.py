"""Validate the committed RAG v003 owner acceptance and preflight packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.v3_public_retrieval_preflight import (  # noqa: E402
    V3PublicRetrievalPreflightError,
    validate_v3_owner_public_use_acceptance,
    validate_v3_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="validate RAG v003 acceptance, hashes, source inventory, and preflight lock"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    try:
        acceptance = validate_v3_owner_public_use_acceptance(root)
        preflight = validate_v3_preflight(root)
    except (OSError, UnicodeDecodeError, ValueError, V3PublicRetrievalPreflightError) as exc:
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
                "acceptance": acceptance,
                "preflight": preflight,
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
