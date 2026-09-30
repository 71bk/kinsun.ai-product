"""Restricted, append-only profile history; never exported as audit metadata."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin


class ElderProfileChange(BaseModel, TenantScopedMixin):
    __tablename__ = "elder_profile_change"
    __pk_name__ = "profile_change_id"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA_NAME}.elder.elder_id", f"{SCHEMA_NAME}.elder.tenant_id"],
            name="fk_profile_change_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "change_type IN ('BASIC_UPDATED','CARE_ENTRY_CREATED',"
            "'CARE_ENTRY_UPDATED','CARE_ENTRY_RETIRED')",
            name="ck_profile_change_type",
        ),
        sa.CheckConstraint("resource_version > 0", name="ck_profile_change_version"),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 200", name="ck_profile_change_reason"
        ),
        sa.Index(
            "ix_profile_change_history", "tenant_id", "elder_id", "created_at", "profile_change_id"
        ),
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    care_profile_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey(
            f"{SCHEMA_NAME}.elder_care_profile_entry.care_profile_entry_id", ondelete="RESTRICT"
        ),
    )
    changed_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    change_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resource_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reason: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
