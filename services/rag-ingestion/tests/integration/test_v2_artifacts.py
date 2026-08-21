from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import rag_ingestion.v2_artifacts as v2_artifacts
from rag_ingestion.allowlist import load_allowlist
from rag_ingestion.v2_artifacts import (
    ALLOWLIST_VERSION,
    ARTIFACT_VERSION,
    CANONICAL_TEXT_HASH_MODE,
    PREFLIGHT_VERSION,
    SCHEMA_VERSION,
    TEST_EVIDENCE_PATH,
    V2ArtifactError,
    _canonical_lf_bytes,
    _validated_execution_receipt,
    _write_json_atomic_no_overwrite,
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
    assert preflight["preflight_version"] == PREFLIGHT_VERSION
    assert preflight["hash_mode"] == CANONICAL_TEXT_HASH_MODE
    assert summary.output_path.name == ARTIFACT_VERSION
    assert summary.source_count == 17
    assert summary.chunk_count == 726
    assert summary.official_source_count == 14
    assert summary.official_chunk_count == 651
    assert summary.research_source_count == 3
    assert summary.research_chunk_count == 75
    assert summary.retrieval_eligible_count == 143

    candidate = summary.output_path
    schema = json.loads(
        (
            REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.1.schema.json"
        ).read_text(encoding="utf-8")
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
    assert {record["schema_version"] for record in records} == {SCHEMA_VERSION}
    assert {record["artifact_version"] for record in records} == {ARTIFACT_VERSION}
    assert len({record["identity"]["chunk_id"] for record in records}) == 726
    assert all(
        record["identity"]["chunk_id"]
        == (
            f"{record['identity']['source_id']}_rag_v2_{ARTIFACT_VERSION}_"
            f"{record['identity']['chunk_index']:04d}"
        )
        for record in records
    )
    assert all(record["governance"]["review_status"] == "needs_review" for record in records)
    assert all(record["governance"]["production_approved"] is False for record in records)
    assert sum(record["retrieval_policy"]["retrieval_eligible"] for record in records) == 143
    for record in records:
        citation = record["citation"]
        if record["provenance"]["is_official_source"]:
            assert citation["direct_source_url"] == citation["direct_official_source_url"]
            assert citation["source_page_url"] == citation["official_source_page_url"]
        else:
            assert citation["direct_official_source_url"] is None
            assert citation["official_source_page_url"] is None

    crosswalk = [
        json.loads(line)
        for line in (candidate / "crosswalk" / f"chunk-id-crosswalk-{ARTIFACT_VERSION}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(crosswalk) == 726
    assert all(row["text_sha256_equal"] for row in crosswalk)
    assert all(row["embedding_text_sha256_equal"] for row in crosswalk)
    assert not any(row["status_changed_automatically"] for row in crosswalk)
    assert all(row["supersedes_artifact_version"] == "v001" for row in crosswalk)
    assert all(
        row["supersedes_chunk_id"]
        == row["successor_chunk_id"].replace(f"_rag_v2_{ARTIFACT_VERSION}_", "_rag_v2_")
        for row in crosswalk
    )

    enum_evidence = json.loads(
        (candidate / "governance" / f"enum-evidence-{ARTIFACT_VERSION}.json").read_text(
            encoding="utf-8"
        )
    )
    for field, field_evidence in enum_evidence["fields"].items():
        canonical_tokens = {
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            for value in field_evidence["canonical_values"]
        }
        evidence_tokens = {
            json.dumps(item["value"], ensure_ascii=False, sort_keys=True)
            for item in field_evidence["evidence"]
        }
        assert evidence_tokens == canonical_tokens
        assert len(field_evidence["evidence"]) == len(canonical_tokens)
        assert all(item["field"] == field for item in field_evidence["evidence"])
        assert all(item["path"] for item in field_evidence["evidence"])
        assert all(item["prior_chunk_id"] for item in field_evidence["evidence"])

    candidate_allowlist = load_allowlist(
        candidate / "manifests" / f"embedding-staging-allowlist-{ALLOWLIST_VERSION}.json"
    )
    assert candidate_allowlist.declared_source_count == 17
    assert candidate_allowlist.declared_chunk_count == 726
    assert candidate_allowlist.governance.effective is False
    assert all(
        entry["supersedes_artifact_version"] == "v001"
        and entry["supersedes_chunk_id"].endswith(f"_rag_v2_{entry['chunk_index']:04d}")
        for entry in candidate_allowlist.raw["entries"]
    )
    version_diff = json.loads(
        (candidate / "reports" / f"version-difference-summary-{ARTIFACT_VERSION}.json").read_text(
            encoding="utf-8"
        )
    )
    assert version_diff["prior_artifact_version"] == "v001"
    assert version_diff["successor_artifact_version"] == ARTIFACT_VERSION
    assert version_diff["underlying_v1_input_shape"] == {
        "nested_metadata_chunks": 661,
        "flat_metadata_chunks": 65,
    }
    validation = _validate_candidate(
        candidate,
        REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.1.schema.json",
    )
    assert validation["status"] == "PASS"
    assert validation["chunk_count"] == 726
    assert before == {path: _sha256(path) for path in PRIOR_ARTIFACT_PATHS}
    assert not list((output_root / ".pending").iterdir())


def test_preflight_hash_bytes_require_utf8_without_bom_and_lf_only(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.txt"
    lf_path.write_bytes(b"first\nsecond\n")
    assert _canonical_lf_bytes(lf_path) == b"first\nsecond\n"

    crlf_path = tmp_path / "crlf.txt"
    crlf_path.write_bytes(b"first\r\nsecond\r\n")
    with pytest.raises(V2ArtifactError, match="LF-only"):
        _canonical_lf_bytes(crlf_path)

    lone_cr_path = tmp_path / "lone-cr.txt"
    lone_cr_path.write_bytes(b"first\rsecond\n")
    with pytest.raises(V2ArtifactError, match="LF-only"):
        _canonical_lf_bytes(lone_cr_path)

    bom_path = tmp_path / "bom.txt"
    bom_path.write_bytes(b"\xef\xbb\xbffirst\n")
    with pytest.raises(V2ArtifactError, match="BOM"):
        _canonical_lf_bytes(bom_path)


def test_collected_node_normalization_preserves_escaped_parameter_ids() -> None:
    node_id = r"tests\unit\test_cli.py::test_reason[unsafe\nreason]"

    assert v2_artifacts._normalize_collected_node_id(node_id) == (
        r"tests/unit/test_cli.py::test_reason[unsafe\nreason]"
    )


def test_preflight_and_candidate_are_immutable(tmp_path: Path) -> None:
    output_root = tmp_path / "rag-v2"
    prepare_preflight(REPOSITORY_ROOT, output_root)

    with pytest.raises(V2ArtifactError, match="refuse to overwrite"):
        prepare_preflight(REPOSITORY_ROOT, output_root)

    build_v2_artifacts(REPOSITORY_ROOT, output_root)
    with pytest.raises(V2ArtifactError, match="refuse to overwrite"):
        build_v2_artifacts(REPOSITORY_ROOT, output_root)


def test_execution_receipt_is_atomic_immutable_and_deeply_validated(tmp_path: Path) -> None:
    junit_path = tmp_path / "pytest-rag-ingestion.xml"
    junit_path.write_bytes(b"<testsuites />\n")
    inventory_digest = "a" * 64
    inventory_file_digest = "b" * 64
    prior_digest = "c" * 64
    prior_file_digest = "d" * 64
    inventory_path = "data/rag-v2/preflight/v008/validation-input-inventory.json"
    prior_path = "data/rag-v2/preflight/v008/prior-artifact-lock.json"
    receipt = {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "preflight_version": PREFLIGHT_VERSION,
        "evidence_version": "v008",
        "status": "PASS",
        "display_command": (
            "python -m pytest services/rag-ingestion/tests --junitxml="
            f"{TEST_EVIDENCE_PATH.as_posix()}"
        ),
        "executed_argv": [
            str(Path(v2_artifacts.sys.executable).resolve()),
            "-m",
            "pytest",
            "services/rag-ingestion/tests",
            "--junitxml="
            + str(
                (
                    REPOSITORY_ROOT
                    / "data/rag-v2/.pending/evidence-v008-test/v008"
                    / TEST_EVIDENCE_PATH.name
                ).resolve()
            ),
        ],
        "exit_code": 0,
        "validation_input_inventory_sha256": inventory_digest,
        "preflight_inventory_path": inventory_path,
        "preflight_inventory_file_sha256": inventory_file_digest,
        "prior_artifact_lock_sha256": prior_digest,
        "prior_artifact_lock_path": prior_path,
        "prior_artifact_lock_file_sha256": prior_file_digest,
        "junit_path": TEST_EVIDENCE_PATH.as_posix(),
        "junit_sha256": _sha256(junit_path),
        "started_at": "2026-08-20T12:00:00+08:00",
        "finished_at": "2026-08-20T12:00:01+08:00",
        "failure_reasons": [],
        "production_approved": False,
    }
    receipt_path = tmp_path / "pytest-execution-receipt.json"
    _write_json_atomic_no_overwrite(receipt_path, receipt)
    raw_receipt = receipt_path.read_bytes()
    assert b"\r" not in raw_receipt
    assert not raw_receipt.startswith(b"\xef\xbb\xbf")

    validated = _validated_execution_receipt(
        receipt_path,
        junit_path=junit_path,
        repository_root=REPOSITORY_ROOT,
        validation_input_inventory_sha256=inventory_digest,
        preflight_inventory_path=inventory_path,
        preflight_inventory_file_sha256=inventory_file_digest,
        prior_artifact_lock_sha256=prior_digest,
        prior_artifact_lock_path=prior_path,
        prior_artifact_lock_file_sha256=prior_file_digest,
    )
    assert validated["exit_code"] == 0
    with pytest.raises(V2ArtifactError, match="already exists"):
        _write_json_atomic_no_overwrite(receipt_path, receipt)

    failed_receipt_path = tmp_path / "failed-receipt.json"
    failed_receipt = {**receipt, "exit_code": 1, "status": "FAIL"}
    _write_json_atomic_no_overwrite(failed_receipt_path, failed_receipt)
    with pytest.raises(V2ArtifactError, match="status does not match"):
        _validated_execution_receipt(
            failed_receipt_path,
            junit_path=junit_path,
            repository_root=REPOSITORY_ROOT,
            validation_input_inventory_sha256=inventory_digest,
            preflight_inventory_path=inventory_path,
            preflight_inventory_file_sha256=inventory_file_digest,
            prior_artifact_lock_sha256=prior_digest,
            prior_artifact_lock_path=prior_path,
            prior_artifact_lock_file_sha256=prior_file_digest,
        )


def test_atomic_publish_refuses_a_final_directory_that_appeared_during_gates(
    tmp_path: Path,
) -> None:
    staged = tmp_path / ".pending" / "candidate-v002-owned"
    destination = tmp_path / "candidates" / "v002"
    staged.mkdir(parents=True)
    destination.mkdir(parents=True)
    (staged / "staged.txt").write_bytes(b"staged\n")
    (destination / "existing.txt").write_bytes(b"existing\n")

    with pytest.raises(V2ArtifactError, match="appeared before atomic publish"):
        v2_artifacts._publish_pending_directory(
            staged,
            destination,
            label="candidate output",
        )
    assert (staged / "staged.txt").read_bytes() == b"staged\n"
    assert (destination / "existing.txt").read_bytes() == b"existing\n"


def test_evidence_runner_atomically_publishes_complete_passing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, output_root, inventory_digest, _ = _runner_repository(tmp_path, monkeypatch)
    calls = {"pytest": 0}
    monkeypatch.setenv("PYTEST_ADDOPTS", "--ignore=services/rag-ingestion/tests")
    monkeypatch.setenv("PYTEST_PLUGINS", "unfrozen_plugin")
    monkeypatch.setenv("PYTHONPATH", "unfrozen/path")

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "PYTEST_ADDOPTS" not in environment
        assert "PYTEST_PLUGINS" not in environment
        assert "PYTHONPATH" not in environment
        assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        if "--collect-only" in command:
            return _collected_test_result()
        calls["pytest"] += 1
        _write_fake_junit(command, inventory_digest)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(v2_artifacts.subprocess, "run", fake_run)
    result = v2_artifacts.run_test_evidence(root, output_root)

    evidence_dir = output_root / "evidence" / "v008"
    assert result["status"] == "PASS"
    assert result["exit_code"] == 0
    assert calls["pytest"] == 1
    assert {path.name for path in evidence_dir.iterdir()} == {
        "pytest-rag-ingestion.xml",
        "pytest-execution-receipt.json",
        "test-evidence.json",
    }
    receipt = json.loads(
        (evidence_dir / "pytest-execution-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["executed_argv"][:4] == [
        str(Path(v2_artifacts.sys.executable)),
        "-m",
        "pytest",
        "services/rag-ingestion/tests",
    ]
    assert "/data/rag-v2/.pending/" in receipt["executed_argv"][4].replace("\\", "/")
    assert not list((output_root / ".pending").iterdir())
    with pytest.raises(V2ArtifactError, match="refuse to overwrite"):
        v2_artifacts.run_test_evidence(root, output_root)
    assert calls["pytest"] == 1


@pytest.mark.parametrize("failure_mode", ["nonzero", "timeout"])
def test_evidence_runner_process_failure_never_publishes_active_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    root, output_root, inventory_digest, _ = _runner_repository(tmp_path, monkeypatch)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if failure_mode == "timeout":
            raise subprocess.TimeoutExpired(command, 300)
        _write_fake_junit(command, inventory_digest)
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setattr(v2_artifacts.subprocess, "run", fake_run)
    with pytest.raises(V2ArtifactError, match="nothing was published"):
        v2_artifacts.run_test_evidence(root, output_root)
    assert not (output_root / "evidence" / "v008").exists()
    assert not list((output_root / ".pending").iterdir())


def test_evidence_runner_detects_inventory_change_during_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, output_root, inventory_digest, inventory_path = _runner_repository(tmp_path, monkeypatch)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        _write_fake_junit(command, inventory_digest)
        with inventory_path.open("ab") as handle:
            handle.write(b"\n")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(v2_artifacts.subprocess, "run", fake_run)
    with pytest.raises(V2ArtifactError, match="nothing was published"):
        v2_artifacts.run_test_evidence(root, output_root)
    assert not (output_root / "evidence" / "v008").exists()
    assert not list((output_root / ".pending").iterdir())


@pytest.mark.parametrize("junit_mode", ["missing", "malformed"])
def test_evidence_runner_rejects_missing_or_malformed_junit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    junit_mode: str,
) -> None:
    root, output_root, inventory_digest, _ = _runner_repository(tmp_path, monkeypatch)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if junit_mode == "malformed":
            junit_path = Path(
                next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
            )
            junit_path.write_bytes(b"<testsuites>\n")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(v2_artifacts.subprocess, "run", fake_run)
    expected_message = "nothing was published" if junit_mode == "missing" else "unreadable"
    with pytest.raises(V2ArtifactError, match=expected_message):
        v2_artifacts.run_test_evidence(root, output_root)
    assert not (output_root / "evidence" / "v008").exists()
    assert not list((output_root / ".pending").iterdir())


@pytest.mark.parametrize(
    ("mode", "expected_message"),
    [
        ("uncollected_identity", "independent collection"),
        ("hidden_failure", "failures.*suite totals"),
        ("all_skipped", "failed, errored, or skipped tests"),
    ],
)
def test_evidence_runner_rejects_self_consistent_junit_semantic_bypasses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_message: str,
) -> None:
    root, output_root, inventory_digest, _ = _runner_repository(tmp_path, monkeypatch)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if "--collect-only" in command:
            return _collected_test_result()
        _write_fake_junit(command, inventory_digest)
        junit_path = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
        )
        junit = junit_path.read_text(encoding="utf-8")
        if mode == "uncollected_identity":
            junit = junit.replace('name="test_demo"', 'name="not_collected"')
        elif mode == "hidden_failure":
            junit = junit.replace(
                'time="0.01" />',
                'time="0.01"><failure>failed</failure></testcase>',
            )
        else:
            junit = junit.replace('skipped="0"', 'skipped="1"').replace(
                'time="0.01" />',
                'time="0.01"><skipped /></testcase>',
            )
        junit_path.write_text(junit, encoding="utf-8", newline="\n")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(v2_artifacts.subprocess, "run", fake_run)
    with pytest.raises(V2ArtifactError, match=expected_message):
        v2_artifacts.run_test_evidence(root, output_root)
    assert not (output_root / "evidence" / "v008").exists()
    assert not list((output_root / ".pending").iterdir())


@pytest.mark.parametrize("stage", ["evidence", "build"])
@pytest.mark.parametrize("preflight_file", ["inventory", "prior_lock"])
@pytest.mark.parametrize("tamper", ["reformat", "bom", "crlf"])
def test_evidence_and_build_reject_noncanonical_preflight_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    preflight_file: str,
    tamper: str,
) -> None:
    root, output_root, _, inventory_path = _runner_repository(tmp_path, monkeypatch)
    target = (
        inventory_path
        if preflight_file == "inventory"
        else inventory_path.with_name("prior-artifact-lock.json")
    )
    raw = target.read_bytes()
    if tamper == "reformat":
        raw = (
            json.dumps(
                json.loads(raw.decode("utf-8")),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
    elif tamper == "bom":
        raw = b"\xef\xbb\xbf" + raw
    else:
        raw = raw.replace(b"\n", b"\r\n")
    target.write_bytes(raw)

    expected = "canonical" if tamper == "reformat" else "BOM|LF-only"
    with pytest.raises(V2ArtifactError, match=expected):
        if stage == "evidence":
            v2_artifacts.run_test_evidence(root, output_root)
        else:
            build_v2_artifacts(root, output_root)
    assert not (output_root / "evidence" / "v008").exists()
    assert not (output_root / "candidates" / ARTIFACT_VERSION).exists()


def _runner_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str, Path]:
    root = tmp_path / "repository"
    output_root = root / "data" / "rag-v2"
    preflight_dir = output_root / "preflight" / PREFLIGHT_VERSION
    inventory_entries: list[dict[str, object]] = [
        {
            "path": "services/rag-ingestion/tests/test_demo.py",
            "size_bytes": 0,
            "sha256": "0" * 64,
            "hash_mode": CANONICAL_TEXT_HASH_MODE,
        }
    ]
    prior_entries: list[dict[str, object]] = []
    inventory = v2_artifacts._inventory_document("validation_input_inventory", inventory_entries)
    prior_lock = v2_artifacts._inventory_document("prior_artifact_immutable_lock", prior_entries)
    inventory_path = preflight_dir / "validation-input-inventory.json"
    prior_lock_path = preflight_dir / "prior-artifact-lock.json"
    v2_artifacts._write_canonical_json(inventory_path, inventory)
    v2_artifacts._write_canonical_json(prior_lock_path, prior_lock)
    monkeypatch.setattr(
        v2_artifacts,
        "_validation_inventory_entries",
        lambda _: inventory_entries,
    )
    monkeypatch.setattr(v2_artifacts, "_prior_lock_entries", lambda _: [])
    return root, output_root, inventory["inventory_sha256"], inventory_path


def _collected_test_result() -> SimpleNamespace:
    return SimpleNamespace(
        returncode=0,
        stdout="tests/test_demo.py::test_demo\n\n1 test collected in 0.01s\n",
        stderr="",
    )


def _write_fake_junit(command: list[str], inventory_digest: str) -> None:
    junit_path = Path(
        next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
    )
    node_ids = ["tests/test_demo.py::test_demo"]
    node_digest = hashlib.sha256(
        json.dumps(node_ids, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    timestamp = datetime.now().astimezone().isoformat()
    junit_path.write_bytes(
        (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites name="pytest tests"><testsuite name="pytest" errors="0" '
            f'failures="0" skipped="0" tests="1" time="0.01" timestamp="{timestamp}">'
            '<properties><property name="validation_input_inventory_sha256" '
            f'value="{inventory_digest}" />'
            '<property name="collected_test_node_hash_mode" '
            'value="sha256_canonical_json_v1" />'
            '<property name="collected_test_node_ids_sha256" '
            f'value="{node_digest}" />'
            '<property name="collected_test_node_count" value="1" /></properties>'
            '<testcase classname="tests.test_demo" name="test_demo" time="0.01" />'
            "</testsuite></testsuites>\n"
        ).encode()
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_candidate(candidate: Path, schema: Path) -> dict[str, object]:
    namespace = runpy.run_path(
        str(REPOSITORY_ROOT / "scripts" / "rag" / "validate_v2_artifacts.py"),
        run_name="rag_v2_validator_test",
    )
    return namespace["validate_candidate"](candidate, schema)
