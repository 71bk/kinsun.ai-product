"""Strict Core Tool request/result envelope."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.restricted_keys import contains_restricted_key

RESTRICTED_PARAMETER_KEYS = {
    "audio",
    "audio_uri",
    "full_prompt",
    "prompt",
    "secret",
    "token",
    "transcript",
    "transcript_text",
}


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: UUID
    agent_run_id: UUID
    tool_name: str = Field(min_length=1, max_length=120)
    tool_version: str = Field(pattern=r"^1\.", max_length=40)
    elder_id: UUID
    purpose: str = Field(min_length=1, max_length=64)
    consent_version: int = Field(ge=1)
    policy_version: str = Field(min_length=1, max_length=80)
    request_id: str = Field(min_length=1, max_length=80)
    idempotency_key: str | None = Field(default=None, max_length=160)
    expected_resource_version: int | None = Field(default=None, ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def reject_restricted_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        if contains_restricted_key(value, RESTRICTED_PARAMETER_KEYS):
            raise ValueError("parameters contain a restricted field")
        return value


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_status: Literal["SUCCESS", "NO_DATA", "BLOCKED", "FAILED"]
    data: Any = None
    resource_id: UUID | None = None
    resource_version: int | None = None
    source_refs: list[UUID] = Field(default_factory=list)
    reason_code: str | None = None
    retryable: bool = False
    redactions: list[str] = Field(default_factory=list)
    trace_id: str
