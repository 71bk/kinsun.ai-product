"""Explicit cross-provider account consolidation persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, VersionedMixin


class AccountMergeRequest(BaseModel, VersionedMixin):
    """One bounded request proving control of two already-created actors."""

    __tablename__ = "account_merge_request"
    __pk_name__ = "account_merge_request_id"
    __table_args__ = (
        sa.CheckConstraint(
            "source_actor_id <> target_actor_id",
            name="ck_account_merge_distinct_actors",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_CONFIRMATION','PENDING_REVIEW','COMPLETED','EXPIRED','REVOKED')",
            name="ck_account_merge_status",
        ),
        sa.CheckConstraint(
            "token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_account_merge_token_digest",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_account_merge_expiry",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_account_merge_completion",
        ),
        sa.CheckConstraint("version > 0", name="ck_account_merge_version"),
        sa.UniqueConstraint("token_digest", name="uq_account_merge_token_digest"),
        sa.Index(
            "uq_account_merge_open_pair",
            "source_actor_id",
            "target_actor_id",
            unique=True,
            postgresql_where=sa.text("status IN ('PENDING_CONFIRMATION','PENDING_REVIEW')"),
        ),
        sa.Index("idx_account_merge_status_expiry", "status", "expires_at"),
    )

    token_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    source_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_external_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{SCHEMA_NAME}.external_identity.external_identity_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    target_external_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{SCHEMA_NAME}.external_identity.external_identity_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    target_app_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.app_session.app_session_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=sa.text("'PENDING_CONFIRMATION'"),
    )
    reason_code: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
