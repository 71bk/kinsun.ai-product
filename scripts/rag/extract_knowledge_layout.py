"""Extract selected public PDF cells/regions with a local, hash-bound recipe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


class ExtractionError(ValueError):
    """Fixed, content-free error code."""


def validate_recipes(recipes: dict, paths: dict[str, Path]) -> None:
    if recipes.get("schema_version") != "knowledge-layout-recipes-v1":
        raise ExtractionError("INVALID_RECIPE_VERSION")
    sources = recipes["sources"]
    ids = [s["id"] for s in sources]
    if not sources or len(set(ids)) != len(ids) or set(ids) != set(paths):
        raise ExtractionError("INVALID_RECIPE_SOURCES")
    counts = {}
    for source in sources:
        if (
            type(source["page_count"]) is not int
            or source["page_count"] < 1
            or re.fullmatch(r"[a-f0-9]{64}", source["pdf_sha256"]) is None
        ):
            raise ExtractionError("INVALID_RECIPE_SOURCE")
        counts[source["id"]] = source["page_count"]
    if not recipes["groups"]:
        raise ExtractionError("EMPTY_RECIPE_GROUPS")
    for group in recipes["groups"]:
        if group["source_id"] not in counts or not group["parents"] or not group["pages"]:
            raise ExtractionError("INVALID_RECIPE_GROUP")
        numbers = [p["number"] for p in group["pages"]]
        if any(
            type(n) is not int or not 1 <= n <= counts[group["source_id"]] for n in numbers
        ) or numbers != sorted(set(numbers)):
            raise ExtractionError("INVALID_RECIPE_PAGES")
        for page in group["pages"]:
            table = page.get("table")
            if table is not None and (
                type(table["count"]) is not int
                or table["count"] < 1
                or type(table["index"]) is not int
                or not 0 <= table["index"] < table["count"]
                or type(table["columns"]) is not int
                or table["columns"] < 2
                or type(table["header_depth"]) not in (int, float)
                or not math.isfinite(table["header_depth"])
                or table["header_depth"] < 0
            ):
                raise ExtractionError("INVALID_RECIPE_TABLE")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExtractionError("DUPLICATE_RECIPE_KEY")
        result[key] = value
    return result


def compact(values, tolerance=3):
    groups = []
    for value in sorted(set(values)):
        if groups and value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(g) / len(g) for g in groups]


def extract(recipes: dict, paths: dict[str, Path]) -> dict:
    validate_recipes(recipes, paths)
    import pdfplumber
    from pdfplumber.utils import extract_text

    pdfs = {}
    try:
        for source in recipes["sources"]:
            path = paths[source["id"]]
            if hashlib.sha256(path.read_bytes()).hexdigest() != source["pdf_sha256"]:
                raise ExtractionError("PDF_HASH_MISMATCH")
            pdfs[source["id"]] = pdfplumber.open(path)
            if len(pdfs[source["id"]].pages) != source["page_count"]:
                raise ExtractionError("PDF_PAGE_COUNT_MISMATCH")

        def text(page, bbox):
            if len(bbox) != 4 or not all(
                type(v) in (int, float) and math.isfinite(v) for v in bbox
            ):
                raise ExtractionError("INVALID_REGION_BOX")
            x0, top, x1, bottom = bbox
            if not 0 <= x0 < x1 <= page.width or not 0 <= top < bottom <= page.height:
                raise ExtractionError("REGION_BOX_OUT_OF_PAGE")
            chars = [
                c
                for c in page.chars
                if x0 <= (c["x0"] + c["x1"]) / 2 < x1
                and top <= (c["top"] + c["bottom"]) / 2 < bottom
            ]
            return extract_text(chars, x_tolerance=2) if chars else ""

        result = {
            "schema_version": "knowledge-layout-extraction-v1",
            "parser": f"pdfplumber-{pdfplumber.__version__}",
            "sources": recipes["sources"],
            "groups": [],
        }
        for group in recipes["groups"]:
            target = {
                "parents": group["parents"],
                "pages": [],
                "notes": [],
                "omissions": group.get("omissions", []),
            }
            pdf = pdfs[group["source_id"]]
            headers_by_page = {}
            for spec in group["pages"]:
                page = pdf.pages[spec["number"] - 1]
                output = {
                    "number": spec["number"],
                    "context": "",
                    "blocks": [],
                    "tables": [],
                    "graphs": [],
                }
                contexts = []
                for bbox in spec.get("context_regions", []):
                    contexts.append(text(page, bbox))
                for bbox in spec.get("blocks", []):
                    output["blocks"].append({"bbox": bbox, "text": text(page, bbox)})
                for diagram in spec.get("graphs", []):
                    graph = {"nodes": [], "edges": diagram["edges"], "notes": []}
                    for node in diagram["nodes"]:
                        label = text(page, node["bbox"])
                        if re.sub(r"\s+", "", label) != re.sub(r"\s+", "", node["expected"]):
                            raise ExtractionError("GRAPH_NODE_MISMATCH")
                        graph["nodes"].append(
                            {"id": node["id"], "bbox": node["bbox"], "text": label}
                        )
                    for note in diagram.get("notes", []):
                        graph["notes"].append(
                            {
                                "node_ids": note["node_ids"],
                                "bbox": note["bbox"],
                                "text": text(page, note["bbox"]),
                            }
                        )
                    output["graphs"].append(graph)
                if spec.get("graphs"):
                    boxes = spec.get("blocks", []) + spec.get("context_regions", [])
                    for diagram in spec["graphs"]:
                        boxes += [n["bbox"] for n in diagram["nodes"]] + [
                            n["bbox"] for n in diagram.get("notes", [])
                        ]
                    scope = [0, min(b[1] for b in boxes), page.width, max(b[3] for b in boxes)]
                    for char in page.chars:
                        if not char["text"].strip():
                            continue
                        x, y = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
                        if scope[0] <= x < scope[2] and scope[1] <= y < scope[3]:
                            if sum(b[0] <= x < b[2] and b[1] <= y < b[3] for b in boxes) != 1:
                                raise ExtractionError("GRAPH_REGION_COVERAGE_MISMATCH")
                table_spec = spec.get("table")
                if table_spec is not None:
                    found = page.find_tables()
                    if len(found) != table_spec["count"]:
                        raise ExtractionError("TABLE_COUNT_MISMATCH")
                    table = found[table_spec["index"]]
                    all_cells = list(table.cells)
                    for supplied in table_spec.get("open_boundary_cells", []):
                        actual = text(page, supplied["bbox"])
                        if re.sub(r"\s+", "", actual) != re.sub(r"\s+", "", supplied["expected"]):
                            raise ExtractionError("OPEN_BOUNDARY_CELL_TEXT_MISMATCH")
                        all_cells.append(tuple(supplied["bbox"]))
                    for char in page.chars:
                        if not char["text"].strip():
                            continue
                        x, y = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
                        if (
                            table.bbox[0] <= x < table.bbox[2]
                            and table.bbox[1] <= y < table.bbox[3]
                        ):
                            if sum(b[0] <= x < b[2] and b[1] <= y < b[3] for b in all_cells) != 1:
                                raise ExtractionError("TABLE_GLYPH_COVERAGE_MISMATCH")
                    boundaries = compact([v for b in all_cells for v in (b[1], b[3])])
                    body_top = min(
                        boundaries,
                        key=lambda y: abs(y - table.bbox[1] - table_spec["header_depth"]),
                    )
                    body = [b for b in all_cells if b[1] >= body_top - 1]
                    axes = compact([v for b in body for v in (b[0], b[2])], tolerance=7)
                    if len(axes) - 1 != table_spec["columns"]:
                        raise ExtractionError("TABLE_COLUMNS_MISMATCH")
                    initial_top = body_top
                    for start, end in zip(boundaries, boundaries[1:]):
                        if start < initial_top - 1 or end - start < 0.1:
                            continue
                        y = (start + end) / 2
                        if all(
                            sum(b[0] <= (x0 + x1) / 2 < b[2] and b[1] <= y < b[3] for b in body)
                            == 1
                            for x0, x1 in zip(axes, axes[1:])
                        ):
                            body_top = start
                            break
                    if (
                        body_top > initial_top
                        and text(
                            page, [table.bbox[0], initial_top, table.bbox[2], body_top]
                        ).strip()
                    ):
                        raise ExtractionError("NONEMPTY_HEADER_GAP")
                    body = [b for b in all_cells if b[1] >= body_top - 1]
                    labels = []
                    for x0, x1 in zip(axes, axes[1:]):
                        center = (x0 + x1) / 2
                        headers = [
                            b for b in all_cells if b[3] <= body_top + 1 and b[0] <= center < b[2]
                        ]
                        labels.append(
                            "".join(
                                re.sub(r"\s+", "", text(page, b))
                                for b in sorted(headers, key=lambda b: b[1])
                            )
                        )
                    if "inherited_headers" in table_spec:
                        if table_spec["header_depth"] != 0:
                            raise ExtractionError("INVALID_INHERITED_HEADER")
                        if (
                            headers_by_page.get(table_spec["inherited_headers_from"])
                            != table_spec["inherited_headers"]
                        ):
                            raise ExtractionError("INHERITED_HEADER_SOURCE_MISMATCH")
                        labels = table_spec["inherited_headers"]
                    if (
                        "expected_headers" in table_spec
                        and labels != table_spec["expected_headers"]
                    ):
                        raise ExtractionError("TABLE_HEADERS_MISMATCH")
                    output["tables"].append(
                        {
                            "axes": axes,
                            "headers": labels,
                            "cells": [{"bbox": list(b), "text": text(page, b)} for b in body],
                        }
                    )
                    headers_by_page[spec["number"]] = labels
                    if table_spec.get("outside_context", False):
                        contexts.append(text(page, [0, 0, page.width, table.bbox[1]]))
                        footer = text(page, [0, table.bbox[3], page.width, 789])
                        if footer.strip():
                            target["notes"].append(
                                {
                                    "page": spec["number"],
                                    "bbox": [0, table.bbox[3], page.width, 789],
                                    "text": f"【PDF實體頁{spec['number']}】\n{footer}",
                                }
                            )
                output["context"] = "\n\n".join(c.strip() for c in contexts if c.strip())
                target["pages"].append(output)
            result["groups"].append(target)
        return result
    finally:
        for pdf in pdfs.values():
            pdf.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipes", type=Path, required=True)
    parser.add_argument("--source", action="append", required=True, metavar="SOURCE_ID=LOCAL_PDF")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        recipes = json.loads(
            args.recipes.read_text(encoding="utf-8"), object_pairs_hook=unique_object
        )
        paths = {}
        for supplied in args.source:
            key, path = supplied.split("=", 1)
            if key in paths:
                raise ExtractionError("DUPLICATE_SOURCE_PATH")
            paths[key] = Path(path)
        result = extract(recipes, paths)
        payload = (
            json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        ).encode()
        if args.output.exists():
            if (
                not args.output.is_file()
                or args.output.is_symlink()
                or args.output.read_bytes() != payload
            ):
                raise ExtractionError("EXTRACTION_OUTPUT_DIFFERS")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as stream:
                stream.write(payload)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "group_count": len(result["groups"]),
                    "page_count": sum(len(g["pages"]) for g in result["groups"]),
                }
            )
        )
        return 0
    except ExtractionError as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
    except ImportError:
        print(json.dumps({"status": "FAILED", "error": "PDF_DEPENDENCY_REQUIRED"}))
    except (OSError, ValueError, KeyError, TypeError, IndexError, UnicodeError):
        print(json.dumps({"status": "FAILED", "error": "PDF_EXTRACTION_FAILED"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
