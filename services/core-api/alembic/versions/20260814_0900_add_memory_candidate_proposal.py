"""add review-gated memory candidate proposal metadata

Revision ID: c8a4e1f7b2d0
Revises: f2c6d8a1e490
Create Date: 2026-08-14 09:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8a4e1f7b2d0"
down_revision: str | Sequence[str] | None = "f2c6d8a1e490"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "care_event_version",
        sa.Column(
            "memory_candidate_proposal", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "memory_version",
        sa.Column("confirmation_question", sa.String(length=300), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "memory_version",
        sa.Column("extractor_version", sa.String(length=80), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "memory_version",
        sa.Column("extraction_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_version_extraction_confidence_range",
        "memory_version",
        "extraction_confidence IS NULL OR "
        "(extraction_confidence >= 0.0000 AND extraction_confidence <= 1.0000)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM {SCHEMA}.care_event_version
            WHERE memory_candidate_proposal IS NOT NULL
          ) OR EXISTS (
            SELECT 1 FROM {SCHEMA}.memory_version
            WHERE confirmation_question IS NOT NULL
               OR extractor_version IS NOT NULL
               OR extraction_confidence IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'cannot remove memory proposal metadata while data exists';
          END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "ck_memory_version_extraction_confidence_range",
        "memory_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("memory_version", "extraction_confidence", schema=SCHEMA)
    op.drop_column("memory_version", "extractor_version", schema=SCHEMA)
    op.drop_column("memory_version", "confirmation_question", schema=SCHEMA)
    op.drop_column("care_event_version", "memory_candidate_proposal", schema=SCHEMA)
