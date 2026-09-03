"""Deterministic Care Action source-event provenance."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

CARE_EVENT_PROVENANCE_SCHEMA_VERSION = "care-event-provenance.v1"


def care_event_snapshot_sha256(
    *,
    event_id: UUID,
    event_version_id: UUID,
    event_version: int,
    event_type: str,
    event_time: datetime | None,
    source_status: str,
    structured_payload: dict[str, Any],
    evidence_text_ref: str | None,
) -> str:
    """Hash the exact formal Care Event snapshot used to create a Care Action."""
    if event_version < 1:
        raise ValueError("event_version must be positive")
    canonical = json.dumps(
        {
            "event_id": str(event_id),
            "event_time": _canonical_datetime(event_time),
            "event_type": event_type,
            "event_version": event_version,
            "event_version_id": str(event_version_id),
            "evidence_text_ref": evidence_text_ref,
            "source_status": source_status,
            "structured_payload": structured_payload,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("event_time must include a timezone offset")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
