"""Strict schemas for the private LINE OIDC handoff endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LineOidcHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    id_token: str = Field(min_length=1, max_length=16_384)
    expected_nonce: str = Field(min_length=32, max_length=512)
    intent: Literal["ELDER", "FAMILY", "STAFF"]

    @field_validator("id_token", "expected_nonce")
    @classmethod
    def validate_ascii_credential(cls, value: str) -> str:
        if (
            value != value.strip()
            or not value.isascii()
            or any(character.isspace() for character in value)
        ):
            raise ValueError("credential has an invalid shape")
        return value


class AuthenticatedLineOidcHandoffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AUTHENTICATED"] = "AUTHENTICATED"
    session_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class PendingLineOidcHandoffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PENDING"] = "PENDING"
    pending_token: str
    expires_at: datetime


class CompleteLineOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pending_token: str = Field(pattern=r"^kp1_[A-Za-z0-9_-]{43}$")
    invitation_code: str | None = Field(default=None, min_length=16, max_length=24)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class CompletedLineOnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ACTIVE", "REDEEMED"]
    intent: Literal["ELDER", "FAMILY"]
    actor_id: UUID
    tenant_id: UUID
    elder_id: UUID
    session_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class LineIdentityMethodStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    google_linked: bool
    line_linked: bool
    recently_authenticated: bool


class LinkLineIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    id_token: str = Field(min_length=1, max_length=16_384)
    expected_nonce: str = Field(min_length=32, max_length=512)

    @field_validator("id_token", "expected_nonce")
    @classmethod
    def validate_ascii_credential(cls, value: str) -> str:
        if (
            value != value.strip()
            or not value.isascii()
            or any(character.isspace() for character in value)
        ):
            raise ValueError("credential has an invalid shape")
        return value


class LinkedLineIdentityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["LINKED", "ALREADY_LINKED"]


class LineAccountMergeRequiredResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["MERGE_REQUIRED"] = "MERGE_REQUIRED"
    merge_token: str = Field(pattern=r"^km1_[A-Za-z0-9_-]{43}$")
    expires_at: datetime


class LineAccountManualReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["MANUAL_REVIEW_REQUIRED"] = "MANUAL_REVIEW_REQUIRED"


class ConfirmLineAccountMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merge_token: str = Field(pattern=r"^km1_[A-Za-z0-9_-]{43}$")


class MergedLineAccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["MERGED"] = "MERGED"
    session_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
