from __future__ import annotations

import copy
import hashlib
import json

import pytest

from app.rag_knowledge_importer import load_knowledge_batch
from app.rag_projection_importer import ProjectionImportError


def _row():
    text = "Synthetic official source text."
    digest = hashlib.sha256(text.encode()).hexdigest()
    return {
        "schema_version": "1.0",
        "chunk_id": "synthetic-1",
        "source": {
            "id": "synthetic",
            "title": "Synthetic source",
            "url": "https://example.gov.tw/source",
            "version": None,
            "section": None,
            "locator": "page 1",
            "page_start": 1,
            "page_end": 1,
            "official": True,
            "published_at": None,
            "version_date": None,
        },
        "content": {
            "text": text,
            "embedding_text": text,
            "text_sha256": digest,
            "embedding_text_sha256": digest,
            "type": "service_guide",
            "language": "en",
            "locale": "en-US",
        },
        "policy": {
            "audiences": ["elder"],
            "purposes": ["general_information"],
            "current_status": "unknown",
            "risk_level": "low",
            "stop_normal_rag": False,
            "requires_official_assessment": None,
            "requires_professional_assessment": True,
            "retrieval_eligible": False,
            "block_reasons": ["current_status_not_current"],
        },
        "provenance": {
            "artifact_version": "v005",
            "prior_chunk_ids": ["prior-1"],
            "review_status": "needs_review",
            "human_source_review": "not_completed",
            "data_classification": "internal",
            "distribution_scope": "internal_knowledge",
            "license_status": "approved",
        },
    }


def _dataset(tmp_path, rows=None, **report_changes):
    report = {
        "schema_version": "knowledge-dataset-v1",
        "dataset_version": "v007",
        "status": "PASS",
        "production_approved": False,
        "activation_allowed": False,
        "chunk_count": 99999,
        "candidate_sha256": "fake",
        **report_changes,
    }
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "chunks.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in (rows if rows is not None else [_row()])),
        encoding="utf-8",
    )
    return tmp_path


def test_batch_recomputes_identity_and_preserves_unreviewed_policy(tmp_path):
    batch = load_knowledge_batch(_dataset(tmp_path))
    assert batch.chunk_count == batch.source_count == 1
    assert (
        batch.candidate_sha256
        == hashlib.sha256((tmp_path / "chunks.jsonl").read_bytes()).hexdigest()
    )
    assert batch.release_id == f"knowledge-v007-{batch.candidate_sha256[:12]}"
    chunk = batch.chunks[0]
    assert chunk.artifact_version == "v007"
    assert chunk.provenance["artifact_version"] == "v005"
    assert chunk.provenance["prior_chunk_ids"] == ["prior-1"]
    assert chunk.source_version is None
    assert chunk.review_status == "needs_review"
    assert chunk.requires_human_review is False
    assert chunk.requires_official_assessment is None
    assert chunk.requires_professional_assessment is True
    assert chunk.retrieval_eligible is False
    assert chunk.retrieval_policy["retrieval_block_reasons"] == ["current_status_not_current"]
    assert batch.production_approved is chunk.production_approved is False


@pytest.mark.parametrize(
    "change", ["hash", "duplicate", "citation", "scope", "assessment", "official", "empty"]
)
def test_invalid_records_are_rejected(tmp_path, change):
    row = _row()
    rows = [row]
    if change == "hash":
        row["content"]["text"] = "Changed"
    elif change == "duplicate":
        rows.append(copy.deepcopy(row))
    elif change == "citation":
        row["source"]["page_start"] = True
    elif change == "scope":
        row["policy"]["audiences"] = "elder"
    elif change == "assessment":
        row["policy"]["requires_professional_assessment"] = "false"
    elif change == "official":
        row["source"]["official"] = False
    else:
        rows = []
    with pytest.raises(ProjectionImportError):
        load_knowledge_batch(_dataset(tmp_path, rows))


@pytest.mark.parametrize("field", ["production_approved", "activation_allowed"])
def test_report_cannot_authorize_activation(tmp_path, field):
    with pytest.raises(ProjectionImportError):
        load_knowledge_batch(_dataset(tmp_path, **{field: True}))


@pytest.mark.parametrize("payload", ['{"chunk_id":"a","chunk_id":"b"}', '{"value":NaN}'])
def test_invalid_json_is_rejected(tmp_path, payload):
    _dataset(tmp_path)
    (tmp_path / "chunks.jsonl").write_text(payload, encoding="utf-8")
    with pytest.raises(ProjectionImportError):
        load_knowledge_batch(tmp_path)


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "ftp://example.gov.tw/file"},
        {"url": "https://user:password@example.gov.tw/file"},
        {"page_start": None},
        {"page_start": 2, "page_end": 1},
        {"official": 1},
    ],
)
def test_source_semantics_are_checked_beyond_schema(tmp_path, changes):
    row = _row()
    row["source"].update(changes)
    with pytest.raises(ProjectionImportError):
        load_knowledge_batch(_dataset(tmp_path, [row]))


def test_mixed_review_history_is_preserved_without_aggregate_verification(tmp_path):
    first, second = _row(), _row()
    second["chunk_id"] = "synthetic-2"
    second["provenance"].update(
        artifact_version="v006", review_status="verified", human_source_review="completed"
    )
    batch = load_knowledge_batch(_dataset(tmp_path, [first, second]))
    assert batch.review_status == "needs_review"
    assert batch.human_source_review == "not_completed"
    assert batch.chunks[1].review_status == "verified"
    assert batch.chunks[1].governance["human_source_review"] == "completed"


@pytest.mark.parametrize("suffix", ["\n", " \n"])
def test_blank_jsonl_lines_are_rejected(tmp_path, suffix):
    _dataset(tmp_path)
    path = tmp_path / "chunks.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + suffix, encoding="utf-8")
    with pytest.raises(ProjectionImportError, match="blank lines"):
        load_knowledge_batch(tmp_path)


@pytest.mark.parametrize("status", ["FAILED", "INCOMPLETE", None])
def test_failed_or_missing_report_status_is_rejected(tmp_path, status):
    with pytest.raises(ProjectionImportError):
        load_knowledge_batch(_dataset(tmp_path, status=status))


def test_long_dataset_version_is_supported(tmp_path):
    batch = load_knowledge_batch(_dataset(tmp_path, dataset_version="v1000"))
    assert batch.artifact_version == "v1000"


@pytest.mark.parametrize("url", ["https://example.com/source", "https://gov.tw.example.com/source"])
def test_self_declared_official_external_hosts_are_rejected(tmp_path, url):
    row = _row()
    row["source"]["url"] = url
    with pytest.raises(ProjectionImportError):
        load_knowledge_batch(_dataset(tmp_path, [row]))


@pytest.mark.parametrize("number", ["1e999", "-1e999"])
def test_report_overflow_numbers_are_rejected(tmp_path, number):
    _dataset(tmp_path)
    path = tmp_path / "report.json"
    payload = path.read_text(encoding="utf-8")
    path.write_text(payload[:-1] + ', "unused_metadata": ' + number + "}", encoding="utf-8")
    with pytest.raises(ProjectionImportError, match="JSON is invalid"):
        load_knowledge_batch(tmp_path)


@pytest.mark.parametrize("classification", ["restricted", "RESTRICTED"])
def test_restricted_data_is_rejected(tmp_path, classification):
    row = _row()
    row["provenance"]["data_classification"] = classification
    with pytest.raises(ProjectionImportError, match="restricted"):
        load_knowledge_batch(_dataset(tmp_path, [row]))
