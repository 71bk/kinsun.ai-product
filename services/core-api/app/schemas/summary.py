"""Traceable daily-summary schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "MEAL",
        "ACTIVITY",
        "SLEEP",
        "MEDICATION_STATEMENT",
        "SOCIAL",
        "IMPORTANT_EVENT",
    ]
    text: str = Field(min_length=1, max_length=500)
    source_event_ids: list[UUID] = Field(min_length=1, max_length=32)
    data_status: Literal["PRESENT", "NOT_MENTIONED", "INSUFFICIENT"]


class CreateSummaryDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_date: date
    summary_type: Literal["PROFESSIONAL_DAILY"] = "PROFESSIONAL_DAILY"
    items: list[SummaryItem] = Field(default_factory=list, max_length=32)
    missing_fields: list[str] = Field(default_factory=list, max_length=32)
    conflict_flags: list[str] = Field(default_factory=list, max_length=32)
    model_version: str | None = Field(default=None, max_length=160)
    prompt_version: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def require_missing_or_items(self) -> CreateSummaryDraftRequest:
        if not self.items and not self.missing_fields:
            raise ValueError("a summary must contain source-backed items or missing_fields")
        return self


class RebuildSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)


class GenerateSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_date: date


class ReviewSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["VERIFY", "REJECT"]
    reason_code: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_id: UUID
    elder_id: UUID
    summary_date: date
    summary_type: Literal["PROFESSIONAL_DAILY"]
    status: Literal[
        "DRAFT",
        "READY",
        "NEEDS_REVIEW",
        "PUBLISHED",
        "STALE",
        "WITHDRAWN",
    ]
    items: list[SummaryItem]
    missing_fields: list[str]
    conflict_flags: list[str]
    version: int
    generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SummaryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SummaryResponse]


class SummaryReviewResponse(SummaryResponse):
    review_record_id: UUID
