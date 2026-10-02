"""Generate only missing knowledge document embeddings; dry-run by default."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/rag-ingestion/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_knowledge import PreparationError, _read_json, load_cache, load_profiles  # noqa: E402
from rag_ingestion.embedding_plan import EmbeddingPlanError, plan_embeddings  # noqa: E402
from rag_ingestion.knowledge_embedding import (  # noqa: E402
    KnowledgeEmbeddingError,
    complete_cache,
    load_dataset,
    write_new_cache,
)


def build_provider(target):
    # Imports/settings are deliberately deferred until --generate is explicit.
    import yaml

    from rag_ingestion.google_embedder import GoogleDocumentEmbedder
    from rag_ingestion.settings import IngestionSettings

    configuration = yaml.safe_load(
        (ROOT / "config/rag/embedding-google.yaml").read_text(encoding="utf-8")
    )
    embedding = configuration["embedding"]
    if (
        target.provider != "google"
        or target.dimension != 1024
        or target.model_version != target.model_id
        or target.config_version != configuration["schema_version"]
        or embedding["provider"] != target.provider
        or embedding["model_id"] != target.model_id
        or embedding["dimension"] != target.dimension
        or embedding["document_input_type"] != target.document_task_type
        or embedding["truncate"] != "NONE"
    ):
        raise KnowledgeEmbeddingError("CONFIGURATION_PROFILE_MISMATCH")
    settings = IngestionSettings(_env_file=ROOT / ".env")
    if (
        settings.gemini_embedding_model_id not in (None, target.model_id)
        or settings.gemini_embedding_dimension != target.dimension
        or settings.gemini_api_key is None
    ):
        raise KnowledgeEmbeddingError("ENVIRONMENT_PROFILE_MISMATCH")
    return GoogleDocumentEmbedder(
        api_key=settings.gemini_api_key.get_secret_value(),
        model_id=target.model_id,
        dimension=target.dimension,
        document_input_type=target.document_task_type,
        batch_size=32,
        timeout_seconds=30,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--profile-registry",
        type=Path,
        default=ROOT / "config/rag/knowledge-embedding-profiles.json",
    )
    parser.add_argument("--profile")
    parser.add_argument("--max-new-texts", type=int, default=32)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    provider = None
    try:
        if not 0 <= args.max_new_texts <= 32:
            raise KnowledgeEmbeddingError("INVALID_NEW_TEXT_LIMIT")
        if args.generate:
            if args.output is None:
                raise KnowledgeEmbeddingError("GENERATE_REQUIRES_OUTPUT")
            output = args.output.resolve()
            if not output.is_relative_to((ROOT / ".rag-work").resolve()):
                raise KnowledgeEmbeddingError("OUTPUT_OUTSIDE_WORK_DIRECTORY")
            if output.exists():
                raise KnowledgeEmbeddingError("OUTPUT_ALREADY_EXISTS")
        target, profiles = load_profiles(args.profile_registry, args.profile)
        cache = load_cache(args.cache, profiles)
        chunks = load_dataset(
            args.dataset,
            ROOT / "contracts/schemas/rag/knowledge-chunk-v1.schema.json",
            _read_json,
        )
        plan = plan_embeddings(chunks, target, known_profiles=profiles, cache=cache)
        if plan.summary.unique_embeddings_required > args.max_new_texts:
            raise KnowledgeEmbeddingError("NEW_TEXT_LIMIT_EXCEEDED")
        if args.generate:
            if plan.summary.unique_embeddings_required:
                provider = build_provider(target)
            document = complete_cache(
                chunks, target, profiles, cache, provider, args.max_new_texts
            )
            if provider is not None:
                provider.close()
                provider = None
            write_new_cache(document, output)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "mode": "GENERATE" if args.generate else "DRY_RUN",
                    "embedding": asdict(plan.summary),
                    "cache_written": args.generate,
                }
            )
        )
        return 0
    except (PreparationError, EmbeddingPlanError, KnowledgeEmbeddingError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
        return 1
    except Exception:
        print(json.dumps({"status": "FAILED", "error": "EMBEDDING_EXECUTION_FAILED"}))
        return 1
    finally:
        if provider is not None:
            try:
                provider.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
