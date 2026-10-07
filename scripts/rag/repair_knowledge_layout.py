"""Rebuild a local PDF layout candidate and embedding plan; dry-run by default."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/rag-ingestion/src"))

from rag_ingestion.embedding_plan import (  # noqa: E402
    EmbeddingPlanError,
    SourceEmbeddingChunk,
    plan_embeddings,
)
from rag_ingestion.knowledge_layout import repair_corpus  # noqa: E402
from rag_ingestion.knowledge_pipeline import KnowledgePipelineError, write_dataset  # noqa: E402
from scripts.rag.prepare_knowledge import PreparationError, load_cache, load_profiles  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument(
        "--extraction",
        type=Path,
        default=ROOT / "data/rag-layout/v001/extraction.jsonl",
    )
    parser.add_argument("--dataset-version", default="v009")
    parser.add_argument("--max-embedding-characters", type=int, default=1500)
    parser.add_argument(
        "--profile-registry",
        type=Path,
        default=ROOT / "config/rag/knowledge-embedding-profiles.json",
    )
    parser.add_argument("--profile")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.write and args.output is None:
            raise KnowledgePipelineError("WRITE_REQUIRES_OUTPUT")
        compilation = repair_corpus(
            args.baseline,
            args.extraction,
            dataset_version=args.dataset_version,
            max_embedding_characters=args.max_embedding_characters,
        )
        target, profiles = load_profiles(args.profile_registry, args.profile)
        cache = load_cache(args.cache, profiles)
        plan = plan_embeddings(
            tuple(
                SourceEmbeddingChunk(
                    c["chunk_id"],
                    c["content"]["embedding_text"],
                    c["content"]["embedding_text_sha256"],
                )
                for c in compilation.chunks
            ),
            target,
            known_profiles=profiles,
            cache=cache,
        )
        if args.write:
            write_dataset(
                compilation,
                args.output,
                {"schema_version": "knowledge-embedding-plan-v1", **asdict(plan)},
            )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "mode": "WRITE" if args.write else "DRY_RUN",
                    "dataset_version": args.dataset_version,
                    "summary": compilation.report["summary"],
                    "embedding": asdict(plan.summary),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (KnowledgePipelineError, PreparationError, EmbeddingPlanError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        print(json.dumps({"status": "FAILED", "error": "LAYOUT_PREPARATION_FAILED"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
