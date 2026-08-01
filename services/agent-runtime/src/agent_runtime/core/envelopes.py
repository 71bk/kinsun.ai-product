"""Standard response envelopes for the Agent Runtime.

Deliberately mirrors ``services/core-api/app/core/envelopes.py`` field for
field. AGENTS.md 8.3 requires one response shape across the whole repository;
two services that each invent their own "standard" envelope is the failure this
avoids. The JSON Schema counterparts live in ``contracts/schemas/common/``
(ResponseMetaV1, ErrorEnvelopeV1) and are shared, not duplicated.

Response format:
    Success: {"data": T, "meta": {"correlation_id": "...",
                                   "timestamp": "...", "schema_version": "1.0"}}
    Error:   {"error": {"code": "...", "reason_code": "...", "retryable": false, ...}}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata attached to every successful response."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
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
