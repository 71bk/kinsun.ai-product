"""Candidate-before-fact memory schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryType(str, Enum):
    PREFERENCE = "PREFERENCE"
    IMPORTANT_RELATIONSHIP = "IMPORTANT_RELATIONSHIP"
    ROUTINE = "ROUTINE"
    COMMUNICATION_PREFERENCE = "COMMUNICATION_PREFERENCE"
    PERSONAL_HISTORY = "PERSONAL_HISTORY"


class MemoryKind(str, Enum):
    MUSIC_PREFERENCE = "MUSIC_PREFERENCE"
    HOBBY = "HOBBY"
    PREFERRED_ADDRESS = "PREFERRED_ADDRESS"
    FAMILY_RELATIONSHIP = "FAMILY_RELATIONSHIP"
    CONTACT_ROUTINE = "CONTACT_ROUTINE"
    DAILY_ROUTINE = "DAILY_ROUTINE"
    HEALTH_INFERENCE = "HEALTH_INFERENCE"
    MEDICATION_JUDGMENT = "MEDICATION_JUDGMENT"
    MOOD_OR_LONELINESS_INFERENCE = "MOOD_OR_LONELINESS_INFERENCE"
    FAMILY_CONFLICT = "FAMILY_CONFLICT"
    FINANCIAL_INFORMATION = "FINANCIAL_INFORMATION"
    SENSITIVE_OR_UNKNOWN = "SENSITIVE_OR_UNKNOWN"


class MemoryRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MemoryPolicyDecision(str, Enum):
    AUTO_ACTIVATED_LOW = "AUTO_ACTIVATED_LOW"
    PENDING_ELDER_CONFIRMATION = "PENDING_ELDER_CONFIRMATION"
    PENDING_SUPPORTED_CONFIRMATION = "PENDING_SUPPORTED_CONFIRMATION"
    ELDER_CONFIRMED_MEDIUM = "ELDER_CONFIRMED_MEDIUM"
    ELDER_CONFIRMED_SUPPORTED = "ELDER_CONFIRMED_SUPPORTED"
    REJECTED_HIGH_RISK = "REJECTED_HIGH_RISK"
    NO_MEMORY = "NO_MEMORY"


class MemoryVerificationLevel(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    POLICY_VERIFIED = "POLICY_VERIFIED"
    ELDER_CONFIRMED = "ELDER_CONFIRMED"


class RequiredMemoryVerification(str, Enum):
    NONE = "NONE"
    ELDER_CONFIRMATION = "ELDER_CONFIRMATION"
    SUPPORTED_ELDER_CONFIRMATION = "SUPPORTED_ELDER_CONFIRMATION"
    RESTRICTED = "RESTRICTED"


class SpeakerVerificationLevel(str, Enum):
    UNKNOWN = "UNKNOWN"
    VERIFIED_ELDER = "VERIFIED_ELDER"
    WITNESSED_ELDER = "WITNESSED_ELDER"
    THIRD_PARTY = "THIRD_PARTY"


class CreateMemoryCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_type: MemoryType
    memory_kind: MemoryKind
    normalized_content: str = Field(min_length=1, max_length=500)
    source_event_ids: list[UUID] = Field(min_length=1, max_length=16)
    possible_conflict: bool = False
    conflict_with_memory_ids: list[UUID] = Field(default_factory=list, max_length=16)
    confirmation_question: str = Field(min_length=1, max_length=300)
    extractor_version: str = Field(min_length=1, max_length=80)
    extraction_confidence: float = Field(ge=0, le=1)
    proposal_risk_hint: MemoryRiskLevel


class ConfirmMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_method: Literal["ELDER_UI", "CAREGIVER_REVIEW", "LEGAL_REPRESENTATIVE"] = Field(
        description=(
            "Only ELDER_UI can activate a candidate. Legacy caregiver and legal "
            "representative values remain parseable during deprecation but fail "
            "closed at the Core authorization gate. VOICE remains unavailable "
            "until the voice path can produce authenticated candidate-specific "
            "affirmative evidence."
        )
    )
    expected_candidate_version: int = Field(ge=1)
    consent_version: int = Field(ge=1)


class VoiceMemoryConfirmationRequest(BaseModel):
    """Trusted Speech-to-Core decision for one exact Memory candidate version."""

    model_config = ConfigDict(extra="forbid")

    confirmation_method: Literal["ELDER_VOICE", "WITNESSED_VOICE"]
    session_id: UUID
    expected_candidate_version: int = Field(ge=1)
    consent_version: int = Field(ge=1)
    confirmation_question_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_intent: Literal["AFFIRM", "REJECT", "UNCERTAIN", "DEFER"]
    witness_actor_id: UUID | None = None
    witness_evidence_reference: str | None = Field(
        default=None,
        min_length=10,
        max_length=300,
        pattern=r"^evidence:[0-9a-fA-F-]{36}$",
    )

    @model_validator(mode="after")
    def validate_witness_pair(self) -> VoiceMemoryConfirmationRequest:
        witnessed = self.confirmation_method == "WITNESSED_VOICE"
        has_witness_pair = (
            self.witness_actor_id is not None and self.witness_evidence_reference is not None
        )
        if witnessed != has_witness_pair:
            raise ValueError(
                "WITNESSED_VOICE requires witness_actor_id and "
                "witness_evidence_reference; ELDER_VOICE forbids them"
            )
        return self


class VoiceMemoryDecisionResponse(BaseModel):
    """Bounded Speech-facing result; Memory content never crosses this boundary."""

    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    status: Literal["ACTIVE", "REJECTED", "DEFERRED", "PENDING_CONFIRMATION"]


class MemoryDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)


class UpdateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=120)


class MemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    elder_id: UUID
    memory_type: MemoryType
    content: str
    status: Literal[
        "CANDIDATE",
        "PENDING_CONFIRMATION",
        "CONFIRMED",
        "ACTIVE",
        "DEFERRED",
        "REJECTED",
        "INACTIVE",
        "DELETED",
    ]
    source_event_ids: list[UUID]
    confirmed_by: UUID | None
    confirmed_at: datetime | None
    version: int
    active_from: datetime | None
    inactive_at: datetime | None
    consent_version: int
    graph_projection_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryResponse]
    next_cursor: str | None
    has_more: bool


class MemoryDeletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    status: Literal["DELETED"]
