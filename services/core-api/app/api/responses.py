"""Canonical API response helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.envelopes import ResponseMeta, SuccessEnvelope
from app.middleware.logging import correlation_id_var


def get_correlation_id() -> str:
    return correlation_id_var.get() or str(uuid.uuid4())


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
