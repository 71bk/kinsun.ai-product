"""add provider-neutral identity and application session foundation

Revision ID: a4c7e9b2d610
Revises: 4f8a2c1d9e60
Create Date: 2026-08-11 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4c7e9b2d610"
down_revision: str | Sequence[str] | None = "4f8a2c1d9e60"
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
        "provider IN ('GOOGLE','LINE')",
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        "uq_external_identity_id_actor",
        "external_identity",
        ["external_identity_id", "actor_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "app_session",
        sa.Column(
            "app_session_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_digest", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "external_identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column(
            "authenticated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
                f"{SCHEMA}.external_identity.external_identity_id",
                f"{SCHEMA}.external_identity.actor_id",
            ],
            name="fk_app_session_external_identity_actor",
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_app_session_actor_status",
        "app_session",
        ["actor_id", "status", "absolute_expires_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "idx_app_session_expiry",
        "app_session",
        ["status", "idle_expires_at", "absolute_expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM {SCHEMA}.app_session) THEN
            RAISE EXCEPTION
              'cannot downgrade while application sessions exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_index(
        "idx_app_session_expiry",
        table_name="app_session",
        schema=SCHEMA,
    )
    op.drop_index(
        "idx_app_session_actor_status",
        table_name="app_session",
        schema=SCHEMA,
    )
    op.drop_table("app_session", schema=SCHEMA)

    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM {SCHEMA}.external_identity
            WHERE provider <> 'LINE'
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while non-LINE external identities exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "ck_external_identity_provider",
        "external_identity",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "uq_external_identity_id_actor",
        "external_identity",
        schema=SCHEMA,
        type_="unique",
    )
    op.create_check_constraint(
        "ck_external_identity_provider",
        "external_identity",
        "provider = 'LINE'",
        schema=SCHEMA,
    )
