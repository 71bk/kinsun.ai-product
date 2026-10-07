"""Source-bound PDF layout repair; no runtime gate or external writes."""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from rag_ingestion.knowledge_pipeline import (
    ROOT,
    SCHEMA_PATH,
    Compilation,
    KnowledgePipelineError,
    read_jsonl,
    sha256,
)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise KnowledgePipelineError(code)


def _box(value) -> tuple[float, ...]:
    _require(
        isinstance(value, list)
        and len(value) == 4
        and all(type(v) in (int, float) and math.isfinite(v) for v in value),
        "INVALID_LAYOUT_BOX",
    )
    _require(value[0] < value[2] and value[1] < value[3], "INVALID_LAYOUT_BOX")
    return tuple(value)


def _text(value) -> str:
    _require(isinstance(value, str) and "\ufffd" not in value, "INVALID_LAYOUT_TEXT")
    # Only inside a coordinate-bound cell/region. Never flatten a whole page.
    return "\n".join(
        re.sub(r"[ \t\u3000]+", " ", line).strip() for line in value.splitlines()
    ).strip()


def table_records(table: dict) -> list[dict]:
    """Repeat a merged cell only where its rectangle actually spans the row.

    Empty cells stay empty. Headers inherited from a preceding page must be
    supplied explicitly in the extraction; no data cell is forward-filled.
    """
    axes, labels = table["axes"], table["headers"]
    _require(
        isinstance(axes, list)
        and len(axes) >= 3
        and all(type(v) in (int, float) and math.isfinite(v) for v in axes)
        and all(a < b for a, b in zip(axes, axes[1:]))
        and isinstance(labels, list)
        and len(labels) == len(axes) - 1
        and all(isinstance(v, str) for v in labels),
        "INVALID_LAYOUT_COLUMNS",
    )
    cells = [(index, _box(c["bbox"]), _text(c["text"])) for index, c in enumerate(table["cells"])]
    _require(bool(cells), "EMPTY_LAYOUT_TABLE")
    boundaries = sorted({coordinate for _, b, _ in cells for coordinate in (b[1], b[3])})
    records = []
    for top, bottom in zip(boundaries, boundaries[1:]):
        if bottom - top < 0.1:
            continue
        y = (top + bottom) / 2
        selected = []
        for x0, x1 in zip(axes, axes[1:]):
            x = (x0 + x1) / 2
            matches = [(i, b, t) for i, b, t in cells if b[0] <= x < b[2] and b[1] <= y < b[3]]
            _require(len(matches) == 1, "AMBIGUOUS_LAYOUT_CELL_COVERAGE")
            selected.append(matches[0])
        if not any(t for _, _, t in selected):
            continue
        lines, used = [], set()
        for index, _, text in selected:
            if index in used:
                continue
            used.add(index)
            columns = [j for j, (other, _, _) in enumerate(selected) if other == index]
            header = "／".join(dict.fromkeys(labels[j] for j in columns if labels[j]))
            lines.append(f"{header}：\n{text}" if header else text)
        records.append({"text": "\n".join(lines), "cells": sorted(used), "row": [top, bottom]})
    _require(bool(records), "EMPTY_LAYOUT_TABLE")
    used_cells = {index for record in records for index in record["cells"]}
    _require(
        all(index in used_cells for index, _, text in cells if text),
        "UNUSED_LAYOUT_CELL",
    )
    return records


def graph_text(graph: dict) -> str:
    """Render only supplied official labels and recorded edge topology."""
    nodes, edges = graph["nodes"], graph["edges"]
    _require(isinstance(nodes, list) and nodes and isinstance(edges, list), "INVALID_LAYOUT_GRAPH")
    by_id = {}
    for node in nodes:
        _require(isinstance(node.get("id"), str) and node["id"] not in by_id, "INVALID_GRAPH_NODE")
        _box(node["bbox"])
        label = _text(node["text"])
        _require(bool(label), "EMPTY_GRAPH_NODE")
        by_id[node["id"]] = label
    seen, lines = set(), []
    for edge in edges:
        _require(
            isinstance(edge, list) and len(edge) == 2 and all(e in by_id for e in edge),
            "INVALID_GRAPH_EDGE",
        )
        pair = tuple(edge)
        _require(pair not in seen, "DUPLICATE_GRAPH_EDGE")
        seen.add(pair)
        lines.append(f"{by_id[edge[0]]} → {by_id[edge[1]]}")
    linked = {n for e in edges for n in e}
    _require(linked == set(by_id), "UNLINKED_GRAPH_NODE")
    for note in graph.get("notes", []):
        attached = note["node_ids"]
        _require(
            isinstance(attached, list)
            and attached
            and len(set(attached)) == len(attached)
            and all(n in by_id for n in attached),
            "INVALID_GRAPH_NOTE",
        )
        _box(note["bbox"])
        text = _text(note["text"])
        _require(bool(text), "EMPTY_GRAPH_NOTE")
        labels = "／".join(by_id[n] for n in attached)
        lines.append(f"{labels}：\n{text}")
    return "\n\n".join(lines)


def _page_units(page: dict) -> list[dict]:
    number = page["number"]
    _require(type(number) is int and number > 0, "INVALID_LAYOUT_PAGE")
    context = _text(page.get("context", ""))
    marker = f"【PDF實體頁{number}】"
    blocks = []
    for block in page.get("blocks", []):
        _box(block["bbox"])
        text = _text(block["text"])
        if text:
            blocks.append(text)
    for graph in page.get("graphs", []):
        blocks.append(graph_text(graph))
    for table in page.get("tables", []):
        blocks.extend(record["text"] for record in table_records(table))
    _require(bool(blocks), "EMPTY_LAYOUT_PAGE")
    return [{"text": "\n\n".join(t for t in (marker, context, *blocks) if t), "page": number}]


def _bounded_group_units(group: dict, prefix: str, notes: str, limit: int) -> list[dict]:
    """Pack complete rows/graphs/regions, keeping page-boundary rows together.

    This is a character budget, not a tokenizer. The provider must separately
    reject over-limit inputs with truncation disabled before any import.
    """
    atoms = []
    contexts = {}
    for page in group["pages"]:
        number = page["number"]
        contexts[number] = _text(page.get("context", ""))
        blocks = [("block", _text(b["text"])) for b in page.get("blocks", [])]
        blocks += [("graph", graph_text(g)) for g in page.get("graphs", [])]
        blocks += [
            ("row", r["text"]) for table in page.get("tables", []) for r in table_records(table)
        ]
        atoms.extend({"page": number, "kind": kind, "text": text} for kind, text in blocks if text)

    def render(items):
        blocks, pages = [], []
        for atom in items:
            page = atom["page"]
            if page not in pages:
                pages.append(page)
                blocks.extend(t for t in (f"【PDF實體頁{page}】", contexts[page]) if t)
            blocks.append(atom["text"])
        return {"text": "\n\n".join(blocks), "page": "、".join(map(str, pages))}

    def fits(items):
        text = "\n\n".join(t for t in (render(items)["text"], notes) if t)
        return len("｜".join(t for t in (prefix, text) if t)) <= limit

    # Preserve both sides of a potentially continued row, without copying a
    # value into an empty cell or claiming that the rows are the same record.
    bundles = []
    for atom in atoms:
        if (
            bundles
            and bundles[-1][-1]["kind"] == atom["kind"] == "row"
            and bundles[-1][-1]["page"] != atom["page"]
        ):
            bundles[-1].append(atom)
        else:
            bundles.append([atom])
    packed, pending = [], []
    for bundle in bundles:
        _require(fits(bundle), "LAYOUT_ATOMIC_INPUT_TOO_LONG")
        if pending and not fits(pending + bundle):
            packed.append(render(pending))
            pending = []
        pending.extend(bundle)
    if pending:
        packed.append(render(pending))
    return packed


def repair_corpus(
    baseline: Path,
    extraction: Path,
    *,
    dataset_version: str = "v009",
    max_embedding_characters: int | None = None,
) -> Compilation:
    _require(re.fullmatch(r"v[0-9]{3,}", dataset_version) is not None, "INVALID_DATASET_VERSION")
    _require(
        max_embedding_characters is None
        or (type(max_embedding_characters) is int and 200 <= max_embedding_characters <= 12000),
        "INVALID_EMBEDDING_CHARACTER_BUDGET",
    )
    rows = read_jsonl(baseline)
    validators = Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )
    by_id = {c["chunk_id"]: c for c in rows}
    _require(len(by_id) == len(rows), "DUPLICATE_CHUNK_ID")
    for c in rows:
        _require(validators.is_valid(c), "INVALID_BASELINE_CONTENT")
        _require(
            all(
                sha256(c["content"][k]) == c["content"][f"{k}_sha256"]
                for k in ("text", "embedding_text")
            ),
            "INVALID_BASELINE_CONTENT",
        )
    documents = read_jsonl(extraction)
    _require(len(documents) == 1, "INVALID_LAYOUT_EXTRACTION")
    document = documents[0]
    extraction_schema = ROOT / "contracts/schemas/rag/knowledge-layout-extraction-v1.schema.json"
    extraction_validator = Draft202012Validator(
        json.loads(extraction_schema.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )
    _require(extraction_validator.is_valid(document), "INVALID_LAYOUT_EXTRACTION")
    sources = {s["id"]: s for s in document["sources"]}
    _require(len(sources) == len(document["sources"]), "DUPLICATE_LAYOUT_SOURCE")
    for source in sources.values():
        _require(
            re.fullmatch(r"[a-f0-9]{64}", source["pdf_sha256"]) is not None
            and type(source["page_count"]) is int
            and source["page_count"] > 0,
            "INVALID_LAYOUT_SOURCE",
        )
    replaced, replacements, differences = set(), [], []
    for group in document["groups"]:
        parents = []
        for expected in group["parents"]:
            cid = expected["chunk_id"]
            _require(cid in by_id and cid not in replaced, "INVALID_LAYOUT_PARENT")
            original = by_id[cid]
            _require(
                original["content"]["text_sha256"] == expected["text_sha256"],
                "LAYOUT_PARENT_HASH_MISMATCH",
            )
            replaced.add(cid)
            parents.append(original)
        _require(bool(parents), "EMPTY_LAYOUT_PARENTS")
        base = parents[0]
        _require(
            all(
                p["policy"] == base["policy"]
                and p["source"] == base["source"]
                and {k: v for k, v in p["provenance"].items() if k != "prior_chunk_ids"}
                == {k: v for k, v in base["provenance"].items() if k != "prior_chunk_ids"}
                for p in parents
            ),
            "LAYOUT_PARENT_METADATA_MISMATCH",
        )
        source = sources.get(base["source"]["id"])
        _require(
            source is not None
            and source["version"] == base["source"]["version"]
            and source["url"] == base["source"]["url"],
            "LAYOUT_SOURCE_VERSION_MISMATCH",
        )
        group_units = []
        page_numbers = [p["number"] for p in group["pages"]]
        _require(page_numbers == sorted(set(page_numbers)), "INVALID_LAYOUT_PAGE_ORDER")
        for page in group["pages"]:
            _require(
                base["source"]["page_start"] <= page["number"] <= base["source"]["page_end"]
                and page["number"] <= source["page_count"],
                "LAYOUT_PAGE_OUT_OF_SCOPE",
            )
            group_units.extend(_page_units(page))
        _require(bool(group_units), "EMPTY_LAYOUT_GROUP")
        # The original semantic unit can cross a page boundary (including the
        # middle of a table row). Keep all its pages together, with explicit
        # page markers and empty cells, rather than guessing continuation data.
        page_numbers = sorted({u["page"] for u in group_units})
        group_units = [
            {
                "text": "\n\n".join(u["text"] for u in group_units),
                "page": "、".join(map(str, page_numbers)),
            }
        ]
        # Canonical notes remain available to every replacement of the original unit.
        for note in group["notes"] + group["omissions"]:
            _box(note["bbox"])
            _require(
                base["source"]["page_start"] <= note["page"] <= base["source"]["page_end"],
                "LAYOUT_PAGE_OUT_OF_SCOPE",
            )
        notes = "\n\n".join(_text(n["text"]) for n in group.get("notes", []))
        if max_embedding_characters is not None:
            prefix = "｜".join(t for t in (base["source"]["title"], base["source"]["section"]) if t)
            group_units = _bounded_group_units(group, prefix, notes, max_embedding_characters)
        new_ids = []
        for unit in group_units:
            text = "\n\n".join(t for t in (unit["text"], notes) if t)
            _require(0 < len(text) <= 12000, "LAYOUT_SEMANTIC_UNIT_TOO_LONG")
            new = copy.deepcopy(base)
            new["chunk_id"] = (
                f"{base['source']['id']}_knowledge_{dataset_version}_{sha256(text)[:20]}"
            )
            new["content"].update(text=text, text_sha256=sha256(text))
            embedding = "｜".join(
                t for t in (base["source"]["title"], base["source"]["section"], text) if t
            )
            new["content"].update(embedding_text=embedding, embedding_text_sha256=sha256(embedding))
            new["provenance"].update(
                artifact_version=dataset_version,
                prior_chunk_ids=[p["chunk_id"] for p in parents],
                review_status="needs_review",
                human_source_review="not_completed",
            )
            new["source"]["locator"] = (
                f"{base['source']['locator']}；版面重建單位／實體頁{unit['page']}"
            )
            _require(validators.is_valid(new), "INVALID_REPAIRED_CHUNK")
            replacements.append(new)
            new_ids.append(new["chunk_id"])
        differences.append(
            {
                "prior_chunk_ids": [p["chunk_id"] for p in parents],
                "new_chunk_ids": new_ids,
                "source_id": source["id"],
                "pdf_sha256": source["pdf_sha256"],
                "omissions": group.get("omissions", []),
            }
        )
    chunks = [c for c in rows if c["chunk_id"] not in replaced] + replacements
    _require(len({c["chunk_id"] for c in chunks}) == len(chunks), "DUPLICATE_REPAIRED_CHUNK_ID")
    report = {
        "schema_version": "knowledge-dataset-v1",
        "dataset_version": dataset_version,
        "status": "PASS",
        "production_approved": False,
        "activation_allowed": False,
        "source_check": "LOCAL_PDF_COORDINATE_EXTRACTION",
        "freshness_verified_online": False,
        "manual_review_required_for_build": False,
        "summary": {
            "input_count": len(rows),
            "retained_count": len(chunks),
            "replaced_count": len(replaced),
            "replacement_count": len(replacements),
            "unchanged_count": len(rows) - len(replaced),
            "error_count": 0,
        },
        "retained_by_source": dict(sorted(Counter(c["source"]["id"] for c in chunks).items())),
        "embedding_comparison": {
            "unchanged_content_count": len(rows) - len(replaced),
            "changed_content_count": len(replacements),
            "available_vectors_verified": False,
        },
        "layout_differences": differences,
    }
    if max_embedding_characters is not None:
        report["embedding_input_policy"] = {
            "max_characters": max_embedding_characters,
            "atomic_units": "COMPLETE_ROWS_GRAPHS_REGIONS",
            "provider_token_validation_required": True,
        }
    return Compilation(tuple(sorted(chunks, key=lambda c: c["chunk_id"])), report)
