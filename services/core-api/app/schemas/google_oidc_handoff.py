"""Strict schemas for the private Google OIDC handoff endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoogleOidcHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    id_token: str = Field(min_length=1, max_length=16_384)
    expected_nonce: str = Field(min_length=32, max_length=512)
    intent: Literal["ELDER", "FAMILY", "STAFF"]

    @field_validator("id_token")
    @classmethod
    def validate_id_token(cls, value: str) -> str:
        if not value.isascii() or any(character.isspace() for character in value):
            raise ValueError("id_token has an invalid shape")
        return value

    @field_validator("expected_nonce")
    @classmethod
    def validate_expected_nonce(cls, value: str) -> str:
        if (
            value != value.strip()
            or not value.isascii()
            or any(character.isspace() for character in value)
        ):
            raise ValueError("expected_nonce has an invalid shape")
        return value


class AuthenticatedGoogleOidcHandoffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AUTHENTICATED"] = "AUTHENTICATED"
    session_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class PendingGoogleOidcHandoffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PENDING"] = "PENDING"
    pending_token: str
    expires_at: datetime
