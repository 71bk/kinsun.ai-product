from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag_ingestion.rag_governance_closeout_acceptance import (
    CONDITIONAL_STOP_COUNT,
    PURPOSE_VERIFIED_COUNT,
    RagGovernanceCloseoutAcceptanceError,
    acceptance_document_for_test,
    build_rag_governance_closeout_acceptance,
    validate_rag_governance_closeout_acceptance,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ACCEPTANCE_ROOT = REPOSITORY_ROOT / "data/rag-v3/review/acceptance/v006"


def test_closeout_document_records_verified_and_deferred_decisions() -> None:
    document = acceptance_document_for_test(REPOSITORY_ROOT)

    purpose = document["purpose_verification"]
    assert purpose["human_verified_classification_count"] == PURPOSE_VERIFIED_COUNT
    assert purpose["needs_review_classification_count"] == 0
    assert len(purpose["decisions"]) == PURPOSE_VERIFIED_COUNT
    assert all(
        decision["decision_review_status"] == "verified" for decision in purpose["decisions"]
    )

    conditional = document["conditional_stop_decision"]
    assert conditional["affected_chunk_count"] == CONDITIONAL_STOP_COUNT
    assert conditional["runtime_policy_candidate_count"] == 0
    assert conditional["audience_review_pending_count"] == CONDITIONAL_STOP_COUNT
    assert all(
        decision["runtime_retrieval_active"] is False
        and decision["stop_normal_rag_preserved"] is True
        and decision["audience_review_status"] == "needs_review"
        for decision in conditional["decisions"]
    )


def test_closeout_builder_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v006"
    summary = build_rag_governance_closeout_acceptance(
        REPOSITORY_ROOT,
        output_path=output,
    )
    result = validate_rag_governance_closeout_acceptance(
        REPOSITORY_ROOT,
        output,
    )

    assert summary.acceptance_sha256 == result["acceptance_sha256"]
    assert result["purpose_verified_count"] == PURPOSE_VERIFIED_COUNT
    assert result["conditional_stop_count"] == CONDITIONAL_STOP_COUNT
    assert result["conditional_stop_active_count"] == 0
    with pytest.raises(RagGovernanceCloseoutAcceptanceError, match="already exists"):
        build_rag_governance_closeout_acceptance(
            REPOSITORY_ROOT,
            output_path=output,
        )


def test_committed_closeout_acceptance_is_valid() -> None:
    result = validate_rag_governance_closeout_acceptance(REPOSITORY_ROOT)
    report = json.loads((ACCEPTANCE_ROOT / "validation-report.json").read_text(encoding="utf-8"))

    assert result["status"] == "PASS"
    assert result["runtime_policy_change"] == "NOT_AUTHORIZED_BY_THIS_ACCEPTANCE"
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False
    assert report["pass_count"] == 16
    assert report["fail_count"] == 0
