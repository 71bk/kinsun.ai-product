"""Build the versioned owner acceptance, preflight, or verified v003 candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.v3_verified_candidate import (  # noqa: E402
    V3VerifiedCandidateError,
    build_owner_human_review_acceptance,
    build_verified_audit_preflight,
    build_verified_candidate,
    build_verified_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="build governed verified RAG v003 artifacts"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    acceptance = subparsers.add_parser("acceptance")
    acceptance.add_argument("--project-owner-id", required=True)
    acceptance.add_argument("--signed-at", required=True)
    acceptance.add_argument("--authorization-statement", action="append", required=True)
    acceptance.add_argument("--confirm-reviewed-all-726-chunks", action="store_true")
    acceptance.add_argument("--confirm-production-remains-blocked", action="store_true")

    subparsers.add_parser("preflight")
    subparsers.add_parser("candidate")
    subparsers.add_parser("audit-preflight")
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    try:
        if args.command == "acceptance":
            if not args.confirm_reviewed_all_726_chunks:
                parser.error("--confirm-reviewed-all-726-chunks is required")
            if not args.confirm_production_remains_blocked:
                parser.error("--confirm-production-remains-blocked is required")
            summary = build_owner_human_review_acceptance(
                root,
                project_owner_id=args.project_owner_id,
                signed_at=args.signed_at,
                authorization_statements=args.authorization_statement,
            )
        elif args.command == "preflight":
            summary = build_verified_preflight(root)
        elif args.command == "candidate":
            summary = build_verified_candidate(root)
        else:
            summary = build_verified_audit_preflight(root)
    except (OSError, UnicodeDecodeError, ValueError, V3VerifiedCandidateError) as exc:
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
