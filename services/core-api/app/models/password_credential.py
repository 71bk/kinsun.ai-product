"""Kinsun-owned Argon2id password credential persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, VersionedMixin


class PasswordCredential(BaseModel, VersionedMixin):
    """One current password authenticator owned by one login principal."""

    __tablename__ = "password_credential"
    __pk_name__ = "password_credential_id"
    __table_args__ = (
        sa.CheckConstraint("algorithm = 'ARGON2ID'", name="ck_password_credential_algorithm"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','LOCKED','REVOKED')",
            name="ck_password_credential_status",
        ),
        sa.CheckConstraint(
            "parameter_version > 0",
            name="ck_password_credential_parameter_version",
        ),
        sa.CheckConstraint(
            "failed_attempt_count >= 0 AND failed_attempt_count <= 20",
            name="ck_password_credential_failed_attempts",
        ),
        sa.CheckConstraint(
            "(status = 'LOCKED' AND locked_until IS NOT NULL) OR "
            "(status <> 'LOCKED' AND locked_until IS NULL)",
            name="ck_password_credential_lock_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_password_credential_version"),
        sa.UniqueConstraint("actor_id", name="uq_password_credential_actor"),
        sa.Index("idx_password_credential_status_lock", "status", "locked_until"),
    )

    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'ARGON2ID'"),
    )
    parameter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'ACTIVE'"),
    )
    failed_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
