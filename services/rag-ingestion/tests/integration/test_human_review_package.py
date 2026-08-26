from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rag_ingestion.human_review_package import (
    EXPECTED_CHUNK_COUNT,
    EXPECTED_FLAGGED_COUNT,
    EXPECTED_SOURCE_COUNT,
    HumanReviewPackageError,
    build_human_review_package,
    validate_human_review_package,
    validate_human_review_package_build_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CANONICAL_PACKAGE = REPOSITORY_ROOT / "data" / "rag-v2" / "human-review" / "v001"
CANDIDATE = REPOSITORY_ROOT / "data" / "rag-v2" / "candidates" / "v002"


def test_human_review_package_covers_every_chunk_without_auto_review(tmp_path: Path) -> None:
    before = _tree_hashes(CANDIDATE)
    output_root = tmp_path / "human-review"

    summary = build_human_review_package(REPOSITORY_ROOT, output_root)
    result = validate_human_review_package(
        REPOSITORY_ROOT,
        summary.output_path,
        output_root=output_root,
    )

    assert result["status"] == "PASS"
    assert result["package_status"] == "READY_FOR_HUMAN_REVIEW"
    assert result["source_assignment_count"] == EXPECTED_SOURCE_COUNT
    assert result["chunk_assignment_count"] == EXPECTED_CHUNK_COUNT
    assert result["flagged_assignment_count"] == EXPECTED_FLAGGED_COUNT
    assert result["baseline_assignment_count"] == 78
    assert result["official_source_count"] == 14
    assert result["official_chunk_count"] == 651
    assert result["research_source_count"] == 3
    assert result["research_chunk_count"] == 75
    assert sum(result["priority_counts"].values()) == EXPECTED_CHUNK_COUNT
    assert result["review_completion_status"] == "NOT_COMPLETED"
    assert result["project_owner_risk_acceptance"] == "NOT_SIGNED"
    assert result["production_approved"] is False

    assignments = _assignment_rows(summary.output_path)
    assert len(assignments) == EXPECTED_CHUNK_COUNT
    assert all(row["human_decision"]["decision_status"] == "pending" for row in assignments)
    assert all(
        row["human_decision"]["recommended_review_status"] == "needs_review" for row in assignments
    )
    assert not any(row["production_approved"] for row in assignments)
    assert {row["review_scope"] for row in assignments} == {"flagged", "baseline"}
    assert {row["review_track"] for row in assignments} == {
        "official_source",
        "research_evidence",
    }
    assert before == _tree_hashes(CANDIDATE)
    assert not list((output_root / ".pending").iterdir())


def test_human_review_package_records_missing_local_sources_and_no_external_access(
    tmp_path: Path,
) -> None:
    summary = build_human_review_package(REPOSITORY_ROOT, tmp_path / "human-review")
    index = json.loads((summary.output_path / "source-file-index.json").read_text(encoding="utf-8"))
    owner = json.loads((summary.output_path / "owner-acceptance.json").read_text(encoding="utf-8"))

    assert index["source_count"] == EXPECTED_SOURCE_COUNT
    assert index["local_source_file_count"] == 0
    assert index["external_access_performed"] is False
    assert all(source["local_source_status"] == "not_available" for source in index["sources"])
    assert all(source["local_source_files"] == [] for source in index["sources"])
    assert owner == {
        "accepted_manifest_sha256": None,
        "allowed_use": "INTERNAL_HUMAN_REVIEW_ONLY",
        "candidate_artifact_version": "v002",
        "human_source_review": "NOT_COMPLETED",
        "package_version": "v001",
        "production_approved": False,
        "production_status": "BLOCKED",
        "project_owner_id": None,
        "schema_version": "1.0.0",
        "signed_at": None,
        "status": "NOT_SIGNED",
    }


def test_human_review_package_is_immutable(tmp_path: Path) -> None:
    output_root = tmp_path / "human-review"
    first = build_human_review_package(REPOSITORY_ROOT, output_root)
    before = _tree_hashes(first.output_path)

    with pytest.raises(HumanReviewPackageError, match="refuse to overwrite"):
        build_human_review_package(REPOSITORY_ROOT, output_root)

    assert before == _tree_hashes(first.output_path)


def test_validator_rejects_a_forged_human_approval_even_with_rewritten_checksums(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "human-review"
    summary = build_human_review_package(REPOSITORY_ROOT, output_root)
    assignment_path = next((summary.output_path / "assignments").glob("*.jsonl"))
    rows = [json.loads(line) for line in assignment_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["human_decision"]["decision_status"] = "approved"
    assignment_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_checksums(summary.output_path)

    with pytest.raises(HumanReviewPackageError, match="differ from candidate bytes"):
        validate_human_review_package(
            REPOSITORY_ROOT,
            summary.output_path,
            output_root=output_root,
        )


def test_committed_human_review_package_is_valid() -> None:
    result = validate_human_review_package_build_snapshot(REPOSITORY_ROOT, CANONICAL_PACKAGE)

    assert result["status"] == "PASS"
    assert result["chunk_assignment_count"] == EXPECTED_CHUNK_COUNT
    assert result["review_completion_status"] == "NOT_COMPLETED"
    assert result["production_approved"] is False


def _assignment_rows(package: Path) -> list[dict[str, object]]:
    rows = []
    for path in sorted((package / "assignments").glob("*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return rows


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
