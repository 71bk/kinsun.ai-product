from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rag_ingestion.staging_embedding_authorization import (
    StagingEmbeddingAuthorizationError,
    build_staging_embedding_authorization,
    validate_staging_embedding_authorization,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PRIOR_ACCEPTANCE = REPOSITORY_ROOT / "data" / "rag-v2" / "human-review" / "acceptance" / "v001"
CANDIDATE = REPOSITORY_ROOT / "data" / "rag-v2" / "candidates" / "v002"
CANONICAL_AUTHORIZATION = (
    REPOSITORY_ROOT / "data" / "rag-v2" / "human-review" / "acceptance" / "v002"
)
OWNER_ID = "IanHsu"
SIGNED_AT = "2026-08-25T11:53:14+08:00"
AUTHORIZATION = "我已覆核，簽核"


def test_authorization_binds_fixed_allowlist_without_mutating_inputs(tmp_path: Path) -> None:
    protected_before = {
        **_tree_hashes(PRIOR_ACCEPTANCE),
        **{f"candidate/{key}": value for key, value in _tree_hashes(CANDIDATE).items()},
    }
    output_root = tmp_path / "acceptance"

    summary = build_staging_embedding_authorization(
        REPOSITORY_ROOT,
        output_root,
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )
    result = validate_staging_embedding_authorization(
        REPOSITORY_ROOT,
        summary.output_path,
    )

    assert result["status"] == "PASS"
    assert result["authorization_status"] == "STAGING_EMBEDDING_AUTHORIZED"
    assert result["project_owner_id"] == OWNER_ID
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["required_document_input_type"] == "RETRIEVAL_DOCUMENT"
    assert result["required_dimension"] == 1024
    assert result["review_status"] == "needs_review"
    assert result["indexing_status"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False
    assert protected_before == {
        **_tree_hashes(PRIOR_ACCEPTANCE),
        **{f"candidate/{key}": value for key, value in _tree_hashes(CANDIDATE).items()},
    }
    assert not list((output_root / ".pending").iterdir())


def test_authorization_refuses_overwrite(tmp_path: Path) -> None:
    output_root = tmp_path / "acceptance"
    build_staging_embedding_authorization(
        REPOSITORY_ROOT,
        output_root,
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )

    with pytest.raises(StagingEmbeddingAuthorizationError, match="refuse to overwrite"):
        build_staging_embedding_authorization(
            REPOSITORY_ROOT,
            output_root,
            project_owner_id=OWNER_ID,
            signed_at=SIGNED_AT,
            authorization_statement=AUTHORIZATION,
        )


def test_validator_rejects_production_approval_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    summary = build_staging_embedding_authorization(
        REPOSITORY_ROOT,
        tmp_path / "acceptance",
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )
    acceptance_path = summary.output_path / "owner-staging-embedding-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["gates"]["production_approved"] = True
    acceptance_path.write_text(
        json.dumps(acceptance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_checksums(summary.output_path)

    with pytest.raises(StagingEmbeddingAuthorizationError, match="schema failure"):
        validate_staging_embedding_authorization(REPOSITORY_ROOT, summary.output_path)


def test_validator_rejects_unbound_allowlist_hash_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    summary = build_staging_embedding_authorization(
        REPOSITORY_ROOT,
        tmp_path / "acceptance",
        project_owner_id=OWNER_ID,
        signed_at=SIGNED_AT,
        authorization_statement=AUTHORIZATION,
    )
    acceptance_path = summary.output_path / "owner-staging-embedding-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["accepted_artifacts"]["allowlist_sha256"] = "f" * 64
    acceptance_path.write_text(
        json.dumps(acceptance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_checksums(summary.output_path)

    with pytest.raises(StagingEmbeddingAuthorizationError, match="semantics are inconsistent"):
        validate_staging_embedding_authorization(REPOSITORY_ROOT, summary.output_path)


def test_committed_staging_embedding_authorization_is_valid() -> None:
    result = validate_staging_embedding_authorization(
        REPOSITORY_ROOT,
        CANONICAL_AUTHORIZATION,
    )

    assert result["status"] == "PASS"
    assert result["project_owner_id"] == OWNER_ID
    assert result["review_status"] == "needs_review"
    assert result["indexing_status"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _rewrite_checksums(package: Path) -> None:
    entries = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
        f"{path.relative_to(package).as_posix()}"
        for path in sorted(package.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    (package / "SHA256SUMS.txt").write_text(
        "\n".join(entries) + "\n",
        encoding="utf-8",
        newline="\n",
    )
