"""Offline preparation checks; never exercise providers, runtime or holdout queries."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from rag_ingestion.knowledge_pipeline import (
    KnowledgePipelineError,
    compile_corpus,
    read_jsonl,
    write_dataset,
)

ROOT = Path(__file__).resolve().parents[4]
CORPUS = ROOT / "data/rag-rechunk/successor/v001/corpus.jsonl"


@pytest.fixture
def official_row():
    return copy.deepcopy(
        next(
            row
            for row in read_jsonl(CORPUS)
            if row["provenance"]["is_official_source"]
            and row["governance"]["current_status"] == "current"
            and "rechunk" not in row
        )
    )


def save_rows(tmp_path, rows):
    path = tmp_path / "input.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(
    "payload",
    [
        '{"a":1,"a":2}\n',
        '{"a":{"b":1,"b":2}}\n',
        '{"a":NaN}\n',
        '{"a":Infinity}\n',
        '{"a":-Infinity}\n',
        '{"a":{"b":[1e999]}}\n',
        "{}\n\n{}\n",
        "{broken}\n",
    ],
)
def test_reader_rejects_ambiguous_or_malformed_json(tmp_path, payload):
    path = tmp_path / "bad.jsonl"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(KnowledgePipelineError):
        read_jsonl(path)


def test_real_corpus_preserves_source_content_and_policy():
    original = {row["identity"]["chunk_id"]: row for row in read_jsonl(CORPUS)}
    result = compile_corpus(CORPUS)
    summary = result.report["summary"]
    assert result.report["status"] != "FAILED"
    assert (
        summary["input_count"],
        summary["retained_count"],
        summary["excluded_count"],
        summary["error_count"],
    ) == (735, 658, 77, 0)
    assert len(result.chunks) == 658
    for chunk in result.chunks:
        row = original[chunk["chunk_id"]]
        assert row["provenance"]["is_official_source"] is True
        for key in ("text", "embedding_text", "text_sha256", "embedding_text_sha256"):
            assert chunk["content"][key] == row["content"][key]
        assert chunk["policy"]["current_status"] == row["governance"]["current_status"]
        assert (
            chunk["policy"]["retrieval_eligible"] == row["retrieval_policy"]["retrieval_eligible"]
        )
        for key in ("requires_official_assessment", "requires_professional_assessment"):
            assert chunk["policy"][key] == row["retrieval_policy"][key]
        assert chunk["provenance"]["review_status"] == row["governance"]["review_status"]
        assert (
            chunk["provenance"]["human_source_review"] == row["governance"]["human_source_review"]
        )


@pytest.mark.parametrize("defect", ["hash", "locator", "page", "duplicate", "schema"])
def test_invalid_content_fails_and_cannot_be_written(tmp_path, official_row, defect):
    rows = [official_row]
    if defect == "hash":
        official_row["content"]["text"] += " changed"
    elif defect == "locator":
        official_row["citation"]["source_locator"] = ""
    elif defect == "page":
        official_row["citation"]["physical_page_start"] = 99
        official_row["citation"]["physical_page_end"] = 1
    elif defect == "duplicate":
        rows.append(copy.deepcopy(official_row))
    else:
        official_row["retrieval_policy"]["requires_official_assessment"] = "yes"
    result = compile_corpus(save_rows(tmp_path, rows))
    assert result.report["status"] == "FAILED"
    assert result.report["summary"]["error_count"] > 0
    assert any(issue["severity"] == "ERROR" for issue in result.report["issues"])
    with pytest.raises(KnowledgePipelineError):
        write_dataset(result, tmp_path / "output")
    assert not (tmp_path / "output/chunks.jsonl").exists()


@pytest.mark.parametrize("text", ["完整短句。", "來源完整句子。" * 1000], ids=["short", "long"])
def test_size_and_unknown_metadata_warn_without_rewriting(tmp_path, official_row, text):
    official_row["content"]["text"] = text
    official_row["content"]["char_count"] = len(text)
    official_row["content"]["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    official_row["governance"]["current_status"] = "unknown"
    official_row["retrieval_policy"]["requires_official_assessment"] = None
    result = compile_corpus(save_rows(tmp_path, [official_row]))
    assert result.report["status"] != "FAILED"
    assert result.report["summary"]["warning_count"] > 0
    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk["content"]["text"] == text
    assert chunk["policy"]["current_status"] == "unknown"
    assert chunk["policy"]["requires_official_assessment"] is None
    assert chunk["provenance"]["review_status"] == official_row["governance"]["review_status"]


def test_baseline_compares_content_without_claiming_existing_vectors(tmp_path, official_row):
    baseline = save_rows(tmp_path, [official_row])
    same = compile_corpus(baseline, baseline_path=baseline)
    assert same.report["embedding_comparison"]["unchanged_content_count"] == 1
    assert same.report["embedding_comparison"]["changed_content_count"] == 0
    assert same.report["embedding_comparison"]["available_vectors_verified"] is False
    changed = copy.deepcopy(official_row)
    changed["content"]["embedding_text"] += " new context"
    changed["content"]["embedding_char_count"] = len(changed["content"]["embedding_text"])
    changed["content"]["embedding_text_sha256"] = hashlib.sha256(
        changed["content"]["embedding_text"].encode()
    ).hexdigest()
    candidate = tmp_path / "changed.jsonl"
    candidate.write_text(json.dumps(changed) + "\n", encoding="utf-8")
    result = compile_corpus(candidate, baseline_path=baseline)
    assert result.report["embedding_comparison"]["unchanged_content_count"] == 0
    assert result.report["embedding_comparison"]["changed_content_count"] == 1
    assert result.report["embedding_comparison"]["available_vectors_verified"] is False


def test_writer_is_idempotent_and_refuses_changed_output(tmp_path, official_row):
    result = compile_corpus(save_rows(tmp_path, [official_row]))
    output = tmp_path / "dataset"
    write_dataset(result, output)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    write_dataset(result, output)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    (output / "chunks.jsonl").write_text("changed\n", encoding="utf-8")
    with pytest.raises(KnowledgePipelineError):
        write_dataset(result, output)
    assert (output / "chunks.jsonl").read_text(encoding="utf-8") == "changed\n"


def test_all_excluded_corpus_cannot_publish_empty_dataset(tmp_path, official_row):
    official_row["provenance"]["is_official_source"] = False
    result = compile_corpus(save_rows(tmp_path, [official_row]))
    assert result.report["status"] == "FAILED"
    assert result.report["summary"]["excluded_count"] == 1
    assert any(i["code"] == "EMPTY_RETAINED_CORPUS" for i in result.report["issues"])
    with pytest.raises(KnowledgePipelineError):
        write_dataset(result, tmp_path / "empty")


def test_previous_normalized_dataset_can_be_next_baseline(tmp_path, official_row):
    source = save_rows(tmp_path, [official_row])
    previous = compile_corpus(source)
    output = tmp_path / "previous"
    write_dataset(previous, output)
    result = compile_corpus(source, baseline_path=output)
    assert result.report["embedding_comparison"] == {
        "unchanged_content_count": 1,
        "changed_content_count": 0,
        "available_vectors_verified": False,
    }


@pytest.mark.parametrize("defect", ["hash", "schema"])
def test_normalized_baseline_still_validates_content_and_metadata(tmp_path, official_row, defect):
    source = save_rows(tmp_path, [official_row])
    row = compile_corpus(source).chunks[0]
    if defect == "hash":
        row["content"]["embedding_text"] += " changed"
    else:
        row["source"]["locator"] = None
    baseline = tmp_path / "normalized.jsonl"
    baseline.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(KnowledgePipelineError, match="INVALID_BASELINE_CONTENT"):
        compile_corpus(source, baseline_path=baseline)


AUDIENCE_PATCHES = ROOT / "config/rag/knowledge-audience-patches.json"
BA13_ID = "mohw_a_unit_case_manager_manual_appendix_20230719_rechunk_successor_v006_0012"


def save_patches(tmp_path, document):
    path = tmp_path / "patches.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_real_ba13_patch_changes_only_target_audience_and_not_input_bytes():
    before_bytes = CORPUS.read_bytes()
    original = compile_corpus(CORPUS)
    patched = compile_corpus(CORPUS, dataset_version="v008", audience_patches_path=AUDIENCE_PATCHES)
    assert patched.report["status"] == "PASS"
    assert patched.report["summary"] == original.report["summary"]
    differences = patched.report["audience_patch_differences"]
    assert len(differences) == 1
    assert differences[0]["chunk_id"] == BA13_ID
    assert differences[0]["field"] == "policy.audiences"
    assert "audience_patch_differences" not in original.report
    for before, after in zip(original.chunks, patched.chunks, strict=True):
        expected = copy.deepcopy(before)
        if before["chunk_id"] == BA13_ID:
            expected["policy"]["audiences"] = ["care_professional", "family_caregiver"]
        assert after == expected
    assert CORPUS.read_bytes() == before_bytes


@pytest.mark.parametrize(
    "defect", ["missing", "source", "hash", "roles", "duplicate", "remove", "extra"]
)
def test_patch_precondition_failures_cannot_write_or_mutate_chunks(tmp_path, defect):
    document = json.loads(AUDIENCE_PATCHES.read_text(encoding="utf-8"))
    patch = document["patches"][0]
    if defect == "missing":
        patch["chunk_id"] = "missing-chunk"
    elif defect == "source":
        patch["expected_source_id"] = "other-source"
    elif defect == "hash":
        patch["expected_text_sha256"] = "0" * 64
    elif defect == "roles":
        patch["from_audiences"] = ["elder"]
        patch["to_audiences"] = ["elder", "family_caregiver"]
    elif defect == "duplicate":
        document["patches"].append(copy.deepcopy(patch))
    elif defect == "remove":
        patch["to_audiences"] = ["family_caregiver"]
    else:
        patch["review_status"] = "verified"
    original = compile_corpus(CORPUS)
    failed = compile_corpus(CORPUS, audience_patches_path=save_patches(tmp_path, document))
    assert failed.report["status"] == "FAILED"
    assert failed.report["audience_patch_differences"] == []
    assert failed.chunks == original.chunks
    with pytest.raises(KnowledgePipelineError):
        write_dataset(failed, tmp_path / "output")


def test_patch_set_is_atomic_when_later_patch_has_no_match(tmp_path):
    document = json.loads(AUDIENCE_PATCHES.read_text(encoding="utf-8"))
    second = copy.deepcopy(document["patches"][0])
    second["chunk_id"] = "not-in-corpus"
    document["patches"].append(second)
    failed = compile_corpus(CORPUS, audience_patches_path=save_patches(tmp_path, document))
    assert failed.report["status"] == "FAILED"
    assert failed.report["audience_patch_differences"] == []
    target = next(row for row in failed.chunks if row["chunk_id"] == BA13_ID)
    assert target["policy"]["audiences"] == ["care_professional"]


def test_patch_config_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "patches.json"
    path.write_text('{"schema_version":"a","schema_version":"b","patches":[]}', encoding="utf-8")
    failed = compile_corpus(CORPUS, audience_patches_path=path)
    assert failed.report["status"] == "FAILED"
    assert failed.report["audience_patch_differences"] == []


def test_explicit_patch_repeat_is_idempotent_against_original_input(tmp_path):
    original = compile_corpus(
        CORPUS, dataset_version="v008", audience_patches_path=AUDIENCE_PATCHES
    )
    repeated = compile_corpus(
        CORPUS, dataset_version="v008", audience_patches_path=AUDIENCE_PATCHES
    )
    output = tmp_path / "v008"
    write_dataset(original, output)
    write_dataset(repeated, output)
    assert original == repeated
