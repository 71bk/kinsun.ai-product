"""Correlation ID propagation.

Takes ``x-correlation-id`` from the request or generates a UUID v4, exposes it
through a ContextVar so the endpoint and the error handlers build the same
envelope value, and echoes it on the response header. Header name and
behaviour match core-api's RequestLoggerMiddleware so a single correlation id
survives across services.

Security: this middleware never reads or logs the request body. Agent input is
elder transcript — Restricted Data under AGENTS.md 4, and must not reach
general logs.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

HEADER_NAME = "x-correlation-id"


def normalize_correlation_id(value: str | None) -> str | None:
    """Accept only the canonical lowercase UUID v4 form used across services."""
    if value is None or len(value) != 36:
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    return value if parsed.version == 4 and str(parsed) == value else None


def resolve_correlation_id(value: str | None) -> str:
    """Return a validated caller ID or an independently generated UUID v4."""
    return normalize_correlation_id(value) or str(uuid.uuid4())


def get_correlation_id() -> str:
    """Return the current correlation id, generating one if unset.

    The error handlers can run before or outside the middleware (for example
    when middleware itself raises), so this must never return an empty string —
    an envelope without a correlation id is unusable for support lookup.
    """
    cid = correlation_id_var.get()
    if not cid:
        cid = str(uuid.uuid4())
        correlation_id_var.set(cid)
    return cid


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind a correlation id to every request and echo it back."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = resolve_correlation_id(request.headers.get(HEADER_NAME))
        correlation_id_var.set(correlation_id)

        response: Response = await call_next(request)
        response.headers[HEADER_NAME] = correlation_id
        return response
