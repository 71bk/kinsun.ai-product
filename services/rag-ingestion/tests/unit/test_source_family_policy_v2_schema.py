from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _schema(name: str) -> dict[str, object]:
    path = REPOSITORY_ROOT / "contracts/schemas/rag" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_owner_source_family_policy_acceptance_schema_is_valid() -> None:
    Draft202012Validator.check_schema(
        _schema("rag-owner-source-family-policy-acceptance-v1.schema.json")
    )


def test_source_family_policy_v2_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_schema("rag-source-family-policy-map-v2.schema.json"))


def test_policy_v2_schema_fixes_production_and_external_gates() -> None:
    schema = _schema("rag-source-family-policy-map-v2.schema.json")
    gates = schema["$defs"]["Gates"]["properties"]

    assert gates["production_approved"]["const"] is False
    assert gates["production_status"]["const"] == "BLOCKED"
    assert gates["external_sync"]["const"] == "NOT_AUTHORIZED"
    assert gates["runtime_integration"]["const"] == "NOT_STARTED"


def test_acceptance_schema_records_five_low_risk_overlays_without_chunk_mutation() -> None:
    schema = _schema("rag-owner-source-family-policy-acceptance-v1.schema.json")
    risk = schema["properties"]["risk_policy_decision"]["properties"]

    assert risk["canonical_risk_level"]["const"] == "low"
    assert risk["affected_chunk_count"]["const"] == 5
    assert risk["chunk_bytes_mutated"]["const"] is False
