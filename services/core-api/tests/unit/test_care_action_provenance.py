"""Deterministic Care Action source-provenance hashing tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.domain.care_action import care_event_snapshot_sha256

EVENT_ID = UUID("71000000-0000-4000-8000-000000000001")
EVENT_VERSION_ID = UUID("72000000-0000-4000-8000-000000000001")


def _hash(*, payload: dict, event_version: int = 1, source_status: str = "VERIFIED") -> str:
    return care_event_snapshot_sha256(
        event_id=EVENT_ID,
        event_version_id=EVENT_VERSION_ID,
        event_version=event_version,
        event_type="MEAL",
        event_time=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        source_status=source_status,
        structured_payload=payload,
        evidence_text_ref='["evidence:73000000-0000-4000-8000-000000000001"]',
    )


def test_snapshot_hash_is_canonical_across_key_order_and_timezone() -> None:
    first = _hash(payload={"meal": "breakfast", "reported": True})
    reordered = _hash(payload={"reported": True, "meal": "breakfast"})
    offset_time = care_event_snapshot_sha256(
        event_id=EVENT_ID,
        event_version_id=EVENT_VERSION_ID,
        event_version=1,
        event_type="MEAL",
        event_time=datetime(2026, 9, 2, 17, 0, tzinfo=UTC) - timedelta(hours=8),
        source_status="VERIFIED",
        structured_payload={"meal": "breakfast", "reported": True},
        evidence_text_ref='["evidence:73000000-0000-4000-8000-000000000001"]',
    )

    assert first == reordered == offset_time
    assert len(first) == 64
    assert first == first.casefold()


def test_snapshot_hash_changes_with_version_payload_or_formal_status() -> None:
    original = _hash(payload={"meal": "breakfast"})

    assert _hash(payload={"meal": "lunch"}) != original
    assert _hash(payload={"meal": "breakfast"}, event_version=2) != original
    assert _hash(payload={"meal": "breakfast"}, source_status="CORRECTED") != original


def test_snapshot_hash_rejects_invalid_version_and_naive_time() -> None:
    with pytest.raises(ValueError, match="event_version"):
        _hash(payload={}, event_version=0)

    with pytest.raises(ValueError, match="timezone"):
        care_event_snapshot_sha256(
            event_id=EVENT_ID,
            event_version_id=EVENT_VERSION_ID,
            event_version=1,
            event_type="MEAL",
            event_time=datetime(2026, 9, 2, 9, 0),
            source_status="VERIFIED",
            structured_payload={},
            evidence_text_ref=None,
        )
