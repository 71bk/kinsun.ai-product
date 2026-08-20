from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
V1_SCHEMA_PATH = REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.schema.json"
V2_SCHEMA_PATH = REPOSITORY_ROOT / "contracts" / "schemas" / "rag" / "rag-chunk-v2.1.schema.json"
V001_CHUNK_ROOT = REPOSITORY_ROOT / "data" / "rag-v2" / "candidates" / "v001" / "chunks"
V002_PREFLIGHT_INVENTORY = (
    REPOSITORY_ROOT / "data" / "rag-v2" / "preflight" / "v002" / "validation-input-inventory.json"
)


@pytest.fixture(scope="module")
def v1_validator() -> Draft202012Validator:
    schema = json.loads(V1_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.fixture(scope="module")
def v2_validator() -> Draft202012Validator:
    schema = json.loads(V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_v1_schema_bytes_remain_frozen() -> None:
    inventory = json.loads(V002_PREFLIGHT_INVENTORY.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in inventory["entries"]
        if item["path"] == "contracts/schemas/rag/rag-chunk-v2.schema.json"
    )
    schema_bytes = V1_SCHEMA_PATH.read_bytes()

    assert len(schema_bytes) == entry["size_bytes"]
    assert hashlib.sha256(schema_bytes).hexdigest() == entry["sha256"]


def test_immutable_v001_candidate_remains_valid(
    v1_validator: Draft202012Validator,
) -> None:
    failures: list[str] = []
    record_count = 0

    for path in sorted(V001_CHUNK_ROOT.glob("*.jsonl")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            record_count += 1
            for error in v1_validator.iter_errors(json.loads(line)):
                failures.append(f"{path.name}:{line_number}: {error.message}")

    assert record_count == 726
    assert failures == []


def test_v1_schema_rejects_v21_citation_fields(
    v1_validator: Draft202012Validator,
) -> None:
    record = _first_record("mohw_1966_apply_ltc.rag-chunk-v2.v001.jsonl")
    record["citation"]["direct_source_url"] = "https://example.invalid/direct"
    record["citation"]["source_page_url"] = "https://example.invalid/page"

    with pytest.raises(ValidationError):
        v1_validator.validate(record)


def test_v002_official_source_accepts_neutral_and_official_urls(
    v2_validator: Draft202012Validator,
) -> None:
    record = _as_v002(_first_record("mohw_1966_apply_ltc.rag-chunk-v2.v001.jsonl"))
    record["citation"]["official_source_page_url"] = "https://example.invalid/official-source-page"
    record["citation"]["source_page_url"] = "https://example.invalid/official-source-page"

    assert record["provenance"]["is_official_source"] is True
    assert record["citation"]["direct_official_source_url"] is not None
    assert record["citation"]["official_source_page_url"] is not None
    v2_validator.validate(record)


@pytest.mark.parametrize("missing_field", ["direct_source_url", "source_page_url"])
def test_v002_requires_both_neutral_source_url_fields(
    v2_validator: Draft202012Validator,
    missing_field: str,
) -> None:
    record = _as_v002(_first_record("mohw_1966_apply_ltc.rag-chunk-v2.v001.jsonl"))
    del record["citation"][missing_field]

    with pytest.raises(ValidationError):
        v2_validator.validate(record)


def test_v002_non_official_source_requires_null_official_urls(
    v2_validator: Draft202012Validator,
) -> None:
    record = _as_v002(
        _first_record("frontiers_do_words_matter_loneliness_nlp_2021.rag-chunk-v2.v001.jsonl")
    )

    assert record["provenance"]["is_official_source"] is False
    assert record["citation"]["direct_source_url"] is not None
    assert record["citation"]["source_page_url"] is not None
    assert record["citation"]["direct_official_source_url"] is None
    assert record["citation"]["official_source_page_url"] is None
    v2_validator.validate(record)

    for field in ("direct_official_source_url", "official_source_page_url"):
        invalid = copy.deepcopy(record)
        invalid["citation"][field] = "https://example.invalid/not-official"
        with pytest.raises(ValidationError):
            v2_validator.validate(invalid)


@pytest.mark.parametrize(
    ("artifact_version", "schema_version"),
    [("v001", "2.1.0"), ("v002", "2.0.0")],
)
def test_artifact_and_schema_versions_must_match(
    v2_validator: Draft202012Validator,
    artifact_version: str,
    schema_version: str,
) -> None:
    record = _as_v002(_first_record("mohw_1966_apply_ltc.rag-chunk-v2.v001.jsonl"))
    record["artifact_version"] = artifact_version
    record["schema_version"] = schema_version

    with pytest.raises(ValidationError):
        v2_validator.validate(record)


def _first_record(filename: str) -> dict[str, object]:
    first_line = (V001_CHUNK_ROOT / filename).read_text(encoding="utf-8").splitlines()[0]
    return json.loads(first_line)


def _as_v002(record: dict[str, object]) -> dict[str, object]:
    successor = copy.deepcopy(record)
    successor["artifact_version"] = "v002"
    successor["schema_version"] = "2.1.0"

    citation = successor["citation"]
    provenance = successor["provenance"]
    assert isinstance(citation, dict)
    assert isinstance(provenance, dict)
    citation["direct_source_url"] = citation["direct_official_source_url"]
    citation["source_page_url"] = citation["official_source_page_url"]
    if provenance["is_official_source"] is False:
        citation["direct_official_source_url"] = None
        citation["official_source_page_url"] = None
    return successor
