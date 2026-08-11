"""add pending external identity handoff foundation

Revision ID: c8d4f1a7e320
Revises: a4c7e9b2d610
Create Date: 2026-08-11 15:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8d4f1a7e320"
down_revision: str | Sequence[str] | None = "a4c7e9b2d610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_table(
        "pending_external_identity",
        sa.Column(
            "pending_external_identity_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_subject_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("digest_key_version", sa.Integer(), nullable=False),
        sa.Column("verified_email", sa.String(length=254), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("intent", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
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
        schema=SCHEMA,
    )
    op.create_index(
        "uq_pending_external_identity_pending_subject",
        "pending_external_identity",
        ["provider", "digest_key_version", "external_subject_digest"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_pending_external_identity_expiry",
        "pending_external_identity",
        ["status", "expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM {SCHEMA}.pending_external_identity) THEN
            RAISE EXCEPTION
              'cannot downgrade while pending external identities exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_index(
        "idx_pending_external_identity_expiry",
        table_name="pending_external_identity",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_pending_external_identity_pending_subject",
        table_name="pending_external_identity",
        schema=SCHEMA,
    )
    op.drop_table("pending_external_identity", schema=SCHEMA)
