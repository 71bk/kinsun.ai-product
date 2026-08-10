"""add LINE account-linking and delivery foundation

Revision ID: 6e1f9a3c7d42
Revises: 9b2e4c6d8f10
Create Date: 2026-08-10 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6e1f9a3c7d42"
down_revision: str | Sequence[str] | None = "9b2e4c6d8f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "external_identity",
        sa.Column(
            "external_identity_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_subject_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("digest_key_version", sa.Integer(), nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encrypted_external_subject", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_timestamps(),
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
        schema="eldercare_ai",
    )
    op.create_index(
        "uq_external_identity_active_subject",
        "external_identity",
        ["provider", "digest_key_version", "external_subject_digest"],
        unique=True,
        schema="eldercare_ai",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_external_identity_active_actor",
        "external_identity",
        ["provider", "actor_id"],
        unique=True,
        schema="eldercare_ai",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "line_link_challenge",
        sa.Column(
            "line_link_challenge_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.tenant.tenant_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "elder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eldercare_ai.elder.elder_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("nonce_digest", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "redeemed_external_identity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "eldercare_ai.external_identity.external_identity_id",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_timestamps(),
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
        schema="eldercare_ai",
    )
    op.create_index(
        "uq_line_link_challenge_pending_actor",
        "line_link_challenge",
        ["actor_id"],
        unique=True,
        schema="eldercare_ai",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "idx_line_link_challenge_actor_status",
        "line_link_challenge",
        ["actor_id", "tenant_id", "status", "expires_at"],
        schema="eldercare_ai",
    )

    op.create_table(
        "line_webhook_receipt",
        sa.Column(
            "line_webhook_receipt_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("webhook_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'PROCESSING'"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('PROCESSING','COMPLETED','FAILED')",
            name="ck_line_webhook_receipt_status",
        ),
        sa.CheckConstraint(
            "attempt_count > 0",
            name="ck_line_webhook_receipt_attempt_count",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND processed_at IS NOT NULL) "
            "OR (status <> 'COMPLETED')",
            name="ck_line_webhook_receipt_processed_at",
        ),
        sa.UniqueConstraint("webhook_event_id", name="uq_line_webhook_receipt_event_id"),
        schema="eldercare_ai",
    )
    op.create_index(
        "idx_line_webhook_receipt_status",
        "line_webhook_receipt",
        ["status", "created_at"],
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_line_webhook_receipt_status",
        table_name="line_webhook_receipt",
        schema="eldercare_ai",
    )
    op.drop_table("line_webhook_receipt", schema="eldercare_ai")

    op.drop_index(
        "idx_line_link_challenge_actor_status",
        table_name="line_link_challenge",
        schema="eldercare_ai",
    )
    op.drop_index(
        "uq_line_link_challenge_pending_actor",
        table_name="line_link_challenge",
        schema="eldercare_ai",
    )
    op.drop_table("line_link_challenge", schema="eldercare_ai")

    op.drop_index(
        "uq_external_identity_active_actor",
        table_name="external_identity",
        schema="eldercare_ai",
    )
    op.drop_index(
        "uq_external_identity_active_subject",
        table_name="external_identity",
        schema="eldercare_ai",
    )
    op.drop_table("external_identity", schema="eldercare_ai")
