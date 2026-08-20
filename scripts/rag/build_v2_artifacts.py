"""Freeze inputs or build the deterministic RagChunkV2 local candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.v2_artifacts import (  # noqa: E402
    build_v2_artifacts,
    prepare_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="prepare or build the immutable RagChunkV2 local candidate"
    )
    parser.add_argument("command", choices=("preflight", "build"))
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)

    repository_root = args.repository_root.resolve()
    output_root = (
        args.output_root.resolve()
        if args.output_root is not None
        else repository_root / "data" / "rag-v2"
    )
    try:
        if args.command == "preflight":
            summary = prepare_preflight(repository_root, output_root)
        else:
            summary = build_v2_artifacts(
                repository_root,
                output_root,
                require_test_evidence=True,
            ).to_dict()
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "command": args.command,
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

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
