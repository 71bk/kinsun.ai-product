from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from agent_runtime.rag.runtime_policy import RuntimePolicyError, load_source_family_runtime_policy

ROOT = Path(__file__).resolve().parents[4]
BASE = (
    ROOT
    / "data/rag-v3/governance/source-family-policy/runtime/candidates/v003"
    / "source-family-runtime-policy.json"
)
SOURCE = "moj_long_term_care_services_act_20210609"


@pytest.fixture
def envelope():
    return {
        "schema_version": "4.0.0",
        "runtime_policy_version": "v004",
        "base_policy_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "base_policy": json.loads(BASE.read_bytes()),
        "projection_binding": {
            "release_id": "rag-v2-v004-aaaaaaaaaaaa",
            "candidate_sha256": "a" * 64,
            "embedding_profile_id": "ep-google-00a12ec45096fa9d97d9e9b6",
            "crosswalk_sha256": "b" * 64,
            "prior_release_id": "rag-v2-v002-bab68588963b",
            "id_mapping": "PRESERVE_SOURCE_AND_INDEX_V002_TO_V004",
            "production_approved": False,
        },
    }


def load(tmp_path, payload):
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    path = tmp_path / "policy.json"
    path.write_bytes(raw)
    return load_source_family_runtime_policy(path, expected_sha256=hashlib.sha256(raw).hexdigest())


def test_maps_only_projection_ids_and_keeps_governed_citation(tmp_path, envelope):
    policy = load(tmp_path, envelope)
    assert len(policy.candidate_chunk_ids) == 554
    assert all("_rag_v2_v004_" in key for key in policy.candidate_chunk_ids)
    raw = (
        ROOT / f"data/rag-v2/candidates/v002/chunks/{SOURCE}.rag-chunk-v2.v002.jsonl"
    ).read_bytes()
    second = json.loads(raw.splitlines()[1])
    source = {
        "chunk_id": SOURCE + "_rag_v2_v004_0002",
        "source_id": SOURCE,
        "text": second["content"]["text"],
    }
    candidate = policy.response_candidate(source, audience="elder", purpose="legal_reference")
    assert candidate is not None
    assert candidate.chunk_id == SOURCE + "_rag_v3_v003_0002"
    assert candidate.requires_professional_assessment is True
    assert candidate.citation.production_approved is False
    assert "第 2 條" in candidate.citation.source_locator
    source["chunk_id"] = SOURCE + "_rag_v2_v002_0002"
    assert policy.response_candidate(source, audience="elder", purpose="legal_reference") is None
    assert SOURCE + "_rag_v2_v004_0048" not in policy.candidate_chunk_ids


@pytest.mark.parametrize(
    "change", ["assessment", "scope", "text", "production", "release", "unknown"]
)
def test_cannot_change_base_policy_or_binding_contract(tmp_path, envelope, change):
    if change == "assessment":
        envelope["base_policy"]["chunks"][0]["requires_professional_assessment"] = True
    elif change == "scope":
        envelope["base_policy"]["chunks"][0]["chunk_allowed_purposes"].append("legal_reference")
    elif change == "text":
        envelope["base_policy"]["chunks"][0]["text_sha256"] = "0" * 64
    elif change == "production":
        envelope["projection_binding"]["production_approved"] = True
    elif change == "release":
        envelope["projection_binding"]["release_id"] = "rag-v2-v004-bbbbbbbbbbbb"
    else:
        envelope["allow_all"] = True
    with pytest.raises(RuntimePolicyError):
        load(tmp_path, envelope)


@pytest.mark.parametrize(
    "backend,release,profile",
    [
        ("opensearch", "rag-v2-v004-aaaaaaaaaaaa", "ep-google-00a12ec45096fa9d97d9e9b6"),
        ("postgresql", "rag-v2-v002-bab68588963b", "ep-google-00a12ec45096fa9d97d9e9b6"),
        ("postgresql", "rag-v2-v004-aaaaaaaaaaaa", "wrong"),
    ],
)
def test_wrong_backend_release_or_profile_rejected(tmp_path, envelope, backend, release, profile):
    policy = load(tmp_path, envelope)
    with pytest.raises(RuntimePolicyError):
        policy.validate_search_binding(
            backend=backend, release_id=release, embedding_profile_id=profile
        )


def test_matching_binding_accepted(tmp_path, envelope):
    policy = load(tmp_path, envelope)
    policy.validate_search_binding(
        backend="postgresql",
        release_id="rag-v2-v004-aaaaaaaaaaaa",
        embedding_profile_id="ep-google-00a12ec45096fa9d97d9e9b6",
    )


def test_local_policy_package_binds_exact_projection_candidate(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "law_policy_builder", ROOT / "scripts/rag/build_law_repair_runtime_policy.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = module.build_files(ROOT)
    assert files == module.build_files(ROOT)
    payload = json.loads(files["source-family-runtime-policy.json"])
    assert payload["base_policy"] == json.loads(BASE.read_bytes())
    assert payload["projection_binding"]["candidate_sha256"] == module.CANDIDATE_SHA
    policy = load(tmp_path, payload)
    assert len(policy.candidate_chunk_ids) == 554
    policy.validate_search_binding(
        backend="postgresql",
        release_id="rag-v2-v004-" + module.CANDIDATE_SHA[:12],
        embedding_profile_id="ep-google-00a12ec45096fa9d97d9e9b6",
    )
    for raw in files.values():
        assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
        raw.decode("utf-8")
