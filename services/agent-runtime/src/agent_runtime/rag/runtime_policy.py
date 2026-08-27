"""Fail-closed runtime loader for the source-family policy v002 projection."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PUBLIC_AUDIENCES = (
    "elder",
    "family_caregiver",
    "care_professional",
    "system_admin",
)
PUBLIC_AUDIENCE_SET = frozenset(PUBLIC_AUDIENCES)
NON_PROFESSIONAL_AUDIENCES = frozenset({"elder", "family_caregiver"})
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

Audience = Literal["elder", "family_caregiver", "care_professional", "system_admin"]
Purpose = Literal[
    "care_record",
    "care_summary",
    "evaluation",
    "explainable_evidence",
    "form_reference",
    "general_information",
    "health_education",
    "human_administered_assessment_design",
    "legal_reference",
    "manual_review",
    "research_reference",
    "resource_navigation",
    "safety_routing",
    "scale_explanation",
    "source_lookup",
]


class RuntimePolicyError(ValueError):
    """Runtime policy bytes or semantics are not safe to use."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RuntimeCitation(_StrictModel):
    artifact_version: Literal["v003"]
    title: str = Field(min_length=1, max_length=512)
    publisher: str | None = Field(max_length=512)
    section: str = Field(min_length=1, max_length=1024)
    physical_page_start: int | None = Field(ge=1)
    physical_page_end: int | None = Field(ge=1)
    printed_page_start: int | None = Field(ge=1)
    printed_page_end: int | None = Field(ge=1)
    source_locator: str = Field(min_length=1, max_length=2048)
    direct_official_source_url: str | None = Field(max_length=4096)
    official_source_page_url: str | None = Field(max_length=4096)
    direct_source_url: str | None = Field(max_length=4096)
    source_page_url: str | None = Field(max_length=4096)
    is_official_source: Literal[True]
    source_version: str | None = Field(max_length=512)
    source_version_date: str | None = Field(max_length=512)
    version_published_at: str | None = Field(max_length=512)
    source_page_updated_at: str | None = Field(max_length=512)
    published_at: str | None = Field(max_length=512)
    last_verified_at: str | None = Field(max_length=512)
    review_status: Literal["verified"]
    production_approved: Literal[False]


class RuntimePolicyChunk(_StrictModel):
    prior_chunk_id: str = Field(min_length=1, max_length=256)
    chunk_id: str = Field(min_length=1, max_length=256)
    source_id: str = Field(min_length=1, max_length=256)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    embedding_text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    effective_risk_level: Literal["low", "medium"]
    retrieval_audiences: tuple[Audience, ...] = Field(min_length=4, max_length=4)
    source_allowed_purposes: tuple[Purpose, ...] = Field(min_length=1)
    chunk_allowed_purposes: tuple[Purpose, ...]
    requires_official_assessment: bool | None
    requires_professional_assessment: bool | None
    citation: RuntimeCitation


class _SourcePolicyBinding(_StrictModel):
    path: Literal[
        "data/rag-v3/governance/source-family-policy/candidates/v002/"
        "source-family-policy-map.json"
    ]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class _CandidateBinding(_StrictModel):
    path: Literal["data/rag-v3/candidates/v003"]
    checksums_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    crosswalk_path: Literal["data/rag-v3/candidates/v003/crosswalk/chunk-id-crosswalk-v003.jsonl"]
    crosswalk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_release_id: Literal["rag-v2-v002-bab68588963b"]
    embedding_profile_id: Literal["ep-google-00a12ec45096fa9d97d9e9b6"]


class _GlobalPolicyV1(_StrictModel):
    retrieval_audiences: tuple[Audience, ...]
    retrieve_before_response_policy: Literal[True]
    ordinary_retrieval_risk_levels: tuple[Literal["low", "medium"], ...]
    ordinary_retrieval_stop_normal_rag: Literal[False]
    purpose_response_gate: Literal["EVALUATE_AFTER_RETRIEVAL"]
    assessment_response_gate: Literal["EVALUATE_AFTER_RETRIEVAL_NULL_DENIES_RESPONSE"]
    high_or_unknown_normal_rag: Literal["DENY"]
    research_route: Literal["INDEPENDENT_RESEARCH_REVIEW_REQUIRED"]
    runtime_safety_from_embedding_similarity: Literal[False]
    production_approved: Literal[False]


class _SummaryV1(_StrictModel):
    source_count: Literal[14]
    chunk_count: Literal[554]
    response_metadata_ready_count: Literal[302]
    risk_overlay_count: Literal[5]


class _Gates(_StrictModel):
    environment: Literal["STAGING"]
    runtime_integration: Literal["READY_FOR_STAGING_TEST"]
    golden_query: Literal["NOT_EXECUTED"]
    external_sync: Literal["NOT_AUTHORIZED"]
    production_status: Literal["BLOCKED"]
    production_approved: Literal[False]


class RuntimePolicyDocumentV1(_StrictModel):
    schema_version: Literal["1.0.0"]
    runtime_policy_version: Literal["v001"]
    source_policy_map_version: Literal["v002"]
    candidate_artifact_version: Literal["v003"]
    status: Literal["STAGING_RUNTIME_CANDIDATE"]
    source_policy_binding: _SourcePolicyBinding
    candidate_binding: _CandidateBinding
    global_policy: _GlobalPolicyV1
    chunks: tuple[RuntimePolicyChunk, ...] = Field(min_length=554, max_length=554)
    summary: _SummaryV1
    gates: _Gates


class RuntimePolicyChunkV2(RuntimePolicyChunk):
    requires_official_assessment: bool
    requires_professional_assessment: bool


class _AssessmentAcceptanceBinding(_StrictModel):
    path: Literal[
        "data/rag-v3/review/acceptance/v004/" "owner-assessment-response-policy-acceptance.json"
    ]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_version: Literal["v004"]


class _PriorRuntimePolicyBinding(_StrictModel):
    path: Literal[
        "data/rag-v3/governance/source-family-policy/runtime/candidates/v001/"
        "source-family-runtime-policy.json"
    ]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_policy_version: Literal["v001"]
    relationship: Literal["SUPERSEDES_WITHOUT_MUTATING_PRIOR_BYTES"]


class _GlobalPolicyV2(_StrictModel):
    retrieval_audiences: tuple[Audience, ...]
    retrieve_before_response_policy: Literal[True]
    ordinary_retrieval_risk_levels: tuple[Literal["low", "medium"], ...]
    ordinary_retrieval_stop_normal_rag: Literal[False]
    purpose_response_gate: Literal["EVALUATE_AFTER_RETRIEVAL"]
    assessment_response_gate: Literal[
        "ALLOW_GENERAL_INFORMATION_TRUE_REQUIRES_DETERMINISTIC_ADVISORY_NULL_DENIES"
    ]
    high_or_unknown_normal_rag: Literal["DENY"]
    research_route: Literal["INDEPENDENT_RESEARCH_REVIEW_REQUIRED"]
    runtime_safety_from_embedding_similarity: Literal[False]
    production_approved: Literal[False]


class _SummaryV2(_StrictModel):
    source_count: Literal[14]
    chunk_count: Literal[554]
    response_metadata_ready_count: Literal[522]
    risk_overlay_count: Literal[5]
    professional_null_to_true_count: Literal[220]
    official_null_to_true_count: Literal[5]
    assessment_advisory_chunk_count: Literal[372]


class RuntimePolicyDocumentV2(_StrictModel):
    schema_version: Literal["2.0.0"]
    runtime_policy_version: Literal["v002"]
    source_policy_map_version: Literal["v002"]
    candidate_artifact_version: Literal["v003"]
    status: Literal["STAGING_RUNTIME_CANDIDATE"]
    source_policy_binding: _SourcePolicyBinding
    candidate_binding: _CandidateBinding
    assessment_acceptance_binding: _AssessmentAcceptanceBinding
    prior_runtime_policy_binding: _PriorRuntimePolicyBinding
    global_policy: _GlobalPolicyV2
    chunks: tuple[RuntimePolicyChunkV2, ...] = Field(min_length=554, max_length=554)
    summary: _SummaryV2
    gates: _Gates


RuntimePolicyDocument = RuntimePolicyDocumentV1 | RuntimePolicyDocumentV2
RuntimePolicyCandidate = RuntimePolicyChunk | RuntimePolicyChunkV2


@dataclass(frozen=True, slots=True)
class SourceFamilyRuntimePolicy:
    """Validated immutable policy projection indexed by the active v002 chunk IDs."""

    document: RuntimePolicyDocument
    sha256: str
    _by_prior_chunk_id: Mapping[str, RuntimePolicyCandidate]

    @property
    def candidate_chunk_ids(self) -> tuple[str, ...]:
        return tuple(self._by_prior_chunk_id)

    def response_candidate(
        self,
        source: Mapping[str, object],
        *,
        audience: str | None,
        purpose: str | None,
    ) -> RuntimePolicyCandidate | None:
        """Apply post-retrieval role, purpose, assessment, and byte-integrity gates."""

        prior_chunk_id = source.get("chunk_id")
        if not isinstance(prior_chunk_id, str):
            return None
        candidate = self._by_prior_chunk_id.get(prior_chunk_id)
        if candidate is None or source.get("source_id") != candidate.source_id:
            return None
        text = source.get("text")
        if not isinstance(text, str) or not hmac.compare_digest(
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            candidate.text_sha256,
        ):
            return None
        if audience not in PUBLIC_AUDIENCE_SET or audience not in candidate.retrieval_audiences:
            return None
        if (
            not isinstance(purpose, str)
            or purpose not in candidate.source_allowed_purposes
            or purpose not in candidate.chunk_allowed_purposes
        ):
            return None
        official = candidate.requires_official_assessment
        professional = candidate.requires_professional_assessment
        if not isinstance(official, bool) or not isinstance(professional, bool):
            return None
        if (
            isinstance(self.document, RuntimePolicyDocumentV1)
            and audience in NON_PROFESSIONAL_AUDIENCES
            and (official or professional)
        ):
            return None
        return candidate


def load_source_family_runtime_policy(
    path: str | Path,
    *,
    expected_sha256: str,
) -> SourceFamilyRuntimePolicy:
    """Load only an independently hash-pinned staging runtime policy."""

    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise RuntimePolicyError(
            "RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256 must be lowercase SHA-256"
        )
    policy_path = Path(path).resolve()
    try:
        raw = policy_path.read_bytes()
    except OSError as exc:
        raise RuntimePolicyError("source-family runtime policy is unavailable") from exc
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise RuntimePolicyError("source-family runtime policy SHA-256 mismatch")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise RuntimePolicyError("source-family runtime policy must be UTF-8 LF-only without BOM")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimePolicyError("source-family runtime policy is not valid UTF-8 JSON") from exc
    try:
        # JSON mode preserves strict scalar validation while accepting JSON arrays
        # for immutable tuple fields.
        if not isinstance(payload, dict):
            raise RuntimePolicyError("source-family runtime policy root must be an object")
        version = payload.get("runtime_policy_version")
        if version == "v001":
            document: RuntimePolicyDocument = RuntimePolicyDocumentV1.model_validate_json(raw)
        elif version == "v002":
            document = RuntimePolicyDocumentV2.model_validate_json(raw)
        else:
            raise RuntimePolicyError("source-family runtime policy version is unsupported")
    except ValidationError as exc:
        raise RuntimePolicyError("source-family runtime policy contract is invalid") from exc
    _validate_semantics(document)
    by_prior_chunk_id = {candidate.prior_chunk_id: candidate for candidate in document.chunks}
    return SourceFamilyRuntimePolicy(
        document=document,
        sha256=actual_sha256,
        _by_prior_chunk_id=MappingProxyType(by_prior_chunk_id),
    )


def _validate_semantics(document: RuntimePolicyDocument) -> None:
    if document.global_policy.retrieval_audiences != PUBLIC_AUDIENCES:
        raise RuntimePolicyError("runtime policy public audiences diverged")
    if document.global_policy.ordinary_retrieval_risk_levels != ("low", "medium"):
        raise RuntimePolicyError("runtime policy risk levels diverged")
    prior_ids = tuple(candidate.prior_chunk_id for candidate in document.chunks)
    successor_ids = tuple(candidate.chunk_id for candidate in document.chunks)
    if prior_ids != tuple(sorted(prior_ids)) or len(set(prior_ids)) != 554:
        raise RuntimePolicyError("runtime policy prior chunk IDs must be sorted and unique")
    if len(set(successor_ids)) != 554:
        raise RuntimePolicyError("runtime policy successor chunk IDs must be unique")
    if len({candidate.source_id for candidate in document.chunks}) != 14:
        raise RuntimePolicyError("runtime policy source count diverged")
    if any(candidate.retrieval_audiences != PUBLIC_AUDIENCES for candidate in document.chunks):
        raise RuntimePolicyError("runtime candidate audiences diverged")
    response_ready = sum(
        isinstance(candidate.requires_official_assessment, bool)
        and isinstance(candidate.requires_professional_assessment, bool)
        and bool(candidate.chunk_allowed_purposes)
        for candidate in document.chunks
    )
    expected_ready = 302 if isinstance(document, RuntimePolicyDocumentV1) else 522
    if response_ready != expected_ready:
        raise RuntimePolicyError("runtime response-metadata-ready count diverged")
    if isinstance(document, RuntimePolicyDocumentV2):
        professional_true = sum(
            candidate.requires_professional_assessment for candidate in document.chunks
        )
        official_true = sum(candidate.requires_official_assessment for candidate in document.chunks)
        advisory_count = sum(
            candidate.requires_official_assessment or candidate.requires_professional_assessment
            for candidate in document.chunks
        )
        if professional_true != 362 or official_true != 61 or advisory_count != 372:
            raise RuntimePolicyError("runtime v002 assessment overlay semantics diverged")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimePolicyError(f"duplicate runtime policy key: {key}")
        result[key] = value
    return result
