"""Strict staff profile commands and restricted read models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["ZH_TW", "NAN_TW", "HAK_TW", "EN_US", "MIXED", "UNKNOWN"]
Category = Literal["HEALTH_CONDITION", "MEDICATION", "ALLERGY", "CARE_PRECAUTION"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class BasicProfileFields(StrictModel):
    display_name: str = Field(min_length=1, max_length=120)
    preferred_name: str | None = Field(min_length=1, max_length=80)
    preferred_language: Language


class ElderProfileResponse(BasicProfileFields):
    elder_id: UUID
    profile_version: int = Field(ge=1)


class UpdateElderProfileRequest(BasicProfileFields):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=200)


class CreateCareProfileRequest(StrictModel):
    category: Category
    content: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=200)


class UpdateCareProfileRequest(CreateCareProfileRequest):
    expected_version: int = Field(ge=1)


class RetireCareProfileRequest(StrictModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=200)


class CareProfileResponse(StrictModel):
    care_profile_entry_id: UUID
    elder_id: UUID
    category: Category
    content: str = Field(min_length=1, max_length=500)
    source_type: Literal[
        "STAFF_RECORDED", "ELDER_REPORTED", "LEGAL_REPRESENTATIVE_REPORTED", "CLINICAL_DOCUMENT"
    ]
    source_actor_id: UUID
    verification_status: Literal["RECORDED", "VERIFIED", "DISPUTED", "RETIRED"]
    effective_from: datetime
    retired_at: datetime | None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class CareProfileListResponse(StrictModel):
    items: list[CareProfileResponse]
    next_cursor: str | None
    has_more: bool


class ProfileChangeResponse(StrictModel):
    profile_change_id: UUID
    elder_id: UUID
    care_profile_entry_id: UUID | None
    changed_by_actor_id: UUID
    changed_by_name: str
    change_type: Literal[
        "BASIC_UPDATED", "CARE_ENTRY_CREATED", "CARE_ENTRY_UPDATED", "CARE_ENTRY_RETIRED"
    ]
    resource_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=200)
    before_data: ElderProfileResponse | CareProfileResponse | None
    after_data: ElderProfileResponse | CareProfileResponse
    created_at: datetime


class ProfileHistoryResponse(StrictModel):
    items: list[ProfileChangeResponse]
    next_cursor: str | None
    has_more: bool
