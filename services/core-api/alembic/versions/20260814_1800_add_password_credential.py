"""add Kinsun Argon2id password credential

Revision ID: b8d0e4f6a213
Revises: a7c9d3e5f102
Create Date: 2026-08-14 18:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8d0e4f6a213"
down_revision: str | Sequence[str] | None = "a7c9d3e5f102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_table(
        "password_credential",
        sa.Column(
            "password_credential_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "algorithm",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ARGON2ID'"),
        ),
        sa.Column("parameter_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column(
            "failed_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
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
        schema=SCHEMA,
    )
    op.create_index(
        "idx_password_credential_status_lock",
        "password_credential",
        ["status", "locked_until"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_password_credential_status_lock",
        table_name="password_credential",
        schema=SCHEMA,
    )
    op.drop_table("password_credential", schema=SCHEMA)
