"""Transactional outbox model for reliable domain event persistence.

The OutboxEvent is written in the same database transaction as domain entity
changes, ensuring atomicity. A separate relay process (out of scope for this
foundation) reads committed entries and publishes them externally.

Maps to `eldercare_ai.outbox_event`, which is richer than a minimal outbox:
the primary key is outbox_event_id, while event_id is a separate UNIQUE column
used as the idempotency key. Delivery state is a status string, not a boolean,
so PUBLISHING and FAILED are distinguishable from "not yet attempted".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import SCHEMA_NAME, Base, pg_enum

#: eldercare_ai.data_classification_enum
DATA_CLASSIFICATION_ENUM = pg_enum(
    "data_classification_enum",
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
    "RESTRICTED",
)


class OutboxEvent(Base):
    """Domain event persisted for reliable relay.

    Inherits from Base (DeclarativeBase), NOT BaseModel — the outbox is
    infrastructure, not a tenant-scoped domain aggregate, and its primary key
    is generated independently of the event's own identity.
    """

    __tablename__ = "outbox_event"

    outbox_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    #: Globally unique domain event id. UNIQUE — used as the idempotency key.
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=func.gen_random_uuid(),
    )
    event_type: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    aggregate_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"),
        nullable=True,
    )
    elder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=True,
    )
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    classification: Mapped[str] = mapped_column(
        DATA_CLASSIFICATION_ENUM,
        nullable=False,
        server_default="RESTRICTED",
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    delivery_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="PENDING",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
