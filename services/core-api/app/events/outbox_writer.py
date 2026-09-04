"""Transactional outbox writer for reliable domain event persistence.

Provides the write-path of the transactional outbox pattern. Events are
written in the same database transaction as domain entity changes, ensuring
atomicity. The leased outbox worker reads committed entries and publishes them
through the configured provider-neutral adapter.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.restricted_keys import contains_restricted_key
from app.models.outbox import OutboxEvent

MAX_PAYLOAD_BYTES = 256 * 1024  # 256 KB
RESTRICTED_PAYLOAD_KEYS = {
    "audio",
    "audio_uri",
    "full_prompt",
    "prompt",
    "secret",
    "token",
    "transcript",
    "transcript_text",
}


async def write_outbox_entry(
    session: AsyncSession,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    tenant_id: uuid.UUID,
    payload: dict,
    trace_id: str,
    aggregate_version: int = 1,
    event_id: uuid.UUID | None = None,
    *,
    elder_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    purpose: str | None = None,
    consent_version: int | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    classification: str = "RESTRICTED",
) -> None:
    """Write an event to the outbox within the caller's transaction.

    This function operates within the caller's existing session/transaction.
    The outbox entry is committed or rolled back together with the caller's
    domain entity changes.

    aggregate_type and trace_id are required because the baseline declares them
    NOT NULL: an event that cannot be traced back to its aggregate and request
    is not auditable (AGENTS.md section 8).

    Args:
        session: The async SQLAlchemy session (caller's transaction).
        event_type: A non-empty string identifying the event type.
        aggregate_type: The aggregate kind that produced the event, e.g. "Elder".
        aggregate_id: UUID of the aggregate that produced the event.
        tenant_id: UUID of the tenant owning this event.
        payload: Dictionary payload to persist as JSON (max 256 KB).
        trace_id: Cross-service trace identifier for this event.
        aggregate_version: Aggregate version at the time of the event (> 0).
        event_id: Optional UUID for idempotency. Generated if not provided.

    Raises:
        ValidationError: If any required field is invalid or payload exceeds
            the 256 KB size limit.
    """
    if event_id is None:
        event_id = uuid.uuid4()

    # Validate required fields
    errors: list[dict] = []

    if not event_type or not isinstance(event_type, str):
        errors.append({"field": "event_type", "reason": "event_type must be a non-empty string"})

    if not aggregate_type or not isinstance(aggregate_type, str):
        errors.append(
            {"field": "aggregate_type", "reason": "aggregate_type must be a non-empty string"}
        )

    if not isinstance(aggregate_id, uuid.UUID):
        errors.append({"field": "aggregate_id", "reason": "aggregate_id must be a valid UUID"})

    if not trace_id or not isinstance(trace_id, str):
        errors.append({"field": "trace_id", "reason": "trace_id must be a non-empty string"})

    if not isinstance(aggregate_version, int) or aggregate_version < 1:
        errors.append(
            {"field": "aggregate_version", "reason": "aggregate_version must be an integer >= 1"}
        )

    if not isinstance(tenant_id, uuid.UUID):
        errors.append({"field": "tenant_id", "reason": "tenant_id must be a valid UUID"})

    if elder_id is not None and not isinstance(elder_id, uuid.UUID):
        errors.append({"field": "elder_id", "reason": "elder_id must be a valid UUID"})

    if actor_id is not None and not isinstance(actor_id, uuid.UUID):
        errors.append({"field": "actor_id", "reason": "actor_id must be a valid UUID"})

    if consent_version is not None and (
        not isinstance(consent_version, int) or consent_version < 1
    ):
        errors.append(
            {
                "field": "consent_version",
                "reason": "consent_version must be an integer >= 1",
            }
        )

    if classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        errors.append(
            {
                "field": "classification",
                "reason": "classification is not an allowed data classification",
            }
        )

    if payload is None:
        errors.append({"field": "payload", "reason": "payload must not be None"})
    elif not isinstance(payload, dict):
        errors.append({"field": "payload", "reason": "payload must be an object"})
    elif contains_restricted_key(payload, RESTRICTED_PAYLOAD_KEYS):
        errors.append({"field": "payload", "reason": "payload contains a restricted field"})

    if errors:
        raise ValidationError(details=errors)

    # Validate payload size
    try:
        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValidationError(
            details=[
                {
                    "field": "payload",
                    "reason": "payload must be valid finite UTF-8 JSON",
                }
            ]
        ) from exc
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise ValidationError(
            details=[
                {
                    "field": "payload",
                    "reason": (
                        f"Payload exceeds maximum size of {MAX_PAYLOAD_BYTES} bytes "
                        f"(actual: {len(payload_bytes)} bytes)"
                    ),
                }
            ]
        )

    # INSERT ... ON CONFLICT DO NOTHING for idempotent writes
    stmt = (
        insert(OutboxEvent)
        .values(
            event_id=event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=purpose,
            consent_version=consent_version,
            trace_id=trace_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
            classification=classification,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )

    await session.execute(stmt)
