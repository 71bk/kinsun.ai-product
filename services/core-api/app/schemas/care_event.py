"""Care-event candidate, review, and response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.restricted_keys import contains_restricted_key


class CareEventType(str, Enum):
    MEAL = "MEAL"
    ACTIVITY = "ACTIVITY"
    SLEEP = "SLEEP"
    MEDICATION_STATEMENT = "MEDICATION_STATEMENT"
    EMOTION_EXPRESSION = "EMOTION_EXPRESSION"
    SOCIAL_CONTACT = "SOCIAL_CONTACT"
    EXPECTED_CONTACT_MISSED = "EXPECTED_CONTACT_MISSED"
    ACTIVITY_PARTICIPATION = "ACTIVITY_PARTICIPATION"
    ACTIVITY_CANCELLED = "ACTIVITY_CANCELLED"
    COMPANIONSHIP_NEED = "COMPANIONSHIP_NEED"


class ConfidenceBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


RESTRICTED_PAYLOAD_KEYS = {
    "transcript",
    "transcript_text",
    "audio",
    "audio_uri",
    "prompt",
    "full_prompt",
    "secret",
    "token",
    "asr_confidence",
}

EVIDENCE_REF_PATTERN = (
    r"^evidence:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
EvidenceRef = Annotated[
    str,
    Field(
        min_length=45,
        max_length=45,
        pattern=EVIDENCE_REF_PATTERN,
        description="Opaque evidence reference in evidence:<UUID> form; never transcript or audio.",
    ),
]


class CreateCareEventCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["CONVERSATION_SESSION", "MANUAL"]
    source_id: UUID | None = None
    source_version: int = Field(default=1, ge=1)
    event_type: CareEventType
    event_time: datetime | None = None
    structured_payload: dict[str, Any]
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=16)
    confidence_band: ConfidenceBand
    review_requirement: Literal["REQUIRED", "OPTIONAL"] = "REQUIRED"
    extractor_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_source(self) -> CreateCareEventCandidateRequest:
        if self.source_type == "CONVERSATION_SESSION" and self.source_id is None:
            raise ValueError("source_id is required for a conversation-session source")
        if contains_restricted_key(self.structured_payload, RESTRICTED_PAYLOAD_KEYS):
            raise ValueError("structured_payload contains a restricted field")
        return self


class ReviewCareEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["VERIFY", "CORRECT", "REJECT", "EXCLUDE"]
    reason_code: str = Field(min_length=1, max_length=120)
    corrected_payload: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_correction(self) -> ReviewCareEventRequest:
        if self.decision == "CORRECT" and self.corrected_payload is None:
            raise ValueError("corrected_payload is required for CORRECT")
        if self.decision != "CORRECT" and self.corrected_payload is not None:
            raise ValueError("corrected_payload is only allowed for CORRECT")
        if self.corrected_payload is not None and contains_restricted_key(
            self.corrected_payload, RESTRICTED_PAYLOAD_KEYS
        ):
            raise ValueError("corrected_payload contains a restricted field")
        return self


class CareEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    elder_id: UUID
    event_type: CareEventType
    event_time: datetime | None
    status: Literal[
        "CANDIDATE",
        "NEEDS_REVIEW",
        "VERIFIED",
        "CORRECTED",
        "REJECTED",
        "EXCLUDED",
        "DELETED",
    ]
    structured_payload: dict[str, Any]
    evidence_refs: list[EvidenceRef] = Field(max_length=16)
    confidence_band: ConfidenceBand
    version: int
    consent_version: int
    created_at: datetime
    updated_at: datetime


class CareEventReviewResponse(CareEventResponse):
    review_record_id: UUID
    rebuild_required: list[str]


class CareEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CareEventResponse]
    next_cursor: str | None
    has_more: bool
