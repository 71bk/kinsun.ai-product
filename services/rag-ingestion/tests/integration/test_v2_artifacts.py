from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from rag_ingestion.allowlist import load_allowlist
from rag_ingestion.v2_artifacts import (
    V2ArtifactError,
    build_v2_artifacts,
    prepare_preflight,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PRIOR_ARTIFACT_PATHS = (
    REPOSITORY_ROOT / "data" / "rag-chunks" / "README.md",
    REPOSITORY_ROOT / "data" / "rag-chunks" / "SHA256SUMS.txt",
    REPOSITORY_ROOT / "data" / "rag-manifest" / "AI_Reviewed_Embedding_Staging_Allowlist_v002.json",
    REPOSITORY_ROOT / "data" / "rag-manifest" / "all_current_chunk_catalog_20260802.json",
    REPOSITORY_ROOT
    / "data"
    / "rag-manifest"
    / "AWS長照_RAG_AI_Source_Review_Current_Candidates_v002.json",
    *(REPOSITORY_ROOT / "data" / "rag-chunks" / "approved").glob("*.jsonl"),
)


def test_v2_candidate_is_complete_schema_valid_and_non_production(tmp_path: Path) -> None:
    before = {path: _sha256(path) for path in PRIOR_ARTIFACT_PATHS}
    output_root = tmp_path / "rag-v2"

    preflight = prepare_preflight(REPOSITORY_ROOT, output_root)
    summary = build_v2_artifacts(REPOSITORY_ROOT, output_root)

    assert preflight["status"] == "PREFLIGHT_FROZEN"
    assert summary.source_count == 17
    assert summary.chunk_count == 726
    assert summary.official_source_count == 14
    assert summary.official_chunk_count == 651
    assert summary.research_source_count == 3
    assert summary.research_chunk_count == 75
    assert summary.retrieval_eligible_count == 143

    candidate = summary.output_path
    schema = json.loads(
        (REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    records = []
    for path in sorted((candidate / "chunks").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            validator.validate(record)
            records.append(record)

    assert len(records) == 726
    assert len({record["identity"]["chunk_id"] for record in records}) == 726
    assert all(record["governance"]["review_status"] == "needs_review" for record in records)
    assert all(record["governance"]["production_approved"] is False for record in records)
    assert sum(record["retrieval_policy"]["retrieval_eligible"] for record in records) == 143

    crosswalk = [
        json.loads(line)
        for line in (candidate / "crosswalk" / "chunk-id-crosswalk-v001.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(crosswalk) == 726
    assert all(row["text_sha256_equal"] for row in crosswalk)
    assert all(row["embedding_text_sha256_equal"] for row in crosswalk)
    assert not any(row["status_changed_automatically"] for row in crosswalk)

    candidate_allowlist = load_allowlist(
        candidate / "manifests" / "embedding-staging-allowlist-v003.json"
    )
    assert candidate_allowlist.declared_source_count == 17
    assert candidate_allowlist.declared_chunk_count == 726
    assert candidate_allowlist.governance.effective is False
    validation = _validate_candidate(
        candidate,
        REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.schema.json",
    )
    assert validation["status"] == "PASS"
    assert validation["chunk_count"] == 726
    assert before == {path: _sha256(path) for path in PRIOR_ARTIFACT_PATHS}


def test_preflight_and_candidate_are_immutable(tmp_path: Path) -> None:
    output_root = tmp_path / "rag-v2"
    prepare_preflight(REPOSITORY_ROOT, output_root)

    with pytest.raises(V2ArtifactError, match="refuse to overwrite"):
        prepare_preflight(REPOSITORY_ROOT, output_root)

    build_v2_artifacts(REPOSITORY_ROOT, output_root)
    with pytest.raises(V2ArtifactError, match="refuse to overwrite"):
        build_v2_artifacts(REPOSITORY_ROOT, output_root)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_candidate(candidate: Path, schema: Path) -> dict[str, object]:
    namespace = runpy.run_path(
        str(REPOSITORY_ROOT / "scripts" / "rag" / "validate_v2_artifacts.py"),
        run_name="rag_v2_validator_test",
    )
    return namespace["validate_candidate"](candidate, schema)
