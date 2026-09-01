"""Strict contracts for accountless Elder onboarding and tablet handoff."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CareProfileCategory = Literal[
    "HEALTH_CONDITION",
    "MEDICATION",
    "ALLERGY",
    "CARE_PRECAUTION",
]
LanguageCode = Literal["ZH_TW", "NAN_TW", "HAK_TW", "EN_US", "MIXED", "UNKNOWN"]
PrimaryCareSetting = Literal["DAYCARE", "COMMUNITY", "HOME_CARE", "INDEPENDENT"]
AcknowledgementStatus = Literal["REQUIRED", "ACKNOWLEDGED"]
AcknowledgementMethod = Literal[
    "ACTOR_CONFIRMATION",
    "ASSISTED_TABLET_ACKNOWLEDGEMENT",
]


class CareProfileEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: CareProfileCategory
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized


class CreateAccountlessElderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=120)
    preferred_name: str | None = Field(default=None, max_length=80)
    preferred_language: LanguageCode = "ZH_TW"
    primary_care_setting: PrimaryCareSetting = "DAYCARE"
    care_unit_id: UUID
    response_length_preference: Literal["SHORT", "STANDARD", "DETAILED"] = "STANDARD"
    timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)
    care_profile: list[CareProfileEntryInput] = Field(default_factory=list, max_length=20)

    @field_validator("display_name", "timezone")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("preferred_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def reject_duplicate_profile_entries(self) -> CreateAccountlessElderRequest:
        keys = [(entry.category, entry.content.casefold()) for entry in self.care_profile]
        if len(set(keys)) != len(keys):
            raise ValueError("care_profile entries must not contain duplicates")
        return self


class CareProfileEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    care_profile_entry_id: UUID
    category: CareProfileCategory
    content: str
    source_type: Literal["STAFF_RECORDED"]
    verification_status: Literal["RECORDED", "VERIFIED", "DISPUTED", "RETIRED"]
    version: int = Field(ge=1)


class AccountlessElderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elder_id: UUID
    actor_id: None
    enrollment_id: UUID
    relationship_id: UUID
    display_name: str
    preferred_name: str | None
    preferred_language: LanguageCode
    primary_care_setting: PrimaryCareSetting
    care_unit_id: UUID
    care_profile: list[CareProfileEntryResponse]


class IssueAssistedSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)


class IssuedAssistedSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assisted_session_id: UUID
    elder_id: UUID
    pairing_token: str = Field(pattern=r"^ep1_[A-Za-z0-9_-]{43}$")
    pairing_expires_at: datetime
    absolute_expires_at: datetime


class ExchangeAssistedSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_token: str = Field(pattern=r"^ep1_[A-Za-z0-9_-]{43}$")


class ActivatedAssistedSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assisted_session_id: UUID
    elder_id: UUID
    display_name: str
    preferred_name: str | None
    session_token: str = Field(pattern=r"^es1_[A-Za-z0-9_-]{43}$")
    idle_expires_at: datetime
    absolute_expires_at: datetime


class AcknowledgeFirstUseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged: Literal[True]


class FirstUseAcknowledgementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AcknowledgementStatus
    policy_version: str = Field(min_length=1, max_length=40)
    consent_version: int | None = Field(default=None, ge=1)
    acknowledged_at: datetime | None = None
    confirmation_method: AcknowledgementMethod | None = None

    @model_validator(mode="after")
    def validate_status_evidence(self) -> FirstUseAcknowledgementResponse:
        evidence = (
            self.consent_version,
            self.acknowledged_at,
            self.confirmation_method,
        )
        if self.status == "ACKNOWLEDGED" and any(value is None for value in evidence):
            raise ValueError("ACKNOWLEDGED status requires acknowledgement evidence")
        if self.status == "REQUIRED" and any(value is not None for value in evidence):
            raise ValueError("REQUIRED status must not include acknowledgement evidence")
        return self


class CurrentAssistedSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assisted_session_id: UUID
    elder_id: UUID
    display_name: str
    preferred_name: str | None
    status: Literal["ACTIVE"]
    idle_expires_at: datetime
    absolute_expires_at: datetime
    first_use_acknowledgement: FirstUseAcknowledgementResponse


class AssistedCompanionTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(min_length=1, max_length=4000)

    @field_validator("input_text")
    @classmethod
    def reject_blank_input(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("input_text must not be blank")
        return value.strip()


class EndAssistedSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ENDED"] = "ENDED"
