"""Institution service enrollment for an Elder care subject."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin


class ElderEnrollment(BaseModel, TenantScopedMixin):
    """A time-bounded Organization service relationship, independent of login."""

    __tablename__ = "elder_enrollment"
    __pk_name__ = "enrollment_id"
    __table_args__ = (
        sa.CheckConstraint(
            "enrollment_type IN ('ORGANIZATION')",
            name="ck_elder_enrollment_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','ACTIVE','SUSPENDED','ENDED')",
            name="ck_elder_enrollment_status",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_elder_enrollment_window",
        ),
        sa.CheckConstraint(
            "(status = 'ENDED' AND ended_at IS NOT NULL AND ended_reason IS NOT NULL) "
            "OR (status <> 'ENDED' AND ended_at IS NULL)",
            name="ck_elder_enrollment_end_state",
        ),
        sa.UniqueConstraint(
            "enrollment_id",
            "elder_id",
            "tenant_id",
            name="uq_elder_enrollment_scope",
        ),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA_NAME}.elder.elder_id", f"{SCHEMA_NAME}.elder.tenant_id"],
            name="fk_elder_enrollment_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.Index(
            "ix_elder_enrollment_active_lookup",
            "tenant_id",
            "elder_id",
            "status",
            "valid_from",
            "valid_until",
        ),
    )

    elder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    care_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_unit.care_unit_id", ondelete="RESTRICT"),
    )
    enrollment_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=sa.text("'ORGANIZATION'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa.text("'ACTIVE'")
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_reason: Mapped[str | None] = mapped_column(String(120))
    created_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
