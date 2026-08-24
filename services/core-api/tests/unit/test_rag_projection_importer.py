from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.rag_projection_importer import (
    ProjectionImportError,
    dry_run_receipt,
    load_projection_batch,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2))
        handle.write("\n")


def _refresh_checksums(candidate: Path) -> None:
    lines = []
    for path in sorted(
        (item for item in candidate.rglob("*") if item.is_file() and item.name != "SHA256SUMS.txt"),
        key=lambda item: item.relative_to(candidate).as_posix(),
    ):
        lines.append(
            f"{_sha256_bytes(path.read_bytes())}  {path.relative_to(candidate).as_posix()}"
        )
    with (candidate / "SHA256SUMS.txt").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def _candidate(tmp_path: Path) -> tuple[Path, Path]:
    candidate = tmp_path / "v001"
    chunk_path = candidate / "chunks" / "synthetic.rag-chunk-v2.v001.jsonl"
    text = "合成長照公開資料。"
    embedding_text = "合成長照公開資料，供文件檢索。"
    record = {
        "schema_version": "2.1.0",
        "artifact_version": "v001",
        "identity": {
            "chunk_id": "synthetic_rag_v2_v001_0001",
            "source_id": "synthetic_source",
            "chunk_index": 1,
        },
        "content": {
            "text": text,
            "embedding_text": embedding_text,
            "text_sha256": _sha256_text(text),
            "embedding_text_sha256": _sha256_text(embedding_text),
            "content_type": "service_guide",
            "language": "zh-Hant",
            "locale": "zh-TW",
        },
        "citation": {"title": "合成長照指南", "section": "申請方式"},
        "governance": {
            "review_status": "needs_review",
            "current_status": "current",
            "production_approved": False,
        },
        "provenance": {"source_version": "synthetic-v1"},
        "retrieval_policy": {
            "risk_level": "low",
            "retrieval_eligible": True,
            "stop_normal_rag": False,
            "requires_human_review": True,
            "requires_official_assessment": False,
            "requires_professional_assessment": False,
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["general_information"],
        },
    }
    chunk_path.parent.mkdir(parents=True)
    chunk_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    chunk_sha256 = _sha256_bytes(chunk_path.read_bytes())

    _write_json(
        candidate / "manifests" / "source-manifest-v001.json",
        {
            "artifact_version": "v001",
            "source_count": 1,
            "chunk_count": 1,
            "sources": [{"source_id": "synthetic_source"}],
        },
    )
    _write_json(
        candidate / "manifests" / "chunk-file-manifest-v001.json",
        {
            "artifact_version": "v001",
            "chunk_file_count": 1,
            "chunk_count": 1,
            "files": [
                {
                    "source_id": "synthetic_source",
                    "path": "chunks/synthetic.rag-chunk-v2.v001.jsonl",
                    "chunk_count": 1,
                    "sha256": chunk_sha256,
                }
            ],
        },
    )
    _write_json(
        candidate / "manifests" / "embedding-staging-allowlist-v001.json",
        {
            "artifact_version": "v001",
            "source_count": 1,
            "chunk_count": 1,
            "human_source_review": "NOT_COMPLETED",
            "embedding_status": "NOT_STARTED",
            "production_status": "BLOCKED",
            "entries": [
                {
                    "chunk_id": "synthetic_rag_v2_v001_0001",
                    "text_sha256": _sha256_text(text),
                    "embedding_text_sha256": _sha256_text(embedding_text),
                }
            ],
        },
    )
    _write_json(candidate / "README.json", {"candidate": "synthetic"})
    _refresh_checksums(candidate)

    schema = tmp_path / "rag-chunk-schema.json"
    _write_json(
        schema, {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
    )
    return candidate, schema


def test_projection_batch_validates_before_database_use(tmp_path: Path) -> None:
    candidate, schema = _candidate(tmp_path)

    batch = load_projection_batch(
        candidate,
        schema,
        expected_source_count=1,
        expected_chunk_count=1,
    )
    receipt = dry_run_receipt(batch)

    assert batch.source_count == 1
    assert batch.chunk_count == 1
    assert batch.production_approved is False
    assert batch.chunks[0].chunk_text == "合成長照公開資料。"
    assert receipt["stored_embedding_count"] == 0
    serialized_receipt = json.dumps(receipt, ensure_ascii=False)
    assert "合成長照公開資料" not in serialized_receipt


def test_projection_batch_rejects_candidate_byte_tampering(tmp_path: Path) -> None:
    candidate, schema = _candidate(tmp_path)
    chunk_path = candidate / "chunks" / "synthetic.rag-chunk-v2.v001.jsonl"
    chunk_path.write_text(chunk_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ProjectionImportError, match="checksum"):
        load_projection_batch(candidate, schema)


def test_projection_batch_rejects_self_consistent_allowlist_mismatch(tmp_path: Path) -> None:
    candidate, schema = _candidate(tmp_path)
    allowlist_path = candidate / "manifests" / "embedding-staging-allowlist-v001.json"
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    allowlist["entries"][0]["text_sha256"] = "0" * 64
    _write_json(allowlist_path, allowlist)
    _refresh_checksums(candidate)

    with pytest.raises(ProjectionImportError, match="attest"):
        load_projection_batch(candidate, schema)


def test_projection_batch_never_promotes_candidate_to_production(tmp_path: Path) -> None:
    candidate, schema = _candidate(tmp_path)
    chunk_path = candidate / "chunks" / "synthetic.rag-chunk-v2.v001.jsonl"
    record = json.loads(chunk_path.read_text(encoding="utf-8"))
    record["governance"]["production_approved"] = True
    chunk_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    chunk_manifest_path = candidate / "manifests" / "chunk-file-manifest-v001.json"
    chunk_manifest = json.loads(chunk_manifest_path.read_text(encoding="utf-8"))
    chunk_manifest["files"][0]["sha256"] = _sha256_bytes(chunk_path.read_bytes())
    _write_json(chunk_manifest_path, chunk_manifest)
    _refresh_checksums(candidate)

    with pytest.raises(ProjectionImportError, match="production-approved"):
        load_projection_batch(candidate, schema)
