"""PDF preconditions and glyph loss guards without an optional PDF dependency."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from rag_ingestion.knowledge_pipeline import ROOT

sys.path.insert(0, str(ROOT))
from scripts.rag.extract_knowledge_layout import (  # noqa: E402
    ExtractionError,
    extract,
    main,
    validate_recipes,
)


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / "public.pdf"
    path.write_bytes(b"synthetic-public-pdf")
    page = SimpleNamespace(width=100, height=100, chars=[])
    closed = []
    pdf = SimpleNamespace(pages=[page], close=lambda: closed.append(True))
    opened = []
    module = ModuleType("pdfplumber")
    module.__version__ = "test"

    def open_pdf(path):
        opened.append(path)
        return pdf

    module.open = open_pdf
    utils = ModuleType("pdfplumber.utils")
    utils.extract_text = lambda chars, **kwargs: "".join(c["text"] for c in chars)
    monkeypatch.setitem(sys.modules, "pdfplumber", module)
    monkeypatch.setitem(sys.modules, "pdfplumber.utils", utils)
    recipes = {
        "schema_version": "knowledge-layout-recipes-v1",
        "sources": [
            {
                "id": "public",
                "page_count": 1,
                "pdf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
        "groups": [
            {
                "source_id": "public",
                "parents": [{"chunk_id": "synthetic", "text_sha256": "0" * 64}],
                "pages": [{"number": 1, "blocks": [[0, 0, 100, 100]]}],
            }
        ],
    }
    return recipes, {"public": path}, page, opened, closed


@pytest.mark.parametrize("kind", ["zero", "negative", "boolean", "duplicate", "unknown_source"])
def test_invalid_page_recipe_cannot_select_another_pdf_page(source, kind):
    recipes, paths, _, opened, _ = source
    spec = recipes["groups"][0]["pages"][0]
    if kind == "duplicate":
        recipes["groups"][0]["pages"].append(copy.deepcopy(spec))
    elif kind == "unknown_source":
        recipes["groups"][0]["source_id"] = "unknown"
    else:
        spec["number"] = {"zero": 0, "negative": -1, "boolean": True}[kind]
    with pytest.raises(ExtractionError):
        extract(recipes, paths)
    assert opened == []


def test_hash_mismatch_fails_before_pdf_load(source):
    recipes, paths, _, opened, _ = source
    recipes["sources"][0]["pdf_sha256"] = "0" * 64
    with pytest.raises(ExtractionError, match="PDF_HASH_MISMATCH"):
        extract(recipes, paths)
    assert opened == []


def test_page_count_mismatch_closes_the_opened_pdf(source):
    recipes, paths, _, _, closed = source
    recipes["sources"][0]["page_count"] = 2
    with pytest.raises(ExtractionError, match="PDF_PAGE_COUNT_MISMATCH"):
        extract(recipes, paths)
    assert closed == [True]


def test_duplicate_or_unbound_source_paths_fail(source):
    recipes, paths, _, _, _ = source
    recipes["sources"].append(copy.deepcopy(recipes["sources"][0]))
    with pytest.raises(ExtractionError, match="INVALID_RECIPE_SOURCES"):
        validate_recipes(recipes, paths)


@pytest.mark.parametrize("kind", ["lost", "duplicate"])
def test_every_table_glyph_belongs_to_exactly_one_physical_cell(source, kind):
    recipes, paths, page, _, closed = source
    page.chars = [{"text": "A", "x0": 10, "x1": 12, "top": 10, "bottom": 12}]
    cells = [] if kind == "lost" else [(0, 0, 100, 100)] * 2
    page.find_tables = lambda: [SimpleNamespace(bbox=(0, 0, 100, 100), cells=cells)]
    recipes["groups"][0]["pages"][0]["table"] = {
        "count": 1,
        "index": 0,
        "columns": 2,
        "header_depth": 0,
    }
    with pytest.raises(ExtractionError, match="TABLE_GLYPH_COVERAGE_MISMATCH"):
        extract(recipes, paths)
    assert closed == [True]


def test_out_of_page_region_is_not_silently_clipped(source):
    recipes, paths, _, _, closed = source
    recipes["groups"][0]["pages"][0]["blocks"] = [[0, 0, 101, 100]]
    with pytest.raises(ExtractionError, match="REGION_BOX_OUT_OF_PAGE"):
        extract(recipes, paths)
    assert closed == [True]


def test_cli_rejects_duplicate_json_keys_and_does_not_echo_input(tmp_path, capsys):
    recipe = tmp_path / "bad.json"
    recipe.write_text('{"sensitive-input":1,"sensitive-input":2}', encoding="utf-8")
    output = tmp_path / "output.jsonl"
    assert main(["--recipes", str(recipe), "--source", "public=x", "--output", str(output)]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "error": "DUPLICATE_RECIPE_KEY",
    }
    assert not output.exists()
