from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rag_ingestion.source_family_runtime_policy_v3 import (
    PURPOSE_NEEDS_REVIEW_COUNT,
    PURPOSE_OVERLAY_COUNT,
    RESPONSE_METADATA_READY_COUNT,
    TARGET_SOURCE_ID,
    SourceFamilyRuntimePolicyV3Error,
    build_owner_purpose_classification_acceptance,
    build_source_family_runtime_policy_v3,
    validate_owner_purpose_classification_acceptance,
    validate_source_family_runtime_policy_v3,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CANONICAL_ACCEPTANCE = REPOSITORY_ROOT / "data/rag-v3/review/acceptance/v005"
CANONICAL_POLICY = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v003"
)
PRIOR_POLICY = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v002"
)


def test_runtime_v003_rebuild_is_deterministic_and_preserves_prior_bytes(
    tmp_path: Path,
) -> None:
    protected = _tree_hashes(PRIOR_POLICY)
    acceptance = tmp_path / "acceptance-v005"
    policy = tmp_path / "runtime-v003"

    build_owner_purpose_classification_acceptance(
        REPOSITORY_ROOT,
        output_path=acceptance,
    )
    summary = build_source_family_runtime_policy_v3(REPOSITORY_ROOT, output_path=policy)
    result = validate_source_family_runtime_policy_v3(REPOSITORY_ROOT, policy)

    assert (
        validate_owner_purpose_classification_acceptance(REPOSITORY_ROOT, acceptance)["status"]
        == "PASS"
    )
    assert result["response_metadata_ready_count"] == RESPONSE_METADATA_READY_COUNT
    assert summary.policy_sha256 == result["policy_sha256"]
    assert (policy / "source-family-runtime-policy.json").read_bytes() == (
        CANONICAL_POLICY / "source-family-runtime-policy.json"
    ).read_bytes()
    assert protected == _tree_hashes(PRIOR_POLICY)


def test_committed_owner_acceptance_and_runtime_v003_are_valid() -> None:
    acceptance = validate_owner_purpose_classification_acceptance(
        REPOSITORY_ROOT,
        CANONICAL_ACCEPTANCE,
    )
    policy = validate_source_family_runtime_policy_v3(REPOSITORY_ROOT, CANONICAL_POLICY)

    assert acceptance["purpose_overlay_count"] == PURPOSE_OVERLAY_COUNT
    assert acceptance["purpose_needs_review_count"] == PURPOSE_NEEDS_REVIEW_COUNT
    assert policy["response_metadata_ready_count"] == RESPONSE_METADATA_READY_COUNT
    assert policy["production_approved"] is False


def test_runtime_v003_fills_all_32_purposes_and_enables_current_core_intent() -> None:
    document = json.loads(
        (CANONICAL_POLICY / "source-family-runtime-policy.json").read_text(encoding="utf-8")
    )
    targets = [chunk for chunk in document["chunks"] if chunk["source_id"] == TARGET_SOURCE_ID]

    assert len(targets) == PURPOSE_OVERLAY_COUNT
    assert all(chunk["chunk_allowed_purposes"] for chunk in targets)
    assert all("general_information" in chunk["chunk_allowed_purposes"] for chunk in targets)
    assert all("general_information" in chunk["source_allowed_purposes"] for chunk in targets)


def test_runtime_v003_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "v003"
    build_source_family_runtime_policy_v3(REPOSITORY_ROOT, output_path=output)

    with pytest.raises(SourceFamilyRuntimePolicyV3Error, match="refuse to overwrite"):
        build_source_family_runtime_policy_v3(REPOSITORY_ROOT, output_path=output)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
