"""Request correlation context shared across application layers."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


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
    """Return the request correlation ID, creating a stable fallback if absent."""
    correlation_id = correlation_id_var.get()
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
        correlation_id_var.set(correlation_id)
    return correlation_id
