"""Export local cache evidence only with explicit --read-live; never changes the DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))

import psycopg  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

from app.database_url import to_psycopg_conninfo  # noqa: E402
from app.rag_knowledge_cache import KnowledgeCacheError, export_knowledge_cache  # noqa: E402

DEFAULT_RELEASE = "rag-v2-v004-f3339ceae77c"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-live", action="store_true")
    parser.add_argument("--release-id", default=DEFAULT_RELEASE)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config/rag/knowledge-embedding-profiles.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.read_live:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN",
                    "release_id": args.release_id,
                    "database_read_performed": False,
                }
            )
        )
        return 0
    if args.output is None:
        parser.error("--read-live requires an explicit --output under .rag-work")
    try:
        output = args.output.resolve()
        scratch = (ROOT / ".rag-work").resolve()
        if not output.is_relative_to(scratch) or output == scratch or output.exists():
            raise ValueError("OUTPUT_BOUNDARY")
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        values = {**dotenv_values(ROOT / ".env"), **os.environ}
        database = values.get("RAG_DATABASE_URL") or values.get("DATABASE_URL")
        if not database:
            raise ValueError("DATABASE_CONFIGURATION")
        with psycopg.connect(
            to_psycopg_conninfo(database), connect_timeout=15
        ) as connection:
            cache = export_knowledge_cache(
                connection, release_id=args.release_id, registry=registry
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(cache, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        print(
            json.dumps(
                {
                    "status": "EXPORTED",
                    "release_id": args.release_id,
                    "profile_id": cache["profiles"][0]["profile_id"],
                    "chunk_count": len(cache["entries"]),
                    "model_version_limitation": (
                        "DB stores model_id only; immutable provider revision is unavailable"
                    ),
                }
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "sqlstate": getattr(exc, "sqlstate", None),
                    "error_code": exc.args[0]
                    if isinstance(exc, KnowledgeCacheError)
                    else "CACHE_EXPORT_FAILED",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
