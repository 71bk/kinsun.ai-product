"""add explicit memory pending-confirmation state

Revision ID: e4b8c2d6a190
Revises: c8a4e1f7b2d0
Create Date: 2026-08-14 13:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e4b8c2d6a190"
down_revision: str | Sequence[str] | None = "c8a4e1f7b2d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.memory DROP CONSTRAINT IF EXISTS memory_status_check"
    )
    op.create_check_constraint(
        "ck_memory_status",
        "memory",
        "status IN ('CANDIDATE','PENDING_CONFIRMATION','CONFIRMED','ACTIVE',"
        "'DEFERRED','REJECTED','INACTIVE','DELETED')",
        schema=SCHEMA,
    )
    op.execute(
        f"UPDATE {SCHEMA}.memory SET status = 'PENDING_CONFIRMATION' "
        "WHERE status = 'CANDIDATE'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE {SCHEMA}.memory SET status = 'CANDIDATE' "
        "WHERE status = 'PENDING_CONFIRMATION'"
    )
    op.drop_constraint("ck_memory_status", "memory", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "memory_status_check",
        "memory",
        "status IN ('CANDIDATE','CONFIRMED','ACTIVE','DEFERRED','REJECTED',"
        "'INACTIVE','DELETED')",
        schema=SCHEMA,
    )
