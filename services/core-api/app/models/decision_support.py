"""Versioned, append-only decision-support policy profiles."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base


class DecisionSupportProfile(Base):
    """Minimal policy metadata; never a diagnosis or global trust score."""

    __tablename__ = "decision_support_profile"
    __table_args__ = (
        sa.CheckConstraint(
            "decision_scope = 'MEMORY_CONFIRMATION'",
            name="ck_decision_support_profile_scope",
        ),
        sa.CheckConstraint(
            "data_class IN ('ALL_MEMORY','PREFERENCE','IMPORTANT_RELATIONSHIP',"
            "'ROUTINE','COMMUNICATION_PREFERENCE','PERSONAL_HISTORY')",
            name="ck_decision_support_profile_data_class",
        ),
        sa.CheckConstraint(
            "mode IN ('STANDARD','SUPPORTED','REPRESENTATIVE_REQUIRED')",
            name="ck_decision_support_profile_mode",
        ),
        sa.CheckConstraint(
            "profile_version > 0",
            name="ck_decision_support_profile_version",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_from",
            name="ck_decision_support_profile_effective_window",
        ),
        sa.CheckConstraint(
            "allowed_memory_risks <@ ARRAY['LOW','MEDIUM']::varchar[]",
            name="ck_decision_support_profile_allowed_risks",
        ),
        sa.CheckConstraint(
            "mode <> 'REPRESENTATIVE_REQUIRED' OR cardinality(allowed_memory_risks) = 0",
            name="ck_decision_support_profile_representative_risks",
        ),
        sa.CheckConstraint(
            "supersedes_profile_id IS NULL OR "
            "supersedes_profile_id <> decision_support_profile_id",
            name="ck_decision_support_profile_not_self_superseding",
        ),
        sa.UniqueConstraint(
            "decision_support_profile_id",
            "profile_version",
            name="uq_decision_support_profile_id_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "elder_id",
            "decision_scope",
            "data_class",
            "profile_version",
            name="uq_decision_support_profile_scope_version",
        ),
        sa.Index(
            "ix_decision_support_profile_resolution",
            "tenant_id",
            "elder_id",
            "decision_scope",
            "data_class",
            "profile_version",
        ),
    )

    decision_support_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"),
        nullable=False,
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    decision_scope: Mapped[str] = mapped_column(String(48), nullable=False)
    data_class: Mapped[str] = mapped_column(String(48), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_memory_risks: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)),
        server_default=sa.text("ARRAY['LOW','MEDIUM']::varchar[]"),
        nullable=False,
    )
    basis_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.decision_support_profile.decision_support_profile_id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
