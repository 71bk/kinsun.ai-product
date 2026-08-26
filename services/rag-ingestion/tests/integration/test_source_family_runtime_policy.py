from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rag_ingestion.source_family_runtime_policy import (
    CHUNK_COUNT,
    RESPONSE_METADATA_READY_COUNT,
    SOURCE_COUNT,
    SourceFamilyRuntimePolicyError,
    build_source_family_runtime_policy,
    validate_source_family_runtime_policy,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CANONICAL_PACKAGE = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v001"
)


def test_runtime_policy_rebuild_is_deterministic_and_does_not_mutate_inputs(
    tmp_path: Path,
) -> None:
    protected = _tree_hashes(
        REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/candidates/v002"
    )
    output = tmp_path / "v001"

    summary = build_source_family_runtime_policy(REPOSITORY_ROOT, output_path=output)
    result = validate_source_family_runtime_policy(REPOSITORY_ROOT, output)

    assert result["status"] == "PASS"
    assert result["source_count"] == SOURCE_COUNT
    assert result["chunk_count"] == CHUNK_COUNT
    assert result["response_metadata_ready_count"] == RESPONSE_METADATA_READY_COUNT
    assert result["production_approved"] is False
    assert summary.policy_sha256 == result["policy_sha256"]
    assert (output / "source-family-runtime-policy.json").read_bytes() == (
        CANONICAL_PACKAGE / "source-family-runtime-policy.json"
    ).read_bytes()
    assert protected == _tree_hashes(
        REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/candidates/v002"
    )


def test_runtime_policy_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "v001"
    build_source_family_runtime_policy(REPOSITORY_ROOT, output_path=output)

    with pytest.raises(SourceFamilyRuntimePolicyError, match="refuse to overwrite"):
        build_source_family_runtime_policy(REPOSITORY_ROOT, output_path=output)


def test_committed_runtime_policy_is_valid() -> None:
    result = validate_source_family_runtime_policy(REPOSITORY_ROOT, CANONICAL_PACKAGE)

    assert result["status"] == "PASS"
    assert result["runtime_integration"] == "READY_FOR_STAGING_TEST"
    assert result["golden_query"] == "NOT_EXECUTED"
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
