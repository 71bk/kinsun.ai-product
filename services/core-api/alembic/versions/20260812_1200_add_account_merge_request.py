"""add explicit account merge request

Revision ID: e7b3a9c4d820
Revises: c8d4f1a7e320
Create Date: 2026-08-12 12:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7b3a9c4d820"
down_revision: str | Sequence[str] | None = "c8d4f1a7e320"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_table(
        "account_merge_request",
        sa.Column(
            "account_merge_request_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_digest", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "source_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_external_identity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{SCHEMA}.external_identity.external_identity_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "target_external_identity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{SCHEMA}.external_identity.external_identity_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "target_app_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.app_session.app_session_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING_CONFIRMATION'"),
        ),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
        sa.CheckConstraint("expires_at > created_at", name="ck_account_merge_expiry"),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_account_merge_completion",
        ),
        sa.CheckConstraint("version > 0", name="ck_account_merge_version"),
        sa.UniqueConstraint("token_digest", name="uq_account_merge_token_digest"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_account_merge_open_pair",
        "account_merge_request",
        ["source_actor_id", "target_actor_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING_CONFIRMATION','PENDING_REVIEW')"),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_account_merge_status_expiry",
        "account_merge_request",
        ["status", "expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM {SCHEMA}.account_merge_request) THEN
            RAISE EXCEPTION 'cannot downgrade while account merge requests exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_index(
        "idx_account_merge_status_expiry",
        table_name="account_merge_request",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_account_merge_open_pair",
        table_name="account_merge_request",
        schema=SCHEMA,
    )
    op.drop_table("account_merge_request", schema=SCHEMA)
