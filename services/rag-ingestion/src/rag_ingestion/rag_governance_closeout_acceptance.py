"""Build the immutable Owner RAG closeout acceptance v006."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_ingestion.source_family_policy_v2 import (
    RISK_DECISION_CHUNK_IDS,
    _load_chunk_records,
)
from rag_ingestion.source_family_runtime_policy import (
    SourceFamilyRuntimePolicyError,
    _assert_text_tree,
    _entries_for_roots,
    _file_entries,
    _json_bytes,
    _read_json,
    _sha256_file,
    _validate_checksums,
    _write_checksums,
    _write_json,
    _write_text,
)
from rag_ingestion.source_family_runtime_policy_v2 import (
    SourceFamilyRuntimePolicyV2Error,
    _canonical_sha256,
    _cleanup_staging_directory,
    _inventory_document,
    _new_staging_directory,
    _publish_directory,
    _refuse_overwrite,
    _validate_inventory_document,
    _validate_package_inventory,
    _validate_schema,
)
from rag_ingestion.source_family_runtime_policy_v3 import (
    validate_owner_purpose_classification_acceptance,
    validate_source_family_runtime_policy_v3,
)

SCHEMA_VERSION = "1.0.0"
ACCEPTANCE_VERSION = "v006"
PURPOSE_VERIFIED_COUNT = 32
CONDITIONAL_STOP_COUNT = 27

OWNER_STATEMENTS = (
    "27 筆 stop_normal_rag=true，可以開放只是到時候在根據身份別確認可以檢索的內容，32筆A檢核通過",
)
SIGNED_AT = "2026-08-28T09:43:47+08:00"

V005_ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v005")
V005_ACCEPTANCE_FILE = V005_ACCEPTANCE_ROOT / "owner-purpose-classification-acceptance.json"
V005_ACCEPTANCE_SHA256 = "a447aede1d6b871afd40294f5ab39b4ad81e4fa96b9a00a83b7897576af5cd24"
V3_RUNTIME_ROOT = Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v003")
V3_RUNTIME_FILE = V3_RUNTIME_ROOT / "source-family-runtime-policy.json"
V3_RUNTIME_SHA256 = "99aa1dd6ccf90970c798664fedaff9ae3dd2f769437ebebc4a54c07478a1b5bd"
SOURCE_POLICY_ROOT = Path("data/rag-v3/governance/source-family-policy/candidates/v002")
SOURCE_POLICY_FILE = SOURCE_POLICY_ROOT / "source-family-policy-map.json"
CANDIDATE_ROOT = Path("data/rag-v3/candidates/v003")

ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v006")
ACCEPTANCE_FILE = ACCEPTANCE_ROOT / "owner-rag-closeout-acceptance.json"
ACCEPTANCE_SCHEMA_PATH = Path(
    "contracts/schemas/rag/rag-owner-rag-closeout-acceptance-v1.schema.json"
)

VALIDATION_INPUT_FILENAME = "validation-input-inventory.json"
PRIOR_LOCK_FILENAME = "prior-artifact-lock.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
MANIFEST_FILENAME = "manifest.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"

FIXED_INPUT_PATHS = (
    Path(".gitattributes"),
    ACCEPTANCE_SCHEMA_PATH,
    Path("scripts/rag/build_rag_governance_closeout_acceptance.py"),
    Path("scripts/rag/validate_rag_governance_closeout_acceptance.py"),
    Path("services/rag-ingestion/src/rag_ingestion/" "rag_governance_closeout_acceptance.py"),
    Path("services/rag-ingestion/tests/integration/" "test_rag_governance_closeout_acceptance.py"),
    V005_ACCEPTANCE_FILE,
    V005_ACCEPTANCE_ROOT / CHECKSUM_FILENAME,
    V3_RUNTIME_FILE,
    V3_RUNTIME_ROOT / CHECKSUM_FILENAME,
    SOURCE_POLICY_FILE,
    SOURCE_POLICY_ROOT / CHECKSUM_FILENAME,
    CANDIDATE_ROOT / CHECKSUM_FILENAME,
)

PRIOR_ARTIFACT_ROOTS = (
    V005_ACCEPTANCE_ROOT,
    V3_RUNTIME_ROOT,
    SOURCE_POLICY_ROOT,
    CANDIDATE_ROOT,
)


class RagGovernanceCloseoutAcceptanceError(SourceFamilyRuntimePolicyError):
    """Raised when the v006 Owner closeout evidence is inconsistent."""


@dataclass(frozen=True, slots=True)
class RagGovernanceCloseoutAcceptanceSummary:
    output_path: Path
    acceptance_sha256: str
    validation_input_inventory_sha256: str
    prior_artifact_lock_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "acceptance_version": ACCEPTANCE_VERSION,
            "output_path": self.output_path.as_posix(),
            "purpose_verified_count": PURPOSE_VERIFIED_COUNT,
            "conditional_stop_count": CONDITIONAL_STOP_COUNT,
            "runtime_policy_candidate_count": 0,
            "acceptance_sha256": self.acceptance_sha256,
            "validation_input_inventory_sha256": (self.validation_input_inventory_sha256),
            "prior_artifact_lock_sha256": self.prior_artifact_lock_sha256,
            "external_sync": "NOT_AUTHORIZED",
            "production_approved": False,
        }


def build_rag_governance_closeout_acceptance(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> RagGovernanceCloseoutAcceptanceSummary:
    """Build v006 atomically without changing prior or runtime artifacts."""

    root = repository_root.resolve()
    destination = (output_path or root / ACCEPTANCE_ROOT).resolve()
    try:
        _refuse_overwrite(destination, "RAG governance closeout acceptance v006")
    except SourceFamilyRuntimePolicyV2Error as exc:
        raise RagGovernanceCloseoutAcceptanceError(str(exc)) from exc
    _validate_prior_artifacts(root)
    document = _acceptance_document(root)
    inventory = _inventory_document(
        "rag_governance_closeout_acceptance_v006_validation_input_inventory",
        _file_entries(root, [root / path for path in FIXED_INPUT_PATHS]),
        "v006 schema, builder, validator, tests, and hash-bound formal inputs",
    )
    prior_lock = _inventory_document(
        "rag_governance_closeout_acceptance_v006_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
        "immutable v005 purpose, runtime v003, source policy v002, and candidate v003 bytes",
    )
    staged = _new_staging_directory(root, "rag-governance-closeout-acceptance-v006")
    try:
        _write_json(staged / ACCEPTANCE_FILE.name, document)
        _write_json(staged / VALIDATION_INPUT_FILENAME, inventory)
        _write_json(staged / PRIOR_LOCK_FILENAME, prior_lock)
        _write_json(staged / VALIDATION_REPORT_FILENAME, _validation_report())
        _write_json(
            staged / MANIFEST_FILENAME,
            {
                "schema_version": SCHEMA_VERSION,
                "acceptance_version": ACCEPTANCE_VERSION,
                "files": [
                    ACCEPTANCE_FILE.name,
                    VALIDATION_INPUT_FILENAME,
                    PRIOR_LOCK_FILENAME,
                    VALIDATION_REPORT_FILENAME,
                ],
                "acceptance_sha256": _sha256_file(staged / ACCEPTANCE_FILE.name),
                "external_sync": "NOT_AUTHORIZED",
                "production_approved": False,
            },
        )
        _write_text(staged / "README.md", _readme())
        _write_checksums(staged)
        result = validate_rag_governance_closeout_acceptance(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return RagGovernanceCloseoutAcceptanceSummary(
        output_path=destination,
        acceptance_sha256=result["acceptance_sha256"],
        validation_input_inventory_sha256=inventory["inventory_sha256"],
        prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_rag_governance_closeout_acceptance(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate Owner evidence, exact decisions, hashes, and deny-by-default gates."""

    root = repository_root.resolve()
    package = (package_path or root / ACCEPTANCE_ROOT).resolve()
    expected_paths = {
        ACCEPTANCE_FILE.name,
        VALIDATION_INPUT_FILENAME,
        PRIOR_LOCK_FILENAME,
        VALIDATION_REPORT_FILENAME,
        MANIFEST_FILENAME,
        "README.md",
        CHECKSUM_FILENAME,
    }
    _validate_package_inventory(package, expected_paths)
    _assert_text_tree(package)
    _validate_checksums(package)
    _validate_prior_artifacts(root)
    _validate_inventory_document(
        package / VALIDATION_INPUT_FILENAME,
        "rag_governance_closeout_acceptance_v006_validation_input_inventory",
        _file_entries(root, [root / path for path in FIXED_INPUT_PATHS]),
    )
    _validate_inventory_document(
        package / PRIOR_LOCK_FILENAME,
        "rag_governance_closeout_acceptance_v006_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
    )
    document = _read_json(package / ACCEPTANCE_FILE.name)
    _validate_schema(root / ACCEPTANCE_SCHEMA_PATH, document, "RAG closeout acceptance")
    expected = _acceptance_document(root)
    if document != expected:
        raise RagGovernanceCloseoutAcceptanceError("RAG closeout acceptance is not reproducible")
    if (package / ACCEPTANCE_FILE.name).read_bytes() != _json_bytes(document):
        raise RagGovernanceCloseoutAcceptanceError(
            "RAG closeout acceptance JSON is not deterministic"
        )
    if _read_json(package / VALIDATION_REPORT_FILENAME) != _validation_report():
        raise RagGovernanceCloseoutAcceptanceError("RAG closeout validation report is inconsistent")
    if (package / "README.md").read_text(encoding="utf-8") != _readme():
        raise RagGovernanceCloseoutAcceptanceError("RAG closeout README is inconsistent")
    manifest = _read_json(package / MANIFEST_FILENAME)
    acceptance_sha256 = _sha256_file(package / ACCEPTANCE_FILE.name)
    if manifest["acceptance_sha256"] != acceptance_sha256:
        raise RagGovernanceCloseoutAcceptanceError("RAG closeout manifest acceptance hash mismatch")
    return {
        "status": "PASS",
        "acceptance_version": ACCEPTANCE_VERSION,
        "acceptance_sha256": acceptance_sha256,
        "purpose_verified_count": PURPOSE_VERIFIED_COUNT,
        "purpose_needs_review_count": 0,
        "conditional_stop_count": CONDITIONAL_STOP_COUNT,
        "conditional_stop_active_count": 0,
        "audience_review_pending_count": CONDITIONAL_STOP_COUNT,
        "runtime_policy_change": "NOT_AUTHORIZED_BY_THIS_ACCEPTANCE",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validate_prior_artifacts(root: Path) -> None:
    try:
        validate_owner_purpose_classification_acceptance(root)
        validate_source_family_runtime_policy_v3(root)
    except SourceFamilyRuntimePolicyError as exc:
        raise RagGovernanceCloseoutAcceptanceError(
            "prior v005 or runtime v003 integrity failed"
        ) from exc
    if _sha256_file(root / V005_ACCEPTANCE_FILE) != V005_ACCEPTANCE_SHA256:
        raise RagGovernanceCloseoutAcceptanceError("prior v005 acceptance bytes changed")
    if _sha256_file(root / V3_RUNTIME_FILE) != V3_RUNTIME_SHA256:
        raise RagGovernanceCloseoutAcceptanceError("prior runtime v003 bytes changed")


def _acceptance_document(root: Path) -> dict[str, Any]:
    statements = list(OWNER_STATEMENTS)
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "status": "SIGNED_STAGING_GOVERNANCE_DECISION",
        "project_owner_id": "IanHsu",
        "signer_role": "PROJECT_OWNER",
        "signed_at": SIGNED_AT,
        "authorization": {
            "channel": "interactive_user_instruction",
            "statements": statements,
            "statements_sha256": _canonical_sha256(statements),
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": "IanHsu",
            "intent": "VERIFY_PURPOSE_AND_AUTHORIZE_CONDITIONAL_STOP_REVIEW",
            "cryptographic_signature": None,
        },
        "bindings": {
            "prior_purpose_acceptance_path": V005_ACCEPTANCE_FILE.as_posix(),
            "prior_purpose_acceptance_sha256": _sha256_file(root / V005_ACCEPTANCE_FILE),
            "prior_runtime_policy_path": V3_RUNTIME_FILE.as_posix(),
            "prior_runtime_policy_sha256": _sha256_file(root / V3_RUNTIME_FILE),
            "source_policy_path": SOURCE_POLICY_FILE.as_posix(),
            "source_policy_sha256": _sha256_file(root / SOURCE_POLICY_FILE),
            "candidate_path": CANDIDATE_ROOT.as_posix(),
            "candidate_checksums_sha256": _sha256_file(root / CANDIDATE_ROOT / CHECKSUM_FILENAME),
        },
        "purpose_verification": {
            "method": "OWNER_VERIFIED_PRIOR_AI_ASSISTED_CLASSIFICATION",
            "affected_chunk_count": PURPOSE_VERIFIED_COUNT,
            "human_verified_classification_count": PURPOSE_VERIFIED_COUNT,
            "needs_review_classification_count": 0,
            "candidate_chunk_bytes_mutated": False,
            "decisions": _verified_purpose_decisions(root),
        },
        "conditional_stop_decision": {
            "affected_chunk_count": CONDITIONAL_STOP_COUNT,
            "owner_disposition": "CONDITIONALLY_RELEASABLE_AFTER_AUDIENCE_REVIEW",
            "runtime_activation": "DENIED_PENDING_AUDIENCE_REVIEW",
            "stop_normal_rag_preserved": True,
            "runtime_policy_candidate_count": 0,
            "audience_review_pending_count": CONDITIONAL_STOP_COUNT,
            "decisions": _conditional_stop_decisions(root),
        },
        "gates": {
            "environment": "STAGING",
            "external_sync": "NOT_AUTHORIZED",
            "runtime_policy_change": "NOT_AUTHORIZED_BY_THIS_ACCEPTANCE",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _verified_purpose_decisions(root: Path) -> list[dict[str, Any]]:
    prior = _read_json(root / V005_ACCEPTANCE_FILE)
    decisions: list[dict[str, Any]] = []
    for decision in prior["decisions"]:
        if decision["decision_review_status"] != "needs_review":
            raise RagGovernanceCloseoutAcceptanceError(
                "prior purpose decision review state diverged"
            )
        verified = dict(decision)
        verified["decision_review_status"] = "verified"
        decisions.append(verified)
    if len(decisions) != PURPOSE_VERIFIED_COUNT:
        raise RagGovernanceCloseoutAcceptanceError("purpose decision count diverged")
    return decisions


def _conditional_stop_decisions(root: Path) -> list[dict[str, Any]]:
    overlays = set(RISK_DECISION_CHUNK_IDS)
    decisions: list[dict[str, Any]] = []
    for records in _load_chunk_records(root).values():
        for record in records:
            identity = record["identity"]
            governance = record["governance"]
            provenance = record["provenance"]
            retrieval = record["retrieval_policy"]
            effective_risk = retrieval["risk_level"]
            if effective_risk is None and identity["chunk_id"] in overlays:
                effective_risk = "low"
            if not (
                provenance["is_official_source"] is True
                and governance["current_status"] == "current"
                and retrieval["stop_normal_rag"] is True
                and effective_risk in {"low", "medium"}
            ):
                continue
            decisions.append(
                {
                    "prior_chunk_id": identity["prior_chunk_id"],
                    "chunk_id": identity["chunk_id"],
                    "source_id": identity["source_id"],
                    "text_sha256": record["content"]["text_sha256"],
                    "effective_risk_level": effective_risk,
                    "observed_allowed_audiences": sorted(retrieval["allowed_audiences"]),
                    "observed_allowed_purposes": sorted(retrieval["allowed_purposes"]),
                    "owner_disposition": ("CONDITIONALLY_RELEASABLE_AFTER_AUDIENCE_REVIEW"),
                    "audience_review_status": "needs_review",
                    "runtime_retrieval_active": False,
                    "stop_normal_rag_preserved": True,
                    "required_next_gate": ("PER_CHUNK_AUDIENCE_AND_PURPOSE_VERIFICATION"),
                }
            )
    decisions.sort(key=lambda item: item["chunk_id"])
    if len(decisions) != CONDITIONAL_STOP_COUNT:
        raise RagGovernanceCloseoutAcceptanceError("conditional stop decision count diverged")
    if len({item["chunk_id"] for item in decisions}) != CONDITIONAL_STOP_COUNT:
        raise RagGovernanceCloseoutAcceptanceError("conditional stop decisions must be unique")
    return decisions


def _validation_report() -> dict[str, Any]:
    checks = (
        "owner_instruction_hash_bound",
        "prior_purpose_acceptance_v005_immutable",
        "prior_runtime_policy_v003_immutable",
        "source_policy_v002_immutable",
        "candidate_v003_immutable",
        "purpose_decisions_32_exact_and_unique",
        "purpose_decisions_32_owner_verified",
        "purpose_needs_review_zero",
        "conditional_stop_27_exact_and_unique",
        "conditional_stop_source_text_hash_bound",
        "conditional_stop_runtime_inactive",
        "conditional_stop_audience_review_pending",
        "stop_normal_rag_bytes_preserved",
        "runtime_policy_unchanged",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "purpose_verified_count": PURPOSE_VERIFIED_COUNT,
        "purpose_needs_review_count": 0,
        "conditional_stop_count": CONDITIONAL_STOP_COUNT,
        "conditional_stop_active_count": 0,
        "audience_review_pending_count": CONDITIONAL_STOP_COUNT,
        "runtime_policy_change": "NOT_AUTHORIZED_BY_THIS_ACCEPTANCE",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _readme() -> str:
    return (
        "# Owner RAG Closeout Acceptance v006\n\n"
        "This immutable staging acceptance records two explicit Owner decisions.\n\n"
        f"- A-unit purpose classifications human verified: `{PURPOSE_VERIFIED_COUNT}`\n"
        "- Purpose classifications still needing review: `0`\n"
        f"- `stop_normal_rag=true` chunks conditionally releasable after per-chunk "
        f"audience and purpose verification: `{CONDITIONAL_STOP_COUNT}`\n"
        "- Conditional stop chunks active in the current runtime policy: `0`\n"
        "- Existing Chunk bytes and `stop_normal_rag` values: unchanged\n"
        "- Runtime policy change: `NOT_AUTHORIZED_BY_THIS_ACCEPTANCE`\n"
        "- External sync: `NOT_AUTHORIZED`\n"
        "- Production: `BLOCKED`\n\n"
        "Do not treat observed audiences as approved release audiences. A versioned "
        "successor requires explicit per-chunk audience and purpose verification.\n"
    )


def acceptance_document_for_test(repository_root: Path) -> Mapping[str, Any]:
    """Expose deterministic content for focused contract tests."""

    return _acceptance_document(repository_root.resolve())
