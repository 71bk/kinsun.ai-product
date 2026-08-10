"""Family notification preference and delivery ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, time

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base, BaseModel, pg_enum

NOTIFICATION_CHANNEL_ENUM = pg_enum(
    "notification_channel_enum",
    "LINE",
    "EMAIL",
    "IN_APP",
)


class NotificationPreference(BaseModel):
    """One family member's opt-in notification settings for one elder."""

    __tablename__ = "notification_preference"
    __pk_name__ = "preference_id"

    family_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(NOTIFICATION_CHANNEL_ENUM),
        server_default=sa.text("'{}'"),
        nullable=False,
    )
    frequency: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'DAILY'"),
        nullable=False,
    )
    send_time_local: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(
        String(64),
        server_default=sa.text("'Asia/Taipei'"),
        nullable=False,
    )
    quiet_hours: Mapped[dict] = mapped_column(
        JSONB,
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    important_event_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.false(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'ACTIVE'"),
        nullable=False,
    )


class NotificationDelivery(Base):
    """Durable state for one provider delivery attempt sequence."""

    __tablename__ = "notification_delivery"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.family_report.report_id"),
        nullable=False,
    )
    report_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.report_version.report_version_id"),
        nullable=False,
    )
    recipient_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    preference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.notification_preference.preference_id"),
    )
    channel: Mapped[str] = mapped_column(NOTIFICATION_CHANNEL_ENUM, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'PENDING'"),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        server_default=sa.text("0"),
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
