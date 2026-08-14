"""Kinsun-owned email authenticator persistence models."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, VersionedMixin


class KinsunEmailChallenge(BaseModel, VersionedMixin):
    """Short-lived, bounded verification challenge for one normalized email."""

    __tablename__ = "kinsun_email_challenge"
    __pk_name__ = "kinsun_email_challenge_id"
    __table_args__ = (
        sa.CheckConstraint(
            "token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_kinsun_email_challenge_token_digest",
        ),
        sa.CheckConstraint(
            "external_subject_digest ~ '^[0-9a-f]{64}$'",
            name="ck_kinsun_email_challenge_subject_digest",
        ),
        sa.CheckConstraint(
            "code_digest ~ '^[0-9a-f]{64}$'",
            name="ck_kinsun_email_challenge_code_digest",
        ),
        sa.CheckConstraint(
            "digest_key_version > 0",
            name="ck_kinsun_email_challenge_key_version",
        ),
        sa.CheckConstraint(
            "intent IN ('ELDER','FAMILY','STAFF')",
            name="ck_kinsun_email_challenge_intent",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','CONSUMED','EXPIRED','LOCKED','REVOKED')",
            name="ck_kinsun_email_challenge_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="ck_kinsun_email_challenge_attempts",
        ),
        sa.CheckConstraint(
            "length(email_address) BETWEEN 3 AND 254",
            name="ck_kinsun_email_challenge_email",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_kinsun_email_challenge_expiry",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND consumed_at IS NULL AND invalidated_at IS NULL) OR "
            "(status = 'CONSUMED' AND consumed_at IS NOT NULL AND invalidated_at IS NULL) OR "
            "(status IN ('EXPIRED','LOCKED','REVOKED') AND consumed_at IS NULL "
            "AND invalidated_at IS NOT NULL)",
            name="ck_kinsun_email_challenge_lifecycle",
        ),
        sa.CheckConstraint("version > 0", name="ck_kinsun_email_challenge_version"),
        sa.UniqueConstraint(
            "token_digest",
            name="uq_kinsun_email_challenge_token_digest",
        ),
        sa.Index(
            "uq_kinsun_email_challenge_pending_subject",
            "digest_key_version",
            "external_subject_digest",
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
        sa.Index(
            "idx_kinsun_email_challenge_expiry",
            "status",
            "expires_at",
        ),
    )

    token_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    email_address: Mapped[str] = mapped_column(String(254), nullable=False)
    external_subject_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    digest_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    code_digest: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
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
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
