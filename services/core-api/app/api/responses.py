"""Canonical API response helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

from app.core.correlation import get_correlation_id
from app.core.envelopes import ErrorBody, ErrorEnvelope, ResponseMeta, SuccessEnvelope


def success(data: Any) -> dict:
    """Build the single supported success envelope."""
    envelope = SuccessEnvelope[Any](
        data=data,
        meta=ResponseMeta(
            correlation_id=get_correlation_id(),
            timestamp=datetime.now(UTC),
        ),
    )
    return envelope.model_dump(mode="json")


def authentication_rejected() -> JSONResponse:
    """Return the canonical generic 401 while allowing the request transaction to commit.

    Password and verification-code failures update bounded attempt/lockout state. Raising a
    domain exception would make ``get_db_session`` roll that state back, so these authentication
    endpoints return the shared envelope explicitly after the service records the rejection.
    """
    correlation_id = get_correlation_id()
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code="authentication_required",
            message="Authentication required.",
            correlation_id=correlation_id,
            reason_code="AUTHENTICATION_FAILED",
            retryable=False,
            details=None,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        content=envelope.model_dump(mode="json"),
    )
