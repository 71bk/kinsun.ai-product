"""Professional Care Action command and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CareActionType = Literal[
    "CONTACT_ELDER",
    "CONTACT_FAMILY",
    "CONFIRM_INFORMATION",
    "INVITE_ACTIVITY",
    "FOLLOW_UP",
    "OTHER",
]
CareActionPriority = Literal["LOW", "MEDIUM", "HIGH"]
CareActionStatus = Literal["OPEN", "IN_PROGRESS", "COMPLETED", "POSTPONED", "CANCELLED"]
CareActionCandidateStatus = Literal["PENDING_REVIEW", "ADOPTED", "REJECTED", "EXCLUDED"]
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("due_at must include a timezone offset")
    return value


def _required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must contain non-whitespace characters")
    return normalized


class CreateCareActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: CareActionType
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    trigger_reason: str = Field(min_length=1, max_length=2000)
    related_event_ids: list[UUID] = Field(min_length=1, max_length=16)
    assignee_actor_id: UUID | None = None
    due_at: datetime
    priority: CareActionPriority = "MEDIUM"

    _normalize_required_text = field_validator("title", "trigger_reason")(_required_text)
    _validate_due_at = field_validator("due_at")(_aware)

    @model_validator(mode="after")
    def validate_event_ids(self) -> CreateCareActionRequest:
        if len(set(self.related_event_ids)) != len(self.related_event_ids):
            raise ValueError("related_event_ids must not contain duplicates")
        return self


class UpdateCareActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["IN_PROGRESS", "COMPLETED", "POSTPONED", "CANCELLED"]
    expected_version: int = Field(ge=1)
    resolution: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None

    _validate_due_at = field_validator("due_at")(_aware)

    @model_validator(mode="after")
    def validate_transition_details(self) -> UpdateCareActionRequest:
        if self.status in {"COMPLETED", "POSTPONED", "CANCELLED"} and not (
            self.resolution and self.resolution.strip()
        ):
            raise ValueError("resolution is required for this status")
        if self.status == "POSTPONED" and self.due_at is None:
            raise ValueError("due_at is required when postponing an action")
        if self.status == "IN_PROGRESS" and self.resolution is not None:
            raise ValueError("resolution is not allowed when starting an action")
        return self


class CareActionSourceEventProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_version_id: UUID
    event_version: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=64)
    event_time: datetime | None
    source_status: Literal["VERIFIED", "CORRECTED"]
    snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    snapshot_schema_version: Literal["care-event-provenance.v1"]


class CareActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    care_action_id: UUID
    elder_id: UUID
    action_type: CareActionType
    title: str
    description: str | None
    trigger_reason: str | None
    related_event_ids: list[UUID]
    source_event_provenance: list[CareActionSourceEventProvenance] = Field(
        default_factory=list,
        max_length=16,
        description=(
            "Server-captured immutable source versions; empty only for legacy actions "
            "created before provenance capture was introduced."
        ),
    )
    assignee_actor_id: UUID
    due_at: datetime | None
    priority: CareActionPriority
    status: CareActionStatus
    resolution: str | None
    created_by_actor_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class CareActionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CareActionResponse]
    next_cursor: str | None
    has_more: bool


class AgentCareActionCandidateProposal(BaseModel):
    """Untrusted Runtime output before Core policy and source binding."""

    model_config = ConfigDict(extra="forbid")

    action_type: CareActionType
    suggested_title: str = Field(min_length=1, max_length=200)
    trigger_reason: str = Field(min_length=1, max_length=2000)
    suggested_due_at: datetime
    priority: Literal["LOW", "MEDIUM"] = "MEDIUM"
    extractor_version: str = Field(min_length=1, max_length=80)

    _normalize_required_text = field_validator("suggested_title", "trigger_reason")(_required_text)
    _validate_due_at = field_validator("suggested_due_at")(_aware)


class AdoptCareActionCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: datetime | None = None
    priority: CareActionPriority | None = None

    _validate_due_at = field_validator("due_at")(_aware)

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        return _required_text(value) if value is not None else None


class DismissCareActionCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["REJECT", "EXCLUDE"]
    expected_version: int = Field(ge=1)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,119}$")
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CareActionCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    care_action_candidate_id: UUID
    elder_id: UUID
    action_type: CareActionType
    suggested_title: str = Field(min_length=1, max_length=200)
    trigger_reason: str = Field(min_length=1, max_length=2000)
    source_event_provenance: list[CareActionSourceEventProvenance] = Field(
        min_length=1,
        max_length=16,
    )
    suggested_due_at: datetime
    priority: Literal["LOW", "MEDIUM"]
    status: CareActionCandidateStatus
    disposition_reason_code: str | None = Field(pattern=r"^[A-Z][A-Z0-9_]{2,119}$")
    disposition_notes: str | None = Field(max_length=2000)
    decided_by_actor_id: UUID | None
    decided_at: datetime | None
    adopted_care_action_id: UUID | None
    extractor_version: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_disposition(self) -> CareActionCandidateResponse:
        decision_fields = (
            self.disposition_reason_code,
            self.decided_by_actor_id,
            self.decided_at,
        )
        if self.status == "PENDING_REVIEW":
            if any(value is not None for value in (*decision_fields, self.disposition_notes)):
                raise ValueError("pending candidate must not contain disposition data")
            if self.adopted_care_action_id is not None:
                raise ValueError("pending candidate must not reference a Care Action")
        elif any(value is None for value in decision_fields):
            raise ValueError("decided candidate requires disposition metadata")
        elif self.status == "ADOPTED" and self.adopted_care_action_id is None:
            raise ValueError("adopted candidate requires a Care Action")
        elif self.status in {"REJECTED", "EXCLUDED"} and self.adopted_care_action_id is not None:
            raise ValueError("dismissed candidate must not reference a Care Action")
        return self


class CareActionCandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CareActionCandidateResponse]
    next_cursor: str | None
    has_more: bool
