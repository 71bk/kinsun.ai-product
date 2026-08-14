"""Strict schemas for Kinsun-owned email authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StartKinsunEmailAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    intent: Literal["ELDER", "FAMILY", "STAFF"]
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class StartedKinsunEmailAuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["CHALLENGE_CREATED"] = "CHALLENGE_CREATED"
    challenge_token: str
    expires_at: datetime


class CompleteKinsunEmailAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    challenge_token: str = Field(pattern=r"^ke1_[A-Za-z0-9_-]{43}$")
    verification_code: str
    invitation_code: str | None = Field(default=None, min_length=16, max_length=24)

    @field_validator("verification_code")
    @classmethod
    def validate_verification_code(cls, value: str) -> str:
        if len(value) != 6 or not value.isdecimal() or not value.isascii():
            raise ValueError("verification_code must contain exactly six ASCII digits")
        return value


class CompletedKinsunEmailAuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AUTHENTICATED"] = "AUTHENTICATED"
    session_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
