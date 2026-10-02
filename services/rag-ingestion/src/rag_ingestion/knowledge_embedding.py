"""Local knowledge dataset validation and complete cache assembly."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from rag_ingestion.embedding_plan import CachedEmbedding, SourceEmbeddingChunk, plan_embeddings
from rag_ingestion.knowledge_pipeline import _source_errors


class KnowledgeEmbeddingError(ValueError):
    """Fixed errors, without source content or credentials."""


def load_dataset(directory, schema_path, read_json):
    report = read_json(directory / "report.json")
    if (
        report.get("schema_version") != "knowledge-dataset-v1"
        or report.get("status") != "PASS"
        or report.get("production_approved") is not False
        or report.get("activation_allowed") is not False
    ):
        raise KnowledgeEmbeddingError("INVALID_DATASET_REPORT")
    validator = Draft202012Validator(read_json(schema_path), format_checker=FormatChecker())
    # Reuse the strict JSON reader for each line without temporary files.
    from json import loads

    def reject_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise KnowledgeEmbeddingError("DUPLICATE_JSON_KEY")
            value[key] = item
        return value

    def reject_constant(_value):
        raise KnowledgeEmbeddingError("NONFINITE_JSON_NUMBER")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise KnowledgeEmbeddingError("NONFINITE_JSON_NUMBER")
        return number

    chunks = []
    for line in (directory / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
        row = loads(
            line,
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
        if not validator.is_valid(row) or _source_errors(row):
            raise KnowledgeEmbeddingError("INVALID_KNOWLEDGE_CHUNK")
        content = row["content"]
        if hashlib.sha256(content["text"].encode()).hexdigest() != content["text_sha256"]:
            raise KnowledgeEmbeddingError("INCONSISTENT_TEXT_HASH")
        chunks.append(
            SourceEmbeddingChunk(
                row["chunk_id"], content["embedding_text"], content["embedding_text_sha256"]
            )
        )
    if not chunks or len(chunks) != report["summary"]["retained_count"]:
        raise KnowledgeEmbeddingError("DATASET_COUNT_MISMATCH")
    return tuple(chunks)


def complete_cache(chunks, target, profiles, cache, provider, max_new_texts):
    plan = plan_embeddings(chunks, target, known_profiles=profiles, cache=cache)
    missing = {}
    for row, chunk in zip(plan.rows, chunks, strict=True):
        if row.action == "EMBED":
            missing.setdefault(chunk.embedding_text_sha256, chunk.embedding_text)
    if len(missing) > max_new_texts:
        raise KnowledgeEmbeddingError("NEW_TEXT_LIMIT_EXCEEDED")
    vectors = {}
    for entry in cache:
        if entry.profile == target and entry.vector is not None:
            vectors[entry.embedding_text_sha256] = entry.vector
    if missing:
        if (
            provider.model_id != target.model_id
            or provider.dimension != target.dimension
            or provider.document_input_type != target.document_task_type
        ):
            raise KnowledgeEmbeddingError("PROVIDER_PROFILE_MISMATCH")
        result = provider.embed_documents(tuple(missing.values()))
        if (
            result.failure_count != 0
            or result.success_count != len(missing)
            or len(result.vectors) != len(missing)
        ):
            raise KnowledgeEmbeddingError("INCOMPLETE_EMBEDDING_RESULT")
        vectors.update(zip(missing, result.vectors, strict=True))
    entries = {}
    for chunk in chunks:
        entries.setdefault(
            chunk.embedding_text_sha256,
            CachedEmbedding(
                chunk.embedding_text,
                chunk.embedding_text_sha256,
                target,
                vectors[chunk.embedding_text_sha256],
            ),
        )
    completed = tuple(entries.values())
    verified = plan_embeddings(chunks, target, known_profiles=profiles, cache=completed)
    if verified.summary.available_reuse != len(chunks):
        raise KnowledgeEmbeddingError("INCOMPLETE_CACHE")
    return {
        "schema_version": "knowledge-embedding-cache-v1",
        "profiles": [asdict(target)],
        "entries": [
            {
                "embedding_text": entry.embedding_text,
                "embedding_text_sha256": entry.embedding_text_sha256,
                "profile_id": target.profile_id,
                "vector": list(entry.vector),
            }
            for entry in completed
        ],
    }


def write_new_cache(document, output: Path):
    payload = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects existing evidence even if another process wins.
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
