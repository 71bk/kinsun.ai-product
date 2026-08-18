"""Strict request and response schemas for purpose-based consent."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.consent import ConsentPurpose

ALLOWED_DELETION_SCOPES = {
    "CONVERSATION_SESSION",
    "TRANSCRIPT",
    "AUDIO_OBJECT",
    "CARE_EVENT",
    "DAILY_SUMMARY",
    "MEMORY",
    "FAMILY_REPORT",
    "NOTIFICATION",
    "SECURE_LINK",
    "COMPANION_SIGNAL",
    "PROACTIVE_TRIGGER",
    "GRAPH",
    "SEARCH_INDEX",
    "CACHE",
}


class CreateConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purposes: list[ConsentPurpose] = Field(min_length=1, max_length=7)
    share_scopes: list[str] = Field(default_factory=list, max_length=32)
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    actor_confirmation: bool
    policy_version: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_period_and_confirmation(self) -> CreateConsentRequest:
        if not self.actor_confirmation:
            raise ValueError("actor_confirmation must be true to create a grant")
        if (
            self.effective_at is not None
            and self.expires_at is not None
            and self.expires_at <= self.effective_at
        ):
            raise ValueError("expires_at must be after effective_at")
        if len(set(self.purposes)) != len(self.purposes):
            raise ValueError("purposes must not contain duplicates")
        return self


class RevokeConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=120)
    requested_effective_at: datetime | None = None
    revoke_scope: list[str] = Field(default_factory=list, max_length=32)
    request_deletion: bool = False

    @field_validator("revoke_scope")
    @classmethod
    def validate_revoke_scope(cls, value: list[str]) -> list[str]:
        unsupported = set(value).difference(ALLOWED_DELETION_SCOPES)
        if unsupported:
            raise ValueError("revoke_scope contains an unsupported value")
        return value


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    consent_id: UUID
    purpose_code: ConsentPurpose
    consent_version: int
    status: Literal["PENDING", "GRANTED", "REVOKED", "EXPIRED", "REJECTED"]
    scope: dict
    policy_version: str
    effective_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    affected_capabilities: list[str]
    deletion_request_id: UUID | None = None


class ConsentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ConsentResponse]
