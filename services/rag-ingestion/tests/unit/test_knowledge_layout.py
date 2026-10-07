"""PDF row relationships, source preconditions, and unchanged governance."""

from __future__ import annotations

import copy
import json
import sys

import pytest

from rag_ingestion.knowledge_layout import (
    _bounded_group_units,
    _text,
    graph_text,
    repair_corpus,
    table_records,
)
from rag_ingestion.knowledge_pipeline import (
    ROOT,
    KnowledgePipelineError,
    compile_corpus,
    sha256,
    write_dataset,
)

EXTRACTION = ROOT / "data/rag-layout/v001/extraction.jsonl"
sys.path.insert(0, str(ROOT))
from scripts.rag.repair_knowledge_layout import main as repair_main  # noqa: E402


def merged_table():
    return {
        "axes": [0, 100, 200],
        "headers": ["問題面向", "對應之給付碼"],
        "cells": [
            {"bbox": [0, 0, 100, 20], "text": "身體功能"},
            {"bbox": [100, 0, 200, 10], "text": "CA07"},
            {"bbox": [100, 10, 200, 20], "text": ""},
        ],
    }


def test_rowspan_is_geometric_and_an_empty_code_never_inherits():
    rows = table_records(merged_table())
    assert len(rows) == 2
    assert "身體功能" in rows[0]["text"] and "CA07" in rows[0]["text"]
    assert "身體功能" in rows[1]["text"] and "CA07" not in rows[1]["text"]
    assert rows[0]["cells"] == [0, 1] and rows[1]["cells"] == [0, 2]


@pytest.mark.parametrize("kind", ["overlap", "gap", "unordered", "nan", "boolean", "unused"])
def test_ambiguous_or_malformed_geometry_fails(kind):
    table = merged_table()
    if kind == "overlap":
        table["cells"].append(copy.deepcopy(table["cells"][0]))
    elif kind == "gap":
        table["cells"].pop()
    elif kind == "unordered":
        table["axes"] = [0, 200, 100]
    elif kind == "nan":
        table["cells"][0]["bbox"][0] = float("nan")
    elif kind == "boolean":
        table["cells"][0]["bbox"][0] = False
    else:
        table["cells"].append({"bbox": [300, 0, 400, 20], "text": "unrepresented"})
    with pytest.raises(KnowledgePipelineError):
        table_records(table)


def cycle_graph():
    return {
        "nodes": [
            {"id": "a", "bbox": [0, 0, 10, 10], "text": "詢問"},
            {"id": "b", "bbox": [10, 0, 20, 10], "text": "追蹤"},
        ],
        "edges": [["a", "b"], ["b", "a"]],
        "notes": [{"node_ids": ["a", "b"], "bbox": [0, 20, 20, 30], "text": "原始旁註"}],
    }


def test_loop_and_shared_note_keep_official_labels():
    text = graph_text(cycle_graph())
    assert "詢問 → 追蹤" in text and "追蹤 → 詢問" in text
    assert "詢問／追蹤：\n原始旁註" in text


@pytest.mark.parametrize(
    "kind", ["duplicate_node", "unresolved_edge", "duplicate_edge", "bad_note", "unlinked_node"]
)
def test_graph_referential_integrity(kind):
    graph = cycle_graph()
    if kind == "duplicate_node":
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
    elif kind == "unresolved_edge":
        graph["edges"][0][1] = "unknown"
    elif kind == "duplicate_edge":
        graph["edges"].append(graph["edges"][0])
    elif kind == "bad_note":
        graph["notes"][0]["node_ids"] = ["unknown"]
    else:
        graph["nodes"].append({"id": "c", "bbox": [20, 0, 30, 10], "text": "孤立"})
    with pytest.raises(KnowledgePipelineError):
        graph_text(graph)


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    directory = tmp_path_factory.mktemp("layout-baseline")
    compilation = compile_corpus(ROOT / "data/rag-rechunk/successor/v001/corpus.jsonl")
    assert compilation.report["status"] == "PASS"
    baseline = directory / "chunks.jsonl"
    baseline.write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in compilation.chunks),
        encoding="utf-8",
    )
    return baseline, compilation.chunks


def test_real_55_parents_preserve_other_chunks_and_all_policy(prepared, tmp_path):
    baseline, before = prepared
    original = {c["chunk_id"]: c for c in before}
    prior_bytes = baseline.read_bytes()
    candidate = repair_corpus(baseline, EXTRACTION)
    summary = candidate.report["summary"]
    assert summary == {
        "input_count": 658,
        "retained_count": 657,
        "replaced_count": 55,
        "replacement_count": 54,
        "unchanged_count": 603,
        "error_count": 0,
    }
    retained = [c for c in candidate.chunks if c["chunk_id"] in original]
    assert len(retained) == 603 and all(c == original[c["chunk_id"]] for c in retained)
    changed = [c for c in candidate.chunks if c["chunk_id"] not in original]
    for c in changed:
        parent = original[c["provenance"]["prior_chunk_ids"][0]]
        assert c["policy"] == parent["policy"]
        assert {k: v for k, v in c["source"].items() if k != "locator"} == {
            k: v for k, v in parent["source"].items() if k != "locator"
        }
        for field in ("license_status", "distribution_scope", "data_classification"):
            assert c["provenance"][field] == parent["provenance"][field]
        assert c["provenance"]["review_status"] == "needs_review"
        assert c["provenance"]["human_source_review"] == "not_completed"
        assert c["content"]["type"] == parent["content"]["type"]
        assert sha256(c["content"]["text"]) == c["content"]["text_sha256"]
        assert sha256(c["content"]["embedding_text"]) == c["content"]["embedding_text_sha256"]
    output = tmp_path / "candidate"
    write_dataset(candidate, output)
    first = {p.name: p.read_bytes() for p in output.iterdir()}
    write_dataset(repair_corpus(baseline, EXTRACTION), output)
    assert first == {p.name: p.read_bytes() for p in output.iterdir()}
    assert baseline.read_bytes() == prior_bytes
    assert candidate.report["production_approved"] is False
    assert candidate.report["activation_allowed"] is False


def test_family_split_row_and_multi_page_tables_remain_complete(prepared):
    result = repair_corpus(prepared[0], EXTRACTION)
    family = next(
        c
        for c in result.chunks
        if len(c["provenance"]["prior_chunk_ids"]) == 2
        and c["provenance"]["artifact_version"] == "v009"
    )
    assert "你/妳的氣色看起來不" in family["content"]["text"]
    assert "好，最近怎麼了？" in family["content"]["text"]
    assert "常常推託的照顧者" in family["content"]["text"]
    courses = next(
        c
        for c in result.chunks
        if c["provenance"]["prior_chunk_ids"]
        == ["mohw_a_unit_case_manager_manual_appendix_20230719_rag_v2_v005_0022"]
    )
    assert all(f"【PDF實體頁{page}】" in courses["content"]["text"] for page in range(141, 146))


def test_bounded_candidate_preserves_every_source_atom_and_note(prepared):
    candidate = repair_corpus(prepared[0], EXTRACTION, max_embedding_characters=1500)
    original = {c["chunk_id"]: c for c in prepared[1]}
    changed = [c for c in candidate.chunks if c["chunk_id"] not in original]
    assert candidate.report["summary"]["unchanged_count"] == 603
    assert len(changed) > 54
    assert all(len(c["content"]["embedding_text"]) <= 1500 for c in changed)
    document = json.loads(EXTRACTION.read_text(encoding="utf-8"))
    for group in document["groups"]:
        parents = [p["chunk_id"] for p in group["parents"]]
        fragments = [c for c in changed if c["provenance"]["prior_chunk_ids"] == parents]
        assert fragments
        for note in group["notes"]:
            assert all(_text(note["text"]) in c["content"]["text"] for c in fragments)
        for page in group["pages"]:
            atoms = [_text(b["text"]) for b in page.get("blocks", [])]
            atoms += [graph_text(g) for g in page.get("graphs", [])]
            atoms += [r["text"] for t in page.get("tables", []) for r in table_records(t)]
            for atom in atoms:
                assert any(
                    atom in c["content"]["text"]
                    and f"【PDF實體頁{page['number']}】" in c["content"]["text"]
                    for c in fragments
                )
        for c in fragments:
            assert c["policy"] == original[parents[0]]["policy"]
            assert c["provenance"]["human_source_review"] == "not_completed"


def test_page_boundary_rows_stay_together_and_never_fill_empty_cells():
    first, second = merged_table(), merged_table()
    second["cells"][0]["text"] = ""
    group = {"pages": [{"number": 1, "tables": [first]}, {"number": 2, "tables": [second]}]}
    units = _bounded_group_units(group, "來源", "共同註解", 200)
    ending, starting = table_records(first)[-1]["text"], table_records(second)[0]["text"]
    assert any(ending in u["text"] and starting in u["text"] for u in units)
    assert "問題面向：\n\n對應之給付碼：\nCA07" in starting


def test_bounded_candidate_rejects_an_oversized_atomic_region(prepared):
    with pytest.raises(KnowledgePipelineError, match="LAYOUT_ATOMIC_INPUT_TOO_LONG"):
        repair_corpus(prepared[0], EXTRACTION, max_embedding_characters=200)


def test_real_professional_cells_keep_code_and_professionals_together():
    source = json.loads(EXTRACTION.read_text(encoding="utf-8"))
    page = next(p for g in source["groups"] for p in g["pages"] if p["number"] == 156)
    rows = table_records(page["tables"][0])
    assert "CA07-IADLs" in rows[0]["text"] and "物理治療人員" in rows[0]["text"]
    assert "CB01-營養照護" in rows[3]["text"] and "語言治療師" in rows[3]["text"]
    assert "牙醫師" not in rows[0]["text"] and "牙醫師" in rows[8]["text"]
    final = next(p for g in source["groups"] for p in g["pages"] if p["number"] == 160)
    blank = table_records(final["tables"][0])[0]["text"]
    assert "對應之給付碼：\n\n建議可介入" in blank
    assert "核派E碼" in blank and "CA07" not in blank


@pytest.mark.parametrize(
    "kind",
    [
        "stale_hash",
        "source_version",
        "source_url",
        "duplicate_parent",
        "page_scope",
        "unknown_field",
        "string_boolean",
        "duplicate_page",
    ],
)
def test_source_and_contract_preconditions_fail_before_writes(prepared, tmp_path, kind):
    document = json.loads(EXTRACTION.read_text(encoding="utf-8"))
    if kind == "stale_hash":
        document["groups"][0]["parents"][0]["text_sha256"] = "0" * 64
    elif kind == "source_version":
        document["sources"][0]["version"] = "wrong"
    elif kind == "source_url":
        document["sources"][0]["url"] = "https://example.gov.tw/wrong"
    elif kind == "duplicate_parent":
        document["groups"].append(copy.deepcopy(document["groups"][0]))
    elif kind == "page_scope":
        document["groups"][0]["pages"][0]["number"] = 999
    elif kind == "unknown_field":
        document["groups"][0]["pages"][0]["verified"] = True
    elif kind == "duplicate_page":
        document["groups"][0]["pages"].append(copy.deepcopy(document["groups"][0]["pages"][0]))
    else:
        document["groups"][0]["pages"][0]["number"] = "111"
    extraction = tmp_path / "bad.jsonl"
    extraction.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(KnowledgePipelineError):
        repair_corpus(prepared[0], extraction)


def test_different_parent_audience_is_not_silently_combined(prepared, tmp_path):
    rows = [copy.deepcopy(c) for c in prepared[1]]
    altered = next(
        c
        for c in rows
        if c["chunk_id"] == "mohw_family_caregiver_support_manual_202507_rag_v2_v005_0049"
    )
    altered["policy"]["audiences"].append("elder")
    baseline = tmp_path / "changed.jsonl"
    baseline.write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in rows), encoding="utf-8"
    )
    with pytest.raises(KnowledgePipelineError, match="LAYOUT_PARENT_METADATA_MISMATCH"):
        repair_corpus(baseline, EXTRACTION)


def test_cli_dry_run_does_not_write_and_explicit_write_never_overwrites(prepared, tmp_path, capsys):
    output = tmp_path / "new-candidate"
    args = ["--baseline", str(prepared[0]), "--output", str(output)]
    assert repair_main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "DRY_RUN"
    assert report["summary"]["replacement_count"] > 54
    assert not output.exists()
    assert repair_main([*args, "--write"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "WRITE"
    file = output / "chunks.jsonl"
    assert all(
        len(json.loads(line)["content"]["embedding_text"]) <= 1500
        for line in file.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["provenance"]["artifact_version"] == "v009"
    )
    file.write_text("existing-different-content", encoding="utf-8")
    assert repair_main([*args, "--write"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED"
    assert file.read_text(encoding="utf-8") == "existing-different-content"


def test_cli_write_requires_a_named_destination(prepared, capsys):
    assert repair_main(["--baseline", str(prepared[0]), "--write"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "error": "WRITE_REQUIRES_OUTPUT",
    }
