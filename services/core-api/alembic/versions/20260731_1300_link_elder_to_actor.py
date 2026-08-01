"""link elder profile to its authenticated actor

Revision ID: 5fb8c2e9d014
Revises: 8d9f27c4a6b1
Create Date: 2026-07-31 13:00:00+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5fb8c2e9d014"
down_revision: Union[str, Sequence[str], None] = "8d9f27c4a6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "elder",
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema="eldercare_ai",
    )
    op.create_foreign_key(
        "fk_elder_actor_id_actor",
        "elder",
        "actor",
        ["actor_id"],
        ["actor_id"],
        source_schema="eldercare_ai",
        referent_schema="eldercare_ai",
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_elder_actor_id",
        "elder",
        ["actor_id"],
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_elder_actor_id",
        "elder",
        schema="eldercare_ai",
        type_="unique",
    )
    op.drop_constraint(
        "fk_elder_actor_id_actor",
        "elder",
        schema="eldercare_ai",
        type_="foreignkey",
    )
    op.drop_column("elder", "actor_id", schema="eldercare_ai")
