"""retire Cognito actor identity column

Revision ID: f2c6d8a1e490
Revises: e7b3a9c4d820
Create Date: 2026-08-13 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2c6d8a1e490"
down_revision: str | Sequence[str] | None = "e7b3a9c4d820"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    # The owner confirmed that no Cognito accounts exist. Refuse to discard an
    # unexpected legacy binding if an environment contradicts that inventory.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM {SCHEMA}.actor
            WHERE cognito_sub IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'cannot retire Cognito while actor.cognito_sub data exists';
          END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "uq_actor_cognito_sub",
        "actor",
        schema=SCHEMA,
        type_="unique",
    )
    op.drop_column("actor", "cognito_sub", schema=SCHEMA)


def downgrade() -> None:
    op.add_column(
        "actor",
        sa.Column("cognito_sub", sa.String(length=200), nullable=True),
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        "uq_actor_cognito_sub",
        "actor",
        ["cognito_sub"],
        schema=SCHEMA,
    )
    op.execute(
        f"""
        COMMENT ON COLUMN {SCHEMA}.actor.cognito_sub IS
        'Legacy external identity subject restored only for migration rollback.';
        """
    )
