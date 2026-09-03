"""Validate and optionally project the immutable RagChunkV2 candidate to PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "core-api"))

from app.database_url import to_psycopg_conninfo  # noqa: E402
from app.rag_projection_importer import (  # noqa: E402
    ProjectionImportError,
    dry_run_receipt,
    import_projection,
    load_projection_batch,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="project RagChunkV2 into PostgreSQL")
    parser.add_argument("command", choices=("dry-run", "import"))
    parser.add_argument(
        "--candidate",
        type=Path,
        default=REPO_ROOT / "data" / "rag-v2" / "candidates" / "v002",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=REPO_ROOT
        / "contracts"
        / "schemas"
        / "rag"
        / "rag-chunk-v2.1.schema.json",
    )
    args = parser.parse_args(argv)

    try:
        batch = load_projection_batch(
            args.candidate,
            args.schema,
            expected_source_count=17,
            expected_chunk_count=726,
        )
        if args.command == "dry-run":
            payload = dry_run_receipt(batch)
        else:
            expected_sha256 = os.getenv("RAG_POSTGRES_CANDIDATE_EXPECTED_SHA256")
            if expected_sha256 != batch.candidate_sha256:
                raise ProjectionImportError(
                    "RAG_POSTGRES_CANDIDATE_EXPECTED_SHA256 must attest the exact candidate"
                )
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ProjectionImportError("DATABASE_URL is required for import")
            if os.getenv("APP_ENV", "development").casefold() == "production":
                raise ProjectionImportError("candidate projection is staging-only")
            with psycopg.connect(to_psycopg_conninfo(database_url)) as connection:
                payload = import_projection(connection, batch).to_dict()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "production_approved": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
