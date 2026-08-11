"""Schemas for elder and family LINE account linking."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateLineLinkChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_token: str = Field(min_length=1, max_length=2048)

    @field_validator("link_token")
    @classmethod
    def reject_invalid_link_token(cls, value: str) -> str:
        if value != value.strip() or any(character.isspace() for character in value):
            raise ValueError("link_token has an invalid shape")
        return value


class LineLinkStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["LINE"] = "LINE"
    linked: bool
    status: Literal["ACTIVE", "UNLINKED"]
    linked_at: datetime | None = None
    can_unlink: bool


class LineLinkChallengeCreatedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    status: Literal["PENDING"] = "PENDING"
    expires_at: datetime
    account_link_url: str = Field(min_length=1, max_length=4096)


class LineLinkChallengeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    status: Literal["PENDING", "REDEEMED", "FAILED", "EXPIRED", "REVOKED"]
    expires_at: datetime
    redeemed_at: datetime | None = None


class LineUnlinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["LINE"] = "LINE"
    linked: Literal[False] = False
    status: Literal["UNLINKED"] = "UNLINKED"
    linked_at: None = None
    can_unlink: Literal[False] = False
