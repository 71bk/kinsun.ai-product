from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rag_ingestion.source_family_runtime_policy_v2 import (
    OFFICIAL_NULL_TO_TRUE_COUNT,
    PROFESSIONAL_NULL_TO_TRUE_COUNT,
    RESPONSE_METADATA_READY_COUNT,
    SourceFamilyRuntimePolicyV2Error,
    build_owner_assessment_response_acceptance,
    build_source_family_runtime_policy_v2,
    validate_owner_assessment_response_acceptance,
    validate_source_family_runtime_policy_v2,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CANONICAL_ACCEPTANCE = REPOSITORY_ROOT / "data/rag-v3/review/acceptance/v004"
CANONICAL_POLICY = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v002"
)


def test_runtime_v002_rebuild_is_deterministic_and_preserves_prior_bytes(
    tmp_path: Path,
) -> None:
    protected = _tree_hashes(
        REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v001"
    )
    acceptance = tmp_path / "acceptance-v004"
    policy = tmp_path / "runtime-v002"

    build_owner_assessment_response_acceptance(
        REPOSITORY_ROOT,
        output_path=acceptance,
    )
    # The policy builder validates the canonical acceptance binding. Build the
    # policy against committed evidence, then compare its bytes independently.
    summary = build_source_family_runtime_policy_v2(REPOSITORY_ROOT, output_path=policy)
    result = validate_source_family_runtime_policy_v2(REPOSITORY_ROOT, policy)

    assert (
        validate_owner_assessment_response_acceptance(REPOSITORY_ROOT, acceptance)["status"]
        == "PASS"
    )
    assert result["response_metadata_ready_count"] == RESPONSE_METADATA_READY_COUNT
    assert summary.policy_sha256 == result["policy_sha256"]
    assert (policy / "source-family-runtime-policy.json").read_bytes() == (
        CANONICAL_POLICY / "source-family-runtime-policy.json"
    ).read_bytes()
    assert protected == _tree_hashes(
        REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v001"
    )


def test_committed_owner_acceptance_and_runtime_v002_are_valid() -> None:
    acceptance = validate_owner_assessment_response_acceptance(
        REPOSITORY_ROOT,
        CANONICAL_ACCEPTANCE,
    )
    policy = validate_source_family_runtime_policy_v2(REPOSITORY_ROOT, CANONICAL_POLICY)

    assert acceptance["professional_null_to_true_count"] == PROFESSIONAL_NULL_TO_TRUE_COUNT
    assert acceptance["official_null_to_true_count"] == OFFICIAL_NULL_TO_TRUE_COUNT
    assert policy["response_metadata_ready_count"] == RESPONSE_METADATA_READY_COUNT
    assert policy["production_approved"] is False


def test_runtime_v002_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "v002"
    build_source_family_runtime_policy_v2(REPOSITORY_ROOT, output_path=output)

    with pytest.raises(SourceFamilyRuntimePolicyV2Error, match="refuse to overwrite"):
        build_source_family_runtime_policy_v2(REPOSITORY_ROOT, output_path=output)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
