"""Minimal human-authored record commands; scope and dates are server-owned."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateServiceRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_assignment_version: int = Field(ge=1)
    record_type: Literal["SERVICE_NOTE"] = "SERVICE_NOTE"
    content: str = Field(min_length=1, max_length=4000)


class ServiceRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    service_record_id: UUID
    assignment_id: UUID
    elder_id: UUID
    worker_id: UUID
    service_date: date
    service_timezone: str
    record_type: Literal["SERVICE_NOTE"]
    content: str
    status: Literal["COMPLETED"]
    version: Literal[1]
    assignment_version: int
    created_at: datetime
    completed_at: datetime


class ServiceRecordCompletionResponse(BaseModel):
    """Command receipt only: completion ends access to the professional note."""

    model_config = ConfigDict(extra="forbid")
    service_record_id: UUID
    assignment_id: UUID
    assignment_version: int = Field(ge=2)
    status: Literal["COMPLETED"]
