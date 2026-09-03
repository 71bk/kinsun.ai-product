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
