"""Short-lived, accountless Elder tablet handoff session."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, VersionedMixin


class AssistedElderSession(BaseModel, TenantScopedMixin, VersionedMixin):
    """A revocable tablet capability retaining the real worker initiator."""

    __tablename__ = "assisted_elder_session"
    __pk_name__ = "assisted_session_id"
    __table_args__ = (
        sa.CheckConstraint(
            "pairing_token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_assisted_elder_session_pairing_digest",
        ),
        sa.CheckConstraint(
            "session_token_digest IS NULL OR session_token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_assisted_elder_session_token_digest",
        ),
        sa.CheckConstraint(
            "status IN ('PAIRING','ACTIVE','ENDED','EXPIRED')",
            name="ck_assisted_elder_session_status",
        ),
        sa.CheckConstraint(
            "initiator_mode = 'STAFF_ASSISTED'",
            name="ck_assisted_elder_session_mode",
        ),
        sa.CheckConstraint(
            "authorization_source_type IN ('RELATIONSHIP','ASSIGNMENT')",
            name="ck_assisted_elder_session_authorization_source",
        ),
        sa.CheckConstraint(
            "pairing_expires_at > created_at AND absolute_expires_at > created_at",
            name="ck_assisted_elder_session_expiry",
        ),
        sa.CheckConstraint(
            "idle_expires_at IS NULL OR idle_expires_at <= absolute_expires_at",
            name="ck_assisted_elder_session_idle_expiry",
        ),
        sa.CheckConstraint(
            "(status = 'PAIRING' AND session_token_digest IS NULL "
            "AND activated_at IS NULL AND last_seen_at IS NULL "
            "AND idle_expires_at IS NULL AND ended_at IS NULL) OR "
            "(status = 'ACTIVE' AND session_token_digest IS NOT NULL "
            "AND activated_at IS NOT NULL AND last_seen_at IS NOT NULL "
            "AND idle_expires_at IS NOT NULL AND ended_at IS NULL) OR "
            "(status IN ('ENDED','EXPIRED') AND ended_at IS NOT NULL)",
            name="ck_assisted_elder_session_state_shape",
        ),
        sa.CheckConstraint("version > 0", name="ck_assisted_elder_session_version"),
        sa.UniqueConstraint(
            "pairing_token_digest", name="uq_assisted_elder_session_pairing_digest"
        ),
        sa.UniqueConstraint(
            "session_token_digest", name="uq_assisted_elder_session_token_digest"
        ),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA_NAME}.elder.elder_id", f"{SCHEMA_NAME}.elder.tenant_id"],
            name="fk_assisted_elder_session_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "elder_id", "tenant_id"],
            [
                f"{SCHEMA_NAME}.elder_enrollment.enrollment_id",
                f"{SCHEMA_NAME}.elder_enrollment.elder_id",
                f"{SCHEMA_NAME}.elder_enrollment.tenant_id",
            ],
            name="fk_assisted_elder_session_enrollment_scope",
            ondelete="RESTRICT",
        ),
        sa.Index(
            "ix_assisted_elder_session_active",
            "tenant_id",
            "elder_id",
            "status",
            "absolute_expires_at",
        ),
        sa.Index(
            "ix_assisted_elder_session_initiator",
            "initiated_by_actor_id",
            "status",
            "absolute_expires_at",
        ),
    )

    elder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    initiated_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    initiator_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa.text("'STAFF_ASSISTED'")
    )
    authorization_source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    authorization_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pairing_token_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    session_token_digest: Mapped[str | None] = mapped_column(sa.CHAR(64))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sa.text("'PAIRING'")
    )
    pairing_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
