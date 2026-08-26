from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_ROOT = REPOSITORY_ROOT / "contracts" / "schemas" / "rag"
V2_SCHEMA_PATH = SCHEMA_ROOT / "rag-chunk-v2.1.schema.json"
V3_SCHEMA_PATH = SCHEMA_ROOT / "rag-chunk-v3.schema.json"
OWNER_ACCEPTANCE_SCHEMA_PATH = SCHEMA_ROOT / "rag-owner-public-use-acceptance-v3.schema.json"
V002_CHUNK_ROOT = REPOSITORY_ROOT / "data" / "rag-v2" / "candidates" / "v002" / "chunks"
SHA256 = "0" * 64


@pytest.fixture(scope="module")
def v3_validator() -> Draft202012Validator:
    v2_schema = json.loads(V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    v3_schema = json.loads(V3_SCHEMA_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(
        v2_schema["$id"],
        Resource.from_contents(v2_schema),
    )
    Draft202012Validator.check_schema(v3_schema)
    return Draft202012Validator(
        v3_schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


@pytest.fixture(scope="module")
def acceptance_validator() -> Draft202012Validator:
    schema = json.loads(OWNER_ACCEPTANCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_v003_official_successor_is_valid(v3_validator: Draft202012Validator) -> None:
    record = _as_v003(_first_record("mohw_1966_apply_ltc.rag-chunk-v2.v002.jsonl"))

    assert record["provenance"]["is_official_source"] is True
    assert record["governance"]["distribution_scope"] == "public_knowledge"
    v3_validator.validate(record)


def test_v003_research_cannot_claim_public_knowledge(
    v3_validator: Draft202012Validator,
) -> None:
    record = _as_v003(
        _first_record("frontiers_loneliness_speech_analysis_2021.rag-chunk-v2.v002.jsonl")
    )
    record["governance"]["distribution_scope"] = "research_evidence"
    v3_validator.validate(record)

    record["governance"]["distribution_scope"] = "public_knowledge"
    with pytest.raises(ValidationError):
        v3_validator.validate(record)


def test_v003_reuse_state_must_match_governance(
    v3_validator: Draft202012Validator,
) -> None:
    record = _as_v003(_first_record("mohw_1966_apply_ltc.rag-chunk-v2.v002.jsonl"))
    record["embedding_reuse"]["status"] = "REUSE_VERIFIED"

    with pytest.raises(ValidationError):
        v3_validator.validate(record)

    record["governance"]["embedding_status"] = "reuse_verified"
    v3_validator.validate(record)


def test_v003_never_auto_promotes_review_or_production(
    v3_validator: Draft202012Validator,
) -> None:
    record = _as_v003(_first_record("mohw_1966_apply_ltc.rag-chunk-v2.v002.jsonl"))
    record["governance"]["review_status"] = "verified"
    record["governance"]["production_approved"] = True

    with pytest.raises(ValidationError):
        v3_validator.validate(record)


def test_owner_public_use_acceptance_is_staging_only(
    acceptance_validator: Draft202012Validator,
) -> None:
    acceptance = _owner_acceptance()
    acceptance_validator.validate(acceptance)

    acceptance["gates"]["external_sync"] = "AUTHORIZED"
    acceptance["gates"]["production_approved"] = True
    with pytest.raises(ValidationError):
        acceptance_validator.validate(acceptance)


def test_owner_approval_cannot_replace_source_evidence(
    acceptance_validator: Draft202012Validator,
) -> None:
    acceptance = _owner_acceptance()
    acceptance["public_use_decision"]["owner_approval_replaces_source_evidence"] = True

    with pytest.raises(ValidationError):
        acceptance_validator.validate(acceptance)


def _first_record(filename: str) -> dict[str, object]:
    line = (V002_CHUNK_ROOT / filename).read_text(encoding="utf-8").splitlines()[0]
    return json.loads(line)


def _as_v003(record: dict[str, object]) -> dict[str, object]:
    successor = copy.deepcopy(record)
    identity = successor["identity"]
    governance = successor["governance"]
    content = successor["content"]
    provenance = successor["provenance"]
    assert isinstance(identity, dict)
    assert isinstance(governance, dict)
    assert isinstance(content, dict)
    assert isinstance(provenance, dict)

    source_id = identity["source_id"]
    chunk_index = identity["chunk_index"]
    prior_chunk_id = identity["chunk_id"]
    prior_chunk_file_id = identity["chunk_file_id"]
    assert isinstance(source_id, str)
    assert isinstance(chunk_index, int)
    assert isinstance(prior_chunk_id, str)
    assert isinstance(prior_chunk_file_id, str)

    successor["schema_version"] = "3.0.0"
    successor["artifact_version"] = "v003"
    identity["prior_chunk_id"] = prior_chunk_id
    identity["prior_chunk_file_id"] = prior_chunk_file_id
    identity["chunk_id"] = f"{source_id}_rag_v3_v003_{chunk_index:04d}"
    identity["chunk_file_id"] = f"{source_id}_rag_v3_v003"

    governance["review_status"] = "needs_review"
    governance["license_status"] = "approved"
    governance["embedding_status"] = "reuse_pending"
    governance["ingestion_status"] = "staging"
    governance["human_source_review"] = "owner_public_use_review_recorded"
    governance["production_gate"] = "blocked"
    governance["production_approved"] = False
    governance["data_classification"] = "public"
    governance["distribution_scope"] = (
        "public_knowledge" if provenance["is_official_source"] is True else "research_evidence"
    )
    governance["storage_target"] = "local_pending_upload"

    successor["review_evidence"] = {
        "acceptance_id": "rag-v3-owner-public-use-v001",
        "acceptance_path": ("data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json"),
        "acceptance_sha256": SHA256,
        "scope": "STAGING_PUBLIC_RETRIEVAL_POLICY",
        "decision": "APPROVED",
        "reviewer_id": "IanHsu",
        "reviewer_role": "PROJECT_OWNER",
        "reviewed_at": "2026-08-25T00:00:00+08:00",
        "authorization_statement_sha256": SHA256,
        "formal_item_level_source_fidelity": "NOT_RECORDED",
        "exact_facts_verified": "NOT_RECORDED",
        "production_approved": False,
    }
    successor["embedding_reuse"] = {
        "status": "REUSE_PENDING",
        "source_release_id": "rag-v2-v002-bab68588963b",
        "source_artifact_version": "v002",
        "source_chunk_id": prior_chunk_id,
        "match_key": "embedding_text_sha256",
        "source_embedding_text_sha256": content["embedding_text_sha256"],
        "embedding_profile_id": "ep-google-00a12ec45096fa9d97d9e9b6",
        "provider": "google",
        "model_id": "gemini-embedding-001",
        "dimension": 1024,
        "document_task_type": "RETRIEVAL_DOCUMENT",
    }
    return successor


def _owner_acceptance() -> dict[str, object]:
    return {
        "schema_version": "3.0.0",
        "acceptance_version": "v001",
        "candidate_artifact_version": "v003",
        "status": "SIGNED",
        "project_owner_id": "IanHsu",
        "signer_role": "PROJECT_OWNER",
        "signed_at": "2026-08-25T00:00:00+08:00",
        "authorization": {
            "channel": "interactive_user_instruction",
            "statements": ["都是公開資料我看過核准", "好那開始V3計劃"],
            "statements_sha256": SHA256,
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": "IanHsu",
            "intent": "AUTHORIZE_V003_STAGING_PUBLIC_RETRIEVAL_POLICY",
            "cryptographic_signature": None,
        },
        "accepted_artifacts": {
            "prior_candidate_path": "data/rag-v2/candidates/v002",
            "prior_candidate_checksums_sha256": SHA256,
            "prior_allowlist_sha256": SHA256,
            "prior_acceptance_path": (
                "data/rag-v2/human-review/acceptance/v002/"
                "owner-staging-embedding-acceptance.json"
            ),
            "prior_acceptance_sha256": SHA256,
            "source_count": 17,
            "chunk_count": 726,
            "official_source_count": 14,
            "official_chunk_count": 651,
            "research_source_count": 3,
            "research_chunk_count": 75,
        },
        "acceptance_scope": "STAGING_PUBLIC_RETRIEVAL_POLICY",
        "public_use_decision": {
            "public_source_review_completed": True,
            "project_use_approved": True,
            "owner_approval_replaces_source_evidence": False,
        },
        "retrieval_policy_decision": {
            "allowed_audiences": [
                "elder",
                "family_caregiver",
                "care_professional",
                "system_admin",
            ],
            "high_or_unknown_normal_rag": "DENY",
            "audience_override_bypasses_risk": False,
            "embedding_reuse_allowed": True,
        },
        "review_assertions": {
            "formal_item_level_source_fidelity": "NOT_RECORDED",
            "exact_facts_verified": "NOT_RECORDED",
            "source_version_verified": "PRESERVE_EXISTING_EVIDENCE",
            "review_status": "needs_review",
        },
        "gates": {
            "environment": "STAGING",
            "candidate_build": "AUTHORIZED",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }
