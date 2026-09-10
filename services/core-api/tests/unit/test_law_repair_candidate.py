from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.rag_projection_importer import load_projection_batch

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "law_repair_builder", ROOT / "scripts/rag/build_law_repair_candidate.py"
)
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture(scope="module")
def candidate_files():
    return builder.build_files(ROOT)


def test_candidate_uses_existing_importer_and_new_strict_schema(tmp_path, candidate_files):
    files, _ = candidate_files
    candidate = tmp_path / "v004"
    for relative, raw in files.items():
        target = candidate / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    batch = load_projection_batch(
        candidate,
        candidate / builder.REPAIR_SCHEMA,
        expected_source_count=17,
        expected_chunk_count=726,
    )
    assert batch.artifact_version == "v004"
    assert batch.chunk_count == 726
    assert batch.production_approved is False
    assert batch.review_status == "needs_review"
    assert all("_rag_v2_v004_" in row.chunk_id for row in batch.chunks)
    law = [row for row in batch.chunks if row.source_id == builder.preview_module(ROOT).SOURCE]
    assert sum(row.retrieval_eligible for row in law) == 71
    stopped = next(row for row in law if row.chunk_id.endswith("_0048"))
    assert stopped.stop_normal_rag is True
    assert stopped.retrieval_eligible is False
    assert stopped.requires_professional_assessment is None


def test_only_scoped_governance_and_version_identity_change(candidate_files):
    files, preview = candidate_files
    helper = builder.preview_module(ROOT)
    originals = helper.inventory(ROOT / helper.BASE, helper.BASE_SHA)
    old = {}
    for path, raw in originals.items():
        if path.startswith("chunks/") and path.endswith(".jsonl"):
            old.update(
                {
                    row["identity"]["chunk_id"]: row
                    for row in (json.loads(line) for line in raw.splitlines())
                }
            )
    scoped = {row["prior_chunk_id"] for row in preview["changes"]}
    changed = 0
    for path, raw in files.items():
        if not path.startswith("chunks/"):
            continue
        for line in raw.splitlines():
            new = json.loads(line)
            prior = old[new["identity"]["prior_chunk_id"]]
            for key in ("content", "citation", "governance", "provenance"):
                assert new[key] == prior[key]
            if prior["identity"]["chunk_id"] in scoped:
                changed += 1
                assert {
                    key
                    for key in new["retrieval_policy"]
                    if new["retrieval_policy"][key] != prior["retrieval_policy"][key]
                } == {
                    "requires_professional_assessment",
                    "retrieval_eligible",
                    "retrieval_block_reasons",
                }
            else:
                assert new["retrieval_policy"] == prior["retrieval_policy"]
    assert changed == 71


def test_repair_schema_rejects_old_version_and_extra_fields(candidate_files):
    files, _ = candidate_files
    schema = json.loads(files[builder.REPAIR_SCHEMA])
    validator = Draft202012Validator(schema)
    record = json.loads(
        next(raw for name, raw in files.items() if name.startswith("chunks/")).splitlines()[0]
    )
    assert not list(validator.iter_errors(record))
    record["artifact_version"] = "v002"
    assert list(validator.iter_errors(record))
    record["artifact_version"] = "v004"
    record["unexpected"] = True
    assert list(validator.iter_errors(record))


def test_deterministic_complete_crosswalk_and_immutable_inputs(candidate_files):
    files, preview = candidate_files
    helper = builder.preview_module(ROOT)
    assert files == builder.build_files(ROOT)[0]
    crosswalk = [
        json.loads(line) for line in files["crosswalk/chunk-id-crosswalk-v004.jsonl"].splitlines()
    ]
    assert len({row["chunk_id"] for row in crosswalk}) == 726
    assert len({row["prior_chunk_id"] for row in crosswalk}) == 726
    assert sum(row["governance_changed"] for row in crosswalk) == 71
    for item in preview["input_inventory"]:
        assert helper.sha((ROOT / item["path"]).read_bytes()) == item["sha256"]
