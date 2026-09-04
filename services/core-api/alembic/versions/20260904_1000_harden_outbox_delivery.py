"""harden outbox delivery leases, retry scheduling, and dead-letter metadata

Revision ID: b8d0f2a4c6e7
Revises: a7c9e1f3b5d6
Create Date: 2026-09-04 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8d0f2a4c6e7"
down_revision: str | Sequence[str] | None = "a7c9e1f3b5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"
TABLE = "outbox_event"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("lease_token", sa.UUID(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("last_dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("last_dead_letter_reason", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column(
            "redrive_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("last_redriven_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    # A pre-M-11 process could have died after writing PUBLISHING. Those rows
    # had no lease identity, so they cannot be safely completed and must be
    # made retryable before the lease-state constraint is installed.
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.{TABLE} "
            "SET delivery_status = 'FAILED', "
            "last_error = 'PUBLISHER_LEASE_MIGRATION_RECOVERY', "
            "next_attempt_at = now() "
            "WHERE delivery_status = 'PUBLISHING'"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.{TABLE} "
            "SET published_at = COALESCE(published_at, updated_at, created_at) "
            "WHERE delivery_status = 'PUBLISHED'"
        )
    )
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.{TABLE} "
            "SET last_dead_lettered_at = COALESCE(updated_at, created_at), "
            "last_dead_letter_reason = COALESCE(last_error, "
            "'PUBLISHER_ATTEMPT_LIMIT_REACHED') "
            "WHERE delivery_status = 'DEAD_LETTER'"
        )
    )

    op.create_check_constraint(
        "ck_outbox_lease_state",
        TABLE,
        "(delivery_status = 'PUBLISHING' AND lease_token IS NOT NULL "
        "AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
        "(delivery_status <> 'PUBLISHING' AND lease_token IS NULL "
        "AND lease_owner IS NULL AND lease_expires_at IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_outbox_published_at",
        TABLE,
        "delivery_status <> 'PUBLISHED' OR published_at IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_outbox_dead_letter_metadata",
        TABLE,
        "delivery_status <> 'DEAD_LETTER' OR "
        "(last_dead_lettered_at IS NOT NULL AND last_dead_letter_reason IS NOT NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_outbox_redrive_count",
        TABLE,
        "redrive_count >= 0",
        schema=SCHEMA,
    )

    op.drop_index("idx_outbox_pending", table_name=TABLE, schema=SCHEMA)
    op.create_index(
        "idx_outbox_delivery_due",
        TABLE,
        ["delivery_status", "next_attempt_at", "created_at", "outbox_event_id"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("delivery_status IN ('PENDING','FAILED')"),
    )
    op.create_index(
        "idx_outbox_expired_lease",
        TABLE,
        ["lease_expires_at", "outbox_event_id"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("delivery_status = 'PUBLISHING'"),
    )
    op.create_index(
        "idx_outbox_dead_letter",
        TABLE,
        ["last_dead_lettered_at", "outbox_event_id"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("delivery_status = 'DEAD_LETTER'"),
    )


def downgrade() -> None:
    # A lease cannot be represented by the pre-M-11 schema. Make any in-flight
    # row retryable before dropping its ownership metadata.
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.{TABLE} "
            "SET delivery_status = 'FAILED', "
            "last_error = 'PUBLISHER_LEASE_DOWNGRADE_RECOVERY', "
            "lease_token = NULL, lease_owner = NULL, lease_expires_at = NULL "
            "WHERE delivery_status = 'PUBLISHING'"
        )
    )
    op.drop_index("idx_outbox_dead_letter", table_name=TABLE, schema=SCHEMA)
    op.drop_index("idx_outbox_expired_lease", table_name=TABLE, schema=SCHEMA)
    op.drop_index("idx_outbox_delivery_due", table_name=TABLE, schema=SCHEMA)
    op.create_index(
        "idx_outbox_pending",
        TABLE,
        ["delivery_status", "created_at"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("delivery_status IN ('PENDING','FAILED')"),
    )
    op.drop_constraint("ck_outbox_redrive_count", TABLE, schema=SCHEMA, type_="check")
    op.drop_constraint("ck_outbox_dead_letter_metadata", TABLE, schema=SCHEMA, type_="check")
    op.drop_constraint("ck_outbox_published_at", TABLE, schema=SCHEMA, type_="check")
    op.drop_constraint("ck_outbox_lease_state", TABLE, schema=SCHEMA, type_="check")
    for column_name in (
        "last_redriven_at",
        "redrive_count",
        "last_dead_letter_reason",
        "last_dead_lettered_at",
        "lease_expires_at",
        "lease_owner",
        "lease_token",
        "last_attempt_at",
        "next_attempt_at",
    ):
        op.drop_column(TABLE, column_name, schema=SCHEMA)
