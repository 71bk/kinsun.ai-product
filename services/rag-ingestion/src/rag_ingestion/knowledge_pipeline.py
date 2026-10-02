"""Local public-knowledge preparation, independent of legacy review packages.

This module checks supplied source records, not the current state of a website.
It preserves retrieval policy and human provenance; neither a successful build
nor an embedding plan authorizes runtime activation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = ROOT / "contracts/schemas/rag/knowledge-chunk-v1.schema.json"


class KnowledgePipelineError(ValueError):
    """Data preparation failure; messages omit source text and credentials."""


@dataclass(frozen=True)
class Compilation:
    chunks: tuple[dict, ...]
    report: dict


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise KnowledgePipelineError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_value):
    raise KnowledgePipelineError("NONFINITE_JSON_NUMBER")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise KnowledgePipelineError("NONFINITE_JSON_NUMBER")
    return result


def read_jsonl(path: Path) -> list[dict]:
    """Read only local UTF-8 objects, rejecting ambiguous or malformed JSONL."""
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                raise KnowledgePipelineError("BLANK_JSONL_LINE")
            row = json.loads(
                line,
                object_pairs_hook=_object,
                parse_constant=_constant,
                parse_float=_finite_float,
            )
            if not isinstance(row, dict):
                raise KnowledgePipelineError("JSONL_OBJECT_REQUIRED")
            rows.append(row)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise KnowledgePipelineError("UNREADABLE_JSONL") from exc
    if not rows:
        raise KnowledgePipelineError("EMPTY_CORPUS")
    return rows


def _rows(path: Path) -> list[dict]:
    if path.is_file():
        return read_jsonl(path)
    files = sorted(path.glob("*.jsonl"))
    if not files:
        raise KnowledgePipelineError("MISSING_BASELINE")
    return [row for member in files for row in read_jsonl(member)]


def _required_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _content_errors(row: dict, *, require_counts: bool = True) -> list[str]:
    content = row.get("content")
    if not isinstance(content, dict):
        return ["MISSING_CONTENT"]
    errors = []
    for field in ("text", "embedding_text"):
        text = content.get(field)
        if not _required_text(text):
            errors.append(f"EMPTY_{field.upper()}")
            continue
        if "\ufffd" in text:
            errors.append("REPLACEMENT_CHARACTER")
        if sha256(text) != content.get(f"{field}_sha256"):
            errors.append(f"{field.upper()}_HASH_MISMATCH")
        count = "char_count" if field == "text" else "embedding_char_count"
        if require_counts and (type(content.get(count)) is not int or content[count] != len(text)):
            errors.append(f"{field.upper()}_CHAR_COUNT_MISMATCH")
    return errors


def _normalize(row: dict) -> dict:
    identity, citation = row["identity"], row["citation"]
    content, provenance = row["content"], row["provenance"]
    governance, policy = row["governance"], row["retrieval_policy"]
    url = next(
        (
            citation.get(field)
            for field in (
                "direct_source_url",
                "direct_official_source_url",
                "source_page_url",
                "official_source_page_url",
            )
            if _required_text(citation.get(field))
        ),
        None,
    )
    prior_ids = row.get("rechunk", {}).get("prior_chunk_ids")
    if prior_ids is None:
        prior = identity.get("prior_chunk_id")
        prior_ids = [prior] if prior is not None else []
    return {
        "schema_version": "1.0",
        "chunk_id": identity["chunk_id"],
        "source": {
            "id": identity["source_id"],
            "title": citation.get("title"),
            "url": url,
            "version": provenance.get("source_version"),
            "section": citation.get("section") or None,
            "locator": citation.get("source_locator"),
            "page_start": citation.get("physical_page_start"),
            "page_end": citation.get("physical_page_end"),
            "official": provenance["is_official_source"],
            "published_at": provenance.get("published_at"),
            "version_date": provenance.get("source_version_date"),
        },
        "content": {
            **{
                key: content[key]
                for key in (
                    "text",
                    "embedding_text",
                    "text_sha256",
                    "embedding_text_sha256",
                    "language",
                    "locale",
                )
            },
            "type": content["content_type"],
        },
        "policy": {
            "audiences": policy["allowed_audiences"],
            "purposes": policy["allowed_purposes"],
            "current_status": governance["current_status"],
            **{
                key: policy[key]
                for key in (
                    "risk_level",
                    "stop_normal_rag",
                    "requires_official_assessment",
                    "requires_professional_assessment",
                    "retrieval_eligible",
                )
            },
            "block_reasons": policy["retrieval_block_reasons"],
        },
        "provenance": {
            "artifact_version": row["artifact_version"],
            "prior_chunk_ids": prior_ids,
            **{
                key: governance[key]
                for key in (
                    "review_status",
                    "human_source_review",
                    "data_classification",
                    "distribution_scope",
                    "license_status",
                )
            },
        },
    }


def _source_errors(chunk: dict) -> list[str]:
    source = chunk["source"]
    errors = []
    if source["official"] is not True:
        errors.append("INVALID_OFFICIAL_FLAG")
    try:
        parsed = urlsplit(source["url"])
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            errors.append("INVALID_SOURCE_URL")
        elif not (parsed.hostname == "gov.tw" or parsed.hostname.endswith(".gov.tw")):
            errors.append("UNSUPPORTED_OFFICIAL_SOURCE_HOST")
    except (TypeError, ValueError, AttributeError):
        errors.append("INVALID_SOURCE_URL")
    start, end = source["page_start"], source["page_end"]
    if (start is None) != (end is None) or (
        start is not None and (type(start) is not int or type(end) is not int or start > end)
    ):
        errors.append("INVALID_PAGE_RANGE")
    if chunk["provenance"]["data_classification"].lower() == "restricted":
        errors.append("RESTRICTED_DATA_NOT_SUPPORTED")
    return errors


def compile_corpus(
    corpus_path: Path, *, dataset_version: str = "v007", baseline_path: Path | None = None
) -> Compilation:
    """Prepare supplied official chunks without creating any human review task.

    Exclusions leave the original corpus untouched. Short/long content, unknown
    currency and missing assessment metadata are visible warnings, not invented
    semantic judgments. Existing retrieval gates are preserved for phase 3.
    """
    if re.fullmatch(r"v[0-9]{3,}", dataset_version) is None:
        raise KnowledgePipelineError("INVALID_DATASET_VERSION")
    rows = read_jsonl(corpus_path)
    validator = Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )
    issues, chunks = [], []
    seen: set[str] = set()
    source_counts: Counter = Counter()
    excluded: Counter = Counter()
    content_groups = defaultdict(list)
    source_versions = defaultdict(lambda: defaultdict(list))

    def issue(cid: str, severity: str, code: str, **extra):
        issues.append({"chunk_id": cid, "severity": severity, "code": code, **extra})

    for index, row in enumerate(rows, 1):
        identity = row.get("identity", {})
        cid = identity.get("chunk_id") if isinstance(identity, dict) else None
        if not _required_text(cid):
            issue(f"line:{index}", "ERROR", "MISSING_CHUNK_ID")
            continue
        if cid in seen:
            issue(cid, "ERROR", "DUPLICATE_CHUNK_ID")
            continue
        seen.add(cid)
        errors = _content_errors(row)
        if errors:
            for code in sorted(set(errors)):
                issue(cid, "ERROR", code)
            continue
        try:
            official = row["provenance"]["is_official_source"]
            if type(official) is not bool:
                raise KnowledgePipelineError("INVALID_OFFICIAL_FLAG")
            if not _required_text(identity.get("source_id")):
                raise KnowledgePipelineError("MISSING_SOURCE_ID")
            source_counts[identity["source_id"]] += 1
            reason = None
            if not official:
                reason = "NON_OFFICIAL_REFERENCE"
            elif row["governance"]["current_status"] == "superseded":
                reason = "SUPERSEDED_SOURCE"
            elif row.get("rechunk", {}).get("recommended_use") == "navigation_only":
                reason = "NAVIGATION_ONLY"
            if reason:
                excluded[reason] += 1
                issue(cid, "EXCLUDED", reason)
                continue
            chunk = _normalize(row)
        except KnowledgePipelineError as exc:
            issue(cid, "ERROR", str(exc))
            continue
        except (KeyError, TypeError, AttributeError):
            issue(cid, "ERROR", "MISSING_OR_INVALID_METADATA")
            continue
        schema_errors = sorted(validator.iter_errors(chunk), key=lambda e: str(e.path))
        if schema_errors:
            issue(
                cid,
                "ERROR",
                "INVALID_CHUNK_SCHEMA",
                fields=[".".join(map(str, error.path)) for error in schema_errors],
            )
            continue
        errors = _source_errors(chunk)
        if errors:
            for code in errors:
                issue(cid, "ERROR", code)
            continue
        source, content, policy = chunk["source"], chunk["content"], chunk["policy"]
        warnings = []
        if len(content["text"]) < 100:
            warnings.append("SHORT_SEMANTIC_UNIT_CHECK")
        if len(content["text"]) > 1800:
            warnings.append("LONG_SEMANTIC_UNIT_CHECK")
        if policy["current_status"] == "unknown":
            warnings.append("SOURCE_CURRENCY_UNKNOWN")
        if source["version"] in (None, "unknown"):
            warnings.append("SOURCE_VERSION_UNKNOWN")
        if not policy["audiences"] or not policy["purposes"]:
            warnings.append("MISSING_RETRIEVAL_SCOPE")
        if any(
            policy[field] is None
            for field in ("requires_official_assessment", "requires_professional_assessment")
        ):
            warnings.append("ASSESSMENT_METADATA_UNKNOWN")
        if not policy["retrieval_eligible"] or policy["block_reasons"]:
            warnings.append("EXISTING_RETRIEVAL_RESTRICTION")
        for code in warnings:
            issue(cid, "WARNING", code)
        content_groups[content["text_sha256"]].append(cid)
        if policy["current_status"] == "current" and source["version"] not in (None, "unknown"):
            source_versions[source["id"]][source["version"]].append(cid)
        chunks.append(chunk)
    for ids in content_groups.values():
        if len(ids) > 1:
            for cid in ids:
                issue(cid, "WARNING", "DUPLICATE_TEXT_DIFFERENT_ID", related_chunk_ids=ids)
    for versions in source_versions.values():
        if len(versions) > 1:
            for ids in versions.values():
                for cid in ids:
                    issue(cid, "ERROR", "CONFLICTING_CURRENT_SOURCE_VERSIONS")
    chunks.sort(key=lambda c: c["chunk_id"])
    if not chunks:
        issue("corpus", "ERROR", "EMPTY_RETAINED_CORPUS")
    errors = sum(item["severity"] == "ERROR" for item in issues)
    report = {
        "schema_version": "knowledge-dataset-v1",
        "dataset_version": dataset_version,
        "status": "FAILED" if errors else "PASS",
        "production_approved": False,
        "activation_allowed": False,
        "source_check": "LOCAL_METADATA_AND_CONTENT_ONLY",
        "freshness_verified_online": False,
        "manual_review_required_for_build": False,
        "summary": {
            "input_count": len(rows),
            "retained_count": len(chunks),
            "excluded_count": sum(excluded.values()),
            "error_count": errors,
            "warning_count": sum(item["severity"] == "WARNING" for item in issues),
            "input_source_count": len(source_counts),
            "retained_source_count": len({c["source"]["id"] for c in chunks}),
        },
        "excluded_by_reason": dict(sorted(excluded.items())),
        "retained_by_source": dict(sorted(Counter(c["source"]["id"] for c in chunks).items())),
        "warnings_by_code": dict(
            sorted(Counter(i["code"] for i in issues if i["severity"] == "WARNING").items())
        ),
        "issues": issues,
    }
    if baseline_path is not None:
        baseline = _rows(baseline_path)
        hashes = set()
        for row in baseline:
            normalized = "chunk_id" in row
            if normalized and (not validator.is_valid(row) or _source_errors(row)):
                raise KnowledgePipelineError("INVALID_BASELINE_CONTENT")
            if _content_errors(row, require_counts=not normalized):
                raise KnowledgePipelineError("INVALID_BASELINE_CONTENT")
            hashes.add(row["content"]["embedding_text_sha256"])
        same = sum(c["content"]["embedding_text_sha256"] in hashes for c in chunks)
        report["embedding_comparison"] = {
            "unchanged_content_count": same,
            "changed_content_count": len(chunks) - same,
            "available_vectors_verified": False,
        }
    return Compilation(tuple(chunks), report)


def _json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def write_dataset(
    compilation: Compilation, output: Path, embedding_plan: dict | None = None
) -> None:
    """Write a small local dataset; identical repeat runs reuse existing files.

    Never mutate input/historical packages. Changed output needs a different
    explicit destination; this is overwrite protection, not an audit chain.
    """
    if compilation.report["status"] != "PASS":
        raise KnowledgePipelineError("INVALID_CORPUS_CANNOT_BE_WRITTEN")
    members = {
        "chunks.jsonl": b"".join(
            (json.dumps(c, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
            for c in compilation.chunks
        ),
        "report.json": _json(compilation.report),
    }
    if embedding_plan is not None:
        members["embedding-plan.json"] = _json(embedding_plan)
    if output.exists():
        if not output.is_dir() or output.is_symlink():
            raise KnowledgePipelineError("OUTPUT_ALREADY_EXISTS")
        if set(p.name for p in output.iterdir()) != set(members) or any(
            (output / name).is_symlink()
            or not (output / name).is_file()
            or (output / name).read_bytes() != value
            for name, value in members.items()
        ):
            raise KnowledgePipelineError("OUTPUT_CONTENT_DIFFERS")
        return
    output.mkdir(parents=True)
    created = []
    try:
        for name, value in members.items():
            with (output / name).open("xb") as stream:
                created.append(output / name)
                stream.write(value)
    except BaseException:
        # Only files created by this invocation may be removed on failure.
        for path in created:
            path.unlink(missing_ok=True)
        if not any(output.iterdir()):
            output.rmdir()
        raise
