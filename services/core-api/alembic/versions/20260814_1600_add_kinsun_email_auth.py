"""add Kinsun-owned email authentication foundation

Revision ID: a7c9d3e5f102
Revises: e4b8c2d6a190
Create Date: 2026-08-14 16:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c9d3e5f102"
down_revision: str | Sequence[str] | None = "e4b8c2d6a190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.drop_constraint(
        "ck_external_identity_provider",
        "external_identity",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_external_identity_provider",
        "external_identity",
        "provider IN ('KINSUN','GOOGLE','LINE')",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_pending_external_identity_provider",
        "pending_external_identity",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_pending_external_identity_provider",
        "pending_external_identity",
        "provider IN ('KINSUN','GOOGLE','LINE')",
        schema=SCHEMA,
    )

    op.create_table(
        "kinsun_email_challenge",
        sa.Column(
            "kinsun_email_challenge_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("email_address", sa.String(length=254), nullable=False),
        sa.Column("external_subject_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("digest_key_version", sa.Integer(), nullable=False),
        sa.Column("code_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("intent", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
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
        sa.Column("max_attempts", sa.Integer(), nullable=False),
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
        schema=SCHEMA,
    )
    op.create_index(
        "uq_kinsun_email_challenge_pending_subject",
        "kinsun_email_challenge",
        ["digest_key_version", "external_subject_digest"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_kinsun_email_challenge_expiry",
        "kinsun_email_challenge",
        ["status", "expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM {SCHEMA}.external_identity WHERE provider = 'KINSUN'
          ) OR EXISTS (
            SELECT 1 FROM {SCHEMA}.pending_external_identity WHERE provider = 'KINSUN'
          ) THEN
            RAISE EXCEPTION 'cannot downgrade while Kinsun identities exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_index(
        "idx_kinsun_email_challenge_expiry",
        table_name="kinsun_email_challenge",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_kinsun_email_challenge_pending_subject",
        table_name="kinsun_email_challenge",
        schema=SCHEMA,
    )
    op.drop_table("kinsun_email_challenge", schema=SCHEMA)

    op.drop_constraint(
        "ck_pending_external_identity_provider",
        "pending_external_identity",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_pending_external_identity_provider",
        "pending_external_identity",
        "provider IN ('GOOGLE','LINE')",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_external_identity_provider",
        "external_identity",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_external_identity_provider",
        "external_identity",
        "provider IN ('GOOGLE','LINE')",
        schema=SCHEMA,
    )
