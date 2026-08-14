"""Strict schemas for Kinsun-owned email authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.services.kinsun_identity_codec import KinsunIdentityCodec


class StartKinsunEmailAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    intent: Literal["ELDER", "FAMILY", "STAFF"]
    display_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        try:
            return KinsunIdentityCodec.normalize_email(value)
        except ValueError:
            raise ValueError("email has an invalid shape") from None


class StartedKinsunEmailAuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["CHALLENGE_CREATED"] = "CHALLENGE_CREATED"
    challenge_token: str
    expires_at: datetime


class CompleteKinsunEmailAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    challenge_token: str = Field(pattern=r"^ke1_[A-Za-z0-9_-]{43}$")
    verification_code: str
    password: SecretStr
    invitation_code: str | None = Field(default=None, min_length=16, max_length=24)

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str) -> str:
        if len(value) != 6 or not value.isdecimal() or not value.isascii():
            raise ValueError("verification_code must contain exactly six ASCII digits")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 12 <= len(password) <= 128 or len(password.encode("utf-8")) > 1024:
            raise ValueError("password must contain between 12 and 128 characters")
        if "\x00" in password:
            raise ValueError("password contains an invalid character")
        return value


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return StartKinsunEmailAuthRequest.validate_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        return CompleteKinsunEmailAuthRequest.validate_password(value)


class CompletedKinsunEmailAuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AUTHENTICATED"] = "AUTHENTICATED"
    session_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
