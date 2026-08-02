"""add encrypted LINE push destination and family link support

Revision ID: b8d5f3a21c74
Revises: a7c4e2d19f60
Create Date: 2026-08-02 02:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d5f3a21c74"
down_revision: str | Sequence[str] | None = "a7c4e2d19f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_identity",
        sa.Column("encrypted_external_subject", sa.Text(), nullable=True),
        schema="eldercare_ai",
    )
    op.alter_column(
        "line_link_challenge",
        "elder_id",
        existing_type=sa.UUID(),
        nullable=True,
        schema="eldercare_ai",
    )


def downgrade() -> None:
    # FAMILY_MEMBER challenges cannot fit the former ELDER-only shape.
    op.execute("DELETE FROM eldercare_ai.line_link_challenge WHERE elder_id IS NULL")
    op.alter_column(
        "line_link_challenge",
        "elder_id",
        existing_type=sa.UUID(),
        nullable=False,
        schema="eldercare_ai",
    )
    op.drop_column(
        "external_identity",
        "encrypted_external_subject",
        schema="eldercare_ai",
    )
