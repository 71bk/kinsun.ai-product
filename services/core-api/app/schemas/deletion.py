"""Deletion workflow status schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DeletionJobItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deletion_job_item_id: UUID
    resource_type: str
    system_of_record: str
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "FAILED", "SKIPPED"]
    attempt_count: int
    started_at: datetime | None
    failure_code: str | None
    completed_at: datetime | None


class DeletionRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deletion_request_id: UUID
    elder_id: UUID
    consent_id: UUID | None
    scope: list[str]
    status: Literal[
        "REQUESTED",
        "IN_PROGRESS",
        "PARTIAL_FAILED",
        "COMPLETED",
        "CANCELLED",
    ]
    reason_code: str | None
    requested_at: datetime
    effective_at: datetime
    completed_at: datetime | None
    items: list[DeletionJobItemResponse]
