"""Actor-owned, daily-only LINE preferences; no provider subject or credential."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class UpdateFamilyLineNotificationPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_enabled: StrictBool
    expected_version: int = Field(ge=0, strict=True)


class FamilyLineNotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    elder_id: UUID
    preference_id: UUID | None
    line_enabled: bool
    version: int = Field(ge=0)
    frequency: Literal["DAILY"] = "DAILY"
    send_time_local: Literal["08:00"] = "08:00"
    timezone: Literal["Asia/Taipei"] = "Asia/Taipei"
    line_status: Literal["UNLINKED", "LINKED", "RELINK_REQUIRED"]
    availability: Literal[
        "READY", "LINE_LINK_REQUIRED", "SERVICE_UNAVAILABLE", "UNSUPPORTED_SCHEDULE"
    ]
    line_link_available: bool
    can_enable: bool
    updated_at: datetime | None
