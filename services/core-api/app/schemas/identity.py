"""Pydantic schemas for Identity API endpoints.

Defines request/response models for:
- GET /api/v1/me → MeResponse
- GET /api/v1/me/authorized-elders → AuthorizedEldersResponse

All responses are wrapped in SuccessEnvelope at the handler layer.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ElderMode(str, Enum):
    """Valid mode values for the authorized-elders query parameter."""

    DAYCARE = "daycare"
    HOME_CARE = "home-care"
    FAMILY = "family"


class MeResponse(BaseModel):
    """Response schema for GET /api/v1/me.

    Contains the authenticated actor's profile information.
    """

    model_config = ConfigDict(from_attributes=True)

    actor_id: UUID
    actor_type: str
    display_name: str
    tenant_id: UUID
    role: str
    care_unit_ids: list[UUID]
    elder_id: UUID | None = None


class InteractionMetricsResponse(BaseModel):
    """Snapshot of completed response sessions in the Elder's local calendar."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    today_count: int = Field(ge=0)
    last_interaction_at: datetime | None
    local_date: date
    timezone: str
    as_of: datetime


class DailySummaryMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    summary_id: UUID
    status: Literal["DRAFT", "READY", "NEEDS_REVIEW", "PUBLISHED", "STALE", "WITHDRAWN"]
    version: int = Field(ge=1)


class DailySummarySnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    local_date: date
    timezone: str
    as_of: datetime
    summary: DailySummaryMetadataResponse | None


class AuthorizedElderItem(BaseModel):
    """A single elder entry in the authorized-elders listing."""

    model_config = ConfigDict(from_attributes=True)

    elder_id: UUID
    display_name: str
    care_unit_name: str | None = None
    authorization_summary: str | None = None
    interaction_metrics: InteractionMetricsResponse | None = None
    daily_summary: DailySummarySnapshotResponse | None = None
    pending_event_review_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Current CANDIDATE/NEEDS_REVIEW events; null without professional "
            "care_event:read and care_event:review access."
        ),
    )
    open_care_action_count: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Unfinished formal actions (OPEN/IN_PROGRESS/POSTPONED); "
            "null without professional care_action:read access."
        ),
    )


class PaginationMeta(BaseModel):
    """Cursor-based pagination metadata."""

    next_cursor: str | None = None
    has_more: bool
    limit: int = Field(ge=1, le=100)


class AuthorizedEldersResponse(BaseModel):
    """Response schema for GET /api/v1/me/authorized-elders.

    Contains paginated list of elders the actor is authorized to access.
    Wrapped in SuccessEnvelope.data at the handler layer.
    """

    items: list[AuthorizedElderItem]
    page: PaginationMeta
