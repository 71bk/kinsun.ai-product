"""Strict input/output fields for the 08:00 LINE daily-notification job."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DailyLineNotificationJobRequest(BaseModel):
    """Scheduler input; report content and recipient identifiers are never accepted."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    job_name: Literal["line-daily-family-report"]
    scheduled_for: datetime
    timezone: Literal["Asia/Taipei"]

    @model_validator(mode="after")
    def validate_schedule_boundary(self) -> DailyLineNotificationJobRequest:
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("scheduled_for must include an explicit UTC offset")
        local = self.scheduled_for.astimezone(ZoneInfo(self.timezone))
        if (local.hour, local.minute, local.second, local.microsecond) != (8, 0, 0, 0):
            raise ValueError("scheduled_for must resolve to exactly 08:00:00 Asia/Taipei")
        return self


class NotificationSourcePeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class DailyLineDeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: UUID
    report_id: UUID
    report_version: int = Field(ge=1)
    status: Literal["SENT", "REPLAYED", "FAILED", "SKIPPED"]
    reason_code: str | None = Field(default=None, max_length=80)


class DailyLineNotificationCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: int = Field(ge=0)
    sent: int = Field(ge=0)
    replayed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    failed: int = Field(ge=0)


class DailyLineNotificationJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    job_name: Literal["line-daily-family-report"] = "line-daily-family-report"
    status: Literal["COMPLETED", "PARTIAL_FAILURE", "NO_ELIGIBLE_REPORTS"]
    scheduled_for: datetime
    timezone: Literal["Asia/Taipei"]
    source_period: NotificationSourcePeriod
    counts: DailyLineNotificationCounts
    deliveries: list[DailyLineDeliveryResult] = Field(max_length=500)
