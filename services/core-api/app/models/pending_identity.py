"""Short-lived external identities awaiting an explicit onboarding decision."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, VersionedMixin


class PendingExternalIdentity(BaseModel, VersionedMixin):
    """A verified provider subject that is not yet linked to a Core actor.

    The provider subject and raw pending credential are never persisted. The
    verified email and display name are retained only for the short onboarding
    window and must not be used to auto-link an existing account.
    """

    __tablename__ = "pending_external_identity"
    __pk_name__ = "pending_external_identity_id"
    __table_args__ = (
        sa.CheckConstraint(
            "provider IN ('GOOGLE','LINE')",
            name="ck_pending_external_identity_provider",
        ),
        sa.CheckConstraint(
            "token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pending_external_identity_token_digest",
        ),
        sa.CheckConstraint(
            "external_subject_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pending_external_identity_subject_digest",
        ),
        sa.CheckConstraint(
            "digest_key_version > 0",
            name="ck_pending_external_identity_digest_key_version",
        ),
        sa.CheckConstraint(
            "intent IN ('ELDER','FAMILY','STAFF')",
            name="ck_pending_external_identity_intent",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','CONSUMED','EXPIRED','REVOKED')",
            name="ck_pending_external_identity_status",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_pending_external_identity_expiry",
        ),
        sa.CheckConstraint(
            "(verified_email IS NULL OR length(verified_email) BETWEEN 3 AND 254)",
            name="ck_pending_external_identity_email",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND consumed_at IS NULL AND invalidated_at IS NULL) OR "
            "(status = 'CONSUMED' AND consumed_at IS NOT NULL AND invalidated_at IS NULL) OR "
            "(status IN ('EXPIRED','REVOKED') AND consumed_at IS NULL "
            "AND invalidated_at IS NOT NULL)",
            name="ck_pending_external_identity_lifecycle",
        ),
        sa.CheckConstraint("version > 0", name="ck_pending_external_identity_version"),
        sa.UniqueConstraint(
            "token_digest",
            name="uq_pending_external_identity_token_digest",
        ),
        sa.Index(
            "uq_pending_external_identity_pending_subject",
            "provider",
            "digest_key_version",
            "external_subject_digest",
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
        sa.Index(
            "idx_pending_external_identity_expiry",
            "status",
            "expires_at",
        ),
    )

    token_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_subject_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    digest_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_email: Mapped[str | None] = mapped_column(String(254))
    display_name: Mapped[str | None] = mapped_column(String(120))
    intent: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'PENDING'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
