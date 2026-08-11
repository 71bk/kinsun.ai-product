"""Provider-neutral, server-owned application session persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, VersionedMixin


class AppSession(BaseModel, VersionedMixin):
    """One revocable opaque browser session for an authenticated Core actor.

    The raw bearer value is never persisted. ``token_digest`` is the lowercase
    SHA-256 digest of a random token with at least 256 bits of entropy.
    Authorization data is deliberately absent: actor, membership, tenant and
    status remain Core database state and must be resolved for each request.
    """

    __tablename__ = "app_session"
    __pk_name__ = "app_session_id"
    __table_args__ = (
        sa.CheckConstraint(
            "token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_app_session_token_digest",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','REVOKED')",
            name="ck_app_session_status",
        ),
        sa.CheckConstraint(
            "last_seen_at >= authenticated_at",
            name="ck_app_session_last_seen",
        ),
        sa.CheckConstraint(
            "idle_expires_at > last_seen_at",
            name="ck_app_session_idle_expiry",
        ),
        sa.CheckConstraint(
            "absolute_expires_at >= idle_expires_at",
            name="ck_app_session_absolute_expiry",
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND revoked_at IS NULL) OR "
            "(status = 'REVOKED' AND revoked_at IS NOT NULL "
            "AND revoked_at >= authenticated_at)",
            name="ck_app_session_revocation",
        ),
        sa.CheckConstraint("version > 0", name="ck_app_session_version"),
        sa.UniqueConstraint("token_digest", name="uq_app_session_token_digest"),
        sa.ForeignKeyConstraint(
            ["external_identity_id", "actor_id"],
            [
                f"{SCHEMA_NAME}.external_identity.external_identity_id",
                f"{SCHEMA_NAME}.external_identity.actor_id",
            ],
            name="fk_app_session_external_identity_actor",
            ondelete="RESTRICT",
        ),
        sa.Index(
            "idx_app_session_actor_status",
            "actor_id",
            "status",
            "absolute_expires_at",
        ),
        sa.Index(
            "idx_app_session_expiry",
            "status",
            "idle_expires_at",
            "absolute_expires_at",
        ),
    )

    token_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'ACTIVE'"),
    )
    authenticated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
