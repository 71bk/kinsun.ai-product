import importlib.util
import json
from dataclasses import asdict, replace
from hashlib import sha256

import pytest

from rag_ingestion.embedding_plan import EmbeddingPlanProfile
from rag_ingestion.knowledge_pipeline import ROOT, read_jsonl

SPEC = importlib.util.spec_from_file_location(
    "prepare_knowledge", ROOT / "scripts/rag/prepare_knowledge.py"
)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)

PROFILE = EmbeddingPlanProfile("test", "synthetic", "model", "001", "DOCUMENT", 2, "1")


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-embedding-profiles-v1",
                "target_profile_id": PROFILE.profile_id,
                "profiles": [asdict(PROFILE)],
            }
        ),
        encoding="utf-8",
    )
    return path


def invoke(registry, capsys, *args):
    code = CLI.main(["--profile-registry", str(registry), *map(str, args)])
    return code, json.loads(capsys.readouterr().out)


def test_explicit_audience_patch_cli_reports_single_local_diff(registry, capsys):
    original = ROOT / "data/rag-rechunk/successor/v001/corpus.jsonl"
    before = original.read_bytes()
    code, report = invoke(
        registry,
        capsys,
        "--dataset-version",
        "v008",
        "--audience-patches",
        ROOT / "config/rag/knowledge-audience-patches.json",
    )
    assert code == 0
    assert report["mode"] == "DRY_RUN"
    assert len(report["audience_patch_differences"]) == 1
    assert report["audience_patch_differences"][0]["to"] == [
        "care_professional",
        "family_caregiver",
    ]
    assert original.read_bytes() == before


def write_cache(tmp_path, entries, profiles=(PROFILE,)):
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-embedding-cache-v1",
                "entries": entries,
                "profiles": [asdict(profile) for profile in profiles],
            }
        ),
        encoding="utf-8",
    )
    return path


def cache_entry(text, **extra):
    return {
        "embedding_text": text,
        "embedding_text_sha256": sha256(text.encode()).hexdigest(),
        "profile_id": PROFILE.profile_id,
        **extra,
    }


def test_real_corpus_dry_run_is_read_only_and_baseline_is_not_vector_evidence(
    registry,
    tmp_path,
    capsys,
):
    destination = tmp_path / "not-created"
    code, result = invoke(registry, capsys, "--output", destination)
    assert code == 0
    assert result["mode"] == "DRY_RUN"
    assert not destination.exists()
    assert result["summary"]["retained_count"] == 658
    assert result["embedding_comparison"]["unchanged_content_count"] == 631
    assert result["embedding"]["summary"]["total"] == 658
    assert result["embedding"]["summary"]["potential_reuse"] == 0
    assert result["embedding"]["summary"]["available_reuse"] == 0


def test_write_is_byte_idempotent_and_plan_never_contains_vectors_or_text(
    registry,
    tmp_path,
    capsys,
):
    destination = tmp_path / "dataset"
    code, _ = invoke(registry, capsys, "--write", "--output", destination)
    assert code == 0
    before = {path.name: path.read_bytes() for path in destination.iterdir()}
    assert set(before) == {"chunks.jsonl", "report.json", "embedding-plan.json"}
    code, _ = invoke(registry, capsys, "--write", "--output", destination)
    assert code == 0
    assert before == {path.name: path.read_bytes() for path in destination.iterdir()}
    plan = json.loads(before["embedding-plan.json"])
    assert all("vector" not in row and "embedding_text" not in row for row in plan["rows"])
    assert plan["summary"]["available_reuse"] == 0


def test_cache_without_vector_is_only_potential_and_valid_vector_is_available(
    registry,
    tmp_path,
    capsys,
):
    rows = read_jsonl(ROOT / "data/rag-rechunk/successor/v001/corpus.jsonl")
    text = next(
        row["content"]["embedding_text"]
        for row in rows
        if (
            row["provenance"]["is_official_source"]
            and row["governance"]["current_status"] != "superseded"
            and row.get("rechunk", {}).get("recommended_use") != "navigation_only"
        )
    )
    path = write_cache(tmp_path, [cache_entry(text)])
    code, result = invoke(registry, capsys, "--cache", path)
    assert code == 0
    assert result["embedding"]["summary"]["potential_reuse"] >= 1
    assert result["embedding"]["summary"]["available_reuse"] == 0
    path = write_cache(tmp_path, [cache_entry(text, vector=[0.5, 0.25])])
    code, result = invoke(registry, capsys, "--cache", path)
    assert code == 0
    assert result["embedding"]["summary"]["available_reuse"] >= 1


@pytest.mark.parametrize(
    "mutation",
    [
        {"profile_id": "unknown"},
        {"vector": [0, 0]},
        {"vector": [1]},
        {"vector": [float("nan"), 1]},
        {"embedding_text_sha256": "a" * 64},
        {"model_id": "wrong-model"},
    ],
)
def test_invalid_cache_fails_without_write_or_echoing_content(
    registry,
    tmp_path,
    capsys,
    mutation,
):
    cache = write_cache(tmp_path, [cache_entry("SECRET-SOURCE-TEXT", **mutation)])
    destination = tmp_path / "dataset"
    code, result = invoke(registry, capsys, "--cache", cache, "--write", "--output", destination)
    assert code == 1
    assert result["status"] == "FAILED"
    assert "SECRET-SOURCE-TEXT" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)
    assert not destination.exists()


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":"x","schema_version":"y"}',
        '{"schema_version":"knowledge-embedding-cache-v1","entries":[],"profiles":[],"extra":1}',
        '{"schema_version":"knowledge-embedding-cache-v1","entries":[1],"profiles":[]}',
        '{"schema_version":"knowledge-embedding-cache-v1","entries":[],"extra":1e999}',
        '{"schema_version":"knowledge-embedding-cache-v1","entries":[]}',
    ],
)
def test_ambiguous_or_malformed_cache_json_rejects(registry, tmp_path, capsys, raw):
    cache = tmp_path / "cache.json"
    cache.write_text(raw, encoding="utf-8")
    assert invoke(registry, capsys, "--cache", cache)[0] == 1


def test_write_requires_explicit_destination(registry, capsys):
    code, result = invoke(registry, capsys, "--write")
    assert code == 1
    assert result["error"] == "WRITE_REQUIRES_OUTPUT"


@pytest.mark.parametrize("field", ["model_id", "config_version"])
def test_saved_cache_profile_drift_rejects_despite_identical_id_and_dimension(
    registry,
    tmp_path,
    capsys,
    field,
):
    # A cache really generated by the old profile cannot borrow today's model
    # identity just because both registry revisions accidentally keep the ID.
    cache = write_cache(tmp_path, [cache_entry("old text", vector=[0.5, 0.25])])
    current = json.loads(registry.read_text(encoding="utf-8"))
    current["profiles"] = [asdict(replace(PROFILE, **{field: "changed"}))]
    registry.write_text(json.dumps(current), encoding="utf-8")
    destination = tmp_path / "dataset"
    code, result = invoke(registry, capsys, "--cache", cache, "--write", "--output", destination)
    assert code == 1
    assert result["error"] == "PROFILE_METADATA_MISMATCH"
    assert not destination.exists()


def test_cache_entries_require_their_own_profile_snapshot(registry, tmp_path, capsys):
    cache = write_cache(tmp_path, [cache_entry("text", vector=[0.5, 0.25])], profiles=())
    code, result = invoke(registry, capsys, "--cache", cache)
    assert code == 1
    assert result["error"] == "UNKNOWN_PROFILE"


def test_compilation_failure_does_not_write(registry, tmp_path, capsys):
    source = tmp_path / "bad-corpus.jsonl"
    source.write_text('{"identity":{"chunk_id":"bad"}}\n', encoding="utf-8")
    destination = tmp_path / "dataset"
    code, result = invoke(registry, capsys, "--corpus", source, "--write", "--output", destination)
    assert code == 1
    assert result["status"] == "FAILED"
    assert not destination.exists()
