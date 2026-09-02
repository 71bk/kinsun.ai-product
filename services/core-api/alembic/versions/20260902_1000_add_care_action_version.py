"""add optimistic versioning to care actions

Revision ID: c9d3e5f7a809
Revises: b8c2d4e5f607
Create Date: 2026-09-02 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d3e5f7a809"
down_revision: str | Sequence[str] | None = "b8c2d4e5f607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "care_action",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_care_action_version_positive",
        "care_action",
        "version >= 1",
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            f"COMMENT ON COLUMN {SCHEMA}.care_action.version "
            "IS 'Optimistic concurrency version for professional care-action updates'"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_care_action_version_positive",
        "care_action",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("care_action", "version", schema=SCHEMA)
