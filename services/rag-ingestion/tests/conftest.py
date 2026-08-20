from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

_RAG_V2_INVENTORY_SHA256_ENV = "RAG_V2_VALIDATION_INPUT_INVENTORY_SHA256"


def _normalize_node_id(node_id: str) -> str:
    path, separator, test_name = node_id.partition("::")
    if not separator:
        return node_id
    normalized_path = path.replace("\\", "/")
    return f"{normalized_path}{separator}{test_name}"


@pytest.fixture(scope="session", autouse=True)
def bind_rag_v2_validation_inventory(
    record_testsuite_property: Any,
    request: pytest.FixtureRequest,
) -> None:
    """Bind formal JUnit evidence to the preflight inputs used by that run."""

    inventory_sha256 = os.getenv(_RAG_V2_INVENTORY_SHA256_ENV)
    if inventory_sha256 is None:
        return
    if re.fullmatch(r"[a-f0-9]{64}", inventory_sha256) is None:
        pytest.fail(f"{_RAG_V2_INVENTORY_SHA256_ENV} must be a lowercase SHA-256 digest")
    record_testsuite_property(
        "validation_input_inventory_sha256",
        inventory_sha256,
    )
    collected_node_ids = sorted(_normalize_node_id(item.nodeid) for item in request.session.items)
    if len(collected_node_ids) != len(set(collected_node_ids)):
        pytest.fail("pytest collected duplicate test node IDs")
    collected_node_payload = json.dumps(
        collected_node_ids,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    record_testsuite_property(
        "collected_test_node_hash_mode",
        "sha256_canonical_json_v1",
    )
    record_testsuite_property(
        "collected_test_node_ids_sha256",
        hashlib.sha256(collected_node_payload.encode("utf-8")).hexdigest(),
    )
    record_testsuite_property(
        "collected_test_node_count",
        str(len(collected_node_ids)),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def synthetic_chunk(chunk_id: str = "synthetic_source_chunk_001") -> dict[str, Any]:
    text = "Synthetic public-care reference text."
    embedding_text = "Synthetic public-care reference text for retrieval."
    return {
        "chunk_id": chunk_id,
        "chunk_index": 1,
        "source_id": "synthetic_source",
        "document_title": "Synthetic Care Guide",
        "section": "Safe information",
        "page_start": 1,
        "page_end": 1,
        "source_locator": "page 1",
        "text": text,
        "embedding_text": embedding_text,
        "metadata": {
            "official_source_url": "https://example.invalid/synthetic-guide",
            "current_status": "current",
            "stop_normal_rag": False,
            "risk_level": "low",
            "requires_human_review": False,
            "requires_official_assessment": False,
            "requires_professional_assessment": False,
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["general_information"],
            "source_version": "synthetic-v1",
            "text_sha256": sha256_text(text),
            "embedding_text_sha256": sha256_text(embedding_text),
        },
    }


def write_dataset(
    root: Path,
    *,
    chunks: list[dict[str, Any]] | None = None,
    effective: bool = True,
    omit_entry_source_id: bool = False,
) -> tuple[Path, Path]:
    records = chunks or [synthetic_chunk()]
    chunks_dir = root / "approved"
    chunks_dir.mkdir(parents=True)
    with (chunks_dir / "synthetic.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in records:
            handle.write(json.dumps(chunk, ensure_ascii=False))
            handle.write("\n")

    entries = []
    for chunk in records:
        entry = {
            "source_number": 1,
            "source_title": "Synthetic Care Guide",
            "source_version": "synthetic-v1",
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "text_sha256": sha256_text(chunk.get("text", "")),
            "embedding_text_sha256": sha256_text(chunk.get("embedding_text", "")),
        }
        if not omit_entry_source_id:
            entry["source_id"] = "synthetic_source"
        entries.append(entry)
    manifest = {
        "schema_version": "test-v1",
        "status": (
            "EFFECTIVE"
            if effective
            else "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE"
        ),
        "source_count": 1,
        "chunk_count": len(entries),
        "sources": [
            {
                "source_number": 1,
                "source_id": "synthetic_source",
                "chunk_count": len(entries),
            }
        ],
        "entries": entries,
        "project_owner_risk_acceptance": "SIGNED" if effective else "NOT_SIGNED",
        "human_source_review": "NOT_COMPLETED",
        "production_status": "BLOCKED",
    }
    manifest_path = root / "allowlist.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path, chunks_dir


@pytest.fixture
def dataset(tmp_path: Path) -> tuple[Path, Path]:
    return write_dataset(tmp_path)
