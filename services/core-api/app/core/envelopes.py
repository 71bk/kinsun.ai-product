"""Standard response envelope schemas for the Core API.

Defines the canonical success and error response structures used across
all API endpoints. Every response is wrapped in either a SuccessEnvelope
or an ErrorEnvelope to provide consistent structure for clients.

Response format:
    Success: {"data": T, "meta": {"correlation_id": "...", "timestamp": "..."}}
    Error:   {"error": {"code": "...", "message": "...", "correlation_id": "...", "details": [...]}}
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata attached to every successful response."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    timestamp: datetime
    schema_version: Literal["1.0"] = "1.0"


class SuccessEnvelope(BaseModel, Generic[T]):
    """Standard success response wrapper."""

    model_config = ConfigDict(extra="forbid")

    data: T
    meta: ResponseMeta


class ValidationDetail(BaseModel):
    """A single field-level validation error."""

    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str


class ErrorBody(BaseModel):
    """Structured error information."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    correlation_id: str
    reason_code: str | None = None
    retryable: bool = False
    details: list[ValidationDetail] | None = None


class ErrorEnvelope(BaseModel):
    """Standard error response wrapper."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
