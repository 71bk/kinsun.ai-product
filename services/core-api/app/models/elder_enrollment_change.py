"""Restricted, immutable enrollment transition history."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin


class ElderEnrollmentChange(BaseModel, TenantScopedMixin):
    __tablename__ = "elder_enrollment_change"
    __pk_name__ = "enrollment_change_id"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["enrollment_id", "elder_id", "tenant_id"],
            [
                f"{SCHEMA_NAME}.elder_enrollment.{column}"
                for column in ("enrollment_id", "elder_id", "tenant_id")
            ],
            name="fk_enrollment_change_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "from_status IN ('ACTIVE','SUSPENDED')", name="ck_enrollment_change_from"
        ),
        sa.CheckConstraint(
            "to_status IN ('ACTIVE','SUSPENDED','ENDED')", name="ck_enrollment_change_to"
        ),
        sa.CheckConstraint("from_status <> to_status", name="ck_enrollment_change_transition"),
        sa.CheckConstraint("version > 1", name="ck_enrollment_change_version"),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 120", name="ck_enrollment_change_reason"
        ),
        sa.UniqueConstraint("enrollment_id", "version", name="uq_enrollment_change_version"),
        sa.Index(
            "ix_enrollment_change_history",
            "tenant_id",
            "enrollment_id",
            "created_at",
            "enrollment_change_id",
        ),
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    elder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    changed_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reason: Mapped[str] = mapped_column(sa.String(120), nullable=False)
