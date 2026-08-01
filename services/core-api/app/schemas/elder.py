"""Pydantic schemas for Elder API endpoints.

Defines response models for:
- GET /api/v1/elders/{elder_id} → ElderResponse
- GET /api/v1/elders/{elder_id}/access-context → AccessContextResponse

All responses are wrapped in SuccessEnvelope at the handler layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ElderResponse(BaseModel):
    """Response schema for GET /api/v1/elders/{elder_id}.

    Contains basic elder profile information visible to authorized actors.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    elder_id: UUID
    display_name: str
    primary_care_setting: Literal["DAYCARE", "COMMUNITY", "HOME_CARE", "INDEPENDENT"]
    status: Literal["ACTIVE", "INACTIVE", "DECEASED", "DELETED"]


class AccessContextResponse(BaseModel):
    """Response schema for GET /api/v1/elders/{elder_id}/access-context.

    Contains the actor's authorization scope summary for the specified elder.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    purpose: str
    allowed_actions: list[str]
    source_type: str | None = None
    source_summary: str
    expires_at: datetime | None = None
