"""Care-assignment command and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssignmentScope = Literal[
    "elder:basic:read",
    "elder:sensitive:read",
    "assignment:read",
    "assignment:start",
    "assignment:complete",
    "care_event:candidate:create",
    "care_event:read",
    "summary:read",
]


class CreateAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    care_unit_id: UUID
    elder_id: UUID
    worker_actor_id: UUID
    service_start: datetime
    service_end: datetime
    allowed_data_scopes: list[AssignmentScope] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_period(self) -> CreateAssignmentRequest:
        if self.service_end <= self.service_start:
            raise ValueError("service_end must be after service_start")
        if len(set(self.allowed_data_scopes)) != len(self.allowed_data_scopes):
            raise ValueError("allowed_data_scopes must not contain duplicates")
        return self


class AssignmentCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=120)


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: UUID
    elder_id: UUID
    provider_tenant_id: UUID
    care_unit_id: UUID
    home_care_worker_id: UUID
    scheduled_start: datetime
    scheduled_end: datetime
    status: Literal[
        "DRAFT",
        "CONFIRMED",
        "IN_PROGRESS",
        "COMPLETED",
        "EXPIRED",
        "CANCELLED",
        "NO_SHOW",
    ]
    allowed_data_scopes: list[str]
    version: int
    expires_at: datetime


class AssignmentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AssignmentResponse]
