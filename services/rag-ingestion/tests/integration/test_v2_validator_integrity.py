from __future__ import annotations

import hashlib
import json
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CANDIDATE = REPOSITORY_ROOT / "data" / "rag-v2" / "candidates" / "v001"
V1_SCHEMA = REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.schema.json"
V2_SCHEMA = REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.1.schema.json"
VALIDATOR = runpy.run_path(
    str(REPOSITORY_ROOT / "scripts" / "rag" / "validate_v2_artifacts.py"),
    run_name="rag_v2_validator_integrity_test",
)
validate_candidate = VALIDATOR["validate_candidate"]
CandidateValidationError = VALIDATOR["CandidateValidationError"]
validate_record_integrity = VALIDATOR["_validate_record_integrity"]
validate_test_evidence = VALIDATOR["_validate_test_evidence"]
validate_candidate_text_bytes = VALIDATOR["_validate_candidate_text_bytes"]
normalize_collected_node_id = VALIDATOR["_normalize_collected_node_id"]
validate_inventory_evidence = VALIDATOR["_validate_inventory_evidence"]
expected_inventory_paths = VALIDATOR["_expected_inventory_paths"]
validate_allowlist = VALIDATOR["_validate_allowlist"]
validate_crosswalk = VALIDATOR["_validate_crosswalk"]
VALIDATION_FIXED_PATHS = VALIDATOR["_VALIDATION_FIXED_PATHS"]
PRIOR_FORMAL_PATHS = VALIDATOR["_PRIOR_FORMAL_PATHS"]


def test_checked_in_candidate_passes_integrity_validation() -> None:
    summary = validate_candidate(CANDIDATE, V1_SCHEMA)

    assert summary["status"] == "PASS"
    assert summary["artifact_version"] == "v001"
    assert summary["chunk_count"] == 726


def test_validator_node_normalization_preserves_escaped_parameter_ids() -> None:
    node_id = r"tests\unit\test_cli.py::test_reason[unsafe\nreason]"

    assert normalize_collected_node_id(node_id) == (
        r"tests/unit/test_cli.py::test_reason[unsafe\nreason]"
    )


def test_text_tampering_fails_even_after_outer_checksums_are_rebuilt(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "v001"
    shutil.copytree(CANDIDATE, candidate)
    chunk_path = sorted((candidate / "chunks").glob("*.jsonl"))[0]
    lines = chunk_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    text = record["content"]["text"]
    record["content"]["text"] = ("X" if text[0] != "X" else "Y") + text[1:]
    lines[0] = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    chunk_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    _rewrite_checksums(candidate)

    with pytest.raises(CandidateValidationError, match="text_sha256 mismatch"):
        validate_candidate(candidate, V1_SCHEMA)


def test_v2_research_record_rejects_official_only_citation_urls() -> None:
    record = _v2_record(official=False)
    record["citation"]["direct_source_url"] = record["citation"]["direct_official_source_url"]
    record["citation"]["source_page_url"] = record["citation"]["official_source_page_url"]

    with pytest.raises(
        CandidateValidationError,
        match="research source uses an official-only citation URL",
    ):
        validate_record_integrity(
            record,
            candidate_version="v002",
            repository_root=REPOSITORY_ROOT,
            prior_cache={},
        )


def test_v2_official_record_requires_matching_neutral_citation_urls() -> None:
    record = _v2_record(official=True)
    record["citation"]["direct_source_url"] = None
    record["citation"]["source_page_url"] = record["citation"]["official_source_page_url"]

    with pytest.raises(
        CandidateValidationError,
        match="official citation URL aliases differ",
    ):
        validate_record_integrity(
            record,
            candidate_version="v002",
            repository_root=REPOSITORY_ROOT,
            prior_cache={},
        )


@pytest.mark.parametrize(
    ("page_start", "page_end", "expected_message"),
    (
        (1, None, "page range is incomplete"),
        (None, 1, "page range is incomplete"),
        (2, 1, "page range is reversed"),
        (True, 1, "positive integers"),
        ("1", 1, "positive integers"),
    ),
)
def test_citation_page_ranges_fail_closed(
    page_start: Any,
    page_end: Any,
    expected_message: str,
) -> None:
    record = _first_record(official=True)
    citation = record["citation"]
    citation["physical_page_start"] = page_start
    citation["physical_page_end"] = page_end

    with pytest.raises(CandidateValidationError, match=expected_message):
        validate_record_integrity(
            record,
            candidate_version="v001",
            repository_root=REPOSITORY_ROOT,
            prior_cache={},
        )


@pytest.mark.parametrize("candidate_version", ("v001", "v002"))
def test_citation_without_pages_requires_version_appropriate_fallback(
    candidate_version: str,
) -> None:
    record = (
        _first_record(official=True) if candidate_version == "v001" else _v2_record(official=True)
    )
    citation = record["citation"]
    for field in (
        "physical_page_start",
        "physical_page_end",
        "printed_page_start",
        "printed_page_end",
    ):
        citation[field] = None
    citation["source_locator"] = None
    if candidate_version == "v001":
        citation["direct_official_source_url"] = None
        citation["official_source_page_url"] = None
    else:
        citation["direct_source_url"] = None
        citation["source_page_url"] = None

    with pytest.raises(CandidateValidationError, match="lacks a source locator or URL"):
        validate_record_integrity(
            record,
            candidate_version=candidate_version,
            repository_root=REPOSITORY_ROOT,
            prior_cache={},
        )


def test_v2_rejects_legacy_successor_chunk_id() -> None:
    record = _first_record(official=True)
    record["artifact_version"] = "v002"
    record["identity"]["chunk_file_id"] = f"{record['identity']['source_id']}_rag_v2_v002"

    with pytest.raises(CandidateValidationError, match="deterministic chunk_id mismatch"):
        validate_record_integrity(
            record,
            candidate_version="v002",
            repository_root=REPOSITORY_ROOT,
            prior_cache={},
        )


def test_v2_crosswalk_requires_explicit_supersession_linkage(tmp_path: Path) -> None:
    record = _v2_record(official=True)
    identity = record["identity"]
    chunk_id = identity["chunk_id"]
    row = {
        "schema_version": "1.0.0",
        "artifact_version": "v002",
        "source_id": identity["source_id"],
        "prior_chunk_id": identity["prior_chunk_id"],
        "supersedes_artifact_version": "v001",
        "supersedes_chunk_id": (f"{identity['source_id']}_rag_v2_{identity['chunk_index']:04d}"),
        "successor_chunk_id": chunk_id,
        "relationship": "metadata_successor",
        "prior_artifact_path": record["provenance"]["prior_artifact_path"],
        "text_sha256_equal": True,
        "embedding_text_sha256_equal": True,
        "status_change_recommendation": "human_review_required",
        "status_changed_automatically": False,
    }
    path = tmp_path / "chunk-id-crosswalk-v002.jsonl"
    _write_jsonl_row(path, row)
    validate_crosswalk(path, candidate_version="v002", records_by_id={chunk_id: record})

    row["supersedes_chunk_id"] = identity["prior_chunk_id"]
    _write_jsonl_row(path, row)
    with pytest.raises(CandidateValidationError, match="crosswalk linkage mismatch"):
        validate_crosswalk(
            path,
            candidate_version="v002",
            records_by_id={chunk_id: record},
        )


def test_v2_allowlist_requires_explicit_supersession_linkage(tmp_path: Path) -> None:
    record = _v2_record(official=True)
    identity = record["identity"]
    content = record["content"]
    source_id = identity["source_id"]
    chunk_id = identity["chunk_id"]
    entry = {
        "source_id": source_id,
        "source_number": 1,
        "chunk_id": chunk_id,
        "prior_chunk_id": identity["prior_chunk_id"],
        "supersedes_artifact_version": "v001",
        "supersedes_chunk_id": (f"{source_id}_rag_v2_{identity['chunk_index']:04d}"),
        "chunk_index": identity["chunk_index"],
        "text_sha256": content["text_sha256"],
        "embedding_text_sha256": content["embedding_text_sha256"],
        "retrieval_eligible": record["retrieval_policy"]["retrieval_eligible"],
        "allowed_use": "INTERNAL_EMERGENCY_DEMO_ONLY",
        "signature_required": True,
        "review_status": "needs_review",
        "human_source_review": "NOT_COMPLETED",
        "embedding_status": "NOT_STARTED",
        "opensearch_indexing_status": "NOT_STARTED",
        "production_gate": "BLOCKED",
    }
    allowlist = {
        "schema_version": "v003",
        "artifact_version": "v002",
        "status": "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE",
        "allowed_use": "INTERNAL_EMERGENCY_DEMO_ONLY",
        "supersedes_allowlist_sha256": hashlib.sha256(
            (
                REPOSITORY_ROOT
                / "data/rag-manifest/AI_Reviewed_Embedding_Staging_Allowlist_v002.json"
            ).read_bytes()
        ).hexdigest(),
        "source_count": 1,
        "chunk_count": 1,
        "sources": [
            {
                "source_id": source_id,
                "source_number": 1,
                "chunk_count": 1,
                "successor_artifact_version": "v002",
                "review_status": "needs_review",
                "human_source_review": "NOT_COMPLETED",
                "production_gate": "BLOCKED",
                "storage_target": "local_pending_upload",
            }
        ],
        "entries": [entry],
        "public_redistribution_allowed": False,
        "project_owner_risk_acceptance": "NOT_SIGNED",
        "human_source_review": "NOT_COMPLETED",
        "embedding_status": "NOT_STARTED",
        "opensearch_indexing_status": "NOT_STARTED",
        "production_status": "BLOCKED",
    }
    allowlist_path = tmp_path / "embedding-staging-allowlist-v003.json"
    validate_allowlist(
        allowlist,
        allowlist_path=allowlist_path,
        candidate_version="v002",
        repository_root=REPOSITORY_ROOT,
        records_by_id={chunk_id: record},
        records_by_source={source_id: [record]},
    )

    entry["supersedes_artifact_version"] = "v000"
    with pytest.raises(
        CandidateValidationError,
        match="allowlist supersedes_artifact_version linkage mismatch",
    ):
        validate_allowlist(
            allowlist,
            allowlist_path=allowlist_path,
            candidate_version="v002",
            repository_root=REPOSITORY_ROOT,
            records_by_id={chunk_id: record},
            records_by_source={source_id: [record]},
        )


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (b"\xef\xbb\xbfplain UTF-8\n", "UTF-8 BOM"),
        (b"line one\r\nline two\r\n", "LF-only"),
        (b"line one\rline two\n", "LF-only"),
    ],
    ids=("bom", "crlf", "lone-cr"),
)
def test_candidate_text_byte_gate_rejects_noncanonical_bytes(
    tmp_path: Path,
    payload: bytes,
    expected_message: str,
) -> None:
    candidate = tmp_path / "v002"
    candidate.mkdir()
    (candidate / "artifact.txt").write_bytes(payload)

    with pytest.raises(CandidateValidationError, match=expected_message):
        validate_candidate_text_bytes(candidate)


def test_formal_validation_rejects_nonrepository_schema(tmp_path: Path) -> None:
    alternate_schema = tmp_path / "rag-chunk-v2.schema.json"
    shutil.copyfile(V2_SCHEMA, alternate_schema)

    with pytest.raises(
        CandidateValidationError,
        match="requires the repository RagChunkV2 schema",
    ):
        validate_candidate(
            CANDIDATE,
            alternate_schema,
            require_test_evidence=True,
        )


def test_formal_evidence_chain_validates_and_detects_copied_junit_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    monkeypatch.setenv("PYTEST_ADDOPTS", "--definitely-not-a-valid-pytest-option")

    validate_test_evidence(
        candidate,
        candidate_version="v002",
        repository_root=repository_root,
        require_test_evidence=True,
    )
    copied_junit = candidate / "reports" / "pytest-rag-ingestion-v002.xml"
    copied_junit.write_text(
        copied_junit.read_text(encoding="utf-8").replace("test_ok", "test_tampered"),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(CandidateValidationError, match="copied JUnit SHA-256"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_rejects_self_consistent_uncollected_testcase(
    tmp_path: Path,
) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    active_junit = repository_root / "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml"
    junit = active_junit.read_text(encoding="utf-8").replace(
        'name="test_ok"',
        'name="not_the_collected_test"',
    )
    evidence = _synchronize_formal_junit(repository_root, candidate, junit)
    evidence["testcase_identity_sha256"] = _canonical_json_sha256(
        [{"classname": "tests.test_demo", "name": "not_the_collected_test"}]
    )
    _write_json(candidate / "reports/test-evidence-v002.json", evidence)

    with pytest.raises(CandidateValidationError, match="independent collection"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_recomputes_testcase_failure_children(tmp_path: Path) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    active_junit = repository_root / "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml"
    junit = active_junit.read_text(encoding="utf-8").replace(
        'file="tests\\test_demo.py" />',
        'file="tests\\test_demo.py"><failure>failed</failure></testcase>',
    )
    _synchronize_formal_junit(repository_root, candidate, junit)

    with pytest.raises(CandidateValidationError, match="failures.*suite totals"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_rejects_all_skipped_suite(tmp_path: Path) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    active_junit = repository_root / "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml"
    junit = (
        active_junit.read_text(encoding="utf-8")
        .replace('skipped="0"', 'skipped="1"')
        .replace(
            'file="tests\\test_demo.py" />',
            'file="tests\\test_demo.py"><skipped /></testcase>',
        )
    )
    evidence = _synchronize_formal_junit(repository_root, candidate, junit)
    evidence["skipped"] = 1
    _write_json(candidate / "reports/test-evidence-v002.json", evidence)

    with pytest.raises(CandidateValidationError, match="skipped tests"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_rejects_unknown_report_fields(tmp_path: Path) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    evidence_path = candidate / "reports/test-evidence-v002.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["production_status"] = "APPROVED"
    _write_json(evidence_path, evidence)

    with pytest.raises(CandidateValidationError, match="missing or unexpected fields"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_rejects_self_consistent_failed_execution_receipt(
    tmp_path: Path,
) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    active_receipt = repository_root / "data/rag-v2/evidence/v003/pytest-execution-receipt.json"
    copied_receipt = candidate / "reports/pytest-execution-receipt-v002.json"
    receipt = json.loads(active_receipt.read_text(encoding="utf-8"))
    receipt["exit_code"] = 1
    _write_json(active_receipt, receipt)
    shutil.copyfile(active_receipt, copied_receipt)
    evidence_path = candidate / "reports/test-evidence-v002.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["execution_receipt_sha256"] = hashlib.sha256(active_receipt.read_bytes()).hexdigest()
    evidence["pytest_exit_code"] = 1
    _write_json(evidence_path, evidence)

    with pytest.raises(CandidateValidationError, match="execution receipt exit_code"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_rejects_fictional_executed_argv(tmp_path: Path) -> None:
    repository_root, candidate = _write_formal_evidence_fixture(tmp_path)
    active_receipt = repository_root / "data/rag-v2/evidence/v003/pytest-execution-receipt.json"
    copied_receipt = candidate / "reports/pytest-execution-receipt-v002.json"
    receipt = json.loads(active_receipt.read_text(encoding="utf-8"))
    receipt["executed_argv"][4] = "--junitxml=" + str(
        (repository_root / "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml").resolve()
    )
    _write_json(active_receipt, receipt)
    shutil.copyfile(active_receipt, copied_receipt)
    evidence_path = candidate / "reports/test-evidence-v002.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["execution_receipt_sha256"] = hashlib.sha256(active_receipt.read_bytes()).hexdigest()
    _write_json(evidence_path, evidence)

    with pytest.raises(CandidateValidationError, match="outside its recorded pending run"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=repository_root,
            require_test_evidence=True,
        )


def test_formal_evidence_rejects_not_required_status(tmp_path: Path) -> None:
    candidate = tmp_path / "v002"
    _write_json(
        candidate / "reports" / "test-evidence-v002.json",
        {"artifact_version": "v002", "status": "NOT_REQUIRED"},
    )

    with pytest.raises(CandidateValidationError, match="requires passing test evidence"):
        validate_test_evidence(
            candidate,
            candidate_version="v002",
            repository_root=tmp_path,
            require_test_evidence=True,
        )


def test_inventory_rejects_a_self_consistent_declared_subset(tmp_path: Path) -> None:
    repository_root, _ = _write_formal_evidence_fixture(tmp_path)
    inventory_path = (
        repository_root
        / "data"
        / "rag-v2"
        / "preflight"
        / "v003"
        / "validation-input-inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["entries"] = inventory["entries"][1:]
    inventory["entry_count"] = len(inventory["entries"])
    inventory["inventory_sha256"] = _canonical_json_sha256(inventory["entries"])
    _write_json(inventory_path, inventory)

    with pytest.raises(CandidateValidationError, match="path set is incomplete"):
        validate_inventory_evidence(
            inventory_path,
            repository_root=repository_root,
            expected_version="v003",
            expected_kind="validation_input_inventory",
            expected_file_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
            expected_inventory_sha256=inventory["inventory_sha256"],
        )


@pytest.mark.parametrize(
    "inventory_kind",
    ("validation_input_inventory", "prior_artifact_immutable_lock"),
    ids=("validation-inventory", "prior-lock"),
)
@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    (
        ("whitespace", "deterministic JSON form"),
        ("reformat", "deterministic JSON form"),
        ("bom", "BOM"),
        ("crlf", "LF-only"),
        ("invalid-utf8", "not UTF-8"),
    ),
)
def test_preflight_documents_require_exact_utf8_lf_deterministic_bytes(
    tmp_path: Path,
    inventory_kind: str,
    mutation: str,
    expected_message: str,
) -> None:
    repository_root, _ = _write_formal_evidence_fixture(tmp_path)
    filename = (
        "validation-input-inventory.json"
        if inventory_kind == "validation_input_inventory"
        else "prior-artifact-lock.json"
    )
    path = repository_root / "data/rag-v2/preflight/v003" / filename
    document = json.loads(path.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    if mutation == "whitespace":
        mutated = raw + b" \n"
    elif mutation == "reformat":
        mutated = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    elif mutation == "bom":
        mutated = b"\xef\xbb\xbf" + raw
    elif mutation == "crlf":
        mutated = raw.replace(b"\n", b"\r\n")
    else:
        mutated = raw + b"\xff"
    path.write_bytes(mutated)

    with pytest.raises(CandidateValidationError, match=expected_message):
        validate_inventory_evidence(
            path,
            repository_root=repository_root,
            expected_version="v003",
            expected_kind=inventory_kind,
            expected_file_sha256=hashlib.sha256(mutated).hexdigest(),
            expected_inventory_sha256=document["inventory_sha256"],
        )


def test_validator_inventory_path_sets_match_the_builder(tmp_path: Path) -> None:
    from rag_ingestion import v2_artifacts

    repository_root = tmp_path / "repository"
    _seed_inventory_repository(repository_root)

    builder_validation = {
        entry["path"] for entry in v2_artifacts._validation_inventory_entries(repository_root)
    }
    builder_prior = {entry["path"] for entry in v2_artifacts._prior_lock_entries(repository_root)}

    assert (
        expected_inventory_paths(repository_root, "validation_input_inventory")
        == builder_validation
    )
    assert (
        expected_inventory_paths(repository_root, "prior_artifact_immutable_lock") == builder_prior
    )


def _rewrite_checksums(candidate: Path) -> None:
    entries = []
    for path in sorted(candidate.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append(f"{digest}  {path.relative_to(candidate).as_posix()}")
    (candidate / "SHA256SUMS.txt").write_text(
        "\n".join(entries) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _first_record(*, official: bool) -> dict[str, Any]:
    for path in sorted((CANDIDATE / "chunks").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["provenance"]["is_official_source"] is official:
                return record
    raise AssertionError(f"candidate contains no official={official} record")


def _v2_record(*, official: bool) -> dict[str, Any]:
    record = _first_record(official=official)
    identity = record["identity"]
    source_id = identity["source_id"]
    chunk_index = identity["chunk_index"]
    record["artifact_version"] = "v002"
    identity["chunk_id"] = f"{source_id}_rag_v2_v002_{chunk_index:04d}"
    identity["chunk_file_id"] = f"{source_id}_rag_v2_v002"
    return record


def _write_formal_evidence_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repository_root = tmp_path / "repository"
    candidate = tmp_path / "v002"
    _seed_inventory_repository(repository_root)
    inventory_entries = _inventory_entries(
        repository_root,
        expected_inventory_paths(repository_root, "validation_input_inventory"),
    )
    prior_entries = _inventory_entries(
        repository_root,
        expected_inventory_paths(repository_root, "prior_artifact_immutable_lock"),
    )
    inventory_digest = _canonical_json_sha256(inventory_entries)
    prior_digest = _canonical_json_sha256(prior_entries)
    preflight_root = repository_root / "data" / "rag-v2" / "preflight" / "v003"
    inventory_path = preflight_root / "validation-input-inventory.json"
    prior_lock_path = preflight_root / "prior-artifact-lock.json"
    _write_json(
        inventory_path,
        {
            "schema_version": "1.0.0",
            "artifact_version": "v003",
            "kind": "validation_input_inventory",
            "hash_mode": "sha256_utf8_lf_raw_bytes_v1",
            "entry_count": len(inventory_entries),
            "inventory_sha256": inventory_digest,
            "entries": inventory_entries,
        },
    )
    _write_json(
        prior_lock_path,
        {
            "schema_version": "1.0.0",
            "artifact_version": "v003",
            "kind": "prior_artifact_immutable_lock",
            "hash_mode": "sha256_utf8_lf_raw_bytes_v1",
            "entry_count": len(prior_entries),
            "inventory_sha256": prior_digest,
            "entries": prior_entries,
            "scope": (
                "prior V1 formal inputs and every non-active RagV2 candidate, "
                "preflight, and evidence file"
            ),
            "active_exclusions": [
                {
                    "path": "data/rag-v2/candidates/v002",
                    "reason": ("active successor candidate; excluded to avoid self-reference"),
                },
                {
                    "path": "data/rag-v2/preflight/v003",
                    "reason": "active preflight; excluded to avoid self-reference",
                },
                {
                    "path": "data/rag-v2/evidence/v003",
                    "reason": "active test evidence; bound separately after preflight",
                },
            ],
        },
    )
    testcase_identity = {
        "classname": "tests.test_demo",
        "name": "test_ok",
    }
    testcase_digest = _canonical_json_sha256([testcase_identity])
    collected_node_ids = ["tests/test_demo.py::test_ok"]
    collected_node_digest = _canonical_json_sha256(collected_node_ids)
    junit = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites name="pytest tests"><testsuite name="pytest" tests="1" '
        'failures="0" errors="0" skipped="0" time="0.125" '
        'timestamp="2026-08-20T12:00:00+08:00">'
        '<properties><property name="validation_input_inventory_sha256" '
        f'value="{inventory_digest}" />'
        '<property name="collected_test_node_hash_mode" '
        'value="sha256_canonical_json_v1" />'
        '<property name="collected_test_node_ids_sha256" '
        f'value="{collected_node_digest}" />'
        '<property name="collected_test_node_count" value="1" /></properties>'
        '<testcase classname="tests.test_demo" name="test_ok" '
        'file="tests\\test_demo.py" /></testsuite></testsuites>\n'
    )
    active_junit = (
        repository_root / "data" / "rag-v2" / "evidence" / "v003" / "pytest-rag-ingestion.xml"
    )
    active_junit.parent.mkdir(parents=True)
    active_junit.write_text(junit, encoding="utf-8", newline="\n")
    copied_junit = candidate / "reports" / "pytest-rag-ingestion-v002.xml"
    copied_junit.parent.mkdir(parents=True)
    copied_junit.write_text(junit, encoding="utf-8", newline="\n")
    junit_sha256 = hashlib.sha256(active_junit.read_bytes()).hexdigest()
    receipt = {
        "schema_version": "1.0.0",
        "artifact_version": "v002",
        "preflight_version": "v003",
        "evidence_version": "v003",
        "status": "PASS",
        "display_command": (
            "python -m pytest services/rag-ingestion/tests --junitxml="
            "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml"
        ),
        "executed_argv": [
            str(Path(sys.executable).resolve()),
            "-m",
            "pytest",
            "services/rag-ingestion/tests",
            "--junitxml="
            + str(
                (
                    repository_root
                    / "data/rag-v2/.pending/evidence-v003-fixture/v003"
                    / "pytest-rag-ingestion.xml"
                ).resolve()
            ),
        ],
        "exit_code": 0,
        "validation_input_inventory_sha256": inventory_digest,
        "preflight_inventory_path": ("data/rag-v2/preflight/v003/validation-input-inventory.json"),
        "preflight_inventory_file_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        "prior_artifact_lock_sha256": prior_digest,
        "prior_artifact_lock_path": ("data/rag-v2/preflight/v003/prior-artifact-lock.json"),
        "prior_artifact_lock_file_sha256": hashlib.sha256(prior_lock_path.read_bytes()).hexdigest(),
        "junit_path": "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml",
        "junit_sha256": junit_sha256,
        "started_at": "2026-08-20T11:59:59+08:00",
        "finished_at": "2026-08-20T12:00:01+08:00",
        "failure_reasons": [],
        "production_approved": False,
    }
    active_receipt = (
        repository_root / "data" / "rag-v2" / "evidence" / "v003" / "pytest-execution-receipt.json"
    )
    _write_json(active_receipt, receipt)
    copied_receipt = candidate / "reports" / "pytest-execution-receipt-v002.json"
    copied_receipt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(active_receipt, copied_receipt)
    receipt_sha256 = hashlib.sha256(active_receipt.read_bytes()).hexdigest()
    _write_json(
        candidate / "reports" / "validation-report-v002.json",
        {
            "artifact_version": "v002",
            "preflight_version": "v003",
            "status": "PASS",
            "fail_count": 0,
            "validation_input_inventory_sha256": inventory_digest,
            "prior_artifact_lock_sha256": prior_digest,
            "production_approved": False,
        },
    )
    _write_json(
        candidate / "reports" / "test-evidence-v002.json",
        {
            "schema_version": "1.0.0",
            "artifact_version": "v002",
            "evidence_version": "v003",
            "preflight_version": "v003",
            "status": "PASS",
            "command": receipt["display_command"],
            "evidence_runner_command": ("python scripts/rag/build_v2_artifacts.py evidence"),
            "evidence_path": "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml",
            "evidence_sha256": junit_sha256,
            "validation_input_inventory_sha256": inventory_digest,
            "junit_validation_input_inventory_sha256": inventory_digest,
            "preflight_inventory_path": (
                "data/rag-v2/preflight/v003/validation-input-inventory.json"
            ),
            "preflight_inventory_file_sha256": hashlib.sha256(
                inventory_path.read_bytes()
            ).hexdigest(),
            "prior_artifact_lock_sha256": prior_digest,
            "prior_artifact_lock_path": ("data/rag-v2/preflight/v003/prior-artifact-lock.json"),
            "prior_artifact_lock_file_sha256": hashlib.sha256(
                prior_lock_path.read_bytes()
            ).hexdigest(),
            "execution_receipt_path": ("data/rag-v2/evidence/v003/pytest-execution-receipt.json"),
            "execution_receipt_sha256": receipt_sha256,
            "pytest_exit_code": 0,
            "pytest_started_at": receipt["started_at"],
            "pytest_finished_at": receipt["finished_at"],
            "testcase_identity_hash_mode": "sha256_canonical_json_v1",
            "testcase_identity_sha256": testcase_digest,
            "testcase_identity_count": 1,
            "testcase_files": ["tests/test_demo.py"],
            "testcase_classnames": ["tests.test_demo"],
            "collection_command": (
                "python -m pytest services/rag-ingestion/tests --collect-only -q"
            ),
            "collected_test_node_hash_mode": "sha256_canonical_json_v1",
            "collected_test_node_ids_sha256": collected_node_digest,
            "collected_test_node_count": 1,
            "execution_timestamp": "2026-08-20T12:00:00+08:00",
            "execution_timestamps": ["2026-08-20T12:00:00+08:00"],
            "execution_time_seconds": 0.125,
            "tests": 1,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "regression_result": "PASS",
            "production_approved": False,
        },
    )
    return repository_root, candidate


def _synchronize_formal_junit(
    repository_root: Path,
    candidate: Path,
    junit: str,
) -> dict[str, Any]:
    active_junit = repository_root / "data/rag-v2/evidence/v003/pytest-rag-ingestion.xml"
    copied_junit = candidate / "reports/pytest-rag-ingestion-v002.xml"
    active_junit.write_text(junit, encoding="utf-8", newline="\n")
    shutil.copyfile(active_junit, copied_junit)
    junit_sha256 = hashlib.sha256(active_junit.read_bytes()).hexdigest()

    active_receipt = repository_root / "data/rag-v2/evidence/v003/pytest-execution-receipt.json"
    copied_receipt = candidate / "reports/pytest-execution-receipt-v002.json"
    receipt = json.loads(active_receipt.read_text(encoding="utf-8"))
    receipt["junit_sha256"] = junit_sha256
    _write_json(active_receipt, receipt)
    shutil.copyfile(active_receipt, copied_receipt)

    evidence_path = candidate / "reports/test-evidence-v002.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["evidence_sha256"] = junit_sha256
    evidence["execution_receipt_sha256"] = hashlib.sha256(active_receipt.read_bytes()).hexdigest()
    _write_json(evidence_path, evidence)
    return evidence


def _seed_inventory_repository(repository_root: Path) -> None:
    for relative_path in set(VALIDATION_FIXED_PATHS) | set(PRIOR_FORMAL_PATHS):
        path = repository_root / relative_path
        if relative_path.as_posix() == "services/rag-ingestion/pyproject.toml":
            _write_text(path, '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        elif path.suffix == ".py":
            _write_text(path, "# frozen fixture\n")
        elif path.suffix == ".json":
            _write_text(path, "{}\n")
        else:
            _write_text(path, "frozen fixture\n")

    _write_text(repository_root / "config/rag/fixture.yaml", "enabled: true\n")
    _write_text(
        repository_root / "contracts/schemas/rag/fixture.schema.json",
        "{}\n",
    )
    _write_text(
        repository_root / "services/rag-ingestion/src/rag_ingestion/nested/extra.py",
        "# frozen fixture\n",
    )
    _write_text(
        repository_root / "services/rag-ingestion/tests/test_demo.py",
        "def test_ok() -> None:\n    assert True\n",
    )
    _write_text(
        repository_root / "data/rag-chunks/approved/source.jsonl",
        "{}\n",
    )
    historical_candidate = repository_root / "data/rag-v2/candidates/v001"
    _write_text(historical_candidate / "README.md", "historical candidate\n")
    _rewrite_checksums(historical_candidate)
    _write_text(
        repository_root / "data/rag-v2/preflight/v001/inventory.json",
        "{}\n",
    )
    _write_text(
        repository_root / "data/rag-v2/evidence/v001/pytest.xml",
        "<testsuites />\n",
    )


def _inventory_entries(
    repository_root: Path,
    relative_paths: set[str],
) -> list[dict[str, Any]]:
    entries = []
    for relative_path in sorted(relative_paths):
        raw = (repository_root / relative_path).read_bytes()
        entries.append(
            {
                "path": relative_path,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "hash_mode": "sha256_utf8_lf_raw_bytes_v1",
            }
        )
    return entries


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _write_jsonl_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
