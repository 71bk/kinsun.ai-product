"""Read a local knowledge dataset into a projection batch without authorizing it."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from app.rag_projection_importer import (
    ProjectionBatch,
    ProjectionImportError,
    _projection_chunk,
    _read_json,
    _reject_keys,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "contracts/schemas/rag/knowledge-chunk-v1.schema.json"
)


def _invalid_constant(value: str):
    raise ProjectionImportError("non-finite JSON number")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ProjectionImportError("non-finite JSON number")
    return result


def _parse(payload: str) -> dict:
    try:
        result = json.loads(
            payload,
            object_pairs_hook=_reject_keys,
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
        )
    except ValueError as exc:
        raise ProjectionImportError("knowledge dataset JSON is invalid") from exc
    if not isinstance(result, dict):
        raise ProjectionImportError("knowledge dataset JSON must be an object")
    return result


def load_knowledge_batch(dataset_dir: Path) -> ProjectionBatch:
    """Validate records locally; report metadata never grants runtime permission."""
    directory = dataset_dir.expanduser().resolve()
    report = _parse((directory / "report.json").read_text(encoding="utf-8"))
    if (
        report.get("schema_version") != "knowledge-dataset-v1"
        or report.get("status") != "PASS"
        or report.get("production_approved") is not False
        or report.get("activation_allowed") is not False
    ):
        raise ProjectionImportError(
            "knowledge report identification or activation boundary is invalid"
        )
    version = report.get("dataset_version")
    if not isinstance(version, str) or not re.fullmatch(r"v[0-9]{3,}", version):
        raise ProjectionImportError("knowledge dataset version is invalid")
    schema = _read_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    path = directory / "chunks.jsonl"
    payload = path.read_bytes()
    lines = payload.decode("utf-8").splitlines()
    if any(not raw.strip() for raw in lines):
        raise ProjectionImportError("knowledge JSONL contains blank lines")
    rows = [(line, _parse(raw)) for line, raw in enumerate(lines, 1)]
    if not rows:
        raise ProjectionImportError("knowledge dataset contains no chunks")
    indexes: Counter[str] = Counter()
    identifiers: set[str] = set()
    chunks = []
    for line, row in rows:
        if not validator.is_valid(row):
            raise ProjectionImportError(f"knowledge schema validation failed at line {line}")
        identifier = row["chunk_id"]
        if identifier in identifiers:
            raise ProjectionImportError("knowledge dataset contains duplicate chunk IDs")
        identifiers.add(identifier)
        source, content, policy, provenance = (
            row[key] for key in ("source", "content", "policy", "provenance")
        )
        if source["official"] is not True:
            raise ProjectionImportError("knowledge dataset must contain official sources")
        if provenance["data_classification"].lower() == "restricted":
            raise ProjectionImportError("restricted knowledge data is not permitted")
        try:
            url = urlsplit(source["url"])
            valid_url = (
                url.scheme in {"http", "https"}
                and bool(url.hostname)
                and (url.hostname == "gov.tw" or url.hostname.endswith(".gov.tw"))
                and url.username is None
                and url.password is None
            )
        except ValueError as exc:
            raise ProjectionImportError("knowledge source URL is invalid") from exc
        if not valid_url:
            raise ProjectionImportError("knowledge source URL must be HTTP(S) without credentials")
        start, end = source["page_start"], source["page_end"]
        if (start is None) != (end is None) or (
            start is not None and (type(start) is not int or type(end) is not int or start > end)
        ):
            raise ProjectionImportError("knowledge source page range is invalid")
        indexes[source["id"]] += 1
        mapped = {
            "schema_version": row["schema_version"],
            "artifact_version": version,
            "identity": {
                "chunk_id": identifier,
                "source_id": source["id"],
                "chunk_index": indexes[source["id"]],
            },
            "content": {**content, "content_type": content["type"]},
            "citation": {
                "title": source["title"],
                "section": source["section"],
                "direct_source_url": source["url"],
                "direct_official_source_url": source["url"],
                "source_locator": source["locator"],
                "physical_page_start": source["page_start"],
                "physical_page_end": source["page_end"],
            },
            "governance": {
                **provenance,
                "current_status": policy["current_status"],
                "production_approved": False,
            },
            "provenance": {
                **provenance,
                **source,
                "source_version": source["version"],
                "source_version_date": source["version_date"],
                "is_official_source": True,
            },
            "retrieval_policy": {
                **policy,
                "allowed_audiences": policy["audiences"],
                "allowed_purposes": policy["purposes"],
                "retrieval_block_reasons": policy["block_reasons"],
                "requires_human_review": False,
            },
        }
        chunks.append(_projection_chunk(mapped, source["id"], version))
    digest = hashlib.sha256(payload).hexdigest()
    reviews = {chunk.review_status for chunk in chunks}
    human_reviews = {chunk.governance["human_source_review"] for chunk in chunks}
    return ProjectionBatch(
        release_id=f"knowledge-{version}-{digest[:12]}",
        artifact_version=version,
        candidate_sha256=digest,
        source_count=len(indexes),
        chunk_count=len(chunks),
        review_status=next(iter(reviews)) if len(reviews) == 1 else "needs_review",
        human_source_review=next(iter(human_reviews))
        if len(human_reviews) == 1
        else "not_completed",
        production_approved=False,
        chunks=tuple(chunks),
    )
