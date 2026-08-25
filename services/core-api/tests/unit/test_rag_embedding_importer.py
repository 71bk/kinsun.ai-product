from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.rag_embedding_importer import (
    EmbeddingImportError,
    EmbeddingProfileBinding,
    load_embedding_import_batch,
    validated_artifact_receipt,
)
from app.rag_projection_importer import ProjectionBatch, ProjectionChunk

EXPECTED_PROFILE_ID = EmbeddingProfileBinding(
    provider="google",
    model_id="gemini-embedding-001",
    dimension=1024,
    document_task_type="RETRIEVAL_DOCUMENT",
    config_version="1.0.0",
).profile_id


def _projection() -> ProjectionBatch:
    chunk = ProjectionChunk(
        chunk_id="synthetic_rag_v2_v001_0001",
        source_id="synthetic_source",
        chunk_index=1,
        artifact_version="v001",
        schema_version="2.1.0",
        document_title="合成長照指南",
        section_title="申請方式",
        content_type="service_guide",
        language="zh-Hant",
        locale="zh-TW",
        chunk_text="合成公開資料。",
        embedding_text="合成公開資料，供文件檢索。",
        text_sha256="b" * 64,
        embedding_text_sha256="c" * 64,
        record_sha256="d" * 64,
        source_version="synthetic-v1",
        review_status="needs_review",
        current_status="current",
        risk_level="low",
        production_approved=False,
        retrieval_eligible=True,
        stop_normal_rag=False,
        requires_human_review=True,
        requires_official_assessment=False,
        requires_professional_assessment=False,
        allowed_audiences=("elder",),
        allowed_purposes=("general_information",),
        citation={"title": "合成長照指南"},
        governance={"production_approved": False},
        provenance={"source_version": "synthetic-v1"},
        retrieval_policy={"retrieval_eligible": True},
    )
    return ProjectionBatch(
        release_id="synthetic-rag-v1",
        artifact_version="v001",
        candidate_sha256="a" * 64,
        source_count=1,
        chunk_count=1,
        review_status="needs_review",
        human_source_review="NOT_COMPLETED",
        production_approved=False,
        chunks=(chunk,),
    )


def _artifact(path: Path, *, dimension: int = 1024) -> str:
    rows = [
        {
            "record_type": "manifest",
            "schema_version": "2.0.0",
            "allowlist_sha256": "e" * 64,
            "embedding_provider": "google",
            "embedding_model_id": "gemini-embedding-001",
            "embedding_dimension": dimension,
            "document_task_type": "RETRIEVAL_DOCUMENT",
            "config_version": "1.0.0",
            "chunk_count": 1,
        },
        {
            "record_type": "embedding",
            "chunk_id": "synthetic_rag_v2_v001_0001",
            "embedding_text_sha256": "c" * 64,
            "allowlist_sha256": "e" * 64,
            "embedding_model_id": "gemini-embedding-001",
            "embedding_dimension": dimension,
            "embedding": [0.125] * dimension,
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_loads_fixed_hash_profile_bound_artifact(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact = tmp_path / "external" / "embeddings.jsonl"
    artifact_sha256 = _artifact(artifact)

    batch = load_embedding_import_batch(
        artifact,
        repository_root=repository_root,
        projection=_projection(),
        expected_artifact_sha256=artifact_sha256,
        expected_allowlist_sha256="e" * 64,
        expected_profile_id=EXPECTED_PROFILE_ID,
    )
    receipt = validated_artifact_receipt(batch)

    assert batch.profile.provider == "google"
    assert batch.profile.dimension == 1024
    assert batch.records[0].vector_fingerprint
    assert receipt["status"] == "VALIDATED_DRY_RUN"
    assert receipt["database_access_performed"] is False
    assert receipt["production_approved"] is False


def test_rejects_dimension_before_database_use(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact = tmp_path / "external" / "embeddings.jsonl"
    artifact_sha256 = _artifact(artifact, dimension=8)

    with pytest.raises(EmbeddingImportError, match="dimension must be 1024"):
        load_embedding_import_batch(
            artifact,
            repository_root=repository_root,
            projection=_projection(),
            expected_artifact_sha256=artifact_sha256,
            expected_allowlist_sha256="e" * 64,
            expected_profile_id=EXPECTED_PROFILE_ID,
        )


def test_rejects_tampered_artifact_hash(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact = tmp_path / "external" / "embeddings.jsonl"
    _artifact(artifact)

    with pytest.raises(EmbeddingImportError, match="attestation does not match"):
        load_embedding_import_batch(
            artifact,
            repository_root=repository_root,
            projection=_projection(),
            expected_artifact_sha256="f" * 64,
            expected_allowlist_sha256="e" * 64,
            expected_profile_id=EXPECTED_PROFILE_ID,
        )


def test_rejects_artifact_inside_repository(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact = repository_root / "embeddings.jsonl"
    artifact_sha256 = _artifact(artifact)

    with pytest.raises(EmbeddingImportError, match="outside the repository"):
        load_embedding_import_batch(
            artifact,
            repository_root=repository_root,
            projection=_projection(),
            expected_artifact_sha256=artifact_sha256,
            expected_allowlist_sha256="e" * 64,
            expected_profile_id=EXPECTED_PROFILE_ID,
        )


def test_rejects_unattested_embedding_profile(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact = tmp_path / "external" / "embeddings.jsonl"
    artifact_sha256 = _artifact(artifact)

    with pytest.raises(EmbeddingImportError, match="profile is not attested"):
        load_embedding_import_batch(
            artifact,
            repository_root=repository_root,
            projection=_projection(),
            expected_artifact_sha256=artifact_sha256,
            expected_allowlist_sha256="e" * 64,
            expected_profile_id="ep-google-unreviewed",
        )
