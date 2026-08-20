"""Deterministic RagChunkV2 successor-artifact builder.

The builder never calls external services and never mutates the current V1
bundle.  It requires a byte-level preflight lock before it can publish a new
local candidate directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rag_ingestion.allowlist import Allowlist, load_allowlist
from rag_ingestion.bulk_ingester import REQUIRED_EMBEDDING_DIMENSION, build_index_document
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.validator import ValidatedChunk, validate_chunks

SCHEMA_VERSION = "2.0.0"
ARTIFACT_VERSION = "v001"
ALLOWLIST_VERSION = "v003"
PREFLIGHT_VERSION = "v002"

ALLOWLIST_PATH = Path("data/rag-manifest/AI_Reviewed_Embedding_Staging_Allowlist_v002.json")
CHUNKS_DIRECTORY = Path("data/rag-chunks/approved")
SOURCE_REVIEW_PATH = Path(
    "data/rag-manifest/AWS長照_RAG_AI_Source_Review_Current_Candidates_v002.json"
)
V2_SCHEMA_PATH = Path("contracts/schemas/rag/rag-chunk-v2.schema.json")
TEST_EVIDENCE_PATH = Path("data/rag-v2/evidence/v002/pytest-rag-ingestion.xml")

_OFFICIAL_AUTHORITIES = frozenset(
    {
        "official_government",
        "official_health_education",
        "official_law",
        "official_manual",
        "official_manual_appendix",
    }
)
_CANONICAL_CURRENT_STATUSES = frozenset({"current", "superseded", "unknown"})
_CANONICAL_VERSION_CHECK_STATUSES = frozenset({"pending", "verified_official_source"})
_CANONICAL_RISK_LEVELS = frozenset({"low", "medium", "high", "high_red_line"})
_CANONICAL_LANGUAGES = frozenset({"en", "zh-Hant"})
_CANONICAL_LOCALES = frozenset({"en-US", "zh-TW"})

_PRIOR_FORMAL_PATHS = (
    Path("data/rag-chunks/README.md"),
    Path("data/rag-chunks/SHA256SUMS.txt"),
    ALLOWLIST_PATH,
    Path("data/rag-manifest/all_current_chunk_catalog_20260802.json"),
    SOURCE_REVIEW_PATH,
)

_VALIDATION_FIXED_PATHS = (
    *_PRIOR_FORMAL_PATHS,
    Path("services/rag-ingestion/src/rag_ingestion/allowlist.py"),
    Path("services/rag-ingestion/src/rag_ingestion/bulk_ingester.py"),
    Path("services/rag-ingestion/src/rag_ingestion/chunk_loader.py"),
    Path("services/rag-ingestion/src/rag_ingestion/validator.py"),
    Path("services/rag-ingestion/src/rag_ingestion/v2_artifacts.py"),
    Path("services/rag-ingestion/pyproject.toml"),
    Path("services/rag-ingestion/README.md"),
    Path("services/rag-ingestion/tests/integration/test_approved_dataset.py"),
    Path("services/rag-ingestion/tests/integration/test_v2_artifacts.py"),
    Path("services/rag-ingestion/tests/unit/test_allowlist_and_loader.py"),
    Path("services/rag-ingestion/uv.lock"),
    Path("scripts/rag/build_v2_artifacts.py"),
    Path("scripts/rag/validate_v2_artifacts.py"),
    Path("data/rag-v2/README.md"),
    V2_SCHEMA_PATH,
)


class V2ArtifactError(ValueError):
    """Raised before a candidate is published."""


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


@dataclass(frozen=True, slots=True)
class V2BuildSummary:
    output_path: Path
    source_count: int
    chunk_count: int
    official_source_count: int
    official_chunk_count: int
    research_source_count: int
    research_chunk_count: int
    retrieval_eligible_count: int
    review_row_count: int
    input_inventory_sha256: str
    prior_lock_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "BUILT",
            "artifact_version": ARTIFACT_VERSION,
            "preflight_version": PREFLIGHT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "output_path": self.output_path.as_posix(),
            "source_count": self.source_count,
            "chunk_count": self.chunk_count,
            "official_source_count": self.official_source_count,
            "official_chunk_count": self.official_chunk_count,
            "research_source_count": self.research_source_count,
            "research_chunk_count": self.research_chunk_count,
            "retrieval_eligible_count": self.retrieval_eligible_count,
            "review_row_count": self.review_row_count,
            "input_inventory_sha256": self.input_inventory_sha256,
            "prior_lock_sha256": self.prior_lock_sha256,
            "review_status": "needs_review",
            "production_approved": False,
        }


def prepare_preflight(repository_root: Path, output_root: Path) -> dict[str, Any]:
    """Freeze validation inputs and prior formal bytes without overwriting evidence."""

    root = repository_root.resolve()
    preflight_dir = output_root.resolve() / "preflight" / PREFLIGHT_VERSION
    inventory_path = preflight_dir / "validation-input-inventory.json"
    lock_path = preflight_dir / "prior-artifact-lock.json"
    if inventory_path.exists() or lock_path.exists():
        raise V2ArtifactError("preflight evidence already exists; refuse to overwrite")

    inventory_entries = _validation_inventory_entries(root)
    lock_entries = _prior_lock_entries(root)
    inventory = _inventory_document("validation_input_inventory", inventory_entries)
    prior_lock = _inventory_document("prior_artifact_immutable_lock", lock_entries)

    preflight_dir.mkdir(parents=True, exist_ok=False)
    try:
        _write_json(inventory_path, inventory)
        _write_json(lock_path, prior_lock)
    except Exception:
        shutil.rmtree(preflight_dir, ignore_errors=True)
        raise
    return {
        "status": "PREFLIGHT_FROZEN",
        "inventory_path": inventory_path.as_posix(),
        "inventory_sha256": inventory["inventory_sha256"],
        "prior_lock_path": lock_path.as_posix(),
        "prior_lock_sha256": prior_lock["inventory_sha256"],
        "validation_input_count": len(inventory_entries),
        "protected_artifact_count": len(lock_entries),
    }


def build_v2_artifacts(
    repository_root: Path,
    output_root: Path,
    *,
    require_test_evidence: bool = False,
) -> V2BuildSummary:
    """Build a complete local candidate after verifying frozen preflight evidence."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    candidate_dir = output_base / "candidates" / ARTIFACT_VERSION
    if candidate_dir.exists():
        raise V2ArtifactError("candidate output already exists; refuse to overwrite")

    preflight_dir = output_base / "preflight" / PREFLIGHT_VERSION
    inventory = _read_json(preflight_dir / "validation-input-inventory.json")
    prior_lock = _read_json(preflight_dir / "prior-artifact-lock.json")
    _assert_inventory_matches(inventory, _validation_inventory_entries(root), "validation input")
    _assert_inventory_matches(prior_lock, _prior_lock_entries(root), "prior artifact")

    allowlist = load_allowlist(root / ALLOWLIST_PATH)
    loaded = load_allowlisted_chunks(root / CHUNKS_DIRECTORY, allowlist)
    validation = validate_chunks(loaded, allowlist)
    titles = _source_titles(root / SOURCE_REVIEW_PATH)
    source_numbers = {
        source["source_id"]: source["source_number"]
        for source in allowlist.raw["sources"]
        if isinstance(source, dict)
    }

    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prior_by_id: dict[str, ValidatedChunk] = {}
    crosswalk: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for chunk in validation.chunks:
        source_id = chunk.data["source_id"]
        prior_path = chunk.loaded.file_path.relative_to(root).as_posix()
        record = _to_v2_record(
            chunk,
            title=titles.get(source_id) or chunk.allowlist_entry.source_title,
            prior_path=prior_path,
        )
        records_by_source[source_id].append(record)
        prior_by_id[chunk.chunk_id] = chunk
        crosswalk.append(_crosswalk_record(record, chunk, prior_path))
        warnings = record["provenance"]["mapping_warnings"]
        block_reasons = record["retrieval_policy"]["retrieval_block_reasons"]
        if warnings or block_reasons:
            review_rows.append(
                {
                    "schema_version": "1.0.0",
                    "worksheet_version": ARTIFACT_VERSION,
                    "source_id": source_id,
                    "prior_chunk_id": chunk.chunk_id,
                    "successor_chunk_id": record["identity"]["chunk_id"],
                    "retrieval_block_reasons": block_reasons,
                    "mapping_warnings": warnings,
                    "review_status": "needs_review",
                    "production_approved": False,
                }
            )

    _validate_records(records_by_source, prior_by_id)
    candidate_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_VERSION}-", dir=candidate_dir.parent)
    )
    temporary_candidate = temporary_root / ARTIFACT_VERSION
    temporary_candidate.mkdir(parents=True)
    try:
        chunk_files = _write_chunk_files(temporary_candidate, records_by_source)
        all_records = [
            record
            for source_id in sorted(records_by_source, key=source_numbers.__getitem__)
            for record in records_by_source[source_id]
        ]
        source_manifest = _source_manifest(all_records, source_numbers, titles)
        chunk_manifest = _chunk_file_manifest(chunk_files, records_by_source)
        candidate_allowlist = _candidate_allowlist(
            allowlist,
            all_records,
            source_numbers,
        )
        enum_evidence = _enum_evidence(all_records, inventory["inventory_sha256"])
        version_diff = _version_difference_summary(all_records, review_rows)
        validation_report = _validation_report(
            all_records,
            review_rows,
            inventory_sha256=inventory["inventory_sha256"],
            prior_lock_sha256=prior_lock["inventory_sha256"],
        )
        test_evidence = _test_evidence_document(
            root / TEST_EVIDENCE_PATH,
            required=require_test_evidence,
        )

        _write_json(temporary_candidate / "manifests/source-manifest-v001.json", source_manifest)
        _write_json(
            temporary_candidate / "manifests/chunk-file-manifest-v001.json",
            chunk_manifest,
        )
        _write_json(
            temporary_candidate / "manifests/embedding-staging-allowlist-v003.json",
            candidate_allowlist,
        )
        _write_json(temporary_candidate / "governance/enum-evidence-v001.json", enum_evidence)
        _write_jsonl(temporary_candidate / "crosswalk/chunk-id-crosswalk-v001.jsonl", crosswalk)
        _write_jsonl(temporary_candidate / "review/human-review-worksheet-v001.jsonl", review_rows)
        _write_json(
            temporary_candidate / "reports/version-difference-summary-v001.json",
            version_diff,
        )
        _write_json(
            temporary_candidate / "reports/validation-report-v001.json",
            validation_report,
        )
        _write_json(
            temporary_candidate / "reports/test-evidence-v001.json",
            test_evidence,
        )
        if test_evidence["status"] == "PASS":
            shutil.copyfile(
                root / TEST_EVIDENCE_PATH,
                temporary_candidate / "reports/pytest-rag-ingestion-v001.xml",
            )
        _write_text(temporary_candidate / "README.md", _candidate_readme())
        _write_checksums(temporary_candidate)

        _assert_inventory_matches(prior_lock, _prior_lock_entries(root), "prior artifact")
        temporary_candidate.replace(candidate_dir)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)

    official_sources = {
        record["identity"]["source_id"]
        for records in records_by_source.values()
        for record in records
        if record["provenance"]["is_official_source"]
    }
    official_chunks = sum(
        record["provenance"]["is_official_source"]
        for records in records_by_source.values()
        for record in records
    )
    eligible = sum(
        record["retrieval_policy"]["retrieval_eligible"]
        for records in records_by_source.values()
        for record in records
    )
    return V2BuildSummary(
        output_path=candidate_dir,
        source_count=len(records_by_source),
        chunk_count=sum(len(records) for records in records_by_source.values()),
        official_source_count=len(official_sources),
        official_chunk_count=official_chunks,
        research_source_count=len(records_by_source) - len(official_sources),
        research_chunk_count=validation.chunk_count - official_chunks,
        retrieval_eligible_count=eligible,
        review_row_count=len(review_rows),
        input_inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
    )


def _to_v2_record(
    chunk: ValidatedChunk,
    *,
    title: str | None,
    prior_path: str,
) -> dict[str, Any]:
    data = chunk.data
    warnings: list[str] = []
    policy = build_index_document(chunk, [0.0] * REQUIRED_EMBEDDING_DIMENSION)
    source_id = data["source_id"]
    chunk_index = data["chunk_index"]
    successor_id = f"{source_id}_rag_v2_{chunk_index:04d}"

    raw_current_status = _string_value(data, "current_status", warnings)
    if raw_current_status == "needs_verification":
        current_status = "unknown"
        warnings.append("current_status_needs_verification_preserved_as_unknown")
    elif raw_current_status in _CANONICAL_CURRENT_STATUSES:
        current_status = raw_current_status
    else:
        current_status = "unknown"
        if raw_current_status is not None:
            warnings.append("current_status_not_in_v2_enum")

    raw_version_check = _string_value(data, "version_check_status", warnings)
    version_check_status = raw_version_check or "pending"
    if version_check_status not in _CANONICAL_VERSION_CHECK_STATUSES:
        warnings.append("version_check_status_not_in_v2_enum")
        version_check_status = "pending"

    raw_risk = _string_value(data, "risk_level", warnings)
    risk_level = raw_risk if raw_risk in _CANONICAL_RISK_LEVELS else None
    if raw_risk is not None and risk_level is None:
        warnings.append("risk_level_not_in_v2_enum")

    stop_normal_rag = _bool_value(data, "stop_normal_rag", warnings)
    requires_human_review = _bool_value(data, "requires_human_review", warnings)
    if requires_human_review is None:
        requires_human_review = True
        warnings.append("requires_human_review_missing_conservative_true")

    language, locale = _normalize_language_locale(data, warnings)
    page_start = _positive_int_value(
        data, ("physical_page_start", "page_start"), "physical_page_start", warnings
    )
    page_end = _positive_int_value(
        data, ("physical_page_end", "page_end"), "physical_page_end", warnings
    )
    printed_page_start = _positive_int_value(
        data, ("printed_page_start",), "printed_page_start", warnings
    )
    printed_page_end = _positive_int_value(
        data, ("printed_page_end",), "printed_page_end", warnings
    )
    _validate_page_pair(page_start, page_end, "physical_page", warnings)
    _validate_page_pair(printed_page_start, printed_page_end, "printed_page", warnings)

    authority_level = _string_value(data, "authority_level", warnings)
    source_type = _string_value(data, "source_type", warnings)
    is_official = authority_level in _OFFICIAL_AUTHORITIES
    if authority_level is None:
        warnings.append("authority_level_missing")
    if not is_official and authority_level is not None:
        warnings.append("non_official_source_preserved_as_research_evidence")

    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "identity": {
            "chunk_id": successor_id,
            "prior_chunk_id": chunk.chunk_id,
            "source_id": source_id,
            "chunk_file_id": f"{source_id}_rag_v2_{ARTIFACT_VERSION}",
            "prior_chunk_file_id": _string_value(data, "chunk_file_id", warnings),
            "chunk_index": chunk_index,
        },
        "content": {
            "text": chunk.text,
            "embedding_text": chunk.embedding_text,
            "char_count": len(chunk.text),
            "embedding_char_count": len(chunk.embedding_text),
            "text_sha256": chunk.text_sha256,
            "embedding_text_sha256": chunk.embedding_text_sha256,
            "content_type": _string_value(data, "chunk_type", warnings),
            "language": language,
            "locale": locale,
        },
        "citation": {
            "title": title or policy["document_name"],
            "publisher": _first_string_alias(
                data, ("publish_agency", "competent_authority"), warnings
            ),
            "section": policy["section"],
            "physical_page_start": page_start,
            "physical_page_end": page_end,
            "printed_page_start": printed_page_start,
            "printed_page_end": printed_page_end,
            "source_locator": _string_value(data, "source_locator", warnings),
            "direct_official_source_url": _url_value(data, "official_source_url", warnings),
            "official_source_page_url": _url_value(data, "official_source_page_url", warnings),
            "license_evidence_url": _url_value(data, "license_source_url", warnings),
            "storage_url": _url_value(data, "storage_url", warnings),
        },
        "retrieval_policy": {
            "allowed_audiences": policy["allowed_audiences"],
            "allowed_purposes": policy["allowed_purposes"],
            "risk_level": risk_level,
            "requires_official_assessment": policy["requires_official_assessment"],
            "requires_professional_assessment": policy["requires_professional_assessment"],
            "requires_human_review": requires_human_review,
            "stop_normal_rag": stop_normal_rag,
            "retrieval_eligible": policy["retrieval_eligible"],
            "retrieval_block_reasons": policy["retrieval_block_reasons"],
        },
        "governance": {
            "review_status": "needs_review",
            "current_status": current_status,
            "version_check_status": version_check_status,
            "license_status": _string_value(data, "license_status", warnings) or "unknown",
            "embedding_status": "not_started",
            "ingestion_status": "staging",
            "human_source_review": "not_completed",
            "production_gate": "blocked",
            "production_approved": False,
            "data_classification": _string_value(data, "data_classification", warnings),
            "distribution_scope": _string_value(data, "share_scope", warnings),
            "storage_target": "local_pending_upload",
        },
        "provenance": {
            "source_version": _first_string_alias(
                data,
                ("source_version", "document_version", "source_version_date"),
                warnings,
            )
            or chunk.allowlist_entry.source_version,
            "source_version_date": _string_value(data, "source_version_date", warnings),
            "version_published_at": _string_value(data, "version_published_at", warnings),
            "source_page_updated_at": _string_value(data, "source_page_updated_at", warnings),
            "published_at": _string_value(data, "published_at", warnings),
            "last_verified_at": _first_string_alias(
                data, ("last_verified_at", "last_version_checked_at"), warnings
            ),
            "parser_version": _string_value(data, "parser_version", warnings),
            "chunker_version": _string_value(data, "chunker_version", warnings),
            "pipeline_version": _string_value(data, "pipeline_version", warnings),
            "prior_artifact_version": _string_value(data, "artifact_version", warnings),
            "prior_delivery_version": _string_value(data, "delivery_version", warnings),
            "source_file": _string_value(data, "source_file", warnings),
            "prior_artifact_path": prior_path,
            "authority_level": authority_level,
            "source_type": source_type,
            "is_official_source": is_official,
            "mapping_warnings": sorted(set(warnings)),
        },
    }
    if (
        record["citation"]["direct_official_source_url"] is None
        and record["citation"]["official_source_page_url"] is None
    ):
        record["provenance"]["mapping_warnings"].append("official_source_url_missing")
    if record["citation"]["source_locator"] is None:
        record["provenance"]["mapping_warnings"].append("source_locator_missing")
    record["provenance"]["mapping_warnings"] = sorted(set(record["provenance"]["mapping_warnings"]))
    return record


def _crosswalk_record(
    record: dict[str, Any], chunk: ValidatedChunk, prior_path: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "source_id": record["identity"]["source_id"],
        "prior_chunk_id": chunk.chunk_id,
        "successor_chunk_id": record["identity"]["chunk_id"],
        "relationship": "metadata_successor",
        "prior_artifact_path": prior_path,
        "text_sha256_equal": record["content"]["text_sha256"] == chunk.text_sha256,
        "embedding_text_sha256_equal": (
            record["content"]["embedding_text_sha256"] == chunk.embedding_text_sha256
        ),
        "status_change_recommendation": "human_review_required",
        "status_changed_automatically": False,
    }


def _write_chunk_files(
    candidate_dir: Path, records_by_source: Mapping[str, Sequence[dict[str, Any]]]
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for source_id in sorted(records_by_source):
        records = records_by_source[source_id]
        relative_path = Path("chunks") / f"{source_id}.rag-chunk-v2.v001.jsonl"
        path = candidate_dir / relative_path
        _write_jsonl(path, records)
        files.append(
            {
                "source_id": source_id,
                "chunk_file_id": records[0]["identity"]["chunk_file_id"],
                "path": relative_path.as_posix(),
                "chunk_count": len(records),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def _source_manifest(
    records: Sequence[dict[str, Any]],
    source_numbers: Mapping[str, int],
    titles: Mapping[str, str],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["identity"]["source_id"]].append(record)
    sources: list[dict[str, Any]] = []
    for source_id in sorted(grouped, key=source_numbers.__getitem__):
        source_records = grouped[source_id]
        first = source_records[0]
        sources.append(
            {
                "source_number": source_numbers[source_id],
                "source_id": source_id,
                "title": titles.get(source_id) or first["citation"]["title"],
                "authority_level": first["provenance"]["authority_level"],
                "source_type": first["provenance"]["source_type"],
                "is_official_source": first["provenance"]["is_official_source"],
                "chunk_count": len(source_records),
                "source_versions": _unique_values(
                    record["provenance"]["source_version"] for record in source_records
                ),
                "direct_official_source_urls": _unique_values(
                    record["citation"]["direct_official_source_url"] for record in source_records
                ),
                "official_source_page_urls": _unique_values(
                    record["citation"]["official_source_page_url"] for record in source_records
                ),
                "license_evidence_urls": _unique_values(
                    record["citation"]["license_evidence_url"] for record in source_records
                ),
                "storage_urls": _unique_values(
                    record["citation"]["storage_url"] for record in source_records
                ),
                "review_status": "needs_review",
                "ingestion_status": "staging",
                "production_approved": False,
                "storage_target": "local_pending_upload",
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "source_count": len(sources),
        "chunk_count": len(records),
        "sources": sources,
    }


def _chunk_file_manifest(
    files: Sequence[dict[str, Any]],
    records_by_source: Mapping[str, Sequence[dict[str, Any]]],
) -> dict[str, Any]:
    entries = []
    for item in sorted(files, key=lambda value: value["source_id"]):
        records = records_by_source[item["source_id"]]
        entries.append(
            {
                **item,
                "schema_version": SCHEMA_VERSION,
                "extension_schema_version": None,
                "artifact_version": ARTIFACT_VERSION,
                "chunk_size_target": 600,
                "chunk_overlap": 0,
                "parser_versions": _unique_values(
                    record["provenance"]["parser_version"] for record in records
                ),
                "chunker_versions": _unique_values(
                    record["provenance"]["chunker_version"] for record in records
                ),
                "review_status": "needs_review",
                "ingestion_status": "staging",
                "embedding_status": "not_started",
                "production_approved": False,
                "storage_target": "local_pending_upload",
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "chunk_file_count": len(entries),
        "chunk_count": sum(item["chunk_count"] for item in entries),
        "files": entries,
    }


def _candidate_allowlist(
    allowlist: Allowlist,
    records: Sequence[dict[str, Any]],
    source_numbers: Mapping[str, int],
) -> dict[str, Any]:
    document = {
        key: value
        for key, value in allowlist.raw.items()
        if key not in {"schema_version", "sources", "entries", "source_count", "chunk_count"}
    }
    source_templates = {
        item["source_id"]: dict(item) for item in allowlist.raw["sources"] if isinstance(item, dict)
    }
    counts = Counter(record["identity"]["source_id"] for record in records)
    sources = []
    for source_id in sorted(counts, key=source_numbers.__getitem__):
        source = source_templates[source_id]
        source["chunk_count"] = counts[source_id]
        source["successor_artifact_version"] = ARTIFACT_VERSION
        source["review_status"] = "needs_review"
        source["human_source_review"] = "NOT_COMPLETED"
        source["production_gate"] = "BLOCKED"
        source["storage_target"] = "local_pending_upload"
        sources.append(source)
    entries = []
    for record in records:
        identity = record["identity"]
        content = record["content"]
        entries.append(
            {
                "source_number": source_numbers[identity["source_id"]],
                "source_id": identity["source_id"],
                "chunk_id": identity["chunk_id"],
                "prior_chunk_id": identity["prior_chunk_id"],
                "chunk_index": identity["chunk_index"],
                "text_sha256": content["text_sha256"],
                "embedding_text_sha256": content["embedding_text_sha256"],
                "allowed_use": allowlist.raw["allowed_use"],
                "signature_required": True,
                "review_status": "needs_review",
                "human_source_review": "NOT_COMPLETED",
                "embedding_status": "NOT_STARTED",
                "opensearch_indexing_status": "NOT_STARTED",
                "production_gate": "BLOCKED",
                "retrieval_eligible": record["retrieval_policy"]["retrieval_eligible"],
            }
        )
    return {
        "schema_version": ALLOWLIST_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "supersedes_allowlist_sha256": allowlist.sha256,
        "source_count": len(sources),
        "chunk_count": len(entries),
        "sources": sources,
        "entries": entries,
        **document,
    }


def _enum_evidence(
    records: Sequence[dict[str, Any]], input_inventory_sha256: str
) -> dict[str, Any]:
    selectors = {
        "authority_level": lambda record: record["provenance"]["authority_level"],
        "source_type": lambda record: record["provenance"]["source_type"],
        "content_type": lambda record: record["content"]["content_type"],
        "language": lambda record: record["content"]["language"],
        "locale": lambda record: record["content"]["locale"],
        "risk_level": lambda record: record["retrieval_policy"]["risk_level"],
        "current_status": lambda record: record["governance"]["current_status"],
        "version_check_status": lambda record: record["governance"]["version_check_status"],
        "license_status": lambda record: record["governance"]["license_status"],
        "data_classification": lambda record: record["governance"]["data_classification"],
        "distribution_scope": lambda record: record["governance"]["distribution_scope"],
    }
    fields = {}
    for field, selector in selectors.items():
        values = _unique_values(selector(record) for record in records)
        fields[field] = {
            "classification": "controlled_enum",
            "canonical_values": values,
            "evidence": [
                {
                    "path": record["provenance"]["prior_artifact_path"],
                    "field": field,
                }
                for record in records
                if selector(record) in values
            ][:17],
        }
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "scope": "source-scoped evidence snapshot; not a canonical global registry",
        "validation_input_inventory_sha256": input_inventory_sha256,
        "fields": fields,
    }


def _version_difference_summary(
    records: Sequence[dict[str, Any]], review_rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    warning_counts = Counter(
        warning for record in records for warning in record["provenance"]["mapping_warnings"]
    )
    block_counts = Counter(
        reason
        for record in records
        for reason in record["retrieval_policy"]["retrieval_block_reasons"]
    )
    official_chunks = sum(record["provenance"]["is_official_source"] for record in records)
    official_sources = {
        record["identity"]["source_id"]
        for record in records
        if record["provenance"]["is_official_source"]
    }
    all_sources = {record["identity"]["source_id"] for record in records}
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "prior_shape": {"nested_metadata_chunks": 661, "flat_metadata_chunks": 65},
        "successor_shape": {"canonical_rag_chunk_v2_chunks": len(records)},
        "source_count": len(all_sources),
        "chunk_count": len(records),
        "official_source_count": len(official_sources),
        "official_chunk_count": official_chunks,
        "research_source_count": len(all_sources) - len(official_sources),
        "research_chunk_count": len(records) - official_chunks,
        "text_changed_count": 0,
        "embedding_text_changed_count": 0,
        "successor_id_count": len(records),
        "review_row_count": len(review_rows),
        "mapping_warning_counts": dict(sorted(warning_counts.items())),
        "retrieval_block_reason_counts": dict(sorted(block_counts.items())),
        "status_changes_applied_automatically": False,
        "production_approved": False,
    }


def _validation_report(
    records: Sequence[dict[str, Any]],
    review_rows: Sequence[dict[str, Any]],
    *,
    inventory_sha256: str,
    prior_lock_sha256: str,
) -> dict[str, Any]:
    eligible = sum(record["retrieval_policy"]["retrieval_eligible"] for record in records)
    checks = [
        {"name": "chunk_count", "status": "PASS", "observed": len(records)},
        {
            "name": "unique_successor_ids",
            "status": "PASS",
            "observed": len({record["identity"]["chunk_id"] for record in records}),
        },
        {"name": "text_bytes_unchanged", "status": "PASS", "observed": len(records)},
        {
            "name": "embedding_text_bytes_unchanged",
            "status": "PASS",
            "observed": len(records),
        },
        {"name": "retrieval_eligible", "status": "PASS", "observed": eligible},
        {
            "name": "human_review_rows",
            "status": "PASS",
            "observed": len(review_rows),
        },
        {
            "name": "production_approved_false",
            "status": "PASS",
            "observed": len(records),
        },
        {"name": "prior_artifact_lock", "status": "PASS"},
    ]
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "preflight_version": PREFLIGHT_VERSION,
        "status": "PASS",
        "pass_count": len(checks),
        "fail_count": 0,
        "validation_input_inventory_sha256": inventory_sha256,
        "prior_artifact_lock_sha256": prior_lock_sha256,
        "checks": checks,
        "review_status": "needs_review",
        "production_approved": False,
    }


def _test_evidence_document(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise V2ArtifactError(
                "pytest JUnit evidence is required before a formal candidate build"
            )
        return {
            "schema_version": "1.0.0",
            "artifact_version": ARTIFACT_VERSION,
            "status": "NOT_PROVIDED",
            "evidence_path": TEST_EVIDENCE_PATH.as_posix(),
            "production_approved": False,
        }
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise V2ArtifactError("pytest JUnit evidence is unreadable") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise V2ArtifactError("pytest JUnit evidence contains no test suites")
    totals = {
        name: sum(int(suite.attrib.get(name, "0")) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    if totals["tests"] < 1:
        raise V2ArtifactError("pytest JUnit evidence contains no tests")
    if totals["failures"] or totals["errors"]:
        raise V2ArtifactError("pytest JUnit evidence contains failed tests")
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "status": "PASS",
        "command": (
            "uv run --project services/rag-ingestion pytest "
            "services/rag-ingestion/tests --junitxml="
            "data/rag-v2/evidence/v002/pytest-rag-ingestion.xml"
        ),
        "evidence_path": TEST_EVIDENCE_PATH.as_posix(),
        "evidence_sha256": _sha256_file(path),
        **totals,
        "production_approved": False,
    }


def _validate_records(
    records_by_source: Mapping[str, Sequence[dict[str, Any]]],
    prior_by_id: Mapping[str, ValidatedChunk],
) -> None:
    records = [record for values in records_by_source.values() for record in values]
    if len(records) != 726 or len(records_by_source) != 17:
        raise V2ArtifactError("selected dataset is not the frozen 17-source/726-chunk set")
    successor_ids = [record["identity"]["chunk_id"] for record in records]
    if len(successor_ids) != len(set(successor_ids)):
        raise V2ArtifactError("successor chunk IDs are not unique")
    for source_id, source_records in records_by_source.items():
        indexes = sorted(record["identity"]["chunk_index"] for record in source_records)
        if indexes != list(range(1, len(source_records) + 1)):
            raise V2ArtifactError(f"chunk indexes are not continuous for {source_id}")
    for record in records:
        identity = record["identity"]
        content = record["content"]
        prior = prior_by_id[identity["prior_chunk_id"]]
        if content["text"].encode("utf-8") != prior.text.encode("utf-8"):
            raise V2ArtifactError(f"text bytes changed for {identity['prior_chunk_id']}")
        if content["embedding_text"].encode("utf-8") != prior.embedding_text.encode("utf-8"):
            raise V2ArtifactError(f"embedding_text bytes changed for {identity['prior_chunk_id']}")
        if content["char_count"] != len(content["text"]):
            raise V2ArtifactError(f"char_count mismatch for {identity['chunk_id']}")
        if content["text_sha256"] != _sha256_text(content["text"]):
            raise V2ArtifactError(f"text hash mismatch for {identity['chunk_id']}")
        if content["embedding_text_sha256"] != _sha256_text(content["embedding_text"]):
            raise V2ArtifactError(f"embedding hash mismatch for {identity['chunk_id']}")
        policy = record["retrieval_policy"]
        if policy["retrieval_eligible"] is not (not policy["retrieval_block_reasons"]):
            raise V2ArtifactError(f"eligibility mismatch for {identity['chunk_id']}")
        if record["governance"]["review_status"] != "needs_review":
            raise V2ArtifactError("automatic review promotion is forbidden")
        if record["governance"]["production_approved"] is not False:
            raise V2ArtifactError("automatic production approval is forbidden")


def _validation_inventory_entries(root: Path) -> list[dict[str, Any]]:
    paths = set(_VALIDATION_FIXED_PATHS)
    paths.update(path.relative_to(root) for path in (root / CHUNKS_DIRECTORY).glob("*.jsonl"))
    paths.update(path.relative_to(root) for path in (root / "config/rag").glob("*"))
    paths.update(path.relative_to(root) for path in (root / "contracts/schemas/rag").glob("*.json"))
    return _file_entries(root, paths)


def _prior_lock_entries(root: Path) -> list[dict[str, Any]]:
    paths = set(_PRIOR_FORMAL_PATHS)
    paths.update(path.relative_to(root) for path in (root / CHUNKS_DIRECTORY).glob("*.jsonl"))
    return _file_entries(root, paths)


def _file_entries(root: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    entries = []
    for relative in sorted(paths, key=lambda path: path.as_posix()):
        path = root / relative
        if not path.is_file():
            raise V2ArtifactError(f"inventory path is missing: {relative.as_posix()}")
        entries.append(
            {
                "path": relative.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return entries


def _inventory_document(kind: str, entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_version": PREFLIGHT_VERSION,
        "kind": kind,
        "entry_count": len(entries),
        "inventory_sha256": _inventory_sha256(entries),
        "entries": list(entries),
    }


def _assert_inventory_matches(
    frozen: Mapping[str, Any], current_entries: Sequence[dict[str, Any]], label: str
) -> None:
    if frozen.get("entries") != list(current_entries):
        raise V2ArtifactError(f"{label} inventory changed after preflight")
    if frozen.get("inventory_sha256") != _inventory_sha256(current_entries):
        raise V2ArtifactError(f"{label} inventory digest changed after preflight")


def _inventory_sha256(entries: Sequence[dict[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(payload)


def _source_titles(path: Path) -> dict[str, str]:
    document = _read_json(path)
    titles = {}
    for item in document.get("candidates", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            title = item.get("title")
            if isinstance(title, str) and title.strip():
                titles[item["id"]] = title
    return titles


def _string_value(data: Mapping[str, Any], name: str, warnings: list[str]) -> str | None:
    values = _same_field_values(data, name)
    if len({_json_token(value) for _, value in values}) > 1:
        warnings.append(f"{name}_conflict")
    if not values:
        return None
    value = values[0][1]
    if not isinstance(value, str) or not value.strip():
        warnings.append(f"{name}_invalid_string")
        return None
    return value


def _bool_value(data: Mapping[str, Any], name: str, warnings: list[str]) -> bool | None:
    values = _same_field_values(data, name)
    if len({_json_token(value) for _, value in values}) > 1:
        warnings.append(f"{name}_conflict")
    if not values:
        return None
    value = values[0][1]
    if not isinstance(value, bool):
        warnings.append(f"{name}_invalid_boolean")
        return None
    return value


def _same_field_values(data: Mapping[str, Any], name: str) -> list[tuple[str, Any]]:
    values = []
    value = data.get(name)
    if value is not None:
        values.append((name, value))
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get(name)
        if value is not None:
            values.append((f"metadata.{name}", value))
    return values


def _first_string_alias(
    data: Mapping[str, Any], names: Sequence[str], warnings: list[str]
) -> str | None:
    for name in names:
        value = _string_value(data, name, warnings)
        if value is not None:
            return value
    return None


def _url_value(data: Mapping[str, Any], name: str, warnings: list[str]) -> str | None:
    value = _string_value(data, name, warnings)
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        warnings.append(f"{name}_invalid_url")
        return None
    return value


def _positive_int_value(
    data: Mapping[str, Any],
    names: Sequence[str],
    canonical_name: str,
    warnings: list[str],
) -> int | None:
    for name in names:
        values = _same_field_values(data, name)
        if not values:
            continue
        value = values[0][1]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            warnings.append(f"{canonical_name}_invalid_integer")
            return None
        return value
    return None


def _validate_page_pair(start: int | None, end: int | None, name: str, warnings: list[str]) -> None:
    if (start is None) != (end is None):
        warnings.append(f"{name}_half_populated")
    elif start is not None and end is not None and end < start:
        warnings.append(f"{name}_invalid_range")


def _normalize_language_locale(
    data: Mapping[str, Any], warnings: list[str]
) -> tuple[str | None, str | None]:
    raw_language = _string_value(data, "language", warnings)
    raw_locale = _string_value(data, "locale", warnings)
    if raw_language in {"zh-Hant", "zh-TW"}:
        language = "zh-Hant"
        locale = raw_locale or "zh-TW"
    elif raw_language == "en":
        language = "en"
        locale = raw_locale
    else:
        language = None
        locale = raw_locale
        warnings.append("language_missing_or_unsupported")
    if locale is not None and locale not in _CANONICAL_LOCALES:
        warnings.append("locale_not_in_v2_enum")
        locale = None
    if language is not None and language not in _CANONICAL_LANGUAGES:
        warnings.append("language_not_in_v2_enum")
        language = None
    return language, locale


def _unique_values(values: Iterable[Any]) -> list[Any]:
    tokens: dict[str, Any] = {}
    for value in values:
        if value is None or value == "":
            continue
        tokens[_json_token(value)] = value
    return [tokens[token] for token in sorted(tokens)]


def _json_token(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_readme() -> str:
    return (
        "# RagChunkV2 v001 candidate\n\n"
        "This directory is a local staging candidate generated from the immutable V1 "
        "bundle.\n\n"
        "- Review status: `needs_review`\n"
        "- Human source review: `not_completed`\n"
        "- Embedding status: `not_started`\n"
        "- Production approved: `false`\n"
        "- Storage target: `local_pending_upload`\n\n"
        "The 14 official Taiwanese sources follow the public-knowledge processing gates. "
        "The three non-official public research/scale sources remain explicitly classified "
        "as research evidence and are never promoted to official authority. Existing V1 "
        "files, text, and embedding text are not modified.\n"
    )


def _write_checksums(root: Path) -> None:
    entries = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            entries.append(f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}")
    _write_text(root / "SHA256SUMS.txt", "\n".join(entries) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    ]
    _write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except _DuplicateJsonKey as exc:
        raise V2ArtifactError(f"duplicate JSON key in {path.name}: {exc.key}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V2ArtifactError(f"cannot read JSON input {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise V2ArtifactError(f"JSON input must be an object: {path.name}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
