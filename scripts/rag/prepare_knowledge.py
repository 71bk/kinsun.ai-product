"""Prepare local knowledge chunks and an offline embedding plan (dry-run by default)."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/rag-ingestion/src"))

from rag_ingestion.embedding_plan import (  # noqa: E402
    CachedEmbedding,
    EmbeddingPlanError,
    EmbeddingPlanProfile,
    SourceEmbeddingChunk,
    plan_embeddings,
)
from rag_ingestion.knowledge_pipeline import (  # noqa: E402
    KnowledgePipelineError,
    compile_corpus,
    write_dataset,
)


class PreparationError(ValueError):
    """Fixed error code without supplied content or paths."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PreparationError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_value):
    raise PreparationError("NONFINITE_JSON_NUMBER")


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise PreparationError("NONFINITE_JSON_NUMBER")
    if isinstance(value, dict):
        for member in value.values():
            _finite(member)
    elif isinstance(value, list):
        for member in value:
            _finite(member)


def _read_json(path: Path):
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object,
            parse_constant=_constant,
        )
        _finite(value)
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PreparationError("UNREADABLE_JSON") from exc


def _shape(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) <= (
        set(required) | set(optional)
    ):
        raise PreparationError("INVALID_JSON_SHAPE")


def load_profiles(path: Path, requested: str | None = None):
    registry = _read_json(path)
    _shape(registry, ("schema_version", "target_profile_id", "profiles"))
    if registry["schema_version"] != "knowledge-embedding-profiles-v1":
        raise PreparationError("INVALID_PROFILE_REGISTRY_VERSION")
    if not isinstance(registry["profiles"], list):
        raise PreparationError("INVALID_PROFILE_REGISTRY")
    profiles = []
    names = [field.name for field in fields(EmbeddingPlanProfile)]
    for row in registry["profiles"]:
        _shape(row, names)
        profiles.append(EmbeddingPlanProfile(**row))
    # Validate the complete registry before indexing possibly malformed IDs.
    target_id = requested if requested is not None else registry["target_profile_id"]
    if not isinstance(target_id, str) or not target_id.strip():
        raise PreparationError("INVALID_TARGET_PROFILE")
    target = next(
        (profile for profile in profiles if profile.profile_id == target_id), None
    )
    if target is None:
        raise PreparationError("UNKNOWN_PROFILE")
    plan_embeddings((), target, known_profiles=profiles)
    return target, tuple(profiles)


def load_cache(path: Path | None, profiles):
    if path is None:
        return ()
    manifest = _read_json(path)
    _shape(manifest, ("schema_version", "entries", "profiles"))
    if manifest["schema_version"] != "knowledge-embedding-cache-v1":
        raise PreparationError("INVALID_CACHE_VERSION")
    if not isinstance(manifest["entries"], list):
        raise PreparationError("INVALID_CACHE_ENTRIES")
    if not isinstance(manifest["profiles"], list):
        raise PreparationError("INVALID_CACHE_PROFILES")
    # Cache identity comes from its saved snapshot, never reconstructed from
    # today's configuration. A reused ID cannot hide changed model/config data.
    registry = {}
    names = [field.name for field in fields(EmbeddingPlanProfile)]
    for row in manifest["profiles"]:
        _shape(row, names)
        snapshot = EmbeddingPlanProfile(**row)
        plan_embeddings((), snapshot, known_profiles=profiles)
        if snapshot.profile_id in registry:
            raise PreparationError("DUPLICATE_CACHE_PROFILE")
        registry[snapshot.profile_id] = snapshot
    entries = []
    for row in manifest["entries"]:
        _shape(
            row, ("embedding_text", "embedding_text_sha256", "profile_id"), ("vector",)
        )
        profile_id = row["profile_id"]
        if not isinstance(profile_id, str) or profile_id not in registry:
            raise PreparationError("UNKNOWN_PROFILE")
        if "vector" in row and not isinstance(row["vector"], list):
            raise PreparationError("INVALID_CACHE_VECTOR")
        entries.append(
            CachedEmbedding(
                row["embedding_text"],
                row["embedding_text_sha256"],
                registry[profile_id],
                tuple(row["vector"]) if "vector" in row else None,
            )
        )
    return tuple(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "data/rag-rechunk/successor/v001/corpus.jsonl",
    )
    parser.add_argument(
        "--baseline", type=Path, default=ROOT / "data/rag-v2/candidates/v004/chunks"
    )
    parser.add_argument("--dataset-version", default="v007")
    parser.add_argument(
        "--profile-registry",
        type=Path,
        default=ROOT / "config/rag/knowledge-embedding-profiles.json",
    )
    parser.add_argument("--profile")
    parser.add_argument("--cache", type=Path)
    parser.add_argument(
        "--audience-patches",
        type=Path,
        help="Explicit hash-bound additive public audience corrections",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.write and args.output is None:
            raise PreparationError("WRITE_REQUIRES_OUTPUT")
        target, profiles = load_profiles(args.profile_registry, args.profile)
        cache = load_cache(args.cache, profiles)
        compilation = compile_corpus(
            args.corpus,
            dataset_version=args.dataset_version,
            baseline_path=args.baseline,
            audience_patches_path=args.audience_patches,
        )
        report = compilation.report
        summary = {
            key: report[key]
            for key in (
                "status",
                "dataset_version",
                "summary",
                "excluded_by_reason",
                "warnings_by_code",
                "embedding_comparison",
                "audience_patch_differences",
            )
            if key in report
        }
        if report["status"] != "PASS":
            print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
            return 1
        plan = plan_embeddings(
            tuple(
                SourceEmbeddingChunk(
                    row["chunk_id"],
                    row["content"]["embedding_text"],
                    row["content"]["embedding_text_sha256"],
                )
                for row in compilation.chunks
            ),
            target,
            known_profiles=profiles,
            cache=cache,
        )
        plan_document = {
            "schema_version": "knowledge-embedding-plan-v1",
            **asdict(plan),
        }
        summary["embedding"] = {"summary": asdict(plan.summary)}
        summary["mode"] = "WRITE" if args.write else "DRY_RUN"
        if args.write:
            write_dataset(compilation, args.output, embedding_plan=plan_document)
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
        return 0
    except (PreparationError, KnowledgePipelineError, EmbeddingPlanError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
        return 1
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        OverflowError,
    ) as exc:
        # Do not emit exception details: they can contain paths or supplied data.
        del exc
        print(json.dumps({"status": "FAILED", "error": "PREPARATION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
