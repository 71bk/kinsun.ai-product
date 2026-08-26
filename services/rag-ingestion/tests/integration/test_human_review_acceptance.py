from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rag_ingestion.human_review_acceptance import (
    HumanReviewAcceptanceError,
    build_human_review_acceptance,
    validate_human_review_acceptance,
    validate_human_review_acceptance_build_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ASSIGNMENT_PACKAGE = REPOSITORY_ROOT / "data" / "rag-v2" / "human-review" / "v001"
CANONICAL_ACCEPTANCE = REPOSITORY_ROOT / "data" / "rag-v2" / "human-review" / "acceptance" / "v001"
OWNER_ID = "IanHsu"
SIGNED_AT = "2026-08-21T17:00:00+08:00"
AUTHORIZATION = "我是 IanHsu，授權簽署風險接受文件。"


def test_owner_acceptance_is_bound_to_immutable_pending_package(tmp_path: Path) -> None:
    before = _tree_hashes(ASSIGNMENT_PACKAGE)
    output_root = tmp_path / "acceptance"

    summary = build_human_review_acceptance(
        REPOSITORY_ROOT,
        output_root,
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )
    result = validate_human_review_acceptance(REPOSITORY_ROOT, summary.output_path)

    assert result["status"] == "PASS"
    assert result["acceptance_status"] == "SIGNED"
    assert result["project_owner_id"] == OWNER_ID
    assert result["acceptance_scope"] == "INTERNAL_HUMAN_REVIEW_ONLY"
    assert result["review_completion_status"] == "NOT_COMPLETED"
    assert result["pending_source_assignments"] == 17
    assert result["pending_chunk_assignments"] == 726
    assert result["production_status"] == "BLOCKED"
    assert result["production_approved"] is False
    assert before == _tree_hashes(ASSIGNMENT_PACKAGE)
    assert not list((output_root / ".pending").iterdir())


def test_owner_acceptance_refuses_overwrite(tmp_path: Path) -> None:
    output_root = tmp_path / "acceptance"
    build_human_review_acceptance(
        REPOSITORY_ROOT,
        output_root,
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )

    with pytest.raises(HumanReviewAcceptanceError, match="refuse to overwrite"):
        build_human_review_acceptance(
            REPOSITORY_ROOT,
            output_root,
            project_owner_id=OWNER_ID,
            signed_at=SIGNED_AT,
            authorization_statement=AUTHORIZATION,
        )


def test_validator_rejects_production_approval_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    summary = build_human_review_acceptance(
        REPOSITORY_ROOT,
        tmp_path / "acceptance",
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )
    acceptance_path = summary.output_path / "owner-risk-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["production_approved"] = True
    acceptance_path.write_text(
        json.dumps(acceptance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_checksums(summary.output_path)

    with pytest.raises(HumanReviewAcceptanceError, match="schema failure"):
        validate_human_review_acceptance(REPOSITORY_ROOT, summary.output_path)


def test_validator_rejects_signature_identity_mismatch_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    summary = build_human_review_acceptance(
        REPOSITORY_ROOT,
        tmp_path / "acceptance",
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )
    acceptance_path = summary.output_path / "owner-risk-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["electronic_signature"]["signature_value"] = "SomeoneElse"
    acceptance_path.write_text(
        json.dumps(acceptance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_checksums(summary.output_path)

    with pytest.raises(HumanReviewAcceptanceError, match="semantics are inconsistent"):
        validate_human_review_acceptance(REPOSITORY_ROOT, summary.output_path)


def test_committed_owner_acceptance_is_valid() -> None:
    result = validate_human_review_acceptance_build_snapshot(
        REPOSITORY_ROOT,
        CANONICAL_ACCEPTANCE,
    )

    assert result["status"] == "PASS"
    assert result["project_owner_id"] == OWNER_ID
    assert result["review_completion_status"] == "NOT_COMPLETED"
    assert result["production_approved"] is False


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _rewrite_checksums(package: Path) -> None:
    entries = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(package).as_posix()}"
        for path in sorted(package.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    (package / "SHA256SUMS.txt").write_text(
        "\n".join(entries) + "\n",
        encoding="utf-8",
        newline="\n",
    )
