"""Build and validate the staging runtime projection for source-family policy v002."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from rag_ingestion.source_family_policy_v2 import (
    PUBLIC_AUDIENCES,
    evaluate_ordinary_retrieval,
    validate_source_family_policy_v2,
)

RUNTIME_POLICY_VERSION = "v001"
SOURCE_POLICY_MAP_VERSION = "v002"
CANDIDATE_ARTIFACT_VERSION = "v003"
SOURCE_COUNT = 14
CHUNK_COUNT = 554
RESPONSE_METADATA_READY_COUNT = 302
HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"

SOURCE_POLICY_ROOT = Path("data/rag-v3/governance/source-family-policy/candidates/v002")
SOURCE_POLICY_PATH = SOURCE_POLICY_ROOT / "source-family-policy-map.json"
SOURCE_POLICY_CHECKSUM_PATH = SOURCE_POLICY_ROOT / "SHA256SUMS.txt"
OWNER_ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v003")
V3_CANDIDATE_ROOT = Path("data/rag-v3/candidates/v003")
V3_CHUNK_ROOT = V3_CANDIDATE_ROOT / "chunks"
CROSSWALK_PATH = V3_CANDIDATE_ROOT / "crosswalk/chunk-id-crosswalk-v003.jsonl"
SCHEMA_PATH = Path("contracts/schemas/rag/rag-source-family-runtime-policy-v1.schema.json")
RUNTIME_ROOT = Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v001")
RUNTIME_POLICY_FILENAME = "source-family-runtime-policy.json"
VALIDATION_INPUT_FILENAME = "validation-input-inventory.json"
PRIOR_LOCK_FILENAME = "prior-artifact-lock.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"

FIXED_INPUT_PATHS = (
    Path(".gitattributes"),
    SCHEMA_PATH,
    Path("scripts/rag/build_source_family_runtime_policy.py"),
    Path("scripts/rag/validate_source_family_runtime_policy.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy.py"),
    Path("services/rag-ingestion/tests/integration/" "test_source_family_runtime_policy.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/runtime_policy.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/models.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/filters.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/hybrid_search.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/client.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/postgres_backend.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/retriever.py"),
    Path("services/agent-runtime/src/agent_runtime/settings.py"),
    Path("services/agent-runtime/src/agent_runtime/app.py"),
    Path("services/agent-runtime/tests/unit/test_source_family_runtime_policy.py"),
    Path("services/agent-runtime/tests/unit/test_rag_retrieval.py"),
    Path("services/agent-runtime/tests/unit/test_postgres_rag_backend.py"),
    Path("services/agent-runtime/tests/integration/test_rag_api.py"),
    Path("config/rag/source-family-golden-queries-v001.json"),
    SOURCE_POLICY_PATH,
    SOURCE_POLICY_CHECKSUM_PATH,
    CROSSWALK_PATH,
)
PRIOR_ARTIFACT_ROOTS = (
    SOURCE_POLICY_ROOT,
    OWNER_ACCEPTANCE_ROOT,
    V3_CANDIDATE_ROOT,
)


class SourceFamilyRuntimePolicyError(ValueError):
    """Raised when runtime policy inputs, bytes, or semantics diverge."""


@dataclass(frozen=True, slots=True)
class RuntimePolicySummary:
    output_path: Path
    policy_sha256: str
    validation_input_inventory_sha256: str
    prior_artifact_lock_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "runtime_policy_version": RUNTIME_POLICY_VERSION,
            "source_policy_map_version": SOURCE_POLICY_MAP_VERSION,
            "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
            "output_path": self.output_path.as_posix(),
            "source_count": SOURCE_COUNT,
            "chunk_count": CHUNK_COUNT,
            "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
            "policy_sha256": self.policy_sha256,
            "validation_input_inventory_sha256": (self.validation_input_inventory_sha256),
            "prior_artifact_lock_sha256": self.prior_artifact_lock_sha256,
            "production_approved": False,
        }


def build_source_family_runtime_policy(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> RuntimePolicySummary:
    """Build the immutable 554-row runtime policy projection atomically."""

    root = repository_root.resolve()
    destination = (output_path or root / RUNTIME_ROOT).resolve()
    if destination.exists():
        raise SourceFamilyRuntimePolicyError(
            "source-family runtime policy already exists; refuse to overwrite"
        )
    validate_source_family_policy_v2(root)
    document = _build_runtime_policy_document(root)
    input_inventory = _inventory_document(
        "source_family_runtime_policy_validation_input_inventory",
        _validation_input_entries(root),
        "runtime schema, builder, validators, tests, Golden Queries, and formal inputs",
    )
    prior_lock = _inventory_document(
        "source_family_runtime_policy_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
        "immutable policy v002, owner acceptance v003, and candidate v003 bytes",
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    pending_root = destination.parent / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="source-family-runtime-policy-v001-", dir=pending_root)
    ).resolve()
    staged = temporary_root / RUNTIME_POLICY_VERSION
    staged.mkdir()
    try:
        _write_json(staged / RUNTIME_POLICY_FILENAME, document)
        _write_json(staged / VALIDATION_INPUT_FILENAME, input_inventory)
        _write_json(staged / PRIOR_LOCK_FILENAME, prior_lock)
        _write_json(staged / VALIDATION_REPORT_FILENAME, _validation_report())
        _write_text(staged / "README.md", _readme(document))
        _write_checksums(staged)
        result = validate_source_family_runtime_policy(root, staged)
        staged.replace(destination)
        return RuntimePolicySummary(
            output_path=destination,
            policy_sha256=result["policy_sha256"],
            validation_input_inventory_sha256=input_inventory["inventory_sha256"],
            prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
        )
    finally:
        if temporary_root.is_dir():
            shutil.rmtree(temporary_root)
        if pending_root.is_dir() and not any(pending_root.iterdir()):
            pending_root.rmdir()


def validate_source_family_runtime_policy(
    repository_root: Path,
    package: Path | None = None,
) -> dict[str, Any]:
    """Validate hashes, source bindings, schema, and exact runtime semantics."""

    root = repository_root.resolve()
    package_root = (package or root / RUNTIME_ROOT).resolve()
    if not package_root.is_dir() or package_root.name != RUNTIME_POLICY_VERSION:
        raise SourceFamilyRuntimePolicyError("runtime policy path/version is invalid")
    expected_paths = {
        "README.md",
        CHECKSUM_FILENAME,
        PRIOR_LOCK_FILENAME,
        RUNTIME_POLICY_FILENAME,
        VALIDATION_INPUT_FILENAME,
        VALIDATION_REPORT_FILENAME,
    }
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise SourceFamilyRuntimePolicyError("runtime policy package inventory is incomplete")
    _assert_text_tree(package_root)
    _validate_checksums(package_root)
    validate_source_family_policy_v2(root)
    if package_root == (root / RUNTIME_ROOT).resolve():
        _validate_frozen_inventory_document(
            package_root / VALIDATION_INPUT_FILENAME,
            expected_kind="source_family_runtime_policy_validation_input_inventory",
        )
    else:
        _validate_inventory_document(
            package_root / VALIDATION_INPUT_FILENAME,
            expected_kind="source_family_runtime_policy_validation_input_inventory",
            current_entries=_validation_input_entries(root),
        )
    _validate_inventory_document(
        package_root / PRIOR_LOCK_FILENAME,
        expected_kind="source_family_runtime_policy_prior_artifact_immutable_lock",
        current_entries=_entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
    )

    document = _read_json(package_root / RUNTIME_POLICY_FILENAME)
    schema = _read_json(root / SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise SourceFamilyRuntimePolicyError(
            f"runtime policy schema failure at {location}: {first.message}"
        )
    expected_document = _build_runtime_policy_document(root)
    if document != expected_document:
        raise SourceFamilyRuntimePolicyError("runtime policy projection is not reproducible")
    if (package_root / RUNTIME_POLICY_FILENAME).read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyError("runtime policy projection is not deterministic JSON")
    if _read_json(package_root / VALIDATION_REPORT_FILENAME) != _validation_report():
        raise SourceFamilyRuntimePolicyError("runtime policy validation report is inconsistent")
    if (package_root / "README.md").read_text(encoding="utf-8") != _readme(document):
        raise SourceFamilyRuntimePolicyError("runtime policy README is inconsistent")
    return {
        "status": "PASS",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "source_policy_map_version": SOURCE_POLICY_MAP_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "source_count": document["summary"]["source_count"],
        "chunk_count": document["summary"]["chunk_count"],
        "response_metadata_ready_count": document["summary"]["response_metadata_ready_count"],
        "policy_sha256": _sha256_file(package_root / RUNTIME_POLICY_FILENAME),
        "runtime_integration": document["gates"]["runtime_integration"],
        "golden_query": document["gates"]["golden_query"],
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _build_runtime_policy_document(root: Path) -> dict[str, Any]:
    source_policy_document = _read_json(root / SOURCE_POLICY_PATH)
    source_policies = {
        item["source_id"]: item for item in source_policy_document["source_policies"]
    }
    risk_decisions = {
        item["chunk_id"]: item["effective_risk_level"]
        for item in source_policy_document["chunk_risk_decisions"]
    }
    crosswalk_rows = _read_jsonl(root / CROSSWALK_PATH)
    crosswalk_by_successor = {row["successor_chunk_id"]: row for row in crosswalk_rows}
    if len(crosswalk_by_successor) != 726:
        raise SourceFamilyRuntimePolicyError("v003 crosswalk must contain 726 unique rows")

    chunks: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    response_ready = 0
    for path in sorted((root / V3_CHUNK_ROOT).glob("*.jsonl")):
        for record in _read_jsonl(path):
            source_id = record["identity"]["source_id"]
            source_policy = source_policies[source_id]
            decision = evaluate_ordinary_retrieval(
                record,
                source_policy,
                risk_decisions,
                actor_role="elder",
                purpose="source_lookup",
            )
            if not decision["retrieval_allowed"]:
                continue
            if source_policy["is_official_source"] is not True:
                raise SourceFamilyRuntimePolicyError(
                    "research source entered the ordinary runtime projection"
                )
            successor_chunk_id = record["identity"]["chunk_id"]
            crosswalk = crosswalk_by_successor.get(successor_chunk_id)
            if crosswalk is None:
                raise SourceFamilyRuntimePolicyError(
                    f"runtime candidate has no crosswalk: {successor_chunk_id}"
                )
            prior_chunk_id = record["identity"]["prior_chunk_id"]
            if (
                crosswalk["prior_chunk_id"] != prior_chunk_id
                or crosswalk["source_id"] != source_id
                or crosswalk["text_unchanged"] is not True
                or crosswalk["embedding_text_unchanged"] is not True
            ):
                raise SourceFamilyRuntimePolicyError(
                    f"runtime crosswalk is not byte-preserving: {successor_chunk_id}"
                )
            reuse = record["embedding_reuse"]
            if (
                reuse["source_chunk_id"] != prior_chunk_id
                or reuse["status"] != "REUSE_VERIFIED"
                or reuse["source_release_id"] != "rag-v2-v002-bab68588963b"
            ):
                raise SourceFamilyRuntimePolicyError(
                    f"runtime embedding reuse binding is invalid: {successor_chunk_id}"
                )
            retrieval = record["retrieval_policy"]
            official_assessment = retrieval["requires_official_assessment"]
            professional_assessment = retrieval["requires_professional_assessment"]
            if (
                isinstance(official_assessment, bool)
                and isinstance(professional_assessment, bool)
                and bool(retrieval["allowed_purposes"])
            ):
                response_ready += 1
            citation = record["citation"]
            provenance = record["provenance"]
            chunks.append(
                {
                    "prior_chunk_id": prior_chunk_id,
                    "chunk_id": successor_chunk_id,
                    "source_id": source_id,
                    "text_sha256": record["content"]["text_sha256"],
                    "embedding_text_sha256": record["content"]["embedding_text_sha256"],
                    "effective_risk_level": decision["effective_risk_level"],
                    "retrieval_audiences": source_policy["policy_decision"]["retrieval_audiences"],
                    "source_allowed_purposes": source_policy["policy_decision"]["allowed_purposes"],
                    "chunk_allowed_purposes": retrieval["allowed_purposes"],
                    "requires_official_assessment": official_assessment,
                    "requires_professional_assessment": professional_assessment,
                    "citation": {
                        "artifact_version": record["artifact_version"],
                        "title": citation["title"],
                        "publisher": citation["publisher"],
                        "section": citation["section"],
                        "physical_page_start": citation["physical_page_start"],
                        "physical_page_end": citation["physical_page_end"],
                        "printed_page_start": citation["printed_page_start"],
                        "printed_page_end": citation["printed_page_end"],
                        "source_locator": citation["source_locator"],
                        "direct_official_source_url": citation["direct_official_source_url"],
                        "official_source_page_url": citation["official_source_page_url"],
                        "direct_source_url": citation["direct_source_url"],
                        "source_page_url": citation["source_page_url"],
                        "is_official_source": provenance["is_official_source"],
                        "source_version": provenance["source_version"],
                        "source_version_date": provenance["source_version_date"],
                        "version_published_at": provenance["version_published_at"],
                        "source_page_updated_at": provenance["source_page_updated_at"],
                        "published_at": provenance["published_at"],
                        "last_verified_at": provenance["last_verified_at"],
                        "review_status": record["governance"]["review_status"],
                        "production_approved": False,
                    },
                }
            )
            source_ids.add(source_id)

    chunks.sort(key=lambda item: item["prior_chunk_id"])
    if len(chunks) != CHUNK_COUNT or len(source_ids) != SOURCE_COUNT:
        raise SourceFamilyRuntimePolicyError(
            f"runtime projection count mismatch: {len(source_ids)} sources/{len(chunks)} chunks"
        )
    if len({item["prior_chunk_id"] for item in chunks}) != CHUNK_COUNT:
        raise SourceFamilyRuntimePolicyError("runtime prior chunk IDs are not unique")
    if len({item["chunk_id"] for item in chunks}) != CHUNK_COUNT:
        raise SourceFamilyRuntimePolicyError("runtime successor chunk IDs are not unique")
    if response_ready != RESPONSE_METADATA_READY_COUNT:
        raise SourceFamilyRuntimePolicyError(
            f"runtime response-ready count mismatch: {response_ready}"
        )

    return {
        "schema_version": "1.0.0",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "source_policy_map_version": SOURCE_POLICY_MAP_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "STAGING_RUNTIME_CANDIDATE",
        "source_policy_binding": {
            "path": SOURCE_POLICY_PATH.as_posix(),
            "sha256": _sha256_file(root / SOURCE_POLICY_PATH),
        },
        "candidate_binding": {
            "path": V3_CANDIDATE_ROOT.as_posix(),
            "checksums_sha256": _sha256_file(root / V3_CANDIDATE_ROOT / CHECKSUM_FILENAME),
            "crosswalk_path": CROSSWALK_PATH.as_posix(),
            "crosswalk_sha256": _sha256_file(root / CROSSWALK_PATH),
            "source_release_id": "rag-v2-v002-bab68588963b",
            "embedding_profile_id": "ep-google-00a12ec45096fa9d97d9e9b6",
        },
        "global_policy": {
            "retrieval_audiences": PUBLIC_AUDIENCES,
            "retrieve_before_response_policy": True,
            "ordinary_retrieval_risk_levels": ["low", "medium"],
            "ordinary_retrieval_stop_normal_rag": False,
            "purpose_response_gate": "EVALUATE_AFTER_RETRIEVAL",
            "assessment_response_gate": ("EVALUATE_AFTER_RETRIEVAL_NULL_DENIES_RESPONSE"),
            "high_or_unknown_normal_rag": "DENY",
            "research_route": "INDEPENDENT_RESEARCH_REVIEW_REQUIRED",
            "runtime_safety_from_embedding_similarity": False,
            "production_approved": False,
        },
        "chunks": chunks,
        "summary": {
            "source_count": len(source_ids),
            "chunk_count": len(chunks),
            "response_metadata_ready_count": response_ready,
            "risk_overlay_count": len(risk_decisions),
        },
        "gates": {
            "environment": "STAGING",
            "runtime_integration": "READY_FOR_STAGING_TEST",
            "golden_query": "NOT_EXECUTED",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _validation_input_entries(root: Path) -> list[dict[str, Any]]:
    paths = list(FIXED_INPUT_PATHS)
    paths.extend(sorted((root / V3_CHUNK_ROOT).glob("*.jsonl")))
    normalized = [path if path.is_absolute() else root / path for path in paths]
    return _file_entries(root, normalized)


def _entries_for_roots(root: Path, roots: Iterable[Path]) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for relative_root in roots:
        artifact_root = root / relative_root
        if not artifact_root.is_dir():
            raise SourceFamilyRuntimePolicyError(
                f"required prior artifact root is missing: {relative_root.as_posix()}"
            )
        paths.extend(path for path in artifact_root.rglob("*") if path.is_file())
    return _file_entries(root, paths)


def _file_entries(root: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file() or not resolved.is_relative_to(root):
            raise SourceFamilyRuntimePolicyError(f"required input is missing: {path}")
        relative = resolved.relative_to(root).as_posix()
        if relative in seen:
            continue
        seen.add(relative)
        entries.append(
            {
                "path": relative,
                "bytes": resolved.stat().st_size,
                "sha256": _sha256_file(resolved),
            }
        )
    return sorted(entries, key=lambda entry: entry["path"])


def _inventory_document(
    kind: str,
    entries: Sequence[Mapping[str, Any]],
    scope: str,
) -> dict[str, Any]:
    normalized = [dict(entry) for entry in entries]
    return {
        "schema_version": "1.0.0",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "kind": kind,
        "hash_mode": HASH_MODE,
        "entry_count": len(normalized),
        "inventory_sha256": _canonical_sha256(normalized),
        "entries": normalized,
        "scope": scope,
        "production_approved": False,
    }


def _validate_inventory_document(
    path: Path,
    *,
    expected_kind: str,
    current_entries: Sequence[Mapping[str, Any]],
) -> None:
    document = _read_json(path)
    expected = _inventory_document(expected_kind, current_entries, document.get("scope", ""))
    if document != expected:
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} changed after packaging")
    if path.read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} is not deterministic JSON")


def _validate_frozen_inventory_document(path: Path, *, expected_kind: str) -> None:
    """Validate a historical inventory as sealed evidence, not current source state."""

    document = _read_json(path)
    required_keys = {
        "schema_version",
        "runtime_policy_version",
        "kind",
        "hash_mode",
        "entry_count",
        "inventory_sha256",
        "entries",
        "scope",
        "production_approved",
    }
    if set(document) != required_keys:
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} fields are invalid")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} entries are invalid")
    expected = {
        **document,
        "schema_version": "1.0.0",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "kind": expected_kind,
        "hash_mode": HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _canonical_sha256(entries),
        "production_approved": False,
    }
    if document != expected:
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} sealed evidence is invalid")
    if any(
        not isinstance(entry, dict)
        or set(entry) != {"path", "bytes", "sha256"}
        or not isinstance(entry["path"], str)
        or not isinstance(entry["bytes"], int)
        or entry["bytes"] < 0
        or not isinstance(entry["sha256"], str)
        or len(entry["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in entry["sha256"])
        for entry in entries
    ):
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} entry is invalid")
    paths = [entry["path"] for entry in entries]
    if len(paths) != len(entries) or paths != sorted(paths) or len(set(paths)) != len(paths):
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} paths are invalid")
    if path.read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyError(f"{expected_kind} is not deterministic JSON")


def _validation_report() -> dict[str, Any]:
    checks = (
        "source_policy_v002_valid",
        "source_policy_sha256_bound",
        "candidate_v003_immutable_lock_bound",
        "crosswalk_726_unique_and_byte_preserving",
        "embedding_reuse_release_and_profile_bound",
        "official_sources_only",
        "all_four_public_roles_present",
        "retrieve_before_response_policy_enabled",
        "purpose_gate_after_retrieval",
        "assessment_null_denies_response",
        "high_and_unknown_risk_excluded",
        "stop_normal_rag_excluded",
        "research_route_excluded",
        "runtime_projection_554_unique_chunks",
        "response_metadata_ready_302",
        "five_owner_risk_overlays_applied",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": "1.0.0",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
        "runtime_integration": "READY_FOR_STAGING_TEST",
        "golden_query": "NOT_EXECUTED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _readme(document: Mapping[str, Any]) -> str:
    return (
        "# Source-Family Runtime Policy v001\n\n"
        "This immutable staging projection binds policy v002 to the byte-preserving "
        "v002-to-v003 chunk crosswalk. It contains no source text, embeddings, secrets, "
        "or personal data.\n\n"
        f"- Search candidates: `{document['summary']['chunk_count']}` across "
        f"`{document['summary']['source_count']}` official sources\n"
        f"- Response-metadata-ready: "
        f"`{document['summary']['response_metadata_ready_count']}`\n"
        "- Retrieval audiences: elder, family caregiver, care professional, system admin\n"
        "- Purpose and assessment checks run after retrieval; null assessment denies response\n"
        "- High/unknown risk, stop-normal-RAG, non-current, and research records are absent\n"
        "- Golden Query: `NOT_EXECUTED`\n"
        "- External sync: `NOT_AUTHORIZED`\n"
        "- Production: `BLOCKED`\n\n"
        "Do not edit this v001 package in place.\n"
    )


def _assert_text_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
            raise SourceFamilyRuntimePolicyError(
                f"runtime policy text must be UTF-8 LF-only without BOM: {path.name}"
            )
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceFamilyRuntimePolicyError(
                f"runtime policy text is not UTF-8: {path.name}"
            ) from exc


def _validate_checksums(package: Path) -> None:
    checksum_path = package / CHECKSUM_FILENAME
    declared: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if separator != "  " or len(digest) != 64 or relative in declared:
            raise SourceFamilyRuntimePolicyError("runtime checksum line is invalid")
        declared[relative] = digest
    actual = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(declared) != actual:
        raise SourceFamilyRuntimePolicyError("runtime checksum inventory mismatch")
    for relative, digest in declared.items():
        if _sha256_file(package / relative) != digest:
            raise SourceFamilyRuntimePolicyError(f"runtime checksum mismatch: {relative}")


def _write_checksums(package: Path) -> None:
    entries = []
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name != CHECKSUM_FILENAME:
            relative = path.relative_to(package).as_posix()
            entries.append(f"{_sha256_file(path)}  {relative}\n")
    _write_text(package / CHECKSUM_FILENAME, "".join(entries))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceFamilyRuntimePolicyError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise SourceFamilyRuntimePolicyError(f"JSON root must be an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SourceFamilyRuntimePolicyError(f"cannot read JSONL: {path}") from exc
    if not lines or any(not line.strip() for line in lines):
        raise SourceFamilyRuntimePolicyError(f"JSONL contains blank lines: {path}")
    for line_number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line, object_pairs_hook=_unique_object)
        except json.JSONDecodeError as exc:
            raise SourceFamilyRuntimePolicyError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise SourceFamilyRuntimePolicyError(
                f"JSONL row must be an object at {path}:{line_number}"
            )
        rows.append(value)
    return rows


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceFamilyRuntimePolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(_json_bytes(value))


def _write_text(path: Path, value: str) -> None:
    path.write_bytes(value.encode("utf-8"))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
