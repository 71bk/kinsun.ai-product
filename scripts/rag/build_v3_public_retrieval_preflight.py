"""Build the v003 public-retrieval owner acceptance or preflight package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.v3_public_retrieval_preflight import (  # noqa: E402
    V3PublicRetrievalPreflightError,
    build_v3_owner_public_use_acceptance,
    build_v3_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="build governed RAG v003 owner acceptance and preflight artifacts"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    acceptance = subparsers.add_parser("acceptance")
    acceptance.add_argument("--project-owner-id", required=True)
    acceptance.add_argument("--signed-at", required=True)
    acceptance.add_argument("--authorization-statement", action="append", required=True)
    acceptance.add_argument(
        "--confirm-staging-public-retrieval-policy",
        action="store_true",
        help="authorize only local candidate construction and staging policy tests",
    )

    subparsers.add_parser("preflight")
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    try:
        if args.command == "acceptance":
            if not args.confirm_staging_public_retrieval_policy:
                parser.error("--confirm-staging-public-retrieval-policy is required")
            summary = build_v3_owner_public_use_acceptance(
                root,
                project_owner_id=args.project_owner_id,
                signed_at=args.signed_at,
                authorization_statements=args.authorization_statement,
            )
        else:
            summary = build_v3_preflight(root)
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
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
