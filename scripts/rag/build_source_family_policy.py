"""Build the RAG v003 source-family policy audit preflight or candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.source_family_policy import (  # noqa: E402
    SourceFamilyPolicyError,
    build_source_family_policy,
    prepare_source_family_policy_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="build governed source-family policy artifacts")
    parser.add_argument("command", choices=("preflight", "build"))
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        root = args.repository_root.resolve()
        summary = (
            prepare_source_family_policy_preflight(root)
            if args.command == "preflight"
            else build_source_family_policy(root)
        )
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
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
