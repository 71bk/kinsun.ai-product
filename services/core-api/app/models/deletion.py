"""Consent-linked deletion workflow and replay-prevention models."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base, BaseModel


class DeletionRequest(BaseModel):
    __tablename__ = "deletion_request"
    __pk_name__ = "deletion_request_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    requested_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.consent_grant.consent_id"),
    )
    scope: Mapped[list[str]] = mapped_column(ARRAY(String()), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'REQUESTED'"),
        nullable=False,
    )
    reason_code: Mapped[str | None] = mapped_column(String(120))
    policy_version: Mapped[str | None] = mapped_column(String(64))
    legal_hold_status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'NOT_EVALUATED'"),
        nullable=False,
    )
    retention_basis: Mapped[str | None] = mapped_column(String(120))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletionJobItem(Base):
    __tablename__ = "deletion_job_item"

    deletion_job_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    deletion_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.deletion_request.deletion_request_id"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    system_of_record: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'PENDING'"),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(120))
    verification_code: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )


class DeletionTombstone(Base):
    """Minimal marker that prevents deleted content from being rebuilt."""

    __tablename__ = "deletion_tombstone"

    deletion_tombstone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id", ondelete="RESTRICT"),
        nullable=False,
    )
    deletion_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{SCHEMA_NAME}.deletion_request.deletion_request_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    subject_ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    retention_basis: Mapped[str] = mapped_column(String(120), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.CheckConstraint(
            "subject_ref_hash ~ '^[0-9a-f]{64}$'",
            name="ck_deletion_tombstone_subject_hash",
        ),
        sa.CheckConstraint(
            "resource_id_hash ~ '^[0-9a-f]{64}$'",
            name="ck_deletion_tombstone_resource_hash",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id_hash",
            name="uq_deletion_tombstone_resource",
        ),
        sa.Index(
            "ix_deletion_tombstone_subject_resource",
            "tenant_id",
            "subject_ref_hash",
            "resource_type",
        ),
    )
