"""Bounded enrollment management commands and restricted read models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.elder_profile import StrictModel

EnrollmentStatus = Literal["PENDING", "ACTIVE", "SUSPENDED", "ENDED"]


class EnrollmentCommand(StrictModel):
    expected_version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=1, max_length=120)


class EnrollmentResponse(StrictModel):
    enrollment_id: UUID
    elder_id: UUID
    display_name: str
    care_unit_id: UUID
    status: EnrollmentStatus
    version: int = Field(ge=1)
    valid_from: datetime
    valid_until: datetime | None
    ended_at: datetime | None
    can_manage: bool


class EnrollmentListResponse(StrictModel):
    items: list[EnrollmentResponse]
    next_cursor: str | None
    has_more: bool


class EnrollmentChangeResponse(StrictModel):
    enrollment_change_id: UUID
    changed_by_actor_id: UUID
    changed_by_name: str
    from_status: EnrollmentStatus
    to_status: EnrollmentStatus
    version: int = Field(ge=2)
    reason: str = Field(min_length=1, max_length=120)
    created_at: datetime


class EnrollmentHistoryResponse(StrictModel):
    items: list[EnrollmentChangeResponse]
    next_cursor: str | None
    has_more: bool
