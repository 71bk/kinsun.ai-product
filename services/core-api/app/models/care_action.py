"""Care-action aggregate ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    source_event_provenance: Mapped[list[CareActionEventProvenance]] = relationship(
        back_populates="care_action",
        cascade="save-update, merge",
        lazy="selectin",
        order_by="CareActionEventProvenance.source_order",
    )


class CareActionEventProvenance(BaseModel):
    """Append-only binding to the exact formal Care Event version used at creation."""

    __tablename__ = "care_action_event_provenance"
    __pk_name__ = "care_action_event_provenance_id"
    __table_args__ = (
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 15",
            name="ck_care_action_event_provenance_order",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_care_action_event_provenance_version",
        ),
        sa.CheckConstraint(
            "source_status IN ('VERIFIED','CORRECTED')",
            name="ck_care_action_event_provenance_status",
        ),
        sa.CheckConstraint(
            "snapshot_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_care_action_event_provenance_sha256",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version = 'care-event-provenance.v1'",
            name="ck_care_action_event_provenance_schema",
        ),
        sa.ForeignKeyConstraint(
            ["event_version_id", "event_id", "event_version"],
            [
                f"{SCHEMA_NAME}.care_event_version.event_version_id",
                f"{SCHEMA_NAME}.care_event_version.event_id",
                f"{SCHEMA_NAME}.care_event_version.version",
            ],
            name="fk_care_action_event_provenance_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "care_action_id",
            "source_order",
            name="uq_care_action_event_provenance_order",
        ),
        sa.UniqueConstraint(
            "care_action_id",
            "event_id",
            name="uq_care_action_event_provenance_event",
        ),
    )

    care_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_action.care_action_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    care_action: Mapped[CareAction] = relationship(back_populates="source_event_provenance")
