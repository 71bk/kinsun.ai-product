from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from rag_ingestion.v3_verified_candidate import promote_record

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_ROOT = REPOSITORY_ROOT / "contracts" / "schemas" / "rag"
V2_SCHEMA_PATH = SCHEMA_ROOT / "rag-chunk-v2.1.schema.json"
V3_SCHEMA_PATH = SCHEMA_ROOT / "rag-chunk-v3.1.schema.json"
ACCEPTANCE_SCHEMA_PATH = SCHEMA_ROOT / "rag-owner-human-review-acceptance-v1.schema.json"
V002_CHUNK_ROOT = REPOSITORY_ROOT / "data/rag-v2/candidates/v002/chunks"
SHA256 = "0" * 64


@pytest.fixture(scope="module")
def chunk_validator() -> Draft202012Validator:
    v2_schema = json.loads(V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema = json.loads(V3_SCHEMA_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(v2_schema["$id"], Resource.from_contents(v2_schema))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


@pytest.fixture(scope="module")
def acceptance_validator() -> Draft202012Validator:
    schema = json.loads(ACCEPTANCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_owner_acceptance_authorizes_verified_staging_only(
    acceptance_validator: Draft202012Validator,
) -> None:
    acceptance = _acceptance()
    acceptance_validator.validate(acceptance)

    acceptance["gates"]["production_approved"] = True
    with pytest.raises(ValidationError):
        acceptance_validator.validate(acceptance)


def test_verified_official_successor_preserves_source_and_safety_fields(
    chunk_validator: Draft202012Validator,
) -> None:
    prior = _first_record("hpa_elder_fall_prevention_tips_manual_202102.rag-chunk-v2.v002.jsonl")
    successor = promote_record(prior, _acceptance(), _acceptance_result())

    chunk_validator.validate(successor)
    assert successor["governance"]["review_status"] == "verified"
    assert successor["governance"]["current_status"] == "current"
    assert successor["governance"]["version_check_status"] == "verified_official_source"
    assert successor["governance"]["license_status"] == prior["governance"]["license_status"]
    assert successor["retrieval_policy"]["risk_level"] == prior["retrieval_policy"]["risk_level"]
    assert (
        successor["retrieval_policy"]["stop_normal_rag"]
        == prior["retrieval_policy"]["stop_normal_rag"]
    )
    assert successor["content"] == prior["content"]
    assert successor["citation"] == prior["citation"]
    assert successor["governance"]["production_approved"] is False


def test_verified_research_successor_stays_research_evidence(
    chunk_validator: Draft202012Validator,
) -> None:
    prior = _first_record("frontiers_loneliness_speech_analysis_2021.rag-chunk-v2.v002.jsonl")
    successor = promote_record(prior, _acceptance(), _acceptance_result())

    chunk_validator.validate(successor)
    assert successor["governance"]["distribution_scope"] == "research_evidence"
    assert successor["governance"]["version_check_status"] == "pending"


def test_verified_successor_cannot_enable_production(
    chunk_validator: Draft202012Validator,
) -> None:
    prior = _first_record("mohw_1966_apply_ltc.rag-chunk-v2.v002.jsonl")
    successor = promote_record(prior, _acceptance(), _acceptance_result())
    successor["governance"]["production_approved"] = True

    with pytest.raises(ValidationError):
        chunk_validator.validate(successor)


def test_explicit_superseded_chunk_is_not_promoted(
    chunk_validator: Draft202012Validator,
) -> None:
    path = V002_CHUNK_ROOT / "mohw_family_caregiver_support_manual_202507.rag-chunk-v2.v002.jsonl"
    prior = next(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["governance"]["current_status"] == "superseded"
    )
    successor = promote_record(prior, _acceptance(), _acceptance_result())

    chunk_validator.validate(successor)
    assert successor["governance"]["current_status"] == "superseded"
    assert "current_status_not_current" in successor["retrieval_policy"]["retrieval_block_reasons"]
    assert successor["retrieval_policy"]["retrieval_eligible"] is False


def _first_record(filename: str) -> dict[str, object]:
    return json.loads((V002_CHUNK_ROOT / filename).read_text(encoding="utf-8").splitlines()[0])


def _acceptance() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v002",
        "candidate_artifact_version": "v003",
        "status": "SIGNED",
        "project_owner_id": "IanHsu",
        "signer_role": "PROJECT_OWNER",
        "signed_at": "2026-08-26T12:00:00+08:00",
        "authorization": {
            "channel": "interactive_user_instruction",
            "statements": ["synthetic owner review test"],
            "statements_sha256": SHA256,
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": "IanHsu",
            "intent": "AUTHORIZE_V003_726_CHUNK_HUMAN_REVIEW",
            "cryptographic_signature": None,
        },
        "accepted_artifacts": {
            "prior_candidate_path": "data/rag-v2/candidates/v002",
            "prior_candidate_checksums_sha256": SHA256,
            "prior_public_use_acceptance_path": (
                "data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json"
            ),
            "prior_public_use_acceptance_sha256": SHA256,
            "prior_source_family_policy_path": (
                "data/rag-v3/governance/source-family-policy/candidates/v001/"
                "source-family-policy-map.json"
            ),
            "prior_source_family_policy_sha256": SHA256,
            "source_count": 17,
            "chunk_count": 726,
            "official_source_count": 14,
            "official_chunk_count": 651,
            "research_source_count": 3,
            "research_chunk_count": 75,
        },
        "review_assertions": {
            "review_method": "MANUAL_PROJECT_OWNER_REVIEW",
            "source_fidelity_verified": True,
            "exact_facts_verified": True,
            "source_versions_latest_confirmed": True,
            "reviewed_chunk_count": 726,
            "review_status": "verified",
        },
        "version_status_decision": {
            "promote_unknown_current_status": True,
            "preserve_explicit_superseded": True,
            "official_version_check_status": "verified_official_source",
            "research_version_check_status": "pending",
        },
        "license_policy_decision": {
            "source_party_public_use_review_completed": True,
            "missing_license_url_automatic_block": False,
            "affected_source_count": 13,
            "license_status_mutation_authorized": False,
        },
        "gates": {
            "environment": "STAGING",
            "candidate_build": "AUTHORIZED",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _acceptance_result() -> dict[str, object]:
    return {
        "acceptance_sha256": SHA256,
        "authorization_statements_sha256": SHA256,
        "project_owner_id": "IanHsu",
        "signed_at": "2026-08-26T12:00:00+08:00",
    }
