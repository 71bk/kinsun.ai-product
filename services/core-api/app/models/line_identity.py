"""LINE account-linking persistence models.

Raw LINE identifiers are never stored in plaintext. Lookup uses a keyed
digest, while the optional encrypted subject exists only for controlled push
delivery.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, VersionedMixin


class ExternalIdentity(BaseModel, VersionedMixin):
    """One active LINE identity mapped to one existing Core actor."""

    __tablename__ = "external_identity"
    __pk_name__ = "external_identity_id"
    __table_args__ = (
        sa.CheckConstraint("provider = 'LINE'", name="ck_external_identity_provider"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUSPENDED','REVOKED')",
            name="ck_external_identity_status",
        ),
        sa.CheckConstraint(
            "digest_key_version > 0",
            name="ck_external_identity_digest_key_version",
        ),
        sa.CheckConstraint("version > 0", name="ck_external_identity_version"),
        sa.CheckConstraint(
            "(status = 'REVOKED' AND revoked_at IS NOT NULL) OR (status <> 'REVOKED')",
            name="ck_external_identity_revoked_at",
        ),
        sa.Index(
            "uq_external_identity_active_subject",
            "provider",
            "digest_key_version",
            "external_subject_digest",
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        ),
        sa.Index(
            "uq_external_identity_active_actor",
            "provider",
            "actor_id",
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        ),
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_subject_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    digest_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'ACTIVE'"),
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    encrypted_external_subject: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LineLinkChallenge(BaseModel, TenantScopedMixin, VersionedMixin):
    """Short-lived nonce binding an authenticated actor to LINE."""

    __tablename__ = "line_link_challenge"
    __pk_name__ = "line_link_challenge_id"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('PENDING','REDEEMED','FAILED','EXPIRED','REVOKED')",
            name="ck_line_link_challenge_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="ck_line_link_challenge_attempts",
        ),
        sa.CheckConstraint("version > 0", name="ck_line_link_challenge_version"),
        sa.CheckConstraint(
            "(status = 'REDEEMED' AND redeemed_external_identity_id IS NOT NULL "
            "AND redeemed_at IS NOT NULL) OR (status <> 'REDEEMED')",
            name="ck_line_link_challenge_redeemed_fields",
        ),
        sa.UniqueConstraint("nonce_digest", name="uq_line_link_challenge_nonce_digest"),
        sa.Index(
            "uq_line_link_challenge_pending_actor",
            "actor_id",
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
        sa.Index(
            "idx_line_link_challenge_actor_status",
            "actor_id",
            "tenant_id",
            "status",
            "expires_at",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id", ondelete="RESTRICT"),
        nullable=False,
    )
    elder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id", ondelete="RESTRICT"),
        nullable=True,
    )
    nonce_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'PENDING'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("3"),
    )
    redeemed_external_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{SCHEMA_NAME}.external_identity.external_identity_id",
            ondelete="RESTRICT",
        ),
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LineWebhookReceipt(BaseModel):
    """Idempotency receipt for one LINE webhook event object."""

    __tablename__ = "line_webhook_receipt"
    __pk_name__ = "line_webhook_receipt_id"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('PROCESSING','COMPLETED','FAILED')",
            name="ck_line_webhook_receipt_status",
        ),
        sa.CheckConstraint(
            "attempt_count > 0",
            name="ck_line_webhook_receipt_attempt_count",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND processed_at IS NOT NULL) " "OR (status <> 'COMPLETED')",
            name="ck_line_webhook_receipt_processed_at",
        ),
        sa.UniqueConstraint("webhook_event_id", name="uq_line_webhook_receipt_event_id"),
        sa.Index("idx_line_webhook_receipt_status", "status", "created_at"),
    )

    webhook_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=sa.text("'PROCESSING'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("1"),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
