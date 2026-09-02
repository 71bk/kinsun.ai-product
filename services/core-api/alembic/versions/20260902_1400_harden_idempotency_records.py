"""harden idempotency claims and response replay

Revision ID: d0e4f6a8b901
Revises: c9d3e5f7a809
Create Date: 2026-09-02 14:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d0e4f6a8b901"
down_revision: str | Sequence[str] | None = "c9d3e5f7a809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.drop_constraint(
        "agent_tool_call_idempotency_key_fkey",
        "agent_tool_call",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "agent_tool_call_idempotency_key_fkey",
        "agent_tool_call",
        "idempotency_record",
        ["idempotency_key"],
        ["idempotency_key"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.add_column(
        "idempotency_record",
        sa.Column(
            "response_body",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "idempotency_record",
        sa.Column(
            "key_format_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "idempotency_record",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_idempotency_key_format_version",
        "idempotency_record",
        "key_format_version IN (1, 2)",
        schema=SCHEMA,
    )
    op.create_index(
        "idx_idempotency_record_expiry",
        "idempotency_record",
        ["expires_at"],
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            f"COMMENT ON COLUMN {SCHEMA}.idempotency_record.response_body "
            "IS 'Bounded immutable JSON response snapshot retained only until expires_at'"
        )
    )
    op.execute(
        sa.text(
            f"COMMENT ON COLUMN {SCHEMA}.idempotency_record.key_format_version "
            "IS '1 is legacy raw key; 2 is tenant/actor-scoped SHA-256 storage key'"
        )
    )
    op.execute(
        sa.text(
            f"COMMENT ON COLUMN {SCHEMA}.idempotency_record.completed_at "
            "IS 'Time at which the immutable response snapshot was finalized'"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "idx_idempotency_record_expiry",
        table_name="idempotency_record",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_idempotency_key_format_version",
        "idempotency_record",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("idempotency_record", "completed_at", schema=SCHEMA)
    op.drop_column("idempotency_record", "key_format_version", schema=SCHEMA)
    op.drop_column("idempotency_record", "response_body", schema=SCHEMA)
    op.drop_constraint(
        "agent_tool_call_idempotency_key_fkey",
        "agent_tool_call",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "agent_tool_call_idempotency_key_fkey",
        "agent_tool_call",
        "idempotency_record",
        ["idempotency_key"],
        ["idempotency_key"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
