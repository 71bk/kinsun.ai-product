"""Provenance-preserving Care Profile entries, separate from AI Memory."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, VersionedMixin


class ElderCareProfileEntry(BaseModel, TenantScopedMixin, VersionedMixin):
    """One bounded care fact whose origin and verification state remain explicit."""

    __tablename__ = "elder_care_profile_entry"
    __pk_name__ = "care_profile_entry_id"
    __table_args__ = (
        sa.CheckConstraint(
            "category IN ('HEALTH_CONDITION','MEDICATION','ALLERGY','CARE_PRECAUTION')",
            name="ck_elder_care_profile_category",
        ),
        sa.CheckConstraint(
            "source_type IN ('STAFF_RECORDED','ELDER_REPORTED',"
            "'LEGAL_REPRESENTATIVE_REPORTED','CLINICAL_DOCUMENT')",
            name="ck_elder_care_profile_source_type",
        ),
        sa.CheckConstraint(
            "verification_status IN ('RECORDED','VERIFIED','DISPUTED','RETIRED')",
            name="ck_elder_care_profile_verification",
        ),
        sa.CheckConstraint(
            "length(btrim(content)) BETWEEN 1 AND 500",
            name="ck_elder_care_profile_content",
        ),
        sa.CheckConstraint(
            "(verification_status = 'RETIRED' AND retired_at IS NOT NULL) "
            "OR (verification_status <> 'RETIRED' AND retired_at IS NULL)",
            name="ck_elder_care_profile_retired_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_elder_care_profile_version"),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA_NAME}.elder.elder_id", f"{SCHEMA_NAME}.elder.tenant_id"],
            name="fk_elder_care_profile_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.Index(
            "ix_elder_care_profile_context",
            "tenant_id",
            "elder_id",
            "verification_status",
            "created_at",
        ),
    )

    elder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(48), nullable=False, server_default=sa.text("'STAFF_RECORDED'")
    )
    source_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa.text("'RECORDED'")
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
