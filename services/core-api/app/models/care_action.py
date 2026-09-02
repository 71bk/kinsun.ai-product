"""Care-action aggregate ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    SCHEMA_NAME,
    BaseModel,
    OptimisticConcurrencyMixin,
    TenantScopedMixin,
    VersionedMixin,
)


class CareAction(
    BaseModel,
    TenantScopedMixin,
    VersionedMixin,
    OptimisticConcurrencyMixin,
):
    """A professional-confirmed follow-up task for one authorized Elder."""

    __tablename__ = "care_action"
    __pk_name__ = "care_action_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    trigger_reason: Mapped[str | None] = mapped_column(Text)
    related_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        server_default=sa.text("'{}'"),
        nullable=False,
    )
    assignee_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str] = mapped_column(
        String(16),
        server_default=sa.text("'MEDIUM'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'OPEN'"),
        nullable=False,
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    created_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
