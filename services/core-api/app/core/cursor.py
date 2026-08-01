"""Opaque cursor encoding for tenant-scoped chronological lists."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from uuid import UUID

from app.core.exceptions import ValidationError


def encode_cursor(created_at: datetime, resource_id: UUID) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "resource_id": str(resource_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(payload["created_at"]), UUID(payload["resource_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError(details=[{"field": "cursor", "reason": "cursor is invalid"}]) from exc
