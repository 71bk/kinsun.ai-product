"""add auditable memory confirmation evidence

Revision ID: a7c34d91e6f2
Revises: 5fb8c2e9d014
Create Date: 2026-07-31 14:00:00+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c34d91e6f2"
down_revision: Union[str, Sequence[str], None] = "5fb8c2e9d014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory",
        sa.Column("confirmation_method", sa.String(length=32), nullable=True),
        schema="eldercare_ai",
    )
    op.add_column(
        "memory",
        sa.Column("confirmation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="eldercare_ai",
    )
    op.add_column(
        "memory",
        sa.Column("confirmation_evidence_ref", sa.String(length=300), nullable=True),
        schema="eldercare_ai",
    )
    op.create_foreign_key(
        "fk_memory_confirmation_session",
        "memory",
        "conversation_session",
        ["confirmation_session_id"],
        ["session_id"],
        source_schema="eldercare_ai",
        referent_schema="eldercare_ai",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_memory_confirmation_method",
        "memory",
        "confirmation_method IS NULL OR confirmation_method IN "
        "('VOICE', 'CAREGIVER_REVIEW', 'LEGAL_REPRESENTATIVE')",
        schema="eldercare_ai",
    )
    op.create_check_constraint(
        "ck_memory_voice_confirmation_evidence",
        "memory",
        "confirmation_method <> 'VOICE' OR "
        "(confirmation_session_id IS NOT NULL AND confirmation_evidence_ref IS NOT NULL)",
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_memory_voice_confirmation_evidence",
        "memory",
        schema="eldercare_ai",
        type_="check",
    )
    op.drop_constraint(
        "ck_memory_confirmation_method",
        "memory",
        schema="eldercare_ai",
        type_="check",
    )
    op.drop_constraint(
        "fk_memory_confirmation_session",
        "memory",
        schema="eldercare_ai",
        type_="foreignkey",
    )
    op.drop_column("memory", "confirmation_evidence_ref", schema="eldercare_ai")
    op.drop_column("memory", "confirmation_session_id", schema="eldercare_ai")
    op.drop_column("memory", "confirmation_method", schema="eldercare_ai")
