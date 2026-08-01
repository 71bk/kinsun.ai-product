"""Family-report draft, publication, withdrawal, and read schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    IMPORTANT_EVENT = "IMPORTANT_EVENT"


class FamilyReportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=500)
    source_ids: list[UUID] = Field(min_length=1, max_length=32)


class CreateFamilyReportDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_scope_ids: list[UUID] = Field(min_length=1, max_length=32)
    report_type: ReportType
    period_start: date
    period_end: date
    items: list[FamilyReportItem] = Field(default_factory=list, max_length=64)
    source_summary_ids: list[UUID] = Field(default_factory=list, max_length=32)
    source_event_ids: list[UUID] = Field(default_factory=list, max_length=64)
    data_gap_notice: str | None = Field(default=None, max_length=500)
    sensitive_review_required: bool = True

    @model_validator(mode="after")
    def validate_period_and_sources(self) -> CreateFamilyReportDraftRequest:
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        if not self.source_summary_ids and not self.source_event_ids:
            raise ValueError("a report draft requires source summaries or verified events")
        return self


class PublishFamilyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    safety_review_passed: Literal[True]
    reason_code: str = Field(min_length=1, max_length=120)


class WithdrawFamilyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=120)


class FamilyReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID
    elder_id: UUID
    recipient_scope_ids: list[UUID]
    report_type: ReportType
    period_start: date
    period_end: date
    status: Literal["DRAFT", "NEEDS_REVIEW", "PUBLISHED", "WITHDRAWN", "STALE"]
    items: list[FamilyReportItem]
    data_gap_notice: str | None
    sensitive_review_required: bool
    version: int
    published_at: datetime | None
    withdrawn_at: datetime | None
    updated_at: datetime


class FamilyReportListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FamilyReportResponse]
