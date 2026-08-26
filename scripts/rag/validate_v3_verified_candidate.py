"""Validate owner evidence, preflight integrity, and the verified v003 candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.v3_verified_candidate import (  # noqa: E402
    V3VerifiedCandidateError,
    validate_owner_human_review_acceptance,
    validate_verified_audit_preflight,
    validate_verified_build_preflight_snapshot,
    validate_verified_candidate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="validate governed verified RAG v003 artifacts"
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    try:
        acceptance = validate_owner_human_review_acceptance(root)
        build_preflight = validate_verified_build_preflight_snapshot(root)
        audit_preflight = validate_verified_audit_preflight(root)
        candidate = validate_verified_candidate(root)
    except (OSError, UnicodeDecodeError, ValueError, V3VerifiedCandidateError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "failure_reason": str(exc),
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
                "build_preflight": build_preflight,
                "audit_preflight": audit_preflight,
                "candidate": candidate,
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
